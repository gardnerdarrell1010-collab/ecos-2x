"""Explicit live C-01 harness. Never invoked by the offline test runner.

Requires an owner-configured ECOS_DEV_DSN (or libpq service reference), psycopg 3,
and a DEVELOPMENT login allowed to seed fixtures and SET ROLE executor.
No credentials are created or printed. Synthetic evidence is retained; temporary
bindings and role membership are removed even when contention fails.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from threading import Barrier
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tests.concurrency.acceptance import assert_claim_observations

PROJECT = "loonpojawpfagzobxoko"

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-ref", required=True, choices=[PROJECT])
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    dsn = os.environ.get("ECOS_DEV_DSN")
    if not dsn:
        parser.error("ECOS_DEV_DSN is not configured; C-01 remains pending")
    import psycopg
    from psycopg import sql
    from psycopg.types.json import Jsonb
    p, inst, ex, retry, definition, stage, occurrence = [str(uuid4()) for _ in range(7)]
    correlation = str(uuid4())
    def connect():
        conn = psycopg.connect(dsn, connect_timeout=15, options="-c statement_timeout=45000 -c lock_timeout=30000")
        host, user = conn.info.host, conn.info.user
        if host != f"db.{PROJECT}.supabase.co" and not (host.endswith(".pooler.supabase.com") and user.endswith("." + PROJECT)):
            conn.close()
            raise ValueError("Connection identity does not match the authorized project")
        if not 170000 <= conn.info.server_version < 180000:
            conn.close()
            raise ValueError("Expected PostgreSQL major version 17")
        return conn
    owner = None
    membership_added = False
    prepared = False
    report = {"gate":"C-01", "project_ref":PROJECT, "fixture_occurrence_id":occurrence,
              "correlation_id":correlation, "provider_calls_executed":False,
              "verified_at":datetime.now(timezone.utc).isoformat(), "status":"failed"}
    try:
        with connect() as db:
            identity = db.execute("select environment,authority,provider_effects_enabled from ecos_meta.database_identity").fetchone()
            if identity != ("development", "non_production", False):
                raise ValueError("Development database identity check failed")
            if db.execute("select exists(select 1 from ecos_meta.principal_binding where role_name='executor')").fetchone()[0]:
                raise ValueError("Executor binding already in use; no fixture changes made")
            prepared = True  # Cleanup also covers an indeterminate seed COMMIT.
            owner = db.execute("select current_user").fetchone()[0]
            member = db.execute("select pg_has_role(current_user,'executor','MEMBER')").fetchone()[0]
            if not member:
                db.execute(sql.SQL("grant executor to {}").format(sql.Identifier(owner)))
                membership_added = True
            db.execute("insert into ecos.executor(id,name,surface,enabled) values(%s,%s,'DATABASE_DETERMINISTIC',true)", (ex,"synthetic_contention_"+ex.replace('-','')))
            db.execute("insert into ecos.executor_instance(id,executor_id,boot_id,availability,principal_id) values(%s,%s,%s,'available',%s)", (inst,ex,str(uuid4()),p))
            db.execute("insert into ecos.retry_policy(id,max_attempts,initial_delay_seconds,max_delay_seconds,backoff_multiplier,jitter_basis_points,retryable_error_classes) values(%s,10,1,30,2,0,'[\"transient\"]')",(retry,))
            db.execute("insert into ecos.work_definition(id,name,definition_version,enabled,fulfillment_kind,retry_policy_id) values(%s,%s,1,true,'staged',%s)",(definition,"synthetic_contention_"+definition.replace('-',''),retry))
            db.execute("insert into ecos.work_stage_definition(id,work_definition_id,stage_key,kind,execution_surface,input_schema_id,result_schema_id,requires_approval) values(%s,%s,'synthetic_contention','deterministic','DATABASE_DETERMINISTIC','synthetic.input.v1','synthetic.result.v1',false)",(stage,definition))
            db.execute("insert into ecos.work_occurrence(id,work_definition_id,stage_definition_id,fulfillment_id,task_id,state,occurrence_key,due_at,retry_at,ready_override_at,priority_override) values(%s,%s,%s,%s,null,'ready',%s,clock_timestamp(),null,null,null)",(occurrence,definition,stage,str(uuid4()),"SYNTHETIC-CONTENTION-"+occurrence))
            db.execute("insert into ecos_meta.principal_binding values('executor',%s,%s,true)",(p,inst))
            db.execute("insert into ecos_meta.principal_operation values(%s,'work.claim')",(p,))
            db.execute("insert into ecos_meta.object_grant values(%s,'work_occurrence',%s)",(p,occurrence))
        prepared = True
        # Open all sessions before releasing the barrier. Distinct PIDs prove real
        # simultaneous server sessions; transaction-pool reuse cannot pass this test.
        barrier = Barrier(100, timeout=45)
        def contender(number):
            with connect() as db:
                db.execute("set local role executor")
                pid = db.execute("select pg_backend_pid()").fetchone()[0]
                db.execute("select ecos.record_heartbeat(clock_timestamp(),%s)",('c'*64,))
                barrier.wait()
                request = {"schema_version":"1.0.0", "context":{"principal_id":p,"executor_instance_id":inst,
                    "correlation_id":correlation,"causation_id":None,"idempotency_key":f"synthetic-contender-{number}"},
                    "arguments":{"executor_instance_id":inst,"lease_seconds":300}}
                result = db.execute("select ecos.operate('work.claim',%s)",(Jsonb(request),)).fetchone()[0]
                if "code" in result:
                    raise RuntimeError("Governed claim rejected: " + result["code"])
                claim = result.get("claim")
                return pid, None if claim is None else {**claim,"claim_id":claim["id"]}
        with ThreadPoolExecutor(max_workers=100) as pool:
            futures = [pool.submit(contender,n) for n in range(100)]
            observations = [f.result(timeout=100) for f in futures]
        if len({pid for pid,_ in observations}) != 100:
            raise AssertionError("Exactly 100 independent server sessions required")
        with connect() as db:
            live = db.execute("select to_jsonb(c)||jsonb_build_object('claim_id',id,'expired',expires_at<=clock_timestamp()) from ecos.work_claim c where occurrence_id=%s and state='active'",(occurrence,)).fetchall()
            runs = db.execute("select to_jsonb(r) from ecos.execution_run r where occurrence_id=%s",(occurrence,)).fetchall()
        winner = assert_claim_observations([c for _,c in observations],[x[0] for x in live],[x[0] for x in runs])
        report.update(status="passed", independent_sessions=100, winners=1, live_claims=len(live), execution_runs=len(runs), winner=winner, backend_pids=sorted(pid for pid,_ in observations))
    except Exception as exc:
        # Do not serialize connection exceptions: libpq errors can contain user/DSN data.
        report.update(error_type=type(exc).__name__, error="Live harness failed; inspect locally without publishing credentials")
        report["error_message"] = "Inspect a local debugger; exception text deliberately omitted"
    finally:
        try:
            if prepared:
                with connect() as db:
                    db.execute("delete from ecos_meta.principal_binding where role_name='executor' and principal_id=%s",(p,))
                    db.execute("update ecos.executor set enabled=false,record_version=record_version+1 where id=%s",(ex,))
                    if membership_added:
                        db.execute(sql.SQL("revoke executor from {}").format(sql.Identifier(owner)))
                report["temporary_binding_removed"] = True
        except Exception as exc:
            report.update(status="failed", cleanup_error_type=type(exc).__name__, temporary_binding_removed=False)
        finally:
            args.report.parent.mkdir(parents=True,exist_ok=True)
            args.report.write_text(json.dumps(report,indent=2,default=str)+"\n",encoding="utf-8")
    if report["status"] != "passed":
        raise SystemExit("C-01 failed; see the redacted report")
    print("C-01 passed: 100 independent sessions, one claim, one run.")

if __name__ == "__main__":
    main()
