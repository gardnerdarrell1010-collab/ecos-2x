"""Exactly two internal Task Loop selection passes; production stays disabled."""
import sys,json,os,tempfile,secrets,socket,subprocess,hashlib
from pathlib import Path
from datetime import datetime,timezone
from uuid import uuid4
r=Path(__file__).resolve().parents[1];sys.path[:0]=[str(r),str(r/'src'),str(r/'scripts')]
from resident2x_acceptance import native,secure_directory,certificate
from phase2_integration import LocalTarget,Fixture
from migrations import inventory,render
from psycopg.types.json import Jsonb
uid=lambda:str(uuid4())
root=Path(tempfile.gettempdir())/('ecos-task-loop-'+uuid4().hex)
secure_directory(root)
import argparse
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--pg-bin',required=True,type=Path)
parser.add_argument('--openssl',required=True,type=Path)
args=parser.parse_args()
pg=args.pg_bin
password=secrets.token_urlsafe(32);pw=root/'init-password';pw.write_text(password)
with socket.socket() as sock:
 sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
running=False;report={'status':'PENDING','passes':[],'production_writes':0}
try:
 native([pg/'initdb.exe','-D',root/'data','-U','postgres','--auth=scram-sha-256','--pwfile='+str(pw),'--encoding=UTF8','--locale=C'])
 pw.unlink()
 certificate(root/'data',args.openssl)
 native([pg/'pg_ctl.exe','-D',root/'data','-l',root/'server.log','-o',f'-h 127.0.0.1 -p {port} -c ssl=on -c log_statement=none -c log_min_error_statement=panic','-w','start']);running=True
 target=LocalTarget(password,port)
 with target.connect() as db:
  db.autocommit=True
  for role in ('anon','authenticated','service_role'):
   db.execute('create role '+role+' nologin')
  db.execute(render(inventory(r/'db/migrations')).replace('\\set ON_ERROR_STOP on\n',''),prepare=False)
 from repair_task_loop_population import read_sources,source_inputs
 from resident2x_acceptance import hosted_admin
 from datetime import timedelta
 connect,_=hosted_admin()
 with connect() as db:
  assert db.execute('select count(*) from ecos.executor where enabled').fetchone()==(0,)
  assert db.execute('select count(*) from ecos.work_definition where enabled').fetchone()==(0,)
  sources=read_sources(db)
  identities={name:(str(e),str(i),str(p)) for name,e,i,p in db.execute("select e.name,e.id,i.id,i.principal_id from ecos.executor e join ecos.executor_instance i on i.executor_id=e.id where e.name in ('online_ada_2x','resident_ada_2x_home01_gmail')")}
 specs=json.loads((r/'runtime/operational_work.json').read_text())['functions']
 def admin(q,a=()):
  with target.connect() as db:
   cur=db.execute(q,a);return cur.fetchall() if cur.description else []
 fixtures={}
 for pass_number in (1,2):
  selected_count=0
  for profile,surface,keys in [('online_ada_2x','ONLINE_SEMANTIC',['A015','A016','A018','A024','A036']),('resident_ada_2x_home01_gmail','RESIDENT_DETERMINISTIC_PROVIDER',['A027','A028'])]:
   if pass_number==1:
    f=Fixture(target)
    # Disposable copies reuse the actual approved identity IDs.
    f.ex,f.inst,f.p=identities[profile]
    f.seed();fixtures[profile]=f
   else:
    f=fixtures[profile]
    for role in ('executor','operations_api'):
     admin('insert into ecos_meta.principal_binding values(%s,%s,%s,true)',(role,f.p,f.inst))
   admin('update ecos.executor set surface=%s,record_version=record_version+1 where id=%s',(surface,f.ex))
   admin('update ecos.work_stage_definition set execution_surface=%s,record_version=record_version+1 where id=%s',(surface,f.stage))
   if pass_number==1:admin("insert into ecos.executor_capability(executor_instance_id,capability_name,capability_version,attested_by,expires_at) values(%s,'ecos.2x.execute',1,%s,clock_timestamp()+interval '1 hour')",(f.inst,f.p))
   def operation(op,args):
    with target.connect() as db:
     db.execute('set local role executor')
     return db.execute('select ecos.operate(%s,%s)',(op,Jsonb(f.request(args)))).fetchone()[0]
   def good(op,args):
    v=operation(op,args);assert 'code' not in v,(op,v.get('code'));return v
   if pass_number==1:good('executor.register',{'host':'INTERNAL','runtime':'task-loop-controlled','software_version':'repair','evidence_hash':'a'*64})
   ids=f.add_work(len(keys));inputs={}
   for short,oid in zip(keys,ids):
    row=dict(sources['TASK-AUTO-'+short[1:].zfill(6)][0]);v=source_inputs(row);inputs[oid]=v
    admin('update ecos.work_occurrence set due_at=%s,retry_at=%s,ready_override_at=%s,record_version=record_version+1 where id=%s',(v['due_at'],v['retry_at'],v['ready_override_at'],oid))
    admin('insert into ecos.work_priority(occurrence_id,business_impact,recurrence_period_seconds) values(%s,%s,%s)',(oid,v['business_impact'],specs[short]['period_seconds']))
    admin("insert into ecos.work_context(occurrence_id,operation,input) values(%s,'work.complete',%s)",(oid,Jsonb({'function':short,'approved_profile':profile,'internal_no_business_effects':True})))
   # One bounded owner RUN NOW request proves future due-time readiness, and
   # the second item cannot run until the first produces the required result.
   now=datetime.now(timezone.utc)
   override=source_inputs({'Next Eligible At':(now+timedelta(days=1)).isoformat(),'Dispatch Importance':'5','Dispatch Score':'16.000','Dispatch Score At':now.isoformat(),'Last Successful At':''})
   admin('update ecos.work_occurrence set due_at=%s,ready_override_at=%s,retry_at=null,record_version=record_version+1 where id=%s',(override['due_at'],override['ready_override_at'],ids[0]))
   admin("insert into ecos.work_dependency(occurrence_id,prerequisite_occurrence_id,required_result_schema_id,required_result_hash) values(%s,%s,'synthetic.result.v1',null)",(ids[1],ids[0]))
   for index in range(len(ids)):
    evaluated=admin('select ecos_meta.selection(id,%s,clock_timestamp()) from ecos.work_occurrence where id=any(%s::uuid[])',(f.inst,ids))
    eligible=[x[0] for x in evaluated if x[0]['eligible']]
    def rank(x):return tuple(-int(x[k]) for k in ('priority_override','immediate_ready','sla_breach_seconds','deadline_pressure_seconds','business_impact','recurrence_relative_age_basis_points'))+(x['created_at'],x['occurrence_id'])
    expected=sorted(eligible,key=rank)[0]['occurrence_id']
    if index==0:assert expected==ids[0]
    claimed=good('work.next',{'executor_instance_id':f.inst,'lease_seconds':120})
    assert claimed['status']=='CLAIMED' and claimed['data']['claim']['occurrence_id']==expected
    package=claimed['data']['work_package'];fence=package['fence']
    assert package['stage']['execution_surface']==surface and claimed['data']['claim']['executor_instance_id']==f.inst
    assert good('work.package',{'fence':fence})['data']['occurrence']['id']==expected
    bad=dict(fence);bad['fence_token']=uid()
    assert operation('work.package',{'fence':bad}).get('code') is not None
    good('work.complete',f.result_arguments(claimed['data']))
    assert admin('select state from ecos.work_occurrence where id=%s',(expected,))[0][0]=='succeeded'
    assert operation('work.package',{'fence':fence}).get('code') is not None
    selected_count+=1
   assert good('work.next',{'executor_instance_id':f.inst,'lease_seconds':120})['status']=='NO_ELIGIBLE_WORK'
   assert admin('select count(*) from ecos.provider_command')[0][0]==0
   # Switch only the disposable caller binding; do not stop/restart an executor.
   admin('delete from ecos_meta.principal_binding where principal_id=%s',(f.p,))
  result={'pass':pass_number,'ranked_selections_completed':selected_count,'work_next':'PASS','run_now':'PASS','dependency_wakeup':'PASS','claim_fencing':'PASS','package':'PASS','surface_routing':'PASS','completion_next_selection':'PASS','provider_business_effects':0}
  report['passes'].append(result);print(json.dumps(result),flush=True)
 report['status']='PASS'
finally:
 if running:native([pg/'pg_ctl.exe','-D',root/'data','-m','fast','-w','stop'])
 (root/'report.json').write_text(json.dumps(report,indent=2))
 print('Receipt: '+str(root/'report.json'))
