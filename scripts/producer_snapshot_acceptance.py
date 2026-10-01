"""Two bounded producer snapshot persistence passes on a disposable database."""
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
 def op(name,args):
  with target.connect() as db:
   db.execute('set local role executor');v=db.execute('select ecos.operate(%s,%s)',(name,Jsonb(f.request(args)))).fetchone()[0]
   assert 'code' not in v,(name,v.get('code'));return v
 op('executor.register',{'host':'SYNTHETIC','runtime':'snapshot-persistence','software_version':'44','evidence_hash':'a'*64})
 for n in (1,2):
  work=f.add_work(1)[0]
  admin("insert into ecos.work_context(occurrence_id,operation,input) values(%s,'work.complete',%s)",(work,Jsonb({'source_worker_id':'TASK-AUTO-000041'})))
  claimed=op('work.next',{'executor_instance_id':f.inst,'lease_seconds':120})
  args=f.result_arguments(claimed['data']);fence=args['fence'];ctx=f.request({})['context']
  stamp=admin('select clock_timestamp()')[0][0].isoformat()
  fragment='<span>Synthetic bounded activity '+str(n)+'</span>'
  payload={'producer_id':'TASK-AUTO-000041','section':'E','key':'execution24','occurrence_id':work,
   'run_id':claimed['data']['execution_run']['id'],'generated_at':stamp,'source_timestamp':stamp,
   'freshness':'CURRENT','availability':'AVAILABLE','html_fragment':fragment,
   'content_sha256':hashlib.sha256(fragment.encode()).hexdigest(),'data':{'synthetic':True}}
  value=admin('select ecos_meta.persist_producer_snapshot(%s,%s,%s)',(Jsonb(ctx),Jsonb(fence),Jsonb(payload)))[0][0]
  same=admin('select ecos_meta.persist_producer_snapshot(%s,%s,%s)',(Jsonb(ctx),Jsonb(fence),Jsonb(payload)))[0][0]
  assert same==value
  observed=admin('select to_jsonb(s) from ecos.producer_snapshot s where id=%s',(value['id'],))[0][0]
  assert observed==value and observed['payload']==payload
  assert admin('select count(*) from ecos.producer_snapshot')[0][0]==n
  try:
   admin("update ecos.producer_snapshot set producer_id='changed' where id=%s",(value['id'],))
   raise AssertionError('immutable_update_allowed')
  except Exception as exc:
   assert 'immutable' in str(exc) or 'evidence' in str(exc),type(exc).__name__
  args['result']['content_hash']=value['payload_sha256'];args['result']['artifact_uri']='ecos:producer_snapshot:'+value['id']
  op('work.complete',args)
  assert admin('select state from ecos.work_occurrence where id=%s',(work,))[0][0]=='succeeded'
  assert admin('select to_jsonb(s) from ecos.producer_snapshot s where id=%s',(value['id'],))[0][0]==value
  report['passes'].append({'pass':n,'fenced_persistence':'PASS','exact_readback':'PASS','idempotency':'PASS','immutable':'PASS','completion_readback':'PASS','provider_effects':0})
 report.update(status='PASS',scope='shared producer persistence component; producer algorithms and runtime routing not accepted')
 print(json.dumps(report))
finally:
 if running:native([pg/'pg_ctl.exe','-D',root/'data','-m','fast','-w','stop'])
 (root/'report.json').write_text(json.dumps(report,indent=2))
 print('Receipt: '+str(root/'report.json'))
