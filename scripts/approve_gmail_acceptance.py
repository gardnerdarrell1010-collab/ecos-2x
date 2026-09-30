"""Record the owner's bounded recipientless draft approval via approval.decide."""
import sys,json
from pathlib import Path
from uuid import uuid4
r=Path('C:/ECOS/ecos-2x');sys.dont_write_bytecode=True;sys.path[:0]=[str(r),str(r/'src'),str(r/'scripts')]
from resident2x_acceptance import hosted_admin
from ecos.core.contracts import content_hash
from psycopg import sql
from psycopg.types.json import Jsonb
fixture_set=sys.argv[2] if len(sys.argv)>2 else 'acceptance'
assert fixture_set in ('acceptance','functional-v2')
s=r/'.local/gmail-enrollment'/fixture_set
fixtures=json.loads((s/'fixtures.json').read_text());n=int(sys.argv[1]);assert n in(1,2)
item=fixtures['passes'][n-1];connect,_=hosted_admin()
with connect() as db:
 rows=db.execute("select c.id,c.request_hash,c.command_type,c.outcome,a.id,a.record_version,a.state,d.request,o.state from ecos.gmail_draft_request d join ecos.provider_command c on c.id=d.command_id join ecos.approval_request a on a.id=c.approval_request_id join ecos.communication_processing p on p.id=d.processing_id join ecos.work_occurrence o on o.id=p.occurrence_id where o.task_id=%s",(item['task_id'],)).fetchall()
 assert len(rows)==1,'Exactly one semantic draft command required'
 command,h,kind,outcome,approval,version,state,request,semantic=rows[0]
 assert kind=='draft.create' and outcome=='pending' and state=='pending' and semantic=='succeeded'
 assert request['to']==[] and request['source_message_id']==item['message_id'] and request['thread_id']==item['thread_id']
 assert content_hash(request)==h and 'functional acceptance' in request['body'].lower()
 assert db.execute('select count(*) from ecos.provider_attempt where provider_command_id=%s',(command,)).fetchone()==(0,)
 path=s/'approver.json'
 if path.exists():identity=json.loads(path.read_text())
 else:
  identity={'role':'gmail_acceptance_approver_'+uuid4().hex[:12],'principal_id':str(uuid4()),'authorization':'Owner explicitly authorized exactly two safe recipientless unsent Gmail draft E2E occurrences. No send approval.'}
  path.write_text(json.dumps(identity,indent=2))
 role=identity['role'];principal=identity['principal_id']
 if not db.execute('select exists(select 1 from pg_roles where rolname=%s)',(role,)).fetchone()[0]:
  db.execute(sql.SQL('create role {} nologin nosuperuser nocreatedb nocreaterole noreplication nobypassrls inherit').format(sql.Identifier(role)))
  db.execute(sql.SQL('grant operations_api to {}').format(sql.Identifier(role)))
  db.execute('insert into ecos_meta.principal_binding values(%s,%s,null,true)',(role,principal))
  db.execute("insert into ecos_meta.principal_domain(principal_id,domain,execution_mode,authority_epoch,executor_generation) values(%s,'gmail.operations','production',1,'2X')",(principal,))
  db.execute("insert into ecos_meta.principal_operation values(%s,'approval.decide')",(principal,))
 for record_type,id_ in [('approval_request',approval),('provider_command',command)]:
  db.execute('insert into ecos_meta.object_grant values(%s,%s,%s) on conflict do nothing',(principal,record_type,id_))
 assert db.execute('select rolcanlogin,rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls from pg_roles where rolname=%s',(role,)).fetchone()==(False,)*6
 assert db.execute("select has_table_privilege(%s,'ecos.provider_command','UPDATE')",(role,)).fetchone()==(False,)
 rid=str(uuid4());wire={'schema_version':'1.0.0','context':{'principal_id':principal,'executor_instance_id':None,'correlation_id':rid,'causation_id':None,'idempotency_key':'gmail-acceptance-approval:'+str(command)},'arguments':{'approval_request_id':str(approval),'expected_version':version,'decision':'approved','subject_hash':h,'reason_code':'owner_authorized_recipientless_acceptance'}}
 (s/('approval-request-'+str(n)+'.json')).write_text(json.dumps(wire,indent=2))
 admin_role=db.execute('select current_user').fetchone()[0]
 db.execute(sql.SQL('grant {} to {}').format(sql.Identifier(role),sql.Identifier(admin_role)))
 db.execute(sql.SQL('set local role {}').format(sql.Identifier(role)))
 response=db.execute("select ecos.operate('approval.decide',%s)",(Jsonb(wire),)).fetchone()[0]
 assert response.get('status')=='committed',response.get('code','approval_not_committed')
 db.execute('reset role')
 db.execute(sql.SQL('revoke {} from {}').format(sql.Identifier(role),sql.Identifier(admin_role)))
 assert db.execute("select pg_has_role(%s,%s,'USAGE'),pg_has_role(%s,%s,'SET')",(admin_role,role,admin_role,role)).fetchone()==(False,False)
 assert db.execute('select state from ecos.approval_request where id=%s',(approval,)).fetchone()==('approved',)
 assert db.execute('select count(*) from ecos.approval_decision where approval_request_id=%s and actor_id=%s and decision=%s',(approval,principal,'approved')).fetchone()==(1,)
 (s/('approval-result-'+str(n)+'.json')).write_text(json.dumps(response,indent=2))
print(json.dumps({'Pass':n,'GovernedOwnerApproval':'PASS','CommandId':str(command),'RecipientCount':0,'SendAuthorized':False,'AdditionalExecutorInstances':0}))
