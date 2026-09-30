"""Explicit synthetic capabilities plus unchanged shared 1.x HTTP implementation.

Provider writes are deliberately absent. No task identity routes execution.
"""
import hashlib
import importlib
import json
import os
from pathlib import Path
import ssl
import subprocess
import sys
import urllib.request

from ecos.core.contracts import content_hash


def shared_http(config):
    shared = config["shared_capability"]
    root = Path(shared["root"]).resolve()
    for name, expected in shared["sha256"].items():
        if hashlib.sha256((root / name).read_bytes()).hexdigest() != expected:
            raise ValueError("shared_capability_hash_mismatch")
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(root))
    module = importlib.import_module("ecos_runtime.local_capability_consumer")
    if Path(module.__file__).resolve() != root / "ecos_runtime/local_capability_consumer.py":
        raise ValueError("shared_capability_origin_mismatch")
    return module.HttpExecutor


def make_handlers(config):
    root = Path(config["state_directory"]).resolve()

    def source(runtime, package):
        task = runtime.read("task", package["task"]["id"])
        if (not task["record"]["business_id"].startswith("SYNTHETIC-RESIDENT2X-")
                or "acceptance-only" not in task["record"]["description"]):
            raise ValueError("synthetic_scope_required")
        return task, runtime.reference("task", task)

    def hello(runtime, package, guard):
        task, ref = source(runtime, package)
        if package["input"] != {"synthetic": True, "value": "Hello"}:
            raise ValueError("synthetic_input_mismatch")
        guard()
        child = subprocess.run([sys.executable, "-I", "-S", "-c",
            "import json,sys; x=json.load(sys.stdin); print(json.dumps({'output':x['value']+' World'}))"],
            input=json.dumps(package["input"]), capture_output=True, text=True, timeout=20,
            env={k: v for k, v in os.environ.items() if k.upper() in ("SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP")},
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), check=True)
        output = json.loads(child.stdout)["output"]
        if output != "Hello World":
            raise ValueError("python_output_mismatch")
        guard()
        result = runtime.invoke("fact.record", {"subject_id": task["record"]["id"],
            "statement": output, "source_references": [ref], "sensitivity": "internal"},
            key=package["occurrence"]["id"] + ":hello-fact")
        fact_id = next(v["record_id"] for v in result["record_versions"] if v["record_type"] == "fact")
        committed = runtime.read("fact", fact_id)
        if (committed["record"]["statement"] != output
                or committed["record"]["subject_id"] != task["record"]["id"]
                or committed["record"]["source_references"] != [ref]):
            raise ValueError("fact_readback_mismatch")
        return {"fact_id": fact_id, "input": "Hello", "python_output": output,
                "content_hash": committed["content_hash"], "readback": committed,
                "source_references": [runtime.reference("fact", committed)],
                "synthetic_identity": task["record"]["business_id"], "provider_effects": False}

    def artifact(runtime, package, guard):
        _, ref = source(runtime, package)
        spec = config["artifacts"][package["input"]["artifact_key"]]
        path = Path(spec["path"]).resolve()
        if not path.is_relative_to(root) or path.stat().st_size > 65536:
            raise ValueError("artifact_scope_violation")
        guard()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != spec["sha256"]:
            raise ValueError("artifact_hash_mismatch")
        return {"content_hash": digest, "source_references": [ref], "read_only": True}

    def http_read(runtime, package, guard):
        _, ref = source(runtime, package)
        endpoint = package["input"]["endpoint_id"]
        definitions = config["http_transports"]
        resource = definitions["resources"][endpoint]
        active = resource["environments"][resource["active_environment"]]
        if any(op["methods"] != ["GET"] for op in active["operations"].values()):
            raise ValueError("provider_effects_disabled")
        # Acceptance endpoints are loopback TLS only; arbitrary hosted egress is not enabled.
        from urllib.parse import urlsplit
        if urlsplit(active["base_url"]).hostname != "localhost":
            raise ValueError("synthetic_endpoint_required")

        def resolve(reference, _resource, **_):
            path = Path(config["secure_references"][reference]).resolve()
            if not path.is_relative_to(root):
                raise ValueError("secret_scope_violation")
            return {"token": path.read_text().strip()}

        context = ssl.create_default_context(cafile=config["http_ca_file"])
        executor = shared_http(config)
        module = importlib.import_module("ecos_runtime.local_capability_consumer")
        opener = urllib.request.build_opener(module._NoRedirect(), urllib.request.HTTPSHandler(context=context)).open
        guard()
        result = executor(definitions, resolve, opener=opener)({"arguments": {
            "endpoint_id": endpoint, "operation": "GET", "transaction_id": "", "body_json": "{}"}})
        if result.get("error") or result.get("http_status") != 200 or result.get("value") != "synthetic-readback":
            raise ValueError("http_readback_failed")
        return {"content_hash": content_hash(result), "source_references": [ref],
                "http_result": result, "shared_implementation": "ecos_runtime.local_capability_consumer.HttpExecutor"}

    return {"hello_world": hello, "artifact_read": artifact, "authenticated_http_read": http_read}
