-- SQL-native execution activity projection over existing authoritative runs/events.
-- Read-only, no scheduler/worker/provider effects and no new grants.
set local role ecos_owner;
create function ecos_meta.execution_activity_window(from_ timestamptz,to_ timestamptz)
returns jsonb language plpgsql stable set search_path=pg_catalog as $$
declare payload_ jsonb;
begin
 if from_ is null or to_ is null or from_>=to_ then raise exception 'invalid_contract' using errcode='22023'; end if;
 with evidence as (
  select r.id,r.occurrence_id,r.stage_definition_id,r.executor_instance_id,r.created_at,r.ended_at,r.state,
   w.work_definition_id,d.name worker_name,e.name executor_name,e.surface,
   case when r.ended_at is not null and r.ended_at>=r.created_at then extract(epoch from r.ended_at-r.created_at) end duration_seconds,
   ev.events,ev.latest_event_at
  from ecos.execution_run r
  join ecos.work_occurrence w on w.id=r.occurrence_id
  join ecos.work_definition d on d.id=w.work_definition_id
  join ecos.executor_instance i on i.id=r.executor_instance_id
  join ecos.executor e on e.id=i.executor_id
  left join lateral (
   select jsonb_agg(jsonb_build_object('event_id',v.id,'event_type',v.event_type,'created_at',v.created_at)
      order by v.created_at,v.id) events,max(v.created_at) latest_event_at
   from ecos.execution_event v where v.aggregate_type='execution_run' and v.aggregate_id=r.id
    and v.created_at>=from_ and v.created_at<to_
  ) ev on true
  where (r.created_at>=from_ and r.created_at<to_)
   or (r.ended_at>=from_ and r.ended_at<to_) or ev.events is not null
 ), grouped as (
  select work_definition_id,worker_name,executor_instance_id,executor_name,surface,state,count(*) run_count
  from evidence group by work_definition_id,worker_name,executor_instance_id,executor_name,surface,state
 )
 select jsonb_build_object('window_start',from_,'window_end_exclusive',to_,'complete_window_evaluated',true,
  'runs',coalesce((select jsonb_agg(to_jsonb(x) order by x.created_at,x.id) from evidence x),'[]'::jsonb),
  'summary',coalesce((select jsonb_agg(to_jsonb(x) order by x.work_definition_id,x.executor_instance_id,x.state) from grouped x),'[]'::jsonb),
  'run_count',(select count(*) from evidence),
  'source_timestamp',(select max(greatest(case when created_at<to_ then created_at end,
    case when ended_at<to_ then ended_at end,latest_event_at)) from evidence)) into payload_;
 -- Preserve all required rows or fail; never truncate and report a false complete window.
 if length(payload_::text)>=40000 then raise exception 'snapshot_capacity_exceeded' using errcode='22001'; end if;
 return payload_;
end $$;
revoke all on function ecos_meta.execution_activity_window(timestamptz,timestamptz) from public;
reset role;
