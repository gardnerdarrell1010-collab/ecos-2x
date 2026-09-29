set local role ecos_owner;
insert into ecos_meta.contract_schema values('https://contracts.ecos.invalid/v1/integrity_finding.schema.json','{"$schema":"https://json-schema.org/draft/2020-12/schema","$id":"https://contracts.ecos.invalid/v1/integrity_finding.schema.json","title":"integrity_finding","type":"object","additionalProperties":false,"properties":{"id":{"type":"string","format":"uuid"},"condition":{"type":"string"},"entity_id":{"type":"string","format":"uuid"},"before_state":{"anyOf":[{"type":"array"},{"type":"object"}]},"detected_at":{"type":"string","format":"date-time"},"correlation_id":{"type":"string","format":"uuid"}},"required":["id","condition","entity_id","before_state","detected_at","correlation_id"]}'::jsonb);
insert into ecos.capability(name,version,description) values('db.governed_operations',1,'Validate/commit business state, audit and outbox');
insert into ecos.capability(name,version,description) values('db.claims',1,'Atomic claims, fences, renewals and recovery');
insert into ecos.capability(name,version,description) values('db.features',1,'Deterministic projections and feature computation');
insert into ecos.capability(name,version,description) values('semantic.interpret',1,'Interpret source evidence into versioned proposals');
insert into ecos.capability(name,version,description) values('semantic.draft',1,'Draft governed content with source references');
insert into ecos.capability(name,version,description) values('semantic.forecast',1,'Explain and propose forecasts using frozen inputs');
insert into ecos.capability(name,version,description) values('semantic.memory_compact',1,'Propose continuity versions with manifest');
insert into ecos.capability(name,version,description) values('human.review',1,'Present human decisions through governed operations');
insert into ecos.capability(name,version,description) values('provider.gmail',1,'Gmail receipt/draft/approved transport and reconciliation');
insert into ecos.capability(name,version,description) values('provider.drive',1,'Drive materialization and hash verification');
insert into ecos.capability(name,version,description) values('provider.toast',1,'Acquire closed actuals with checkpoint evidence');
insert into ecos.capability(name,version,description) values('provider.twilio',1,'SMS transport and reconciliation');
insert into ecos.capability(name,version,description) values('provider.calendar',1,'Calendar references and delta ingestion');
insert into ecos.capability(name,version,description) values('provider.finance',1,'Read account facts with as-of provenance');
insert into ecos.capability(name,version,description) values('provider.publication',1,'Publish approved artifact versions');
insert into ecos.capability(name,version,description) values('provider.owner_review',1,'Receive review packages and ACK after commit proof');
insert into ecos.capability(name,version,description) values('local.render',1,'Safe templates, sample isolation, exact byte readback');
insert into ecos.capability(name,version,description) values('recovery.export',1,'Create independent logical/portable packages');
create or replace function ecos_meta.record_value(kind text,entity uuid,lock_ boolean default false) returns jsonb language plpgsql set search_path=pg_catalog as $$
declare v jsonb;
begin
 if kind not in ('task','project','party','artifact','fact','memory_record','memory_version','work_occurrence','provider_receipt','communication','approval_request','integrity_finding') then raise exception 'invalid_contract' using errcode='22023'; end if;
 execute format('select to_jsonb(t) from ecos.%I t where id=$1%s',kind,case when lock_ then ' for update' else '' end) into v using entity;
 if v is null then raise exception 'missing_reference' using errcode='23503'; end if; return v;
end $$;

create or replace function ecos.bootstrap_package() returns jsonb language plpgsql security definer set search_path=pg_catalog set timezone='UTC' as $$
declare p ecos_meta.principal_binding; g record; v jsonb; source jsonb; contexts jsonb:='[]'; refs jsonb:='[]'; heads jsonb:='[]'; works jsonb:='[]'; bindings jsonb; bundle jsonb; package jsonb; ceiling_ text; exceptions_ jsonb:='[]';
begin p:=ecos_meta.current_principal(); select ceiling into ceiling_ from ecos_meta.principal_clearance where principal_id=p.principal_id;
 for g in select * from ecos_meta.object_grant where principal_id=p.principal_id order by record_type,record_id loop
  if g.record_type not in ('task','memory_version','work_occurrence','integrity_finding') then continue; end if;
  begin perform ecos_meta.require_access(p.principal_id,g.record_type,g.record_id); exception when insufficient_privilege then continue; end;
  v:=ecos_meta.record_value(g.record_type,g.record_id);
  if g.record_type='memory_version' then
   if not exists(select 1 from ecos.memory_record where active_head_version_id=g.record_id) then continue; end if;
   if exists(select 1 from jsonb_array_elements((v->'provenance')||(v->'authoritative_references')) r where not exists(select 1 from ecos_meta.object_grant where principal_id=p.principal_id and record_type=r->>'record_type' and record_id=(r->>'record_id')::uuid)) then continue; end if;
   heads:=heads||jsonb_build_array(v);
  elsif g.record_type='work_occurrence' then works:=works||jsonb_build_array(v); end if;
  source:=jsonb_build_object('record_type',g.record_type,'record_id',g.record_id,'record_version',coalesce((v->>'record_version')::bigint,1),'content_hash',ecos_meta.content_hash(v),'authority',case when g.record_type='memory_version' then 'governed_memory' else 'structured_ecos' end);
  if g.record_type='integrity_finding' then exceptions_:=exceptions_||jsonb_build_array(source); end if;
  contexts:=contexts||jsonb_build_array(jsonb_build_object('source',source,'record_schema_id','https://contracts.ecos.invalid/v1/'||g.record_type||'.schema.json','record',v)); refs:=refs||jsonb_build_array(source);
 end loop;
 select jsonb_agg(jsonb_build_object('operation',o.name,'path','/v1/operations/'||o.name,'request_schema_id',o.document->>'request_schema','response_schema_id',o.document->>'response_schema') order by o.name) into bindings from ecos_meta.operation_contract o join ecos_meta.principal_operation po on po.operation=o.name and po.principal_id=p.principal_id where ecos_meta.operation_authorized(o.name,p.role_name);
 if bindings is null then raise exception 'forbidden'; end if;
 select jsonb_agg(jsonb_build_object('schema_id',schema_id,'sha256',ecos_meta.content_hash(document),'document',document) order by schema_id) into bundle from ecos_meta.contract_schema;
 package:=jsonb_build_object('package_id',gen_random_uuid(),'schema_version','1.0.0','database_schema_version','1.0.0','generated_at',clock_timestamp(),'principal_id',p.principal_id,'sensitivity_ceiling',coalesce(ceiling_,'internal'),'governed_context',refs,'context_records',contexts,'active_memory_heads',heads,'unresolved_exceptions',exceptions_,'operation_schema_ids',(select jsonb_agg(distinct e.value) from jsonb_array_elements(bindings) b cross join lateral jsonb_array_elements(jsonb_build_array(b->'request_schema_id',b->'response_schema_id')) e),'capability_vocabulary',(select coalesce(jsonb_agg(distinct name),'["db.governed_operations"]'::jsonb) from ecos.capability),'operation_bindings',bindings,'schema_bundle',bundle,'relevant_work',works);
 package:=package||jsonb_build_object('content_hash',ecos_meta.content_hash(package)); perform ecos_meta.assert_contract('bootstrap_package',package); return package;
end $$;


create or replace function ecos_meta.claim_work(ctx jsonb,args jsonb) returns jsonb language plpgsql set search_path=pg_catalog as $$
declare o ecos.work_occurrence; c ecos.work_claim; r ecos.execution_run; sel jsonb; at_ timestamptz:=clock_timestamp(); instance uuid:=(args->>'executor_instance_id')::uuid; principal uuid:=(ctx->>'principal_id')::uuid;
begin
 if ctx->>'executor_instance_id' is distinct from args->>'executor_instance_id' then raise exception 'forbidden' using errcode='42501'; end if;
 for o in select w.* from ecos.work_occurrence w cross join lateral (select ecos_meta.selection(w.id,instance,at_) s) q
 where w.state in ('pending','ready','retry_wait','claimed','running') and (w.due_at<=at_ or w.ready_override_at<=at_) and (w.retry_at is null or w.retry_at<=at_) and (q.s->>'eligible')::boolean and exists(select 1 from ecos_meta.object_grant g where g.principal_id=principal and g.record_type='work_occurrence' and g.record_id=w.id)
 order by (q.s->>'priority_override')::bigint desc,(q.s->>'immediate_ready')::boolean desc,(q.s->>'sla_breach_seconds')::bigint desc,(q.s->>'deadline_pressure_seconds')::bigint desc,(q.s->>'business_impact')::bigint desc,(q.s->>'recurrence_relative_age_basis_points')::bigint desc,w.created_at,w.id for update of w skip locked limit 1 loop
  perform ecos_meta.recover_occurrence(o.id);
  sel:=ecos_meta.selection(o.id,instance,clock_timestamp());
  if not (sel->>'eligible')::boolean then continue; end if;
  update ecos.work_occurrence set state='ready',record_version=record_version+1 where id=o.id and state in ('pending','retry_wait');
  update ecos.work_occurrence set state='claimed',claim_version=claim_version+1,attempt_count=attempt_count+1,record_version=record_version+1 where id=o.id returning * into o;
  insert into ecos.work_claim(occurrence_id,stage_definition_id,executor_instance_id,claim_version,fence_token,state,acquired_at,expires_at,renewed_at) values(o.id,o.stage_definition_id,instance,o.claim_version,gen_random_uuid(),'active',clock_timestamp(),clock_timestamp()+make_interval(secs=>(args->>'lease_seconds')::int),clock_timestamp()) returning * into c;
  insert into ecos.execution_run(claim_id,occurrence_id,stage_definition_id,claim_version,fence_token,executor_instance_id,state,selection_evidence,correlation_id,ended_at) values(c.id,c.occurrence_id,c.stage_definition_id,c.claim_version,c.fence_token,c.executor_instance_id,'started',sel,(ctx->>'correlation_id')::uuid,null) returning * into r;
  perform ecos_meta.execution_event(r.id,'started','selected');
  update ecos.work_occurrence set state='running',record_version=record_version+1 where id=o.id;
  return jsonb_build_object('schema_version','1.0.0','correlation_id',ctx->'correlation_id','claim',to_jsonb(c),'execution_run',ecos_meta.run_wire(to_jsonb(r)));
 end loop;
 return jsonb_build_object('schema_version','1.0.0','correlation_id',ctx->'correlation_id','claim',null,'execution_run',null);
end $$;

reset role;
