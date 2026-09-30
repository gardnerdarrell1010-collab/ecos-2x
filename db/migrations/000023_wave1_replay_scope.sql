-- Recheck Wave 1 object grants and mode isolation before cached operation replay.
set local role ecos_owner;
alter function ecos_meta.require_operation_scope(text,jsonb,uuid) rename to require_operation_scope_domain;
create function ecos_meta.require_operation_scope(op text,args jsonb,principal uuid) returns void
language plpgsql stable set search_path=pg_catalog as $$
declare occurrence_ uuid; task_ uuid; b ecos_meta.principal_domain; prior ecos.toast_batch;
begin
 perform ecos_meta.require_operation_scope_domain(op,args,principal);
 if op='toast.batch.commit' then
  occurrence_:=(args->'fence'->>'occurrence_id')::uuid;
  perform ecos_meta.require_access(principal,'work_occurrence',occurrence_);
  select task_id into task_ from ecos.work_occurrence where id=occurrence_;
  perform ecos_meta.require_access(principal,'task',task_);
  select * into b from ecos_meta.principal_domain where principal_id=principal;
  select * into prior from ecos.toast_batch where occurrence_id=occurrence_;
  if prior.id is not null and (prior.domain<>b.domain or prior.execution_mode<>b.execution_mode) then
   raise exception 'forbidden' using errcode='42501';
  end if;
 end if;
end $$;
create trigger immutable before update or delete on ecos.toast_batch for each row execute function ecos_meta.forbid_evidence_change();
create trigger immutable before update or delete on ecos_meta.domain_authority_event for each row execute function ecos_meta.forbid_evidence_change();
revoke all on all functions in schema ecos_meta from public;
reset role;
