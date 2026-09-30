"""Wave 1 transactional acceptance, disposable data only."""
import json
from datetime import datetime,timezone,timedelta
from psycopg.types.json import Jsonb

def checks(target,Fixture):
    f=Fixture(target);f.seed();passed=[]
    def admin(q,args=()):
        with target.connect() as db:
            c=db.execute(q,args);return c.fetchall() if c.description else []
    def op(name,args,request=None):
        with target.connect() as db:
            db.execute('set local role executor')
            return db.execute('select ecos.operate(%s,%s)',(name,Jsonb(request or f.request(args)))).fetchone()[0]
    def new_work():
        w=f.add_work(1)[0]
        admin("insert into ecos.work_context(occurrence_id,operation,input) values(%s,'work.complete','{}')",(w,))
        r=op('work.next',{'executor_instance_id':f.inst,'lease_seconds':120})
        assert r.get('status')=='CLAIMED',r
        return r,f.result_arguments(r['data'])['fence']
    try:
        r=op('executor.register',{'host':'SYNTHETIC-WAVE1','runtime':'batch-test','software_version':'1','evidence_hash':'a'*64});assert 'code' not in r,r
        claimed,fence=new_work()
        args={'fence':fence,'restaurant_hash':'b'*64,'business_date':'2026-09-27',
              'observation_json':json.dumps({'status':'CLOSED_ACTUALS','business_date':'2026-09-27','rows':[{'amount':1.25,'clock_hours':0.5}]}),
              'projection_json':json.dumps({'schema_version':'ECOS-TOAST-OPERATING-SNAPSHOT-1','freshness':{'age_seconds':12.5}}),
              'source_hash':'c'*64,'expected_checkpoint_version':0}
        bad=dict(args,fence=dict(fence,fence_token='00000000-0000-4000-8000-000000000000'))
        assert op('toast.batch.commit',bad).get('code') in ('expired_fence','forbidden'),op('toast.batch.commit',bad)
        assert admin('select count(*) from ecos.toast_batch')[0][0]==0
        passed.append('stale_fence_cannot_commit_batch')
        with target.connect() as db:
            db.execute('set local role executor')
            r=db.execute("select ecos.operate('toast.batch.commit',%s)",(Jsonb(f.request(args)),)).fetchone()[0]
            assert r.get('status')=='committed',r
            db.rollback()
        assert admin('select count(*) from ecos.toast_batch')[0][0]==0
        assert admin('select count(*) from ecos.toast_checkpoint')[0][0]==0
        passed.append('crash_before_commit_leaves_no_partial_batch_or_checkpoint')
        request=f.request(args)
        first=op('toast.batch.commit',args,request);assert first.get('status')=='committed',first
        assert op('toast.batch.commit',args,request)==first
        replay=op('toast.batch.commit',args);assert replay['data']==first['data']
        with target.connect() as db:
            db.execute('set local role executor')
            readback=db.execute('select ecos.toast_readback(%s)',(fence['occurrence_id'],)).fetchone()[0]
        assert readback['observation_json']==args['observation_json']
        assert readback['observation']['rows'][0]['amount']==1.25
        assert readback['projection_json']==args['projection_json']
        assert admin('select count(*) from ecos.toast_batch')[0][0]==1
        assert admin('select record_version from ecos.toast_checkpoint')[0][0]==1
        passed.extend(['independent_committed_readback_preserves_decimal_values','same_request_and_new_key_replay_single_batch_checkpoint'])
        admin("delete from ecos_meta.object_grant where principal_id=%s and record_type='work_occurrence' and record_id=%s",(f.p,fence['occurrence_id']))
        assert op('toast.batch.commit',args,request).get('code')=='forbidden'
        admin("insert into ecos_meta.object_grant values(%s,'work_occurrence',%s)",(f.p,fence['occurrence_id']))
        admin("delete from ecos_meta.object_grant where principal_id=%s and record_type='task' and record_id=%s",(f.p,f.task))
        assert op('toast.batch.commit',args,request).get('code')=='forbidden'
        admin("insert into ecos_meta.object_grant values(%s,'task',%s)",(f.p,f.task))
        passed.append('cached_batch_replay_rechecks_revoked_occurrence_and_task_grants')
        for kind,identity in [('task',f.task),('work_occurrence',fence['occurrence_id'])]:
            admin("insert into ecos_meta.object_domain values(%s,%s,'toast.acquisition')",(kind,identity))
        admin("update ecos_meta.principal_domain set domain='toast.acquisition',execution_mode='shadow' where principal_id=%s",(f.p,))
        assert op('toast.batch.commit',args,request).get('code')=='forbidden'
        admin("update ecos_meta.principal_domain set domain='synthetic.acceptance',execution_mode='synthetic' where principal_id=%s",(f.p,))
        admin("delete from ecos_meta.object_domain where record_id=any(%s::uuid[])",([f.task,fence['occurrence_id']],))
        passed.append('cached_batch_replay_cannot_cross_domain_or_mode')
        try:admin("update ecos.toast_batch set source_hash=repeat('a',64)")
        except Exception as exc:assert exc.sqlstate=='23514'
        else:raise AssertionError('immutable batch changed')
        passed.append('committed_batch_immutable')
        assert op('toast.batch.commit',dict(args,source_hash='d'*64)).get('code')=='idempotency_conflict'
        passed.append('conflicting_occurrence_payload_rejected')
        assert op('work.complete',f.result_arguments(claimed['data']))['status']=='committed'
        claimed2,fence2=new_work()
        second=dict(args,fence=fence2)
        assert op('toast.batch.commit',second).get('code')=='stale_version'
        assert admin('select count(*) from ecos.toast_batch')[0][0]==1
        second['expected_checkpoint_version']=1
        assert op('toast.batch.commit',second)['status']=='committed'
        assert admin('select record_version from ecos.toast_checkpoint')[0][0]==2
        assert admin('select count(*) from ecos.toast_closed_date')[0][0]==1
        passed.append('checkpoint_compare_and_swap_and_closed_date_upsert')
        assert op('work.complete',f.result_arguments(claimed2['data']))['status']=='committed'
        claimed3,fence3=new_work()
        today=datetime.now(timezone.utc).date().isoformat()
        third=dict(args,fence=fence3,business_date=today,observation_json=json.dumps({'status':'CLOSED_ACTUALS','business_date':today,'rows':[]}),expected_checkpoint_version=2)
        assert op('toast.batch.commit',third).get('code')=='invalid_contract'
        passed.append('open_business_date_rejected')
        with target.connect() as db:
            db.execute('set local role executor')
            try:db.execute('delete from ecos.toast_batch')
            except Exception as exc:assert exc.sqlstate=='42501'
            else:raise AssertionError('executor directly changed batches')
        passed.append('direct_batch_mutation_denied')
    finally:f.cleanup()
    return passed
