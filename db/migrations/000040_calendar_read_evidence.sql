-- Preserve evidence returned by the existing authenticated Calendar connector.
-- This operation has no Calendar mutation or provider-send path.
set local role ecos_owner;
alter function ecos_meta.apply_operation(text,jsonb,jsonb) rename to apply_operation_before_calendar_evidence;
create function ecos_meta.apply_operation(op text,ctx jsonb,args jsonb) returns jsonb
language plpgsql set search_path=pg_catalog as $$
declare c ecos.work_claim; scope_ jsonb; receipt_ ecos.provider_receipt; v jsonb;
 principal uuid:=(ctx->>'principal_id')::uuid; hash_ text;
begin
 if op<>'calendar.evidence.record' then return ecos_meta.apply_operation_before_calendar_evidence(op,ctx,args); end if;
 c:=ecos_meta.core_claim(ctx,args,array['calendar_sms_reminder']);
 select input->'calendar_scope' into scope_ from ecos.work_context where occurrence_id=c.occurrence_id;
 if scope_ is null or scope_->>'calendar_id' is distinct from args->>'calendar_id'
  or scope_->>'account_scope' is distinct from args->>'account_scope'
  or args->'event'->>'id' is null or args->'event'->>'etag' is null
  or octet_length((args->'event')::text)>6000 then raise exception 'forbidden' using errcode='42501'; end if;
 hash_:=ecos_meta.content_hash(args->'event');
 perform pg_advisory_xact_lock(hashtextextended('calendar:'||(args->>'account_scope')||':'||(args->>'calendar_id')||':'||(args->'event'->>'id'),0));
 select * into receipt_ from ecos.provider_receipt where provider='google_calendar' and account_scope=args->>'account_scope'
  and dedupe_key=(args->>'calendar_id')||':'||(args->'event'->>'id')||':'||hash_;
 if receipt_.id is null then
  insert into ecos.provider_receipt(provider,account_scope,provider_event_id,dedupe_key,provider_object_id,provider_occurred_at,
   received_at,raw_artifact_uri,raw_content_hash,signature_verified,correlation_id)
  values('google_calendar',args->>'account_scope',args->'event'->>'etag',(args->>'calendar_id')||':'||(args->'event'->>'id')||':'||hash_,
   args->'event'->>'id',(args->'event'->>'updated')::timestamptz,clock_timestamp(),
   'data:application/json;base64,'||replace(encode(convert_to((args->'event')::text,'UTF8'),'base64'),E'\n',''),
   hash_,false,(ctx->>'correlation_id')::uuid) returning * into receipt_;
  perform ecos_meta.core_inherit(principal,c.occurrence_id,'provider_receipt',receipt_.id);
 else perform ecos_meta.require_access(principal,'provider_receipt',receipt_.id); end if;
 v:=ecos_meta.record_value('provider_receipt',receipt_.id);
 return jsonb_build_object('schema_version','1.0.0','correlation_id',ctx->'correlation_id','status','committed','data',v);
end $$;
revoke all on all functions in schema ecos_meta from public;
reset role;

set local role ecos_owner;
insert into ecos_meta.contract_schema values('https://contracts.ecos.invalid/v1/calendar.evidence.record-request.schema.json','{"$schema":"https://json-schema.org/draft/2020-12/schema","$id":"https://contracts.ecos.invalid/v1/calendar.evidence.record-request.schema.json","type":"object","properties":{"schema_version":{"const":"1.0.0"},"context":{"$ref":"https://contracts.ecos.invalid/v1/request_context.schema.json"},"arguments":{"type":"object","properties":{"fence":{"$ref":"https://contracts.ecos.invalid/v1/fence.schema.json"},"account_scope":{"type":"string","minLength":1,"maxLength":200},"calendar_id":{"type":"string","minLength":1,"maxLength":200},"observed_at":{"type":"string","format":"date-time"},"event":{"type":"object"}},"required":["fence","account_scope","calendar_id","observed_at","event"],"additionalProperties":false}},"required":["schema_version","context","arguments"],"additionalProperties":false}'::jsonb);
insert into ecos_meta.operation_contract values('calendar.evidence.record','{"name":"calendar.evidence.record","request_schema":"https://contracts.ecos.invalid/v1/calendar.evidence.record-request.schema.json","response_schema":"https://contracts.ecos.invalid/v1/phase2_result.schema.json","required_role":"executor","semantic_proposable":false,"idempotency_scope":"principal_id + operation + idempotency_key","atomicity":"single transaction"}'::jsonb);
reset role;
