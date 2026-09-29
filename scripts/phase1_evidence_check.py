"""Offline integrity check of observed Phase 1 evidence; never reruns live tests."""
import argparse,hashlib,json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--require-complete',action='store_true')
    args=parser.parse_args()
    verification=json.loads((ROOT/'docs/PHASE1_VERIFICATION.json').read_text())
    results=json.loads((ROOT/'docs/PHASE1_RESULTS.json').read_text())
    observed=json.loads((ROOT/verification['evidence']).read_text())
    for name,digest in verification['source_sha256'].items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest()!=digest:
            raise ValueError('Evidence no longer matches source: '+name)
    for migration in observed['database']['migrations']:
        if hashlib.sha256((ROOT/'db/migrations'/migration['name']).read_bytes()).hexdigest()!=migration['sha256']:
            raise ValueError('Database migration checksum mismatch: '+migration['name'])
    known=set(observed['transactional']['passed_checks'])|set(observed['durability'])
    for gate in results['gates']:
        if gate['status']=='passed' and (not gate['evidence_checks'] or not set(gate['evidence_checks'])<=known):
            raise ValueError('Gate has no observed check: '+gate['id'])
    pending=[g['id'] for g in results['gates'] if g['required_phase']==1 and g['status']!='passed']
    print(json.dumps({'source_and_database_checksums':'passed','live_named_checks':len(observed['transactional']['passed_checks']),'phase1_pending':pending,'release_gate':'BLOCKED' if pending else 'PASSED'},indent=2))
    return 2 if pending and args.require_complete else 0
if __name__=='__main__':
    raise SystemExit(main())
