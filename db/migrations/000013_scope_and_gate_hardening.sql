set local role ecos_owner;
create index command_occurrence_by_occurrence on ecos.command_occurrence(occurrence_id);
create index emergency_intent_by_heartbeat on ecos.emergency_intent(heartbeat_id);
create index capability_attestation_lookup on ecos.executor_capability(capability_name,capability_version);
create index work_approval_request on ecos.work_approval(approval_request_id);
create index entity_contract_schema on ecos_meta.entity_contract(schema_id);
create index notification_policy_recipient on ecos_meta.notification_policy(recipient_party_id);
create index principal_binding_instance on ecos_meta.principal_binding(executor_instance_id);
create index principal_operation_name on ecos_meta.principal_operation(operation);
create unique index emergency_unknown_once on ecos.emergency_intent(executor_instance_id,condition) where heartbeat_id is null;
create function ecos_meta.gate_configuration_lock() returns trigger language plpgsql set search_path=pg_catalog as $$
begin perform pg_advisory_xact_lock(684026,20); return null; end $$;
do $$ declare n text; begin foreach n in array array['executor','executor_instance','executor_capability','stage_capability_requirement','work_definition','work_stage_definition','work_approval','approval_request','task_dependency','work_dependency'] loop
execute format('create trigger configuration_lock before insert or update or delete on ecos.%I for each statement execute function ecos_meta.gate_configuration_lock()',n); end loop; end $$;
create trigger configuration_lock before update on ecos_meta.control for each statement execute function ecos_meta.gate_configuration_lock();
create function ecos_meta.memory_version_guard() returns trigger language plpgsql set search_path=pg_catalog as $$
declare p ecos_meta.principal_binding; m ecos.memory_record; s ecos.memory_scope;
begin
 p:=ecos_meta.current_principal(); select * into m from ecos.memory_record where id=new.memory_record_id for update; select * into s from ecos.memory_scope where id=new.scope_id;
 if not s.authorized_role_names ? p.role_name::text then raise exception 'forbidden' using errcode='42501'; end if;
 if new.sensitivity<>s.sensitivity or new.supersedes_version_id is distinct from m.active_head_version_id or new.content_hash<>ecos_meta.content_hash(to_jsonb(new)) then raise exception 'invalid_contract' using errcode='22023'; end if;
 return new; end $$;
create trigger memory_guard before insert on ecos.memory_version for each row execute function ecos_meta.memory_version_guard();
-- Analytics is an explicit aggregate-only boundary; no access to raw operational rows.
revoke select on ecos.work_occurrence,ecos.outbox_item,ecos.v_work_health,ecos.v_outbox_health from read_only_analytics;
create function ecos.health_summary() returns jsonb language sql security definer set search_path=pg_catalog as $$
 select jsonb_build_object('as_of',statement_timestamp(),'work',(select coalesce(jsonb_agg(to_jsonb(w)),'[]') from ecos.v_work_health w),'outbox',(select coalesce(jsonb_agg(to_jsonb(o)),'[]') from ecos.v_outbox_health o)) $$;
grant execute on function ecos.health_summary() to read_only_analytics;
reset role;

set local role ecos_owner;
create or replace function ecos.operate(operation text,request jsonb) returns jsonb language plpgsql security definer set search_path=pg_catalog set timezone='UTC' as $$
declare p ecos_meta.principal_binding; ctx jsonb; args jsonb; hash_ text; prior ecos_meta.operation_receipt; result_ jsonb; response_name text; err text; detail_ text; code_ text; corr uuid;
begin
 ctx:=request->'context'; args:=request->'arguments'; corr:=(ctx->>'correlation_id')::uuid;
 if octet_length(request::text)>1048576 then raise exception 'invalid_contract' using errcode='22023'; end if;
 if not exists(select 1 from ecos_meta.operation_contract where name=operation) then raise exception 'invalid_contract' using errcode='22023'; end if;
 perform ecos_meta.assert_contract(operation||'-request',request);
 p:=ecos_meta.current_principal(); if not coalesce(ecos_meta.operation_authorized(operation,p.role_name),false) then raise exception 'forbidden' using errcode='42501'; end if;
 if p.principal_id::text<>ctx->>'principal_id' or p.executor_instance_id::text is distinct from ctx->>'executor_instance_id' then raise exception 'forbidden' using errcode='42501'; end if;
 if not exists(select 1 from ecos_meta.principal_operation po where po.principal_id=p.principal_id and po.operation=operate.operation) then raise exception 'forbidden' using errcode='42501'; end if;
 if not exists(select 1 from ecos_meta.database_identity where environment='development' and authority='non_production' and not provider_effects_enabled) then raise exception 'gate_blocked' using errcode='23514'; end if;
 hash_:=ecos_meta.content_hash(request);
 perform pg_advisory_xact_lock(hashtextextended(p.principal_id::text||':'||operation||':'||(ctx->>'idempotency_key'),0));
 select * into prior from ecos_meta.operation_receipt r where r.principal_id=p.principal_id and r.operation=operate.operation and r.idempotency_key=ctx->>'idempotency_key';
 if found then if prior.request_hash<>hash_ then raise exception 'idempotency_conflict' using errcode='23505'; end if; return prior.result; end if;
 if operation in ('approval.decide','task.transition','task.evidence.attach','proposal.commit') then perform pg_advisory_xact_lock(684026,20); else perform pg_advisory_xact_lock_shared(684026,20); end if;
 perform 1 from ecos_meta.control for share;
 if exists(select 1 from ecos_meta.control where maintenance) then raise exception 'gate_blocked' using errcode='23514'; end if;
 if operation='proposal.commit' then result_:=ecos_meta.commit_proposal(ctx,args->'proposal'); else result_:=ecos_meta.apply_operation(operation,ctx,args); end if;
 select split_part(split_part(document->>'response_schema','/v1/',2),'.schema.json',1) into response_name from ecos_meta.operation_contract where name=operation;
 perform ecos_meta.assert_contract(response_name,result_);
 insert into ecos_meta.operation_receipt values(p.principal_id,operation,ctx->>'idempotency_key',hash_,result_,clock_timestamp());
 insert into ecos_meta.operation_audit(operation,principal_id,correlation_id,causation_id,request_hash,result_hash) values(operation,p.principal_id,corr,(ctx->>'causation_id')::uuid,hash_,ecos_meta.content_hash(result_));
 return result_;
exception when others then
 get stacked diagnostics err=message_text,detail_=pg_exception_detail;
 code_:=case when err in ('invalid_contract','unauthenticated','forbidden','stale_version','invalid_transition','gate_blocked','idempotency_conflict','expired_fence','unknown_outcome') then err when sqlstate in ('22023','22P02','22007','22008') then 'invalid_contract' when sqlstate='42501' then 'forbidden' when sqlstate='23505' then 'idempotency_conflict' when sqlstate='40001' then 'stale_version' when sqlstate in ('23514','23503') then 'gate_blocked' else 'internal_error' end;
 return jsonb_build_object('code',code_,'message',code_||case when code_='internal_error' then ' ['||sqlstate||']' else '' end||case when detail_ like 'contract:%' then ' ('||detail_||')' else '' end,'correlation_id',coalesce(corr,gen_random_uuid()),'retryable',false);
end $$;

reset role;
