-- Phase 2 portable control plane. Accepted Phase 1 objects remain the foundation.
set local role ecos_owner;
create table ecos_meta.executor_policy(
 surface text primary key check(surface in ('DATABASE_DETERMINISTIC','RESIDENT_DETERMINISTIC_PROVIDER','ONLINE_SEMANTIC','INTERACTIVE_ADA')),
 stale_seconds int not null check(stale_seconds between 10 and 3600),
 maximum_instances int not null check(maximum_instances between 1 and 10),
 source text not null, effective_at timestamptz not null, record_version bigint not null default 1
);
insert into ecos_meta.executor_policy values
 ('DATABASE_DETERMINISTIC',60,1,'Phase 2 engineering default; in-database service identity',clock_timestamp(),1),
 ('RESIDENT_DETERMINISTIC_PROVIDER',90,1,'Phase 2 authorized topology; configurable heartbeat engineering default',clock_timestamp(),1),
 ('ONLINE_SEMANTIC',300,8,'Phase 2 authorized topology; configurable heartbeat engineering default',clock_timestamp(),1),
 ('INTERACTIVE_ADA',300,1,'Phase 2 authorized topology; configurable heartbeat engineering default',clock_timestamp(),1);
create table ecos.executor_presence(
 executor_instance_id uuid primary key references ecos.executor_instance,
 host text not null, runtime text not null, software_version text not null,
 started_at timestamptz not null default clock_timestamp(), stopped_at timestamptz,
 status text not null check(status in ('available','unavailable','stopped')),
 evidence_hash text not null check(evidence_hash ~ '^[a-f0-9]{64}$'),
 record_version bigint not null default 1
);
create table ecos.heartbeat_load(
 heartbeat_id uuid primary key references ecos.heartbeat,
 reported_running int not null check(reported_running>=0),
 actual_running int not null check(actual_running>=0),
 load_basis_points int not null check(load_basis_points between 0 and 10000)
);
create table ecos.resource_provider(provider text primary key, description text not null);
insert into ecos.resource_provider values
 ('database','PostgreSQL client and health metrics; pool metrics only when observed'),
 ('executors','Governed executor capacity'),('sheets','1.x shadow reads only; retired from normal dispatch after cutover'),
 ('drive','API operations and transfer'),('gmail','API and action pressure'),('toast','Provider requests'),
 ('twilio','Send volume; synthetic transport only in Phase 2'),('vercel_blob','Operations storage and egress'),
 ('home01','ECOS attributable bytes only; no inference from total host network');
create table ecos.resource_metric(
 provider text references ecos.resource_provider, metric text, unit text not null,
 measurement_source text not null, fresh_seconds int not null check(fresh_seconds>0),
 primary key(provider,metric)
);
insert into ecos.resource_metric values
 ('database','connections','connections','pg_stat_activity; includes visible shared database clients',60),
 ('database','pool_utilization','basis_points','UNKNOWN until authenticated pool telemetry supplied',60),
 ('database','query_latency','milliseconds','client measured governed operation duration',60),
 ('database','lock_waits','sessions','pg_stat_activity wait_event_type=Lock',60),
 ('database','health','failure_count','authenticated bounded health probe',60),
 ('executors','active','instances','fresh registered executor presence',60),
 ('executors','duration','milliseconds','execution_run start and end timestamps',300),
 ('sheets','requests','requests','adapter measured requests',60),('drive','requests','requests','adapter measured requests',60),
 ('drive','bytes','bytes','adapter measured payload bytes',60),('gmail','requests','requests','adapter measured requests',60),
 ('toast','requests','requests','adapter measured requests',60),('twilio','sends','actions','adapter measured sends',60),
 ('vercel_blob','operations','operations','adapter measurement',60),('vercel_blob','storage','bytes','provider measurement',300),
 ('vercel_blob','egress','bytes','adapter measurement',60),('home01','bytes','bytes','ECOS adapter measurement only',60);
create table ecos.resource_budget(
 provider text, metric text, hard_limit bigint check(hard_limit>=0), elevated_limit bigint check(elevated_limit>=0),
 window_seconds int not null check(window_seconds>0), source text not null,
 effective_at timestamptz not null, verification text not null check(verification in ('UNKNOWN','OWNER_CONFIGURED','VERIFIED')),
 record_version bigint not null default 1,
 primary key(provider,metric), foreign key(provider,metric) references ecos.resource_metric,
 check((verification='UNKNOWN' and hard_limit is null) or verification<>'UNKNOWN'),
 check(elevated_limit is null or hard_limit is null or elevated_limit<=hard_limit)
);
insert into ecos.resource_budget select provider,metric,null,null,60,'UNKNOWN: no provider quota asserted',clock_timestamp(),'UNKNOWN',1 from ecos.resource_metric;
create table ecos.resource_usage_window(
 id uuid primary key default gen_random_uuid(), provider text, metric text,
 observed_at timestamptz not null, received_at timestamptz not null default clock_timestamp(), value bigint check(value>=0),
 evidence_hash text not null check(evidence_hash ~ '^[a-f0-9]{64}$'), principal_id uuid not null,
 foreign key(provider,metric) references ecos.resource_metric
);
create index resource_observation_latest on ecos.resource_usage_window(provider,metric,observed_at desc);
create table ecos.resource_health(
 provider text primary key references ecos.resource_provider,
 pressure text not null check(pressure in ('NORMAL','ELEVATED','THROTTLED','BLOCKED','UNKNOWN')),
 reason text not null, observed_at timestamptz not null, valid_until timestamptz not null,
 source text not null, record_version bigint not null default 1
);
create table ecos.stage_resource_requirement(
 stage_definition_id uuid references ecos.work_stage_definition, provider text, metric text,
 reserved_units bigint not null default 0 check(reserved_units>=0), unknown_blocks boolean not null default false,
 primary key(stage_definition_id,provider,metric), foreign key(provider,metric) references ecos.resource_metric
);
create table ecos.resource_reservation(
 claim_id uuid references ecos.work_claim, provider text, metric text, units bigint not null check(units>=0),
 primary key(claim_id,provider,metric), foreign key(provider,metric) references ecos.resource_metric
);
create index resource_reservations_budget on ecos.resource_reservation(provider,metric);
create table ecos.work_context(
 occurrence_id uuid primary key references ecos.work_occurrence,
 operation text not null references ecos_meta.operation_contract,
 source_references jsonb not null default '[]' check(jsonb_typeof(source_references)='array' and jsonb_array_length(source_references)<=16),
 memory_references jsonb not null default '[]' check(jsonb_typeof(memory_references)='array' and jsonb_array_length(memory_references)<=8),
 input jsonb not null default '{}' check(jsonb_typeof(input)='object' and octet_length(input::text)<=16384),
 record_version bigint not null default 1
);
create table ecos.work_wakeup(
 occurrence_id uuid primary key references ecos.work_occurrence, generation bigint not null default 1,
 created_at timestamptz not null default clock_timestamp(), correlation_id uuid not null,
 source text not null, consumed_at timestamptz
);
create index work_wakeup_pending on ecos.work_wakeup(created_at) where consumed_at is null;
create table ecos.proposal_submission(
 proposal_id uuid primary key, occurrence_id uuid not null references ecos.work_occurrence,
 principal_id uuid not null, proposal jsonb not null, content_hash text not null,
 created_at timestamptz not null default clock_timestamp()
);
create table ecos.package_measurement(
 id uuid primary key default gen_random_uuid(), occurrence_id uuid not null references ecos.work_occurrence,
 principal_id uuid not null, measured_at timestamptz not null default clock_timestamp(),
 payload_bytes bigint not null check(payload_bytes>0), source_count int not null
);
create index package_measurement_work on ecos.package_measurement(occurrence_id);
create table ecos.control_plane_event(
 id uuid primary key default gen_random_uuid(), event_type text not null, entity_id uuid,
 correlation_id uuid not null, payload jsonb not null, created_at timestamptz not null default clock_timestamp()
);
create trigger immutable before update or delete on ecos.control_plane_event for each row execute function ecos_meta.forbid_evidence_change();
create trigger immutable before update or delete on ecos.proposal_submission for each row execute function ecos_meta.forbid_evidence_change();
create trigger immutable before update or delete on ecos.resource_usage_window for each row execute function ecos_meta.forbid_evidence_change();

create function ecos_meta.resource_pressure(provider_ text,metric_ text,at_ timestamptz) returns text language plpgsql stable set search_path=pg_catalog as $$
declare h ecos.resource_health; b ecos.resource_budget; m ecos.resource_metric; u ecos.resource_usage_window;
begin
 select * into h from ecos.resource_health where provider=provider_;
 if h.valid_until>at_ and h.pressure in ('THROTTLED','BLOCKED') then return h.pressure; end if;
 select * into b from ecos.resource_budget where provider=provider_ and metric=metric_ and effective_at<=at_;
 select * into m from ecos.resource_metric where provider=provider_ and metric=metric_;
 select * into u from ecos.resource_usage_window where provider=provider_ and metric=metric_ and observed_at<=at_ order by observed_at desc,received_at desc limit 1;
 if u.id is null or u.value is null or u.observed_at+make_interval(secs=>m.fresh_seconds)<=at_ or b.hard_limit is null then return 'UNKNOWN'; end if;
 if u.value>=b.hard_limit then return 'BLOCKED'; end if;
 if b.elevated_limit is not null and u.value>=b.elevated_limit then return 'ELEVATED'; end if;
 return 'NORMAL';
end $$;

alter function ecos_meta.selection(uuid,uuid,timestamptz) rename to selection_phase1;
create function ecos_meta.selection(oid uuid,instance uuid,at_ timestamptz) returns jsonb language plpgsql stable set search_path=pg_catalog as $$
declare s jsonb; reasons jsonb; req record; pressure_ text; used_ bigint; limit_ bigint;
begin
 s:=ecos_meta.selection_phase1(oid,instance,at_); reasons:=s->'reason_codes';
 if exists(select 1 from ecos.executor_presence where executor_instance_id=instance and status<>'available') then reasons:=reasons||'"executor_unavailable"'::jsonb; end if;
 for req in select r.* from ecos.stage_resource_requirement r join ecos.work_occurrence w on w.stage_definition_id=r.stage_definition_id where w.id=oid loop
  pressure_:=ecos_meta.resource_pressure(req.provider,req.metric,at_);
  if pressure_ in ('BLOCKED','THROTTLED') or (pressure_='UNKNOWN' and req.unknown_blocks) then reasons:=reasons||to_jsonb('resource_'||req.provider); end if;
  select hard_limit into limit_ from ecos.resource_budget where provider=req.provider and metric=req.metric and effective_at<=at_;
  select coalesce(sum(rr.units),0) into used_ from ecos.resource_reservation rr join ecos.work_claim c on c.id=rr.claim_id where rr.provider=req.provider and rr.metric=req.metric and c.state='active' and c.expires_at>at_ and c.occurrence_id<>oid;
  if limit_ is not null and used_+req.reserved_units>limit_ then reasons:=reasons||to_jsonb('budget_'||req.provider); end if;
 end loop;
 return s||jsonb_build_object('reason_codes',reasons,'eligible',jsonb_array_length(reasons)=0);
end $$;

-- Only work sharing a scarce resource serializes; unrelated claims retain SKIP LOCKED concurrency.
create function ecos_meta.reserve_resources() returns trigger language plpgsql set search_path=pg_catalog as $$
declare r record; s jsonb;
begin
 for r in select * from ecos.stage_resource_requirement where stage_definition_id=new.stage_definition_id order by provider,metric loop
  perform 1 from ecos.resource_budget where provider=r.provider and metric=r.metric for update;
 end loop;
 s:=ecos_meta.selection(new.occurrence_id,new.executor_instance_id,clock_timestamp());
 if (s->'reason_codes'-'attempt_limit')<>'[]'::jsonb then raise exception 'gate_blocked' using errcode='23514'; end if;
 return new;
end $$;
create trigger reserve_resources before insert on ecos.work_claim for each row execute function ecos_meta.reserve_resources();
create function ecos_meta.record_reservations() returns trigger language plpgsql set search_path=pg_catalog as $$
begin
 insert into ecos.resource_reservation select new.id,provider,metric,reserved_units from ecos.stage_resource_requirement where stage_definition_id=new.stage_definition_id;
 update ecos.work_wakeup set consumed_at=clock_timestamp() where occurrence_id=new.occurrence_id;
 return new;
end $$;
create trigger record_reservations after insert on ecos.work_claim for each row execute function ecos_meta.record_reservations();

create function ecos_meta.wake_work(oid uuid,corr uuid,source_ text) returns void language plpgsql set search_path=pg_catalog as $$
begin
 insert into ecos.work_wakeup(occurrence_id,correlation_id,source) values(oid,corr,source_)
 on conflict(occurrence_id) do update set consumed_at=null,generation=ecos.work_wakeup.generation+1,created_at=clock_timestamp(),correlation_id=excluded.correlation_id,source=excluded.source;
 insert into ecos.control_plane_event(event_type,entity_id,correlation_id,payload) values('work.ready',oid,corr,jsonb_build_object('source',source_));
 perform pg_notify('ecos_work_ready',oid::text);
end $$;
create function ecos_meta.release_dependents() returns trigger language plpgsql set search_path=pg_catalog as $$
declare w record; corr uuid;
begin
 select correlation_id into corr from ecos.execution_run where id=new.execution_run_id;
 for w in select o.id from ecos.work_dependency d join ecos.work_occurrence o on o.id=d.occurrence_id where d.prerequisite_occurrence_id=new.occurrence_id and o.state in ('pending','ready','retry_wait') and not exists(select 1 from ecos.work_dependency x where x.occurrence_id=o.id and not exists(select 1 from ecos.stage_result r where r.occurrence_id=x.prerequisite_occurrence_id and r.result_schema_id=x.required_result_schema_id and (x.required_result_hash is null or x.required_result_hash=r.content_hash))) loop
  perform ecos_meta.wake_work(w.id,corr,'stage_result_committed');
 end loop;
 return new;
end $$;
create trigger release_dependents after insert on ecos.stage_result for each row execute function ecos_meta.release_dependents();

create function ecos_meta.work_package(ctx jsonb,f jsonb) returns jsonb language plpgsql set search_path=pg_catalog set timezone='UTC' as $$
declare c ecos.work_claim; w ecos.work_occurrence; t ecos.task; wc ecos.work_context; s ecos.work_stage_definition; refs jsonb; r jsonb; payload jsonb; bytes_ bigint;
begin
 c:=ecos_meta.check_fence(ctx,f); select * into w from ecos.work_occurrence where id=c.occurrence_id;
 select * into wc from ecos.work_context where occurrence_id=w.id;
 if wc.occurrence_id is null then raise exception 'invalid_contract' using errcode='22023'; end if;
 if not exists(select 1 from ecos_meta.principal_operation where principal_id=(ctx->>'principal_id')::uuid and operation=wc.operation) then raise exception 'forbidden' using errcode='42501'; end if;
 if w.task_id is not null then perform ecos_meta.require_access((ctx->>'principal_id')::uuid,'task',w.task_id); select * into t from ecos.task where id=w.task_id; end if;
 refs:=wc.source_references||wc.memory_references;
 perform ecos_meta.verify_sources((ctx->>'principal_id')::uuid,refs);
 select * into s from ecos.work_stage_definition where id=w.stage_definition_id;
 payload:=jsonb_build_object('occurrence',to_jsonb(w),'stage',to_jsonb(s),
 'task',case when t.id is null then null else jsonb_build_object('id',t.id,'title',t.title,'record_version',t.record_version,'lifecycle_state',t.lifecycle_state) end,
 'operation',(select document from ecos_meta.operation_contract where name=wc.operation),
 'capability_requirements',(select coalesce(jsonb_agg(jsonb_build_object('name',capability_name,'minimum_version',minimum_version)),'[]') from ecos.stage_capability_requirement where stage_definition_id=s.id),
 'source_references',wc.source_references,'memory_references',wc.memory_references,'input',wc.input,
 'deadline_sla',(select to_jsonb(p) from ecos.work_priority p where occurrence_id=w.id),
 'approval_context',(select coalesce(jsonb_agg(to_jsonb(a)),'[]') from ecos.work_approval a where occurrence_id=w.id),
 'correlation_id',ctx->'correlation_id','fence',f,'context_version',wc.record_version,
 'retry_policy',(select to_jsonb(r) from ecos.work_definition d join ecos.retry_policy r on r.id=d.retry_policy_id where d.id=w.work_definition_id),
 'idempotency',jsonb_build_object('scope','principal + operation + key','occurrence_key',w.occurrence_key));
 bytes_:=octet_length(payload::text); if bytes_>32768 then raise exception 'invalid_contract' using errcode='22023'; end if;
 insert into ecos.package_measurement(occurrence_id,principal_id,payload_bytes,source_count) values(w.id,(ctx->>'principal_id')::uuid,bytes_,jsonb_array_length(refs));
 return payload;
end $$;

alter function ecos_meta.require_operation_scope(text,jsonb,uuid) rename to require_operation_scope_phase1;
create function ecos_meta.require_operation_scope(op text,args jsonb,principal uuid) returns void language plpgsql stable set search_path=pg_catalog as $$
begin
 perform ecos_meta.require_operation_scope_phase1(op,args,principal);
 if op in ('work.package','work.fail','work.defer','work.release','work.dead_letter','semantic.proposal.submit') then perform ecos_meta.require_access(principal,'work_occurrence',(args->'fence'->>'occurrence_id')::uuid); end if;
 if op='semantic.proposal.submit' then
  perform ecos_meta.verify_sources(principal,args->'proposal'->'source_references');
 end if;
end $$;

create function ecos_meta.presence_heartbeat(ctx jsonb,args jsonb) returns jsonb language plpgsql set search_path=pg_catalog as $$
declare inst uuid:=(ctx->>'executor_instance_id')::uuid; observed timestamptz:=(args->>'observed_at')::timestamptz; ttl int; hid uuid; count_ int;
begin
 perform 1 from ecos.executor_presence where executor_instance_id=inst and status='available' for update;
 if not found or observed>clock_timestamp()+interval '5 seconds' then raise exception 'gate_blocked' using errcode='23514'; end if;
 select p.stale_seconds into ttl from ecos.executor_instance i join ecos.executor e on e.id=i.executor_id join ecos_meta.executor_policy p on p.surface=e.surface where i.id=inst and e.enabled;
 if ttl is null or observed<=clock_timestamp()-make_interval(secs=>ttl) then raise exception 'gate_blocked' using errcode='23514'; end if;
 select count(*) into count_ from ecos.work_claim where executor_instance_id=inst and state='active' and expires_at>clock_timestamp();
 insert into ecos.heartbeat(executor_instance_id,observed_at,received_at,valid_until,availability,evidence_hash) values(inst,observed,clock_timestamp(),least(observed,clock_timestamp())+make_interval(secs=>ttl),'available',args->>'evidence_hash') returning id into hid;
 insert into ecos.heartbeat_load values(hid,(args->>'reported_running')::int,count_,(args->>'load_basis_points')::int);
 return jsonb_build_object('heartbeat_id',hid,'running_count',count_,'stale_seconds',ttl);
end $$;

alter function ecos_meta.apply_operation(text,jsonb,jsonb) rename to apply_operation_phase1;
create function ecos_meta.apply_operation(op text,ctx jsonb,args jsonb) returns jsonb language plpgsql set search_path=pg_catalog set timezone='UTC' as $$
declare data_ jsonb:='{}'; status_ text:='committed'; inst uuid:=(ctx->>'executor_instance_id')::uuid; principal uuid:=(ctx->>'principal_id')::uuid; corr uuid:=(ctx->>'correlation_id')::uuid; s text; pol ecos_meta.executor_policy; count_ int; c ecos.work_claim; run_ ecos.execution_run; retry_ ecos.retry_policy; until_ timestamptz; w record; n int:=0; p jsonb; prior ecos.proposal_submission; oid uuid; pressure_ text;
begin
 if op='executor.register' then
  perform pg_advisory_xact_lock(684026,200);
  select e.surface into s from ecos.executor_instance i join ecos.executor e on e.id=i.executor_id where i.id=inst and i.principal_id=principal and e.enabled;
  if s is null then raise exception 'forbidden' using errcode='42501'; end if;
  select * into pol from ecos_meta.executor_policy where surface=s;
  if exists(select 1 from ecos.executor_presence where executor_instance_id=inst and status='stopped') then raise exception 'gate_blocked' using errcode='23514'; end if;
  select count(*) into count_ from ecos.executor_presence p join ecos.executor_instance i on i.id=p.executor_instance_id join ecos.executor e on e.id=i.executor_id join ecos.v_node_health h on h.executor_instance_id=i.id where e.surface=s and p.status='available' and h.availability='available' and i.id<>inst;
  if count_>=pol.maximum_instances then raise exception 'gate_blocked' using errcode='23514'; end if;
  insert into ecos.executor_presence(executor_instance_id,host,runtime,software_version,status,evidence_hash) values(inst,args->>'host',args->>'runtime',args->>'software_version','available',args->>'evidence_hash')
  on conflict(executor_instance_id) do update set host=excluded.host,runtime=excluded.runtime,software_version=excluded.software_version,status='available',evidence_hash=excluded.evidence_hash,record_version=ecos.executor_presence.record_version+1;
  data_:=ecos_meta.presence_heartbeat(ctx,jsonb_build_object('observed_at',clock_timestamp(),'evidence_hash',args->>'evidence_hash','reported_running',0,'load_basis_points',0));
  data_:=data_||jsonb_build_object('executor_instance_id',inst,'surface',s,'authority','PRE_CUTOVER_NON_AUTHORITATIVE','capabilities',(select coalesce(jsonb_agg(jsonb_build_object('name',capability_name,'version',capability_version)),'[]') from ecos.executor_capability where executor_instance_id=inst and expires_at>clock_timestamp()));
 elsif op='executor.heartbeat' then data_:=ecos_meta.presence_heartbeat(ctx,args);
 elsif op='executor.stop' then
  perform 1 from ecos.executor_presence where executor_instance_id=inst for update;
  if not found then raise exception 'gate_blocked' using errcode='23514'; end if;
  if exists(select 1 from ecos.work_claim where executor_instance_id=inst and state='active' and expires_at>clock_timestamp()) then raise exception 'gate_blocked' using errcode='23514'; end if;
  update ecos.executor_presence set status='stopped',stopped_at=clock_timestamp(),record_version=record_version+1 where executor_instance_id=inst;
  data_:=jsonb_build_object('executor_instance_id',inst,'reason',args->>'reason');
 elsif op='work.next' then
  data_:=ecos_meta.claim_work(ctx,args);
  if data_->'claim'='null'::jsonb then status_:='NO_ELIGIBLE_WORK'; else data_:=data_||jsonb_build_object('work_package',ecos_meta.work_package(ctx,ecos_meta.fence(data_->'claim'))); status_:='CLAIMED'; end if;
 elsif op='work.package' then data_:=ecos_meta.work_package(ctx,args->'fence');
 elsif op in ('work.fail','work.defer','work.release','work.dead_letter') then
  c:=ecos_meta.check_fence(ctx,args->'fence'); select * into run_ from ecos.execution_run where claim_id=c.id;
  select r.* into retry_ from ecos.work_occurrence o join ecos.work_definition d on d.id=o.work_definition_id join ecos.retry_policy r on r.id=d.retry_policy_id where o.id=c.occurrence_id;
  until_:=case when op='work.defer' then (args->>'until')::timestamptz when op='work.fail' then clock_timestamp()+make_interval(secs=>least(retry_.max_delay_seconds,retry_.initial_delay_seconds*power(retry_.backoff_multiplier,least(20,(select attempt_count-1 from ecos.work_occurrence where id=c.occurrence_id))))::int) else clock_timestamp() end;
  if op='work.defer' and (until_<=clock_timestamp() or until_>clock_timestamp()+interval '30 days') then raise exception 'invalid_contract' using errcode='22023'; end if;
  update ecos.work_occurrence set state='retry_wait',retry_at=until_,record_version=record_version+1 where id=c.occurrence_id;
  if op='work.dead_letter' or (op='work.fail' and (not (args->>'retryable')::boolean or (select attempt_count from ecos.work_occurrence where id=c.occurrence_id)>=retry_.max_attempts)) then update ecos.work_occurrence set state='dead_lettered',record_version=record_version+1 where id=c.occurrence_id; end if;
  update ecos.work_claim set state='released',record_version=record_version+1 where id=c.id;
  update ecos.execution_run set state=case when op='work.fail' then 'failed' else 'cancelled' end,ended_at=clock_timestamp(),record_version=record_version+1 where id=run_.id;
  perform ecos_meta.execution_event(run_.id,case when op='work.fail' then 'failed' else 'cancelled' end,args->>'reason');
  data_:=jsonb_build_object('occurrence_id',c.occurrence_id,'retry_at',until_);
 elsif op='semantic.proposal.submit' then
  c:=ecos_meta.check_fence(ctx,args->'fence'); p:=args->'proposal';
  if not exists(select 1 from ecos.work_stage_definition where id=c.stage_definition_id and kind='semantic') or p->>'correlation_id'<>corr::text or ecos_meta.content_hash(p)<>p->>'content_hash' then raise exception 'invalid_contract' using errcode='22023'; end if;
  select * into prior from ecos.proposal_submission where proposal_id=(p->>'id')::uuid;
  if found then if prior.content_hash<>p->>'content_hash' or prior.principal_id<>principal or prior.occurrence_id<>c.occurrence_id then raise exception 'idempotency_conflict' using errcode='23505'; end if;
  else insert into ecos.proposal_submission values((p->>'id')::uuid,c.occurrence_id,principal,p,p->>'content_hash',clock_timestamp()); end if;
  data_:=jsonb_build_object('proposal_id',p->'id','content_hash',p->'content_hash');
 elsif op='resource.observe' then
  if (args->>'observed_at')::timestamptz>clock_timestamp()+interval '5 seconds' then raise exception 'invalid_contract' using errcode='22023'; end if;
  insert into ecos.resource_usage_window(provider,metric,observed_at,value,evidence_hash,principal_id) values(args->>'provider',args->>'metric',(args->>'observed_at')::timestamptz,(args->>'value')::bigint,args->>'evidence_hash',principal);
  pressure_:=ecos_meta.resource_pressure(args->>'provider',args->>'metric',clock_timestamp()); data_:=jsonb_build_object('pressure',pressure_);
 elsif op='recovery.sweep' then
  -- Safety net only: bounded, object-scoped work; no global scoring or provider calls.
  for w in select o.id from ecos.work_occurrence o join ecos_meta.object_grant g on g.record_type='work_occurrence' and g.record_id=o.id and g.principal_id=principal where o.state in ('claimed','running') and exists(select 1 from ecos.work_claim c where c.occurrence_id=o.id and c.state='active' and c.expires_at<=clock_timestamp()) order by o.id for update of o skip locked limit (args->>'limit')::int loop
   perform ecos_meta.repair_expired_claim(w.id,corr); n:=n+1;
  end loop;
  for w in select o.id from ecos.work_occurrence o join ecos_meta.object_grant g on g.record_type='work_occurrence' and g.record_id=o.id and g.principal_id=principal where o.state in ('pending','ready','retry_wait') and o.due_at<=clock_timestamp() and (o.retry_at is null or o.retry_at<=clock_timestamp()) and not exists(select 1 from ecos.work_wakeup x where x.occurrence_id=o.id and x.consumed_at is null) and not exists(select 1 from ecos.work_dependency d where d.occurrence_id=o.id and not exists(select 1 from ecos.stage_result r where r.occurrence_id=d.prerequisite_occurrence_id and r.result_schema_id=d.required_result_schema_id and (d.required_result_hash is null or d.required_result_hash=r.content_hash))) order by o.id limit (args->>'limit')::int loop
   perform ecos_meta.wake_work(w.id,corr,'recovery_sweep');
  end loop;
  update ecos.executor_presence p set status='unavailable',record_version=p.record_version+1 from ecos.v_node_health h where h.executor_instance_id=p.executor_instance_id and h.availability in ('unknown','unavailable') and p.status='available';
  data_:=jsonb_build_object('recovered_claims',n,'pending_wakeups',(select count(*) from ecos.work_wakeup where consumed_at is null),'outbox_recoverable',(select count(*) from ecos.outbox_item where state in ('pending','retry_wait') or (state='claimed' and lease_expires_at<=clock_timestamp())));
 else return ecos_meta.apply_operation_phase1(op,ctx,args);
 end if;
 insert into ecos.control_plane_event(event_type,entity_id,correlation_id,payload) values(op,inst,corr,data_);
 return jsonb_build_object('schema_version','1.0.0','correlation_id',corr,'status',status_,'data',data_);
end $$;

create view ecos.v_executor_status with(security_invoker=true) as
 select i.id,i.executor_id,e.surface,e.enabled,p.host,p.runtime,p.software_version,p.started_at,p.stopped_at,p.record_version,h.valid_until,h.received_at,
 case when p.status='stopped' then 'stopped' when p.status='unavailable' or h.availability in ('unknown','unavailable') then 'unavailable' else h.availability end status,
 (select count(*) from ecos.work_claim c where c.executor_instance_id=i.id and c.state='active' and c.expires_at>statement_timestamp()) running_count
 from ecos.executor_instance i join ecos.executor e on e.id=i.executor_id left join ecos.executor_presence p on p.executor_instance_id=i.id left join ecos.v_node_health h on h.executor_instance_id=i.id;
create view ecos.v_resource_pressure with(security_invoker=true) as
 select m.*,b.hard_limit,b.elevated_limit,b.window_seconds,b.source quota_source,b.verification,b.effective_at,ecos_meta.resource_pressure(m.provider,m.metric,statement_timestamp()) pressure
 from ecos.resource_metric m join ecos.resource_budget b using(provider,metric);
create view ecos.v_current_claims with(security_invoker=true) as select c.*,statement_timestamp()-c.acquired_at age from ecos.work_claim c where state='active';
create view ecos.v_ready_work with(security_invoker=true) as select * from ecos.v_work_readiness where (selection_evidence->>'eligible')::boolean;
create view ecos.v_blocked_work with(security_invoker=true) as select * from ecos.v_work_readiness where not (selection_evidence->>'eligible')::boolean;
create view ecos.v_recent_failures with(security_invoker=true) as select id,occurrence_id,executor_instance_id,state,created_at,ended_at from ecos.execution_run where state in ('failed','abandoned') and created_at>statement_timestamp()-interval '24 hours';
create view ecos.v_dead_letters with(security_invoker=true) as select id,stage_definition_id,attempt_count,created_at from ecos.work_occurrence where state='dead_lettered';
create view ecos.v_work_aging with(security_invoker=true) as select o.id,o.state,o.due_at,p.deadline,p.sla_deadline,statement_timestamp()-o.due_at age from ecos.work_occurrence o left join ecos.work_priority p on p.occurrence_id=o.id where o.state not in ('succeeded','cancelled');
create function ecos.control_plane_health() returns jsonb language sql security definer set search_path=pg_catalog as $$
 select jsonb_build_object('as_of',statement_timestamp(),'authority','PRE_CUTOVER_NON_AUTHORITATIVE',
 'active_executors',(select count(*) from ecos.v_executor_status where status='available'),
 'stale_executors',(select count(*) from ecos.v_executor_status where status='unavailable'),
 'active_claims',(select count(*) from ecos.work_claim where state='active' and expires_at>statement_timestamp()),
 'outbox_backlog',(select count(*) from ecos.outbox_item where state in ('pending','retry_wait','claimed')),
 'outbox_oldest',(select min(created_at) from ecos.outbox_item where state in ('pending','retry_wait','claimed')),
 'claim_oldest',(select min(acquired_at) from ecos.work_claim where state='active'),
 'visible_connections',(select count(*) from pg_stat_activity where datname=current_database()),
 'max_connections',current_setting('max_connections')::int,
 'visible_lock_waits',(select count(*) from pg_stat_activity where datname=current_database() and wait_event_type='Lock'),
 'pool_utilization',null,'query_latency',null,'unavailable_metrics','["pool_utilization","query_latency","host_cpu","host_bandwidth"]'::jsonb) $$;

revoke all on all functions in schema ecos_meta from public;
revoke all on function ecos.control_plane_health() from public;
grant execute on function ecos.control_plane_health() to read_only_analytics,operations_api,auditor;
grant select on all tables in schema ecos to auditor,backup_operator;
grant select on ecos_meta.executor_policy to auditor,backup_operator;
reset role;
