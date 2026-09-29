-- Deliberately retained synthetic evidence for cross-transaction crash recovery.
begin;
set local timezone='UTC';
do $$
declare p uuid:=gen_random_uuid(); t uuid:=gen_random_uuid(); recipient uuid:=gen_random_uuid(); req jsonb; result_ jsonb;
begin
 if exists(select 1 from ecos.task where business_id='SYNTHETIC-PHASE1-DURABILITY-20260929') or exists(select 1 from ecos_meta.principal_binding where role_name in ('operations_api','provider_adapter')) then raise exception 'Fixture already exists or role in use; inspect rather than overwrite'; end if;
 insert into ecos.task(id,business_id,title,project_id,lifecycle_state,wait_reason,description) values(t,'SYNTHETIC-PHASE1-DURABILITY-20260929','Synthetic Phase 1 committed outbox',null,'open','none','Retained synthetic failure-injection evidence. No provider transport authorized.');
 insert into ecos.party values(recipient,'SYNTHETIC-DURABILITY-RECIPIENT','Synthetic non-routable recipient',1);
 insert into ecos_meta.notification_policy values(t,recipient,'sms','synthetic:never-send','synthetic:committed-fixture',repeat('a',64),'synthetic-durability');
 insert into ecos_meta.principal_binding values('operations_api',p,null,true);
 insert into ecos_meta.principal_operation values(p,'task.transition'),(p,'provider.result.record');
 insert into ecos_meta.object_grant values(p,'task',t);
 req:=jsonb_build_object('schema_version','1.0.0','context',jsonb_build_object('principal_id',p,'executor_instance_id',null,'correlation_id',gen_random_uuid(),'causation_id',null,'idempotency_key','synthetic-committed-durability'),'arguments',jsonb_build_object('task_id',t,'expected_version',1,'target_state','waiting','wait_reason','owner','reason_code','synthetic_durability','evidence','[]'::jsonb));
 execute format('grant operations_api to %I',current_user);
 perform set_config('role','operations_api',true); result_:=ecos.operate('task.transition',req); perform set_config('role','postgres',true);
 if result_->>'status'<>'committed' then raise exception 'Durability operation failed: %',result_; end if;
 execute format('revoke operations_api from %I',current_user);
 insert into ecos_meta.object_grant select p,'provider_command',c.id from ecos.provider_command c join ecos.domain_event e on e.id=c.causation_id where e.aggregate_id=t;
 delete from ecos_meta.principal_binding where role_name='operations_api' and principal_id=p;
end $$;
commit;
select t.id task_id,e.id domain_event_id,c.id provider_command_id,o.id provider_outbox_id,o.state,a.principal_id,a.correlation_id from ecos.task t join ecos.domain_event e on e.aggregate_id=t.id join ecos.provider_command c on c.causation_id=e.id join ecos.outbox_item o on o.provider_command_id=c.id join ecos_meta.operation_audit a on a.correlation_id=e.correlation_id where t.business_id='SYNTHETIC-PHASE1-DURABILITY-20260929';
