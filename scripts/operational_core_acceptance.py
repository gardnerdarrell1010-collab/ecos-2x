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
 for n in (1,2):
  for stage in ('task_coverage_proactive_control','sms_transport_queue_consume'):
   admin('update ecos.work_stage_definition set stage_key=%s,record_version=record_version+1 where id=%s',(stage,f.stage))
   w=f.add_work(1)[0]
   admin("insert into ecos.work_context(occurrence_id,operation,input) values(%s,'work.complete','{}')",(w,))
   claimed=good('work.next',{'executor_instance_id':f.inst,'lease_seconds':120},'executor')
   fence=f.result_arguments(claimed['data'])['fence']
   stamp=datetime.now(timezone.utc).isoformat()
   if stage=='task_coverage_proactive_control':
    scope=good('runtime.scope.read',{'fence':fence,'record_type':'task','after_id':None,'limit':100},'executor')['data'];assert any(x['record']['id']==f.task for x in scope['records'])
    party=uid();admin("insert into ecos.party(id,business_id,name) values(%s,%s,'Synthetic')",(party,'SYNTHETIC-'+party));grant('party',party)
    nid,did=uid(),uid()
    notification={'id':nid,'schema_version':'1.0.0','created_at':stamp,'record_version':1,'business_reason_code':'synthetic_review','subject_type':'task','subject_id':f.task,'content_artifact_uri':'synthetic:message','content_hash':'a'*64,'policy_version':1}
    delivery={'id':did,'schema_version':'1.0.0','created_at':stamp,'record_version':1,'notification_id':nid,'recipient_party_id':party,'channel':'sms','destination_reference':'synthetic:recipient','policy_key':'synthetic-'+str(n),'state':'planned','approval_request_id':None,'provider_command_id':None}
    a={'fence':fence,'notification':notification,'delivery':delivery,'source_references':[source()]}
    first=good('notification.enqueue',a,'executor')['data'];second=good('notification.enqueue',a,'executor')['data'];assert first==second
    assert read('delivery',did)['record']['state']=='planned'
   else:
    rid,cid=uid(),uid()
    receipt={'id':rid,'schema_version':'1.0.0','created_at':stamp,'provider':'twilio','account_scope':'synthetic','provider_event_id':cid,'dedupe_key':cid,'provider_object_id':cid,'provider_occurred_at':stamp,'received_at':stamp,'raw_artifact_uri':'synthetic:raw','raw_content_hash':'b'*64,'signature_verified':True,'correlation_id':f.correlation}
    communication={'id':cid,'schema_version':'1.0.0','created_at':stamp,'record_version':1,'receipt_id':rid,'channel':'sms','provider_thread_id':cid,'direction':'inbound','sender_party_id':None,'body_artifact_uri':'synthetic:body','body_hash':'b'*64}
    a={'fence':fence,'receipt':receipt,'communication':communication,'queue_item':'synthetic/item.json'}
    first=good('sms.receipt.persist',a,'executor')['data'];second=good('sms.receipt.persist',a,'executor')['data'];assert first==second
    assert read('communication',cid)['record']['receipt_id']==rid
   good('work.complete',f.result_arguments(claimed['data']),'executor')
   assert read('work_occurrence',w)['record']['state']=='succeeded'
  report['passes'].append({'pass':n,'scope_notification_receipt':'PASS','provider_effects':0})
  print(json.dumps(report['passes'][-1]),flush=True)
 report['status']='PASS'
finally:
 if running:native([pg/'pg_ctl.exe','-D',root/'data','-m','fast','-w','stop'])
 (root/'report.json').write_text(json.dumps(report,indent=2))
 print('Receipt: '+str(root/'report.json'))
