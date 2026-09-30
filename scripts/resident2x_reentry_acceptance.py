"""Rollback-only acceptance through authenticated ecos.operate, never private-helper acceptance alone."""
import sys,json
from pathlib import Path
from uuid import uuid4
ROOT=Path(__file__).resolve().parents[1];sys.dont_write_bytecode=True;sys.path[:0]=[str(ROOT),str(ROOT/'src')]
from scripts.resident2x_acceptance import hosted_admin
from psycopg import sql
from psycopg.types.json import Jsonb

def main():
    connect,_=hosted_admin()
    executor,instance,principal,cap=[str(uuid4()) for _ in range(4)]
    role='synthetic_renewal_'+uuid4().hex[:12];evidence='a'*64
    with connect() as db:
        db.execute('set local statement_timeout=20000')
        if not db.execute("select to_regprocedure('ecos_meta.require_domain_before_renewal_reentry(uuid,text)') is not null").fetchone()[0]:
            db.execute((ROOT/'db/migrations/000028_renewal_reentry.sql').read_text(),prepare=False)
        db.execute(sql.SQL('create role {} nologin inherit').format(sql.Identifier(role)))
        db.execute(sql.SQL('grant executor,operations_api to {}').format(sql.Identifier(role)))
        db.execute(sql.SQL('grant {} to postgres').format(sql.Identifier(role)))
        db.execute("insert into ecos.executor(id,name,surface,enabled) values(%s,'synthetic-renewal-boundary','RESIDENT_DETERMINISTIC_PROVIDER',true)",(executor,))
        db.execute("insert into ecos.executor_instance(id,executor_id,boot_id,availability,principal_id) values(%s,%s,%s,'available',%s)",(instance,executor,str(uuid4()),principal))
        db.execute('insert into ecos_meta.principal_binding values(%s,%s,%s,true)',(role,principal,instance))
        db.execute("insert into ecos_meta.principal_domain(principal_id,domain,execution_mode,authority_epoch) values(%s,'synthetic.acceptance','synthetic',1)",(principal,))
        for operation in ['executor.heartbeat','work.next']:
            db.execute('insert into ecos_meta.principal_operation values(%s,%s)',(principal,operation))
        db.execute("insert into ecos.executor_presence(executor_instance_id,host,runtime,software_version,status,evidence_hash) values(%s,'synthetic','synthetic','test','available',%s)",(instance,evidence))
        db.execute("insert into ecos.executor_capability(id,executor_instance_id,capability_name,capability_version,attested_by,expires_at) values(%s,%s,'ecos.2x.execute',1,%s,clock_timestamp()-interval '1 second')",(cap,instance,principal))
        db.execute("insert into ecos_meta.capability_renewal_policy values(%s,%s,%s,60,30,true,'synthetic rollback acceptance',default)",(cap,principal,evidence))
        def call(operation,wrong_hash=False):
            context={'principal_id':principal,'executor_instance_id':instance,'correlation_id':str(uuid4()),'causation_id':None,'idempotency_key':str(uuid4())}
            args={'executor_instance_id':instance,'lease_seconds':30} if operation=='work.next' else {'observed_at':db.execute('select clock_timestamp()').fetchone()[0].isoformat(),'evidence_hash':('b'*64 if wrong_hash else evidence),'reported_running':0,'load_basis_points':0}
            request={'schema_version':'1.0.0','context':context,'arguments':args}
            db.execute(sql.SQL('set local role {}').format(sql.Identifier(role)))
            response=db.execute('select ecos.operate(%s,%s)',(operation,Jsonb(request))).fetchone()[0]
            db.execute('reset role');return response
        assert call('work.next').get('code')=='gate_blocked'
        assert call('executor.heartbeat',True)['data']['capabilities_renewed']==0
        assert call('work.next').get('code')=='gate_blocked'
        assert call('executor.heartbeat')['data']['capabilities_renewed']==1
        assert call('work.next')['status']=='NO_ELIGIBLE_WORK'
        db.execute('update ecos_meta.capability_renewal_policy set enabled=false where capability_id=%s',(cap,))
        db.execute("update ecos.executor_capability set expires_at=clock_timestamp()-interval '1 second',record_version=record_version+1 where id=%s",(cap,))
        assert call('executor.heartbeat').get('code')=='gate_blocked'
        db.rollback()
    with connect() as db:assert not db.execute('select exists(select 1 from ecos.executor where id=%s)',(executor,)).fetchone()[0]
    print(json.dumps({'authenticated_operation_boundary':'PASS','expired_work_rejected':'PASS','expired_heartbeat_renewal':'PASS','eligible_after_renewal':'PASS','wrong_hash_stays_ineligible':'PASS','revoked_enrollment_rejected':'PASS','rollback':'PASS'}))

if __name__ == "__main__":
    main()
