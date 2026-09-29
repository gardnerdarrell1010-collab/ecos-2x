begin;
do $$
declare p uuid; item_ jsonb; attempt_ uuid;
begin
 select a.principal_id into strict p from ecos_meta.operation_audit a join ecos.domain_event e on a.correlation_id=e.correlation_id join ecos.task t on t.id=e.aggregate_id where t.business_id='SYNTHETIC-PHASE1-DURABILITY-20260929';
 if exists(select 1 from ecos_meta.principal_binding where role_name='provider_adapter') then raise exception 'Provider role already in use'; end if;
 insert into ecos_meta.principal_binding values('provider_adapter',p,null,true); execute format('grant provider_adapter to %I',current_user);
 perform set_config('role','provider_adapter',true); item_:=ecos.claim_outbox(120);
 if item_->'item'->>'id'<>'cb37a924-9dd3-4493-8255-fb1876573911' then raise exception 'Unexpected fixture item'; end if;
 begin perform ecos.ack_outbox((item_->'item'->>'id')::uuid,'e81de5ce-230f-4737-9ff3-9cc59b1032f5'); raise exception 'Expired token accepted'; exception when serialization_failure then null; end;
 perform ecos.ack_outbox((item_->'item'->>'id')::uuid,(item_->>'lease_token')::uuid);
 attempt_:=ecos.begin_synthetic_attempt('42044aab-ddf0-4a8b-8de4-e86f61509c03',repeat('a',64));
 perform set_config('role','postgres',true);
 perform set_config('ecos.durability_ack',jsonb_build_object('acknowledged_domain_outbox',item_->'item'->'id','attempt_id',attempt_,'simulated_consumer_exit_before_result',true)::text,true);
 execute format('revoke provider_adapter from %I',current_user); delete from ecos_meta.principal_binding where role_name='provider_adapter' and principal_id=p;
end $$;
select current_setting('ecos.durability_ack')::jsonb evidence;
commit;
