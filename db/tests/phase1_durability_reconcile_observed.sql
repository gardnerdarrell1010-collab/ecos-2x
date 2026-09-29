begin;
set local timezone='UTC';
do $$
declare p uuid; cmd uuid:='42044aab-ddf0-4a8b-8de4-e86f61509c03'; attempt_ uuid:='2c86d727-44c0-44b4-8fc8-ae0227347a04'; r jsonb; original jsonb; result_ jsonb; req jsonb; item_ jsonb;
begin
 select principal_id into strict p from ecos_meta.operation_audit where correlation_id='81321a94-7132-40d8-8cb8-68cbfd10cdee';
 if exists(select 1 from ecos_meta.principal_binding where role_name='provider_adapter') then raise exception 'Provider role already in use'; end if;
 insert into ecos_meta.principal_binding values('provider_adapter',p,null,true); execute format('grant provider_adapter to %I',current_user);
 perform set_config('role','provider_adapter',true);
 begin perform ecos.begin_synthetic_attempt(cmd,repeat('a',64)); raise exception 'Unknown command resent'; exception when check_violation then null; end;
 if ecos.claim_outbox(120) is not null then raise exception 'Unknown provider command dispatched'; end if;
 result_:=jsonb_build_object('id',gen_random_uuid(),'schema_version','1.0.0','created_at',clock_timestamp(),'provider_command_id',cmd,'provider_attempt_id',attempt_,'outcome','reconciled','provider_object_id','SYNTHETIC-NO-EXTERNAL-CALL','observed_at',clock_timestamp(),'evidence_hash',repeat('b',64),'reconciled_outcome','succeeded');
 req:=jsonb_build_object('schema_version','1.0.0','context',jsonb_build_object('principal_id',p,'executor_instance_id',null,'correlation_id','81321a94-7132-40d8-8cb8-68cbfd10cdee','causation_id',null,'idempotency_key','synthetic-reconcile-after-crash'),'arguments',jsonb_build_object('result',result_));
 r:=ecos.operate('provider.result.record',req); if r->>'status'<>'committed' then raise exception 'Reconciliation failed: %',r; end if; original:=r;
 r:=ecos.operate('provider.result.record',req); if r<>original then raise exception 'Replay differed'; end if;
 item_:=ecos.claim_outbox(120); if item_->'item'->>'provider_command_id'<>cmd::text then raise exception 'ACK recovery absent'; end if;
 perform ecos.ack_outbox((item_->'item'->>'id')::uuid,(item_->>'lease_token')::uuid);
 if ecos.claim_outbox(120) is not null then raise exception 'Logical duplicate redelivery'; end if;
 perform set_config('role','postgres',true);
 execute format('revoke provider_adapter from %I',current_user); delete from ecos_meta.principal_binding where role_name='provider_adapter' and principal_id=p;
end $$;
commit;
select c.outcome,(select count(*) from ecos.provider_attempt where provider_command_id=c.id) attempts,(select count(*) from ecos.provider_result where provider_command_id=c.id) results,(select count(*) from ecos.delivery_attempt da join ecos.delivery d on d.id=da.delivery_id where d.provider_command_id=c.id) delivery_attempts,(select jsonb_agg(jsonb_build_object('id',o.id,'state',o.state,'attempt_count',o.attempt_count) order by o.id) from ecos.outbox_item o where o.domain_event_id=c.causation_id) outbox from ecos.provider_command c where c.id='42044aab-ddf0-4a8b-8de4-e86f61509c03';
