"""Bind existing command instructions to PostgreSQL without changing command outcomes.

Administrative configuration only. Preserve the entire previous instruction text
and source provenance in a private receipt; never enable execution.
"""
import hashlib
import json
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'scripts'), str(ROOT / 'src')]
from configure_worker_instructions import off
from resident2x_acceptance import hosted_admin, secure_directory

BINDING = """ECOS 2.x COMMAND OPERATIONAL STORAGE BINDING
PostgreSQL ECOS 2.x is the sole current operational authority. Before executing this command, read ecos.bootstrap_package through the existing dedicated authenticated transport. Load its executor identity, instance, enabled/availability state, current capabilities and expiry/validity, active Command Registry and governed context. Executor capabilities are authoritative PostgreSQL lookup data, never inferred from a prompt, tool inventory, domain, memory or previous run. SQL work.next and stage_capability_requirement determine compatibility; normal claims, fences, dependencies, approvals and provider-effect governance still apply.
In the preserved command below, ECOS Master Database/workbook and operational ECOS Sheets references mean the corresponding current PostgreSQL governed records, schema metadata and relationships. Task Loop means work_definition, work_stage_definition, work_instruction_version and their occurrences; Run Control and leases mean execution_run, execution_event and work_claim; Tasks, Projects, communications, notifications, deliveries, artifacts and memory mean their existing typed PostgreSQL contracts. Read the current Command Registry from this bootstrap. Use existing governed operations and independently read back changes. Do not use archived raw migration rows as current state, and do not access the former ECOS Master Database for operational reads or writes. Legitimate external business spreadsheets and provider documents remain unchanged. If a required corresponding configuration, typed record or governed operation is unavailable, report that exact missing prerequisite; do not invent a replacement or report a successful load. Preserve all original command outcomes and non-storage responsibilities. This binding does not authorize activation or provider effects.

COMPLETE PRESERVED COMMAND INSTRUCTIONS (STORAGE REFERENCES RESOLVED AS ABOVE):
"""


def main():
    connect, _ = hosted_admin()
    receipt = ROOT / '.local' / ('command-storage-binding-' + uuid4().hex)
    secure_directory(receipt)
    with connect() as db:
        db.execute('select pg_advisory_xact_lock(684026,20)')
        off(db)
        rows = db.execute('select to_jsonb(c) from ecos.command_registry c where active order by command for update').fetchall()
        before = [r[0] for r in rows if not r[0]['ai_interpretation'].startswith(BINDING)]
        (receipt / 'before.json').write_text(json.dumps(before, indent=2), encoding='utf-8')
        for row in before:
            updated = db.execute('update ecos.command_registry set ai_interpretation=%s,record_version=record_version+1,updated_at=clock_timestamp() where command_id=%s and record_version=%s',
                (BINDING + row['ai_interpretation'], row['command_id'], row['record_version']))
            assert updated.rowcount == 1
        off(db)
    with connect() as db:
        off(db)
        for row in before:
            after = db.execute('select to_jsonb(c) from ecos.command_registry c where command_id=%s', (row['command_id'],)).fetchone()[0]
            assert after['ai_interpretation'] == BINDING + row['ai_interpretation']
            assert after['record_version'] == row['record_version'] + 1
            assert all(after[k] == v for k, v in row.items() if k not in ('ai_interpretation', 'record_version', 'updated_at'))
    result = {'commands_bound': len(before), 'independent_readback': 'PASS',
              'source_text_preserved': True, 'production_off': True,
              'binding_sha256': hashlib.sha256(BINDING.encode()).hexdigest()}
    (receipt / 'readback.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result))


if __name__ == '__main__':
    main()
