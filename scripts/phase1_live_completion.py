"""Explicit Phase 1 live acceptance. Secrets are read only into process memory.

Only the canonical development Session Pooler is permitted. Local restore work is
performed separately; the default offline harness never imports this module.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import threading
import time
from uuid import uuid4
import psycopg
from psycopg.types.json import Jsonb

PROJECT='loonpojawpfagzobxoko'
SECRET_REF='google-drive:1x8dB_y3doSdGOxVLhWG7gmQ4SAcTjVLf'
COUNT=15
def uid(): return str(uuid4())

class SessionTarget:
    def __init__(self, secret_materialization):
        self._password=Path(secret_materialization).read_text(encoding='utf-8-sig').strip()
    def connect(self):
        return psycopg.connect(host='aws-0-us-west-1.pooler.supabase.com',port=5432,
            dbname='postgres',user='postgres.'+PROJECT,password=self._password,
            sslmode='require',connect_timeout=20,options='-c statement_timeout=45000 -c lock_timeout=30000 -c timezone=UTC')
    def clear(self): self._password=None

class Fixture:
    def __init__(self,target):
        self.target=target
        self.p,self.inst,self.ex,self.retry,self.definition,self.stage,self.task,self.correlation=[uid() for _ in range(8)]
        self.occurrences=[]
        self.added_roles=[]
    def seed(self):
        with self.target.connect() as db:
            assert db.execute('select environment,authority,provider_effects_enabled from ecos_meta.database_identity').fetchone() in [('development','non_production',False),('production','domain_scoped',True)]
            assert not db.execute("select exists(select 1 from ecos_meta.principal_binding where role_name in ('executor','operations_api'))").fetchone()[0], 'Fixture roles already bound'
            assert not db.execute('select maintenance from ecos_meta.control').fetchone()[0], 'Maintenance already enabled'
            for role in ('executor','operations_api'):
                if not db.execute('select pg_has_role(current_user,%s,\'SET\')',(role,)).fetchone()[0]:
                    db.execute(psycopg.sql.SQL('grant {} to postgres').format(psycopg.sql.Identifier(role)))
                    self.added_roles.append(role)
            db.execute("insert into ecos.task(id,business_id,title,project_id,lifecycle_state,wait_reason,description) values(%s,%s,'Synthetic Phase 1 completion',null,'open','none','Disposable acceptance evidence')",(self.task,'SYNTHETIC-PHASE1-COMPLETION-'+self.task))
            db.execute("insert into ecos.executor(id,name,surface,enabled) values(%s,%s,'DATABASE_DETERMINISTIC',true)",(self.ex,'synthetic_'+self.ex.replace('-','')))
            db.execute("insert into ecos.executor_instance(id,executor_id,boot_id,availability,principal_id) values(%s,%s,%s,'available',%s)",(self.inst,self.ex,uid(),self.p))
            db.execute("insert into ecos.retry_policy(id,max_attempts,initial_delay_seconds,max_delay_seconds,backoff_multiplier,jitter_basis_points,retryable_error_classes) values(%s,10,1,30,2,0,'[\"transient\"]')",(self.retry,))
            db.execute("insert into ecos.work_definition(id,name,definition_version,enabled,fulfillment_kind,retry_policy_id) values(%s,%s,1,true,'staged',%s)",(self.definition,'synthetic_'+self.definition.replace('-',''),self.retry))
            db.execute("insert into ecos.work_stage_definition(id,work_definition_id,stage_key,kind,execution_surface,input_schema_id,result_schema_id,requires_approval) values(%s,%s,'synthetic_completion','deterministic','DATABASE_DETERMINISTIC','synthetic.input.v1','synthetic.result.v1',false)",(self.stage,self.definition))
            db.execute("insert into ecos.stage_capability_requirement(stage_definition_id,capability_name,minimum_version) values(%s,'db.governed_operations',1)",(self.stage,))
            db.execute("insert into ecos.executor_capability(executor_instance_id,capability_name,capability_version,attested_by,expires_at) values(%s,'db.governed_operations',1,%s,clock_timestamp()+interval '1 hour')",(self.inst,self.p))
            for role in ('executor','operations_api'):
                db.execute('insert into ecos_meta.principal_binding values(%s,%s,%s,true)',(role,self.p,self.inst))
            if db.execute("select to_regclass('ecos_meta.principal_domain')").fetchone()[0]:
                db.execute("insert into ecos_meta.principal_domain values(%s,'synthetic.acceptance','synthetic',1)",(self.p,))
            db.execute("insert into ecos_meta.principal_operation select %s,name from ecos_meta.operation_contract",(self.p,))
            db.execute("insert into ecos_meta.object_grant values(%s,'task',%s)",(self.p,self.task))
    def add_work(self,count):
        ids=[]
        with self.target.connect() as db:
            for _ in range(count):
                work=uid();ids.append(work)
                db.execute("insert into ecos.work_occurrence(id,work_definition_id,stage_definition_id,fulfillment_id,task_id,state,occurrence_key,due_at,retry_at,ready_override_at,priority_override) values(%s,%s,%s,%s,%s,'ready',%s,clock_timestamp()-interval '1 second',null,null,null)",(work,self.definition,self.stage,uid(),self.task,'SYNTHETIC-COMPLETION-'+work))
                db.execute("insert into ecos_meta.object_grant values(%s,'work_occurrence',%s)",(self.p,work))
        self.occurrences+=ids
        return ids
    def request(self,arguments):
        return {'schema_version':'1.0.0','context':{'principal_id':self.p,'executor_instance_id':self.inst,'correlation_id':self.correlation,'causation_id':None,'idempotency_key':'synthetic-'+uid()},'arguments':arguments}
    def operate(self,db,operation,arguments):
        return db.execute('select ecos.operate(%s,%s)',(operation,Jsonb(self.request(arguments)))).fetchone()[0]
    def executor(self,db):
        db.execute('set local role executor')
        db.execute('select ecos.record_heartbeat(clock_timestamp(),%s)',('c'*64,))
    def claim(self,db): return self.operate(db,'work.claim',{'executor_instance_id':self.inst,'lease_seconds':300})
    def result_arguments(self,claim_result):
        c=claim_result['claim'];run=claim_result['execution_run']
        fence={k:c['id'] if k=='claim_id' else c[k] for k in ('claim_id','occurrence_id','stage_definition_id','claim_version','fence_token','executor_instance_id')}
        stamp=datetime.now(timezone.utc).isoformat()
        result={'id':uid(),'schema_version':'1.0.0','created_at':stamp,'occurrence_id':c['occurrence_id'],'stage_definition_id':c['stage_definition_id'],'execution_run_id':run['id'],'result_schema_id':'synthetic.result.v1','content_hash':'d'*64,'artifact_uri':'synthetic:phase1-completion','verified_at':stamp,'verified_by':self.p,'source_references':[]}
        return {'fence':fence,'result':result}
    def complete(self,result):
        with self.target.connect() as db:
            self.executor(db)
            response=self.operate(db,'work.complete',self.result_arguments(result))
            assert response.get('status')=='committed', 'Completion rejected: '+str(response.get('code'))
    def cleanup(self):
        with self.target.connect() as db:
            # Fixture-only teardown. Preserve immutable runs/events and end residual
            # test claims; this is not an executor mutation interface.
            db.execute("update ecos.work_claim set state='revoked',record_version=record_version+1 where executor_instance_id=%s and state='active'",(self.inst,))
            db.execute("update ecos.execution_run set state='cancelled',ended_at=clock_timestamp(),record_version=record_version+1 where executor_instance_id=%s and state='started'",(self.inst,))
            db.execute("update ecos.work_occurrence set state='cancelled',record_version=record_version+1 where work_definition_id=%s and state not in ('succeeded','cancelled')",(self.definition,))
            if db.execute("select to_regclass('ecos.executor_presence')").fetchone()[0]:
                db.execute("update ecos.executor_presence set status='stopped',stopped_at=clock_timestamp(),record_version=record_version+1 where executor_instance_id=%s",(self.inst,))
            db.execute('delete from ecos_meta.principal_binding where principal_id=%s',(self.p,))
            db.execute('update ecos.executor set enabled=false,record_version=record_version+1 where id=%s',(self.ex,))
            for role in self.added_roles:
                db.execute(psycopg.sql.SQL('revoke {} from postgres').format(psycopg.sql.Identifier(role)))

def contend(fixture,work_count):
    ids=fixture.add_work(work_count)
    start=threading.Barrier(COUNT,timeout=35)
    hold=threading.Barrier(COUNT,timeout=35)
    diagnostics={}
    def worker(n):
        diagnostic={'contender':n,'phase':'connecting'}
        diagnostics[n]=diagnostic
        try:
            with fixture.target.connect() as db:
                diagnostic['phase']='obtaining_backend'
                pid=db.execute('select pg_backend_pid()').fetchone()[0]
                diagnostic.update(backend_pid=pid,phase='heartbeat')
                fixture.executor(db)
                diagnostic['phase']='starting_barrier'
                start.wait()
                diagnostic['phase']='claim_operation'
                before=time.monotonic()
                result=fixture.claim(db)
                after=time.monotonic()
                diagnostic.update(phase='precommit_barrier',result=result)
                assert 'code' not in result, 'Claim returned an error'
                hold.wait()
            diagnostic['phase']='committed'
            return {'contender':n,'backend_pid':pid,'started':before,'returned':after,'result':result}
        except Exception as exc:
            diagnostic.update(error_type=type(exc).__name__,sqlstate=getattr(exc,'sqlstate',None))
            return None
    with ThreadPoolExecutor(max_workers=COUNT) as pool:
        rows=list(pool.map(worker,range(COUNT)))
    if any(row is None for row in rows):
        return {'status':'failed','requested_sessions':COUNT,'observed_backend_sessions':len({d['backend_pid'] for d in diagnostics.values() if 'backend_pid' in d}),'observations':list(diagnostics.values())}
    assert len({x['backend_pid'] for x in rows})==COUNT,'Not independent server sessions'
    winners=[x for x in rows if x['result']['claim'] is not None]
    expected=1 if work_count==1 else COUNT
    assert len(winners)==expected,'Incorrect winner count'
    assert len({x['result']['claim']['occurrence_id'] for x in winners})==expected,'Duplicate occurrence ownership'
    with fixture.target.connect() as db:
        claims=db.execute("select to_jsonb(c) from ecos.work_claim c where occurrence_id=any(%s::uuid[]) and state='active' and expires_at>clock_timestamp()",(ids,)).fetchall()
        runs=db.execute('select to_jsonb(r) from ecos.execution_run r where occurrence_id=any(%s::uuid[])',(ids,)).fetchall()
        assert len(claims)==len(runs)==expected,'Invalid durable ownership count'
        assert all(x[0]['selection_evidence']['eligible'] for x in runs),'Readiness gate bypassed'
        for winner in winners:
            claim=winner['result']['claim']; run=next(x[0] for x in runs if x[0]['claim_id']==claim['id'])
            for field in ('occurrence_id','stage_definition_id','claim_version','fence_token','executor_instance_id'):
                assert run[field]==claim[field], 'Fence mismatch'
    for winner in winners: fixture.complete(winner['result'])
    return {'status':'passed','sessions':COUNT,'backend_pids':sorted(x['backend_pid'] for x in rows),'initial_eligible_occurrences':ids,'winners':expected,'valid_losers':COUNT-expected,'all_operations_returned_before_any_commit':True,'observations':rows,'durable_claims':[x[0] for x in claims],'durable_runs':[x[0] for x in runs]}

def wait_blocked(target,pid,blocker):
    deadline=time.monotonic()+15
    with target.connect() as probe:
        while time.monotonic()<deadline:
            row=probe.execute('select pg_blocking_pids(%s)',(pid,)).fetchone()[0]
            if blocker in row: return row
            time.sleep(.05)
    raise AssertionError('Expected independent session did not block at the invariant boundary')

def race_gate(f,kind):
    work=f.add_work(1)[0]
    approval=uid()
    if kind!='maintenance':
        with f.target.connect() as db:
            subject_hash=db.execute('select ecos_meta.content_hash(to_jsonb(t)) from ecos.task t where id=%s',(f.task,)).fetchone()[0]
            db.execute('update ecos.work_stage_definition set requires_approval=true,record_version=record_version+1 where id=%s',(f.stage,))
            db.execute("insert into ecos.approval_request(id,task_id,subject_type,subject_id,subject_hash,state,expires_at) values(%s,%s,'task',%s,%s,'approved',clock_timestamp()+interval '1 hour')",(approval,f.task,f.task,subject_hash))
            db.execute('insert into ecos.work_approval values(%s,%s,%s)',(work,approval,subject_hash))
    claim=None
    if kind=='revocation_effect':
        with f.target.connect() as db:
            f.executor(db);claim=f.claim(db);assert claim.get('claim') is not None
    writer=f.target.connect()
    info={};ready=threading.Event()
    try:
        writer_pid=writer.execute('select pg_backend_pid()').fetchone()[0]
        if kind=='maintenance': writer.execute('update ecos_meta.control set maintenance=true,record_version=record_version+1')
        elif kind=='expiry': writer.execute("update ecos.approval_request set expires_at=clock_timestamp()+interval '1 second',record_version=record_version+1 where id=%s",(approval,))
        else: writer.execute("update ecos.approval_request set state='revoked',record_version=record_version+1 where id=%s",(approval,))
        def contender():
            with f.target.connect() as db:
                f.executor(db);info['pid']=db.execute('select pg_backend_pid()').fetchone()[0];ready.set()
                return f.operate(db,'work.complete',f.result_arguments(claim)) if claim else f.claim(db)
        with ThreadPoolExecutor(max_workers=1) as pool:
            future=pool.submit(contender)
            assert ready.wait(20)
            blockers=wait_blocked(f.target,info['pid'],writer_pid)
            if kind=='expiry': time.sleep(1.2)
            writer.commit()
            result=future.result(timeout=40)
        assert writer_pid!=info['pid']
        assert result.get('code')=='gate_blocked' if kind in ('maintenance','revocation_effect') else result.get('claim') is None
        with f.target.connect() as db:
            state=db.execute('select state,claim_version from ecos.work_occurrence where id=%s',(work,)).fetchone()
            count=db.execute('select count(*) from ecos.stage_result where occurrence_id=%s',(work,)).fetchone()[0]
            assert count==0,'Blocked effect committed'
            if not claim: assert state==('ready',0),'Blocked claim mutated work'
        return {'status':'passed','race':kind,'writer_pid':writer_pid,'contender_pid':info['pid'],'observed_blockers':blockers,'operation_result':result,'readback_state':state,'stage_result_count':count}
    finally:
        writer.rollback();writer.close()
        with f.target.connect() as db:
            if kind=='maintenance':db.execute('update ecos_meta.control set maintenance=false,record_version=record_version+1 where maintenance')
            # Prevent this completed race fixture from joining the next test.
            db.execute('delete from ecos_meta.object_grant where principal_id=%s and record_type=\'work_occurrence\' and record_id=%s',(f.p,work))

def dependency_race(f):
    a,b=uid(),uid()
    with f.target.connect() as db:
        for t in (a,b):db.execute("insert into ecos.task(id,business_id,title,project_id,lifecycle_state,wait_reason,description) values(%s,%s,'Synthetic concurrent graph',null,'open','none','Phase 1 graph race')",(t,'SYNTHETIC-CYCLE-'+t))
    writer=f.target.connect();info={};ready=threading.Event()
    try:
        pid=writer.execute('select pg_backend_pid()').fetchone()[0]
        writer.execute("insert into ecos.task_dependency(task_id,prerequisite_task_id,satisfaction_rule) values(%s,%s,'completed')",(a,b))
        def second():
            try:
                with f.target.connect() as db:
                    info['pid']=db.execute('select pg_backend_pid()').fetchone()[0];ready.set()
                    db.execute("insert into ecos.task_dependency(task_id,prerequisite_task_id,satisfaction_rule) values(%s,%s,'completed')",(b,a))
                return 'accepted'
            except psycopg.errors.CheckViolation: return '23514'
        with ThreadPoolExecutor(max_workers=1) as pool:
            future=pool.submit(second);assert ready.wait(20)
            blockers=wait_blocked(f.target,info['pid'],pid);writer.commit();result=future.result(timeout=40)
        assert result=='23514','Concurrent graph cycle was accepted'
        with f.target.connect() as db:
            edges=db.execute('select task_id::text,prerequisite_task_id::text from ecos.task_dependency where task_id=any(%s::uuid[])',([a,b],)).fetchall()
            assert edges==[(a,b)]
        return {'status':'passed','writer_pid':pid,'contender_pid':info['pid'],'observed_blockers':blockers,'rejection_sqlstate':result,'final_edges':edges}
    finally: writer.rollback();writer.close()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--secret-materialization',required=True,type=Path)
    parser.add_argument('--report',required=True,type=Path)
    parser.add_argument('--gates',choices=['all','concurrency','races'],default='all')
    args=parser.parse_args()
    report={'started_at':datetime.now(timezone.utc).isoformat(),'connection_mode':'Supabase Shared Pooler Session Mode','canonical_secret_reference':SECRET_REF,'project_ref':PROJECT,'provider_calls_executed':False,'production_data_migrated':False}
    target=SessionTarget(args.secret_materialization);fixture=Fixture(target)
    try:
        fixture.seed()
        if args.gates in ('all','concurrency'):
            report['test_a']=contend(fixture,1)
            assert report['test_a']['status']=='passed', 'Test A did not establish the required completed simultaneous operations'
            report['test_b']=contend(fixture,COUNT)
            assert report['test_b']['status']=='passed', 'Test B did not establish parallel operations'
        if args.gates in ('all','races'):
            report['c06']=[race_gate(fixture,k) for k in ('maintenance','revocation_effect','expiry')]
            report['task02']=dependency_race(fixture)
        report['status']='passed'
    except Exception as exc:
        report.update(status='failed',error_type=type(exc).__name__,sqlstate=getattr(exc,'sqlstate',None))
        if isinstance(exc,AssertionError):report['assertion']=str(exc)
    finally:
        try:fixture.cleanup();report['fixture_cleanup']='passed'
        except Exception as exc:report.update(status='failed',cleanup_error_type=type(exc).__name__)
        target.clear()
        report['finished_at']=datetime.now(timezone.utc).isoformat()
        args.report.parent.mkdir(parents=True,exist_ok=True)
        args.report.write_text(json.dumps(report,indent=2,default=str)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('test_a','test_b','c06','task02')},indent=2))
    return 0 if report['status']=='passed' else 1
if __name__=='__main__':raise SystemExit(main())
