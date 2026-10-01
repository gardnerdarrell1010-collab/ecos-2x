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

 admin("update ecos.executor set surface='ONLINE_SEMANTIC',record_version=record_version+1 where id=%s",(f.ex,))
 good('executor.register',{'host':'SYNTHETIC','runtime':'core-cadence-acceptance','software_version':'candidate38','evidence_hash':'a'*64},'executor')
 for stage,period in [('incremental_continuity',21600)]:
  admin("update ecos.work_stage_definition set stage_key=%s,execution_surface='ONLINE_SEMANTIC',kind='semantic',record_version=record_version+1 where id=%s",(stage,f.stage))
  w=f.add_work(1)[0]
  admin("update ecos.work_occurrence set task_id=null,due_at=clock_timestamp()-make_interval(secs=>%s),record_version=record_version+1 where id=%s",(period+1,w))
  admin("insert into ecos.work_priority(occurrence_id,recurrence_period_seconds) values(%s,%s)",(w,period))
  admin("insert into ecos.work_context(occurrence_id,operation,input) values(%s,'work.complete','{}')",(w,))
  for n in (1,2):
   if n==2:
    # Advance only the disposable fixture's due time after verifying the preserved cadence.
    future=admin("select max(ended_at)+make_interval(secs=>%s) from ecos.execution_run where occurrence_id=%s",(period+1,w))[0][0]
    next_id=admin('select ecos_meta.materialize_occurrence(%s,%s)',(w,future))[0][0]
    assert admin("select o.due_at=r.ended_at+make_interval(secs=>%s) from ecos.work_occurrence o,ecos.execution_run r where o.id=%s and r.occurrence_id=%s",(period,next_id,w))[0][0]
    admin("update ecos.work_occurrence set due_at=clock_timestamp()-interval '1 second',record_version=record_version+1 where id=%s",(next_id,))
   claimed=good('work.next',{'executor_instance_id':f.inst,'lease_seconds':120},'executor')
   assert claimed['status']=='CLAIMED',claimed
   current=claimed['data']['claim']['occurrence_id']
   assert (current==w)==(n==1)
   assert claimed['data']['work_package']['task'] is None
   fence=f.result_arguments(claimed['data'])['fence']
   assert good('work.package',{'fence':fence},'executor')['data']['occurrence']['id']==current
   assert not admin("select 1 from ecos_meta.object_domain where record_type='work_occurrence' and record_id=%s",(current,))
   scope=good('runtime.scope.read',{'fence':fence,'record_type':'task','after_id':None,'limit':100},'executor')['data']
   assert any(x['record']['id']==f.task for x in scope['records'])
   if stage!='incremental_continuity':
    ref=source();versions=[{k:ref[k] for k in ('record_type','record_id','record_version')}]
    ev={'source':ref,'assertion':'Synthetic core review from exact scoped source','verification':'verified'}
    state='waiting' if n==1 else 'open'
    item={'item_id':uid(),'depends_on_item_ids':[],'source_references':[ref],'expected_record_versions':versions,'proposed_operations':[{'operation':'task.transition','arguments':{'task_id':f.task,'expected_version':ref['record_version'],'target_state':state,'wait_reason':'owner' if n==1 else 'none','reason_code':'synthetic_core_review','evidence':[ev]}}],'evidence':[ev],'confidence_basis_points':10000,'unresolved_ambiguity':[]}
    proposal={'id':uid(),'proposal_type':'synthetic_core_review','schema_version':'1.0.0','created_at':datetime.now(timezone.utc).isoformat(),'correlation_id':f.correlation,'source_references':[ref],'expected_record_versions':versions,'items':[item]}
    proposal['content_hash']=admin('select ecos_meta.content_hash(%s)',(Jsonb(proposal),))[0][0]
    good('semantic.proposal.submit',{'fence':fence,'proposal':proposal},'executor')
    good('core.review.commit',{'fence':fence,'proposal_id':proposal['id']},'executor')
    assert read('task',f.task)['record']['lifecycle_state']==state
   snapshot=good('continuity.snapshot',{'fence':fence},'executor')['data']
   records=snapshot.pop('records'); boundary=snapshot
   module=(r/'supabase/functions/online-ada-2x/continuity_core.mjs').as_uri()
   node=Path('C:/Users/info/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe')
   code="import {encryptSnapshot,verifySnapshot} from '"+module+"';let s='';for await(const c of process.stdin)s+=c;const v=JSON.parse(s);const key=new Uint8Array(32).fill(7);if(v.wire){await verifySnapshot(v.wire,v.boundary,key);process.stdout.write('{}');}else{process.stdout.write(JSON.stringify(await encryptSnapshot(v.records,v.boundary,key,v.id)));}"
   def crypto(v):
    return json.loads(subprocess.run([str(node),'--input-type=module','-e',code],input=json.dumps(v),capture_output=True,text=True,check=True,creationflags=subprocess.CREATE_NO_WINDOW).stdout)
   package=uid(); wire=crypto({'records':records,'boundary':boundary,'id':package})
   args_={'fence':fence,'package_id':package,'boundary':boundary,**wire}
   value=good('continuity.checkpoint.commit',args_,'executor')['data']
   manifest=read('export_package',package)['record']['manifest']
   import base64
   from ecos.core.export_verify import verify_inventory
   files=root/('package-'+str(n));files.mkdir()
   for name,identity in value['files'].items():
    artifact=read('artifact',identity)['record']
    raw=base64.b64decode(artifact['uri'].split(';base64,')[1],validate=True)
    (files/name).write_bytes(raw)
   assert verify_inventory(files,manifest)==3
   crypto({'wire':{**wire,'ciphertext':base64.b64encode((files/'records.aes-gcm').read_bytes()).decode()},'boundary':boundary})
   assert read('backup_record',value['backup_id'])['record']['encrypted']
   # No head advancement until the verified stage result commits.
   before=good('continuity.snapshot',{'fence':fence},'executor')['data']['previous_package_id']
   assert before==boundary['previous_package_id']
   good('work.complete',f.result_arguments(claimed['data']),'executor')
   assert read('work_occurrence',current)['record']['state']=='succeeded'
   report['passes'].append({'checkpoint_manifest_parity':'PASS','encrypted_readback':'PASS','stage':stage,'pass':n,'cadence':period,'domain_required':False,'readback':'PASS','provider_effects':0})
   print(json.dumps(report['passes'][-1]),flush=True)
  assert good('work.next',{'executor_instance_id':f.inst,'lease_seconds':120},'executor')['status']=='NO_ELIGIBLE_WORK'
  # Retire only this disposable fixture cadence before reusing its stage definition.
  admin('update ecos.work_priority set recurrence_period_seconds=null where occurrence_id in(select id from ecos.work_occurrence where stage_definition_id=%s)',(f.stage,))
 report['status']='PASS'
finally:
 if running:native([pg/'pg_ctl.exe','-D',root/'data','-m','fast','-w','stop'])
 (root/'report.json').write_text(json.dumps(report,indent=2))
 print('Receipt: '+str(root/'report.json'))
