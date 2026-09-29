set local role ecos_owner;
create or replace function ecos.bootstrap_package() returns jsonb language plpgsql security definer set search_path=pg_catalog set timezone='UTC' as $$
declare p ecos_meta.principal_binding; g record; v jsonb; source jsonb; contexts jsonb:='[]'; refs jsonb:='[]'; heads jsonb:='[]'; works jsonb:='[]'; bindings jsonb; bundle jsonb; package jsonb; ceiling_ text;
begin p:=ecos_meta.current_principal(); select ceiling into ceiling_ from ecos_meta.principal_clearance where principal_id=p.principal_id;
 for g in select * from ecos_meta.object_grant where principal_id=p.principal_id order by record_type,record_id loop
  if g.record_type not in ('task','memory_version','work_occurrence') then continue; end if;
  begin perform ecos_meta.require_access(p.principal_id,g.record_type,g.record_id); exception when insufficient_privilege then continue; end;
  v:=ecos_meta.record_value(g.record_type,g.record_id);
  if g.record_type='memory_version' then
   if not exists(select 1 from ecos.memory_record where active_head_version_id=g.record_id) then continue; end if;
   if exists(select 1 from jsonb_array_elements((v->'provenance')||(v->'authoritative_references')) r where not exists(select 1 from ecos_meta.object_grant where principal_id=p.principal_id and record_type=r->>'record_type' and record_id=(r->>'record_id')::uuid)) then continue; end if;
   heads:=heads||jsonb_build_array(v);
  elsif g.record_type='work_occurrence' then works:=works||jsonb_build_array(v); end if;
  source:=jsonb_build_object('record_type',g.record_type,'record_id',g.record_id,'record_version',coalesce((v->>'record_version')::bigint,1),'content_hash',ecos_meta.content_hash(v),'authority',case when g.record_type='memory_version' then 'governed_memory' else 'structured_ecos' end);
  contexts:=contexts||jsonb_build_array(jsonb_build_object('source',source,'record_schema_id','https://contracts.ecos.invalid/v1/'||g.record_type||'.schema.json','record',v)); refs:=refs||jsonb_build_array(source);
 end loop;
 select jsonb_agg(jsonb_build_object('operation',o.name,'path','/v1/operations/'||o.name,'request_schema_id',o.document->>'request_schema','response_schema_id',o.document->>'response_schema') order by o.name) into bindings from ecos_meta.operation_contract o join ecos_meta.principal_operation po on po.operation=o.name and po.principal_id=p.principal_id where ecos_meta.operation_authorized(o.name,p.role_name);
 if bindings is null then raise exception 'forbidden'; end if;
 select jsonb_agg(jsonb_build_object('schema_id',schema_id,'sha256',ecos_meta.content_hash(document),'document',document) order by schema_id) into bundle from ecos_meta.contract_schema;
 package:=jsonb_build_object('package_id',gen_random_uuid(),'schema_version','1.0.0','database_schema_version','1.0.0','generated_at',clock_timestamp(),'principal_id',p.principal_id,'sensitivity_ceiling',coalesce(ceiling_,'internal'),'governed_context',refs,'context_records',contexts,'active_memory_heads',heads,'unresolved_exceptions','[]'::jsonb,'operation_schema_ids',(select jsonb_agg(distinct e.value) from jsonb_array_elements(bindings) b cross join lateral jsonb_array_elements(jsonb_build_array(b->'request_schema_id',b->'response_schema_id')) e),'capability_vocabulary',(select coalesce(jsonb_agg(distinct name),'["db.governed_operations"]'::jsonb) from ecos.capability),'operation_bindings',bindings,'schema_bundle',bundle,'relevant_work',works);
 package:=package||jsonb_build_object('content_hash',ecos_meta.content_hash(package)); perform ecos_meta.assert_contract('bootstrap_package',package); return package;
end $$;

reset role;
