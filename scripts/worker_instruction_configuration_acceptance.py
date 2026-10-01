"""Bounded administrative instruction configuration acceptance on a disposable database."""
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
 from configure_worker_instructions import plan,configure,readback,POSTGRESQL_ACCESS_BINDING
 f=Fixture(target);f.seed()
 def admin(q,a=()):
  with target.connect() as db:
   cur=db.execute(q,a);return cur.fetchall() if cur.description else []
 admin("update ecos.executor set enabled=false,record_version=record_version+1")
 admin("update ecos.work_definition set enabled=false,record_version=record_version+1")
 text='Complete synthetic instructions: keep CRLF\r\nUnicode: \u03a9; preserve  spaces.\n'
 def seed_source(text):
  batch=uid()
  admin("insert into ecos_migration.raw_migration_batch(id,source_system,extracted_at,source_registry_version,artifact_uri,sha256,row_count,column_names,source_family) values(%s,'synthetic',clock_timestamp(),'synthetic','synthetic:instructions',%s,1,%s,'Task Loop')",(batch,'a'*64,Jsonb(['Task Loop ID','Instructions'])))
  admin('insert into ecos_migration.raw_source_row values(%s,%s,%s,%s)',(batch,'row:1',Jsonb({'values':['TASK-AUTO-SYNTHETIC',text]}),'b'*64))
 seed_source(text)
 mapping=[{'source_worker_id':'TASK-AUTO-SYNTHETIC','work_definition_id':f.definition,'stage_definition_id':f.stage}]
 for version in (1,2):
  if version==2:
   text+='Version 2 complete content.\n'
   seed_source(text)
  with target.connect() as db:document=plan(db,mapping,postgresql_access=(version==2))
  with target.connect() as db:assert configure(db,document)['configured']==1
  with target.connect() as db:assert readback(db,document)['verified']==1
  with target.connect() as db:assert configure(db,document)['replayed']==1
  assert admin('select count(*) from ecos.work_instruction_version')[0][0]==version
 assert not admin("select 1 from ecos_meta.operation_contract where name='work.instruction.publish'")
 assert not admin("select 1 from ecos_meta.principal_operation where operation='work.instruction.publish'")
 # Only disposable fixture execution control is opened to retrieve a package; no handler runs.
 admin('update ecos.executor set enabled=true,record_version=record_version+1 where id=%s',(f.ex,))
 admin('update ecos.work_definition set enabled=true,record_version=record_version+1 where id=%s',(f.definition,))
 w=f.add_work(1)[0];admin("insert into ecos.work_context(occurrence_id,operation,input) values(%s,'work.complete','{}')",(w,))
 def op(name,args):
  with target.connect() as db:
   db.execute('set local role executor')
   result=db.execute('select ecos.operate(%s,%s)',(name,Jsonb(f.request(args)))).fetchone()[0]
   assert 'code' not in result,(name,result.get('code'));return result
 op('executor.register',{'host':'SYNTHETIC','runtime':'config-acceptance','software_version':'42','evidence_hash':'a'*64})
 claimed=op('work.next',{'executor_instance_id':f.inst,'lease_seconds':120})
 instruction=claimed['data']['work_package']['functional_instructions']
 assert instruction['instruction_version']==2 and instruction['instruction_text'].encode()==(POSTGRESQL_ACCESS_BINDING+text).encode()
 fence=f.result_arguments(claimed['data'])['fence']
 assert op('work.package',{'fence':fence})['data']['functional_instructions']==instruction
 op('work.release',{'fence':fence,'reason':'configuration_readback_only'})
 report.update(status='PASS',configuration_atomic_readback='PASS',versioning='PASS',replay='PASS',work_package='PASS',publish_removed=True,provider_effects=0)
 print(json.dumps(report))
finally:
 if running:native([pg/'pg_ctl.exe','-D',root/'data','-m','fast','-w','stop'])
 (root/'report.json').write_text(json.dumps(report,indent=2))
 print('Receipt: '+str(root/'report.json'))
