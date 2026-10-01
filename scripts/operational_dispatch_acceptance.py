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

 admin("update ecos.executor set surface='RESIDENT_DETERMINISTIC_PROVIDER',record_version=record_version+1 where id=%s",(f.ex,))
 good('executor.register',{'host':'SYNTHETIC','runtime':'structural-acceptance','software_version':'candidate35','evidence_hash':'a'*64},'executor')
 admin("insert into ecos_meta.principal_binding values('provider_adapter',%s,%s,true)",(f.p,f.inst))
 from types import SimpleNamespace
 from runtime.resident2x.operational_sms import dispatch,inline
 for n in (1,2):
  admin("update ecos.work_stage_definition set stage_key='sms_outbound_dispatch',execution_surface='RESIDENT_DETERMINISTIC_PROVIDER',record_version=record_version+1 where id=%s",(f.stage,))
  w=f.add_work(1)[0];admin("insert into ecos.work_context(occurrence_id,operation,input) values(%s,'work.complete','{}')",(w,))
  body='Synthetic internal dispatch';hash_=hashlib.sha256(body.encode()).hexdigest();deliveries=[]
  for j in range(2):
   party,nid,did=uid(),uid(),uid();deliveries.append(did)
   admin("insert into ecos.party(id,business_id,name) values(%s,%s,'Synthetic')",(party,'SYNTHETIC-'+party))
   admin("insert into ecos.notification(id,business_reason_code,subject_type,subject_id,content_artifact_uri,content_hash,policy_version) values(%s,'synthetic_dispatch','task',%s,%s,%s,1)",(nid,f.task,inline('text/plain',body.encode()),hash_))
   admin("insert into ecos.delivery(id,notification_id,recipient_party_id,channel,destination_reference,policy_key,state) values(%s,%s,%s,'sms','+15005550006','synthetic','planned')",(did,nid,party))
   grant('notification',nid);grant('delivery',did)
  deliveries.sort()
  admin("update ecos.delivery set state='ready',record_version=record_version+1 where id=%s",(deliveries[0],))
  admin("delete from ecos_meta.notification_policy where task_id=%s",(f.task,))
  admin("insert into ecos_meta.notification_policy select %s,d.recipient_party_id,'sms',d.destination_reference,n.content_artifact_uri,n.content_hash,d.policy_key from ecos.delivery d join ecos.notification n on n.id=d.notification_id where d.id=%s",(f.task,deliveries[1]))
  claimed=good('work.next',{'executor_instance_id':f.inst,'lease_seconds':120},'executor');fence=f.result_arguments(claimed['data'])['fence']
  package=claimed['data']['work_package'];calls=[]
  class Runtime:
   def invoke(self,op,args,**kw):return good(op,args,'provider_adapter' if op=='provider.result.record' else 'executor')
   def read(self,kind,identity):return read(kind,identity)
  def send(request):
   calls.append(request['delivery_id'])
   if request['delivery_id']=='NDEL-'+deliveries[0]:raise ValueError('synthetic_unknown_outcome')
   return SimpleNamespace(provider_message_id='SM'+str(n)*32,status='accepted')
  def guard():good('work.package',{'fence':fence},'executor')
  value=dispatch(Runtime(),package,guard,send,{'sender':'+15005550006','account_scope':'synthetic','transport':{},'connector_definitions':{}})
  assert deliveries[1] in value['accepted'] and any(x['delivery_id']==deliveries[0] for x in value['held']),value
  assert len(calls)==2,calls
  assert read('delivery',deliveries[1])['record']['state']=='delivered'
  assert admin("select outcome from ecos.provider_command where id=(select provider_command_id from ecos.delivery where id=%s)",(deliveries[0],))[0][0]=='unknown_outcome'
  assert good('sms.dispatch.begin',{'fence':fence,'delivery_id':deliveries[1],'expected_version':1,'account_scope':'synthetic','request':{'to':'+15005550006','from':'+15005550006','body':body}},'executor')['data']['disposition']=='completed'
  good('work.complete',f.result_arguments(claimed['data']),'executor')
  assert read('work_occurrence',w)['record']['state']=='succeeded'
  # Remove the prior ambiguous fixture from this caller's scope only; retain all evidence.
  admin("delete from ecos_meta.object_grant where principal_id=%s and record_type='delivery' and record_id=%s",(f.p,deliveries[0]))
  report['passes'].append({'pass':n,'resident_dispatch_sql_sid_readback':'PASS','unrelated_delivery_after_unknown':'PASS','no_replay':'PASS','external_effects':0})
  print(json.dumps(report['passes'][-1]),flush=True)
 report['status']='PASS'
finally:
 if running:native([pg/'pg_ctl.exe','-D',root/'data','-m','fast','-w','stop'])
 (root/'report.json').write_text(json.dumps(report,indent=2))
 print('Receipt: '+str(root/'report.json'))
