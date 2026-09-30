"""SQL-native Resident. Production authority is scoped by domain in PostgreSQL.

Enrollment supplies a dedicated login and scoped, attested capabilities. PostgreSQL
owns selection, fences, leases and retries. The local journal only preserves exact
requests across ambiguous commits; it is not a second work queue.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import signal
import threading
import time
import psycopg
from uuid import uuid4

from ecos.core.contracts import content_hash
from scripts.phase2_executor_client import GovernedClient
from runtime.executor_profiles import validate_profile

VERSION = "2.0.1-domain-authority.1"


def now():
    return datetime.now(timezone.utc).isoformat()


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, sort_keys=True, ensure_ascii=False, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


@contextmanager
def singleton(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as lock:
        lock.seek(0)
        if os.name == "nt":
            import msvcrt
            if path.stat().st_size == 0:
                lock.write(b"0")
                lock.flush()
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            lock.seek(0)
            if os.name == "nt":
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock, fcntl.LOCK_UN)


class OperationRejected(RuntimeError):
    def __init__(self, operation, code):
        self.operation, self.code = operation, code
        super().__init__(operation + ":" + code)


class Resident:
    expected_identity = "RESIDENT_ADA_2X_HOME01"
    stage_kind = "deterministic"
    runtime_name = "resident-ada-2x"
    host_name = "HOME-01"

    def __init__(self, config, connect, handlers):
        self.profile = validate_profile(config, expected_identity=self.expected_identity)
        if config.get("authority") == "PRE_CUTOVER_NON_AUTHORITATIVE":
            # Backward-compatible synthetic configuration; never production authority.
            if config.get("provider_effects_enabled") is not False:
                raise ValueError("synthetic_effects_forbidden")
        elif (config.get("authority") != "DOMAIN_SCOPED_PRODUCTION"
              or config.get("execution_mode") not in ("synthetic", "shadow", "production")
              or not config.get("domain")):
            raise ValueError("domain_authority_configuration_required")
        self.config, self.connect, self.handlers = config, connect, handlers
        self.root = Path(config["state_directory"]).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.client = GovernedClient(connect)
        self.stopping = threading.Event()
        self.journal_lock = threading.Lock()
        self.evidence_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        self.session = str(uuid4())
        self.state_path = self.root / "state.json"
        self.state = json.loads(self.state_path.read_text()) if self.state_path.exists() else {
            "instance_id": config["instance_id"], "cycle": 0, "active": None}
        if self.state["instance_id"] != config["instance_id"]:
            raise ValueError("state_instance_mismatch")

    def request(self, arguments, key):
        return {"schema_version": "1.0.0", "context": {
            "principal_id": self.config["principal_id"],
            "executor_instance_id": self.config["instance_id"],
            "correlation_id": self.config["correlation_id"],
            "causation_id": None, "idempotency_key": key}, "arguments": arguments}

    def invoke(self, operation, arguments, *, key=None, client=None):
        client = client or self.client
        request = self.request(arguments, key or str(uuid4()))
        path = None
        if key:
            path = self.root / "requests" / (hashlib.sha256((operation + key).encode()).hexdigest() + ".json")
            if path.exists():
                saved = json.loads(path.read_text())
                # The original bytes win after a crash, never a regenerated timestamp/UUID.
                request = saved["request"]
                if saved["operation"] != operation:
                    raise ValueError("journal_operation_mismatch")
            else:
                save(path, {"operation": operation, "request": request})
        result = client.operate(operation, request)
        if "code" in result:
            raise OperationRejected(operation, result["code"])
        if path:
            save(path, {"operation": operation, "request": request, "result": result})
        return result

    def read(self, kind, identity):
        # Separate connection and transaction: never rely on the write response.
        with self.connect() as db:
            value = db.execute("select ecos.read_record(%s,%s)", (kind, identity)).fetchone()[0]
        if content_hash(value["record"]) != value["content_hash"]:
            raise ValueError("readback_hash_mismatch")
        if value["record"]["id"] != identity:
            raise ValueError("readback_identity_mismatch")
        return value

    def reference(self, kind, value):
        return {"record_type": kind, "record_id": value["record"]["id"],
                "record_version": value["record"]["record_version"],
                "content_hash": value["content_hash"], "authority": "structured_ecos"}

    def heartbeat(self, client, running):
        response = self.invoke("executor.heartbeat", {
            "observed_at": now(), "evidence_hash": self.evidence_hash,
            "reported_running": int(running), "load_basis_points": 100 if running else 0}, client=client)
        save(self.root / "connectivity.json", {"at": now(),
             "identity": self.config["identity"], "status": "connected"})
        save(self.root / "heartbeat.json", {"pid": os.getpid(), "identity": self.config["identity"],
             "instance_id": self.config["instance_id"], "at": now(), "running": running,
             "generation": self.profile["generation"], "control_plane": self.profile["control_plane"],
             "display_name": self.profile["display_name"], "domain": self.config.get("domain"),
             "authority": self.config["authority"], "response": response})

    @contextmanager
    def keepalive(self, fence):
        done, lost = threading.Event(), []
        client = GovernedClient(self.connect)

        def pump():
            while not done.wait(self.config.get("heartbeat_seconds", 5)):
                try:
                    self.heartbeat(client, True)
                    self.invoke("work.renew", {"fence": fence, "lease_seconds": self.config.get("lease_seconds", 120)}, client=client)
                except Exception as exc:
                    lost.append(exc)
                    break

        thread = threading.Thread(target=pump, name="resident2x-lease", daemon=True)
        thread.start()
        try:
            def guard():
                if lost:
                    raise lost[0]
                if self.stopping.is_set():
                    raise InterruptedError("resident_stopping")
                self.invoke("work.renew", {"fence": fence, "lease_seconds": self.config.get("lease_seconds", 120)})
            yield guard
        finally:
            done.set()
            thread.join(timeout=50)
            client.close()

    def finish_control(self, action, fence, reason, *, until=None, retryable=False):
        if action not in ("work.fail", "work.defer", "work.release"):
            raise ValueError("unknown_disposition")
        args = {"fence": fence, "reason": reason}
        if action == "work.defer":
            args["until"] = until
        if action == "work.fail":
            args["retryable"] = retryable
        key = fence["claim_id"] + ":" + action
        save(self.root / "terminal" / (fence["claim_id"] + ".json"),
             {"operation": action, "arguments": args, "key": key})
        return self.invoke(action, args, key=key)

    def execute(self, claimed):
        data = claimed["data"]
        package, run = data["work_package"], data["execution_run"]
        fence = package["fence"]
        occurrence = package["occurrence"]["id"]
        receipt_path = self.root / "results" / (occurrence + ".json")
        terminal_path = self.root / "terminal" / (fence["claim_id"] + ".json")
        # A prior committed completion can be replayed without trying to renew a released fence.
        if terminal_path.exists():
            terminal = json.loads(terminal_path.read_text())
            response = self.invoke(terminal["operation"], terminal["arguments"], key=terminal["key"])
            if terminal["operation"] == "work.complete":
                committed = self.read("work_occurrence", occurrence)
                if committed["record"]["state"] != "succeeded":
                    raise ValueError("completion_readback_failed")
                receipt = json.loads(receipt_path.read_text())
                receipt.update(completion=response, occurrence_readback=committed, claim=fence,
                    resident_identity=self.config["identity"], completed_at=now())
                save(receipt_path, receipt)
            return {"occurrence_id": occurrence, "replayed_terminal": True, "response": response}
        with self.keepalive(fence) as guard:
            guard()
            fresh = self.invoke("work.package", {"fence": fence})["data"]
            if fresh != package:
                # A lease renewal changes claim expiry, not the package fence or source inputs.
                if any(fresh[k] != package[k] for k in ("input", "stage", "source_references", "context_version", "fence")):
                    raise ValueError("work_package_changed")
            stage = package["stage"]["stage_key"]
            handler = self.handlers.get(stage)
            if handler is None or package["stage"]["kind"] != self.stage_kind:
                self.finish_control("work.fail", fence, "unsupported_capability")
                return {"occurrence_id": occurrence, "disposition": "unsupported_capability"}
            declared = {v["name"]: v["minimum_version"] for v in package["capability_requirements"]}
            if not declared or any(self.config["capabilities"].get(k, 0) < v for k, v in declared.items()):
                raise ValueError("capability_mismatch")
            if not receipt_path.exists():
                result = handler(self, package, guard)
                save(receipt_path, {"occurrence_id": occurrence, "execution_run_id": run["id"],
                     "pid": os.getpid(), "instance_id": self.config["instance_id"], "result": result})
            receipt = json.loads(receipt_path.read_text())
            result = receipt["result"]
            guard()
            if result.get("fact_id"):
                checked = self.read("fact", result["fact_id"])
                if checked["content_hash"] != result["content_hash"] or checked["record"]["statement"] != "Hello World":
                    raise ValueError("committed_result_changed")
            stamp = now()
            arguments = {"fence": fence, "result": {
                "id": str(uuid4()), "schema_version": "1.0.0", "created_at": stamp,
                "occurrence_id": occurrence, "stage_definition_id": fence["stage_definition_id"],
                "execution_run_id": run["id"], "result_schema_id": package["stage"]["result_schema_id"],
                "content_hash": result["content_hash"], "artifact_uri": receipt_path.as_uri(),
                "verified_at": stamp, "verified_by": self.config["principal_id"],
                "source_references": result["source_references"]}}
            terminal = {"operation": "work.complete", "arguments": arguments, "key": occurrence + ":complete:" + run["id"]}
            save(terminal_path, terminal)
            response = self.invoke("work.complete", arguments, key=terminal["key"])
            committed = self.read("work_occurrence", occurrence)
            if committed["record"]["state"] != "succeeded":
                raise ValueError("completion_readback_failed")
            receipt.update(completion=response, occurrence_readback=committed, claim=fence,
                           resident_identity=self.config["identity"], completed_at=now())
            save(receipt_path, receipt)
            return receipt

    def run(self, max_cycles=0):
        # Retain journal and active claim after an ambiguous database response.
        # Only connection failures are retried; governance rejections fail closed.
        failures = 0
        while not self.stopping.is_set():
            try:
                return self._run_connected(max_cycles)
            except psycopg.OperationalError:
                failures += 1
                self.client.close()
                delay = min(60, 2 ** min(failures, 6))
                save(self.root / "connectivity.json", {
                    "at": now(), "identity": self.config["identity"],
                    "status": "reconnecting", "consecutive_failures": failures,
                    "retry_seconds": delay, "active_claim_preserved": bool(self.state["active"])})
                self.stopping.wait(delay)

    def _run_connected(self, max_cycles=0):
        with singleton(self.root / "resident2x.lock"):
            save(self.root / "process.json", {"pid": os.getpid(), "identity": self.config["identity"],
                 "instance_id": self.config["instance_id"], "runtime": str(Path(__file__).resolve()),
                 "version": VERSION, "session": self.session, "started_at": now()})
            try:
                registered = self.invoke("executor.register", {"host": self.host_name,
                    "runtime": self.runtime_name, "software_version": VERSION,
                    "evidence_hash": self.evidence_hash})
                if registered["data"]["authority"] != self.config["authority"]:
                    raise ValueError("authority_mismatch")
                count = 0
                while not self.stopping.is_set() and (not max_cycles or count < max_cycles):
                    self.heartbeat(self.client, bool(self.state["active"]))
                    if self.state["active"] is None:
                        claimed = self.invoke("work.next", {"executor_instance_id": self.config["instance_id"],
                            "lease_seconds": self.config.get("lease_seconds", 120)}, key="next:" + str(self.state["cycle"]))
                        if claimed["status"] == "NO_ELIGIBLE_WORK":
                            self.state["cycle"] += 1
                            save(self.state_path, self.state)
                            count += 1
                            self.stopping.wait(self.config.get("poll_seconds", 2))
                            continue
                        self.state["active"] = claimed
                        save(self.state_path, self.state)
                    try:
                        self.execute(self.state["active"])
                    except InterruptedError:
                        self.finish_control("work.release", self.state["active"]["data"]["work_package"]["fence"], "graceful_shutdown")
                    except OperationRejected as exc:
                        # Preserve intent for diagnosis/recovery. Never retry external effects after a lost fence.
                        save(self.root / "failure.json", {"at": now(), "operation": exc.operation, "code": exc.code})
                        if exc.code == "expired_fence" and exc.operation in ("work.renew", "work.package", "work.complete"):
                            self.invoke("recovery.sweep", {"limit": 10})
                            current = self.read("work_occurrence", self.state["active"]["data"]["claim"]["occurrence_id"])
                            if current["record"]["state"] not in ("retry_wait", "ready", "succeeded"):
                                raise
                        else:
                            raise
                    except psycopg.OperationalError:
                        # Do not turn an unknown commit into a terminal failure.
                        raise
                    except Exception as exc:
                        self.finish_control("work.fail", self.state["active"]["data"]["work_package"]["fence"], "capability_execution_failed", retryable=False)
                        save(self.root / "failure.json", {"at": now(), "type": type(exc).__name__})
                        # An isolated failed capability must not strand unrelated runnable work.
                    self.state["active"] = None
                    self.state["cycle"] += 1
                    save(self.state_path, self.state)
                    count += 1
                self.heartbeat(self.client, False)
            finally:
                self.client.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--max-cycles", type=int, default=0)
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    from runtime.resident2x.capabilities import make_handlers
    from runtime.resident2x.connection import connection_factory
    if config.get("domain") == "toast.acquisition":
        from runtime.resident2x.toast_wave1 import handler
        handlers = {"toast_acquire": handler(config)}
    else:
        handlers = make_handlers(config)
    runtime = Resident(config, connection_factory(config), handlers)
    signal.signal(signal.SIGINT, lambda *_: runtime.stopping.set())
    signal.signal(signal.SIGTERM, lambda *_: runtime.stopping.set())
    try:
        runtime.run(args.max_cycles)
    except Exception as exc:
        print(json.dumps({"status": "failed", "error_type": type(exc).__name__}))
        return 1
    print(json.dumps({"status": "stopped", "pid": os.getpid(), "identity": config["identity"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
