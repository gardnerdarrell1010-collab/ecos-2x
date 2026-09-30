"""Actual disposable SQL tests; callbacks are synthetic provider stand-ins."""
from uuid import uuid4
from psycopg.types.json import Jsonb


def checks(target, Fixture):
    f=Fixture(target);f.seed();passed=[]
    def admin(q,args=()):
        with target.connect() as db:
            c=db.execute(q,args);return c.fetchall() if c.description else []
    def call(q,args=()):
        with target.connect() as db:
            db.execute('set local role provider_adapter')
            return db.execute(q,args).fetchone()[0]
    def denied(callback):
        try:callback()
        except Exception as exc:
            assert exc.sqlstate in ('23514','42501','P0001'),str(exc)
        else:raise AssertionError('unsafe effect admitted')
    def begin(epoch,key=None,target_='toast.compatibility'):
        return call('select ecos.domain_effect_begin(%s,%s,%s,%s)',(target_,epoch,key or str(uuid4()),'a'*64))
    def finish(reservation,epoch):
        call('select ecos.domain_effect_finish(%s,%s,%s)',(reservation['command_id'],epoch,'b'*64))
    def transfer(owner):
        admin("update ecos_meta.domain_authority set owner=%s,epoch=epoch+1,evidence=%s where domain='toast.acquisition'",
              (owner,'Synthetic authority effect test '+str(uuid4())))
        return admin("select epoch from ecos_meta.domain_authority where domain='toast.acquisition'")[0][0]
    def bind(generation,epoch,domain='toast.acquisition',mode='production'):
        admin('update ecos_meta.principal_domain set domain=%s,execution_mode=%s,authority_epoch=%s,executor_generation=%s where principal_id=%s',
              (domain,mode,epoch,generation,f.p))
    def op(name,args):
        with target.connect() as db:
            db.execute('set local role executor')
            return db.execute('select ecos.operate(%s,%s)',(name,Jsonb(f.request(args)))).fetchone()[0]
    try:
        admin('grant provider_adapter to postgres')
        admin("insert into ecos_meta.principal_binding values('provider_adapter',%s,%s,true)",(f.p,f.inst))
        admin("insert into ecos_meta.domain_effect_scope values(%s,'toast.compatibility'),(%s,'toast.dashboard')",(f.p,f.p))
        epoch=admin("select epoch from ecos_meta.domain_authority where domain='toast.acquisition'")[0][0]
        bind('1X',epoch)
        grant=call("select ecos.domain_effect_grant('toast.compatibility')")
        assert grant['epoch']==epoch and grant['generation']=='1X'
        first=begin(epoch);finish(first,epoch);passed.append('current_1x_effect_authorized')
        pending=begin(epoch)
        denied(lambda:transfer('2X'));passed.append('unresolved_effect_blocks_transfer_after_connection_closes')
        denied(lambda:begin(epoch,'wrong-target','other.domain'));passed.append('ungranted_target_denied')
        finish(pending,epoch)
        new_epoch=transfer('2X')
        denied(lambda:begin(epoch));passed.append('stale_1x_drive_publication_denied_before_callback')
        denied(lambda:begin(epoch,target_='toast.dashboard'));passed.append('stale_1x_registry_snapshot_denied')
        assert op('work.next',{'executor_instance_id':f.inst,'lease_seconds':30})['code']=='forbidden'
        passed.append('1x_generation_cannot_claim_sql')
        bind('2X',new_epoch,mode='shadow')
        denied(lambda:begin(new_epoch));passed.append('shadow_cannot_publish_authoritative_output')
        bind('2X',new_epoch)
        key=str(uuid4());r=begin(new_epoch,key);finish(r,new_epoch)
        assert begin(new_epoch,key)['already_completed'];passed.append('current_2x_effect_and_idempotent_replay')
        rollback_epoch=transfer('1X')
        denied(lambda:begin(new_epoch,key));passed.append('stale_2x_replay_denied_after_rollback')
        denied(lambda:begin(new_epoch));passed.append('stale_2x_new_effect_denied_after_rollback')
        bind('1X',rollback_epoch)
        r=begin(rollback_epoch);finish(r,rollback_epoch);passed.append('rollback_1x_requires_new_epoch')
        bind('1X',1,'staffing.features')
        denied(lambda:begin(1));passed.append('wrong_domain_even_with_target_scope_denied')
        final_epoch=transfer('2X');bind('2X',final_epoch)
        admin("update ecos.executor set surface='RESIDENT_DETERMINISTIC_PROVIDER',record_version=record_version+1 where id=%s",(f.ex,))
        admin("update ecos.work_stage_definition set execution_surface='RESIDENT_DETERMINISTIC_PROVIDER',record_version=record_version+1 where id=%s",(f.stage,))
        args={'executor_instance_id':f.inst,'lease_seconds':30}
        assert op('work.next',args)['code']=='gate_blocked';passed.append('resident_2x_missing_generation_capability_denied')
        admin("update ecos.executor set surface='ONLINE_SEMANTIC',record_version=record_version+1 where id=%s",(f.ex,))
        assert op('work.next',args)['code']=='gate_blocked';passed.append('online_missing_generation_capability_denied')
        admin("update ecos.executor set surface='RESIDENT_DETERMINISTIC_PROVIDER',record_version=record_version+1 where id=%s",(f.ex,))
        admin("insert into ecos.executor_capability(executor_instance_id,capability_name,capability_version,attested_by,expires_at) values(%s,'ecos.2x.execute',1,%s,clock_timestamp()+interval '1 hour')",(f.inst,f.p))
        assert 'code' not in op('executor.register',{'host':'synthetic','runtime':'synthetic','software_version':'1','evidence_hash':'a'*64})
        work=f.add_work(1)[0]
        for kind,identity in [('task',f.task),('work_occurrence',work)]:
            admin("insert into ecos_meta.object_domain values(%s,%s,'toast.acquisition')",(kind,identity))
        admin("insert into ecos.work_context(occurrence_id,operation,input) values(%s,'work.complete','{}')",(work,))
        claimed=op('work.next',args);assert claimed['status']=='CLAIMED',claimed
        assert op('work.complete',f.result_arguments(claimed['data']))['status']=='committed'
        passed.append('compatible_resident_2x_claim_and_completion')
        transfer('1X')
        assert op('work.complete',f.result_arguments(claimed['data']))['code']=='gate_blocked'
        passed.append('old_sql_completion_rejected_after_epoch_advance')
    finally:
        admin("delete from ecos_meta.principal_binding where role_name='provider_adapter'")
        admin('revoke provider_adapter from postgres')
        f.cleanup()
    return passed
