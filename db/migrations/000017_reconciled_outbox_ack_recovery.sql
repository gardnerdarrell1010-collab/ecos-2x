-- Reconciled/succeeded commands may reacquire transport leases for ACK only.
-- begin_synthetic_attempt still rejects non-pending commands, preventing resends.
set local role ecos_owner;
create or replace function ecos.claim_outbox(lease_seconds integer default 30) returns jsonb language plpgsql security definer set search_path=pg_catalog as $$
declare p ecos_meta.principal_binding; o ecos.outbox_item; tok uuid:=gen_random_uuid();
begin p:=ecos_meta.current_principal();
 if lease_seconds not between 1 and 300 then raise exception 'invalid_contract'; end if;
 if not exists(select 1 from ecos_meta.principal_operation where principal_id=p.principal_id and operation='provider.result.record') then raise exception 'forbidden' using errcode='42501'; end if;
 perform 1 from ecos_meta.control for share; if exists(select 1 from ecos_meta.control where maintenance) then return null; end if;
 select b.* into o from ecos.outbox_item b where b.available_at<=clock_timestamp() and (b.state in ('pending','retry_wait') or (b.state='claimed' and b.lease_expires_at<=clock_timestamp()))
 and ((b.provider_command_id is null and exists(select 1 from ecos.domain_event e join ecos_meta.object_grant g on g.record_type=e.aggregate_type and g.record_id=e.aggregate_id and g.principal_id=p.principal_id where e.id=b.domain_event_id)) or exists(select 1 from ecos_meta.object_grant where principal_id=p.principal_id and record_type='provider_command' and record_id=b.provider_command_id))
 and not exists(select 1 from ecos.provider_command c where c.id=b.provider_command_id and not (c.outcome in ('pending','succeeded') or (c.outcome='reconciled' and exists(select 1 from ecos.provider_result pr where pr.provider_command_id=c.id and pr.reconciled_outcome='succeeded'))))
 order by b.available_at,b.id for update skip locked limit 1;
 if o.id is null then return null; end if;
 update ecos.outbox_item set state='claimed',lease_expires_at=clock_timestamp()+make_interval(secs=>lease_seconds),attempt_count=attempt_count+1,record_version=record_version+1 where id=o.id returning * into o;
 insert into ecos_meta.outbox_lease values(o.id,tok,p.principal_id) on conflict(item_id) do update set token=excluded.token,principal_id=excluded.principal_id;
 return jsonb_build_object('item',to_jsonb(o),'lease_token',tok);
end $$;

reset role;
