-- Private operation entry point. Authenticated SQL role is bound server-side, never by request.
create function ecos.operate(operation text,request jsonb) returns jsonb language plpgsql security definer set search_path=pg_catalog set timezone='UTC' as $$
declare p ecos_meta.principal_binding; ctx jsonb; args jsonb; hash_ text; prior ecos_meta.operation_receipt; result_ jsonb; response_name text; err text; code_ text; corr uuid;
begin
 ctx:=request->'context'; args:=request->'arguments'; corr:=(ctx->>'correlation_id')::uuid;
 if octet_length(request::text)>1048576 then raise exception 'invalid_contract' using errcode='22023'; end if;
 if not exists(select 1 from ecos_meta.operation_contract where name=operation) then raise exception 'invalid_contract' using errcode='22023'; end if;
 perform ecos_meta.assert_contract(operation||'-request',request);
 p:=ecos_meta.current_principal();
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
 get stacked diagnostics err=message_text;
 code_:=case when err in ('invalid_contract','unauthenticated','forbidden','stale_version','invalid_transition','gate_blocked','idempotency_conflict','expired_fence','unknown_outcome') then err when sqlstate in ('22023','22P02','22007','22008') then 'invalid_contract' when sqlstate='42501' then 'forbidden' when sqlstate='23505' then 'idempotency_conflict' when sqlstate='40001' then 'stale_version' when sqlstate in ('23514','23503') then 'gate_blocked' else 'internal_error' end;
 return jsonb_build_object('code',code_,'message',code_,'correlation_id',coalesce(corr,gen_random_uuid()),'retryable',false);
end $$;
create function ecos.read_record(kind text,entity uuid) returns jsonb language plpgsql security definer set search_path=pg_catalog set timezone='UTC' as $$
declare p ecos_meta.principal_binding; v jsonb;
begin p:=ecos_meta.current_principal(); perform ecos_meta.require_access(p.principal_id,kind,entity); v:=ecos_meta.record_value(kind,entity); return jsonb_build_object('record',v,'content_hash',ecos_meta.content_hash(v)); end $$;
create function ecos.record_heartbeat(observed timestamptz,evidence_hash text) returns uuid language plpgsql security definer set search_path=pg_catalog as $$
declare p ecos_meta.principal_binding; id_ uuid;
begin p:=ecos_meta.current_principal(); if p.executor_instance_id is null or observed>clock_timestamp()+interval '5 seconds' then raise exception 'forbidden' using errcode='42501'; end if;
 insert into ecos.heartbeat(executor_instance_id,observed_at,received_at,valid_until,availability,evidence_hash) values(p.executor_instance_id,observed,clock_timestamp(),clock_timestamp()+interval '60 seconds','available',evidence_hash) returning id into id_; return id_; end $$;
create function ecos.claim_outbox(lease_seconds integer default 30) returns jsonb language plpgsql security definer set search_path=pg_catalog as $$
declare p ecos_meta.principal_binding; o ecos.outbox_item; tok uuid:=gen_random_uuid();
begin p:=ecos_meta.current_principal();
 if lease_seconds not between 1 and 300 then raise exception 'invalid_contract'; end if;
 if not exists(select 1 from ecos_meta.principal_operation where principal_id=p.principal_id and operation='provider.result.record') then raise exception 'forbidden' using errcode='42501'; end if;
 perform 1 from ecos_meta.control for share; if exists(select 1 from ecos_meta.control where maintenance) then return null; end if;
 select b.* into o from ecos.outbox_item b where b.available_at<=clock_timestamp() and (b.state in ('pending','retry_wait') or (b.state='claimed' and b.lease_expires_at<=clock_timestamp()))
 and (b.provider_command_id is null or exists(select 1 from ecos_meta.object_grant where principal_id=p.principal_id and record_type='provider_command' and record_id=b.provider_command_id))
 and not exists(select 1 from ecos.provider_command c where c.id=b.provider_command_id and c.outcome<>'pending')
 order by b.available_at,b.id for update skip locked limit 1;
 if o.id is null then return null; end if;
 update ecos.outbox_item set state='claimed',lease_expires_at=clock_timestamp()+make_interval(secs=>lease_seconds),attempt_count=attempt_count+1,record_version=record_version+1 where id=o.id returning * into o;
 insert into ecos_meta.outbox_lease values(o.id,tok,p.principal_id) on conflict(item_id) do update set token=excluded.token,principal_id=excluded.principal_id;
 return jsonb_build_object('item',to_jsonb(o),'lease_token',tok);
end $$;
create function ecos.ack_outbox(item uuid,token uuid) returns void language plpgsql security definer set search_path=pg_catalog as $$
declare p ecos_meta.principal_binding; o ecos.outbox_item;
begin p:=ecos_meta.current_principal(); select * into o from ecos.outbox_item where id=item for update;
 if o.state<>'claimed' or o.lease_expires_at<=clock_timestamp() or not exists(select 1 from ecos_meta.outbox_lease where item_id=item and outbox_lease.token=ack_outbox.token and principal_id=p.principal_id) then raise exception 'expired_fence' using errcode='40001'; end if;
 if o.provider_command_id is not null and not exists(select 1 from ecos.provider_command c where c.id=o.provider_command_id and (c.outcome='succeeded' or (c.outcome='reconciled' and exists(select 1 from ecos.provider_result r where r.provider_command_id=c.id and reconciled_outcome='succeeded')))) then raise exception 'unknown_outcome' using errcode='23514'; end if;
 update ecos.outbox_item set state='delivered',lease_expires_at=null,record_version=record_version+1 where id=item;
end $$;
create function ecos.begin_synthetic_attempt(command uuid,request_hash_ text) returns uuid language plpgsql security definer set search_path=pg_catalog as $$
declare p ecos_meta.principal_binding; c ecos.provider_command; id_ uuid;
begin p:=ecos_meta.current_principal(); perform ecos_meta.require_access(p.principal_id,'provider_command',command);
 select * into c from ecos.provider_command where id=command for update;
 if c.provider<>'synthetic' or c.account_scope<>'development' or c.request_hash<>request_hash_ or c.outcome<>'pending' then raise exception 'unknown_outcome' using errcode='23514'; end if;
 -- Before any simulated effect, hold the command unknown. A consumer crash cannot cause blind resend.
 insert into ecos.provider_attempt(provider_command_id,attempt_number,request_hash,started_at,completed_at,provider_request_id,response_hash,error_class,outcome) values(command,coalesce((select max(attempt_number) from ecos.provider_attempt where provider_command_id=command),0)+1,request_hash_,clock_timestamp(),null,null,null,'ambiguous','unknown_outcome') returning id into id_;
 update ecos.provider_command set outcome='unknown_outcome',record_version=record_version+1 where id=command;
 return id_; end $$;
create view ecos.v_node_health with(security_invoker=true) as select i.id executor_instance_id,i.boot_id,h.id heartbeat_id,h.received_at,h.valid_until,case when h.id is null then 'unknown' when h.valid_until<=clock_timestamp() then 'unavailable' else h.availability end availability from ecos.executor_instance i left join lateral(select * from ecos.heartbeat where executor_instance_id=i.id order by received_at desc,id desc limit 1) h on true;
create view ecos.v_work_health with(security_invoker=true) as select state,stage_definition_id,count(*) occurrences,min(due_at) oldest_due_at from ecos.work_occurrence group by state,stage_definition_id;
create view ecos.v_outbox_health with(security_invoker=true) as select destination,state,count(*) items,min(created_at) oldest_committed_at,min(lease_expires_at) earliest_lease_expiry from ecos.outbox_item group by destination,state;
create view ecos.v_provider_reconciliation with(security_invoker=true) as select id,provider,outcome,reconciliation_strategy,created_at from ecos.provider_command where outcome='unknown_outcome';
create view ecos.v_memory_heads with(security_invoker=true) as select m.memory_kind,v.* from ecos.memory_record m join ecos.memory_version v on v.id=m.active_head_version_id;
create function ecos_meta.watchdog(correlation uuid) returns bigint language plpgsql set search_path=pg_catalog as $$
declare n bigint;
begin insert into ecos.emergency_intent(executor_instance_id,heartbeat_id,condition,correlation_id) select executor_instance_id,heartbeat_id,'stale_heartbeat',correlation from ecos.v_node_health where availability in ('unknown','unavailable') on conflict do nothing; get diagnostics n=row_count; return n; end $$;
create function ecos_meta.repair_expired_claim(oid uuid,correlation uuid) returns uuid language plpgsql set search_path=pg_catalog as $$
declare before_ jsonb; after_ jsonb; finding uuid;
begin perform 1 from ecos.work_occurrence where id=oid for update;
 select jsonb_agg(to_jsonb(c) order by id) into before_ from ecos.work_claim c where occurrence_id=oid and state='active' and expires_at<=clock_timestamp(); if before_ is null then return null; end if;
 insert into ecos.integrity_finding(condition,entity_id,before_state,correlation_id) values('expired_active_claim',oid,before_,correlation) returning id into finding;
 perform ecos_meta.recover_occurrence(oid);
 select jsonb_agg(to_jsonb(c) order by id) into after_ from ecos.work_claim c where occurrence_id=oid and id in(select (value->>'id')::uuid from jsonb_array_elements(before_));
 insert into ecos.repair_action(finding_id,before_state,after_state,procedure_name,correlation_id,result) values(finding,before_,after_,'recover_occurrence',correlation,'repaired'); return finding; end $$;
create function ecos_migration.quarantine_row(batch uuid,locator text,raw jsonb) returns uuid language plpgsql set search_path=pg_catalog as $$
declare b ecos_migration.raw_migration_batch; reasons jsonb:='[]'; id_ uuid; hash_ text:=ecos_meta.content_hash(raw); oldhash text;
begin select * into b from ecos_migration.raw_migration_batch where id=batch for update; if b.id is null then raise exception 'missing_batch'; end if;
 select raw_hash into oldhash from ecos_migration.raw_source_row where batch_id=batch and source_locator=locator;
 if oldhash is not null then if oldhash<>hash_ then raise exception 'idempotency_conflict'; end if; select id into id_ from ecos_migration.quarantine_item where batch_id=batch and source_locator=locator; return id_; end if;
 if (select jsonb_agg(key order by key) from jsonb_object_keys(raw) key)<>(select jsonb_agg(value order by value) from jsonb_array_elements_text(b.column_names) value) then reasons:=reasons||'"column_drift"'::jsonb; end if;
 if nullif(raw->>'legacy_id','') is null then reasons:=reasons||'"missing_id"'::jsonb; end if;
 if exists(select 1 from ecos_migration.raw_source_row where batch_id=batch and raw_value->>'legacy_id'=raw->>'legacy_id') then
  reasons:=reasons||'"duplicate_legacy_id"'::jsonb;
  update ecos_migration.quarantine_item set state='identity_unresolved',reason_codes=reason_codes||'"duplicate_legacy_id"'::jsonb,record_version=record_version+1 where batch_id=batch and legacy_id=raw->>'legacy_id' and not reason_codes ? 'duplicate_legacy_id';
 end if;
 if raw->>'state' not in ('draft','open','waiting','completed','cancelled') then reasons:=reasons||'"unknown_lifecycle"'::jsonb; end if;
 if jsonb_typeof(raw->'title') is distinct from 'string' then reasons:=reasons||'"invalid_type"'::jsonb; end if;
 if raw->>'project_id' is not null and not exists(select 1 from ecos.project where id::text=raw->>'project_id') then reasons:=reasons||'"missing_foreign_reference"'::jsonb; end if;
 insert into ecos_migration.raw_source_row values(batch,locator,raw,hash_);
 insert into ecos_migration.quarantine_item(batch_id,source_locator,raw_hash,legacy_id,source_family,classification,state,reason_codes,identity_resolution_id,transformation_version,target_id) values(batch,locator,hash_,raw->>'legacy_id',b.source_family,'MIGRATE_CURRENT_STATE',case when reasons='[]' then 'received' else 'invalid' end,reasons,null,null,null) returning id into id_; return id_;
end $$;

-- Fixed non-login service roles. No credential or production authority is created.
do $$ declare role_ text; begin foreach role_ in array array['ecos_owner','migration_runner','operations_api','executor','provider_adapter','auditor','backup_operator','read_only_analytics'] loop
 if exists(select 1 from pg_roles where rolname=role_) then raise exception 'Unexpected pre-existing ECOS role: %',role_; end if;
 execute format('create role %I nologin noinherit nosuperuser nocreatedb nocreaterole noreplication nobypassrls',role_);
end loop;
execute format('grant ecos_owner to %I',current_user);
end $$;
grant ecos_owner to migration_runner;
do $$ declare r record; n text; begin
 foreach n in array array['ecos','ecos_meta','ecos_migration'] loop
 execute format('revoke all on all tables in schema %I from public',n);
 execute format('revoke all on all functions in schema %I from public',n);
 execute format('revoke all on schema %I from public',n);
 execute format('alter schema %I owner to ecos_owner',n);
 end loop;
 for r in select n.nspname,c.relname,c.relkind from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname in ('ecos','ecos_meta','ecos_migration') and c.relkind in ('r','v') loop
 execute format('alter %s %I.%I owner to ecos_owner',case when r.relkind='v' then 'view' else 'table' end,r.nspname,r.relname); end loop;
 for r in select p.oid::regprocedure sig from pg_proc p join pg_namespace n on n.oid=p.pronamespace where n.nspname in ('ecos','ecos_meta','ecos_migration') loop execute format('alter function %s owner to ecos_owner',r.sig); end loop;
end $$;
alter default privileges for role ecos_owner in schema ecos,ecos_meta,ecos_migration revoke execute on functions from public;
grant usage on schema ecos to operations_api,executor,provider_adapter;
grant execute on function ecos.operate(text,jsonb),ecos.read_record(text,uuid) to operations_api,executor,provider_adapter;
grant execute on function ecos.record_heartbeat(timestamptz,text) to executor;
grant execute on function ecos.claim_outbox(integer),ecos.ack_outbox(uuid,uuid),ecos.begin_synthetic_attempt(uuid,text) to provider_adapter;
grant usage on schema ecos,ecos_meta,ecos_migration to auditor,backup_operator;
grant select on all tables in schema ecos,ecos_meta,ecos_migration to auditor,backup_operator;
-- Analytics receives only aggregate queue metrics, with base-table permission for invoker views.
grant usage on schema ecos to read_only_analytics;
grant select on ecos.work_occurrence,ecos.outbox_item,ecos.v_work_health,ecos.v_outbox_health to read_only_analytics;
