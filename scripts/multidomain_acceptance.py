"""Two committed synthetic SQL paths per contract on a private disposable database."""
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
 def good(op,args,role='operations_api'):
  with target.connect() as db:
   db.execute('set local role '+role)
   res=db.execute('select ecos.operate(%s,%s)',(op,Jsonb(f.request(args)))).fetchone()[0]
   assert 'code' not in res,(op,res)
   return res
 def read(kind,identity):
  with target.connect() as db:
   db.execute('set local role operations_api')
   return db.execute('select ecos.read_record(%s,%s)',(kind,identity)).fetchone()[0]
 def grant(kind,identity):admin('insert into ecos_meta.object_grant values(%s,%s,%s)',(f.p,kind,identity))
 def source():
  rr=read('task',f.task)
  return {'record_type':'task','record_id':f.task,'record_version':rr['record']['record_version'],'content_hash':rr['content_hash'],'authority':'structured_ecos'}
 for cap in ('ecos.2x.execute','semantic.interpret'):
  admin("insert into ecos.executor_capability(executor_instance_id,capability_name,capability_version,attested_by,expires_at) values(%s,%s,1,%s,clock_timestamp()+interval '1 hour')",(f.inst,cap,f.p))

 good('executor.register',{'host':'SYNTHETIC','runtime':'structural-acceptance','software_version':'candidate35','evidence_hash':'a'*64},'executor')
 admin("insert into ecos_meta.domain_authority(domain,owner,epoch,evidence) values('test.domain_a','2X',1,'Local multidomain acceptance'),('test.domain_b','2X',1,'Local multidomain acceptance')")
 for domain in ('test.domain_a','test.domain_b'):
  admin("insert into ecos_meta.principal_domain values(%s,%s,'production',1,'2X')",(f.p,domain))
 for n,domain in enumerate(('test.domain_a','test.domain_b'),1):
  w=f.add_work(1)[0]
  admin("insert into ecos.work_context(occurrence_id,operation,input) values(%s,'work.complete','{}')",(w,))
  admin("insert into ecos_meta.object_domain values('task',%s,%s) on conflict(record_type,record_id) do update set domain=excluded.domain",(f.task,domain))
  admin("insert into ecos_meta.object_domain values('work_occurrence',%s,%s)",(w,domain))
  claimed=good('work.next',{'executor_instance_id':f.inst,'lease_seconds':120},'executor')
  assert claimed['data']['claim']['occurrence_id']==w,claimed
  fence=f.result_arguments(claimed['data'])['fence']
  assert good('work.package',{'fence':fence},'executor')['data']['occurrence']['id']==w
  ref=source()
  state='waiting' if n==1 else 'open'
  good('task.transition',{'task_id':f.task,'expected_version':ref['record_version'],'target_state':state,'wait_reason':'owner' if n==1 else 'none','reason_code':'multidomain_acceptance','evidence':[{'source':ref,'assertion':'Synthetic multi-domain governed round trip','verification':'verified'}]})
  assert read('task',f.task)['record']['lifecycle_state']==state
  request=f.request(f.result_arguments(claimed['data']))
  with target.connect() as db:
   db.execute('set local role executor')
   first=db.execute('select ecos.operate(%s,%s)',('work.complete',Jsonb(request))).fetchone()[0]
   assert first.get('status')=='committed',first
   assert db.execute('select ecos.operate(%s,%s)',('work.complete',Jsonb(request))).fetchone()[0]==first
  assert read('work_occurrence',w)['record']['state']=='succeeded'
  denied=uid();admin("insert into ecos.task(id,business_id,title,lifecycle_state,wait_reason,description) values(%s,%s,'Ungrant test','open','none','Synthetic permission denial')",(denied,'SYNTHETIC-'+denied))
  admin("insert into ecos_meta.object_domain values('task',%s,%s)",(denied,domain))
  try:read('task',denied);raise AssertionError('Object grant bypass')
  except Exception as e:assert getattr(e,'sqlstate',None)=='42501',type(e).__name__
  assert admin('select count(*) from ecos.provider_command')[0][0]==0
  report['passes'].append({'pass':n,'governed_multidomain_roundtrip':'PASS','claim_completion_idempotency':'PASS','object_grant_denial':'PASS','provider_effects':0})
  print(json.dumps(report['passes'][-1]),flush=True)
 report['status']='PASS'
finally:
 if running:native([pg/'pg_ctl.exe','-D',root/'data','-m','fast','-w','stop'])
 (root/'report.json').write_text(json.dumps(report,indent=2))
 print('Receipt: '+str(root/'report.json'))
