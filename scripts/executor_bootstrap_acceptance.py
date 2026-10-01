"""Two authoritative bootstrap scenarios on a disposable database."""
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
 from contextlib import contextmanager
 from types import SimpleNamespace
 from runtime.resident2x.executor import Resident
 f=Fixture(target);f.seed()
 def admin(q,a=()):
  with target.connect() as db:
   cur=db.execute(q,a);return cur.fetchall() if cur.description else []
 @contextmanager
 def bound():
  with target.connect() as db:
   db.execute('set local role executor');yield db
 before=admin('select ecos_meta.content_hash(jsonb_agg(to_jsonb(c) order by name,version)) from ecos.capability c')[0][0]
 for n in (1,2):
  checked=[]
  for surface,identity in [('RESIDENT_DETERMINISTIC_PROVIDER','RESIDENT_ADA_2X_HOME01'),('ONLINE_SEMANTIC','ONLINE_ADA_2X'),('INTERACTIVE_ADA','INTERACTIVE_ADA')]:
   admin('update ecos.executor set surface=%s,enabled=%s,record_version=record_version+1 where id=%s',(surface,n==1,f.ex))
   admin("update ecos.executor_capability set expires_at=clock_timestamp()+make_interval(secs=>%s),record_version=record_version+1 where executor_instance_id=%s",(3600 if n==1 else -3600,f.inst))
   with bound() as db: package=db.execute('select ecos.bootstrap_package()').fetchone()[0]
   ctx=package['executor_context'];assert ctx['identity']==identity and ctx['executor_instance_id']==f.inst
   assert ctx['enabled']==(n==1) and ctx['capabilities'][0]['valid']==(n==1)
   assert package['operational_authority']=='POSTGRESQL_ECOS_2X' and package['operation_bindings']
   agent=SimpleNamespace(connect=bound,expected_identity=identity,config={'instance_id':f.inst,'principal_id':f.p,'capabilities':{'invented.local.value':99}})
   Resident.refresh_bootstrap(agent)
   assert 'invented.local.value' not in agent.config['capabilities']
   assert ('db.governed_operations' in agent.config['capabilities'])==(n==1)
   if n==2:
    try:Resident.refresh_bootstrap(agent,require_enabled=True)
    except ValueError as exc:assert str(exc)=='executor_not_operational'
    else:raise AssertionError('disabled_executor_allowed')
   checked.append(identity)
  report['passes'].append({'pass':n,'identities':checked,'authoritative_capability_validity':'PASS','local_capability_ignored':'PASS','disabled_state_readback':'PASS','provider_effects':0})
 after=admin('select ecos_meta.content_hash(jsonb_agg(to_jsonb(c) order by name,version)) from ecos.capability c')[0][0];assert after==before
 report.update(status='PASS',capability_catalog_modified=False,scope='bootstrap SQL and runtime consumption; deployed launchers not accepted')
 print(json.dumps(report))
finally:
 if running:native([pg/'pg_ctl.exe','-D',root/'data','-m','fast','-w','stop'])
 (root/'report.json').write_text(json.dumps(report,indent=2))
 print('Receipt: '+str(root/'report.json'))
