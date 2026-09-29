"""One offline entrypoint: generated artifacts, unittest suite and pending gate report."""
import argparse
from datetime import datetime, timezone
import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/"src")]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--require-phase1",action="store_true",help="Fail if any Phase 1 integration gate is pending")
    parser.add_argument("--report",type=Path,help="Write a JSON evidence summary to a local file")
    args = parser.parse_args()
    for script in ("build_contracts.py","build_worker_registry.py","build_foundation_data.py","build_fixtures.py"):
        result = subprocess.run([sys.executable,str(ROOT/"scripts"/script),"--check"],cwd=ROOT,check=False)
        if result.returncode:
            return result.returncode
    suite = unittest.defaultTestLoader.discover(str(ROOT/"tests"),top_level_dir=str(ROOT))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    gates = json.loads((ROOT/"tests/acceptance-catalog.json").read_text())["gates"]
    pending = [g for g in gates if g["status"] != "passed"]
    summary = {"verified_at":datetime.now(timezone.utc).isoformat(), "python_version":sys.version.split()[0],
        "platform":sys.platform, "tests_run":result.testsRun,
        "offline_passed":result.testsRun-len(result.skipped)-len(result.failures)-len(result.errors),
        "failures":len(result.failures),"errors":len(result.errors),"skipped_integration":len(result.skipped),
        "pending_phase1":[g["id"] for g in pending if g["required_phase"]==1],
        "operational_maturity":"designed", "database_tests_executed":False, "provider_calls_executed":False}
    print(json.dumps(summary,indent=2))
    if args.report:
        args.report.parent.mkdir(parents=True,exist_ok=True)
        args.report.write_text(json.dumps(summary,indent=2)+"\n",encoding="utf-8",newline="\n")
    if not result.wasSuccessful():
        return 1
    if args.require_phase1 and any(g["required_phase"]==1 for g in pending):
        print("PHASE 1 RELEASE BLOCKED: integration acceptance evidence is pending.")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
