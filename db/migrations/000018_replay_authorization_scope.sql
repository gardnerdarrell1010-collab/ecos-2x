set local role ecos_owner;
create function ecos_meta.require_operation_scope(op text,args jsonb,principal uuid) returns void language plpgsql stable set search_path=pg_catalog as $$
declare ref jsonb; item jsonb; nested jsonb; target uuid; kind_ text;
begin
 if op in ('task.transition','task.evidence.attach') then perform ecos_meta.require_access(principal,'task',(args->>'task_id')::uuid);
 elsif op='approval.decide' then
  perform ecos_meta.require_access(principal,'approval_request',(args->>'approval_request_id')::uuid);
  select subject_type,subject_id into kind_,target from ecos.approval_request where id=(args->>'approval_request_id')::uuid;
  perform ecos_meta.require_access(principal,kind_,target);
 elsif op in ('work.renew','work.complete') then perform ecos_meta.require_access(principal,'work_occurrence',(args->'fence'->>'occurrence_id')::uuid);
 elsif op='memory.activate' then perform ecos_meta.require_access(principal,'memory_record',(args->>'memory_record_id')::uuid);
 elsif op='provider.result.record' then perform ecos_meta.require_access(principal,'provider_command',(args->'result'->>'provider_command_id')::uuid);
 elsif op='fact.record' then
  select record_type into kind_ from ecos_meta.object_grant where principal_id=principal and record_id=(args->>'subject_id')::uuid order by record_type limit 1;
  if kind_ is null then raise exception 'forbidden' using errcode='42501'; end if;
  perform ecos_meta.require_access(principal,kind_,(args->>'subject_id')::uuid);
 elsif op='proposal.commit' then
  for item in select value from jsonb_array_elements(args->'proposal'->'items') loop
   for nested in select value from jsonb_array_elements(item->'proposed_operations') loop
    if not exists(select 1 from ecos_meta.principal_operation where principal_id=principal and operation=nested->>'operation') then raise exception 'forbidden' using errcode='42501'; end if;
    perform ecos_meta.require_operation_scope(nested->>'operation',nested->'arguments',principal);
   end loop;
  end loop;
 end if;
 for ref in select value from jsonb_array_elements(coalesce(args->'source_references','[]')||coalesce(args->'new_version'->'provenance','[]')||coalesce(args->'new_version'->'authoritative_references','[]')||coalesce(args->'result'->'source_references','[]')) loop
  perform ecos_meta.require_access(principal,ref->>'record_type',(ref->>'record_id')::uuid);
 end loop;
end $$;
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
 perform ecos_meta.require_operation_scope(operation,args,p.principal_id);
 hash_:=ecos_meta.content_hash(request);
 perform pg_advisory_xact_lock(hashtextextended(p.principal_id::text||':'||operation||':'||(ctx->>'idempotency_key'),0));
 select * into prior from ecos_meta.operation_receipt r where r.principal_id=p.principal_id and r.operation=operate.operation and r.idempotency_key=ctx->>'idempotency_key';
 if found then if prior.request_hash<>hash_ then raise exception 'idempotency_conflict' using errcode='23505'; end if; if operation='work.claim' and prior.result->'claim'<>'null'::jsonb then perform ecos_meta.require_access(p.principal_id,'work_occurrence',(prior.result->'claim'->>'occurrence_id')::uuid); end if; return prior.result; end if;
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
