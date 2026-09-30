"""Rollback-only hosted synthetic renewal verification, no production enrollment changes."""
import sys,json
from pathlib import Path
from uuid import uuid4
ROOT=Path(__file__).resolve().parents[1];sys.dont_write_bytecode=True;sys.path[:0]=[str(ROOT),str(ROOT/'src')]
from scripts.resident2x_acceptance import hosted_admin
from psycopg.types.json import Jsonb

def main():
    connect,_=hosted_admin()
    ids=[str(uuid4()) for _ in range(4)]
    executor,instance,principal,cap=ids
    evidence='a'*64
    with connect() as db:
        db.execute('set local statement_timeout=20000')
        installed=db.execute("select to_regclass('ecos_meta.capability_renewal_policy') is not null").fetchone()[0]
        if not installed:db.execute((ROOT/'db/migrations/000027_capability_renewal.sql').read_text(),prepare=False)
        db.execute("insert into ecos.executor(id,name,surface,enabled) values(%s,'synthetic-renewal','RESIDENT_DETERMINISTIC_PROVIDER',true)",(executor,))
        db.execute("insert into ecos.executor_instance(id,executor_id,boot_id,availability,principal_id) values(%s,%s,%s,'available',%s)",(instance,executor,str(uuid4()),principal))
        db.execute("insert into ecos.executor_presence(executor_instance_id,host,runtime,software_version,status,evidence_hash) values(%s,'synthetic','synthetic','test','available',%s)",(instance,evidence))
        db.execute("insert into ecos.executor_capability(id,executor_instance_id,capability_name,capability_version,attested_by,expires_at) values(%s,%s,'ecos.2x.execute',1,%s,clock_timestamp()+interval '1 second')",(cap,instance,principal))
        db.execute("insert into ecos_meta.capability_renewal_policy values(%s,%s,%s,60,30,true,'synthetic rollback acceptance',default)",(cap,principal,evidence))
        ctx={'executor_instance_id':instance,'principal_id':principal}
        def beat(hash_=evidence):
            return db.execute("select ecos_meta.presence_heartbeat(%s,jsonb_build_object('observed_at',clock_timestamp(),'evidence_hash',%s::text,'reported_running',0,'load_basis_points',0))",(Jsonb(ctx),hash_)).fetchone()[0]
        assert beat()['capabilities_renewed']==1
        assert db.execute('select expires_at>clock_timestamp()+interval \'50 seconds\' from ecos.executor_capability where id=%s',(cap,)).fetchone()[0]
        assert beat()['capabilities_renewed']==0
        db.execute("update ecos.executor_capability set expires_at=clock_timestamp()-interval '1 second',record_version=record_version+1 where id=%s",(cap,))
        assert beat('b'*64)['capabilities_renewed']==0
        db.execute('update ecos_meta.capability_renewal_policy set enabled=false where capability_id=%s',(cap,))
        assert beat()['capabilities_renewed']==0
        db.execute('update ecos_meta.capability_renewal_policy set enabled=true where capability_id=%s',(cap,))
        assert beat()['capabilities_renewed']==1
        assert db.execute('select renewal_count from ecos_meta.capability_renewal_receipt where capability_id=%s',(cap,)).fetchone()[0]==2
        assert not db.execute("select has_table_privilege('executor','ecos_meta.capability_renewal_policy','UPDATE')").fetchone()[0]
        assert not db.execute("select has_function_privilege('executor','ecos_meta.presence_heartbeat(jsonb,jsonb)','EXECUTE')").fetchone()[0]
        db.rollback()
    with connect() as db:
        assert db.execute("select to_regclass('ecos_meta.capability_renewal_policy') is not null").fetchone()[0]==installed
        assert not db.execute('select exists(select 1 from ecos.executor where id=%s)',(executor,)).fetchone()[0]
    print(json.dumps({'synthetic_renewal':'PASS','expiry_recovery':'PASS','wrong_hash_denied':'PASS','revocation':'PASS','no_executor_policy_write':'PASS','independent_rollback_verification':'PASS'}))

if __name__ == "__main__":
    main()
