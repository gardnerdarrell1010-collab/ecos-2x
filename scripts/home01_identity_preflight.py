"""Read-only canonical Home01 authentication and local identity transition guard."""
import argparse
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'src')]
from runtime.resident2x.connection import connection_factory


def validate(before, after, context, state):
    allowed = {'instance_id', 'executor_id', 'principal_id', 'database', 'database_password_file'}
    if any(before.get(k) != after.get(k) for k in before.keys() | after.keys() if k not in allowed):
        raise ValueError('provider_or_runtime_configuration_changed')
    if before['instance_id'] not in ('d46614c2-d42d-45fe-a7da-e753a15354a9', 'd50696aa-a03b-43d7-b15b-1a692df58977'):
        raise ValueError('unexpected_source_instance')
    expected = {'executor_name': 'resident_ada_2x_home01',
                'executor_id': 'd84cb9bc-7e4b-49f4-85b3-e70c2247ab11',
                'executor_instance_id': 'd50696aa-a03b-43d7-b15b-1a692df58977'}
    if any(context[k] != v for k, v in expected.items()):
        raise ValueError('canonical_identity_mismatch')
    if after['instance_id'] != context['executor_instance_id'] or after['principal_id'] != context['principal_id'] or after['executor_id'] != context['executor_id']:
        raise ValueError('configuration_identity_mismatch')
    if not context['enabled'] or context['availability'] != 'available':
        raise ValueError('canonical_executor_not_operational')
    if state.get('active') is not None:
        raise ValueError('active_claim_requires_reconciliation')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--config', type=Path, required=True)
    p.add_argument('--candidate', type=Path, required=True)
    a = p.parse_args()
    before = json.loads(a.config.read_text())
    after = json.loads(a.candidate.read_text())
    state = json.loads((Path(before['state_directory']) / 'state.json').read_text())
    with connection_factory(after)() as db:
        db.execute('set transaction read only')
        context = db.execute('select ecos.bootstrap_package()').fetchone()[0]['executor_context']
    validate(before, after, context, state)
    print('CanonicalHome01Preflight=PASS')


if __name__ == '__main__':
    main()
