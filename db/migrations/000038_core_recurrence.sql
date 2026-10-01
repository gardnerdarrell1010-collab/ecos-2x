-- Materialize recurring core work during the existing work.next transaction.
-- Configuration is an existing occurrence + work_priority cadence, not a scheduler.
set local role ecos_owner;

create function ecos_meta.materialize_occurrence(template uuid, at_ timestamptz) returns uuid
language plpgsql set search_path=pg_catalog as $$
declare seed ecos.work_occurrence; latest ecos.work_occurrence; context_ ecos.work_context;
 priority_ ecos.work_priority; stage_ ecos.work_stage_definition; due_ timestamptz; oid uuid; grant_ record; domain_ text; ended_ timestamptz;
begin
 select * into seed from ecos.work_occurrence where id=template;
 select * into stage_ from ecos.work_stage_definition where id=seed.stage_definition_id;
 select * into priority_ from ecos.work_priority where occurrence_id=seed.id;
 select domain into domain_ from ecos_meta.object_domain where record_type='work_occurrence' and record_id=seed.id;
 if stage_.execution_surface is distinct from (case when stage_.stage_key in ('sms_transport_queue_consume','sms_outbound_dispatch') then 'RESIDENT_DETERMINISTIC_PROVIDER' else 'ONLINE_SEMANTIC' end)
  or priority_.recurrence_period_seconds is distinct from (case stage_.stage_key
   when 'task_coverage_proactive_control' then 1800 when 'outstanding_request_monitor' then 7200
   when 'incremental_continuity' then 21600 when 'ai_task_bridge' then 240
   when 'sms_transport_queue_consume' then 300 when 'sms_outbound_dispatch' then 300 when 'calendar_sms_reminder' then 900 end)
  or priority_.recurrence_period_seconds is null
  or seed.task_id is not null
  or (stage_.stage_key in ('task_coverage_proactive_control','outstanding_request_monitor','incremental_continuity','ai_task_bridge') and domain_ is not null)
  then raise exception 'invalid_contract'; end if;
 if not exists(select 1 from ecos.work_definition where id=seed.work_definition_id and enabled) then return null; end if;
 perform pg_advisory_xact_lock(hashtextextended('core-recurrence:'||seed.fulfillment_id::text,0));
 select * into latest from ecos.work_occurrence where fulfillment_id=seed.fulfillment_id order by due_at desc,id desc limit 1;
 -- An unresolved occurrence retains its normal retry/claim lifecycle. No overlap or replay.
 if latest.state<>'succeeded' then return latest.id; end if;
 select r.ended_at into ended_ from ecos.stage_result sr join ecos.execution_run r on r.id=sr.execution_run_id
  where sr.occurrence_id=latest.id order by r.ended_at desc limit 1;
 if ended_ is null then raise exception 'gate_blocked'; end if;
 due_:=ended_+make_interval(secs=>priority_.recurrence_period_seconds::double precision);
 if due_>at_ then return null; end if;
 -- Completion-relative schedules produce one next occurrence, never missed-interval replays.
 select * into context_ from ecos.work_context where occurrence_id=seed.id;
 if context_.occurrence_id is null then raise exception 'invalid_contract'; end if;
 insert into ecos.work_occurrence(work_definition_id,stage_definition_id,fulfillment_id,task_id,state,occurrence_key,due_at)
 values(seed.work_definition_id,seed.stage_definition_id,seed.fulfillment_id,null,'pending',
  'core:'||seed.fulfillment_id::text||':'||extract(epoch from due_)::text,due_) returning id into oid;
 if domain_ is not null then insert into ecos_meta.object_domain values('work_occurrence',oid,domain_); end if;
 insert into ecos.work_context(occurrence_id,operation,source_references,memory_references,input)
 values(oid,context_.operation,context_.source_references,context_.memory_references,context_.input);
 insert into ecos.work_priority(occurrence_id,business_impact,recurrence_period_seconds)
 values(oid,priority_.business_impact,priority_.recurrence_period_seconds);
 -- Preserve only explicit occurrence recipients. No domain-derived record authority.
 for grant_ in select principal_id from ecos_meta.object_grant where record_type='work_occurrence' and record_id=seed.id loop
  insert into ecos_meta.object_grant values(grant_.principal_id,'work_occurrence',oid);
 end loop;
 return oid;
end $$;

alter function ecos_meta.apply_operation(text,jsonb,jsonb) rename to apply_operation_before_core_recurrence;
create function ecos_meta.apply_operation(op text,ctx jsonb,args jsonb) returns jsonb
language plpgsql set search_path=pg_catalog as $$
declare seed record;
begin
 if op='work.next' then
  for seed in
   select distinct on(o.fulfillment_id) o.id from ecos.work_occurrence o
   join ecos.work_priority p on p.occurrence_id=o.id
   join ecos.work_stage_definition s on s.id=o.stage_definition_id
   join ecos.work_definition d on d.id=o.work_definition_id
   join ecos_meta.object_grant g on g.record_type='work_occurrence' and g.record_id=o.id
   where g.principal_id=(ctx->>'principal_id')::uuid and d.enabled and o.task_id is null
    and s.stage_key in ('task_coverage_proactive_control','outstanding_request_monitor','incremental_continuity','ai_task_bridge','sms_transport_queue_consume','sms_outbound_dispatch','calendar_sms_reminder')
    and p.recurrence_period_seconds is not null
   order by o.fulfillment_id,o.due_at desc,o.id desc
  loop perform ecos_meta.materialize_occurrence(seed.id,clock_timestamp()); end loop;
 end if;
 return ecos_meta.apply_operation_before_core_recurrence(op,ctx,args);
end $$;
revoke all on all functions in schema ecos_meta from public;
reset role;
