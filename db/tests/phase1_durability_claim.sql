-- Separate transaction: claim committed work, then simulate consumer exit without acknowledgement.
begin;
do $$
declare p uuid; item_ jsonb;
begin
 select a.principal_id into strict p from ecos_meta.operation_audit a join ecos.domain_event e on a.correlation_id=e.correlation_id join ecos.task t on t.id=e.aggregate_id where t.business_id='SYNTHETIC-PHASE1-DURABILITY-20260929';
 if exists(select 1 from ecos_meta.principal_binding where role_name='provider_adapter') then raise exception 'Provider role already in use'; end if;
 insert into ecos_meta.principal_binding values('provider_adapter',p,null,true); execute format('grant provider_adapter to %I',current_user);
 perform set_config('role','provider_adapter',true); item_:=ecos.claim_outbox(1); perform set_config('role','postgres',true);
 if item_ is null then raise exception 'Committed outbox not discoverable'; end if;
 perform set_config('ecos.durability_claim',item_::text,true);
 execute format('revoke provider_adapter from %I',current_user); delete from ecos_meta.principal_binding where role_name='provider_adapter' and principal_id=p;
end $$;
select current_setting('ecos.durability_claim')::jsonb claimed;
commit;
