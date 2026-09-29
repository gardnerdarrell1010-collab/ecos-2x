-- Additional gate guards and portable read/recurrence support.
set local role ecos_owner;
create table ecos_meta.principal_clearance(principal_id uuid primary key,ceiling text not null check(ceiling in ('public','internal','confidential','restricted')));
create or replace function ecos_meta.require_access(principal uuid,kind text,entity uuid) returns void language plpgsql stable set search_path=pg_catalog as $$
declare sensitivity_ text:='internal'; ceiling_ text;
begin
 if not exists(select 1 from ecos_meta.object_grant where principal_id=principal and record_type=kind and record_id=entity) then raise exception 'forbidden' using errcode='42501'; end if;
 select ceiling into ceiling_ from ecos_meta.principal_clearance where principal_id=principal; ceiling_:=coalesce(ceiling_,'internal');
 if kind='fact' then select sensitivity into sensitivity_ from ecos.fact where id=entity;
 elsif kind='memory_scope' then select sensitivity into sensitivity_ from ecos.memory_scope where id=entity;
 elsif kind='memory_version' then select sensitivity into sensitivity_ from ecos.memory_version where id=entity; end if;
 if array_position(array['public','internal','confidential','restricted'],coalesce(sensitivity_,'internal'))>array_position(array['public','internal','confidential','restricted'],ceiling_) then raise exception 'forbidden' using errcode='42501'; end if;
end $$;
create function ecos_meta.operation_authorized(op text,role_ name) returns boolean language sql stable set search_path=pg_catalog as $$
 select case when document->>'required_role'='owner' then pg_has_role(role_,'operations_api','MEMBER') else pg_has_role(role_,(document->>'required_role')::name,'MEMBER') end from ecos_meta.operation_contract where name=op $$;
-- Wrap role, grant and sensitivity checks in current_principal; operations still recheck object access.
create function ecos_meta.operation_role_guard() returns trigger language plpgsql set search_path=pg_catalog as $$
declare p ecos_meta.principal_binding;
begin p:=ecos_meta.current_principal(); if not coalesce(ecos_meta.operation_authorized(new.operation,p.role_name),false) then raise exception 'forbidden' using errcode='42501'; end if; return new; end $$;
create trigger operation_role_guard before insert on ecos_meta.operation_receipt for each row execute function ecos_meta.operation_role_guard();
create function ecos_meta.execution_reference_guard() returns trigger language plpgsql set search_path=pg_catalog as $$
declare r ecos.execution_run;
begin select * into r from ecos.execution_run where id=(new.payload->>'execution_run_id')::uuid;
 if r.id is null or r.id<>new.aggregate_id or r.occurrence_id::text<>new.payload->>'occurrence_id' or ecos_meta.fence(to_jsonb(r))<>new.payload->'fence' or r.correlation_id<>new.correlation_id then raise exception 'invalid_execution_reference' using errcode='23514'; end if; return new; end $$;
create trigger execution_reference before insert on ecos.execution_event for each row execute function ecos_meta.execution_reference_guard();
create function ecos_meta.delivery_attempt_guard() returns trigger language plpgsql set search_path=pg_catalog as $$
begin if not exists(select 1 from ecos.delivery d join ecos.provider_attempt a on a.provider_command_id=d.provider_command_id where d.id=new.delivery_id and a.id=new.provider_attempt_id) then raise exception 'invalid_delivery_attempt' using errcode='23514'; end if; return new; end $$;
create trigger delivery_reference before insert on ecos.delivery_attempt for each row execute function ecos_meta.delivery_attempt_guard();
create function ecos_meta.schedule_guard() returns trigger language plpgsql set search_path=pg_catalog as $$
begin if not exists(select 1 from pg_timezone_names where name=new.timezone) then raise exception 'invalid_timezone' using errcode='23514'; end if; return new; end $$;
create trigger timezone_guard before insert or update on ecos.task_schedule for each row execute function ecos_meta.schedule_guard();
create function ecos_meta.local_occurrence(local_time timestamp,zone text,gap_policy text,fold_policy text) returns timestamptz language plpgsql stable set search_path=pg_catalog as $$
declare result_ timestamptz; local_ timestamp:=local_time; tries int:=0;
begin
 if gap_policy not in ('skip','next_valid') or fold_policy not in ('earlier','later') or not exists(select 1 from pg_timezone_names where name=zone) then raise exception 'invalid_contract'; end if;
 loop
  select case when fold_policy='earlier' then min(candidate) else max(candidate) end into result_ from generate_series((local_ at time zone zone)-interval '3 hours',(local_ at time zone zone)+interval '3 hours',interval '1 minute') candidate where candidate at time zone zone=local_;
  if result_ is not null then return result_; end if;
  if gap_policy='skip' then return null; end if;
  local_:=local_+interval '1 minute'; tries:=tries+1; if tries>1440 then raise exception 'unresolvable_local_time'; end if;
 end loop;
end $$;
create table ecos.schedule_occurrence(schedule_id uuid not null references ecos.task_schedule,schedule_version bigint not null,logical_local_time timestamp not null,occurrence_id uuid not null unique references ecos.work_occurrence,primary key(schedule_id,schedule_version,logical_local_time));
create function ecos_meta.materialize_occurrence(schedule uuid,expected bigint,stage uuid,logical_time timestamp) returns uuid language plpgsql set search_path=pg_catalog as $$
declare s ecos.task_schedule; w ecos.work_stage_definition; due_ timestamptz; oid uuid;
begin select * into s from ecos.task_schedule where id=schedule for update;
 if s.record_version is distinct from expected then raise exception 'stale_version' using errcode='40001'; end if;
 select occurrence_id into oid from ecos.schedule_occurrence where schedule_id=schedule and schedule_version=expected and logical_local_time=logical_time; if found then return oid; end if;
 select * into w from ecos.work_stage_definition where id=stage;
 due_:=ecos_meta.local_occurrence(logical_time,s.timezone,s.dst_gap_policy,s.dst_fold_policy); if due_ is null then return null; end if;
 insert into ecos.work_occurrence(work_definition_id,stage_definition_id,fulfillment_id,task_id,state,occurrence_key,due_at,retry_at,ready_override_at,priority_override) values(w.work_definition_id,w.id,gen_random_uuid(),s.task_id,'pending',schedule::text||':'||expected::text||':'||logical_time::text,due_,null,null,null) returning id into oid;
 insert into ecos.schedule_occurrence values(schedule,expected,logical_time,oid); return oid;
end $$;
create function ecos_meta.reconcile_schedule() returns trigger language plpgsql set search_path=pg_catalog as $$
begin if (to_jsonb(old)-'record_version')<>(to_jsonb(new)-'record_version') then
 if exists(select 1 from ecos.schedule_occurrence s join ecos.work_occurrence w on w.id=s.occurrence_id where s.schedule_id=new.id and w.state in ('claimed','running')) then raise exception 'gate_blocked' using errcode='23514'; end if;
 update ecos.work_occurrence w set state='cancelled',record_version=w.record_version+1 from ecos.schedule_occurrence s where s.schedule_id=new.id and s.occurrence_id=w.id and w.due_at>clock_timestamp() and w.state in ('pending','ready','retry_wait'); end if; return new; end $$;
create trigger schedule_reconcile after update on ecos.task_schedule for each row execute function ecos_meta.reconcile_schedule();
create view ecos.v_work_readiness with(security_invoker=true) as select w.id occurrence_id,i.id executor_instance_id,ecos_meta.selection(w.id,i.id,statement_timestamp()) selection_evidence from ecos.work_occurrence w cross join ecos.executor_instance i;
create view ecos.v_system_status_header with(security_invoker=true) as select statement_timestamp() as_of,exists(select 1 from ecos.v_node_health where availability<>'available') executor_degraded,exists(select 1 from ecos.provider_command where outcome='unknown_outcome') unresolved_provider_outcome,exists(select 1 from ecos_meta.control where maintenance) maintenance;
create function ecos.bootstrap_package() returns jsonb language plpgsql security definer set search_path=pg_catalog set timezone='UTC' as $$
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
 package:=jsonb_build_object('package_id',gen_random_uuid(),'schema_version','1.0.0','database_schema_version','1.0.0','generated_at',clock_timestamp(),'principal_id',p.principal_id,'sensitivity_ceiling',coalesce(ceiling_,'internal'),'governed_context',refs,'context_records',contexts,'active_memory_heads',heads,'unresolved_exceptions','[]'::jsonb,'operation_schema_ids',(select jsonb_agg(distinct value) from jsonb_array_elements(bindings) b cross join lateral jsonb_array_elements(jsonb_build_array(b->'request_schema_id',b->'response_schema_id'))),'capability_vocabulary',(select coalesce(jsonb_agg(distinct name),'["db.governed_operations"]'::jsonb) from ecos.capability),'operation_bindings',bindings,'schema_bundle',bundle,'relevant_work',works);
 package:=package||jsonb_build_object('content_hash',ecos_meta.content_hash(package)); perform ecos_meta.assert_contract('bootstrap_package',package); return package;
end $$;
grant execute on function ecos.bootstrap_package() to operations_api,executor;
revoke all on all functions in schema ecos_meta from public;
grant select on ecos_meta.principal_clearance,ecos.schedule_occurrence to auditor,backup_operator;
reset role;
