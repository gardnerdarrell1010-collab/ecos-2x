"""Instantiate Gmail stage definitions disabled until governed integration passes.

No occurrences, claims, schedules, executor grants or provider effects are created.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'src'), str(ROOT / 'scripts')]

STAGES = (
    ('gmail_intake', 'gmail_intake', 'semantic', 'ONLINE_SEMANTIC', False,
     ['ecos.2x.execute', 'provider.gmail', 'semantic.interpret', 'db.governed_operations']),
    ('gmail_semantic', 'gmail_semantic', 'semantic', 'ONLINE_SEMANTIC', False,
     ['ecos.2x.execute', 'semantic.interpret', 'semantic.draft', 'db.governed_operations']),
    ('gmail_dispatch', 'gmail_draft', 'deterministic', 'RESIDENT_DETERMINISTIC_PROVIDER', True,
     ['ecos.2x.execute', 'provider.gmail', 'db.governed_operations']),
    ('gmail_dispatch', 'gmail_send', 'deterministic', 'RESIDENT_DETERMINISTIC_PROVIDER', True,
     ['ecos.2x.execute', 'provider.gmail', 'db.governed_operations']),
)


def prepare(connect):
    result = []
    with connect() as db:
        db.execute('select pg_advisory_xact_lock(684026, 1010)')
        for definition, stage, kind, surface, approval, capabilities in STAGES:
            row = db.execute('select id,enabled from ecos.work_definition where name=%s and definition_version=1', (definition,)).fetchone()
            if row:
                definition_id, enabled = row
                if enabled: raise ValueError('already_active_definition_requires_reconciliation')
            else:
                retry = db.execute("insert into ecos.retry_policy(max_attempts,initial_delay_seconds,max_delay_seconds,backoff_multiplier,jitter_basis_points,retryable_error_classes) values(1,1,1,1,0,'[]') returning id").fetchone()[0]
                definition_id = db.execute("insert into ecos.work_definition(name,definition_version,enabled,fulfillment_kind,retry_policy_id) values(%s,1,false,'staged',%s) returning id", (definition,retry)).fetchone()[0]
            schema_in, schema_out = 'ecos.gmail.'+stage+'.input.v1', 'ecos.gmail.'+stage+'.result.v1'
            prior = db.execute('select id,kind,execution_surface,requires_approval,input_schema_id,result_schema_id from ecos.work_stage_definition where work_definition_id=%s and stage_key=%s', (definition_id,stage)).fetchone()
            if prior:
                stage_id=prior[0]
                if prior[1:] != (kind,surface,approval,schema_in,schema_out): raise ValueError('gmail_stage_drift')
            else:
                stage_id=db.execute('insert into ecos.work_stage_definition(work_definition_id,stage_key,kind,execution_surface,input_schema_id,result_schema_id,requires_approval) values(%s,%s,%s,%s,%s,%s,%s) returning id',(definition_id,stage,kind,surface,schema_in,schema_out,approval)).fetchone()[0]
            for cap in capabilities:
                db.execute('insert into ecos.stage_capability_requirement(stage_definition_id,capability_name,minimum_version) values(%s,%s,1) on conflict(stage_definition_id,capability_name) do nothing',(stage_id,cap))
            actual=db.execute('select capability_name,minimum_version from ecos.stage_capability_requirement where stage_definition_id=%s order by capability_name',(stage_id,)).fetchall()
            if actual != [(c,1) for c in sorted(capabilities)]: raise ValueError('gmail_capability_requirement_drift')
            result.append({'definition':definition,'stage':stage,'surface':surface,'requires_approval':approval,'enabled':False})
    with connect() as db:
        for row in result:
            actual=db.execute('select d.enabled,s.requires_approval from ecos.work_stage_definition s join ecos.work_definition d on d.id=s.work_definition_id where d.name=%s and s.stage_key=%s',(row['definition'],row['stage'])).fetchone()
            assert actual == (False,row['requires_approval'])
    return result


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--hosted',action='store_true',required=True);parser.add_argument('--apply',action='store_true',required=True);parser.parse_args()
    from resident2x_acceptance import hosted_admin
    connect,_=hosted_admin()
    print(json.dumps({'prepared':prepare(connect),'provider_effects':False,'A017':'RETIRED_UNTOUCHED'}))
