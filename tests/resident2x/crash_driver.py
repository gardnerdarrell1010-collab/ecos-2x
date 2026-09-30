"""Acceptance-only abrupt exit AFTER the real fact commit, BEFORE client journaling.

No fake database responses. The subsequent ordinary Resident process must recover.
"""
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
sys.dont_write_bytecode = True
from scripts.phase2_executor_client import GovernedClient

original = GovernedClient.operate


def crash_after_commit(self, operation, request):
    result = original(self, operation, request)
    if operation == "fact.record" and "code" not in result:
        config = json.loads(Path(sys.argv[sys.argv.index("--config") + 1]).read_text())
        marker = Path(config["state_directory"]) / "crash.json"
        marker.write_text(json.dumps({"pid": os.getpid(), "after_real_commit": True,
                                     "record_versions": result["record_versions"]}))
        os._exit(73)
    return result


GovernedClient.operate = crash_after_commit
from runtime.resident2x.executor import main
raise SystemExit(main())
