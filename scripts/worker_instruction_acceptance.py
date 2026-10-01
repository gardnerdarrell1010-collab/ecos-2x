"""One preserved instruction round trip on a private disposable database; no execution."""
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
 from resident2x_acceptance import hosted_admin
 from phase2_executor_client import GovernedClient
 connect,_=hosted_admin()
 with connect() as live:
  off=live.execute("select (select count(*) from ecos.executor where enabled),(select count(*) from ecos.work_definition where enabled),(select count(*) from ecos.work_claim where state='active' and expires_at>clock_timestamp())").fetchone()
  assert off==(0,0,0)
  rows=live.execute("select b.column_names,r.raw_value->'values',b.id,r.source_locator from ecos_migration.raw_source_row r join ecos_migration.raw_migration_batch b on b.id=r.batch_id where b.source_family='Task Loop' order by b.extracted_at desc").fetchall()
 latest={}
 for cols,values,batch,locator in rows:
  if not values:continue
  row=dict(zip(cols,values));key=row.get('Task Loop ID','')
  if key.startswith('TASK-AUTO-') and key not in latest:latest[key]=(row,batch,locator)
 row,batch,locator=max(latest.values(),key=lambda x:len(x[0].get('Instructions','').encode()))
 text=row['Instructions'];digest=hashlib.sha256(text.encode('utf-8')).hexdigest()
 def admin(q,a=()):
  with target.connect() as db:
   cur=db.execute(q,a);return cur.fetchall() if cur.description else []
 def op(operation,args,role='operations_api'):
  with target.connect() as db:
   db.execute('set local role '+role)
   return db.execute('select ecos.operate(%s,%s)',(operation,Jsonb(f.request(args)))).fetchone()[0]
 def good(operation,args,role='operations_api'):
  res=op(operation,args,role);assert 'code' not in res,(operation,res.get('code'));return res
 for kind,identity in [('work_definition',f.definition),('work_stage_definition',f.stage)]:
  admin('insert into ecos_meta.object_grant values(%s,%s,%s)',(f.p,kind,identity))
 args={'work_definition_id':f.definition,'stage_definition_id':f.stage,'expected_version':0,'instruction_text':text,'source_reference':f'ecos_migration:{batch}:{locator}:Instructions','content_sha256':digest}
 published=good('work.instruction.publish',args)['data'];assert published['instruction_version']==1
 assert op('work.instruction.publish',args,'executor').get('code')=='forbidden'
 w=f.add_work(1)[0]
 admin("insert into ecos.work_context(occurrence_id,operation,input) values(%s,'work.complete','{}')",(w,))
 good('executor.register',{'host':'SYNTHETIC','runtime':'instruction-contract','software_version':'41','evidence_hash':'a'*64},'executor')
 claimed=good('work.next',{'executor_instance_id':f.inst,'lease_seconds':120},'executor')
 assert claimed.get('status')=='CLAIMED'
 fence=f.result_arguments(claimed['data'])['fence']
 package=claimed['data']['work_package']
 assert package['functional_instructions']['instruction_text'].encode()==text.encode()
 assert package['functional_instructions']['content_sha256']==digest
 # The existing Resident client consumes the package as JSON without filtering fields.
 def resident_connect():
  db=target.connect();db.autocommit=True;db.execute('set role executor');return db
 client=GovernedClient(resident_connect)
 try:readback=client.operate('work.package',f.request({'fence':fence}))['data']
 finally:client.close()
 assert readback['functional_instructions']==package['functional_instructions']
 # A new version is append-only and cannot replace the active claim's instructions.
 args['expected_version']=1
 second=good('work.instruction.publish',args)['data'];assert second['instruction_version']==2
 assert good('work.package',{'fence':fence},'executor')['data']['functional_instructions']['id']==published['id']
 assert admin('select count(*) from ecos.work_instruction_version where stage_definition_id=%s',(f.stage,))[0][0]==2
 try:
  admin('update ecos.work_instruction_version set instruction_text=instruction_text where id=%s',(published['id'],))
  raise AssertionError('immutable_guard_missing')
 except __import__('psycopg').Error:pass
 good('work.release',{'fence':fence,'reason':'instruction_readback_only'},'executor')
 report.update(status='PASS',source_worker=row['Task Loop ID'],source_bytes=len(text.encode()),source_sha256=digest,lossless_roundtrip='PASS',versioning='PASS',claim_version_pin='PASS',executor_publication_denied='PASS',resident_client_readback='PASS',production_off=True,provider_effects=0)
 print(json.dumps(report),flush=True)
finally:
 if running:native([pg/'pg_ctl.exe','-D',root/'data','-m','fast','-w','stop'])
 (root/'report.json').write_text(json.dumps(report,indent=2))
 print('Receipt: '+str(root/'report.json'))
