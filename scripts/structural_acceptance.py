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
 admin("update ecos.executor set surface='ONLINE_SEMANTIC',record_version=record_version+1 where id=%s",(f.ex,))
 for cap in ('ecos.2x.execute','semantic.interpret'):
  admin("insert into ecos.executor_capability(executor_instance_id,capability_name,capability_version,attested_by,expires_at) values(%s,%s,1,%s,clock_timestamp()+interval '1 hour')",(f.inst,cap,f.p))
 admin("update ecos.work_definition set enabled=true,record_version=record_version+1 where name='sms_continuation'")
 good('executor.register',{'host':'SYNTHETIC','runtime':'structural-acceptance','software_version':'candidate35','evidence_hash':'a'*64},'executor')
 for n in (1,2):
  ref=source();party=uid();grant('party',party)
  args=dict(id=party,expected_version=0,business_id='SYNTHETIC-ORG-'+party,name='Synthetic organization',party_kind='organization',provenance=[ref])
  good('party.put',args);assert read('party',party)['record']['party_kind']=='organization'
  args.update(expected_version=1,name='Synthetic organization revised');good('party.put',args)
  assert read('party',party)['record']['record_version']==2
  rel=uid();grant('relationship',rel)
  args=dict(id=rel,expected_version=0,source_system='synthetic',source_relationship_id=uid(),source_type='party',source_id=party,target_type='task',target_id=f.task,relationship_type='affiliation',status='active',effective_from=None,effective_to=None,provenance=[ref])
  good('relationship.put',args);assert read('relationship',rel)['record']['source_id']==party
  args.update(expected_version=1,status='inactive');good('relationship.put',args)
  assert read('relationship',rel)['record']['status']=='inactive'
  aid=uid();grant('approval_request',aid);subject=read('party',party)
  good('approval.request',dict(id=aid,subject_type='party',subject_id=party,subject_hash=subject['content_hash'],expiration_mode='never',expires_at=None,provenance=[ref]))
  assert read('approval_request',aid)['record']['expiration_mode']=='never'
  good('approval.decide',dict(approval_request_id=aid,expected_version=1,decision='approved',subject_hash=subject['content_hash'],reason_code='synthetic_acceptance'))
  assert read('approval_request',aid)['record']['state']=='approved'
  assert admin('select count(*) from ecos.approval_decision where approval_request_id=%s',(aid,))[0][0]==1
  message=uid();artifacts=[]
  for part in ('part-1','part-2'):
   art=uid();grant('artifact',art)
   good('artifact.register',dict(id=art,business_id='SYNTHETIC-ART-'+art,provider='gmail',provider_object_id=message,uri='synthetic:'+part,content_hash='a'*64,attachment_id=part,provenance=[ref]))
   assert read('artifact',art)['record']['attachment_id']==part;artifacts.append(art)
  assert len(set(artifacts))==2
  # SMS continuation is a local synthetic semantic client; no Twilio network call.
  receipt,comm=uid(),uid()
  admin("insert into ecos.provider_receipt(id,provider,account_scope,provider_event_id,dedupe_key,provider_object_id,provider_occurred_at,received_at,raw_artifact_uri,raw_content_hash,signature_verified,correlation_id) values(%s,'twilio','synthetic',%s,%s,%s,clock_timestamp(),clock_timestamp(),'synthetic:sms',%s,true,%s)",(receipt,comm,comm,comm,'b'*64,f.correlation))
  admin("insert into ecos.communication(id,receipt_id,channel,provider_thread_id,direction,body_artifact_uri,body_hash) values(%s,%s,'sms',%s,'inbound','synthetic:sms',%s)",(comm,receipt,comm,'b'*64));grant('communication',comm)
  queued=good('sms.continuation.enqueue',dict(communication_id=comm,source_version=1,task_id=f.task))['data']
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
  result=f.result_arguments(claimed['data']);result['result']['result_schema_id']='ecos.sms.continuation.result.v1'
  good('work.complete',result,'executor')
  assert read('work_occurrence',queued['occurrence_id'])['record']['state']=='succeeded'
  assert admin('select count(*) from ecos.provider_command')[0][0]==0
  report['passes'].append({'pass':n,'organization':'PASS','relationship':'PASS','approval':'PASS','artifact':'PASS','sms':'PASS','independent_readback':'PASS'})
  print(json.dumps(report['passes'][-1]),flush=True)
 report['status']='PASS'
finally:
 if running:native([pg/'pg_ctl.exe','-D',root/'data','-m','fast','-w','stop'])
 (root/'report.json').write_text(json.dumps(report,indent=2))
 print('Receipt: '+str(root/'report.json'))
