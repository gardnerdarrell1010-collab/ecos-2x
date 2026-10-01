-- Owner correction: remove the separate instruction publication surface.
-- Preserve normalized immutable storage, claim pins, receipts and work.package.
set local role ecos_owner;
-- Administrative configuration records the actual database actor, not a fabricated executor.
alter table ecos.work_instruction_version add column configured_by_role name;
alter table ecos.work_instruction_version alter column published_by drop not null;
alter table ecos.work_instruction_version add constraint instruction_actor_present
 check(published_by is not null or configured_by_role is not null);
create unique index instruction_configuration_replay on ecos.work_instruction_version(stage_definition_id,correlation_id);
delete from ecos_meta.principal_operation where operation='work.instruction.publish';
delete from ecos_meta.operation_contract where name='work.instruction.publish';
create or replace function ecos_meta.apply_operation(op text,ctx jsonb,args jsonb) returns jsonb
language plpgsql set search_path=pg_catalog as $$
begin
 if op='work.instruction.publish' then raise exception 'operation_removed' using errcode='42501'; end if;
 return ecos_meta.apply_operation_before_instructions(op,ctx,args);
end $$;
create or replace function ecos_meta.require_operation_scope(op text,args jsonb,principal uuid) returns void
language plpgsql stable set search_path=pg_catalog as $$
begin
 perform ecos_meta.require_operation_scope_before_instructions(op,args,principal);
end $$;
revoke all on all functions in schema ecos_meta from public;
reset role;
