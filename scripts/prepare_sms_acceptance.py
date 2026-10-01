"""Prepare exactly two isolated synthetic SMS occurrences; no held records touched."""
import sys,json,hashlib
from pathlib import Path
from uuid import uuid4
from urllib.parse import quote
r=Path(__file__).resolve().parents[1];sys.path[:0]=[str(r),str(r/'src'),str(r/'scripts')]
from resident2x_acceptance import hosted_admin
from psycopg.types.json import Jsonb
s=r/'.local/sms2x-enrollment';m=json.loads((s/'enrollment.json').read_text())
assert not (s/'fixtures.json').exists(),'Existing fixtures require reconciliation'
connect,_=hosted_admin();passes=[]
with connect() as db:
 stage=db.execute("select s.id,d.id,d.enabled from ecos.work_stage_definition s join ecos.work_definition d on d.id=s.work_definition_id where d.name='sms_continuation' and s.stage_key='sms_continuation'").fetchone()
 assert stage and stage[2] is False
 baseline={'communications':db.execute("select count(*),md5(string_agg(to_jsonb(c)::text,'' order by id)) from ecos.communication c where channel='sms'").fetchone(),'gmail_ledger':db.execute("select business_id,record_version,md5(description) from ecos.task where business_id=any(%s) order by business_id",(['CONVERT-2X-A001','CONVERT-2X-A035','CONVERT-2X-A010'],)).fetchall()}
 for n in (1,2):
  task,receipt,comm,processing,occ,fulfillment,corr=[str(uuid4()) for _ in range(7)]
  text='Synthetic SMS acceptance '+str(n)+': please mark the related synthetic task waiting for owner review. Do not send a message.'
  digest=hashlib.sha256(text.encode()).hexdigest();uri='data:text/plain;charset=utf-8,'+quote(text,safe='')
  db.execute("insert into ecos.task(id,business_id,title,lifecycle_state,wait_reason,description) values(%s,%s,%s,'open','none',%s)",(task,'SYNTHETIC-SMS-'+task,'Synthetic SMS functional acceptance '+str(n),text))
  db.execute("insert into ecos.provider_receipt(id,provider,account_scope,provider_event_id,dedupe_key,provider_object_id,provider_occurred_at,received_at,raw_artifact_uri,raw_content_hash,signature_verified,correlation_id) values(%s,'twilio','synthetic-acceptance',%s,%s,%s,clock_timestamp(),clock_timestamp(),%s,%s,false,%s)",(receipt,'SYNTHETIC-'+comm,'SYNTHETIC-'+comm,'SYNTHETIC-'+comm,uri,digest,corr))
  db.execute("insert into ecos.communication(id,receipt_id,channel,provider_thread_id,direction,body_artifact_uri,body_hash) values(%s,%s,'sms',%s,'inbound',%s,%s)",(comm,receipt,'SYNTHETIC-'+comm,uri,digest))
  db.execute("insert into ecos.work_occurrence(id,work_definition_id,stage_definition_id,fulfillment_id,task_id,state,occurrence_key,due_at) values(%s,%s,%s,%s,%s,'ready',%s,clock_timestamp())",(occ,stage[1],stage[0],fulfillment,task,'SYNTHETIC-SMS-'+comm))
  db.execute("insert into ecos.communication_processing(id,communication_id,source_version,state,occurrence_id) values(%s,%s,1,'ready',%s)",(processing,comm,occ))
  source=db.execute("select jsonb_build_object('record_type','communication','record_id',id,'record_version',record_version,'content_hash',ecos_meta.content_hash(to_jsonb(c)),'authority','structured_ecos') from ecos.communication c where id=%s",(comm,)).fetchone()[0]
  db.execute("insert into ecos.work_context(occurrence_id,operation,source_references,input) values(%s,'sms.continuation.complete',%s,%s)",(occ,Jsonb([source]),Jsonb({'processing_id':processing,'communication_id':comm,'synthetic_acceptance':True,'pass':n})))
  for kind,id_ in [('task',task),('provider_receipt',receipt),('communication',comm),('communication_processing',processing),('work_occurrence',occ)]:
   db.execute("insert into ecos_meta.object_domain values(%s,%s,'sms.operations')",(kind,id_))
   db.execute('insert into ecos_meta.object_grant values(%s,%s,%s)',(m['principal_id'],kind,id_))
  passes.append(dict(pass_number=n,task_id=task,communication_id=comm,processing_id=processing,receipt_id=receipt,occurrence_id=occ,correlation_id=corr))
(s/'fixtures.json').write_text(json.dumps({'passes':passes,'baseline':baseline},default=str,indent=2))
print(json.dumps({'SyntheticOccurrencesPrepared':2,'SMSDefinitionEnabled':False,'HeldContinuationsTouched':0,'ProviderCalls':0}))
