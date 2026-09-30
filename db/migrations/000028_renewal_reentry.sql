-- Permit only enrollment maintenance to reach hash-verified renewal after expiry.
-- Business work retains the existing ecos.2x.execute requirement unchanged.
set local role ecos_owner;
alter function ecos_meta.require_domain(uuid,text) rename to require_domain_before_renewal_reentry;
create function ecos_meta.require_domain(principal uuid,operation text) returns void
language plpgsql set search_path=pg_catalog as $$
begin
 if operation in ('executor.register','executor.heartbeat') and exists(
   select 1 from ecos_meta.principal_domain b
   join ecos.executor_instance i on i.principal_id=b.principal_id
   join ecos.executor e on e.id=i.executor_id and e.enabled
   join ecos.executor_capability c on c.executor_instance_id=i.id and c.capability_name='ecos.2x.execute' and c.capability_version>=1
   join ecos_meta.capability_renewal_policy p on p.capability_id=c.id and p.attested_by=c.attested_by and p.enabled
   where b.principal_id=principal and b.executor_generation='2X'
     and i.id=(ecos_meta.current_principal()).executor_instance_id
 ) then
  -- Preserve production domain ownership, generation and authority epoch gates.
  perform ecos_meta.require_domain_epoch23(principal,operation);
  return;
 end if;
 perform ecos_meta.require_domain_before_renewal_reentry(principal,operation);
end $$;
revoke all on function ecos_meta.require_domain(uuid,text),ecos_meta.require_domain_before_renewal_reentry(uuid,text) from public,executor,operations_api,provider_adapter;
reset role;
