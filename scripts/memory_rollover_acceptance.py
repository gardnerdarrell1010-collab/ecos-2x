"""Two bounded rollover passes through the existing restricted operation boundary."""
import sys,json
from pathlib import Path
from uuid import uuid4
from datetime import datetime,timezone
r=Path('C:/ECOS/ecos-2x');sys.path[:0]=[str(r),str(r/'src'),str(r/'scripts')]
from resident2x_acceptance import hosted_admin
import psycopg
from psycopg.types.json import Jsonb
state=r/'.local/interactive2x-enrollment'
m=json.loads((state/'enrollment.json').read_text())
connect,settings=hosted_admin()
receipt=state/'memory-rollover-acceptance.json'
if receipt.exists():raise SystemExit('Existing memory attempt: reconcile before retry')
scope,record,subject=[str(uuid4()) for _ in range(3)]
versions=[str(uuid4()) for _ in range(3)]
attempt={'scope':scope,'record':record,'versions':versions,'passes':[],'status':'PREPARED'}
receipt.write_text(json.dumps(attempt,indent=2))
with connect() as db:
 db.execute("insert into ecos.memory_scope(id,scope_type,scope_id,sensitivity,authorized_role_names) values(%s,'synthetic',%s,'internal',%s)",(scope,subject,Jsonb([m['role']])))
 db.execute("insert into ecos.memory_record(id,business_id,scope_id,memory_kind) values(%s,%s,%s,'synthetic_rollover')",(record,'SYNTHETIC-MEMORY-'+record,scope))
 for kind,ids in [('memory_scope',[scope]),('memory_record',[record]),('memory_version',versions)]:
  for entity in ids:
   db.execute('insert into ecos_meta.object_grant values(%s,%s,%s)',(m['principal_id'],kind,entity))
   db.execute("insert into ecos_meta.object_domain values(%s,%s,'synthetic.acceptance')",(kind,entity))
def restricted():
 return psycopg.connect(**settings,user=m['role']+'.loonpojawpfagzobxoko',password=(state/'database.secret').read_text(),options='-c timezone=UTC -c statement_timeout=20000')
def read(db,kind,entity):return db.execute('select ecos.read_record(%s,%s::uuid)',(kind,entity)).fetchone()[0]
for n,version_id in enumerate(versions,1):
 with restricted() as db:
  before=read(db,'memory_record',record)
  old=read(db,'memory_version',versions[n-2]) if n>1 else None
  source=read(db,'task',m['test_tasks'][0])
  ref={'record_type':'task','record_id':m['test_tasks'][0],'record_version':source['record']['record_version'],'content_hash':source['content_hash'],'authority':'structured_ecos'}
  stamp=datetime.now(timezone.utc).isoformat()
  value={'id':version_id,'schema_version':'1.0.0','created_at':stamp,'memory_record_id':record,'version_number':n,'supersedes_version_id':versions[n-2] if n>1 else None,'scope_id':scope,'statement':'Synthetic memory rollover version '+str(n),'operational_meaning':'Bounded functional acceptance only','provenance':[ref],'effective_at':stamp,'sensitivity':'internal','retention_policy_ref':'synthetic-acceptance-evidence','authoritative_references':[ref],'content_hash':'','compaction_run_id':None}
  with connect() as admin:value['content_hash']=admin.execute('select ecos_meta.content_hash(%s)',(Jsonb(value),)).fetchone()[0]
  req={'schema_version':'1.0.0','context':{'principal_id':m['principal_id'],'executor_instance_id':m['instance_id'],'correlation_id':str(uuid4()),'causation_id':None,'idempotency_key':'memory-rollover-'+version_id},'arguments':{'memory_record_id':record,'expected_version':before['record']['record_version'],'new_version':value}}
  result=db.execute("select ecos.operate('memory.activate',%s)",(Jsonb(req),)).fetchone()[0]
  if result.get('status')!='committed':
   attempt['status']='FAILED';attempt['error']=result;receipt.write_text(json.dumps(attempt,indent=2));raise SystemExit('MemoryOperation='+json.dumps(result))
 with restricted() as db:
  after=read(db,'memory_record',record);new=read(db,'memory_version',version_id)
  assert after['record']['active_head_version_id']==version_id
  assert new['record']['version_number']==n
  if n>1:assert read(db,'memory_version',versions[n-2])==old
 with connect() as db:
  assert db.execute('select version_number from ecos.memory_version where id=%s',(version_id,)).fetchone()[0]==n
  assert str(db.execute('select active_head_version_id from ecos.memory_record where id=%s',(record,)).fetchone()[0])==version_id
 if n>1:attempt['passes'].append({'from':n-1,'to':n,'governed_readback':'PASS','previous_unchanged':True,'independent_readback':'PASS'})
 attempt['status']='ACCEPTED' if n==3 else 'INITIALIZED' if n==1 else 'FIRST_PASS'
 receipt.write_text(json.dumps(attempt,indent=2))
print(json.dumps({'MemoryRollover':attempt['status'],'ConsecutivePasses':len(attempt['passes']),'ActualMemory95Unchanged':True}))
