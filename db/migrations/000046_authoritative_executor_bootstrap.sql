-- Extend the existing bootstrap; canonical capability catalog remains unchanged.
set local role ecos_owner;
update ecos_meta.contract_schema set document=jsonb_set(document,'{properties}',document->'properties'||$props${"operational_authority":{"const":"POSTGRESQL_ECOS_2X"},"executor_context":{"type":"object","properties":{"identity":{"type":"string","minLength":1,"maxLength":10000},"executor_id":{"type":"string","format":"uuid"},"executor_name":{"type":"string","minLength":1,"maxLength":10000},"executor_instance_id":{"type":"string","format":"uuid"},"principal_id":{"type":"string","format":"uuid"},"surface":{"type":"string","minLength":1,"maxLength":10000},"enabled":{"type":"boolean"},"availability":{"type":"string","minLength":1,"maxLength":10000},"observed_at":{"type":"string","format":"date-time"},"capabilities":{"type":"array","items":{"type":"object","properties":{"name":{"type":"string","pattern":"^[a-z][a-z0-9_.-]{0,127}$"},"version":{"type":"integer","minimum":1},"expires_at":{"type":"string","format":"date-time"},"valid":{"type":"boolean"}},"required":["name","version","expires_at","valid"],"additionalProperties":false},"minItems":0,"uniqueItems":false}},"required":["identity","executor_id","executor_name","executor_instance_id","principal_id","surface","enabled","availability","observed_at","capabilities"],"additionalProperties":false}}$props$::jsonb)
 where schema_id='https://contracts.ecos.invalid/v1/bootstrap_package.schema.json';
alter function ecos.bootstrap_package() rename to bootstrap_package_before_executor_context;
create function ecos.bootstrap_package() returns jsonb language plpgsql security definer
set search_path=pg_catalog set timezone='UTC' as $$
declare p ecos_meta.principal_binding; result_ jsonb; context_ jsonb; at_ timestamptz:=clock_timestamp();
begin
 p:=ecos_meta.current_principal();
 result_:=ecos.bootstrap_package_before_executor_context();
 select jsonb_build_object('identity',case e.surface when 'ONLINE_SEMANTIC' then 'ONLINE_ADA_2X'
  when 'RESIDENT_DETERMINISTIC_PROVIDER' then 'RESIDENT_ADA_2X_HOME01'
  when 'INTERACTIVE_ADA' then 'INTERACTIVE_ADA' else 'DATABASE_DETERMINISTIC' end,
  'executor_id',e.id,'executor_name',e.name,'executor_instance_id',i.id,'principal_id',i.principal_id,
  'surface',e.surface,'enabled',e.enabled,'availability',i.availability,'observed_at',at_,
  'capabilities',coalesce((select jsonb_agg(jsonb_build_object('name',c.capability_name,'version',c.capability_version,
    'expires_at',c.expires_at,'valid',c.expires_at>at_) order by c.capability_name,c.capability_version)
   from ecos.executor_capability c join ecos.capability k on k.name=c.capability_name and k.version=c.capability_version
   where c.executor_instance_id=i.id),'[]'::jsonb)) into context_
 from ecos.executor_instance i join ecos.executor e on e.id=i.executor_id
 where i.id=p.executor_instance_id and i.principal_id=p.principal_id;
 if context_ is null then raise exception 'executor_identity_unavailable' using errcode='28000'; end if;
 result_:=(result_-'content_hash')||jsonb_build_object('executor_context',context_,'operational_authority','POSTGRESQL_ECOS_2X');
 result_:=result_||jsonb_build_object('content_hash',ecos_meta.content_hash(result_));
 perform ecos_meta.assert_contract('bootstrap_package',result_);
 return result_;
end $$;
revoke all on function ecos.bootstrap_package() from public;
grant execute on function ecos.bootstrap_package() to executor,operations_api;
reset role;
