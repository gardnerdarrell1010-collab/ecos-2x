-- Unbound work routes through canonical capabilities, not a worker-name allowlist.
-- Preserve explicit domain records and the existing object grants and claim fences.
set local role ecos_owner;
alter function ecos_meta.selection(uuid,uuid,timestamptz) rename to selection_before_capability_routing;
create function ecos_meta.selection(occurrence uuid,instance uuid,at_ timestamptz)
returns jsonb language plpgsql stable set search_path=pg_catalog as $$
begin
 if not exists(select 1 from ecos_meta.object_domain where record_type='work_occurrence' and record_id=occurrence) then
  return ecos_meta.selection_phase2(occurrence,instance,at_);
 end if;
 return ecos_meta.selection_before_capability_routing(occurrence,instance,at_);
end $$;
alter function ecos_meta.require_access(uuid,text,uuid) rename to require_access_before_capability_routing;
create function ecos_meta.require_access(principal uuid,kind text,entity uuid)
returns void language plpgsql stable set search_path=pg_catalog as $$
begin
 if kind='work_occurrence' and not exists(select 1 from ecos_meta.object_domain where record_type=kind and record_id=entity) then
  perform ecos_meta.require_access_phase2(principal,kind,entity); return;
 end if;
 perform ecos_meta.require_access_before_capability_routing(principal,kind,entity);
end $$;
revoke all on function ecos_meta.selection(uuid,uuid,timestamptz),ecos_meta.require_access(uuid,text,uuid) from public;
reset role;
