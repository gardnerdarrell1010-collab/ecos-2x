"""Two committed synthetic SQL paths per contract on a private disposable database."""
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
root=Path(tempfile.gettempdir())/('ecos-structural-'+uuid4().hex)
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
 f=Fixture(target);f.seed()
 def admin(q,a=()):
  with target.connect() as db:
   cur=db.execute(q,a);return cur.fetchall() if cur.description else []
 def good(op,args,role='operations_api'):
  with target.connect() as db:
   db.execute('set local role '+role)
   res=db.execute('select ecos.operate(%s,%s)',(op,Jsonb(f.request(args)))).fetchone()[0]
   assert 'code' not in res,(op,res)
   return res
 def read(kind,identity):
  with target.connect() as db:
   db.execute('set local role operations_api')
   return db.execute('select ecos.read_record(%s,%s)',(kind,identity)).fetchone()[0]
 def grant(kind,identity):admin('insert into ecos_meta.object_grant values(%s,%s,%s)',(f.p,kind,identity))
 def source():
  rr=read('task',f.task)
  return {'record_type':'task','record_id':f.task,'record_version':rr['record']['record_version'],'content_hash':rr['content_hash'],'authority':'structured_ecos'}
 for cap in ('ecos.2x.execute','semantic.interpret'):
  admin("insert into ecos.executor_capability(executor_instance_id,capability_name,capability_version,attested_by,expires_at) values(%s,%s,1,%s,clock_timestamp()+interval '1 hour')",(f.inst,cap,f.p))

 good('executor.register',{'host':'SYNTHETIC','runtime':'operational-acceptance','software_version':'candidate37','evidence_hash':'a'*64},'executor')
 import importlib.util
 from runtime.resident2x.operational_sms import intake
 spec=importlib.util.spec_from_file_location('accepted_sms_parser','D:/ECOS/Node/runtime/releases/slots/1.0.011/ecos_runtime/communications.py')
 primitive=importlib.util.module_from_spec(spec);spec.loader.exec_module(primitive)
 admin("update ecos.executor set surface='RESIDENT_DETERMINISTIC_PROVIDER',record_version=record_version+1 where id=%s",(f.ex,))
 admin("update ecos.work_stage_definition set stage_key='sms_transport_queue_consume',execution_surface='RESIDENT_DETERMINISTIC_PROVIDER',record_version=record_version+1 where id=%s",(f.stage,))
 for n in (1,2):
  w=f.add_work(1)[0];admin("insert into ecos.work_context(occurrence_id,operation,input) values(%s,'work.complete','{}')",(w,))
  admin("update ecos.work_occurrence set task_id=null,record_version=record_version+1 where id=%s",(w,))
  admin("insert into ecos_meta.object_domain values('work_occurrence',%s,'synthetic.acceptance')",(w,))
  admin("insert into ecos.work_priority(occurrence_id,recurrence_period_seconds) values(%s,300)",(w,))
  claimed=good('work.next',{'executor_instance_id':f.inst,'lease_seconds':120},'executor');package=claimed['data']['work_package'];fence=package['fence']
  sid='SM'+str(n)*32;path='sms-transport/pending/inbound/'+sid+'.json';calls=[]
  event={'provider':'Twilio','provider_message_id':sid,'direction':'inbound','channel':'sms','body':'Synthetic receipt '+str(n),'from':'+15005550006','to':'+15005550006','received_at':datetime.now(timezone.utc).isoformat()}
  class Runtime:
   def invoke(self,op,args,**kw):return good(op,args,'executor')
   def read(self,kind,identity):return read(kind,identity)
  def http(request):
   operation=request['arguments']['operation'];calls.append(operation)
   if operation=='queue-list':return {'http_status':200,'items':[{'pathname':path}]}
   assert request['arguments']['transaction_id']==path
   if operation=='queue-item':return {'http_status':200,'event':event}
   assert operation=='queue-ack'
   # An independent connection observes the durable commit before ACK.
   assert admin("select count(*) from ecos.communication c join ecos.provider_receipt r on r.id=c.receipt_id where r.provider_object_id=%s",(sid,))[0][0]==1
   return {'http_status':200,'acknowledged':True,'processed_pathname':path.replace('/pending/','/processed/')}
  value=intake(Runtime(),package,lambda:good('work.package',{'fence':fence},'executor'),http,primitive.inbound_evidence,'synthetic')
  assert len(value['verified'])==1 and not value['held'],value
  assert calls==['queue-list','queue-item','queue-ack']
  good('work.complete',f.result_arguments(claimed['data']),'executor')
  assert read('work_occurrence',w)['record']['state']=='succeeded'
  report['passes'].append({'pass':n,'resident_list_get_commit_independent_readback_ack':'PASS','external_effects':0})
  print(json.dumps(report['passes'][-1]),flush=True)
 future=admin("select max(ended_at)+interval '301 seconds' from ecos.execution_run where occurrence_id=%s",(w,))[0][0]
 child=admin('select ecos_meta.materialize_occurrence(%s,%s)',(w,future))[0][0]
 assert admin("select domain from ecos_meta.object_domain where record_type='work_occurrence' and record_id=%s",(child,))[0][0]=='synthetic.acceptance'
 assert admin("select o.due_at=r.ended_at+interval '300 seconds' from ecos.work_occurrence o,ecos.execution_run r where o.id=%s and r.occurrence_id=%s",(child,w))[0][0]
 report['provider_recurrence_domain_preserved']=True
 report['status']='PASS'
finally:
 if running:native([pg/'pg_ctl.exe','-D',root/'data','-m','fast','-w','stop'])
 (root/'report.json').write_text(json.dumps(report,indent=2))
 print('Receipt: '+str(root/'report.json'))
