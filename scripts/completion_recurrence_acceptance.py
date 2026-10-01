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
 import time
 op('executor.register',{'host':'SYNTHETIC','runtime':'recurrence-parity','software_version':'48','evidence_hash':'a'*64})
 for n in (1,2):
  admin('update ecos.work_stage_definition set stage_key=%s,record_version=record_version+1 where id=%s',('arbitrary_recurrence_'+str(n),f.stage))
  work=f.add_work(1)[0]
  admin('update ecos.work_occurrence set task_id=null,record_version=record_version+1 where id=%s',(work,))
  admin("insert into ecos.work_context(occurrence_id,operation,input) values(%s,'work.complete',%s)",(work,Jsonb({"schedule_mode":"completion_relative"})))
  admin("insert into ecos.work_priority(occurrence_id,business_impact,recurrence_period_seconds,dispatch_importance,dependency_impact,task_loop_id) values(%s,3,1,3,4,%s)",(work,'SYNTHETIC-'+str(n)))
  admin('select ecos_meta.refresh_dispatch_score(%s,clock_timestamp())',(work,))
  first=op('work.next',{'executor_instance_id':f.inst,'lease_seconds':120})
  assert first['data']['claim']['occurrence_id']==work
  op('work.complete',f.result_arguments(first['data']))
  time.sleep(1.1)
  second=op('work.next',{'executor_instance_id':f.inst,'lease_seconds':120})
  child=second['data']['claim']['occurrence_id'];assert child!=work
  assert admin('select p.dispatch_importance,p.dependency_impact,o.ready_override_at,o.fulfillment_id=(select fulfillment_id from ecos.work_occurrence where id=%s) from ecos.work_occurrence o join ecos.work_priority p on p.occurrence_id=o.id where o.id=%s',(work,child))[0]==(3,4,None,True)
  assert admin('select count(*) from ecos.work_occurrence where fulfillment_id=(select fulfillment_id from ecos.work_occurrence where id=%s)',(work,))[0][0]==2
  op('work.complete',f.result_arguments(second['data']))
  admin("update ecos.work_context set input='{}',record_version=record_version+1 where occurrence_id in (%s,%s)",(work,child))
  report['passes'].append({'pass':n,'arbitrary_stage_recurrence':'PASS','same_fulfillment':'PASS','one_successor':'PASS','priority_inherited':'PASS','claim_package_completion':'PASS','provider_effects':0})
 report.update(status='PASS',scope='existing completion-relative materializer, no new scheduler or executor')
 print(json.dumps(report))

finally:
 if running:native([pg/'pg_ctl.exe','-D',root/'data','-m','fast','-w','stop'])
 (root/'report.json').write_text(json.dumps(report,indent=2))
 print('Receipt: '+str(root/'report.json'))
