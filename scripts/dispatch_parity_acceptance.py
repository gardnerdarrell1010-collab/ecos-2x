"""Two bounded preserved dispatch scoring passes on a disposable database."""
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
   assert 'code' not in v,(name,v);return v
 from decimal import Decimal
 from datetime import timedelta
 at=datetime.now(timezone.utc)
 op('executor.register',{'host':'SYNTHETIC','runtime':'dispatch-parity','software_version':'47','evidence_hash':'a'*64})
 for n in (1,2):
  ids=f.add_work(3)
  for index,work in enumerate(ids):
   admin("insert into ecos.work_context(occurrence_id,operation,input) values(%s,'work.complete','{}')",(work,))
   admin("update ecos.work_occurrence set due_at=%s,record_version=record_version+1 where id=%s",(at-timedelta(seconds=600),work))
   admin("insert into ecos.work_priority(occurrence_id,business_impact,recurrence_period_seconds,dispatch_importance,dependency_impact,task_loop_id) values(%s,0,600,%s,1,%s)",(work,index+1,'SYNTHETIC-'+str(index)))
   assert admin('select ecos_meta.refresh_dispatch_score(%s,%s)',(work,at))[0][0]
  # Normalized .3/.2 weights, recurrence-relative pressure and exact decimal readback.
  expected=[]
  for importance in (1,2,3):
   base=(Decimal(importance)*Decimal('.3')+Decimal('.2'))/Decimal('.5')
   expected.append((base+(Decimal('15.999')-base)/Decimal(11)).quantize(Decimal('.001')))
  actual=[admin('select dispatch_score::numeric from ecos.work_priority where occurrence_id=%s',(w,))[0][0] for w in ids]
  assert actual==expected
  before=admin('select dispatch_score_at from ecos.work_priority where occurrence_id=%s',(ids[0],))[0][0]
  assert not admin('select ecos_meta.refresh_dispatch_score(%s,%s)',(ids[0],at))[0][0]
  assert admin('select dispatch_score_at from ecos.work_priority where occurrence_id=%s',(ids[0],))[0][0]==before
  # RUN NOW floats immediately, without a population recalculation.
  admin("update ecos.work_occurrence set ready_override_at=%s,record_version=record_version+1 where id=%s",(at,ids[0]))
  claimed=op('work.next',{'executor_instance_id':f.inst,'lease_seconds':120})
  assert claimed['data']['claim']['occurrence_id']==ids[0]
  args=f.result_arguments(claimed['data'])
  package=op('work.package',{'fence':args['fence']})['data'];assert package['occurrence']['id']==ids[0]
  assert admin('select dispatch_score::numeric from ecos.work_priority where occurrence_id=%s',(ids[0],))[0][0]==16
  op('work.complete',args)
  assert admin('select state from ecos.work_occurrence where id=%s',(ids[0],))[0][0]=='succeeded'
  assert admin('select dispatch_score::numeric from ecos.work_priority where occurrence_id=%s',(ids[0],))[0][0]<16
  for work in (ids[2],ids[1]):
   claimed=op('work.next',{'executor_instance_id':f.inst,'lease_seconds':120})
   assert claimed['data']['claim']['occurrence_id']==work
   op('work.complete',f.result_arguments(claimed['data']))
  report['passes'].append({'pass':n,'formula':'PASS','anti_churn':'PASS','run_now':'PASS','ranked_claim_package_completion':'PASS','provider_effects':0})
 report.update(status='PASS',scope='dispatch formula, persisted ranking and changed-occurrence updates; existing work.next PT10M refresh hookup')
 print(json.dumps(report))

finally:
 if running:native([pg/'pg_ctl.exe','-D',root/'data','-m','fast','-w','stop'])
 (root/'report.json').write_text(json.dumps(report,indent=2))
 print('Receipt: '+str(root/'report.json'))

