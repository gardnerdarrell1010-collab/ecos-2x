"""Two internal Online transport-to-SQL SMS completions on a disposable database only."""
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
root=Path(tempfile.gettempdir())/('ecos-online-sms-'+uuid4().hex)
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
   request=f.request(args)
   if op=='sms.continuation.complete':
    node=Path('C:/Users/info/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe')
    module=(r/'supabase/functions/online-ada-2x/online_transport_core.mjs').as_uri()
    code="import {boundRequest} from '"+module+"';let s='';for await(const c of process.stdin)s+=c;const v=JSON.parse(s);process.stdout.write(JSON.stringify(boundRequest(v.operation,v.request,v.identity)));"
    result=subprocess.run([str(node),'--input-type=module','-e',code],input=json.dumps({'operation':op,'request':request,'identity':{'principal':f.p,'instance':f.inst}}),capture_output=True,text=True,check=True,creationflags=subprocess.CREATE_NO_WINDOW)
    request=json.loads(result.stdout)
   res=db.execute('select ecos.operate(%s,%s)',(op,Jsonb(request))).fetchone()[0]
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
 admin("update ecos.executor set surface='ONLINE_SEMANTIC',record_version=record_version+1 where id=%s",(f.ex,))
 for cap in ('ecos.2x.execute','semantic.interpret'):
  admin("insert into ecos.executor_capability(executor_instance_id,capability_name,capability_version,attested_by,expires_at) values(%s,%s,1,%s,clock_timestamp()+interval '1 hour')",(f.inst,cap,f.p))
 admin("update ecos.work_stage_definition set stage_key='sms_inbound_process',execution_surface='ONLINE_SEMANTIC',kind='semantic',record_version=record_version+1 where id=%s",(f.stage,))
 good('executor.register',{'host':'SYNTHETIC','runtime':'structural-acceptance','software_version':'candidate35','evidence_hash':'a'*64},'executor')
 for n in (1,2):
  # SMS continuation is a local synthetic semantic client; no Twilio network call.
  receipt,comm=uid(),uid()
  admin("insert into ecos.provider_receipt(id,provider,account_scope,provider_event_id,dedupe_key,provider_object_id,provider_occurred_at,received_at,raw_artifact_uri,raw_content_hash,signature_verified,correlation_id) values(%s,'twilio','synthetic',%s,%s,%s,clock_timestamp(),clock_timestamp(),'synthetic:sms',%s,true,%s)",(receipt,comm,comm,comm,'b'*64,f.correlation))
  admin("insert into ecos.communication(id,receipt_id,channel,provider_thread_id,direction,body_artifact_uri,body_hash) values(%s,%s,'sms',%s,'inbound','synthetic:sms',%s)",(comm,receipt,comm,'b'*64));grant('communication',comm)
  grant('provider_receipt',receipt)
  admin("insert into ecos_meta.object_domain values('communication',%s,'synthetic.acceptance')",(comm,))
  parent=f.add_work(1)[0]
  admin("update ecos.work_occurrence set state='cancelled',record_version=record_version+1 where id=%s",(parent,))
  admin("insert into ecos.work_context(occurrence_id,operation,input) values(%s,'work.complete',%s)",(parent,Jsonb({'sms_processing_target':{'principal_id':f.p,'stage_id':f.stage,'instructions':'Synthetic scoped continuation'}})))
  occurrence=str(admin('select ecos_meta.core_sms_handoff(%s,%s)',(parent,comm))[0][0])
  assert admin("select input->>'instructions' from ecos.work_context where occurrence_id=%s",(occurrence,))[0][0]=='Synthetic scoped continuation'
  assert str(admin('select ecos_meta.core_sms_handoff(%s,%s)',(parent,comm))[0][0])==occurrence
  processing=str(admin('select id from ecos.communication_processing where occurrence_id=%s',(occurrence,))[0][0])
  queued={'occurrence_id':occurrence,'processing_id':processing}
  assert read('communication_processing',queued['processing_id'])['record']['state']=='ready'
  claimed=good('work.next',{'executor_instance_id':f.inst,'lease_seconds':120},'executor')
  assert claimed['data']['claim']['occurrence_id']==queued['occurrence_id'],claimed
  fence={k:claimed['data']['claim']['id'] if k=='claim_id' else claimed['data']['claim'][k] for k in ('claim_id','occurrence_id','stage_definition_id','claim_version','fence_token','executor_instance_id')}
  ref=source();versions=[{k:ref[k] for k in ('record_type','record_id','record_version')}]
  cr=read('communication',comm)
  cref={'record_type':'communication','record_id':comm,'record_version':1,'content_hash':cr['content_hash'],'authority':'structured_ecos'}
  ev={'source':ref,'assertion':'Synthetic continuation state','verification':'verified'}
  target_state='waiting' if n==1 else 'open'
  item={'item_id':uid(),'depends_on_item_ids':[],'source_references':[ref],'expected_record_versions':versions,'proposed_operations':[{'operation':'task.transition','arguments':{'task_id':f.task,'expected_version':ref['record_version'],'target_state':target_state,'wait_reason':'owner' if n==1 else 'none','reason_code':'synthetic_continuation','evidence':[ev]}}],'evidence':[ev],'confidence_basis_points':10000,'unresolved_ambiguity':[]}
  proposal={'id':uid(),'proposal_type':'synthetic_continuation','schema_version':'1.0.0','created_at':datetime.now(timezone.utc).isoformat(),'correlation_id':f.correlation,'source_references':[ref],'expected_record_versions':versions,'items':[item]}
  proposal['source_references'].append(cref)
  proposal['content_hash']=admin('select ecos_meta.content_hash(%s)',(Jsonb(proposal),))[0][0]
  good('semantic.proposal.submit',{'fence':fence,'proposal':proposal},'executor')
  assert read('communication_processing',queued['processing_id'])['record']['state']=='ready'
  good('sms.continuation.complete',{'fence':fence,'proposal_id':proposal['id']},'executor')
  assert read('communication_processing',queued['processing_id'])['record']['state']=='succeeded'
  assert read('task',f.task)['record']['lifecycle_state']==target_state
  stamp=datetime.now(timezone.utc).isoformat()
  party=uid();admin("insert into ecos.party(id,business_id,name) values(%s,%s,'Synthetic')",(party,'SYNTHETIC-'+party));grant('party',party)
  nid,did=uid(),uid()
  notification={'id':nid,'schema_version':'1.0.0','created_at':stamp,'record_version':1,'business_reason_code':'synthetic_review','subject_type':'task','subject_id':f.task,'content_artifact_uri':'synthetic:message','content_hash':'a'*64,'policy_version':1}
  delivery={'id':did,'schema_version':'1.0.0','created_at':stamp,'record_version':1,'notification_id':nid,'recipient_party_id':party,'channel':'sms','destination_reference':'synthetic:recipient','policy_key':'synthetic-sms-'+str(n),'state':'planned','approval_request_id':None,'provider_command_id':None}
  a={'fence':fence,'notification':notification,'delivery':delivery,'source_references':[source()]}
  first=good('notification.enqueue',a,'executor')['data'];second=good('notification.enqueue',a,'executor')['data'];assert first==second
  assert read('delivery',did)['record']['state']=='planned'
  result=f.result_arguments(claimed['data']);result['result']['result_schema_id']='synthetic.result.v1'
  good('work.complete',result,'executor')
  assert read('work_occurrence',queued['occurrence_id'])['record']['state']=='succeeded'
  assert admin('select count(*) from ecos.provider_command')[0][0]==0
  report['passes'].append({'pass':n,'sms_handoff_semantic_notification_completion':'PASS','task_and_processing_readback':'PASS','provider_effects':0})
  print(json.dumps(report['passes'][-1]),flush=True)
 report['status']='PASS'
finally:
 if running:native([pg/'pg_ctl.exe','-D',root/'data','-m','fast','-w','stop'])
 (root/'report.json').write_text(json.dumps(report,indent=2))
 print('Receipt: '+str(root/'report.json'))
