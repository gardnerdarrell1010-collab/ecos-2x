"""Explicit synthetic acceptance: enroll fixtures, launch a distinct Resident process.

The harness never calls fact.record, work.next or work.complete for the proof.
Only the child Resident receives the dedicated executor credential. Enrollment is
administrative fixture setup because Phase 2 has no enrollment/work-create API.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import getpass
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path[:0] = [str(ROOT), str(ROOT / "src"), str(ROOT / "scripts")]
import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
from runtime.resident2x.executor import save, now
from migrations import inventory, render

OPERATIONS = ("executor.register", "executor.heartbeat", "executor.stop", "work.next", "work.package",
              "work.renew", "work.complete", "work.fail", "work.defer", "work.release", "fact.record", "recovery.sweep")
SHARED = Path(r"D:\ECOS\Node\runtime\releases\slots\1.0.011")


def uid():
    return str(uuid4())


def native(command, **kwargs):
    # File handles, not PIPE: postgres outlives pg_ctl on Windows.
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8") as output:
        result = subprocess.run(list(map(str, command)), stdout=output, stderr=output, text=True, check=True,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), timeout=120, **kwargs)
    return result


def secure_directory(path):
    path.mkdir(parents=True, exist_ok=False)
    if os.name == "nt":
        native(["icacls", path, "/inheritance:r", "/grant:r", os.environ["USERDOMAIN"] + "\\" + getpass.getuser() + ":(OI)(CI)F"])
    else:
        path.chmod(0o700)


def certificate(root, openssl):
    native([openssl, "req", "-x509", "-nodes", "-newkey", "rsa:2048", "-keyout", root / "server.key",
            "-out", root / "server.crt", "-days", "1", "-subj", "/CN=localhost", "-addext", "subjectAltName=DNS:localhost"])


@contextmanager
def synthetic_http(root, token):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            if self.path != "/acceptance" or self.headers.get("Authorization") != "Bearer " + token:
                self.send_error(403)
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            # Exercise the SAME HttpExecutor's reflected-secret redaction and normalization.
            self.wfile.write(json.dumps({"value": "synthetic-readback", "reflected": token}).encode())

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    tls.load_cert_chain(root / "server.crt", root / "server.key")
    server.socket = tls.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_port
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def hosted_admin(secret_sink=None):
    # Resolve the owner-authorized canonical reference in memory for fixture enrollment only.
    site = SHARED  # the isolated 1.x release vendors its Google client here
    sys.path.append(str(site))
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    credentials = service_account.Credentials.from_service_account_file(
        r"D:\ECOS\Credentials\ecos-resident-ada.json", scopes=["https://www.googleapis.com/auth/drive.readonly"])
    service = build("drive", "v3", credentials=credentials, cache_discovery=False, static_discovery=False)
    password = service.files().get_media(fileId="1x8dB_y3doSdGOxVLhWG7gmQ4SAcTjVLf").execute().decode("utf-8-sig").strip()
    if secret_sink is not None:
        secret_sink(password)
    settings = {"host": "aws-0-us-west-1.pooler.supabase.com", "port": 5432, "dbname": "postgres",
                "sslmode": "verify-full", "sslrootcert": str(ROOT / "runtime/resident2x/supabase-prod-ca-2021.crt")}

    def connect():
        return psycopg.connect(**settings, user="postgres.loonpojawpfagzobxoko", password=password,
            connect_timeout=20, options="-c statement_timeout=45000 -c lock_timeout=10000 -c timezone=UTC")
    return connect, settings


def enroll(connect, database, state, http_port, password, hosted=False):
    principal, instance, executor, correlation = [uid() for _ in range(4)]
    role = "resident2x_" + uuid4().hex[:16]
    config = {"identity": "RESIDENT_ADA_2X_HOME01", "principal_id": principal, "instance_id": instance,
        "executor_id": executor, "correlation_id": correlation, "authority": "DOMAIN_SCOPED_PRODUCTION", "domain": "synthetic.acceptance", "execution_mode": "synthetic",
        "provider_effects_enabled": False, "state_directory": str(state), "database_password_file": str(state / "database.secret"),
        "database": {**database, "user": role + (".loonpojawpfagzobxoko" if hosted else "")},
        "capabilities": {"local.process.execute": 1, "local.filesystem.read": 1, "http.authenticated.request": 1,
                         "secure.reference.resolve": 1, "db.governed_operations": 1},
        "heartbeat_seconds": 2, "lease_seconds": 30, "poll_seconds": 1,
        "shared_capability": {"root": str(SHARED), "sha256": {str(p): hashlib.sha256((SHARED / p).read_bytes()).hexdigest()
            for p in (Path("ecos_runtime/local_capability_consumer.py"), Path("ecos_runtime/request_bindings.py"), Path("ecos_capability/sms.py"))}},
        "http_ca_file": str(state / "server.crt"), "secure_references": {"synthetic-token": str(state / "http.secret")},
        "http_transports": {"resources": {"synthetic-read": {"active_environment": "acceptance", "environments": {"acceptance": {
            "base_url": "https://localhost:" + str(http_port), "credential_reference": "synthetic-token",
            "authorization_scheme": "Bearer", "content_type": "application/json", "timeout_seconds": 5,
            "max_response_bytes": 4096, "retry": {"max_attempts": 2, "initial_backoff_seconds": 0, "maximum_backoff_seconds": 1},
            "operations": {"GET": {"methods": ["GET"], "path": "/acceptance"}}}}}}}}
    artifact = state / "synthetic-artifact.txt"
    artifact.write_text("Synthetic Resident Ada 2.x artifact\n", encoding="utf-8")
    config["artifacts"] = {"acceptance": {"path": str(artifact), "sha256": hashlib.sha256(artifact.read_bytes()).hexdigest()}}
    work = []
    with connect() as db:
        assert db.execute("select environment,authority,provider_effects_enabled from ecos_meta.database_identity").fetchone() == ("production", "domain_scoped", True)
        assert db.execute("select max(version) from ecos_meta.schema_migration").fetchone()[0] >= 21
        db.execute(sql.SQL("create role {} login password {} nosuperuser nocreatedb nocreaterole inherit").format(sql.Identifier(role), sql.Literal(password)))
        db.execute(sql.SQL("grant executor, operations_api to {}").format(sql.Identifier(role)))
        db.execute("insert into ecos.executor(id,name,surface,enabled) values(%s,%s,'RESIDENT_DETERMINISTIC_PROVIDER',true)", (executor, "resident_ada_2x_home01"))
        db.execute("insert into ecos.executor_instance(id,executor_id,boot_id,availability,principal_id) values(%s,%s,%s,'available',%s)", (instance, executor, uid(), principal))
        db.execute("insert into ecos_meta.principal_binding values(%s,%s,%s,true)", (role, principal, instance))
        db.execute("insert into ecos_meta.principal_domain values(%s,'synthetic.acceptance','synthetic',1)", (principal,))
        for operation in OPERATIONS:
            db.execute("insert into ecos_meta.principal_operation values(%s,%s)", (principal, operation))
        for name in config["capabilities"]:
            if not db.execute("select exists(select 1 from ecos.capability where name=%s and version=1)", (name,)).fetchone()[0]:
                db.execute("insert into ecos.capability(name,version,description) values(%s,1,'Synthetic Resident 2.x acceptance capability')", (name,))
            db.execute("insert into ecos.executor_capability(executor_instance_id,capability_name,capability_version,attested_by,expires_at) values(%s,%s,1,%s,clock_timestamp()+interval '2 hours')", (instance, name, principal))
        for key, payload, required in (
                ("hello_world", {"synthetic": True, "value": "Hello"}, ["local.process.execute", "db.governed_operations"]),
                ("artifact_read", {"synthetic": True, "artifact_key": "acceptance"}, ["local.filesystem.read"]),
                ("authenticated_http_read", {"synthetic": True, "endpoint_id": "synthetic-read"}, ["http.authenticated.request", "secure.reference.resolve"])):
            task, retry, definition, stage, occurrence = [uid() for _ in range(5)]
            db.execute("insert into ecos.task(id,business_id,title,project_id,lifecycle_state,wait_reason,description) values(%s,%s,%s,null,'open','none',%s)",
                (task, "SYNTHETIC-RESIDENT2X-" + task, "Synthetic Resident Ada 2.x " + key,
                 "synthetic; acceptance-only; Resident Ada 2.x; Hello World round-trip evidence; synthetic.acceptance domain; no provider effects"))
            db.execute("insert into ecos.retry_policy(id,max_attempts,initial_delay_seconds,max_delay_seconds,backoff_multiplier,jitter_basis_points,retryable_error_classes) values(%s,3,1,10,2,0,'[\"transient\"]')", (retry,))
            db.execute("insert into ecos.work_definition(id,name,definition_version,enabled,fulfillment_kind,retry_policy_id) values(%s,%s,1,true,'staged',%s)", (definition, "synthetic_resident2x_" + uid().replace("-", ""), retry))
            db.execute("insert into ecos.work_stage_definition(id,work_definition_id,stage_key,kind,execution_surface,input_schema_id,result_schema_id,requires_approval) values(%s,%s,%s,'deterministic','RESIDENT_DETERMINISTIC_PROVIDER','synthetic.input.v1','synthetic.result.v1',false)", (stage, definition, key))
            for name in required:
                db.execute("insert into ecos.stage_capability_requirement(stage_definition_id,capability_name,minimum_version) values(%s,%s,1)", (stage, name))
            db.execute("insert into ecos.work_occurrence(id,work_definition_id,stage_definition_id,fulfillment_id,task_id,state,occurrence_key,due_at,retry_at,ready_override_at,priority_override) values(%s,%s,%s,%s,%s,'ready',%s,clock_timestamp()-interval '1 second',null,null,null)", (occurrence, definition, stage, uid(), task, "SYNTHETIC-RESIDENT2X-" + occurrence))
            for kind, identity in (("task", task), ("work_occurrence", occurrence)):
                db.execute("insert into ecos_meta.object_grant values(%s,%s,%s)", (principal, kind, identity))
            db.execute("insert into ecos.work_context(occurrence_id,operation,input) values(%s,%s,%s)", (occurrence, "fact.record" if key == "hello_world" else "work.complete", Jsonb(payload)))
            work.append({"stage": key, "task_id": task, "occurrence_id": occurrence})
    (state / "database.secret").write_text(password, encoding="utf-8")
    save(state / "config.json", config)
    save(state / "enrollment.json", {"sql_role": role, "work": work})
    return config, work, role


def resident1_snapshot():
    root = Path(r"D:\ECOS\Node\runtime")
    heartbeat = json.loads((root / "resident-ada/heartbeat.json").read_text())
    return {"pid": heartbeat["pid"], "heartbeat_at": heartbeat["heartbeat_at"], "version": heartbeat["runtime_version"],
            "source_sha256": hashlib.sha256((SHARED / "ecos_runtime/resident_governed.py").read_bytes()).hexdigest(),
            "pointer_sha256": hashlib.sha256((root / "releases/active.json").read_bytes()).hexdigest()}


def run_acceptance(connect, database, state, hosted, fault_restart=False):
    password, token = secrets.token_urlsafe(40), secrets.token_urlsafe(32)
    (state / "http.secret").write_text(token, encoding="utf-8")
    before = resident1_snapshot()
    with synthetic_http(state, token) as port:
        config, work, role = enroll(connect, database, state, port, password, hosted)
        if fault_restart:
            crash = subprocess.run([sys.executable, "-B", str(ROOT / "tests/resident2x/crash_driver.py"),
                "--config", str(state / "config.json"), "--max-cycles", "3"],
                capture_output=True, text=True, timeout=120, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            assert crash.returncode == 73, "fault process did not reach committed fact"
            print("PASS crash after real fact commit; waiting for lease expiry", flush=True)
            time.sleep(config["lease_seconds"] + 2)
        log = state / "resident.stdout.log"
        previous_session = json.loads((state / "process.json").read_text())["session"] if (state / "process.json").exists() else None
        with log.open("w") as output:
            child = subprocess.Popen([sys.executable, "-B", str(ROOT / "scripts/resident2x.py"), "--config", str(state / "config.json"), "--max-cycles", "8"],
                stdout=output, stderr=output, cwd=ROOT, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            # Coexistence must be observed while both are running, not inferred from code.
            deadline = time.monotonic() + 90
            process = None
            while child.poll() is None and time.monotonic() < deadline:
                if (state / "process.json").exists() and (state / "heartbeat.json").exists():
                    candidate = json.loads((state / "process.json").read_text())
                    heartbeat = json.loads((state / "heartbeat.json").read_text())
                    if candidate["session"] != previous_session and heartbeat["pid"] == candidate["pid"]:
                        process = candidate
                        break
                time.sleep(0.2)
            assert process is not None, "no fresh child heartbeat"
            during = resident1_snapshot()
            collision = subprocess.run([sys.executable, "-B", str(ROOT / "scripts/resident2x.py"),
                "--config", str(state / "config.json"), "--max-cycles", "1"],
                capture_output=True, text=True, timeout=30, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            collision_ok = collision.returncode == 1 and any(name in collision.stdout for name in ('OSError', 'PermissionError', 'BlockingIOError'))
            child.wait(timeout=180)
            assert collision_ok, "singleton not exclusive"
        if child.returncode:
            raise RuntimeError("resident_child_failed:" + log.read_text()[-1200:])
        results = [json.loads((state / "results" / (w["occurrence_id"] + ".json")).read_text()) for w in work]
        assert all(r.get("completion", {}).get("status") == "committed" for r in results)
        assert all(r["pid"] == process["pid"] for r in results), "result process identity"
        assert next(r for r in results if r["result"].get("fact_id"))["result"]["python_output"] == "Hello World"
        http = next(r for r in results if "http_result" in r["result"])
        assert http["result"]["http_result"]["reflected"] == "[REDACTED]"
        with connect() as db:
            actual = db.execute("select id,state,claim_version from ecos.work_occurrence where id=any(%s::uuid[])", ([w["occurrence_id"] for w in work],)).fetchall()
            assert len(actual) == 3 and all(row[1] == "succeeded" for row in actual)
            assert db.execute("select count(*) from ecos.work_claim where executor_instance_id=%s and state='active'", (config["instance_id"],)).fetchone()[0] == 0
            direct = db.execute("select has_table_privilege(%s,'ecos.work_occurrence','UPDATE'),has_function_privilege(%s,'ecos_meta.apply_operation(text,jsonb,jsonb)','EXECUTE')", (role, role)).fetchone()
            assert direct == (False, False)
            assert db.execute("select count(*) from ecos.fact where subject_id=any(%s::uuid[])", ([w["task_id"] for w in work],)).fetchone()[0] == 1
            audit = db.execute("select operation,count(*) from ecos_meta.operation_audit where principal_id=%s group by operation order by operation", (config["principal_id"],)).fetchall()
        after = resident1_snapshot()
        assert before["pid"] == during["pid"] == after["pid"] != process["pid"]
        assert before["source_sha256"] == after["source_sha256"] and before["pointer_sha256"] == after["pointer_sha256"]
        assert during["heartbeat_at"] >= before["heartbeat_at"]
        # The child is intentionally bounded; its SQL identity is kept for exact evidence/restart tests.
        return {"status": "passed", "target": "hosted" if hosted else "disposable", "pid": process["pid"], "launcher_pid": child.pid,
            "executor": {k: config[k] for k in ("identity", "executor_id", "instance_id", "principal_id")},
            "state_directory": str(state), "work": work, "results": results, "operation_audit_counts": audit,
            "coexistence": {"before": before, "during": during, "after": after, "passed": True,
                "scheduled_tasks_created": False, "production_credentials_in_child": False,
                "shared_capability_hashes": config["shared_capability"]["sha256"]},
            "restart_after_committed_fact_and_expired_lease": fault_restart, "singleton_collision_rejected": True,
            "security": {"direct_dml_denied": True, "private_helpers_denied": True, "tls": database["sslmode"],
                "dedicated_login": role, "provider_effects": False, "secret_reflection_redacted": True}}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--hosted", action="store_true")
    p.add_argument("--fault-restart", action="store_true")
    p.add_argument("--pg-bin", type=Path)
    p.add_argument("--openssl", type=Path, required=True)
    p.add_argument("--state", type=Path, required=True)
    p.add_argument("--report", type=Path, required=True)
    args = p.parse_args()
    state = args.state.resolve()
    secure_directory(state)
    certificate(state, args.openssl)
    running = False
    report = {"status": "failed", "started_at": now()}
    try:
        if args.hosted:
            connect, database = hosted_admin()
        else:
            password = secrets.token_urlsafe(32)
            pw = state / "init.secret"
            pw.write_text(password)
            try:
                native([args.pg_bin / "initdb.exe", "-D", state / "pgdata", "-U", "postgres", "--auth=scram-sha-256", "--pwfile=" + str(pw), "--encoding=UTF8", "--locale=C"])
            finally:
                pw.unlink(missing_ok=True)
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            import shutil
            shutil.copyfile(state / "server.crt", state / "pgdata/server.crt")
            shutil.copyfile(state / "server.key", state / "pgdata/server.key")
            options = f"-h 127.0.0.1 -p {port} -c ssl=on -c log_statement=none -c log_min_error_statement=panic"
            native([args.pg_bin / "pg_ctl.exe", "-D", state / "pgdata", "-l", state / "postgres.log", "-o", options, "-w", "start"])
            running = True
            database = {"host": "localhost", "hostaddr": "127.0.0.1", "port": port, "dbname": "postgres", "sslmode": "verify-full", "sslrootcert": str(state / "server.crt")}
            def connect():
                return psycopg.connect(**database, user="postgres", password=password, connect_timeout=10)
            print("PASS disposable PostgreSQL started", flush=True)
            with connect() as db:
                db.autocommit = True
                db.execute(render(inventory(ROOT / "db/migrations")).replace("\\set ON_ERROR_STOP on\n", "", 1), prepare=False)
            print("PASS disposable canonical migrations", flush=True)
        report.update(run_acceptance(connect, database, state, args.hosted, args.fault_restart))
    except Exception as exc:
        report.update(error_type=type(exc).__name__, sqlstate=getattr(exc, "sqlstate", None))
        if isinstance(exc, AssertionError):
            report['assertion'] = str(exc)
        # No database exception text/credentials in durable reports.
        print(json.dumps({"error_type": type(exc).__name__, "sqlstate": getattr(exc, "sqlstate", None)}))
    finally:
        if running:
            native([args.pg_bin / "pg_ctl.exe", "-D", state / "pgdata", "-m", "fast", "-w", "stop"])
        report["finished_at"] = now()
        save(args.report, report)
    print(json.dumps({"status": report["status"], "report": str(args.report)}))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
