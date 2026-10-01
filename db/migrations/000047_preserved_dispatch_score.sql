-- Preserve the owner-locked Task Loop formula in the existing priority storage.
-- Scores refresh explicitly or for the changed occurrence, never on selection scans.
set local role ecos_owner;
alter table ecos.work_priority
 add column dispatch_importance smallint check(dispatch_importance between 1 and 5),
 add column dependency_impact smallint check(dependency_impact between 1 and 5),
 add column task_loop_id text,
 add column effective_ready_at timestamptz,
 add column dispatch_score text check(dispatch_score ~ '^[0-9]{1,2}[.][0-9]{3}$' and dispatch_score::numeric between 0 and 16),
 add column dispatch_score_at timestamptz,
 add constraint complete_dispatch_inputs check
 ((dispatch_importance is null and dependency_impact is null and task_loop_id is null)
 or (dispatch_importance is not null and dependency_impact is not null and task_loop_id is not null));

create function ecos_meta.dispatch_score(importance numeric, impact numeric,
 ready_at timestamptz, interval_seconds numeric, at_ timestamptz, run_now boolean)
returns numeric language plpgsql immutable set search_path=pg_catalog as $$
declare base_ numeric; overdue_ numeric; pressure_ numeric;
begin
 if importance not between 1 and 5 or impact not between 1 and 5
 or importance is null or impact is null or ready_at is null or at_ is null
 or interval_seconds is null or interval_seconds<=0 then
  raise exception 'invalid_dispatch_inputs' using errcode='22023';
 end if;
 if run_now then return 16.000; end if;
 base_:=(importance*0.3+impact*0.2)/0.5;
 overdue_:=greatest(0,extract(epoch from at_-ready_at)/interval_seconds);
 pressure_:=overdue_/(overdue_+10);
 -- The normal score must never round into the reserved RUN NOW value.
 return least(15.999,round(base_+(15.999-base_)*pressure_,3));
end $$;

create function ecos_meta.refresh_dispatch_score(occurrence uuid,at_ timestamptz)
returns boolean language plpgsql set search_path=pg_catalog as $$
declare w ecos.work_occurrence; p ecos.work_priority; ready_ timestamptz; score_ numeric; forced_ boolean;
begin
 select * into w from ecos.work_occurrence where id=occurrence;
 select * into p from ecos.work_priority where occurrence_id=occurrence for update;
 if p.task_loop_id is null then return false; end if;
 ready_:=greatest(w.due_at,w.retry_at);
 forced_:=w.ready_override_at is not null and w.ready_override_at<=at_
  and w.state not in ('succeeded','cancelled');
 score_:=ecos_meta.dispatch_score(p.dispatch_importance,p.dependency_impact,
  ready_,p.recurrence_period_seconds,at_,forced_);
 if p.effective_ready_at is not distinct from ready_ and p.dispatch_score::numeric is not distinct from score_ then
  return false;
 end if;
 update ecos.work_priority set effective_ready_at=ready_,dispatch_score=to_char(score_,'FM990.000'),
  dispatch_score_at=case when forced_ then w.ready_override_at else at_ end
  where occurrence_id=occurrence;
 return true;
end $$;

create function ecos_meta.dispatch_score_event() returns trigger language plpgsql set search_path=pg_catalog as $$
begin
 perform ecos_meta.refresh_dispatch_score(new.id,clock_timestamp());
 return new;
end $$;
create trigger dispatch_score_changed_occurrence after update of due_at,retry_at,ready_override_at,state
 on ecos.work_occurrence for each row
 when (old.due_at is distinct from new.due_at or old.retry_at is distinct from new.retry_at
 or old.ready_override_at is distinct from new.ready_override_at
 or (old.state is distinct from new.state and new.state in ('succeeded','retry_wait','failed','dead_lettered','cancelled')))
 execute function ecos_meta.dispatch_score_event();

create function ecos_meta.refresh_dispatch_population(at_ timestamptz) returns bigint
language plpgsql set search_path=pg_catalog as $$
declare item record; changed_ bigint:=0;
begin
 for item in select p.occurrence_id from ecos.work_priority p
 join ecos.work_occurrence w on w.id=p.occurrence_id
 join ecos.work_definition d on d.id=w.work_definition_id
 where p.task_loop_id is not null and d.enabled and w.state not in ('succeeded','cancelled')
 order by p.occurrence_id loop
  if ecos_meta.refresh_dispatch_score(item.occurrence_id,at_) then changed_:=changed_+1; end if;
 end loop;
 return changed_;
end $$;
-- A025's existing PT10M responsibility is absorbed at the existing work.next
-- wake-up boundary. This records its last refresh; it creates no timer or executor.
create table ecos_meta.dispatch_refresh_state (
 singleton boolean primary key default true check(singleton),
 refreshed_at timestamptz
);
insert into ecos_meta.dispatch_refresh_state(singleton) values(true);
revoke all on ecos_meta.dispatch_refresh_state from public,executor,operations_api,provider_adapter;
create function ecos_meta.refresh_dispatch_if_due(at_ timestamptz) returns void
language plpgsql set search_path=pg_catalog as $$
declare last_ timestamptz;
begin
 if not exists(select 1 from ecos.work_priority p join ecos.work_occurrence w on w.id=p.occurrence_id
  join ecos.work_definition d on d.id=w.work_definition_id where p.task_loop_id is not null and d.enabled) then return; end if;
 if not pg_try_advisory_xact_lock(684026,47) then return; end if;
 select refreshed_at into last_ from ecos_meta.dispatch_refresh_state where singleton for update;
 if last_ is not null and at_<last_+interval '10 minutes' then return; end if;
 perform ecos_meta.refresh_dispatch_population(at_);
 update ecos_meta.dispatch_refresh_state set refreshed_at=at_ where singleton;
end $$;
alter function ecos_meta.apply_operation(text,jsonb,jsonb) rename to apply_operation_before_dispatch_refresh;
create function ecos_meta.apply_operation(op text,ctx jsonb,args jsonb) returns jsonb
language plpgsql set search_path=pg_catalog as $$
begin
 if op='work.next' then perform ecos_meta.refresh_dispatch_if_due(clock_timestamp()); end if;
 return ecos_meta.apply_operation_before_dispatch_refresh(op,ctx,args);
end $$;
revoke all on function ecos_meta.dispatch_score(numeric,numeric,timestamptz,numeric,timestamptz,boolean),
 ecos_meta.refresh_dispatch_score(uuid,timestamptz),ecos_meta.dispatch_score_event(),
 ecos_meta.refresh_dispatch_population(timestamptz),ecos_meta.refresh_dispatch_if_due(timestamptz),
 ecos_meta.apply_operation(text,jsonb,jsonb) from public;

alter function ecos_meta.selection(uuid,uuid,timestamptz) rename to selection_before_dispatch_score;
create function ecos_meta.selection(occurrence uuid,instance uuid,at_ timestamptz)
returns jsonb language plpgsql stable set search_path=pg_catalog as $$
declare s jsonb; p ecos.work_priority;
begin
 s:=ecos_meta.selection_before_dispatch_score(occurrence,instance,at_);
 select * into p from ecos.work_priority where occurrence_id=occurrence;
 if p.task_loop_id is null then return s; end if;
 if p.dispatch_score is null then
  return s||jsonb_build_object('eligible',false,'reason_codes',(s->'reason_codes')||'"dispatch_score_missing"'::jsonb);
 end if;
 return s||jsonb_build_object('policy_version','task-loop-owner-locked-v1',
  'dispatch_score',p.dispatch_score,'effective_ready_at',p.effective_ready_at,'task_loop_id',p.task_loop_id);
end $$;
update ecos_meta.contract_schema set document=jsonb_set(document,'{properties}',
 document->'properties'||'{"policy_version":{"enum":["lexicographic-v1","task-loop-owner-locked-v1"]},"dispatch_score":{"type":"string","pattern":"^[0-9]{1,2}[.][0-9]{3}$"},"effective_ready_at":{"type":"string","format":"date-time"},"task_loop_id":{"type":"string"}}'::jsonb)
 where schema_id='https://contracts.ecos.invalid/v1/selection_evidence.schema.json';
create or replace function ecos_meta.claim_work(ctx jsonb,args jsonb) returns jsonb language plpgsql set search_path=pg_catalog as $$
declare o ecos.work_occurrence; c ecos.work_claim; r ecos.execution_run; sel jsonb; at_ timestamptz:=clock_timestamp(); instance uuid:=(args->>'executor_instance_id')::uuid; principal uuid:=(ctx->>'principal_id')::uuid;
begin
 if ctx->>'executor_instance_id' is distinct from args->>'executor_instance_id' then raise exception 'forbidden' using errcode='42501'; end if;
 for o in select w.* from ecos.work_occurrence w cross join lateral (select ecos_meta.selection(w.id,instance,at_) s) q
 where w.state in ('pending','ready','retry_wait','claimed','running') and (w.due_at<=at_ or w.ready_override_at<=at_) and (w.retry_at is null or w.retry_at<=at_) and (q.s->>'eligible')::boolean and exists(select 1 from ecos_meta.object_grant g where g.principal_id=principal and g.record_type='work_occurrence' and g.record_id=w.id)
 order by coalesce((q.s->>'dispatch_score')::numeric,(q.s->>'priority_override')::numeric) desc,(q.s->>'immediate_ready')::boolean desc,case when not(q.s ? 'dispatch_score') then (q.s->>'sla_breach_seconds')::bigint end desc,case when not(q.s ? 'dispatch_score') then (q.s->>'deadline_pressure_seconds')::bigint end desc,case when not(q.s ? 'dispatch_score') then (q.s->>'business_impact')::bigint end desc,case when not(q.s ? 'dispatch_score') then (q.s->>'recurrence_relative_age_basis_points')::bigint end desc,(q.s->>'effective_ready_at')::timestamptz,case when q.s ? 'dispatch_score' then w.due_at end,q.s->>'task_loop_id',w.created_at,w.id for update of w skip locked limit 1 loop
  perform ecos_meta.recover_occurrence(o.id);
  sel:=ecos_meta.selection(o.id,instance,clock_timestamp());
  if not (sel->>'eligible')::boolean then continue; end if;
  update ecos.work_occurrence set state='ready',record_version=record_version+1 where id=o.id and state in ('pending','retry_wait');
  update ecos.work_occurrence set state='claimed',claim_version=claim_version+1,attempt_count=attempt_count+1,record_version=record_version+1 where id=o.id returning * into o;
  insert into ecos.work_claim(occurrence_id,stage_definition_id,executor_instance_id,claim_version,fence_token,state,acquired_at,expires_at,renewed_at) values(o.id,o.stage_definition_id,instance,o.claim_version,gen_random_uuid(),'active',clock_timestamp(),clock_timestamp()+make_interval(secs=>(args->>'lease_seconds')::int),clock_timestamp()) returning * into c;
  insert into ecos.execution_run(claim_id,occurrence_id,stage_definition_id,claim_version,fence_token,executor_instance_id,state,selection_evidence,correlation_id,ended_at) values(c.id,c.occurrence_id,c.stage_definition_id,c.claim_version,c.fence_token,c.executor_instance_id,'started',sel,(ctx->>'correlation_id')::uuid,null) returning * into r;
  perform ecos_meta.execution_event(r.id,'started','selected');
  update ecos.work_occurrence set state='running',record_version=record_version+1 where id=o.id;
  return jsonb_build_object('schema_version','1.0.0','correlation_id',ctx->'correlation_id','claim',to_jsonb(c),'execution_run',ecos_meta.run_wire(to_jsonb(r)));
 end loop;
 return jsonb_build_object('schema_version','1.0.0','correlation_id',ctx->'correlation_id','claim',null,'execution_run',null);
end $$;

revoke all on function ecos_meta.selection(uuid,uuid,timestamptz) from public;
reset role;
