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

 admin("update ecos.executor set surface='ONLINE_SEMANTIC',record_version=record_version+1 where id=%s",(f.ex,))
 good('executor.register',{'host':'SYNTHETIC','runtime':'core-cadence-acceptance','software_version':'candidate38','evidence_hash':'a'*64},'executor')
 for stage,period in [('calendar_sms_reminder',None)]:
  admin("update ecos.work_stage_definition set stage_key=%s,execution_surface='ONLINE_SEMANTIC',kind='semantic',record_version=record_version+1 where id=%s",(stage,f.stage))
  for n in (1,2):
   w=f.add_work(1)[0]
   admin("insert into ecos.work_context(occurrence_id,operation,input) values(%s,'work.complete',%s)",(w,Jsonb({'calendar_scope':{'account_scope':'synthetic','calendar_id':'synthetic'}})))
   claimed=good('work.next',{'executor_instance_id':f.inst,'lease_seconds':120},'executor')
   assert claimed['status']=='CLAIMED',claimed
   current=claimed['data']['claim']['occurrence_id']
   assert current==w

   fence=f.result_arguments(claimed['data'])['fence']
   assert good('work.package',{'fence':fence},'executor')['data']['occurrence']['id']==current
   assert not admin("select 1 from ecos_meta.object_domain where record_type='work_occurrence' and record_id=%s",(current,))
   scope=good('runtime.scope.read',{'fence':fence,'record_type':'task','after_id':None,'limit':100},'executor')['data']
   assert any(x['record']['id']==f.task for x in scope['records'])
   stamp=datetime.now(timezone.utc).isoformat()
   event={'id':'synthetic-'+str(n),'etag':'revision-'+str(n),'summary':'Synthetic reminder','updated':stamp,'start':{'dateTime':stamp}}
   evidence=good('calendar.evidence.record',{'fence':fence,'calendar_id':'synthetic','account_scope':'synthetic','observed_at':stamp,'event':event},'executor')['data']
   er=read('provider_receipt',evidence['id'])
   assert er['record']['provider_object_id']==event['id']
   event_ref={'record_type':'provider_receipt','record_id':evidence['id'],'record_version':1,'content_hash':er['content_hash'],'authority':'structured_ecos'}
   if stage!='incremental_continuity':
    ref=source();versions=[{k:ref[k] for k in ('record_type','record_id','record_version')}]
    ev={'source':ref,'assertion':'Synthetic core review from exact scoped source','verification':'verified'}
    state='waiting' if n==1 else 'open'
    item={'item_id':uid(),'depends_on_item_ids':[],'source_references':[ref],'expected_record_versions':versions,'proposed_operations':[{'operation':'task.transition','arguments':{'task_id':f.task,'expected_version':ref['record_version'],'target_state':state,'wait_reason':'owner' if n==1 else 'none','reason_code':'synthetic_core_review','evidence':[ev]}}],'evidence':[ev],'confidence_basis_points':10000,'unresolved_ambiguity':[]}
    proposal={'id':uid(),'proposal_type':'synthetic_core_review','schema_version':'1.0.0','created_at':datetime.now(timezone.utc).isoformat(),'correlation_id':f.correlation,'source_references':[ref],'expected_record_versions':versions,'items':[item]}
    proposal['source_references'].append(event_ref)
    proposal['items'][0]['source_references'].append(event_ref)
    proposal['content_hash']=admin('select ecos_meta.content_hash(%s)',(Jsonb(proposal),))[0][0]
    good('semantic.proposal.submit',{'fence':fence,'proposal':proposal},'executor')
    good('core.review.commit',{'fence':fence,'proposal_id':proposal['id']},'executor')
    assert read('task',f.task)['record']['lifecycle_state']==state
   stamp=datetime.now(timezone.utc).isoformat()
   if stage=='outstanding_request_monitor':
    rid,cid=uid(),uid()
    admin("insert into ecos.provider_receipt(id,provider,account_scope,provider_event_id,dedupe_key,provider_object_id,provider_occurred_at,received_at,raw_artifact_uri,raw_content_hash,signature_verified,correlation_id) values(%s,'gmail','synthetic',%s,%s,%s,clock_timestamp(),clock_timestamp(),'synthetic:gmail',%s,false,%s)",(rid,cid,cid,cid,'b'*64,f.correlation))
    admin("insert into ecos.communication(id,receipt_id,channel,provider_thread_id,direction,body_artifact_uri,body_hash) values(%s,%s,'email',%s,'inbound','synthetic:gmail',%s)",(cid,rid,cid,'b'*64))
    grant('communication',cid);grant('provider_receipt',rid)
    evidence=good('runtime.evidence.read',{'fence':fence,'communication_id':cid},'executor')['data']
    assert evidence['receipt']['provider_object_id']==cid and evidence['communication']['receipt_id']==rid
   party=uid();admin("insert into ecos.party(id,business_id,name) values(%s,%s,'Synthetic')",(party,'SYNTHETIC-'+party));grant('party',party)
   nid,did=uid(),uid()
   notification={'id':nid,'schema_version':'1.0.0','created_at':stamp,'record_version':1,'business_reason_code':'synthetic_review','subject_type':'task','subject_id':f.task,'content_artifact_uri':'synthetic:message','content_hash':'a'*64,'policy_version':1}
   delivery={'id':did,'schema_version':'1.0.0','created_at':stamp,'record_version':1,'notification_id':nid,'recipient_party_id':party,'channel':'sms','destination_reference':'synthetic:recipient','policy_key':stage+str(n),'state':'planned','approval_request_id':None,'provider_command_id':None}
   a={'fence':fence,'notification':notification,'delivery':delivery,'source_references':[source(),event_ref]}
   first=good('notification.enqueue',a,'executor')['data'];second=good('notification.enqueue',a,'executor')['data'];assert first==second
   assert read('delivery',did)['record']['state']=='planned'
   good('work.complete',f.result_arguments(claimed['data']),'executor')
   assert read('work_occurrence',current)['record']['state']=='succeeded'
   report['passes'].append({'stage':stage,'pass':n,'readback':'PASS','conditional_notification_dedup':'PASS','task_mutation':'PASS','provider_effects':0})
   print(json.dumps(report['passes'][-1]),flush=True)
  assert good('work.next',{'executor_instance_id':f.inst,'lease_seconds':120},'executor')['status']=='NO_ELIGIBLE_WORK'
  # Retire only this disposable fixture cadence before reusing its stage definition.
  admin('update ecos.work_priority set recurrence_period_seconds=null where occurrence_id in(select id from ecos.work_occurrence where stage_definition_id=%s)',(f.stage,))
 report['status']='PASS'
finally:
 if running:native([pg/'pg_ctl.exe','-D',root/'data','-m','fast','-w','stop'])
 (root/'report.json').write_text(json.dumps(report,indent=2))
 print('Receipt: '+str(root/'report.json'))
