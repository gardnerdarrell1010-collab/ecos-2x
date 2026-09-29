"""Offline PostgreSQL migration planner and transaction renderer. Never connects."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATTERN = re.compile(r"^(\d{6})_([a-z][a-z0-9_]+)\.sql$")


def inventory(directory):
    result = []
    for path in sorted(directory.glob("*.sql")):
        match = PATTERN.fullmatch(path.name)
        if not match:
            raise ValueError("Invalid migration filename: " + path.name)
        data = path.read_bytes()
        sql = data.decode("utf-8")
        if re.search(r"(?im)^\s*(begin|commit|rollback)\s*;|^\s*\\", sql):
            raise ValueError("Migration cannot control transactions or psql commands")
        result.append({"version": int(match[1]), "name": path.name, "sha256": hashlib.sha256(data).hexdigest(), "sql": sql})
    if [item["version"] for item in result] != list(range(1, len(result) + 1)):
        raise ValueError("Migration versions must be contiguous and unique starting at 1")
    return result


def plan(migrations, applied):
    if [r["version"] for r in applied] != list(range(1, len(applied) + 1)):
        raise ValueError("Applied history is not a contiguous prefix")
    if len(applied) > len(migrations):
        raise ValueError("Unknown applied migration")
    for prior, local in zip(applied, migrations):
        if any(prior[key] != local[key] for key in ("version", "name", "sha256")):
            raise ValueError("Applied migration drift")
    return migrations[len(applied):]


def render(migrations):
    if not migrations:
        raise ValueError("No migration inventory")
    sql = ["-- REVIEW ONLY: Phase 0 never executes this file.", "\\set ON_ERROR_STOP on", "begin;",
        "select pg_advisory_xact_lock(684026, 2);",
        "create schema if not exists ecos_meta;",
        "revoke all on schema ecos_meta from public;",
        "create table if not exists ecos_meta.schema_migration (version bigint primary key, name text not null unique, sha256 text not null check (sha256 ~ '^[a-f0-9]{64}$'), applied_at timestamptz not null default clock_timestamp());",
        "revoke all on ecos_meta.schema_migration from public;",
        "do $history$ begin if exists (select 1 from ecos_meta.schema_migration having count(*) <> coalesce(max(version), 0) or min(version) <> 1) then raise exception 'Non-contiguous migration history'; end if; end $history$;",
        f"do $history$ begin if exists (select 1 from ecos_meta.schema_migration where version > {len(migrations)} or version < 1) then raise exception 'Unknown migration version'; end if; end $history$;"]
    for migration in migrations:
        version, name, digest, body = (migration[k] for k in ("version", "name", "sha256", "sql"))
        tag = "$migration_body_" + digest[:16] + "$"
        if tag in body or "$migration_gate$" in body:
            raise ValueError("SQL delimiter conflict")
        sql.append(f"""do $migration_gate$
begin
  if exists (select 1 from ecos_meta.schema_migration where version = {version}) then
    if not exists (select 1 from ecos_meta.schema_migration where version = {version} and name = '{name}' and sha256 = '{digest}') then
      raise exception 'Migration drift at version {version}';
    end if;
  else
    execute {tag}{body}{tag};
    insert into ecos_meta.schema_migration(version, name, sha256) values ({version}, '{name}', '{digest}');
  end if;
end $migration_gate$;""")
    return "\n".join(sql + ["commit;", ""])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["plan", "render"])
    parser.add_argument("--applied-history", type=Path)
    args = parser.parse_args()
    migrations = inventory(ROOT / "db/migrations")
    if args.command == "render":
        if args.applied_history:
            parser.error("render validates live history inside its future transaction; no history file accepted")
        print(render(migrations))
    else:
        applied = json.loads(args.applied_history.read_text()) if args.applied_history else []
        print(json.dumps([{k:v for k,v in m.items() if k != "sql"} for m in plan(migrations, applied)], indent=2))
