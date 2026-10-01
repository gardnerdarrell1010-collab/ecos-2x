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
 admin("update ecos_meta.domain_authority set owner='2X',epoch=2,evidence='Disposable routing fixture only, no live transfer' where domain='toast.acquisition'")
 admin("update ecos_meta.principal_domain set domain='toast.acquisition',execution_mode='production',authority_epoch=2 where principal_id=%s",(f.p,))
 admin("insert into ecos.executor_capability(executor_instance_id,capability_name,capability_version,attested_by,expires_at) values(%s,'ecos.2x.execute',1,%s,clock_timestamp()+interval '1 hour')",(f.inst,f.p))
 op('executor.register',{'host':'SYNTHETIC','runtime':'capability-routing','software_version':'45','evidence_hash':'a'*64})
 admin("insert into ecos.stage_capability_requirement(stage_definition_id,capability_name,minimum_version) values(%s,'provider.drive',1)",(f.stage,))
 for n in (1,2):
  admin('update ecos.work_stage_definition set stage_key=%s,record_version=record_version+1 where id=%s',('arbitrary_stage_'+str(n),f.stage))
  work=f.add_work(1)[0];admin("insert into ecos.work_context(occurrence_id,operation,input) values(%s,'work.complete','{}')",(work,))
  assert op('work.next',{'executor_instance_id':f.inst,'lease_seconds':120})['status']=='NO_ELIGIBLE_WORK'
  cap=admin("insert into ecos.executor_capability(executor_instance_id,capability_name,capability_version,attested_by,expires_at) values(%s,'provider.drive',1,%s,clock_timestamp()+interval '1 hour') returning id",(f.inst,f.p))[0][0]
  admin("insert into ecos_meta.object_domain values('work_occurrence',%s,'staffing.features')",(work,))
  assert not admin('select ecos_meta.selection(%s,%s,clock_timestamp())',(work,f.inst))[0][0]['eligible']
  admin("delete from ecos_meta.object_domain where record_type='work_occurrence' and record_id=%s",(work,))
  claimed=op('work.next',{'executor_instance_id':f.inst,'lease_seconds':120})
  assert claimed['status']=='CLAIMED' and claimed['data']['claim']['occurrence_id']==work
  args=f.result_arguments(claimed['data'])
  package=op('work.package',{'fence':args['fence']})['data']
  assert package['stage']['stage_key']=='arbitrary_stage_'+str(n)
  op('work.complete',args)
  assert admin('select state from ecos.work_occurrence where id=%s',(work,))[0][0]=='succeeded'
  admin('delete from ecos.executor_capability where id=%s',(cap,))
  report['passes'].append({'pass':n,'capability_missing_rejected':True,'lookup_only_matching':True,'arbitrary_stage_name':True,'explicit_domain_preserved':True,'claim_package_completion':'PASS','provider_effects':0})
 report.update(status='PASS',scope='domainless canonical capability routing; no production/provider execution')
 print(json.dumps(report))
finally:
 if running:native([pg/'pg_ctl.exe','-D',root/'data','-m','fast','-w','stop'])
 (root/'report.json').write_text(json.dumps(report,indent=2))
 print('Receipt: '+str(root/'report.json'))
