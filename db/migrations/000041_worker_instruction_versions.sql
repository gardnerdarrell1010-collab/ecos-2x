-- Complete worker instructions are immutable versions, scoped to an existing stage.
set local role ecos_owner;
create table ecos.work_instruction_version (
 id uuid primary key default gen_random_uuid(),
 work_definition_id uuid not null references ecos.work_definition,
 stage_definition_id uuid not null references ecos.work_stage_definition,
 instruction_version bigint not null check(instruction_version>0),
 instruction_text text not null check(octet_length(instruction_text) between 1 and 262144),
 content_sha256 text not null check(content_sha256=encode(sha256(convert_to(instruction_text,'UTF8')),'hex')),
 source_reference text not null check(length(source_reference) between 1 and 2048),
 published_by uuid not null,
 correlation_id uuid not null,
 published_at timestamptz not null default clock_timestamp(),
 unique(stage_definition_id,instruction_version)
);
-- Pin once per claim, including absence. A later publication cannot change an active package.
create table ecos.work_claim_instruction (
 claim_id uuid primary key references ecos.work_claim,
 instruction_id uuid references ecos.work_instruction_version
);
create trigger immutable before update or delete on ecos.work_instruction_version
 for each row execute function ecos_meta.forbid_evidence_change();
create trigger immutable before update or delete on ecos.work_claim_instruction
 for each row execute function ecos_meta.forbid_evidence_change();
alter table ecos.work_instruction_version enable row level security;
alter table ecos.work_claim_instruction enable row level security;
revoke all on ecos.work_instruction_version,ecos.work_claim_instruction from public,anon,authenticated,service_role,executor,operations_api;

alter function ecos_meta.require_operation_scope(text,jsonb,uuid) rename to require_operation_scope_before_instructions;
create function ecos_meta.require_operation_scope(op text,args jsonb,principal uuid) returns void
 language plpgsql stable set search_path=pg_catalog as $$
begin
 perform ecos_meta.require_operation_scope_before_instructions(op,args,principal);
 if op='work.instruction.publish' then
  perform ecos_meta.require_access(principal,'work_definition',(args->>'work_definition_id')::uuid);
  perform ecos_meta.require_access(principal,'work_stage_definition',(args->>'stage_definition_id')::uuid);
 end if;
end $$;

alter function ecos_meta.apply_operation(text,jsonb,jsonb) rename to apply_operation_before_instructions;
create function ecos_meta.apply_operation(op text,ctx jsonb,args jsonb) returns jsonb
 language plpgsql set search_path=pg_catalog as $$
declare v ecos.work_instruction_version; version_ bigint;
begin
 if op<>'work.instruction.publish' then return ecos_meta.apply_operation_before_instructions(op,ctx,args); end if;
 perform 1 from ecos.work_stage_definition where id=(args->>'stage_definition_id')::uuid
  and work_definition_id=(args->>'work_definition_id')::uuid for update;
 if not found then raise exception 'invalid_contract' using errcode='22023'; end if;
 select coalesce(max(instruction_version),0) into version_ from ecos.work_instruction_version
  where stage_definition_id=(args->>'stage_definition_id')::uuid;
 if version_<>(args->>'expected_version')::bigint then raise exception 'stale_version' using errcode='40001'; end if;
 insert into ecos.work_instruction_version(work_definition_id,stage_definition_id,instruction_version,
  instruction_text,content_sha256,source_reference,published_by,correlation_id)
 values((args->>'work_definition_id')::uuid,(args->>'stage_definition_id')::uuid,version_+1,
  args->>'instruction_text',args->>'content_sha256',args->>'source_reference',
  (ctx->>'principal_id')::uuid,(ctx->>'correlation_id')::uuid) returning * into v;
 return jsonb_build_object('schema_version','1.0.0','correlation_id',ctx->'correlation_id',
  'status','committed','data',to_jsonb(v)-'instruction_text');
end $$;

create or replace function ecos_meta.work_package(ctx jsonb,f jsonb) returns jsonb language plpgsql set search_path=pg_catalog set timezone='UTC' as $$
declare c ecos.work_claim; w ecos.work_occurrence; t ecos.task; wc ecos.work_context; s ecos.work_stage_definition; refs jsonb; payload jsonb; bytes_ bigint; instruction_ jsonb;
begin
 c:=ecos_meta.check_fence(ctx,f); select * into w from ecos.work_occurrence where id=c.occurrence_id;
 select * into wc from ecos.work_context where occurrence_id=w.id;
 if wc.occurrence_id is null then raise exception 'invalid_contract' using errcode='22023'; end if;
 if not exists(select 1 from ecos_meta.principal_operation where principal_id=(ctx->>'principal_id')::uuid and operation=wc.operation) then raise exception 'forbidden' using errcode='42501'; end if;
 if w.task_id is not null then perform ecos_meta.require_access((ctx->>'principal_id')::uuid,'task',w.task_id); select * into t from ecos.task where id=w.task_id; end if;
 refs:=wc.source_references||wc.memory_references;
 perform ecos_meta.verify_sources((ctx->>'principal_id')::uuid,refs);
 select * into s from ecos.work_stage_definition where id=w.stage_definition_id;
 payload:=jsonb_build_object('occurrence',to_jsonb(w),'stage',to_jsonb(s),
 'task',case when t.id is null then null else jsonb_build_object('id',t.id,'title',t.title,'record_version',t.record_version,'lifecycle_state',t.lifecycle_state) end,
 'operation',(select document from ecos_meta.operation_contract where name=wc.operation),
 'capability_requirements',(select coalesce(jsonb_agg(jsonb_build_object('name',capability_name,'minimum_version',minimum_version)),'[]') from ecos.stage_capability_requirement where stage_definition_id=s.id),
 'source_references',wc.source_references,'memory_references',wc.memory_references,'input',wc.input,
 'deadline_sla',(select to_jsonb(p) from ecos.work_priority p where occurrence_id=w.id),
 'approval_context',(select coalesce(jsonb_agg(to_jsonb(a)),'[]') from ecos.work_approval a where occurrence_id=w.id),
 'correlation_id',ctx->'correlation_id','fence',f,'context_version',wc.record_version,
 'retry_policy',(select to_jsonb(r) from ecos.work_definition d join ecos.retry_policy r on r.id=d.retry_policy_id where d.id=w.work_definition_id),
 'idempotency',jsonb_build_object('scope','principal + operation + key','occurrence_key',w.occurrence_key));
 bytes_:=octet_length(payload::text); if bytes_>32768 then raise exception 'invalid_contract' using errcode='22023'; end if;
 -- The existing context limit is unchanged; instruction text has its own explicit bound.
 perform 1 from ecos.work_claim where id=c.id for update;
 insert into ecos.work_claim_instruction(claim_id,instruction_id)
 select c.id,(select id from ecos.work_instruction_version where stage_definition_id=s.id
  and work_definition_id=w.work_definition_id order by instruction_version desc limit 1)
 on conflict(claim_id) do nothing;
 select to_jsonb(v) into instruction_ from ecos.work_claim_instruction p
 join ecos.work_instruction_version v on v.id=p.instruction_id where p.claim_id=c.id;
 payload:=payload||jsonb_build_object('functional_instructions',instruction_);
 bytes_:=octet_length(payload::text);
 insert into ecos.package_measurement(occurrence_id,principal_id,payload_bytes,source_count) values(w.id,(ctx->>'principal_id')::uuid,bytes_,jsonb_array_length(refs));
 return payload;
end $$;
insert into ecos_meta.contract_schema values('https://contracts.ecos.invalid/v1/work.instruction.publish-request.schema.json','{"$schema":"https://json-schema.org/draft/2020-12/schema","$id":"https://contracts.ecos.invalid/v1/work.instruction.publish-request.schema.json","type":"object","properties":{"schema_version":{"const":"1.0.0"},"context":{"$ref":"https://contracts.ecos.invalid/v1/request_context.schema.json"},"arguments":{"type":"object","properties":{"work_definition_id":{"type":"string","format":"uuid"},"stage_definition_id":{"type":"string","format":"uuid"},"expected_version":{"type":"integer","minimum":0},"instruction_text":{"type":"string","minLength":1,"maxLength":65536},"source_reference":{"type":"string","minLength":1,"maxLength":2048},"content_sha256":{"type":"string","pattern":"^[a-f0-9]{64}$"}},"required":["work_definition_id","stage_definition_id","expected_version","instruction_text","source_reference","content_sha256"],"additionalProperties":false}},"required":["schema_version","context","arguments"],"additionalProperties":false}'::jsonb);
insert into ecos_meta.operation_contract values('work.instruction.publish','{"name":"work.instruction.publish","request_schema":"https://contracts.ecos.invalid/v1/work.instruction.publish-request.schema.json","response_schema":"https://contracts.ecos.invalid/v1/phase2_result.schema.json","required_role":"operations_api","semantic_proposable":false,"idempotency_scope":"principal_id + operation + idempotency_key","atomicity":"single transaction"}'::jsonb);
revoke all on all functions in schema ecos_meta from public;
reset role;
