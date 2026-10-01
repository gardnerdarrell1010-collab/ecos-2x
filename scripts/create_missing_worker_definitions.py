"""Create missing disabled canonical definitions from current conversion ledger and source.

Administrative migration only; no executor grants, occurrences, domains, or activation.
The preserved source is copied verbatim. This is configuration, not runtime acceptance.
"""
import json,sys,re
from pathlib import Path
from uuid import uuid4
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'src'),str(ROOT/'scripts')]
from psycopg.types.json import Jsonb
from configure_worker_instructions import plan,configure,readback,off
from repair_task_loop_population import read_sources
from resident2x_acceptance import hosted_admin,secure_directory

CAPABILITIES={
 'google.sheets.read':['db.governed_operations'], 'google.sheets.write':['db.governed_operations'],
 'ecos.writeback':['db.governed_operations'], 'semantic.reasoning':['semantic.interpret'],
 'google.drive.read':['provider.drive'], 'google.drive.write':['provider.drive'],
 'google.docs.read':['provider.drive'], 'google.docs.write':['provider.drive'],
 'gmail.read':['provider.gmail'], 'google.calendar.read':['provider.calendar'],
 'financial.records.read':['provider.finance'], 'vercel.deploy':['provider.publication'],
 'html.render':['local.render'], 'local_filesystem':['local.filesystem.read','local.filesystem.write'],
 'spreadsheet.xlsx.read':['spreadsheet.xlsx.read'], 'local.process.execute':['local.process.execute'],
 'secure.reference.resolve':['secure.reference.resolve'], 'http.authenticated.request':['http.authenticated.request']}


def prepare(db, receipt):
    db.execute('select pg_advisory_xact_lock(684026,20)');off(db)
    sources=read_sources(db)
    existing=set(x[0] for x in db.execute('select source_reference from ecos.work_instruction_version'))
    proposed=[]
    for business,description,version in db.execute("select business_id,description,record_version from ecos.task where business_id like 'CONVERT-2X-A%' order by business_id"):
        info=json.loads(description)
        if info['target'] not in ('ONLINE_2X','RESIDENT_2X'):continue
        worker=info['legacy_worker_id'];row,batch,locator=sources[worker]
        reference='ecos_migration:'+batch+':'+locator+':Instructions'
        if reference in existing:continue
        text=row['Instructions'];offset=text.index('ECOS_CAPABILITIES=')+len('ECOS_CAPABILITIES=')
        declared=json.JSONDecoder().raw_decode(text[offset:])[0]['stages']
        if len(declared)!=1:raise ValueError('multiple_source_stages_require_exact_mapping')
        stage=declared[0]['stage'];caps=sorted({'ecos.2x.execute'}|{mapped for cap in declared[0]['required'] for mapped in CAPABILITIES[cap]})
        name=worker.lower().replace('-','_')
        if db.execute('select 1 from ecos.work_definition where name=%s',(name,)).fetchone():raise ValueError('canonical_definition_already_exists_reconcile')
        if db.execute('select 1 from ecos.work_stage_definition where stage_key=%s',(stage,)).fetchone():raise ValueError('possible_existing_stage_requires_reconciliation')
        proposed.append({'worker':worker,'ledger':business,'ledger_version':version,'target':info['target'],'name':name,'stage':stage,'caps':caps,'source_max_attempts':row.get('Maximum Attempts',''),'batch':batch,'locator':locator})
    if len(proposed)!=25:raise ValueError('population_changed')
    # Reuse the same conservative, no-automatic-retry configuration policy as existing
    # disabled migration definitions. Preserve unresolved legacy retry values in evidence.
    policy=db.execute("select id from ecos.retry_policy where max_attempts=1 and initial_delay_seconds=1 and max_delay_seconds=1 and backoff_multiplier=1 and jitter_basis_points=0 and retryable_error_classes='[]'::jsonb order by id limit 1").fetchone()[0]
    needed={c for x in proposed for c in x['caps']}
    existing_caps={r[0] for r in db.execute('select name from ecos.capability where version=1')}
    if needed-existing_caps:
        raise ValueError('required_capability_not_in_approved_catalog')
    schema_id='https://contracts.ecos.invalid/v1/worker-configuration-input.schema.json'
    schema={'$schema':'https://json-schema.org/draft/2020-12/schema','$id':schema_id,'type':'object','properties':{'source_worker_id':{'type':'string'},'source_reference':{'type':'string'}},'required':['source_worker_id','source_reference'],'additionalProperties':True}
    db.execute('insert into ecos_meta.contract_schema values(%s,%s) on conflict(schema_id) do nothing',(schema_id,Jsonb(schema)))
    mapping=[]
    for item in proposed:
        definition,stage=str(uuid4()),str(uuid4())
        selected_policy=policy
        maximum=str(item['source_max_attempts']).strip()
        if maximum.isdigit() and int(maximum)>0:
            match=db.execute("select id from ecos.retry_policy where max_attempts=%s and retryable_error_classes='[]'::jsonb order by id limit 1",(int(maximum),)).fetchone()
            if match is None:raise ValueError('missing_existing_explicit_attempt_policy')
            selected_policy=match[0]
        surface='ONLINE_SEMANTIC' if item['target']=='ONLINE_2X' else 'RESIDENT_DETERMINISTIC_PROVIDER'
        kind='semantic' if item['target']=='ONLINE_2X' else 'deterministic'
        db.execute("insert into ecos.work_definition(id,name,definition_version,enabled,fulfillment_kind,retry_policy_id) values(%s,%s,1,false,'single_stage',%s)",(definition,item['name'],selected_policy))
        db.execute('''insert into ecos.work_stage_definition(id,work_definition_id,stage_key,kind,execution_surface,input_schema_id,result_schema_id,requires_approval)
            values(%s,%s,%s,%s,%s,%s,'https://contracts.ecos.invalid/v1/stage_result.schema.json',false)''',(stage,definition,item['stage'],kind,surface,schema_id))
        for cap in item['caps']:
            db.execute('insert into ecos.stage_capability_requirement(stage_definition_id,capability_name,minimum_version) values(%s,%s,1)',(stage,cap))
        item.update(definition_id=definition,stage_id=stage,retry_semantics='PENDING_SOURCE_DEFAULT_EQUIVALENCE',runtime_acceptance='NOT_PROVEN',instruction_transformation='NONE_LOSSLESS')
        mapping.append({'source_worker_id':item['worker'],'work_definition_id':definition,'stage_definition_id':stage})
    document=plan(db,mapping);configure(db,document)
    (receipt/'plan.json').write_text(json.dumps(document,indent=2))
    (receipt/'configuration.json').write_text(json.dumps(proposed,indent=2))
    return document,proposed


def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--apply',action='store_true',required=True);parser.parse_args()
    receipt=ROOT/'.local'/('remaining-definitions-'+uuid4().hex);secure_directory(receipt)
    connect,_=hosted_admin()
    with connect() as db:document,proposed=prepare(db,receipt)
    with connect() as db:
        result=readback(db,document)
        for item in proposed:
            row=db.execute('select d.enabled,s.execution_surface from ecos.work_definition d join ecos.work_stage_definition s on s.work_definition_id=d.id where d.id=%s and s.id=%s',(item['definition_id'],item['stage_id'])).fetchone()
            assert row==(False,'ONLINE_SEMANTIC' if item['target']=='ONLINE_2X' else 'RESIDENT_DETERMINISTIC_PROVIDER')
        result.update(created=len(proposed),instruction_rows=db.execute('select count(*) from ecos.work_instruction_version').fetchone()[0],runtime_acceptance='NOT_PROVEN',provider_effects=0)
    (receipt/'readback.json').write_text(json.dumps(result,indent=2));print(json.dumps(result));print('Receipt: '+str(receipt))

if __name__=='__main__':main()
