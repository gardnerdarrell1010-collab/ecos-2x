"""Owner-authorized real Toast reads through a dedicated shadow Resident process.

Private provider payloads and credentials stay in the ACL-protected ignored state directory.
This does not publish to Drive/Sheets or transfer domain ownership.
"""
import argparse,json,secrets,subprocess,sys,time
from datetime import datetime,timedelta,timezone
from pathlib import Path
from uuid import uuid4
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'src'),str(ROOT/'scripts')]
from psycopg import sql
from psycopg.types.json import Jsonb
from resident2x_acceptance import hosted_admin,secure_directory,resident1_snapshot,SHARED
from runtime.resident2x.executor import save
def uid():return str(uuid4())

def enroll(connect,database,state,dates,crash=None):
    principal,instance,executor,correlation=[uid() for _ in range(4)]
    role='resident2x_'+uuid4().hex[:16];password=secrets.token_urlsafe(40)
    config={'identity':'RESIDENT_ADA_2X_HOME01','principal_id':principal,'instance_id':instance,'executor_id':executor,
        'correlation_id':correlation,'authority':'DOMAIN_SCOPED_PRODUCTION','domain':'toast.acquisition','execution_mode':'shadow',
        'provider_effects_enabled':False,'state_directory':str(state),'database_password_file':str(state/'database.secret'),
        'database':dict(database,user=role+'.loonpojawpfagzobxoko'),
        'control_plane':'POSTGRESQL','work_sources':['POSTGRESQL'],
        'capabilities':{'ecos.2x.execute':1,'local.process.execute':1,'toast.api.read':1,'secure.reference.resolve':1,'db.governed_operations':1},
        'heartbeat_seconds':3,'lease_seconds':30,'poll_seconds':1,
        'wave1':{'shared_root':str(SHARED),'credential_reference':r'D:\ECOS\Credentials\ecos-resident-ada.json'}}
    if crash:config['wave1']['acceptance_crash']=crash
    work=[];as_of=datetime.now(timezone.utc).isoformat()
    with connect() as db:
        assert db.execute("select owner from ecos_meta.domain_authority where domain='toast.acquisition'").fetchone()[0]=='1X'
        assert db.execute("select count(*) from ecos.v_executor_status where status='available'").fetchone()[0]==0
        db.execute(sql.SQL('create role {} login password {} nosuperuser nocreatedb nocreaterole inherit').format(sql.Identifier(role),sql.Literal(password)))
        db.execute(sql.SQL('grant executor,operations_api to {}').format(sql.Identifier(role)))
        db.execute("insert into ecos.executor(id,name,surface,enabled) values(%s,%s,'RESIDENT_DETERMINISTIC_PROVIDER',true)",(executor,'wave1_shadow_'+executor.replace('-','')))
        db.execute("insert into ecos.executor_instance(id,executor_id,boot_id,availability,principal_id) values(%s,%s,%s,'available',%s)",(instance,executor,uid(),principal))
        db.execute('insert into ecos_meta.principal_binding values(%s,%s,%s,true)',(role,principal,instance))
        db.execute("insert into ecos_meta.principal_domain select %s,domain,'shadow',epoch from ecos_meta.domain_authority where domain='toast.acquisition'",(principal,))
        for op in ('executor.register','executor.heartbeat','executor.stop','work.next','work.package','work.renew','work.complete','work.fail','work.defer','work.release','recovery.sweep','toast.batch.commit'):
            db.execute('insert into ecos_meta.principal_operation values(%s,%s)',(principal,op))
        for cap in config['capabilities']:
            db.execute("insert into ecos.capability(name,version,description) values(%s,1,'Wave 1 existing deterministic provider capability') on conflict do nothing",(cap,))
            db.execute("insert into ecos.executor_capability(executor_instance_id,capability_name,capability_version,attested_by,expires_at) values(%s,%s,1,%s,clock_timestamp()+interval '2 hours')",(instance,cap,principal))
        for day in dates:
            task,retry,definition,stage,occurrence=[uid() for _ in range(5)]
            db.execute("insert into ecos.task(id,business_id,title,project_id,lifecycle_state,wait_reason,description) values(%s,%s,'Wave 1 Toast shadow acceptance',null,'open','none','A029/A047 retain 1X authority; no compatibility publication')",(task,'WAVE1-SHADOW-'+task))
            db.execute("insert into ecos.retry_policy(id,max_attempts,initial_delay_seconds,max_delay_seconds,backoff_multiplier,jitter_basis_points,retryable_error_classes) values(%s,3,1,10,2,0,'[\"transient\"]')",(retry,))
            db.execute("insert into ecos.work_definition(id,name,definition_version,enabled,fulfillment_kind,retry_policy_id) values(%s,%s,1,true,'staged',%s)",(definition,'wave1_shadow_'+definition.replace('-',''),retry))
            db.execute("insert into ecos.work_stage_definition(id,work_definition_id,stage_key,kind,execution_surface,input_schema_id,result_schema_id,requires_approval) values(%s,%s,'toast_acquire','deterministic','RESIDENT_DETERMINISTIC_PROVIDER','wave1.toast.input.v1','wave1.toast.result.v1',false)",(stage,definition))
            for cap in config['capabilities']:
                db.execute('insert into ecos.stage_capability_requirement(stage_definition_id,capability_name,minimum_version) values(%s,%s,1)',(stage,cap))
            db.execute("insert into ecos.work_occurrence(id,work_definition_id,stage_definition_id,fulfillment_id,task_id,state,occurrence_key,due_at) values(%s,%s,%s,%s,%s,'ready',%s,clock_timestamp())",(occurrence,definition,stage,uid(),task,'WAVE1-SHADOW-'+occurrence))
            for kind,identity in (('task',task),('work_occurrence',occurrence)):
                db.execute('insert into ecos_meta.object_grant values(%s,%s,%s)',(principal,kind,identity))
                db.execute("insert into ecos_meta.object_domain values(%s,%s,'toast.acquisition')",(kind,identity))
            db.execute("insert into ecos.work_context(occurrence_id,operation,input) values(%s,'work.complete',%s)",(occurrence,Jsonb({'business_date':day,'as_of':as_of})))
            work.append({'business_date':day,'occurrence_id':occurrence,'task_id':task,'definition_id':definition})
    (state/'database.secret').write_text(password,encoding='utf-8')
    save(state/'config.json',config);save(state/'enrollment.json',{'role':role,'work':work})
    return config,work,role

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--crash',choices=['after_acquisition','after_commit']);parser.add_argument('--dates',nargs='+');parser.add_argument('--resume',type=Path);args=parser.parse_args()
    connect,database=hosted_admin();before=resident1_snapshot()
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S');state=args.resume or ROOT/'.local'/('wave1-resident-shadow-'+stamp)
    dates=args.dates or [(datetime.now().date()-timedelta(days=i)).isoformat() for i in (2,1)]
    if args.resume:
        config=json.loads((state/'config.json').read_text());enrollment=json.loads((state/'enrollment.json').read_text());work=enrollment['work'];role=enrollment['role']
        assert config['execution_mode']=='shadow' and config['domain']=='toast.acquisition'
    else:
        secure_directory(state);config,work,role=enroll(connect,database,state,dates,args.crash)
    report={'state_directory':str(state),'mode':'shadow','status':'failed','domain_transfer':False,'provider_business_writes':False}
    try:
        attempts=2 if args.crash else 1
        for attempt in range(attempts):
            log=state/('resident-'+str(attempt)+'.log')
            with log.open('w') as stream:
                child=subprocess.Popen([sys.executable,'-B',str(ROOT/'scripts/resident2x.py'),'--config',str(state/'config.json'),'--max-cycles','8'],cwd=ROOT,stdout=stream,stderr=stream,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                print(json.dumps({'state_directory':str(state),'resident_pid':child.pid,'attempt':attempt}),flush=True)
                code=child.wait(timeout=480)
            if args.crash and attempt==0:
                assert code==77,('crash injection did not execute',code)
                time.sleep(config['lease_seconds']+2)
            else:assert code==0,('resident failed',code)
        receipts=[json.loads((state/'results'/(w['occurrence_id']+'.json')).read_text()) for w in work]
        assert all(r.get('completion',{}).get('status')=='committed' and r['result']['sql_readback_verified'] for r in receipts)
        with connect() as db:
            for w,r in zip(work,receipts):
                row=db.execute('select to_jsonb(b) from ecos.toast_batch b where occurrence_id=%s',(w['occurrence_id'],)).fetchone()[0]
                assert row['content_hash']==r['result']['content_hash'] and row['execution_mode']=='shadow'
                assert db.execute('select state from ecos.work_occurrence where id=%s',(w['occurrence_id'],)).fetchone()[0]=='succeeded'
        after=resident1_snapshot()
        assert all(before[k]==after[k] for k in ('pid','version','source_sha256','pointer_sha256'))
        report.update(status='passed',crash_recovery=args.crash,work=work,receipts=[{'occurrence_id':r['occurrence_id'],'pid':r['pid'],'result':r['result']} for r in receipts],resident1_unchanged=True)
    except Exception as exc:
        report.update(error_type=type(exc).__name__,safe_error=str(exc)[:300])
    finally:
        # Teardown only this explicitly enrolled shadow identity; never alter competing claims.
        with connect() as db:
            active=db.execute("select count(*) from ecos.work_claim where executor_instance_id=%s and state='active' and expires_at>clock_timestamp()",(config['instance_id'],)).fetchone()[0]
            if active==0:
                db.execute("update ecos.executor_presence set status='stopped',stopped_at=clock_timestamp(),record_version=record_version+1 where executor_instance_id=%s",(config['instance_id'],))
                db.execute('update ecos.executor set enabled=false,record_version=record_version+1 where id=%s',(config['executor_id'],))
                db.execute('update ecos.work_definition set enabled=false,record_version=record_version+1 where id=any(%s::uuid[]) and enabled',([w['definition_id'] for w in work],))
                db.execute('update ecos_meta.principal_binding set enabled=false where principal_id=%s',(config['principal_id'],))
                db.execute(sql.SQL('alter role {} nologin').format(sql.Identifier(role)))
                report['shadow_enrollment_retired']=True
            else:report['shadow_enrollment_retired']=False
        save(state/'report.json',report)
    print(json.dumps(report));return 0 if report['status']=='passed' else 1
if __name__=='__main__':raise SystemExit(main())
