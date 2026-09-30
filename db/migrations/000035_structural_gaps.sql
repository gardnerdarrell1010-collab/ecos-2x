-- Additive structural contracts; no operational population migration.
set local role ecos_owner;
alter table ecos.party add column party_kind text check(party_kind in ('person','organization'));
comment on column ecos.party.party_kind is 'NULL preserves unclassified legacy records; new governed writes require explicit source-supported kind.';
alter table ecos.artifact add column attachment_id text;
alter table ecos.artifact add constraint artifact_attachment_scope check(attachment_id is null or (provider='gmail' and length(btrim(attachment_id)) between 1 and 512));
alter table ecos.artifact drop constraint artifact_provider_provider_object_id_key;
create unique index artifact_provider_object_unique on ecos.artifact(provider,provider_object_id) where attachment_id is null;
create unique index artifact_attachment_unique on ecos.artifact(provider,provider_object_id,attachment_id) where attachment_id is not null;

alter table ecos.approval_request add column expiration_mode text not null default 'expires' check(expiration_mode in ('expires','never'));
alter table ecos.approval_request alter column expires_at drop not null;
alter table ecos.approval_request add constraint approval_expiration_explicit check((expiration_mode='expires' and expires_at is not null) or (expiration_mode='never' and expires_at is null));
update ecos_meta.contract_schema set document=jsonb_set(jsonb_set(document,'{properties,expires_at}','{"anyOf":[{"type":"string","format":"date-time"},{"type":"null"}]}'),'{properties,expiration_mode}','{"type":"string","enum":["expires","never"]}') || '{"allOf":[{"if":{"properties":{"expiration_mode":{"const":"never"}},"required":["expiration_mode"]},"then":{"properties":{"expires_at":{"type":"null"}}},"else":{"properties":{"expires_at":{"type":"string","format":"date-time"}}}}]}'::jsonb where schema_id='https://contracts.ecos.invalid/v1/approval_request.schema.json';

create table ecos.relationship (
 id uuid primary key, record_version bigint not null default 1 check(record_version>0),
 source_system text not null check(length(btrim(source_system)) between 1 and 200),
 source_relationship_id text not null check(length(btrim(source_relationship_id)) between 1 and 200),
 source_type text not null check(source_type in ('party','project','task')),
 source_id uuid not null, target_type text not null check(target_type in ('party','project','task')),
 target_id uuid not null, relationship_type text not null check(length(btrim(relationship_type)) between 1 and 128),
 status text not null check(length(btrim(status)) between 1 and 128),
 effective_from timestamptz, effective_to timestamptz,
 provenance jsonb not null check(jsonb_typeof(provenance)='array' and jsonb_array_length(provenance)>0),
 unique(source_system,source_relationship_id),
 check(effective_from is null or effective_to is null or effective_to>=effective_from)
);
alter table ecos.relationship enable row level security;
revoke all on ecos.relationship from public,executor,operations_api,provider_adapter;

alter function ecos_meta.record_value(text,uuid,boolean) rename to record_value_before_structural;
create function ecos_meta.record_value(kind text,entity uuid,lock_ boolean default false) returns jsonb language plpgsql set search_path=pg_catalog as $$
declare v jsonb;
begin
 if kind not in ('relationship','communication_processing') then
  v:=ecos_meta.record_value_before_structural(kind,entity,lock_);
  if kind='party' and v->'party_kind'='null'::jsonb then v:=v-'party_kind'; end if;
  if kind='artifact' and v->'attachment_id'='null'::jsonb then v:=v-'attachment_id'; end if;
  if kind='approval_request' and v->>'expiration_mode'='expires' then v:=v-'expiration_mode'; end if;
  return v;
 end if;
 execute format('select to_jsonb(t) from ecos.%I t where id=$1%s',kind,case when lock_ then ' for update' else '' end) into v using entity;
 if v is null then raise exception 'missing_reference' using errcode='23503'; end if;
 return v;
end $$;

alter function ecos_meta.require_operation_scope(text,jsonb,uuid) rename to require_operation_scope_before_structural;
create function ecos_meta.require_operation_scope(op text,args jsonb,principal uuid) returns void language plpgsql stable set search_path=pg_catalog as $$
declare ref_ jsonb;
begin
 perform ecos_meta.require_operation_scope_before_structural(op,args,principal);
 if op in ('party.put','relationship.put','artifact.register','approval.request') then
  perform ecos_meta.require_access(principal,case op when 'party.put' then 'party' when 'relationship.put' then 'relationship' when 'artifact.register' then 'artifact' else 'approval_request' end,(args->>'id')::uuid);
  for ref_ in select value from jsonb_array_elements(args->'provenance') loop
   perform ecos_meta.require_access(principal,ref_->>'record_type',(ref_->>'record_id')::uuid);
  end loop;
 end if;
 if op='relationship.put' then
  perform ecos_meta.require_access(principal,args->>'source_type',(args->>'source_id')::uuid);
  perform ecos_meta.require_access(principal,args->>'target_type',(args->>'target_id')::uuid);
 elsif op='approval.request' then
  perform ecos_meta.require_access(principal,args->>'subject_type',(args->>'subject_id')::uuid);
 elsif op='sms.continuation.enqueue' then
  perform ecos_meta.require_access(principal,'communication',(args->>'communication_id')::uuid);
  perform ecos_meta.require_access(principal,'task',(args->>'task_id')::uuid);
 elsif op='sms.continuation.complete' then
  perform ecos_meta.require_access(principal,'work_occurrence',(args->'fence'->>'occurrence_id')::uuid);
 end if;
end $$;

-- Prepared definition only. No held occurrence is created or released here.
do $$ declare retry_ uuid; definition_ uuid; stage_ uuid;
begin
 if exists(select 1 from ecos.work_definition where name='sms_continuation') then raise exception 'existing_sms_contract_requires_reconciliation'; end if;
 insert into ecos.retry_policy(max_attempts,initial_delay_seconds,max_delay_seconds,backoff_multiplier,jitter_basis_points,retryable_error_classes) values(1,1,1,1,0,'[]') returning id into retry_;
 insert into ecos.work_definition(name,definition_version,enabled,fulfillment_kind,retry_policy_id) values('sms_continuation',1,false,'staged',retry_) returning id into definition_;
 insert into ecos.work_stage_definition(work_definition_id,stage_key,kind,execution_surface,input_schema_id,result_schema_id,requires_approval) values(definition_,'sms_continuation','semantic','ONLINE_SEMANTIC','ecos.sms.continuation.input.v1','ecos.sms.continuation.result.v1',false) returning id into stage_;
 insert into ecos.stage_capability_requirement(stage_definition_id,capability_name,minimum_version) values(stage_,'ecos.2x.execute',1),(stage_,'semantic.interpret',1),(stage_,'db.governed_operations',1);
end $$;

alter function ecos_meta.apply_operation(text,jsonb,jsonb) rename to apply_operation_before_structural;
create function ecos_meta.apply_operation(op text,ctx jsonb,args jsonb) returns jsonb language plpgsql set search_path=pg_catalog as $$
declare principal uuid:=(ctx->>'principal_id')::uuid; id_ uuid:=(args->>'id')::uuid; v jsonb; prior jsonb; ver bigint; kind_ text;
 c ecos.communication; p ecos.communication_processing; claim_ ecos.work_claim; stage_ ecos.work_stage_definition;
 domain_ text; occurrence_ uuid; processing_ uuid; refs jsonb; proposal_ jsonb; committed_ jsonb;
begin
 if op not in ('party.put','relationship.put','artifact.register','approval.request','sms.continuation.enqueue','sms.continuation.complete') then return ecos_meta.apply_operation_before_structural(op,ctx,args); end if;
 if args ? 'provenance' then perform ecos_meta.verify_sources(principal,args->'provenance'); end if;
 if op='party.put' then
  select to_jsonb(t) into prior from ecos.party t where id=id_ for update;
  if coalesce((prior->>'record_version')::bigint,0)<>(args->>'expected_version')::bigint then raise exception 'stale_version' using errcode='40001'; end if;
  if prior is null then insert into ecos.party(id,business_id,name,party_kind) values(id_,args->>'business_id',args->>'name',args->>'party_kind');
  else
   if prior->>'business_id'<>args->>'business_id' or (prior->>'party_kind' is not null and prior->>'party_kind'<>args->>'party_kind') then raise exception 'invalid_contract'; end if;
   update ecos.party set name=args->>'name',party_kind=args->>'party_kind',record_version=record_version+1 where id=id_;
  end if;
  v:=ecos_meta.record_value('party',id_);
 elsif op='relationship.put' then
  perform ecos_meta.record_value(args->>'source_type',(args->>'source_id')::uuid,true);
  perform ecos_meta.record_value(args->>'target_type',(args->>'target_id')::uuid,true);
  select to_jsonb(t) into prior from ecos.relationship t where id=id_ for update;
  if coalesce((prior->>'record_version')::bigint,0)<>(args->>'expected_version')::bigint then raise exception 'stale_version' using errcode='40001'; end if;
  if prior is null then
   insert into ecos.relationship(id,source_system,source_relationship_id,source_type,source_id,target_type,target_id,relationship_type,status,effective_from,effective_to,provenance)
   values(id_,args->>'source_system',args->>'source_relationship_id',args->>'source_type',(args->>'source_id')::uuid,args->>'target_type',(args->>'target_id')::uuid,args->>'relationship_type',args->>'status',(args->>'effective_from')::timestamptz,(args->>'effective_to')::timestamptz,args->'provenance');
  else
   if (prior-array['record_version','status','effective_from','effective_to','provenance'])<>(args-array['expected_version','status','effective_from','effective_to','provenance']) then raise exception 'invalid_contract'; end if;
   update ecos.relationship set status=args->>'status',effective_from=(args->>'effective_from')::timestamptz,effective_to=(args->>'effective_to')::timestamptz,provenance=args->'provenance',record_version=record_version+1 where id=id_;
  end if;
  v:=ecos_meta.record_value('relationship',id_);
 elsif op='artifact.register' then
  insert into ecos.artifact(id,business_id,provider,provider_object_id,uri,content_hash,attachment_id) values(id_,args->>'business_id',args->>'provider',args->>'provider_object_id',args->>'uri',args->>'content_hash',args->>'attachment_id');
  v:=ecos_meta.record_value('artifact',id_);
 elsif op='approval.request' then
  v:=ecos_meta.record_value(args->>'subject_type',(args->>'subject_id')::uuid,true);
  if ecos_meta.content_hash(v)<>args->>'subject_hash' then raise exception 'stale_version' using errcode='40001'; end if;
  insert into ecos.approval_request(id,task_id,subject_type,subject_id,subject_hash,state,expires_at,expiration_mode) values(id_,null,args->>'subject_type',(args->>'subject_id')::uuid,args->>'subject_hash','pending',(args->>'expires_at')::timestamptz,args->>'expiration_mode');
  v:=ecos_meta.record_value('approval_request',id_);
 elsif op='sms.continuation.enqueue' then
  select * into c from ecos.communication where id=(args->>'communication_id')::uuid for update;
  if c.id is null or c.record_version<>(args->>'source_version')::bigint or c.channel<>'sms' or not exists(select 1 from ecos.provider_receipt where id=c.receipt_id and provider='twilio') then raise exception 'gate_blocked'; end if;
  if exists(select 1 from ecos.communication_processing where communication_id=c.id and source_version=c.record_version) then raise exception 'idempotency_conflict' using errcode='23505'; end if;
  select * into stage_ from ecos.work_stage_definition where stage_key='sms_continuation' and work_definition_id in(select id from ecos.work_definition where name='sms_continuation' and definition_version=1);
  if stage_.id is null then raise exception 'gate_blocked'; end if;
  select domain into domain_ from ecos_meta.principal_domain where principal_id=principal;
  occurrence_:=gen_random_uuid(); processing_:=gen_random_uuid();
  insert into ecos.work_occurrence(id,work_definition_id,stage_definition_id,fulfillment_id,task_id,state,occurrence_key,due_at) values(occurrence_,stage_.work_definition_id,stage_.id,gen_random_uuid(),(args->>'task_id')::uuid,'ready','sms:'||c.id::text||':'||c.record_version::text,clock_timestamp());
  insert into ecos.communication_processing(id,communication_id,source_version,state,occurrence_id) values(processing_,c.id,c.record_version,'ready',occurrence_);
  insert into ecos_meta.object_domain values('work_occurrence',occurrence_,domain_),('communication_processing',processing_,domain_);
  insert into ecos_meta.object_grant values(principal,'work_occurrence',occurrence_),(principal,'communication_processing',processing_);
  refs:=jsonb_build_array(jsonb_build_object('record_type','communication','record_id',c.id,'record_version',c.record_version,'content_hash',ecos_meta.content_hash(to_jsonb(c)),'authority','structured_ecos'));
  insert into ecos.work_context(occurrence_id,operation,source_references,input) values(occurrence_,'sms.continuation.complete',refs,jsonb_build_object('processing_id',processing_,'communication_id',c.id));
  v:=jsonb_build_object('processing_id',processing_,'occurrence_id',occurrence_);
 elsif op='sms.continuation.complete' then
  claim_:=ecos_meta.check_fence(ctx,args->'fence');
  if not exists(select 1 from ecos.work_stage_definition where id=claim_.stage_definition_id and stage_key='sms_continuation' and execution_surface='ONLINE_SEMANTIC') then raise exception 'forbidden' using errcode='42501'; end if;
  select * into p from ecos.communication_processing where occurrence_id=claim_.occurrence_id for update;
  perform ecos_meta.require_access(principal,'communication',p.communication_id);
  if p.id is null or p.state<>'ready' then raise exception 'gate_blocked'; end if;
  select proposal into proposal_ from ecos.proposal_submission where proposal_id=(args->>'proposal_id')::uuid and occurrence_id=claim_.occurrence_id and principal_id=principal;
  if proposal_ is null then raise exception 'gate_blocked'; end if;
  perform ecos_meta.verify_sources(principal,(select source_references from ecos.work_context where occurrence_id=claim_.occurrence_id));
  if not exists(select 1 from jsonb_array_elements(proposal_->'source_references') ref where ref->>'record_type'='communication' and ref->>'record_id'=p.communication_id::text and (ref->>'record_version')::bigint=p.source_version) then raise exception 'invalid_contract'; end if;
  committed_:=ecos_meta.commit_proposal(ctx,proposal_);
  if exists(select 1 from jsonb_array_elements(committed_->'items') i where i->>'state'<>'committed') then raise exception 'gate_blocked'; end if;
  update ecos.communication_processing set state='running',proposal_id=(args->>'proposal_id')::uuid,record_version=record_version+1 where id=p.id;
  update ecos.communication_processing set state='succeeded',record_version=record_version+1 where id=p.id;
  v:=ecos_meta.record_value('communication_processing',p.id);
 end if;
 return jsonb_build_object('schema_version','1.0.0','correlation_id',ctx->'correlation_id','status','committed','data',v);
end $$;
revoke all on all functions in schema ecos_meta from public;
reset role;

set local role ecos_owner;
insert into ecos_meta.contract_schema values('https://contracts.ecos.invalid/v1/party.put-request.schema.json','{"$schema":"https://json-schema.org/draft/2020-12/schema","$id":"https://contracts.ecos.invalid/v1/party.put-request.schema.json","title":"party.put-request","type":"object","properties":{"schema_version":{"const":"1.0.0"},"context":{"$ref":"https://contracts.ecos.invalid/v1/request_context.schema.json"},"arguments":{"type":"object","properties":{"id":{"type":"string","format":"uuid"},"expected_version":{"type":"integer","minimum":0},"business_id":{"type":"string","minLength":1,"maxLength":512},"name":{"type":"string","minLength":1,"maxLength":512},"party_kind":{"type":"string","enum":["person","organization"]},"provenance":{"type":"array","minItems":1,"maxItems":50,"items":{"$ref":"https://contracts.ecos.invalid/v1/source_reference.schema.json"}}},"required":["id","expected_version","business_id","name","party_kind","provenance"],"additionalProperties":false}},"required":["schema_version","context","arguments"],"additionalProperties":false}'::jsonb);
insert into ecos_meta.operation_contract values('party.put','{"name":"party.put","request_schema":"https://contracts.ecos.invalid/v1/party.put-request.schema.json","response_schema":"https://contracts.ecos.invalid/v1/phase2_result.schema.json","required_role":"operations_api","semantic_proposable":false,"idempotency_scope":"principal_id + operation + idempotency_key","atomicity":"single transaction"}'::jsonb);
insert into ecos_meta.contract_schema values('https://contracts.ecos.invalid/v1/relationship.put-request.schema.json','{"$schema":"https://json-schema.org/draft/2020-12/schema","$id":"https://contracts.ecos.invalid/v1/relationship.put-request.schema.json","title":"relationship.put-request","type":"object","properties":{"schema_version":{"const":"1.0.0"},"context":{"$ref":"https://contracts.ecos.invalid/v1/request_context.schema.json"},"arguments":{"type":"object","properties":{"id":{"type":"string","format":"uuid"},"expected_version":{"type":"integer","minimum":0},"source_system":{"type":"string","minLength":1,"maxLength":512},"source_relationship_id":{"type":"string","minLength":1,"maxLength":512},"source_type":{"type":"string","enum":["party","project","task"]},"source_id":{"type":"string","format":"uuid"},"target_type":{"type":"string","enum":["party","project","task"]},"target_id":{"type":"string","format":"uuid"},"relationship_type":{"type":"string","minLength":1,"maxLength":512},"status":{"type":"string","minLength":1,"maxLength":512},"effective_from":{"anyOf":[{"type":"string","format":"date-time"},{"type":"null"}]},"effective_to":{"anyOf":[{"type":"string","format":"date-time"},{"type":"null"}]},"provenance":{"type":"array","minItems":1,"maxItems":50,"items":{"$ref":"https://contracts.ecos.invalid/v1/source_reference.schema.json"}}},"required":["id","expected_version","source_system","source_relationship_id","source_type","source_id","target_type","target_id","relationship_type","status","effective_from","effective_to","provenance"],"additionalProperties":false}},"required":["schema_version","context","arguments"],"additionalProperties":false}'::jsonb);
insert into ecos_meta.operation_contract values('relationship.put','{"name":"relationship.put","request_schema":"https://contracts.ecos.invalid/v1/relationship.put-request.schema.json","response_schema":"https://contracts.ecos.invalid/v1/phase2_result.schema.json","required_role":"operations_api","semantic_proposable":false,"idempotency_scope":"principal_id + operation + idempotency_key","atomicity":"single transaction"}'::jsonb);
insert into ecos_meta.contract_schema values('https://contracts.ecos.invalid/v1/artifact.register-request.schema.json','{"$schema":"https://json-schema.org/draft/2020-12/schema","$id":"https://contracts.ecos.invalid/v1/artifact.register-request.schema.json","title":"artifact.register-request","type":"object","properties":{"schema_version":{"const":"1.0.0"},"context":{"$ref":"https://contracts.ecos.invalid/v1/request_context.schema.json"},"arguments":{"type":"object","properties":{"id":{"type":"string","format":"uuid"},"business_id":{"type":"string","minLength":1,"maxLength":512},"provider":{"type":"string","minLength":1,"maxLength":512},"provider_object_id":{"type":"string","minLength":1,"maxLength":512},"uri":{"type":"string","minLength":1,"maxLength":512},"content_hash":{"type":"string","pattern":"^[a-f0-9]{64}$"},"attachment_id":{"anyOf":[{"type":"string","minLength":1,"maxLength":512},{"type":"null"}]},"provenance":{"type":"array","minItems":1,"maxItems":50,"items":{"$ref":"https://contracts.ecos.invalid/v1/source_reference.schema.json"}}},"required":["id","business_id","provider","provider_object_id","uri","content_hash","attachment_id","provenance"],"additionalProperties":false}},"required":["schema_version","context","arguments"],"additionalProperties":false}'::jsonb);
insert into ecos_meta.operation_contract values('artifact.register','{"name":"artifact.register","request_schema":"https://contracts.ecos.invalid/v1/artifact.register-request.schema.json","response_schema":"https://contracts.ecos.invalid/v1/phase2_result.schema.json","required_role":"operations_api","semantic_proposable":false,"idempotency_scope":"principal_id + operation + idempotency_key","atomicity":"single transaction"}'::jsonb);
insert into ecos_meta.contract_schema values('https://contracts.ecos.invalid/v1/approval.request-request.schema.json','{"$schema":"https://json-schema.org/draft/2020-12/schema","$id":"https://contracts.ecos.invalid/v1/approval.request-request.schema.json","title":"approval.request-request","type":"object","properties":{"schema_version":{"const":"1.0.0"},"context":{"$ref":"https://contracts.ecos.invalid/v1/request_context.schema.json"},"arguments":{"type":"object","properties":{"id":{"type":"string","format":"uuid"},"subject_type":{"type":"string","enum":["party","project","task"]},"subject_id":{"type":"string","format":"uuid"},"subject_hash":{"type":"string","pattern":"^[a-f0-9]{64}$"},"expiration_mode":{"type":"string","enum":["expires","never"]},"expires_at":{"anyOf":[{"type":"string","format":"date-time"},{"type":"null"}]},"provenance":{"type":"array","minItems":1,"maxItems":50,"items":{"$ref":"https://contracts.ecos.invalid/v1/source_reference.schema.json"}}},"required":["id","subject_type","subject_id","subject_hash","expiration_mode","expires_at","provenance"],"additionalProperties":false}},"required":["schema_version","context","arguments"],"additionalProperties":false}'::jsonb);
insert into ecos_meta.operation_contract values('approval.request','{"name":"approval.request","request_schema":"https://contracts.ecos.invalid/v1/approval.request-request.schema.json","response_schema":"https://contracts.ecos.invalid/v1/phase2_result.schema.json","required_role":"operations_api","semantic_proposable":false,"idempotency_scope":"principal_id + operation + idempotency_key","atomicity":"single transaction"}'::jsonb);
insert into ecos_meta.contract_schema values('https://contracts.ecos.invalid/v1/sms.continuation.enqueue-request.schema.json','{"$schema":"https://json-schema.org/draft/2020-12/schema","$id":"https://contracts.ecos.invalid/v1/sms.continuation.enqueue-request.schema.json","title":"sms.continuation.enqueue-request","type":"object","properties":{"schema_version":{"const":"1.0.0"},"context":{"$ref":"https://contracts.ecos.invalid/v1/request_context.schema.json"},"arguments":{"type":"object","properties":{"communication_id":{"type":"string","format":"uuid"},"source_version":{"type":"integer","minimum":1},"task_id":{"type":"string","format":"uuid"}},"required":["communication_id","source_version","task_id"],"additionalProperties":false}},"required":["schema_version","context","arguments"],"additionalProperties":false}'::jsonb);
insert into ecos_meta.operation_contract values('sms.continuation.enqueue','{"name":"sms.continuation.enqueue","request_schema":"https://contracts.ecos.invalid/v1/sms.continuation.enqueue-request.schema.json","response_schema":"https://contracts.ecos.invalid/v1/phase2_result.schema.json","required_role":"operations_api","semantic_proposable":false,"idempotency_scope":"principal_id + operation + idempotency_key","atomicity":"single transaction"}'::jsonb);
insert into ecos_meta.contract_schema values('https://contracts.ecos.invalid/v1/sms.continuation.complete-request.schema.json','{"$schema":"https://json-schema.org/draft/2020-12/schema","$id":"https://contracts.ecos.invalid/v1/sms.continuation.complete-request.schema.json","title":"sms.continuation.complete-request","type":"object","properties":{"schema_version":{"const":"1.0.0"},"context":{"$ref":"https://contracts.ecos.invalid/v1/request_context.schema.json"},"arguments":{"type":"object","properties":{"fence":{"$ref":"https://contracts.ecos.invalid/v1/fence.schema.json"},"proposal_id":{"type":"string","format":"uuid"}},"required":["fence","proposal_id"],"additionalProperties":false}},"required":["schema_version","context","arguments"],"additionalProperties":false}'::jsonb);
insert into ecos_meta.operation_contract values('sms.continuation.complete','{"name":"sms.continuation.complete","request_schema":"https://contracts.ecos.invalid/v1/sms.continuation.complete-request.schema.json","response_schema":"https://contracts.ecos.invalid/v1/phase2_result.schema.json","required_role":"executor","semantic_proposable":false,"idempotency_scope":"principal_id + operation + idempotency_key","atomicity":"single transaction"}'::jsonb);
reset role;
