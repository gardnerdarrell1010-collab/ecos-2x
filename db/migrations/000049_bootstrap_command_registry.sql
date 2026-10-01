-- Bring the already-existing operational Command Registry into canonical schema
-- history, and return its current active versions through the existing bootstrap.
create table if not exists ecos.command_registry (
 command_id uuid primary key default gen_random_uuid(),
 command text not null unique,
 business_outcome text not null,
 ai_interpretation text not null,
 active boolean not null default true,
 source_system text not null,
 source_reference text,
 source_row integer,
 record_version integer not null default 1 check(record_version>=1),
 created_at timestamptz not null default now(),
 updated_at timestamptz not null default now()
);
grant select on ecos.command_registry to ecos_owner;
set local role ecos_owner;
update ecos_meta.contract_schema set document=jsonb_set(document,'{properties}',document->'properties'||
 '{"command_registry":{"type":"array","items":{"type":"object","properties":{"command_id":{"type":"string","format":"uuid"},"command":{"type":"string"},"business_outcome":{"type":"string"},"ai_interpretation":{"type":"string"},"record_version":{"type":"integer","minimum":1}},"required":["command_id","command","business_outcome","ai_interpretation","record_version"],"additionalProperties":false},"minItems":0,"uniqueItems":false}}'::jsonb)
 where schema_id='https://contracts.ecos.invalid/v1/bootstrap_package.schema.json';
alter function ecos.bootstrap_package() rename to bootstrap_package_before_command_registry;
create function ecos.bootstrap_package() returns jsonb language plpgsql security definer
set search_path=pg_catalog set timezone='UTC' as $$
declare result_ jsonb; registry_ jsonb;
begin
 -- Existing bootstrap performs the identity, scope and operation checks.
 result_:=ecos.bootstrap_package_before_command_registry();
 select coalesce(jsonb_agg(jsonb_build_object('command_id',command_id,'command',command,
  'business_outcome',business_outcome,'ai_interpretation',ai_interpretation,
  'record_version',record_version) order by command),'[]'::jsonb) into registry_
 from ecos.command_registry where active;
 result_:=(result_-'content_hash')||jsonb_build_object('command_registry',registry_);
 result_:=result_||jsonb_build_object('content_hash',ecos_meta.content_hash(result_));
 perform ecos_meta.assert_contract('bootstrap_package',result_);
 return result_;
end $$;
revoke all on function ecos.bootstrap_package() from public;
grant execute on function ecos.bootstrap_package() to executor,operations_api;
reset role;
