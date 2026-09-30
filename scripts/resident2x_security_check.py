"""Secret-safe verification of new runtime and unchanged accepted SQL/contracts."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path[:0] = [str(ROOT), str(ROOT / "src"), str(ROOT / "scripts")]
from resident2x_acceptance import hosted_admin, resident1_snapshot
from runtime.resident2x.executor import Resident, save, now
from runtime.resident2x.connection import connection_factory


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    known_secrets = []
    # Exact comparison includes the canonical credential, never its value or digest in reports.
    hosted_admin(secret_sink=known_secrets.append)
    for name in ("database_password_file",):
        known_secrets.append(Path(config[name]).read_text().strip())
    known_secrets.extend(Path(path).read_text().strip() for path in config["secure_references"].values())
    names = subprocess.check_output(["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=ROOT).decode().split("\0")
    patterns = {"private_key": r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
        "github_token": r"gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,}",
        "openai_key": r"sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{32,}", "aws_access_key": r"AKIA[0-9A-Z]{16}",
        "database_url_password": r"postgres(?:ql)?://[^\s:/]+:[^\s@]+@", "supabase_key": r"sbp_[a-zA-Z0-9]{30,}"}
    findings = []
    for name in filter(None, names):
        if not (ROOT / name).is_file():
            continue
        text = (ROOT / name).read_text(encoding="utf-8", errors="replace")
        for label, pattern in patterns.items():
            if re.search(pattern, text):
                findings.append({"path": name, "pattern": label})
        if any(secret and secret in text for secret in known_secrets):
            findings.append({"path": name, "pattern": "exact_known_secret"})
    changed = subprocess.check_output(["git", "diff", "3c7e81fb07b793a085e4c7910ea16f94ba0f3157", "--name-only", "--", "db", "contracts"], cwd=ROOT).decode().strip()
    assert not changed, "accepted database/contracts changed"
    connect = connection_factory(config)
    denied = {}
    for label, query, parameters in (
        ("direct_table_read", "select * from ecos.work_occurrence limit 0", ()),
        ("private_operation", "select ecos_meta.apply_operation('fact.record','{}','{}')", ()),
        ("ungranted_object", "select ecos.read_record('task','00000000-0000-4000-8000-000000000001')", ())):
        try:
            with connect() as db:
                db.execute(query, parameters)
        except Exception as exc:
            denied[label] = getattr(exc, "sqlstate", None) == "42501"
        else:
            denied[label] = False
    runtime = Resident(config, connect, {})
    request = runtime.request({"observed_at": now(), "evidence_hash": "a" * 64, "reported_running": 0, "load_basis_points": 0}, "synthetic-spoof-denial")
    request["context"]["principal_id"] = "00000000-0000-4000-8000-000000000001"
    try:
        denied["spoofed_principal"] = runtime.client.operate("executor.heartbeat", request).get("code") == "forbidden"
    finally:
        runtime.client.close()
    result = {"status": "passed" if not findings and all(denied.values()) else "failed", "at": now(),
        "files_scanned": len(list(filter(None, names))), "findings": findings,
        "known_secret_exact_comparison": "passed" if not any(f['pattern']=='exact_known_secret' for f in findings) else "failed",
        "canonical_secret_retrieved_for_enrollment_only": True,
        "accepted_migrations_and_contracts": "byte-unchanged", "denials": denied,
        "resident1": resident1_snapshot(), "tls": config["database"]["sslmode"],
        "ca_file_sha256": hashlib.sha256(Path(config["database"]["sslrootcert"]).read_bytes()).hexdigest()}
    save(args.report, result)
    print(json.dumps(result))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
