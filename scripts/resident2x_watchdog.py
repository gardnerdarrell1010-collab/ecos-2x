"""Windows startup/restart entrypoint; PostgreSQL remains the only work scheduler."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path[:0] = [str(ROOT), str(ROOT / 'src')]
from runtime.executor_profiles import validate_profile
from runtime.resident2x.executor import singleton


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    validate_profile(config, expected_identity='RESIDENT_ADA_2X_HOME01')
    manifest = json.loads((ROOT / 'installed-manifest.json').read_text())
    for name, expected in manifest['files'].items():
        path = (ROOT / name).resolve()
        if not path.is_relative_to(ROOT) or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError('installed_release_hash_mismatch')
    state = Path(config['state_directory'])
    with singleton(state / 'supervisor.lock'):
        try:
            with singleton(state / 'resident2x.lock'):
                pass
        except OSError:
            heartbeat = json.loads((state / 'heartbeat.json').read_text())
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(heartbeat['at'])).total_seconds()
            if heartbeat['instance_id'] != config['instance_id'] or not 0 <= age < 90:
                raise RuntimeError('locked_resident_health_unverified')
            return 0
        # The child takes the same OS lock. A competing direct start cannot
        # become a second executor even in the gap following the probe above.
        with (state / 'supervisor.stdout.log').open('ab') as out, (state / 'supervisor.stderr.log').open('ab') as err:
            return subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/resident2x.py'),
                '--config', str(args.config.resolve())], cwd=ROOT, stdout=out, stderr=err,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), check=False).returncode


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({'status': 'failed', 'error_type': type(exc).__name__}))
        raise SystemExit(1)
