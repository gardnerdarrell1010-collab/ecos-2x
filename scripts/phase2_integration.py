"""Explicit synthetic PostgreSQL integration; default check.py stays offline.

Starts one private disposable loopback database, rebuilds canonical migrations,
runs real SQL operations plus independent 15-session races, then stops it.
No hosted credentials or production providers are used.
"""
import argparse
from datetime import datetime,timezone,timedelta
import getpass,hashlib,json,os,secrets,socket,subprocess,tempfile
from pathlib import Path
import psycopg
from psycopg.types.json import Jsonb
from migrations import inventory,render
from phase1_recovery_completion import run_sql_suite
from phase1_live_completion import Fixture,contend,uid
ROOT=Path(__file__).resolve().parents[1]

class LocalTarget:
    def __init__(self,password,port):self.password=password;self.port=port
    def connect(self):return psycopg.connect(host='127.0.0.1',port=self.port,dbname='postgres',user='postgres',password=self.password,sslmode='require',connect_timeout=10,options='-c timezone=UTC -c statement_timeout=45000 -c lock_timeout=15000')

def tests(target):
    f=Fixture(target);f.seed();checks=[]
    def mark(name):checks.append(name)
    def admin(q,args=()):
        with target.connect() as db:
            cur=db.execute(q,args)
            return cur.fetchall() if cur.description else []
    def op(name,args,role='executor',key=None):
        req=f.request(args)
        if key:req['context']['idempotency_key']=key
        with target.connect() as db:
            db.execute('set local role '+role)
            return db.execute('select ecos.operate(%s,%s)',(name,Jsonb(req))).fetchone()[0]
    def good(name,args,role='executor'):
        r=op(name,args,role);assert 'code' not in r,(name,r);return r
    def work(stage=None):
        w=f.add_work(1)[0]
        if stage:admin('update ecos.work_occurrence set stage_definition_id=%s,record_version=record_version+1 where id=%s',(stage,w))
        admin("insert into ecos.work_context(occurrence_id,operation,input) values(%s,'work.complete','{\"fixture\":true}')",(w,))
        return w
    def claim():return good('work.next',{'executor_instance_id':f.inst,'lease_seconds':120})
    def fence(r):return {k:r['data']['claim']['id'] if k=='claim_id' else r['data']['claim'][k] for k in ('claim_id','occurrence_id','stage_definition_id','claim_version','fence_token','executor_instance_id')}
    register={'host':'SYNTHETIC-HOME-01','runtime':'synthetic-contract-client','software_version':'phase2-test','evidence_hash':'e'*64}
    try:
        good('executor.register',register);mark('executor_registration_with_attested_capabilities')
        r=good('executor.heartbeat',{'observed_at':datetime.now(timezone.utc).isoformat(),'evidence_hash':'e'*64,'reported_running':0,'load_basis_points':0})
        assert r['data']['running_count']==0;mark('heartbeat_freshness_and_running_count')
        r=op('executor.heartbeat',{'observed_at':(datetime.now(timezone.utc)-timedelta(hours=1)).isoformat(),'evidence_hash':'e'*64,'reported_running':0,'load_basis_points':0})
        assert r.get('code')=='gate_blocked';mark('delayed_heartbeat_rejected')
        w=work();admin('delete from ecos.executor_capability where executor_instance_id=%s',(f.inst,))
        assert claim()['status']=='NO_ELIGIBLE_WORK';mark('incompatible_capability_no_claim')
        admin("insert into ecos.executor_capability(executor_instance_id,capability_name,capability_version,attested_by,expires_at) values(%s,'db.governed_operations',1,%s,clock_timestamp()+interval '1 hour')",(f.inst,f.p))
        r=claim();assert r['data']['claim']['occurrence_id']==w;mark('capability_compatible_atomic_claim')
        pkg=r['data']['work_package'];assert len(json.dumps(pkg).encode())<32768 and 'description' not in pkg['task'];assert 'history' not in pkg and len(pkg['source_references'])==0
        admin("insert into ecos_meta.object_grant values(%s,'task',%s) on conflict do nothing",(f.p,f.task))
        assert good('work.package',{'fence':fence(r)})['data']['occurrence']['id']==w;mark('narrow_work_package_bounded_context')
        req=f.result_arguments(r['data']);good('work.complete',req);mark('database_deterministic_slice_complete')
        assert admin('select count(*) from ecos.package_measurement where occurrence_id=%s',(w,))[0][0]==2;mark('work_package_payload_bytes_recorded')
        # A provider-dependent stage and unrelated SQL stage prove scoped pressure.
        st=uid();admin("insert into ecos.work_stage_definition(id,work_definition_id,stage_key,kind,execution_surface,input_schema_id,result_schema_id,requires_approval) values(%s,%s,'dependent','deterministic','DATABASE_DETERMINISTIC','synthetic.input.v1','synthetic.result.v1',false)",(st,f.definition))
        admin("insert into ecos.stage_resource_requirement values(%s,'drive','requests',1,false)",(st,))
        dep=work(st);free=work()
        admin("insert into ecos.resource_health values('drive','BLOCKED','synthetic pressure',clock_timestamp(),clock_timestamp()+interval '1 hour','synthetic integration',1)")
        r=claim();assert r['data']['claim']['occurrence_id']==free;good('work.complete',f.result_arguments(r['data']));assert claim()['status']=='NO_ELIGIBLE_WORK';mark('resource_block_isolates_dependent_work_unrelated_continues')
        admin("update ecos.resource_health set pressure='NORMAL',record_version=record_version+1 where provider='drive'")
        r=claim();assert r['data']['claim']['occurrence_id']==dep;good('work.release',{'fence':fence(r),'reason':'synthetic_release'});mark('release_preserves_occurrence')
        r=claim();good('work.defer',{'fence':fence(r),'reason':'synthetic_defer','until':(datetime.now(timezone.utc)+timedelta(minutes=10)).isoformat()});assert claim()['status']=='NO_ELIGIBLE_WORK';mark('defer_backoff_enforced')
        admin("update ecos.work_occurrence set retry_at=clock_timestamp()-interval '1 second',record_version=record_version+1 where id=%s",(dep,))
        r=claim();good('work.fail',{'fence':fence(r),'reason':'synthetic_permanent','retryable':False});assert admin('select state from ecos.work_occurrence where id=%s',(dep,))[0][0]=='dead_lettered';mark('failure_dead_letter_audit')
        # Configured test budget is explicit synthetic config, never a guessed quota.
        admin("update ecos.resource_budget set hard_limit=10,elevated_limit=5,verification='OWNER_CONFIGURED',source='synthetic test fixture only',record_version=record_version+1 where provider='drive' and metric='requests'")
        for value,expected in [(0,'NORMAL'),(6,'ELEVATED'),(10,'BLOCKED'),(None,'UNKNOWN')]:
            r=good('resource.observe',{'provider':'drive','metric':'requests','observed_at':datetime.now(timezone.utc).isoformat(),'value':value,'evidence_hash':'f'*64},'operations_api');assert r['data']['pressure']==expected
        mark('resource_pressure_transitions_unknown_not_zero')
        # Durable dependency wakeup survives listener absence and a consumed signal.
        first=work();second=work()
        admin("insert into ecos.work_dependency(occurrence_id,prerequisite_occurrence_id,required_result_schema_id,required_result_hash) values(%s,%s,'synthetic.result.v1',null)",(second,first))
        r=claim();assert r['data']['claim']['occurrence_id']==first;good('work.complete',f.result_arguments(r['data']))
        assert admin('select count(*) from ecos.work_wakeup where occurrence_id=%s and consumed_at is null',(second,))[0][0]==1;mark('completion_transaction_durable_dependent_wakeup')
        admin('update ecos.work_wakeup set consumed_at=clock_timestamp() where occurrence_id=%s',(second,))
        good('recovery.sweep',{'limit':100},'operations_api');assert admin('select consumed_at from ecos.work_wakeup where occurrence_id=%s',(second,))[0][0] is None
        r=claim();assert r['data']['claim']['occurrence_id']==second;good('work.complete',f.result_arguments(r['data']));mark('lost_transient_wakeup_recovered')
        # Loss recovery preserves immutable results and rejects the abandoned fence.
        lost=work();r=claim();old=fence(r)
        admin("update ecos.work_claim set expires_at=clock_timestamp()-interval '1 second',record_version=record_version+1 where id=%s",(old['claim_id'],))
        good('recovery.sweep',{'limit':100},'operations_api');assert admin('select count(*) from ecos.repair_action a join ecos.integrity_finding i on i.id=a.finding_id where i.entity_id=%s',(lost,))[0][0]==1
        assert op('work.release',{'fence':old,'reason':'stale'}).get('code')=='stale_version'
        r=claim();assert fence(r)['claim_version']>old['claim_version'];good('work.complete',f.result_arguments(r['data']));mark('executor_loss_expired_fence_repair_readback')
        # A latest old observation cannot claim freshness.
        admin("insert into ecos.heartbeat(executor_instance_id,observed_at,received_at,valid_until,availability,evidence_hash) values(%s,clock_timestamp()-interval '1 hour',clock_timestamp(),clock_timestamp()-interval '59 minutes','available',%s)",(f.inst,'a'*64))
        assert admin('select availability from ecos.v_node_health where executor_instance_id=%s',(f.inst,))[0][0]=='unavailable'
        good('recovery.sweep',{'limit':100},'operations_api');assert admin('select status from ecos.executor_presence where executor_instance_id=%s',(f.inst,))[0][0]=='unavailable';mark('deterministic_stale_detection')
        good('executor.register',register)
        # Semantic adapter contract on the actual SQL surface; interpretation fixture is synthetic.
        admin("update ecos.executor set surface='ONLINE_SEMANTIC',record_version=record_version+1 where id=%s",(f.ex,))
        st2=uid();admin("insert into ecos.work_stage_definition(id,work_definition_id,stage_key,kind,execution_surface,input_schema_id,result_schema_id,requires_approval) values(%s,%s,'semantic','semantic','ONLINE_SEMANTIC','synthetic.input.v1','synthetic.result.v1',false)",(st2,f.definition))
        sw=work(st2);r=claim();assert r['data']['claim']['occurrence_id']==sw
        source=admin('select to_jsonb(t),ecos_meta.content_hash(to_jsonb(t)) from ecos.task t where id=%s',(f.task,))[0]
        ref={'record_type':'task','record_id':f.task,'record_version':source[0]['record_version'],'content_hash':source[1],'authority':'structured_ecos'}
        versions=[{'record_type':'task','record_id':f.task,'record_version':source[0]['record_version']}]
        ev={'source':ref,'assertion':'Synthetic owner requests waiting state','verification':'verified'}
        item={'item_id':uid(),'depends_on_item_ids':[],'source_references':[ref],'expected_record_versions':versions,'proposed_operations':[{'operation':'task.transition','arguments':{'task_id':f.task,'expected_version':source[0]['record_version'],'target_state':'waiting','wait_reason':'owner','reason_code':'synthetic_review','evidence':[ev]}}],'evidence':[ev],'confidence_basis_points':9000,'unresolved_ambiguity':[]}
        proposal={'id':uid(),'proposal_type':'synthetic_review','schema_version':'1.0.0','created_at':datetime.now(timezone.utc).isoformat(),'correlation_id':f.correlation,'source_references':[ref],'expected_record_versions':versions,'items':[item]}
        proposal['content_hash']=admin('select ecos_meta.content_hash(%s)',(Jsonb(proposal),))[0][0]
        good('semantic.proposal.submit',{'fence':fence(r),'proposal':proposal})
        assert admin('select lifecycle_state from ecos.task where id=%s',(f.task,))[0][0]=='open';mark('semantic_submission_immutable_no_business_mutation')
        commit_work=work();admin("update ecos.work_context set operation='proposal.commit' where occurrence_id=%s",(commit_work,))
        admin("insert into ecos.work_dependency(occurrence_id,prerequisite_occurrence_id,required_result_schema_id,required_result_hash) values(%s,%s,'synthetic.result.v1',%s)",(commit_work,sw,proposal['content_hash']))
        result_args=f.result_arguments(r['data']);result_args['result']['content_hash']=proposal['content_hash']
        good('work.complete',result_args)
        admin("update ecos.executor set surface='DATABASE_DETERMINISTIC',record_version=record_version+1 where id=%s",(f.ex,))
        r=claim();assert r['data']['claim']['occurrence_id']==commit_work
        party=uid();admin("insert into ecos.party values(%s,%s,'Synthetic recipient',1)",(party,'SYNTHETIC-PHASE2-'+party))
        admin("insert into ecos_meta.notification_policy values(%s,%s,'sms','synthetic:recipient','synthetic:message',%s,'synthetic-phase2')",(f.task,party,'a'*64))
        good('proposal.commit',{'proposal':proposal},'operations_api')
        assert admin('select lifecycle_state from ecos.task where id=%s',(f.task,))[0][0]=='waiting'
        good('work.complete',f.result_arguments(r['data']));mark('semantic_to_deterministic_commit_hybrid_handoff')
        cmd=admin("select id from ecos.provider_command where causation_id in(select id from ecos.domain_event where aggregate_id=%s) and provider='synthetic'",(f.task,))[0][0]
        assert admin('select count(*) from ecos.delivery where provider_command_id=%s',(cmd,))[0][0]==1;mark('synthetic_notification_delivery_provider_outbox')
        admin('grant provider_adapter to postgres');f.added_roles.append('provider_adapter')
        admin("insert into ecos_meta.principal_binding values('provider_adapter',%s,%s,true)",(f.p,f.inst))
        admin("insert into ecos_meta.object_grant values(%s,'provider_command',%s)",(f.p,cmd))
        with target.connect() as db:
            db.execute('set local role provider_adapter');outbox=db.execute('select ecos.claim_outbox(30)').fetchone()[0]
            attempt=db.execute('select ecos.begin_synthetic_attempt(%s,%s)',(cmd,'a'*64)).fetchone()[0]
        provider_result={'id':uid(),'schema_version':'1.0.0','created_at':datetime.now(timezone.utc).isoformat(),'provider_command_id':str(cmd),'provider_attempt_id':str(attempt),'outcome':'reconciled','provider_object_id':'SYNTHETIC-PHASE2','observed_at':datetime.now(timezone.utc).isoformat(),'evidence_hash':'b'*64,'reconciled_outcome':'succeeded'}
        good('provider.result.record',{'result':provider_result},'provider_adapter')
        good('provider.result.record',{'result':provider_result},'provider_adapter')
        assert admin('select count(*) from ecos.provider_result where provider_command_id=%s',(cmd,))[0][0]==1
        assert admin('select state from ecos.delivery where provider_command_id=%s',(cmd,))[0][0]=='delivered';mark('synthetic_provider_duplicate_idempotency')
        with target.connect() as db:
            db.execute('set local role provider_adapter');db.execute('select ecos.ack_outbox(%s,%s)',(outbox['item']['id'],outbox['lease_token']))
        mark('synthetic_adapter_ack_after_durable_result')
        good('executor.stop',{'reason':'synthetic graceful completion'});mark('graceful_stop_no_active_claims')
        assert op('executor.register',register).get('code')=='gate_blocked';mark('stopped_instance_cannot_restart_same_identity')
        assert admin('select count(*) from ecos_meta.operation_audit where principal_id=%s',(f.p,))[0][0]>20;mark('operation_audit_durable')
        return checks
    finally:f.cleanup()

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--pg-bin',required=True,type=Path);parser.add_argument('--openssl',required=True,type=Path);parser.add_argument('--report',required=True,type=Path);args=parser.parse_args()
    root=Path(tempfile.mkdtemp(prefix='ecos-phase2-test-'));data=root/'data';pw=root/'init-password';password=secrets.token_urlsafe(32);port=55433;running=False
    report={'started_at':datetime.now(timezone.utc).isoformat(),'status':'failed','provider_side_effects':False,'ecos_1x_writes':False,'authority_switch':False,'runtime_directory':str(root)}
    def native(binary,a):
        with tempfile.TemporaryFile(mode='w+',encoding='utf-8') as output:
            proc=subprocess.run([str(args.pg_bin/(binary+'.exe'))]+list(map(str,a)),stdout=output,stderr=output,text=True,creationflags=subprocess.CREATE_NO_WINDOW,timeout=120)
            output.seek(0);message=output.read()
        if proc.returncode:raise RuntimeError(message.replace(password,'[REDACTED]')[:2000])
    try:
        with socket.socket() as sock:sock.bind(('127.0.0.1',port))
        account=os.environ.get('USERDOMAIN','')+'\\'+getpass.getuser()
        subprocess.run(['icacls',str(root),'/inheritance:r','/grant:r',account+':(OI)(CI)F'],capture_output=True,check=True,creationflags=subprocess.CREATE_NO_WINDOW)
        pw.write_text(password,encoding='utf-8')
        try:native('initdb',['-D',data,'-U','postgres','--auth=scram-sha-256','--pwfile='+str(pw),'--encoding=UTF8','--locale=C'])
        finally:pw.unlink(missing_ok=True)
        subprocess.run([str(args.openssl),'req','-x509','-nodes','-newkey','rsa:2048','-keyout',str(data/'server.key'),'-out',str(data/'server.crt'),'-days','1','-subj','/CN=localhost'],capture_output=True,check=True,creationflags=subprocess.CREATE_NO_WINDOW)
        native('pg_ctl',['-D',data,'-l',root/'server.log','-o',f'-h 127.0.0.1 -p {port} -c ssl=on -c max_connections=25 -c log_statement=none -c log_min_error_statement=panic','-w','start']);running=True
        target=LocalTarget(password,port)
        with target.connect() as db:
            db.autocommit=True
            report['postgresql']=db.execute('select version()').fetchone()[0]
            chain=render(inventory(ROOT/'db/migrations')).replace('\\set ON_ERROR_STOP on\n','',1)
            db.execute(chain,prepare=False);report['migration_rebuild']='passed'
            db.execute(chain,prepare=False);report['migration_repeat']='passed'
            report['phase1_regression']=run_sql_suite(db)
        report['phase2_checks']=tests(target)
        f=Fixture(target);f.seed()
        try:report['concurrency']={'same_work':contend(f,1),'different_work':contend(f,15)}
        finally:f.cleanup()
        assert all(x['status']=='passed' for x in report['concurrency'].values())
        report['status']='passed'
    except Exception as exc:
        report['error_type']=type(exc).__name__;report['error']=str(exc).replace(password,'[REDACTED]')[:2000]
    finally:
        if running:native('pg_ctl',['-D',data,'-m','fast','-w','stop']);report['disposable_server_stopped']=True
        args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(report,indent=2,default=str)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('concurrency',)},default=str))
    return 0 if report['status']=='passed' else 1
if __name__=='__main__':raise SystemExit(main())
