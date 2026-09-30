"""Owner-authorized second Resident profile; no changes to Toast enrollment."""
import argparse,hashlib,json,secrets,subprocess,sys,time
from pathlib import Path
from uuid import uuid4
from datetime import datetime,timezone
r=Path('C:/ECOS/ecos-2x');sys.dont_write_bytecode=True
sys.path[:0]=[str(r),str(r/'src'),str(r/'scripts')]
from resident2x_acceptance import hosted_admin,secure_directory
from migrations import inventory,plan
from runtime.resident2x.executor import save
from psycopg import sql

def main():
 parser=argparse.ArgumentParser();parser.add_argument('--expected-head',required=True);a=parser.parse_args()
 g=[r'C:\Program Files\Git\cmd\git.exe','-C',str(r)]
 def git(*args):return subprocess.check_output(g+list(args),stderr=subprocess.PIPE)
 assert git('rev-parse','HEAD').decode().strip()==a.expected_head and not git('status','--porcelain').strip()
 state=Path('D:/ECOS/Node/runtime/resident2x/state/gmail-home01')
 assert not state.exists(),'Existing Gmail enrollment requires reconciliation; no duplicate created'
 connect,database=hosted_admin()
 with connect() as db:
  assert db.execute("select maximum_instances from ecos_meta.executor_policy where surface='RESIDENT_DETERMINISTIC_PROVIDER'").fetchone()==(1,)
  assert db.execute("select count(*) from ecos.executor where name='resident_ada_2x_home01_gmail'").fetchone()==(0,)
  toast=db.execute("select i.id,i.principal_id,i.executor_id from ecos.executor_instance i join ecos_meta.principal_domain d on d.principal_id=i.principal_id join ecos.executor e on e.id=i.executor_id where d.domain='toast.acquisition' and d.execution_mode='production' and e.enabled").fetchall()
  assert len(toast)==1
  history=[dict(zip(('version','name','sha256'),x)) for x in db.execute('select version,name,sha256 from ecos_meta.schema_migration order by version')]
  pending=plan(inventory(r/'db/migrations'),history)
  assert [x['version'] for x in pending] in ([32],[])
 secure_directory(state)
 release=state.parents[1]/'releases'/('gmail-'+a.expected_head)
 secure_directory(release)
 manifest={}
 for name in filter(None,git('ls-files','-z','runtime','src','scripts','requirements.lock','requirements-resident.lock','requirements-phase1.lock').decode().split('\0')):
  data=git('show',a.expected_head+':'+name);p=release/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data);manifest[name]=hashlib.sha256(data).hexdigest()
 save(release/'installed-manifest.json',{'head':a.expected_head,'files':manifest,'installed_at':datetime.now(timezone.utc).isoformat()})
 principal,instance,executor,correlation,boot=[str(uuid4()) for _ in range(5)]
 role='resident2x_'+uuid4().hex[:16];password=secrets.token_urlsafe(48)
 caps={'ecos.2x.execute':1,'provider.gmail':1,'db.governed_operations':1}
 operations=['executor.register','executor.heartbeat','executor.stop','work.next','work.package','work.renew','work.complete','work.fail','work.defer','work.release','gmail.dispatch.begin','gmail.dispatch.finish','provider.result.record','recovery.sweep']
 config={'identity':'RESIDENT_ADA_2X_HOME01','principal_id':principal,'instance_id':instance,'executor_id':executor,'correlation_id':correlation,'authority':'DOMAIN_SCOPED_PRODUCTION','domain':'gmail.operations','execution_mode':'production','provider_effects_enabled':True,'state_directory':str(state),'database_password_file':str(state/'database.secret'),'database':{**database,'user':role+'.loonpojawpfagzobxoko'},'control_plane':'POSTGRESQL','work_sources':['POSTGRESQL'],'capabilities':caps,'heartbeat_seconds':5,'lease_seconds':120,'poll_seconds':5,'google_client_library':'D:/ECOS/Node/runtime/releases/slots/1.0.011','gmail_credential_file':str(r/'.local/gmail-enrollment/oauth.json')}
 (state/'database.secret').write_text(password,encoding='utf-8');save(state/'config.json',config)
 save(state/'enrollment.json',{'status':'PREPARED','head':a.expected_head,'release':str(release),'instance_id':instance,'principal_id':principal,'executor_id':executor,'role':role})
 with connect() as db:
  db.execute('select pg_advisory_xact_lock(684026,2)')
  assert db.execute("select maximum_instances from ecos_meta.executor_policy where surface='RESIDENT_DETERMINISTIC_PROVIDER' for update").fetchone()==(1,)
  for item in pending:
   db.execute(item['sql'],prepare=False);db.execute('insert into ecos_meta.schema_migration(version,name,sha256) values(%s,%s,%s)',(item['version'],item['name'],item['sha256']))
  db.execute("insert into ecos_meta.domain_authority(domain,owner,epoch,evidence) values('gmail.operations','2X',1,'Owner approved Gmail functional cutover and exactly one additional Gmail-only Resident profile')")
  db.execute(sql.SQL('create role {} login password {} nosuperuser nocreatedb nocreaterole noreplication nobypassrls inherit').format(sql.Identifier(role),sql.Literal(password)))
  db.execute(sql.SQL('grant executor,operations_api,provider_adapter to {}').format(sql.Identifier(role)))
  db.execute("insert into ecos.executor(id,name,surface,enabled) values(%s,'resident_ada_2x_home01_gmail','RESIDENT_DETERMINISTIC_PROVIDER',true)",(executor,))
  db.execute("insert into ecos.executor_instance(id,executor_id,boot_id,availability,principal_id) values(%s,%s,%s,'available',%s)",(instance,executor,boot,principal))
  db.execute('insert into ecos_meta.principal_binding values(%s,%s,%s,true)',(role,principal,instance))
  db.execute("insert into ecos_meta.principal_domain(principal_id,domain,execution_mode,authority_epoch,executor_generation) values(%s,'gmail.operations','production',1,'2X')",(principal,))
  for op in operations:db.execute('insert into ecos_meta.principal_operation values(%s,%s)',(principal,op))
  for cap in caps:
   row=db.execute("insert into ecos.executor_capability(executor_instance_id,capability_name,capability_version,attested_by,expires_at) values(%s,%s,1,%s,clock_timestamp()+interval '24 hours') returning id",(instance,cap,principal)).fetchone()
   db.execute('insert into ecos_meta.capability_renewal_policy(capability_id,attested_by,evidence_hash,lease_seconds,renew_before_seconds,enabled,authorization_reference) values(%s,%s,%s,86400,43200,true,%s)',(row[0],principal,manifest['runtime/resident2x/executor.py'],'Owner approval: exactly one additional Gmail-only Resident profile using existing heartbeat renewal'))
  db.execute("update ecos_meta.executor_policy set maximum_instances=2,source='Owner approved exactly one additional Gmail-only Resident profile; maximum 2',record_version=record_version+1,effective_at=clock_timestamp() where surface='RESIDENT_DETERMINISTIC_PROVIDER' and maximum_instances=1")
  assert db.execute('select rolsuper,rolcreatedb,rolcreaterole,rolreplication,rolbypassrls from pg_roles where rolname=%s',(role,)).fetchone()==(False,)*5
 save(state/'enrollment.json',{'status':'ENROLLED','head':a.expected_head,'release':str(release),'instance_id':instance,'principal_id':principal,'executor_id':executor,'role':role})
 with (state/'launch.stdout.log').open('ab') as out,(state/'launch.stderr.log').open('ab') as err:
  child=subprocess.Popen([str(r/'.venv/Scripts/python.exe'),'-B',str(release/'scripts/resident2x.py'),'--config',str(state/'config.json')],cwd=release,stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
 save(state/'launch.json',{'pid':child.pid,'release':str(release)})
 for _ in range(15):
  if child.poll() is not None:raise RuntimeError('Gmail Resident exited; private logs preserved')
  if (state/'heartbeat.json').exists():break
  time.sleep(1)
 else:raise RuntimeError('Heartbeat pending; do not start another instance')
 with connect() as db:
  assert db.execute("select evidence_hash from ecos.executor_presence where executor_instance_id=%s and status='available'",(instance,)).fetchone()==(manifest['runtime/resident2x/executor.py'],)
  assert db.execute('select exists(select 1 from ecos.heartbeat where executor_instance_id=%s and valid_until>clock_timestamp())',(instance,)).fetchone()==(True,)
  assert db.execute('select count(*) from ecos_meta.object_grant where principal_id=%s',(principal,)).fetchone()==(0,)
 result={'GmailResidentRegistration':'PASS','GmailResidentHeartbeat':'PASS','ResidentInstanceLimit':2,'GmailCapabilities':sorted(caps),'PrivilegedRoleFlags':False,'ObjectGrants':0,'ToastModified':False,'OnlineModified':False,'StartupInstallation':'ADMIN_REQUIRED','Release':str(release),'Config':str(state/'config.json')}
 save(state/'enrollment-verification.json',result);print(json.dumps(result))

if __name__=='__main__':
 try:main()
 except Exception as exc:
  print(json.dumps({'status':'FAILED_OR_PENDING_RECONCILIATION','error_type':type(exc).__name__}));raise SystemExit(1)
