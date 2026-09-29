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
    completion={k:json.loads((ROOT/p).read_text()) for k,p in verification.get('completion_evidence',{}).items()}
    if completion:
        races=completion['races']; recovery=completion['recovery']
        if races['status']=='passed' and races['fixture_cleanup']=='passed':
            assert {r['race'] for r in races['c06']}=={'maintenance','revocation_effect','expiry'}
            for r in races['c06']:
                assert r['status']=='passed' and r['writer_pid']!=r['contender_pid']
                assert r['writer_pid'] in r['observed_blockers'] and r['stage_result_count']==0
            known.add('independent_gate_races')
            cycle=races['task02']
            assert cycle['status']=='passed' and cycle['rejection_sqlstate']=='23514'
            assert cycle['writer_pid']!=cycle['contender_pid'] and cycle['writer_pid'] in cycle['observed_blockers']
            assert len(cycle['final_edges'])==1
            known.add('concurrent_dependency_cycle')
        if recovery['status']=='passed':
            assert recovery['disposable_server_stopped'] and not recovery.get('schema_differences')
            mig=recovery['mig01'];rest=recovery['rest01']
            assert mig['status']==rest['status']=='passed' and mig['repeat_chain']=='passed'
            assert len(mig['transactional_checks'])==len(rest['transactional_checks'])==31
            assert mig['schema_inventory']==rest['source_schema_inventory']==rest['restored_schema_inventory']
            assert rest['source_data_inventory']==rest['restored_data_inventory']
            assert len(rest['source_data_inventory'])==74 and rest['corrupt_manifest_rejected']
            for version,name,digest in mig['migration_order']:
                assert hashlib.sha256((ROOT/'db/migrations'/name).read_bytes()).hexdigest()==digest
            known.update(['clean_canonical_rebuild','portable_export_restore'])
        final=completion['final-readback']
        assert final['ssl'] and final['database_identity']==['development','non_production',False]
        assert final['cleanup']==[0,0,False,False,False]
        assert not final['secret_scan']['password_matches'] and not final['secret_scan']['password_in_git_diff']
        assert set(final['transactional_checks'])==set(observed['transactional']['passed_checks'])
        contract=json.loads((ROOT/results['acceptance_override']).read_text())
        assert contract['independent_sessions']==15 and contract['test_a']['valid_losers']==14
        assert contract['designed_maximum_executors']==10 and contract['stress_margin_percent']==50
        concurrency=completion['concurrency']
        assert concurrency['status']=='passed' and concurrency['fixture_cleanup']=='passed'
        for name,expected in [('test_a',1),('test_b',15)]:
            t=concurrency[name]
            assert t['status']=='passed' and t['sessions']==15 and len(set(t['backend_pids']))==15
            assert len(t['observations'])==15 and t['all_operations_returned_before_any_commit']
            assert len(t['initial_eligible_occurrences'])==expected
            winners=[o for o in t['observations'] if o['result']['claim'] is not None]
            assert len(winners)==t['winners']==expected and t['valid_losers']==15-expected
            assert len({o['backend_pid'] for o in t['observations']})==15
            assert all(o['started']<=o['returned'] and 'code' not in o['result'] for o in t['observations'])
            assert len(t['durable_claims'])==len(t['durable_runs'])==expected
            assert len({c['occurrence_id'] for c in t['durable_claims']})==expected
            assert {w['result']['claim']['id'] for w in winners}=={c['id'] for c in t['durable_claims']}
            for claim in t['durable_claims']:
                run=next(r for r in t['durable_runs'] if r['claim_id']==claim['id'])
                assert claim['state']=='active' and run['selection_evidence']['eligible']
                assert claim['claim_version']==1
                for field in ['occurrence_id','stage_definition_id','claim_version','fence_token','executor_instance_id']:
                    assert claim[field]==run[field]
        readback=completion['concurrency-readback']
        assert readback['status']=='passed' and readback['ssl'] and readback['cleanup']==[0,0,False,False,False]
        assert len(readback['completed_occurrences'])==16
        assert all(row[1:]==['succeeded',1,1,0] for row in readback['completed_occurrences'])
        assert readback['capability_readback'] and all(row[2]>=row[3] and row[4] for row in readback['capability_readback'])
        known.update(['same_work_15_sessions','different_work_15_sessions'])
    for gate in results['gates']:
        if gate['status']=='passed' and (not gate['evidence_checks'] or not set(gate['evidence_checks'])<=known):
            raise ValueError('Gate has no observed check: '+gate['id'])
    pending=[g['id'] for g in results['gates'] if g['required_phase']==1 and g['status']!='passed']
    assert results['phase1_pending']==len(pending)
    print(json.dumps({'source_and_database_checksums':'passed','live_named_checks':len(observed['transactional']['passed_checks']),'phase1_pending':pending,'release_gate':'BLOCKED' if pending else 'PASSED'},indent=2))
    return 2 if pending and args.require_complete else 0
if __name__=='__main__':raise SystemExit(main())
