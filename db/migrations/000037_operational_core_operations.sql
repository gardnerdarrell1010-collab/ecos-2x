-- Operations on existing operational entities. No executor, domain or queue creation.
set local role ecos_owner;

-- Core records need explicit object authority, not a fabricated provider domain.
alter function ecos_meta.require_access(uuid,text,uuid) rename to require_access_before_core;
create function ecos_meta.require_access(principal uuid,kind text,entity uuid) returns void
language plpgsql stable set search_path=pg_catalog as $$
begin
 if kind in ('task','task_schedule','task_dependency','task_assignment','project','party','relationship','notification','delivery','artifact','fact','memory_record','memory_version','memory_scope','task_evidence','export_package','backup_record','restore_test')
  and not exists(select 1 from ecos_meta.object_domain where record_type=kind and record_id=entity) then
  perform ecos_meta.require_access_phase2(principal,kind,entity); return;
 end if;
 if kind='work_occurrence' and not exists(select 1 from ecos_meta.object_domain where record_type=kind and record_id=entity)
  and exists(select 1 from ecos.work_occurrence o join ecos.work_stage_definition s on s.id=o.stage_definition_id where o.id=entity and s.execution_surface='ONLINE_SEMANTIC' and s.stage_key in ('task_coverage_proactive_control','outstanding_request_monitor','ai_task_bridge','incremental_continuity')) then
  perform ecos_meta.require_access_phase2(principal,kind,entity); return;
 end if;
 perform ecos_meta.require_access_before_core(principal,kind,entity);
end $$;

alter function ecos_meta.selection(uuid,uuid,timestamptz) rename to selection_before_core;
create function ecos_meta.selection(occurrence uuid,instance uuid,at_ timestamptz) returns jsonb
language plpgsql stable set search_path=pg_catalog as $$
declare result_ jsonb;
begin
 if not exists(select 1 from ecos_meta.object_domain where record_type='work_occurrence' and record_id=occurrence)
  and exists(select 1 from ecos.work_occurrence o join ecos.work_stage_definition s on s.id=o.stage_definition_id where o.id=occurrence and s.execution_surface='ONLINE_SEMANTIC' and s.stage_key in ('task_coverage_proactive_control','outstanding_request_monitor','ai_task_bridge','incremental_continuity')) then
  return ecos_meta.selection_phase2(occurrence,instance,at_);
 end if;
 result_:=ecos_meta.selection_before_core(occurrence,instance,at_);
 -- A028 is a batch consumer. Its delivery-level command is the replay fence;
 -- an ambiguous delivery must not freeze unrelated deliveries in that batch.
 if exists(select 1 from ecos.work_occurrence o join ecos.work_stage_definition s on s.id=o.stage_definition_id
   where o.id=occurrence and s.stage_key='sms_outbound_dispatch' and s.execution_surface='RESIDENT_DETERMINISTIC_PROVIDER')
  and not exists(select 1 from ecos.command_occurrence co join ecos.provider_command c on c.id=co.provider_command_id
   where co.occurrence_id=occurrence and c.outcome in ('accepted','unknown_outcome')
    and (c.provider<>'twilio' or c.command_type<>'sms.send' or not exists(
     select 1 from ecos.delivery d where d.provider_command_id=c.id and d.id=c.causation_id and d.channel='sms'))) then
  result_:=jsonb_set(result_,'{reason_codes}',(result_->'reason_codes')-'idempotency');
  result_:=jsonb_set(result_,'{eligible}',to_jsonb(jsonb_array_length(result_->'reason_codes')=0));
 end if;
 return result_;
end $$;

alter function ecos_meta.record_value(text,uuid,boolean) rename to record_value_before_core;
create function ecos_meta.record_value(kind text,entity uuid,lock_ boolean default false) returns jsonb
language plpgsql set search_path=pg_catalog as $$
declare v jsonb;
begin
 if kind not in ('notification','delivery','provider_receipt','provider_command','provider_attempt','export_package','backup_record','restore_test','memory_scope','task_schedule','task_dependency','task_assignment') then return ecos_meta.record_value_before_core(kind,entity,lock_); end if;
 execute format('select to_jsonb(t) from ecos.%I t where id=$1%s',kind,case when lock_ then ' for update' else '' end) into v using entity;
 if v is null then raise exception 'missing_reference' using errcode='23503'; end if;
 return v;
end $$;

create function ecos_meta.core_claim(ctx jsonb,args jsonb,stages text[]) returns ecos.work_claim
language plpgsql set search_path=pg_catalog as $$
declare c ecos.work_claim;
begin
 c:=ecos_meta.check_fence(ctx,args->'fence');
 perform ecos_meta.require_access((ctx->>'principal_id')::uuid,'work_occurrence',c.occurrence_id);
 if not exists(select 1 from ecos.work_stage_definition where id=c.stage_definition_id and stage_key=any(stages)) then
  raise exception 'forbidden' using errcode='42501';
 end if;
 return c;
end $$;

create function ecos_meta.core_inherit(principal uuid,occurrence uuid,kind text,entity uuid) returns void
language plpgsql set search_path=pg_catalog as $$
declare domain_ text;
begin
 select domain into domain_ from ecos_meta.object_domain where record_type='work_occurrence' and record_id=occurrence;
 if domain_ is null then
  insert into ecos_meta.object_grant values(principal,kind,entity) on conflict do nothing;
  return;
 end if;
 if exists(select 1 from ecos_meta.object_domain where record_type=kind and record_id=entity and domain<>domain_) then raise exception 'forbidden' using errcode='42501'; end if;
 insert into ecos_meta.object_domain values(kind,entity,domain_) on conflict do nothing;
 insert into ecos_meta.object_grant values(principal,kind,entity) on conflict do nothing;
end $$;

alter function ecos_meta.apply_operation(text,jsonb,jsonb) rename to apply_operation_before_core;
create function ecos_meta.core_sms_handoff(parent uuid,communication_ uuid) returns uuid
language plpgsql set search_path=pg_catalog as $$
declare target_ jsonb; stage_ ecos.work_stage_definition; comm ecos.communication;
 principal_ uuid; occurrence_ uuid; processing_ uuid; domain_ text;
begin
 select input->'sms_processing_target' into target_ from ecos.work_context where occurrence_id=parent;
 if target_ is null then return null; end if;
 principal_:=(target_->>'principal_id')::uuid;
 select * into stage_ from ecos.work_stage_definition where id=(target_->>'stage_id')::uuid;
 if stage_.stage_key is distinct from 'sms_inbound_process' or stage_.execution_surface is distinct from 'ONLINE_SEMANTIC'
  or not exists(select 1 from ecos.executor_instance i join ecos.executor e on e.id=i.executor_id
    where i.principal_id=principal_ and e.enabled and e.surface='ONLINE_SEMANTIC')
  or not exists(select 1 from ecos_meta.principal_operation where principal_id=principal_ and operation='sms.continuation.complete') then raise exception 'gate_blocked'; end if;
 select * into comm from ecos.communication where id=communication_ for update;
 select occurrence_id into occurrence_ from ecos.communication_processing where communication_id=comm.id and source_version=comm.record_version;
 if occurrence_ is not null then return occurrence_; end if;
 select domain into domain_ from ecos_meta.object_domain where record_type='communication' and record_id=comm.id;
 if domain_ is null or not exists(select 1 from ecos_meta.principal_domain where principal_id=principal_ and domain=domain_) then raise exception 'forbidden' using errcode='42501'; end if;
 occurrence_:=gen_random_uuid();processing_:=gen_random_uuid();
 insert into ecos.work_occurrence(id,work_definition_id,stage_definition_id,fulfillment_id,task_id,state,occurrence_key,due_at)
  values(occurrence_,stage_.work_definition_id,stage_.id,gen_random_uuid(),null,'pending','sms:'||comm.id::text||':'||comm.record_version::text,clock_timestamp());
 insert into ecos.communication_processing(id,communication_id,source_version,state,occurrence_id) values(processing_,comm.id,comm.record_version,'ready',occurrence_);
 insert into ecos_meta.object_domain values('work_occurrence',occurrence_,domain_),('communication_processing',processing_,domain_);
 insert into ecos_meta.object_grant values(principal_,'work_occurrence',occurrence_),(principal_,'communication_processing',processing_),
  (principal_,'communication',comm.id),(principal_,'provider_receipt',comm.receipt_id) on conflict do nothing;
 insert into ecos.work_context(occurrence_id,operation,source_references,input)
 values(occurrence_,'sms.continuation.complete',jsonb_build_array(jsonb_build_object('record_type','communication',
  'record_id',comm.id,'record_version',comm.record_version,'content_hash',ecos_meta.content_hash(to_jsonb(comm)),'authority','structured_ecos')),
  jsonb_build_object('communication_id',comm.id,'processing_id',processing_,
   'instructions',target_->>'instructions','delivery_principal_id',target_->>'delivery_principal_id'));
 return occurrence_;
end $$;

create function ecos_meta.apply_operation(op text,ctx jsonb,args jsonb) returns jsonb
language plpgsql set search_path=pg_catalog as $$
declare principal uuid:=(ctx->>'principal_id')::uuid; claim_ ecos.work_claim;
 v jsonb; prior jsonb; records_ jsonb:='[]'; kind text; item record;
 n ecos.notification; d ecos.delivery; receipt ecos.provider_receipt; comm ecos.communication;
 id_ uuid; hash_ text; key_ text; last_id uuid; delivery_principal uuid;
begin
 if op not in ('runtime.scope.read','notification.enqueue','sms.receipt.persist') then
  return ecos_meta.apply_operation_before_core(op,ctx,args);
 end if;
 if op='sms.receipt.persist' then
  claim_:=ecos_meta.core_claim(ctx,args,array['sms_transport_queue_consume']);
  perform ecos_meta.assert_contract('provider_receipt',args->'receipt');
  perform ecos_meta.assert_contract('communication',args->'communication');
  receipt:=jsonb_populate_record(null::ecos.provider_receipt,args->'receipt');
  comm:=jsonb_populate_record(null::ecos.communication,args->'communication');
  if receipt.provider<>'twilio' or receipt.provider_object_id is null
   or comm.receipt_id<>receipt.id or comm.channel<>'sms' or comm.direction<>'inbound'
   or length(btrim(args->>'queue_item'))=0 then raise exception 'invalid_contract'; end if;
  perform pg_advisory_xact_lock(hashtextextended(receipt.provider||':'||receipt.account_scope||':'||receipt.dedupe_key,0));
  select to_jsonb(r) into prior from ecos.provider_receipt r where provider=receipt.provider and account_scope=receipt.account_scope and dedupe_key=receipt.dedupe_key;
  if prior is not null then
   if prior->>'raw_content_hash'<>receipt.raw_content_hash or prior->>'provider_object_id'<>receipt.provider_object_id then raise exception 'idempotency_conflict' using errcode='23505'; end if;
   receipt.id:=(prior->>'id')::uuid;
   perform ecos_meta.require_access(principal,'provider_receipt',receipt.id);
   select * into comm from ecos.communication where receipt_id=receipt.id;
   if comm.id is null then raise exception 'gate_blocked'; end if;
   perform ecos_meta.require_access(principal,'communication',comm.id);
  else
   perform ecos_meta.insert_wire('provider_receipt',args->'receipt');
   perform ecos_meta.insert_wire('communication',args->'communication');
   perform ecos_meta.core_inherit(principal,claim_.occurrence_id,'provider_receipt',receipt.id);
   perform ecos_meta.core_inherit(principal,claim_.occurrence_id,'communication',comm.id);
  end if;
  v:=jsonb_build_object('receipt',ecos_meta.record_value('provider_receipt',receipt.id),'communication',ecos_meta.record_value('communication',comm.id),'queue_item',args->'queue_item',
   'processing_occurrence_id',ecos_meta.core_sms_handoff(claim_.occurrence_id,comm.id));
 elsif op='runtime.scope.read' then
  claim_:=ecos_meta.core_claim(ctx,args,array['task_coverage_proactive_control','outstanding_request_monitor','ai_task_bridge','calendar_sms_reminder','sms_inbound_process','incremental_continuity','sms_outbound_dispatch']);
  kind:=args->>'record_type';
  if kind not in ('task','task_schedule','task_dependency','task_assignment','project','notification','delivery','communication','provider_receipt','party','relationship','memory_record','memory_version','artifact') then raise exception 'invalid_contract'; end if;
  -- Paging scans only explicit object grants; capabilities never authorize records.
  for item in select record_id from ecos_meta.object_grant where principal_id=principal and record_type=kind
    and ((args->>'after_id') is null or record_id>(args->>'after_id')::uuid) order by record_id limit (args->>'limit')::integer loop
   perform ecos_meta.require_access(principal,kind,item.record_id);
   v:=ecos_meta.record_value(kind,item.record_id);
   records_:=records_||jsonb_build_array(jsonb_build_object('record',v,'content_hash',ecos_meta.content_hash(v)));
   last_id:=item.record_id;
  end loop;
  v:=jsonb_build_object('records',records_,'last_scanned_id',last_id,'scope','explicit_object_grants');
 elsif op='notification.enqueue' then
  claim_:=ecos_meta.core_claim(ctx,args,array['task_coverage_proactive_control','outstanding_request_monitor','ai_task_bridge','calendar_sms_reminder','sms_inbound_process','sms_continuation']);
  perform ecos_meta.assert_contract('notification',args->'notification');
  perform ecos_meta.assert_contract('delivery',args->'delivery');
  n:=jsonb_populate_record(null::ecos.notification,args->'notification');
  d:=jsonb_populate_record(null::ecos.delivery,args->'delivery');
  perform ecos_meta.require_access(principal,n.subject_type,n.subject_id);
  perform ecos_meta.require_access(principal,'party',d.recipient_party_id);
  perform ecos_meta.verify_sources(principal,args->'source_references');
  if jsonb_array_length(args->'source_references')=0 or d.notification_id<>n.id or d.state<>'planned'
   or d.provider_command_id is not null or n.record_version<>1 or d.record_version<>1 then raise exception 'invalid_contract'; end if;
  if d.approval_request_id is not null then perform ecos_meta.require_access(principal,'approval_request',d.approval_request_id); end if;
  key_:=n.subject_type||':'||n.subject_id::text||':'||d.recipient_party_id::text||':'||d.channel||':'||d.policy_key;
  perform pg_advisory_xact_lock(hashtextextended(key_,0));
  select to_jsonb(x) into prior from ecos.delivery x join ecos.notification y on y.id=x.notification_id
    where y.subject_type=n.subject_type and y.subject_id=n.subject_id and x.recipient_party_id=d.recipient_party_id and x.channel=d.channel and x.policy_key=d.policy_key;
  if prior is not null then
   id_:=(prior->>'notification_id')::uuid;
   perform ecos_meta.require_access(principal,'notification',id_);
   perform ecos_meta.require_access(principal,'delivery',(prior->>'id')::uuid);
   if (select content_hash from ecos.notification where id=id_)<>n.content_hash or prior->>'destination_reference'<>d.destination_reference then raise exception 'idempotency_conflict' using errcode='23505'; end if;
   n.id:=id_;d.id:=(prior->>'id')::uuid;
  else
   perform ecos_meta.insert_wire('notification',args->'notification');
   perform ecos_meta.insert_wire('delivery',args->'delivery');
   perform ecos_meta.core_inherit(principal,claim_.occurrence_id,'notification',n.id);
   perform ecos_meta.core_inherit(principal,claim_.occurrence_id,'delivery',d.id);
   select (input->>'delivery_principal_id')::uuid into delivery_principal from ecos.work_context where occurrence_id=claim_.occurrence_id;
   if delivery_principal is not null then
    if not exists(select 1 from ecos.executor_instance i join ecos.executor e on e.id=i.executor_id
     where i.principal_id=delivery_principal and e.enabled and e.surface='RESIDENT_DETERMINISTIC_PROVIDER')
     or not exists(select 1 from ecos_meta.principal_operation where principal_id=delivery_principal and operation='sms.dispatch.begin') then raise exception 'gate_blocked'; end if;
    insert into ecos_meta.object_grant values(delivery_principal,'notification',n.id),(delivery_principal,'delivery',d.id) on conflict do nothing;
    if d.approval_request_id is not null then
     insert into ecos_meta.object_grant values(delivery_principal,'approval_request',d.approval_request_id) on conflict do nothing;
    end if;
   end if;
  end if;
  v:=jsonb_build_object('notification',ecos_meta.record_value('notification',n.id),'delivery',ecos_meta.record_value('delivery',d.id));
 end if;
 return jsonb_build_object('schema_version','1.0.0','correlation_id',ctx->'correlation_id','status','committed','data',v);
end $$;
revoke all on all functions in schema ecos_meta from public;
reset role;

set local role ecos_owner;
alter function ecos_meta.apply_operation(text,jsonb,jsonb) rename to apply_operation_before_core_review;
create function ecos_meta.apply_operation(op text,ctx jsonb,args jsonb) returns jsonb
language plpgsql set search_path=pg_catalog as $$
declare principal uuid:=(ctx->>'principal_id')::uuid; claim_ ecos.work_claim;
 proposal_ jsonb; committed_ jsonb; p ecos.communication_processing; v jsonb; event_ record;
begin
 if op not in ('core.review.commit','sms.continuation.complete') then
  return ecos_meta.apply_operation_before_core_review(op,ctx,args);
 end if;
 if op='sms.continuation.complete' then
  claim_:=ecos_meta.core_claim(ctx,args,array['sms_continuation','sms_inbound_process']);
  select * into p from ecos.communication_processing where occurrence_id=claim_.occurrence_id for update;
  if p.id is null or p.state<>'ready' then raise exception 'gate_blocked'; end if;
  perform ecos_meta.require_access(principal,'communication_processing',p.id);
  perform ecos_meta.require_access(principal,'communication',p.communication_id);
 else
  claim_:=ecos_meta.core_claim(ctx,args,array['task_coverage_proactive_control','outstanding_request_monitor','ai_task_bridge','calendar_sms_reminder']);
 end if;
 if not exists(select 1 from ecos.work_stage_definition where id=claim_.stage_definition_id and execution_surface='ONLINE_SEMANTIC') then raise exception 'forbidden' using errcode='42501'; end if;
 select proposal into proposal_ from ecos.proposal_submission where proposal_id=(args->>'proposal_id')::uuid
  and occurrence_id=claim_.occurrence_id and principal_id=principal;
 if proposal_ is null then raise exception 'gate_blocked'; end if;
 if op='sms.continuation.complete' and not exists(select 1 from jsonb_array_elements(proposal_->'source_references') ref
  where ref->>'record_type'='communication' and ref->>'record_id'=p.communication_id::text and (ref->>'record_version')::bigint=p.source_version) then raise exception 'invalid_contract'; end if;
 perform ecos_meta.verify_sources(principal,(select source_references from ecos.work_context where occurrence_id=claim_.occurrence_id));
 committed_:=ecos_meta.commit_proposal(ctx,proposal_);
 if exists(select 1 from jsonb_array_elements(committed_->'items') i where i->>'state'<>'committed') then raise exception 'gate_blocked'; end if;
 for event_ in select ev.aggregate_type,ev.aggregate_id from jsonb_array_elements(committed_->'items') i
  cross join lateral jsonb_array_elements_text(i->'committed_event_ids') event_id
  join ecos.domain_event ev on ev.id=event_id::uuid where ev.aggregate_type='fact'
 loop perform ecos_meta.core_inherit(principal,claim_.occurrence_id,event_.aggregate_type,event_.aggregate_id); end loop;
 if op='sms.continuation.complete' then
  update ecos.communication_processing set state='running',proposal_id=(args->>'proposal_id')::uuid,record_version=record_version+1 where id=p.id;
  update ecos.communication_processing set state='succeeded',record_version=record_version+1 where id=p.id;
  v:=ecos_meta.record_value('communication_processing',p.id);
 else v:=committed_; end if;
 return jsonb_build_object('schema_version','1.0.0','correlation_id',ctx->'correlation_id','status','committed','data',v);
end $$;
insert into ecos_meta.contract_schema
 select 'https://contracts.ecos.invalid/v1/core.review.commit-request.schema.json',
  jsonb_set(document,'{$id}','"https://contracts.ecos.invalid/v1/core.review.commit-request.schema.json"')
 from ecos_meta.contract_schema where schema_id='https://contracts.ecos.invalid/v1/sms.continuation.complete-request.schema.json';
insert into ecos_meta.operation_contract values('core.review.commit',
 '{"name":"core.review.commit","request_schema":"https://contracts.ecos.invalid/v1/core.review.commit-request.schema.json","response_schema":"https://contracts.ecos.invalid/v1/phase2_result.schema.json","required_role":"executor","semantic_proposable":false,"idempotency_scope":"principal_id + operation + idempotency_key","atomicity":"single transaction"}');
revoke all on all functions in schema ecos_meta from public;
reset role;

set local role ecos_owner;
alter function ecos_meta.apply_operation(text,jsonb,jsonb) rename to apply_operation_core_records;
create function ecos_meta.apply_operation(op text,ctx jsonb,args jsonb) returns jsonb
language plpgsql set search_path=pg_catalog as $$
declare principal uuid:=(ctx->>'principal_id')::uuid; claim_ ecos.work_claim;
 d ecos.delivery; n ecos.notification; cmd ecos.provider_command; approval ecos.approval_request;
 attempt_ uuid; v jsonb; request_ jsonb; hash_ text;
begin
 if op not in ('sms.dispatch.begin','sms.dispatch.readback') then return ecos_meta.apply_operation_core_records(op,ctx,args); end if;
 claim_:=ecos_meta.core_claim(ctx,args,array['sms_outbound_dispatch']);
 perform ecos_meta.require_access(principal,'delivery',(args->>'delivery_id')::uuid);
 select * into d from ecos.delivery where id=(args->>'delivery_id')::uuid for update;
 perform ecos_meta.require_access(principal,'notification',d.notification_id);
 select * into n from ecos.notification where id=d.notification_id;
 if op='sms.dispatch.readback' then
  if d.provider_command_id is null or not exists(select 1 from ecos.provider_result where provider_command_id=d.provider_command_id and provider_object_id ~ '^SM[0-9a-fA-F]{32}$' and (outcome='succeeded' or reconciled_outcome='succeeded')) then raise exception 'gate_blocked'; end if;
  v:=jsonb_build_object('delivery',to_jsonb(d),'provider_acceptance',true);
 else
  if d.provider_command_id is not null then
   perform ecos_meta.require_access(principal,'provider_command',d.provider_command_id);
   select * into cmd from ecos.provider_command where id=d.provider_command_id;
   if exists(select 1 from ecos.provider_result where provider_command_id=cmd.id and provider_object_id ~ '^SM[0-9a-fA-F]{32}$' and (outcome='succeeded' or reconciled_outcome='succeeded')) then
    v:=jsonb_build_object('disposition','completed','command_id',cmd.id);
   else v:=jsonb_build_object('disposition','hold','command_id',cmd.id); end if;
  else
   if d.channel<>'sms' or d.state not in ('planned','ready') or d.record_version<>(args->>'expected_version')::bigint then raise exception 'gate_blocked'; end if;
   request_:=args->'request';
   if request_->>'to' is distinct from d.destination_reference or request_->>'to' !~ '^\+[1-9][0-9]{7,14}$'
    or request_->>'from' !~ '^\+[1-9][0-9]{7,14}$' or encode(sha256(convert_to(request_->>'body','UTF8')),'hex')<>n.content_hash then raise exception 'invalid_contract'; end if;
   if d.approval_request_id is not null then
    perform ecos_meta.require_access(principal,'approval_request',d.approval_request_id);
    select * into approval from ecos.approval_request where id=d.approval_request_id for share;
    if approval.state<>'approved' or (approval.expires_at is not null and approval.expires_at<=clock_timestamp())
     or approval.subject_type<>'delivery' or approval.subject_id<>d.id or approval.subject_hash<>ecos_meta.content_hash(to_jsonb(d))
     or not exists(select 1 from ecos.approval_decision where approval_request_id=approval.id and decision='approved') then raise exception 'gate_blocked'; end if;
   end if;
   if d.state='planned' then
    if d.approval_request_id is null and not exists(select 1 from ecos_meta.notification_policy p
     where n.subject_type='task' and p.task_id=n.subject_id and p.recipient_party_id=d.recipient_party_id
      and p.channel='sms' and p.destination_reference=d.destination_reference and p.policy_key=d.policy_key
      and p.content_hash=n.content_hash) then raise exception 'gate_blocked'; end if;
    update ecos.delivery set state='ready',record_version=record_version+1 where id=d.id;
   end if;
   hash_:=ecos_meta.content_hash(request_);
   insert into ecos.provider_command(provider,account_scope,command_type,idempotency_key,request_schema_id,request_artifact_uri,request_hash,correlation_id,causation_id,outcome,reconciliation_strategy,approval_request_id)
    values('twilio',args->>'account_scope','sms.send','delivery:'||d.id::text,'ecos.sms.send.v1',
     'data:application/json;base64,'||replace(encode(convert_to(request_::text,'UTF8'),'base64'),E'\n',''),
     hash_,(ctx->>'correlation_id')::uuid,d.id,'pending','manual_only',d.approval_request_id) returning * into cmd;
   perform ecos_meta.core_inherit(principal,claim_.occurrence_id,'provider_command',cmd.id);
   insert into ecos.command_occurrence values(cmd.id,claim_.occurrence_id);
   insert into ecos.provider_attempt(provider_command_id,attempt_number,request_hash,started_at,outcome) values(cmd.id,1,hash_,clock_timestamp(),'unknown_outcome') returning id into attempt_;
   perform ecos_meta.core_inherit(principal,claim_.occurrence_id,'provider_attempt',attempt_);
   update ecos.provider_command set outcome='unknown_outcome',record_version=record_version+1 where id=cmd.id;
   update ecos.delivery set provider_command_id=cmd.id,record_version=record_version+1 where id=d.id;
   -- The existing immutable command retains the complete request before dispatch.
   v:=jsonb_build_object('disposition','dispatch','command_id',cmd.id,'attempt_id',attempt_,'request_hash',hash_);
  end if;
 end if;
 return jsonb_build_object('schema_version','1.0.0','correlation_id',ctx->'correlation_id','status','committed','data',v);
end $$;
revoke all on all functions in schema ecos_meta from public;
reset role;

set local role ecos_owner;
insert into ecos_meta.contract_schema values('https://contracts.ecos.invalid/v1/runtime.scope.read-request.schema.json','{"$schema":"https://json-schema.org/draft/2020-12/schema","$id":"https://contracts.ecos.invalid/v1/runtime.scope.read-request.schema.json","type":"object","properties":{"schema_version":{"const":"1.0.0"},"context":{"$ref":"https://contracts.ecos.invalid/v1/request_context.schema.json"},"arguments":{"type":"object","properties":{"fence":{"$ref":"https://contracts.ecos.invalid/v1/fence.schema.json"},"record_type":{"type":"string","enum":["task","task_schedule","task_dependency","task_assignment","project","notification","delivery","communication","provider_receipt","party","relationship","memory_record","memory_version","artifact"]},"after_id":{"anyOf":[{"type":"string","format":"uuid"},{"type":"null"}]},"limit":{"type":"integer","minimum":1,"maximum":100}},"required":["fence","record_type","after_id","limit"],"additionalProperties":false}},"required":["schema_version","context","arguments"],"additionalProperties":false}'::jsonb);
insert into ecos_meta.operation_contract values('runtime.scope.read','{"name":"runtime.scope.read","request_schema":"https://contracts.ecos.invalid/v1/runtime.scope.read-request.schema.json","response_schema":"https://contracts.ecos.invalid/v1/phase2_result.schema.json","required_role":"executor","semantic_proposable":false,"idempotency_scope":"principal_id + operation + idempotency_key","atomicity":"single transaction"}'::jsonb);
insert into ecos_meta.contract_schema values('https://contracts.ecos.invalid/v1/notification.enqueue-request.schema.json','{"$schema":"https://json-schema.org/draft/2020-12/schema","$id":"https://contracts.ecos.invalid/v1/notification.enqueue-request.schema.json","type":"object","properties":{"schema_version":{"const":"1.0.0"},"context":{"$ref":"https://contracts.ecos.invalid/v1/request_context.schema.json"},"arguments":{"type":"object","properties":{"fence":{"$ref":"https://contracts.ecos.invalid/v1/fence.schema.json"},"notification":{"$ref":"https://contracts.ecos.invalid/v1/notification.schema.json"},"delivery":{"$ref":"https://contracts.ecos.invalid/v1/delivery.schema.json"},"source_references":{"type":"array","minItems":1,"maxItems":50,"items":{"$ref":"https://contracts.ecos.invalid/v1/source_reference.schema.json"}}},"required":["fence","notification","delivery","source_references"],"additionalProperties":false}},"required":["schema_version","context","arguments"],"additionalProperties":false}'::jsonb);
insert into ecos_meta.operation_contract values('notification.enqueue','{"name":"notification.enqueue","request_schema":"https://contracts.ecos.invalid/v1/notification.enqueue-request.schema.json","response_schema":"https://contracts.ecos.invalid/v1/phase2_result.schema.json","required_role":"executor","semantic_proposable":false,"idempotency_scope":"principal_id + operation + idempotency_key","atomicity":"single transaction"}'::jsonb);
insert into ecos_meta.contract_schema values('https://contracts.ecos.invalid/v1/sms.receipt.persist-request.schema.json','{"$schema":"https://json-schema.org/draft/2020-12/schema","$id":"https://contracts.ecos.invalid/v1/sms.receipt.persist-request.schema.json","type":"object","properties":{"schema_version":{"const":"1.0.0"},"context":{"$ref":"https://contracts.ecos.invalid/v1/request_context.schema.json"},"arguments":{"type":"object","properties":{"fence":{"$ref":"https://contracts.ecos.invalid/v1/fence.schema.json"},"receipt":{"$ref":"https://contracts.ecos.invalid/v1/provider_receipt.schema.json"},"communication":{"$ref":"https://contracts.ecos.invalid/v1/communication.schema.json"},"queue_item":{"type":"string","minLength":1,"maxLength":10000}},"required":["fence","receipt","communication","queue_item"],"additionalProperties":false}},"required":["schema_version","context","arguments"],"additionalProperties":false}'::jsonb);
insert into ecos_meta.operation_contract values('sms.receipt.persist','{"name":"sms.receipt.persist","request_schema":"https://contracts.ecos.invalid/v1/sms.receipt.persist-request.schema.json","response_schema":"https://contracts.ecos.invalid/v1/phase2_result.schema.json","required_role":"executor","semantic_proposable":false,"idempotency_scope":"principal_id + operation + idempotency_key","atomicity":"single transaction"}'::jsonb);
insert into ecos_meta.contract_schema values('https://contracts.ecos.invalid/v1/sms.dispatch.begin-request.schema.json','{"$schema":"https://json-schema.org/draft/2020-12/schema","$id":"https://contracts.ecos.invalid/v1/sms.dispatch.begin-request.schema.json","type":"object","properties":{"schema_version":{"const":"1.0.0"},"context":{"$ref":"https://contracts.ecos.invalid/v1/request_context.schema.json"},"arguments":{"type":"object","properties":{"fence":{"$ref":"https://contracts.ecos.invalid/v1/fence.schema.json"},"delivery_id":{"type":"string","format":"uuid"},"expected_version":{"type":"integer","minimum":1},"account_scope":{"type":"string","minLength":1,"maxLength":10000},"request":{"type":"object","properties":{"to":{"type":"string","minLength":1,"maxLength":10000},"from":{"type":"string","minLength":1,"maxLength":10000},"body":{"type":"string","minLength":1,"maxLength":1600}},"required":["to","from","body"],"additionalProperties":false}},"required":["fence","delivery_id","expected_version","account_scope","request"],"additionalProperties":false}},"required":["schema_version","context","arguments"],"additionalProperties":false}'::jsonb);
insert into ecos_meta.operation_contract values('sms.dispatch.begin','{"name":"sms.dispatch.begin","request_schema":"https://contracts.ecos.invalid/v1/sms.dispatch.begin-request.schema.json","response_schema":"https://contracts.ecos.invalid/v1/phase2_result.schema.json","required_role":"executor","semantic_proposable":false,"idempotency_scope":"principal_id + operation + idempotency_key","atomicity":"single transaction"}'::jsonb);
insert into ecos_meta.contract_schema values('https://contracts.ecos.invalid/v1/sms.dispatch.readback-request.schema.json','{"$schema":"https://json-schema.org/draft/2020-12/schema","$id":"https://contracts.ecos.invalid/v1/sms.dispatch.readback-request.schema.json","type":"object","properties":{"schema_version":{"const":"1.0.0"},"context":{"$ref":"https://contracts.ecos.invalid/v1/request_context.schema.json"},"arguments":{"type":"object","properties":{"fence":{"$ref":"https://contracts.ecos.invalid/v1/fence.schema.json"},"delivery_id":{"type":"string","format":"uuid"}},"required":["fence","delivery_id"],"additionalProperties":false}},"required":["schema_version","context","arguments"],"additionalProperties":false}'::jsonb);
insert into ecos_meta.operation_contract values('sms.dispatch.readback','{"name":"sms.dispatch.readback","request_schema":"https://contracts.ecos.invalid/v1/sms.dispatch.readback-request.schema.json","response_schema":"https://contracts.ecos.invalid/v1/phase2_result.schema.json","required_role":"executor","semantic_proposable":false,"idempotency_scope":"principal_id + operation + idempotency_key","atomicity":"single transaction"}'::jsonb);
reset role;
