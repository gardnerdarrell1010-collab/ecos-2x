"""Apply the tested operations and bind only the eight existing mapped definitions.

Online activation and the later installed-Resident activation are separate phases.
No provider is invoked here. Historical backlog rows are not changed or enqueued.
"""
import argparse, hashlib, json, subprocess, sys
from pathlib import Path
from uuid import uuid4
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'src'),str(ROOT/'scripts')]
from resident2x_acceptance import hosted_admin,secure_directory
from migrations import inventory,plan
from psycopg.types.json import Jsonb

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--expected-head',required=True)
 p.add_argument('--phase',choices=['online','resident'],required=True)
 p.add_argument('--calendar-account',required=True)
 p.add_argument('--verify-only',action='store_true',help='Validate the complete transaction, then roll it back without activation.')
 a=p.parse_args()
 git=[r'C:\Program Files\Git\cmd\git.exe','-c','safe.directory='+ROOT.as_posix(),'-C',str(ROOT)]
 assert subprocess.check_output(git+['rev-parse','HEAD']).decode().strip()==a.expected_head
 assert not subprocess.check_output(git+['status','--porcelain']).strip()
 online=json.loads((ROOT/'.local/online2x-enrollment/enrollment.json').read_text())
 resident_path=Path('D:/ECOS/Node/runtime/resident2x/state/gmail-home01/config.json')
 resident=json.loads(resident_path.read_text())
 definitions=json.loads((ROOT/'runtime/operational_work.json').read_text())['functions']
 receipt=ROOT/'.local'/('operational-activation-'+uuid4().hex);secure_directory(receipt)
 def save(name,value):(receipt/name).write_text(json.dumps(value,default=str,indent=2)+'\n')
 connect,_=hosted_admin()
 online_ops=['runtime.scope.read','runtime.evidence.read','notification.enqueue','core.review.commit',
  'continuity.snapshot','continuity.checkpoint.commit','calendar.evidence.record','sms.continuation.complete']
 resident_ops=['runtime.scope.read','sms.receipt.persist','sms.dispatch.begin','sms.dispatch.readback']
 selected=['A015','A016','A018','A024','A031','A036'] if a.phase=='online' else ['A027','A028']
 with connect() as db:
  db.execute('select pg_advisory_xact_lock(684026,2)')
  history=[dict(zip(('version','name','sha256'),row)) for row in db.execute('select version,name,sha256 from ecos_meta.schema_migration order by version')]
  pending=plan(inventory(ROOT/'db/migrations'),history)
  assert [m['version'] for m in pending] in ([37,38,39,40],[])
  names=[v['definition'] for v in definitions.values()]
  before=db.execute('select to_jsonb(d) from ecos.work_definition d where name=any(%s) order by name',(names,)).fetchall()
  assert len(before)==8
  save('preimage.json',{'history':history,'definitions':before,
   'bindings':db.execute('select to_jsonb(p) from ecos_meta.principal_domain p where principal_id=any(%s::uuid[])',( [online['principal_id'],resident['principal_id']],)).fetchall(),
   'operations':db.execute('select * from ecos_meta.principal_operation where principal_id=any(%s::uuid[])',([online['principal_id'],resident['principal_id']],)).fetchall()})
  for identity,name in [(online,'online_ada_2x'),(resident,'resident_ada_2x_home01_gmail')]:
   assert db.execute('select e.name,e.enabled from ecos.executor_instance i join ecos.executor e on e.id=i.executor_id where i.id=%s and i.principal_id=%s',(identity['instance_id'],identity['principal_id'])).fetchone()==(name,True)
  for m in pending:
   db.execute(m['sql'],prepare=False)
   db.execute('insert into ecos_meta.schema_migration(version,name,sha256) values(%s,%s,%s)',(m['version'],m['name'],m['sha256']))
  for identity,operations in [(online,online_ops),(resident,resident_ops)]:
   for operation in operations:db.execute('insert into ecos_meta.principal_operation values(%s,%s) on conflict do nothing',(identity['principal_id'],operation))
  if a.phase=='online':
   # Only migrated operational core tasks; never conversion tasks, fixtures or provider-owned tasks.
   db.execute("""insert into ecos_meta.object_grant select %s,'task',t.id from ecos.task t
    where t.lifecycle_state in ('open','waiting') and (t.business_id like 'TASK-CONV-%%' or t.business_id like 'TASK-IMPORT-%%' or t.business_id like 'TASK-GMAIL-%%')
    and not exists(select 1 from ecos_meta.object_domain d where d.record_type='task' and d.record_id=t.id)
    on conflict do nothing""",(online['principal_id'],))
   for kind in ('task_schedule','task_dependency','task_assignment'):
    db.execute(f"insert into ecos_meta.object_grant select %s,%s,c.id from ecos.{kind} c join ecos_meta.object_grant g on g.record_type='task' and g.record_id=c.task_id and g.principal_id=%s on conflict do nothing",(online['principal_id'],kind,online['principal_id']))
   db.execute("insert into ecos_meta.object_grant select %s,'project',t.project_id from ecos.task t join ecos_meta.object_grant g on g.record_type='task' and g.record_id=t.id and g.principal_id=%s where t.project_id is not null on conflict do nothing",(online['principal_id'],online['principal_id']))
   db.execute("insert into ecos_meta.object_grant select %s,'party',ta.party_id from ecos.task_assignment ta join ecos_meta.object_grant g on g.record_type='task' and g.record_id=ta.task_id and g.principal_id=%s on conflict do nothing",(online['principal_id'],online['principal_id']))
   db.execute("insert into ecos_meta.object_grant select %s,'notification',n.id from ecos.notification n join ecos_meta.object_grant g on g.record_type=n.subject_type and g.record_id=n.subject_id and g.principal_id=%s on conflict do nothing",(online['principal_id'],online['principal_id']))
   db.execute("insert into ecos_meta.object_grant select %s,'delivery',d.id from ecos.delivery d join ecos_meta.object_grant g on g.record_type='notification' and g.record_id=d.notification_id and g.principal_id=%s on conflict do nothing",(online['principal_id'],online['principal_id']))
   db.execute("insert into ecos_meta.object_grant select %s,'party',d.recipient_party_id from ecos.delivery d join ecos_meta.object_grant g on g.record_type='delivery' and g.record_id=d.id and g.principal_id=%s on conflict do nothing",(online['principal_id'],online['principal_id']))
   # Reuse the current enrollment's heartbeat evidence and 24h/12h renewal policy.
   evidence=db.execute('select evidence_hash from ecos.executor_presence where executor_instance_id=%s',(online['instance_id'],)).fetchone()[0]
   cap=db.execute("select id,attested_by from ecos.executor_capability where executor_instance_id=%s and capability_name='provider.calendar' and capability_version=1",(online['instance_id'],)).fetchone()
   if cap is None:
    cap=db.execute("insert into ecos.executor_capability(executor_instance_id,capability_name,capability_version,attested_by,expires_at) values(%s,'provider.calendar',1,%s,clock_timestamp()+interval '24 hours') returning id,attested_by",(online['instance_id'],online['principal_id'])).fetchone()
   db.execute('insert into ecos_meta.capability_renewal_policy values(%s,%s,%s,86400,43200,true,%s,clock_timestamp()) on conflict(capability_id) do nothing',(cap[0],cap[1],evidence,'Owner-approved A036; existing authenticated Calendar connector read verified; no Calendar/provider mutations'))
  else:
   assert resident.get('operational_sms') and {'http.authenticated.request','provider.twilio'}<=set(resident['capabilities'])
   evidence=hashlib.sha256((ROOT/'runtime/resident2x/executor.py').read_bytes()).hexdigest()
   assert db.execute('select evidence_hash from ecos.executor_presence where executor_instance_id=%s',(resident['instance_id'],)).fetchone()==(evidence,), 'Installed Resident release not verified'
   for cap_name in resident['capabilities']:
    cap=db.execute('select id,attested_by from ecos.executor_capability where executor_instance_id=%s and capability_name=%s and capability_version=1',(resident['instance_id'],cap_name)).fetchone()
    if cap is None:cap=db.execute("insert into ecos.executor_capability(executor_instance_id,capability_name,capability_version,attested_by,expires_at) values(%s,%s,1,%s,clock_timestamp()+interval '24 hours') returning id,attested_by",(resident['instance_id'],cap_name,resident['principal_id'])).fetchone()
    db.execute('insert into ecos_meta.capability_renewal_policy values(%s,%s,%s,86400,43200,true,%s,clock_timestamp()) on conflict(capability_id) do update set evidence_hash=excluded.evidence_hash,enabled=true,authorization_reference=excluded.authorization_reference',(cap[0],cap[1],evidence,'Owner-approved existing Resident A027/A028 operation binding; exact installed release'))
  results=[]
  for short in selected:
   spec=definitions[short]
   stage=db.execute('select s.id,s.work_definition_id,s.execution_surface from ecos.work_stage_definition s join ecos.work_definition d on d.id=s.work_definition_id where d.name=%s and s.stage_key=%s',(spec['definition'],spec['stage'])).fetchone()
   assert stage and stage[2]==spec['surface']
   identity=resident if short in ('A027','A028') else online
   existing=db.execute('select id from ecos.work_occurrence where stage_definition_id=%s order by created_at limit 1',(stage[0],)).fetchone()
   oid=None
   if spec['period_seconds'] and existing is None:
    oid=str(uuid4());inp={'instructions':spec['instructions'],'schedule_mode':'completion_relative','delivery_principal_id':resident['principal_id']}
    if short=='A027':
     sms_stage=db.execute("select id from ecos.work_stage_definition where stage_key='sms_inbound_process'").fetchone()[0]
     inp['sms_processing_target']={'principal_id':online['principal_id'],'stage_id':str(sms_stage),
      'instructions':definitions['A031']['instructions'],'delivery_principal_id':resident['principal_id']}
    if short=='A036':inp['calendar_scope']={'calendar_id':'primary','account_scope':a.calendar_account}
    db.execute("insert into ecos.work_occurrence(id,work_definition_id,stage_definition_id,fulfillment_id,task_id,state,occurrence_key,due_at) values(%s,%s,%s,%s,null,'pending',%s,clock_timestamp())",(oid,stage[1],stage[0],str(uuid4()),'operational:'+short+':initial'))
    db.execute("insert into ecos.work_context(occurrence_id,operation,input) values(%s,'work.complete',%s)",(oid,Jsonb(inp)))
    db.execute('insert into ecos.work_priority(occurrence_id,recurrence_period_seconds) values(%s,%s)',(oid,spec['period_seconds']))
    db.execute("insert into ecos_meta.object_grant values(%s,'work_occurrence',%s)",(identity['principal_id'],oid))
    if spec['domain']:db.execute("insert into ecos_meta.object_domain values('work_occurrence',%s,%s)",(oid,spec['domain']))
   elif existing:oid=str(existing[0])
   db.execute('update ecos.work_definition set enabled=true,record_version=record_version+1 where id=%s and not enabled',(stage[1],))
   results.append({'function':short,'occurrence_id':oid,'period_seconds':spec['period_seconds'],'domain':spec['domain'],'production_definition_enabled':True})
  save('committed-bindings.json',results)
  if a.verify_only:
   for item in results:
    if item['occurrence_id']:
     identity=resident if item['function'] in ('A027','A028') else online
     db.execute('select ecos_meta.selection(%s,%s,clock_timestamp())',(item['occurrence_id'],identity['instance_id'])).fetchone()
   db.rollback()
   print(json.dumps({'Phase':a.phase,'TransactionValidation':'PASS','RolledBack':True,'ProviderCalls':0,'Receipt':str(receipt)}))
   return
 with connect() as db:
  readback=[]
  for item in results:
   identity=resident if item['function'] in ('A027','A028') else online
   selection=db.execute('select ecos_meta.selection(%s,%s,clock_timestamp())',(item['occurrence_id'],identity['instance_id'])).fetchone()[0] if item['occurrence_id'] else None
   readback.append({**item,'selection':selection})
  assert db.execute("select count(*) from ecos_meta.domain_authority where domain='ecos.core'").fetchone()==(0,)
  save('readback.json',readback)
 print(json.dumps({'Phase':a.phase,'BindingsReadbackVerified':True,'CoreDomainRequired':False,'ProviderCalls':0,'Receipt':str(receipt)}))

if __name__=='__main__':
 try:main()
 except Exception as exc:
  print(json.dumps({'Status':'FAILED_OR_PENDING_RECONCILIATION','ErrorType':type(exc).__name__}))
  raise SystemExit(1)
