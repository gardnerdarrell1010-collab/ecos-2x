"""Additional Phase 2 surface, resource, authorization and catalog acceptance."""
import json,threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
from pathlib import Path
from psycopg.types.json import Jsonb

def additional(target,Fixture):
    f=Fixture(target);f.seed();checks=[];measurements={}
    def admin(q,args=()):
        with target.connect() as db:
            c=db.execute(q,args);return c.fetchall() if c.description else []
    def op(name,args,role='executor',request=None):
        with target.connect() as db:
            db.execute('set local role '+role)
            return db.execute('select ecos.operate(%s,%s)',(name,Jsonb(request or f.request(args)))).fetchone()[0]
    def good(name,args,role='executor'):
        r=op(name,args,role);assert 'code' not in r,(name,r);return r
    def fence(r):return {k:r['data']['claim']['id'] if k=='claim_id' else r['data']['claim'][k] for k in ('claim_id','occurrence_id','stage_definition_id','claim_version','fence_token','executor_instance_id')}
    def work(n=1):
        ids=f.add_work(n)
        for w in ids:admin("insert into ecos.work_context(occurrence_id,operation,input) values(%s,'work.complete','{}')",(w,))
        return ids
    register={'host':'SYNTHETIC-ACCEPTANCE','runtime':'contract-client','software_version':'phase2','evidence_hash':'a'*64}
    try:
        for surface in ('INTERACTIVE_ADA','RESIDENT_DETERMINISTIC_PROVIDER','ONLINE_SEMANTIC','DATABASE_DETERMINISTIC'):
            admin('update ecos.executor set surface=%s,record_version=record_version+1 where id=%s',(surface,f.ex))
            admin('update ecos.work_stage_definition set execution_surface=%s,record_version=record_version+1 where id=%s',(surface,f.stage))
            good('executor.register',register);w=work()[0]
            r=good('work.next',{'executor_instance_id':f.inst,'lease_seconds':120});assert r['data']['claim']['occurrence_id']==w
            assert good('executor.heartbeat',{'observed_at':datetime.now(timezone.utc).isoformat(),'evidence_hash':'a'*64,'reported_running':1,'load_basis_points':100})['data']['running_count']==1
            good('work.renew',{'fence':fence(r),'lease_seconds':120});good('work.complete',f.result_arguments(r['data']))
            checks.append(surface+'_governed_claim_renew_complete')
        # Numeric budget contention on two eligible occurrences, separate backends.
        admin("update ecos.resource_budget set hard_limit=1,elevated_limit=1,verification='OWNER_CONFIGURED',source='synthetic acceptance',record_version=record_version+1 where provider='drive' and metric='requests'")
        admin("insert into ecos.stage_resource_requirement values(%s,'drive','requests',1,false)",(f.stage,))
        work(2);barrier=threading.Barrier(2)
        def compete(_):
            with target.connect() as db:
                db.execute('set local role executor');pid=db.execute('select pg_backend_pid()').fetchone()[0];barrier.wait()
                r=db.execute("select ecos.operate('work.next',%s)",(Jsonb(f.request({'executor_instance_id':f.inst,'lease_seconds':120})),)).fetchone()[0]
                return {'backend':pid,'result':r}
        with ThreadPoolExecutor(max_workers=2) as pool:rows=list(pool.map(compete,range(2)))
        winners=[x['result'] for x in rows if x['result'].get('status')=='CLAIMED'];assert len(winners)==1,rows
        assert len(set(x['backend'] for x in rows))==2
        assert all(x['result'].get('status') in ('CLAIMED','NO_ELIGIBLE_WORK') or x['result'].get('code')=='gate_blocked' for x in rows)
        used=admin("select coalesce(sum(r.units),0) from ecos.resource_reservation r join ecos.work_claim c on c.id=r.claim_id where c.state='active' and c.expires_at>clock_timestamp() and r.provider='drive'")[0][0];assert used==1
        measurements['resource_contention']=rows;checks.append('resource_budget_two_session_single_reservation')
        r=winners[0];good('work.complete',f.result_arguments(r['data']))
        r=good('work.next',{'executor_instance_id':f.inst,'lease_seconds':120});assert r['status']=='CLAIMED'
        good('work.release',{'fence':fence(r),'reason':'synthetic_resource_release'})
        assert admin("select count(*) from ecos.resource_reservation rr join ecos.work_claim c on c.id=rr.claim_id where c.state='active' and c.expires_at>clock_timestamp() and rr.provider='drive'")[0][0]==0
        checks.append('completion_and_release_free_effective_reservations')
        # Deny stale measurements when this requirement requires known telemetry.
        admin('update ecos.stage_resource_requirement set unknown_blocks=true where stage_definition_id=%s',(f.stage,))
        assert good('work.next',{'executor_instance_id':f.inst,'lease_seconds':120})['status']=='NO_ELIGIBLE_WORK'
        good('resource.observe',{'provider':'drive','metric':'requests','observed_at':datetime.now(timezone.utc).isoformat(),'value':0,'evidence_hash':'b'*64},'operations_api')
        request=f.request({'executor_instance_id':f.inst,'lease_seconds':120});r=op('work.next',{},request=request);assert r['status']=='CLAIMED'
        assert op('work.next',{},request=request)==r;checks.append('work_next_idempotent_single_claim')
        occurrence=r['data']['claim']['occurrence_id']
        admin("delete from ecos_meta.object_grant where principal_id=%s and record_type='work_occurrence' and record_id=%s",(f.p,occurrence))
        assert op('work.next',{},request=request).get('code')=='forbidden','Cached work.next must recheck revoked object scope'
        admin("insert into ecos_meta.object_grant values(%s,'work_occurrence',%s)",(f.p,occurrence))
        admin("delete from ecos_meta.object_grant where principal_id=%s and record_type='task' and record_id=%s",(f.p,f.task))
        assert op('work.next',{},request=request).get('code')=='forbidden','Cached package must recheck task scope'
        admin("insert into ecos_meta.object_grant values(%s,'task',%s)",(f.p,f.task));checks.append('work_next_cached_package_revocation_enforced')
        good('work.dead_letter',{'fence':fence(r),'reason':'synthetic_authorized_dead_letter'},'operations_api')
        checks.append('unknown_resource_blocks_and_dead_letter_authorization')
        # Schema privileges must remain operation-only for executors, without PUBLIC helpers.
        assert admin("select count(*) from pg_proc p join pg_namespace n on n.oid=p.pronamespace cross join lateral aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) a where n.nspname='ecos_meta' and a.grantee=0 and a.privilege_type='EXECUTE'")[0][0]==0
        assert not admin("select has_table_privilege('executor','ecos.executor_presence','INSERT') or has_table_privilege('executor','ecos.work_context','SELECT')")[0][0]
        assert not admin("select has_function_privilege('executor','ecos_meta.apply_operation(text,jsonb,jsonb)','EXECUTE')")[0][0]
        bad=f.request(register);bad['context']['principal_id']='00000000-0000-4000-8000-000000000001'
        assert op('executor.register',{},request=bad).get('code')=='forbidden'
        assert op('resource.observe',{'provider':'drive','metric':'requests','observed_at':datetime.now(timezone.utc).isoformat(),'value':0,'evidence_hash':'a'*64}).get('code')=='forbidden'
        checks.append('private_helpers_direct_tables_spoofed_principal_role_denied')
        # A bounded shadow compares only normalized time gates; no live 1.x rows enter PostgreSQL.
        inputs=json.loads((Path(__file__).resolve().parents[1]/'docs/evidence/phase2/shadow-inputs.json').read_text())
        comparisons=[]
        admin('delete from ecos.stage_resource_requirement where stage_definition_id=%s',(f.stage,))
        for sample in inputs['samples']:
            w=work()[0]
            admin('update ecos.work_definition set enabled=%s,record_version=record_version+1 where id=%s',(sample['enabled'],f.definition))
            admin("update ecos.work_occurrence set due_at=clock_timestamp()+make_interval(secs=>%s),record_version=record_version+1 where id=%s",(-60 if sample['due'] else 60,w))
            evidence=admin('select ecos_meta.selection(%s,%s,clock_timestamp())',(w,f.inst))[0][0]
            time_allowed='not_due' not in evidence['reason_codes'] and 'disabled' not in evidence['reason_codes']
            expected=sample['enabled'] and sample['due'];assert time_allowed==expected
            comparisons.append({'sample':sample['sample'],'source_values_sha256':sample['source_values_sha256'],'one_x_time_gate':expected,'two_x_time_gate':time_allowed,'classification':'EQUIVALENT','scope':'time admission only'})
        measurements['shadow_comparison']={'scope':inputs['scope'],'comparisons':comparisons,'global_shadow_verified':False}
        checks.append('bounded_readonly_1x_time_gate_shadow_equivalence')
        from phase2_executor_client import GovernedClient
        def connected_executor():
            db=target.connect();db.execute('set role executor');db.commit();return db
        client=GovernedClient(connected_executor)
        try:
            for _ in range(2):
                response=client.operate('executor.heartbeat',f.request({'observed_at':datetime.now(timezone.utc).isoformat(),'evidence_hash':'a'*64,'reported_running':0,'load_basis_points':0}))
                assert 'code' not in response,response
            assert client.metrics['connections_opened']==1
            measurements['client']=client.metrics.copy()
        finally:client.close()
        import psycopg
        delays=[];attempts=[]
        def saturated():
            attempts.append(1);raise psycopg.OperationalError('synthetic connection pressure')
        client=GovernedClient(saturated,sleep=delays.append)
        try:
            try:client.operate('executor.heartbeat',f.request({}));raise AssertionError('Pressure must fail closed')
            except psycopg.OperationalError:pass
            assert len(attempts)==3 and delays==[0.25,1.0]
            measurements['connection_pressure']={'attempts':len(attempts),'backoff_seconds':delays,'bounded':True}
        finally:client.close()
        checks.append('client_reuses_connection_measures_bytes_latency_bounded_pressure_backoff')
        measurements['health']=admin('select ecos.control_plane_health()')[0][0]
        measurements['package_bytes']=admin('select min(payload_bytes),max(payload_bytes),count(*) from ecos.package_measurement where principal_id=%s',(f.p,))[0]
        for view in ('v_executor_status','v_resource_pressure','v_current_claims','v_ready_work','v_blocked_work','v_recent_failures','v_dead_letters','v_work_aging'):
            admin('select * from ecos.'+view+' limit 1')
        checks.append('all_phase2_observability_views_queryable')
        return {'status':'passed','checks':checks,'measurements':measurements}
    finally:f.cleanup()
