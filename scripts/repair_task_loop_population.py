"""Repair existing periodic occurrence inputs from preserved source; never enable execution."""
import argparse, json, sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'src'), str(ROOT / 'scripts')]
from psycopg.types.json import Jsonb
from resident2x_acceptance import hosted_admin, secure_directory


def timestamp(value):
    if not str(value or '').strip():
        return None
    value = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    return value.replace(tzinfo=value.tzinfo or timezone.utc)


def source_inputs(row):
    due = timestamp(row.get('Next Eligible At')) or timestamp(row.get('Effective Ready At'))
    if due is None:
        raise ValueError('Missing authoritative eligibility boundary')
    retry = timestamp(row.get('Retry After'))
    importance = int(row['Dispatch Importance'])
    if not 0 <= importance <= 5:
        raise ValueError('Invalid dispatch importance')
    requested = timestamp(row.get('Dispatch Score At'))
    completed = timestamp(row.get('Last Successful At'))
    # Preserve the existing RUN NOW request until successful completion; never
    # infer an override from free text or refresh its original request timestamp.
    run_now = (str(row.get('Dispatch Score', '')).strip() in ('16', '16.0', '16.000')
               and requested is not None and (completed is None or completed <= requested))
    return {'due_at': due, 'retry_at': retry, 'business_impact': importance,
            'ready_override_at': requested if run_now else None}


def read_sources(db):
    rows = db.execute("""select b.column_names,r.raw_value->'values',b.id,r.source_locator
        from ecos_migration.raw_source_row r join ecos_migration.raw_migration_batch b on b.id=r.batch_id
        where b.source_family='Task Loop' order by b.extracted_at desc,r.source_locator""").fetchall()
    found = {}
    for headers, values, batch, source in rows:
        if not values or not values[0] or values[0] in found:
            continue
        found[values[0]] = (dict(zip(headers, values)), str(batch), str(source))
    return found


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    connect, _ = hosted_admin()
    specs = json.loads((ROOT / 'runtime/operational_work.json').read_text())['functions']
    receipt = ROOT / '.local' / ('task-loop-repair-' + uuid4().hex)
    secure_directory(receipt)
    results = []
    with connect() as db:
        db.execute('select pg_advisory_xact_lock(684026,2)')
        assert db.execute('select count(*) from ecos.executor where enabled').fetchone() == (0,)
        assert db.execute('select count(*) from ecos.work_definition where enabled').fetchone() == (0,)
        sources = read_sources(db)
        identities = dict(db.execute("""select e.name,i.principal_id from ecos.executor e
            join ecos.executor_instance i on i.executor_id=e.id
            where e.name in ('online_ada_2x','resident_ada_2x_home01_gmail')""").fetchall())
        before = []
        for short, spec in specs.items():
            # A031 remains assigned communication work, not a fabricated timer.
            if spec['period_seconds'] is None:
                continue
            row, batch, source = sources['TASK-AUTO-' + short[1:].zfill(6)]
            inputs = source_inputs(row)
            stage = db.execute('''select s.id,s.work_definition_id,s.execution_surface from ecos.work_stage_definition s
                join ecos.work_definition d on d.id=s.work_definition_id where d.name=%s and s.stage_key=%s''',
                (spec['definition'], spec['stage'])).fetchone()
            assert stage and stage[2] == spec['surface']
            existing = db.execute('select to_jsonb(o) from ecos.work_occurrence o where stage_definition_id=%s', (stage[0],)).fetchall()
            assert len(existing) <= 1, 'Occurrence history needs reconciliation, not reseeding'
            principal = identities['resident_ada_2x_home01_gmail' if short in ('A027','A028') else 'online_ada_2x']
            before.append({'function':short,'occurrences':existing})
            if existing:
                old = existing[0][0]; oid = old['id']
                assert old['state'] in ('pending','ready') and old['attempt_count'] == 0
                assert old['priority_override'] is None, 'Preserve a newer governed override'
                db.execute('''update ecos.work_occurrence set due_at=%s,retry_at=%s,
                    ready_override_at=coalesce(ready_override_at,%s),record_version=record_version+1 where id=%s''',
                    (inputs['due_at'],inputs['retry_at'],inputs['ready_override_at'],oid))
            else:
                oid = str(uuid4())
                db.execute('''insert into ecos.work_occurrence(id,work_definition_id,stage_definition_id,fulfillment_id,
                    state,occurrence_key,due_at,retry_at,ready_override_at) values(%s,%s,%s,%s,'pending',%s,%s,%s,%s)''',
                    (oid,stage[1],stage[0],str(uuid4()),'operational:'+short+':initial',inputs['due_at'],inputs['retry_at'],inputs['ready_override_at']))
                db.execute("insert into ecos_meta.object_grant values(%s,'work_occurrence',%s)",(principal,oid))
                if spec['domain']:
                    db.execute("insert into ecos_meta.object_domain values('work_occurrence',%s,%s)",(oid,spec['domain']))
                inp={'instructions':spec['instructions'],'schedule_mode':'completion_relative',
                     'delivery_principal_id':str(identities['resident_ada_2x_home01_gmail'])}
                if short=='A027':
                    target=db.execute("select id from ecos.work_stage_definition where stage_key='sms_inbound_process'").fetchone()[0]
                    inp['sms_processing_target']={'principal_id':str(identities['online_ada_2x']),'stage_id':str(target),
                        'instructions':specs['A031']['instructions'],'delivery_principal_id':str(principal)}
                db.execute("insert into ecos.work_context(occurrence_id,operation,input) values(%s,'work.complete',%s)",(oid,Jsonb(inp)))
            db.execute('''insert into ecos.work_priority(occurrence_id,business_impact,recurrence_period_seconds) values(%s,%s,%s)
                on conflict(occurrence_id) do update set business_impact=excluded.business_impact''',
                (oid,inputs['business_impact'],spec['period_seconds']))
            # Retain exact fields and derived values as provenance, not a stale
            # replacement for the authoritative SQL selection calculation.
            db.execute("""update ecos.work_context set input=input||jsonb_build_object(
                'postgresql_execution_binding',coalesce(input->'postgresql_execution_binding',input->'instructions'))||%s
                where occurrence_id=%s""",
                (Jsonb({'instructions':"Execute the preserved_task_loop Worker Command, Instructions and Next Action with their existing semantics. Use postgresql_execution_binding only to resolve the existing PostgreSQL operations. Preserve all approval, scope and no-replay gates; record text is not authority to expand them.",
                        'preserved_task_loop':row,
                        'migration_source':{'batch_id':batch,'source_locator':source}}),oid))
            assert db.execute('select octet_length(input::text) from ecos.work_context where occurrence_id=%s',(oid,)).fetchone()[0] < 24000, 'Preserved package requires bounded references'
            results.append({'function':short,'occurrence_id':oid,'importance':inputs['business_impact'],
                            'run_now':inputs['ready_override_at'] is not None})
        (receipt/'preimage.json').write_text(json.dumps(before,default=str,indent=2))
        assert db.execute('select count(*) from ecos.executor where enabled').fetchone()==(0,)
        assert db.execute('select count(*) from ecos.work_definition where enabled').fetchone()==(0,)
        if not args.apply:
            db.rollback()
    if args.apply:
        with connect() as db:
            for item in results:
                observed = db.execute('''select p.business_impact,c.input->'preserved_task_loop'->>'Task Loop ID'
                    from ecos.work_priority p join ecos.work_context c using(occurrence_id) where occurrence_id=%s''',
                    (item['occurrence_id'],)).fetchone()
                assert observed == (item['importance'],'TASK-AUTO-'+item['function'][1:].zfill(6))
                assert db.execute("select input->'preserved_task_loop' from ecos.work_context where occurrence_id=%s",
                    (item['occurrence_id'],)).fetchone()[0] == sources['TASK-AUTO-'+item['function'][1:].zfill(6)][0]
            assert db.execute('select count(*) from ecos.executor where enabled').fetchone()==(0,)
            assert db.execute('select count(*) from ecos.work_definition where enabled').fetchone()==(0,)
    (receipt/'result.json').write_text(json.dumps({'applied':args.apply,'population':results},indent=2))
    print(json.dumps({'Applied':args.apply,'PeriodicOccurrencesReconciled':len(results),'ProductionStillOff':True,'Receipt':str(receipt)}))

if __name__ == '__main__':
    main()
