"""Plan/apply exact worker instructions through the existing administrative configuration path.

No runtime operation, connector grant, activation, source transformation, or provider call.
The caller supplies the approved source-worker -> existing definition/stage mapping.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'src'), str(ROOT/'scripts')]
from repair_task_loop_population import read_sources
from resident2x_acceptance import hosted_admin


def digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def off(db):
    if db.execute("select (select count(*) from ecos.executor where enabled)+(select count(*) from ecos.work_definition where enabled)+(select count(*) from ecos.work_claim where state='active' and expires_at>clock_timestamp())").fetchone()[0]:
        raise ValueError('production_must_remain_off')


def state(db, definition, stage):
    row = db.execute('''select d.record_version,s.record_version from ecos.work_definition d
        join ecos.work_stage_definition s on s.work_definition_id=d.id
        where d.id=%s and s.id=%s and not d.enabled''', (definition, stage)).fetchone()
    if row is None:
        raise ValueError('existing_disabled_definition_stage_required')
    version = db.execute('select coalesce(max(instruction_version),0) from ecos.work_instruction_version where stage_definition_id=%s', (stage,)).fetchone()[0]
    caps = db.execute('select capability_name,minimum_version from ecos.stage_capability_requirement where stage_definition_id=%s order by capability_name', (stage,)).fetchall()
    return {'definition_version':row[0], 'stage_version':row[1], 'instruction_version':version,
            'capabilities_sha256':digest(json.dumps(caps, separators=(',', ':')))}


def plan(db, mapping):
    off(db)
    sources = read_sources(db)
    items, seen = [], set()
    if not mapping:
        raise ValueError('empty_mapping')
    for item in mapping:
        stage = item['stage_definition_id']
        if stage in seen:
            raise ValueError('duplicate_stage_mapping')
        seen.add(stage)
        row, batch, locator = sources[item['source_worker_id']]
        text = row.get('Instructions')
        if not isinstance(text, str) or not 0 < len(text.encode('utf-8')) <= 262144:
            raise ValueError('complete_instruction_text_required')
        items.append({**item, 'source_batch_id':batch, 'source_locator':locator,
                      'instruction_sha256':digest(text),
                      'expected':state(db,item['work_definition_id'],stage)})
    return {'schema_version':1, 'configuration_id':str(uuid4()), 'items':items}


def source_text(db, item):
    row = db.execute('''select b.column_names,r.raw_value->'values'
        from ecos_migration.raw_source_row r join ecos_migration.raw_migration_batch b on b.id=r.batch_id
        where b.source_family='Task Loop' and b.id=%s and r.source_locator=%s''',
        (item['source_batch_id'],item['source_locator'])).fetchone()
    if row is None:
        raise ValueError('source_missing')
    source = dict(zip(*row))
    text = source['Instructions']
    if source['Task Loop ID'] != item['source_worker_id'] or digest(text) != item['instruction_sha256']:
        raise ValueError('source_drift')
    return text


def configure(db, document):
    """Call within the SAME transaction as existing definition/stage configuration writes."""
    db.execute('select pg_advisory_xact_lock(684026,20)')
    off(db)
    items = document['items']
    if not items or len({x['stage_definition_id'] for x in items}) != len(items):
        raise ValueError('empty_or_duplicate_stage_mapping')
    # Validate the complete batch before any write. Shared definitions advance only once.
    prepared, definitions, replayed = [], set(), []
    for item in items:
        definition, stage = item['work_definition_id'], item['stage_definition_id']
        db.execute('select id from ecos.work_definition where id=%s for update',(definition,))
        db.execute('select id from ecos.work_stage_definition where id=%s for update',(stage,))
        text = source_text(db,item)
        reference = 'ecos_migration:'+item['source_batch_id']+':'+item['source_locator']+':Instructions'
        prior = db.execute('''select instruction_version,content_sha256,source_reference from ecos.work_instruction_version
            where stage_definition_id=%s and correlation_id=%s''',(stage,document['configuration_id'])).fetchone()
        current = state(db,definition,stage)
        if prior:
            expected = {**item['expected'], 'definition_version':item['expected']['definition_version']+1,
                        'stage_version':item['expected']['stage_version']+1,
                        'instruction_version':item['expected']['instruction_version']+1}
            if current != expected or prior != (expected['instruction_version'],digest(text),reference):
                raise ValueError('replay_state_drift')
            replayed.append(stage)
            continue
        if current != item['expected']:
            raise ValueError('configuration_version_drift')
        prepared.append((item,text,reference))
        definitions.add(definition)
    if replayed and prepared:
        raise ValueError('partial_batch_requires_reconciliation')
    for definition in sorted(definitions):
        db.execute('update ecos.work_definition set record_version=record_version+1 where id=%s',(definition,))
    for item,text,reference in prepared:
        db.execute('update ecos.work_stage_definition set record_version=record_version+1 where id=%s',(item['stage_definition_id'],))
        db.execute('''insert into ecos.work_instruction_version(work_definition_id,stage_definition_id,
            instruction_version,instruction_text,content_sha256,source_reference,configured_by_role,correlation_id)
            values(%s,%s,%s,%s,%s,%s,current_user,%s)''',
            (item['work_definition_id'],item['stage_definition_id'],item['expected']['instruction_version']+1,
             text,digest(text),reference,document['configuration_id']))
    off(db)
    return {'configured':len(prepared),'replayed':len(replayed),'provider_effects':0}


def readback(db, document):
    off(db)
    for item in document['items']:
        row = db.execute('''select work_definition_id,instruction_version,instruction_text,content_sha256,
            configured_by_role from ecos.work_instruction_version where stage_definition_id=%s and correlation_id=%s''',
            (item['stage_definition_id'],document['configuration_id'])).fetchone()
        if not row or str(row[0]) != item['work_definition_id'] or row[1] != item['expected']['instruction_version']+1 or row[2] != source_text(db,item) or row[3] != item['instruction_sha256'] or not row[4]:
            raise ValueError('instruction_readback_failed')
        expected = {**item['expected'],'definition_version':item['expected']['definition_version']+1,
                    'stage_version':item['expected']['stage_version']+1,'instruction_version':row[1]}
        if state(db,item['work_definition_id'],item['stage_definition_id']) != expected:
            raise ValueError('configuration_readback_failed')
    return {'verified':len(document['items']),'production_off':True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mapping',type=Path)
    parser.add_argument('--plan',required=True,type=Path)
    parser.add_argument('--apply',action='store_true')
    args = parser.parse_args()
    connect,_ = hosted_admin()
    if not args.apply:
        if args.mapping is None:
            parser.error('--mapping is required to prepare a plan')
        with connect() as db:
            document=plan(db,json.loads(args.mapping.read_text(encoding='utf-8')))
        with args.plan.open('x',encoding='utf-8',newline='\n') as out:
            json.dump(document,out,indent=2)
        print(json.dumps({'planned':len(document['items']),'writes':0}))
    else:
        document=json.loads(args.plan.read_text(encoding='utf-8'))
        with connect() as db:
            result=configure(db,document)
        with connect() as db:
            result.update(readback(db,document))
        print(json.dumps(result))


if __name__=='__main__':
    main()
