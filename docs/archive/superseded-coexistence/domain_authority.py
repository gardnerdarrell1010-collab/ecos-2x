"""1.x provider-boundary adapter; never selects or claims PostgreSQL work."""
import json
import hashlib
from pathlib import Path
from .domain_effects import DomainEffects


def capture(dispatcher, item):
    from .resident_governed import SheetsTable
    settings=SheetsTable(dispatcher.service,dispatcher.spreadsheet_id,'Settings')
    def setting(key):
        found=settings.exact_record({'Setting Key':key,'Active':'TRUE'})
        if found is None:raise ValueError('authority_setting_missing_or_ambiguous')
        return found[1]['Value']
    bindings=json.loads(setting('ECOS_DOMAIN_AUTHORITY_EFFECT_BINDINGS'))
    binding=bindings['workers'][item.task_id]
    reference=Path(setting(binding['connection_reference_setting']))
    config=json.loads(reference.read_text(encoding='utf-8-sig'))
    database=config['database']
    if database.get('sslmode')!='verify-full' or not database.get('sslrootcert'):
        raise ValueError('authority_tls_verification_required')
    def connect():
        import psycopg
        return psycopg.connect(**database,
            password=Path(config['password_file']).read_text(encoding='utf-8-sig').strip(),
            connect_timeout=10,application_name='RESIDENT_ADA_1X_HOME01_AUTHORITY',
            options='-c statement_timeout=15000 -c lock_timeout=5000 -c timezone=UTC')
    effects=DomainEffects(connect)
    grant=effects.capture(binding['target'])
    if grant['generation']!='1X' or grant['domain']!=binding['domain']:
        raise ValueError('authority_generation_or_domain_mismatch')
    return effects,grant


def _readback(dispatcher, item, run_id, outcome):
    if outcome.get('verification_result') != 'PASSED':
        raise ValueError('authority_effect_worker_not_verified')
    from .resident_governed import SheetsTable
    if item.task_id == 'TASK-AUTO-000029':
        from .staffing_history_io import read, SOURCE_NAME
        _, actual = read(dispatcher, SOURCE_NAME)
        expected = outcome['readback_evidence']
        if any(actual[k] != expected[k] for k in ('file_id','sha256','coverage_through')):
            raise ValueError('authority_effect_drive_readback_changed')
        afr = SheetsTable(dispatcher.service,dispatcher.spreadsheet_id,'Authoritative Files').exact_record(
            {'Authoritative File ID':actual['authoritative_file_id']})
        notes=json.loads(afr[1]['Notes'])
        artifact=SheetsTable(dispatcher.service,dispatcher.spreadsheet_id,'Artifacts').exact_record(
            {'Artifact ID':notes['artifact_id']})
        if artifact is None or artifact[1]['Hash / Duplicate Key'] != actual['sha256']:
            raise ValueError('authority_effect_artifact_hash_mismatch')
        return {'verified':True,'file_id':actual['file_id'],'sha256':actual['sha256'],
                'coverage_through':actual['coverage_through'],'run_id':run_id}
    if item.task_id == 'TASK-AUTO-000047':
        evidence=outcome['business_outcome_evidence']
        exact=SheetsTable(dispatcher.service,dispatcher.spreadsheet_id,'Staging Records').exact_record(
            {'Staging ID':evidence['staging_id']})
        if exact is None:
            raise ValueError('authority_effect_snapshot_missing')
        from .producer_snapshots import decode
        body=decode(exact[1],item.task_id)
        if body['run_id'] != run_id or body['occurrence_id'] != dispatcher._occurrence_id(item):
            raise ValueError('authority_effect_snapshot_identity_changed')
        return {'verified':True,'staging_id':evidence['staging_id'],'run_id':run_id,
                'sha256':hashlib.sha256(exact[1]['Raw Payload / Evidence'].encode()).hexdigest()}
    raise ValueError('authority_effect_worker_not_scoped')


def execute(dispatcher, parent_claim, item, run_id, worker):
    """Reserve before execution; unresolved reservations prevent authority transfer.

    This adapter does not consume PostgreSQL work. The existing worker retains
    acquisition, claim checks, output contracts and independent readback.
    """
    effects,grant=capture(dispatcher,item)
    intent={'task':item.task_id,'run':run_id,'occurrence':dispatcher._occurrence_id(item),
            'instructions':item.payload['Instructions']}
    request_hash=hashlib.sha256(json.dumps(intent,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    completed={}
    def effect():
        dispatcher._validate_delegated_claim(**parent_claim)
        completed['outcome']=worker(dispatcher,parent_claim,item,run_id)
    def verify():
        if 'outcome' not in completed:
            raise ValueError('completed_effect_requires_outcome_reconciliation')
        return _readback(dispatcher,item,run_id,completed['outcome'])
    effects.execute(grant,run_id,request_hash,effect,verify)
    return completed['outcome']
