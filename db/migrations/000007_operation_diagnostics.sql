set local role ecos_owner;
create or replace function ecos_meta.assert_contract(name text,v jsonb) returns void language plpgsql stable set search_path=pg_catalog as $$
declare s jsonb;
begin select document into s from ecos_meta.contract_schema where schema_id='https://contracts.ecos.invalid/v1/'||name||'.schema.json';
 if s is null or not ecos_meta.valid_json(s,v) then raise exception 'invalid_contract' using errcode='22023',detail='contract:'||name; end if;
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
 hash_:=ecos_meta.content_hash(request);
 perform pg_advisory_xact_lock(hashtextextended(p.principal_id::text||':'||operation||':'||(ctx->>'idempotency_key'),0));
 select * into prior from ecos_meta.operation_receipt r where r.principal_id=p.principal_id and r.operation=operate.operation and r.idempotency_key=ctx->>'idempotency_key';
 if found then if prior.request_hash<>hash_ then raise exception 'idempotency_conflict' using errcode='23505'; end if; return prior.result; end if;
 if operation='approval.decide' then perform pg_advisory_xact_lock(684026,20); else perform pg_advisory_xact_lock_shared(684026,20); end if;
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
 return jsonb_build_object('code',code_,'message',code_||case when detail_ like 'contract:%' then ' ('||detail_||')' else '' end,'correlation_id',coalesce(corr,gen_random_uuid()),'retryable',false);
end $$;

reset role;
