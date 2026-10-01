"""Archive a reconciled Gmail claim locally after SQL recovery; never alter SQL state."""
import argparse
import json
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'src')]
from runtime.resident2x.connection import connection_factory
from runtime.resident2x.executor import Resident, save, singleton

parser = argparse.ArgumentParser()
parser.add_argument('--config', type=Path, required=True)
parser.add_argument('--check-only', action='store_true')
args = parser.parse_args()
config = json.loads(args.config.read_text())
assert config['domain'] == 'gmail.operations'
expected = {'ecos.2x.execute', 'provider.gmail', 'db.governed_operations'}
if config.get('operational_sms'):
    expected |= {'http.authenticated.request', 'provider.twilio'}
assert set(config['capabilities']) == expected
runtime = Resident(config, connection_factory(config), {})
active = runtime.state['active']
if active is not None:
    occurrence = active['data']['work_package']['occurrence']['id']
    current = runtime.read('work_occurrence', occurrence)['record']
    assert current['state'] == 'retry_wait', 'SQL claim recovery required before local resume'
if not args.check_only:
    with singleton(runtime.root / 'resident2x.lock'):
        receipt = runtime.root / ('reconciled-claim-' + uuid4().hex + '.json')
        save(receipt, runtime.state)
        runtime.state['active'] = None
        runtime.state['cycle'] += 1
        save(runtime.state_path, runtime.state)
print('GmailLocalResumePreflight=PASS')
