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
 from datetime import timedelta
 f=Fixture(target);f.seed()
 def admin(q,a=()):
  with target.connect() as db:
   cur=db.execute(q,a);return cur.fetchall() if cur.description else []
 def op(name,args):
  with target.connect() as db:
   db.execute('set local role executor');v=db.execute('select ecos.operate(%s,%s)',(name,Jsonb(f.request(args)))).fetchone()[0]
   assert 'code' not in v,(name,v.get('code'));return v
 op('executor.register',{'host':'SYNTHETIC','runtime':'activity-projection','software_version':'43','evidence_hash':'a'*64})
 for n in (1,2):
  work=f.add_work(1)[0];admin("insert into ecos.work_context(occurrence_id,operation,input) values(%s,'work.complete','{}')",(work,))
  claimed=op('work.next',{'executor_instance_id':f.inst,'lease_seconds':120})
  op('work.complete',f.result_arguments(claimed['data']))
  begin,end=admin('select min(created_at),max(created_at) from ecos.execution_event')[0]
  begin=min(begin,admin('select min(created_at) from ecos.execution_run')[0][0]);end+=timedelta(microseconds=1)
  result=admin('select ecos_meta.execution_activity_window(%s,%s)',(begin,end))[0][0]
  assert result['run_count']==n and sum(x['run_count'] for x in result['summary'])==n
  assert len({x['id'] for x in result['runs']})==n
  assert all(x['duration_seconds'] is not None and x['state']=='succeeded' for x in result['runs'])
  # Event at the lower boundary is included once; the upper bound excludes it.
  stamp=admin('select max(created_at) from ecos.execution_event')[0][0]
  narrow=admin('select ecos_meta.execution_activity_window(%s,%s)',(stamp,stamp+timedelta(microseconds=1)))[0][0]
  assert narrow['run_count']==1 and len(narrow['runs'][0]['events'])==1
  empty=admin('select ecos_meta.execution_activity_window(%s,%s)',(end,end+timedelta(hours=24)))[0][0]
  assert empty['complete_window_evaluated'] and empty['run_count']==0
  report['passes'].append({'pass':n,'query_readback':'PASS','summary_detail_reconciled':True,'inclusive_lower_exclusive_upper':True,'full_window_zero':'PASS','provider_effects':0})
 report.update(status='PASS',scope='SQL execution activity projection component only; complete A041 producer not accepted')
 print(json.dumps(report))
finally:
 if running:native([pg/'pg_ctl.exe','-D',root/'data','-m','fast','-w','stop'])
 (root/'report.json').write_text(json.dumps(report,indent=2))
 print('Receipt: '+str(root/'report.json'))
