"""Enroll the explicitly authorized SMS-only Online profile. Never output secrets."""
import sys,json,secrets,hashlib,subprocess,urllib.request,urllib.error
from pathlib import Path
from uuid import uuid4
from urllib.parse import quote
r=Path(__file__).resolve().parents[1];sys.path[:0]=[str(r),str(r/'src'),str(r/'scripts')]
from resident2x_acceptance import hosted_admin,secure_directory
from psycopg import sql
state=r/'.local/sms2x-enrollment'
assert not state.exists(),'Existing enrollment requires readback; do not duplicate'
secure_directory(state)
connect,database=hosted_admin()
old={line.split('=',1)[0]:line.split('=',1)[1] for line in (r/'.local/online2x-enrollment/server-secrets.env').read_text().splitlines() if '=' in line}
assert old.get('ECOS_ONLINE_OAUTH_SUBJECT')
node=Path('C:/Users/info/.cache/codex-runtimes/codex-primary-runtime/dependencies/node')
cli=[str(node/'bin/node.exe'),str(node/'node_modules/pnpm/bin/pnpm.cjs'),'dlx','supabase']
def cli_call(args):
 p=subprocess.run(cli+args,cwd=r,capture_output=True,text=True,timeout=120,creationflags=subprocess.CREATE_NO_WINDOW)
 if p.returncode:raise RuntimeError('Supabase management command failed; output suppressed')
 return p.stdout
cli_call(['projects','api-keys','--help'])
keys=json.loads(cli_call(['projects','api-keys','--project-ref','loonpojawpfagzobxoko','--reveal','--output','json']))
key=next(x['api_key'] for x in keys if x.get('name')=='service_role')
base='https://loonpojawpfagzobxoko.supabase.co/auth/v1/admin/oauth/clients'
def call(method,url,data=None):
 req=urllib.request.Request(url,data=json.dumps(data).encode() if data is not None else None,method=method,headers={'apikey':key,'Authorization':'Bearer '+key,'Content-Type':'application/json'})
 try:
  with urllib.request.urlopen(req,timeout=30) as response:return json.load(response)
 except urllib.error.HTTPError as e:raise RuntimeError('OAuth management HTTP '+str(e.code)) from None
listed=call('GET',base);clients=listed.get('clients',[]) if isinstance(listed,dict) else listed
assert not any(x.get('client_name')=='ECOS Online Ada 2.x SMS' for x in clients),'Existing OAuth client requires reconciliation'
client=call('POST',base,{'client_name':'ECOS Online Ada 2.x SMS','client_type':'public','redirect_uris':['https://gardnerdarrell1010-collab.github.io/ecos-2x/oauth/consent/'],'grant_types':['authorization_code','refresh_token'],'response_types':['code'],'token_endpoint_auth_method':'none'})
(state/'oauth-client.json').write_text(json.dumps(client))
client_id=client.get('client_id') or client.get('id');assert client_id
principal,instance,executor,boot=[str(uuid4()) for _ in range(4)]
role='online2x_sms_'+uuid4().hex[:12];password=secrets.token_urlsafe(48)
ops=['executor.register','executor.heartbeat','work.next','work.package','work.renew','work.complete','work.fail','work.defer','work.release','semantic.proposal.submit','sms.continuation.complete','task.transition']
caps=['ecos.2x.execute','semantic.interpret','db.governed_operations']
folder=r/'supabase/functions/online-ada-2x-sms'
evidence=hashlib.sha256(b''.join(p.read_bytes() for p in sorted(folder.iterdir()) if p.is_file())).hexdigest()
meta=dict(identity='ONLINE_ADA_2X_SMS',principal_id=principal,instance_id=instance,executor_id=executor,boot_id=boot,role=role,domain='sms.operations',oauth_client_id=client_id,operations=ops,capabilities=caps,evidence_hash=evidence,status='PREPARED')
(state/'enrollment.json').write_text(json.dumps(meta,indent=2));(state/'database.secret').write_text(password)
with connect() as db:
 assert db.execute('select max(version) from ecos_meta.schema_migration').fetchone()==(35,)
 assert not db.execute("select exists(select 1 from ecos.executor where name='online_ada_2x_sms')").fetchone()[0]
 assert not db.execute("select exists(select 1 from ecos_meta.domain_authority where domain='sms.operations')").fetchone()[0]
 db.execute("insert into ecos_meta.domain_authority(domain,owner,epoch,evidence) values('sms.operations','2X',1,'Explicit owner approval: ONLINE_ADA_2X_SMS, isolated semantic continuation only; no provider sending')")
 db.execute(sql.SQL('create role {} login password {} nosuperuser nocreatedb nocreaterole noreplication nobypassrls inherit').format(sql.Identifier(role),sql.Literal(password)))
 db.execute(sql.SQL('grant executor,operations_api to {}').format(sql.Identifier(role)))
 db.execute("insert into ecos.executor(id,name,surface,enabled) values(%s,'online_ada_2x_sms','ONLINE_SEMANTIC',true)",(executor,))
 db.execute("insert into ecos.executor_instance(id,executor_id,boot_id,availability,principal_id) values(%s,%s,%s,'available',%s)",(instance,executor,boot,principal))
 db.execute('insert into ecos_meta.principal_binding values(%s,%s,%s,true)',(role,principal,instance))
 db.execute("insert into ecos_meta.principal_domain(principal_id,domain,execution_mode,authority_epoch,executor_generation) values(%s,'sms.operations','production',1,'2X')",(principal,))
 for op in ops:db.execute('insert into ecos_meta.principal_operation values(%s,%s)',(principal,op))
 for cap in caps:
  cid=db.execute("insert into ecos.executor_capability(executor_instance_id,capability_name,capability_version,attested_by,expires_at) values(%s,%s,1,%s,clock_timestamp()+interval '24 hours') returning id",(instance,cap,principal)).fetchone()[0]
  db.execute('insert into ecos_meta.capability_renewal_policy(capability_id,attested_by,evidence_hash,lease_seconds,renew_before_seconds,enabled,authorization_reference) values(%s,%s,%s,86400,43200,true,%s)',(cid,principal,evidence,'Explicit SMS profile authorization; existing bounded renewal model'))
meta['status']='ENROLLED_NO_PRODUCTION_OBJECT_GRANTS';(state/'enrollment.json').write_text(json.dumps(meta,indent=2))
url='postgresql://'+role+'.loonpojawpfagzobxoko:'+quote(password,safe='')+'@'+database['host']+':5432/postgres'
env={'ECOS_SMS_PRINCIPAL_ID':principal,'ECOS_SMS_INSTANCE_ID':instance,'ECOS_SMS_OAUTH_CLIENT_ID':client_id,'ECOS_SMS_OAUTH_SUBJECT':old['ECOS_ONLINE_OAUTH_SUBJECT'],'ECOS_SMS_DATABASE_URL':url}
if old.get('ECOS_ONLINE_DATABASE_CA'):env['ECOS_SMS_DATABASE_CA']=old['ECOS_ONLINE_DATABASE_CA']
(state/'server-secrets.env').write_text(''.join(k+'='+v+'\n' for k,v in env.items()))
cli_call(['secrets','set','--help']);cli_call(['functions','deploy','--help'])
cli_call(['secrets','set','--env-file',str(state/'server-secrets.env'),'--project-ref','loonpojawpfagzobxoko'])
cli_call(['functions','deploy','online-ada-2x-sms','--project-ref','loonpojawpfagzobxoko','--no-verify-jwt','--use-api'])
meta['status']='DEPLOYED_AWAITING_OAUTH_CONNECTION';(state/'enrollment.json').write_text(json.dumps(meta,indent=2))
with connect() as db:
 assert db.execute('select rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls from pg_roles where rolname=%s',(role,)).fetchone()==(False,)*5
 assert db.execute('select count(*) from ecos_meta.object_grant where principal_id=%s',(principal,)).fetchone()==(0,)
 assert set(x[0] for x in db.execute('select operation from ecos_meta.principal_operation where principal_id=%s',(principal,)))==set(ops)
print(json.dumps({'Profile':meta['identity'],'Domain':'sms.operations','Enrollment':'PASS','HostedDeployment':'PASS','OAuthClientID':client_id,'ObjectGrants':0,'SecretValuesOutput':False,'SMSDefinitionEnabled':False}))
