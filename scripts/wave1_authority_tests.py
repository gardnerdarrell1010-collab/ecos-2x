"""Explicit SQL authority tests against disposable fixtures only."""
from psycopg.types.json import Jsonb

def checks(target,Fixture):
    f=Fixture(target);f.seed();passed=[]
    def admin(sql,args=()):
        with target.connect() as db:
            c=db.execute(sql,args);return c.fetchall() if c.description else []
    def op(name,args,request=None):
        with target.connect() as db:
            db.execute('set local role executor')
            return db.execute('select ecos.operate(%s,%s)',(name,Jsonb(request or f.request(args)))).fetchone()[0]
    register={'host':'SYNTHETIC-AUTHORITY','runtime':'authority-fixture','software_version':'1','evidence_hash':'a'*64}
    try:
        original=op('executor.register',register);assert 'code' not in original, original
        admin("update ecos_meta.principal_domain set domain='toast.acquisition',execution_mode='production' where principal_id=%s",(f.p,))
        assert op('executor.register',register)['code']=='gate_blocked';passed.append('1x_owned_domain_denies_2x_production')
        admin("update ecos_meta.principal_domain set execution_mode='shadow' where principal_id=%s",(f.p,))
        request=f.request(register)
        assert 'code' not in op('executor.register',register,request)
        assert op('fact.record',{'subject_id':f.task,'statement':'blocked shadow mutation','source_references':[{'record_type':'task','record_id':f.task,'record_version':1,'content_hash':'a'*64,'authority':'structured_ecos'}],'sensitivity':'internal'})['code']=='forbidden'
        passed.append('shadow_general_business_mutation_denied')
        work=f.add_work(1)[0]
        assert op('work.next',{'executor_instance_id':f.inst,'lease_seconds':30})['status']=='NO_ELIGIBLE_WORK'
        passed.append('unmapped_work_denied')
        for kind,identity in [('work_occurrence',work),('task',f.task)]:
            admin("insert into ecos_meta.object_domain values(%s,%s,'toast.acquisition')",(kind,identity))
        admin("insert into ecos.work_context(occurrence_id,operation,input) values(%s,'work.complete','{}')",(work,))
        claim=op('work.next',{'executor_instance_id':f.inst,'lease_seconds':30})
        assert claim['status']=='CLAIMED';passed.append('scoped_shadow_claim_allowed')
        admin("update ecos_meta.principal_domain set execution_mode='production' where principal_id=%s",(f.p,))
        assert op('executor.register',register,request)['code']=='gate_blocked'
        assert op('work.complete',f.result_arguments(claim['data']))['code']=='gate_blocked'
        passed.append('domain_authority_rechecked_before_replay_and_completion')
        try:
            admin("update ecos_meta.domain_authority set owner='2X',epoch=epoch+1,evidence='Synthetic attempt with a live domain claim must be rejected' where domain='toast.acquisition'")
        except Exception as exc:assert exc.sqlstate=='23514'
        else:raise AssertionError('domain transferred with live claim')
        passed.append('transfer_requires_domain_claim_drain')
        admin("update ecos_meta.principal_domain set execution_mode='shadow' where principal_id=%s",(f.p,))
        assert op('work.complete',f.result_arguments(claim['data']))['status']=='committed'
        admin("update ecos_meta.principal_domain set execution_mode='production' where principal_id=%s",(f.p,))
        admin("update ecos_meta.domain_authority set owner='2X',epoch=epoch+1,evidence='Synthetic local acceptance old path drained proof only' where domain='toast.acquisition'")
        assert op('executor.register',register)['code']=='gate_blocked';passed.append('old_epoch_rejected_after_transfer')
        admin("update ecos_meta.principal_domain set authority_epoch=2 where principal_id=%s",(f.p,))
        assert 'code' not in op('executor.register',register)
        admin("update ecos_meta.object_domain set domain='staffing.features' where record_type='task' and record_id=%s",(f.task,))
        assert op('fact.record',{'subject_id':f.task,'statement':'cross-domain','source_references':[{'record_type':'task','record_id':f.task,'record_version':1,'content_hash':'a'*64,'authority':'structured_ecos'}],'sensitivity':'internal'})['code']=='forbidden'
        passed.append('cross_domain_object_mutation_denied')
        with target.connect() as db:
            db.execute('set local role executor')
            try:db.execute("update ecos_meta.domain_authority set owner='2X'")
            except Exception as exc:assert exc.sqlstate=='42501'
            else:raise AssertionError('executor changed domain authority')
        passed.append('executor_cannot_change_authority')
        admin("update ecos_meta.domain_authority set owner='1X',epoch=epoch+1,evidence='Synthetic rollback proof: new owner drained before reversal' where domain='toast.acquisition'")
        assert op('executor.register',register)['code']=='gate_blocked';passed.append('rollback_epoch_fences_old_owner')
        assert len(admin("select * from ecos_meta.domain_authority_event where domain='toast.acquisition'"))==2
        passed.append('transfer_and_rollback_audited')
    finally:
        f.cleanup()
    return passed
