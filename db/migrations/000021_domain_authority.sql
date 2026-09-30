-- Owner decision 2026-09-29: production infrastructure, domain-scoped authority.
-- Forward migration; accepted migration bytes are unchanged.
set local role ecos_owner;
alter table ecos_meta.database_identity drop constraint database_identity_environment_check;
alter table ecos_meta.database_identity drop constraint database_identity_authority_check;
alter table ecos_meta.database_identity drop constraint database_identity_provider_effects_enabled_check;
update ecos_meta.database_identity set environment='production',authority='domain_scoped',provider_effects_enabled=true;
alter table ecos_meta.database_identity add check(environment='production');
alter table ecos_meta.database_identity add check(authority='domain_scoped');
comment on column ecos_meta.database_identity.provider_effects_enabled is 'Infrastructure supports effects; NOT authorization. Domain ownership, principal grants, fence and provider contract must all permit each effect.';
create table ecos_meta.domain_authority(
 domain text primary key check(domain ~ '^[a-z][a-z0-9_.-]{0,127}$'),
 owner text not null check(owner in ('1X','2X')), epoch bigint not null default 1 check(epoch>0),
 evidence text not null, updated_at timestamptz not null default clock_timestamp());
insert into ecos_meta.domain_authority(domain,owner,evidence) values
 ('synthetic.acceptance','2X','Isolated synthetic fixtures only; not business domain authority'),
 ('toast.acquisition','1X','Owner decision: A029/A047 stay 1.x until Wave 1 acceptance and transfer'),
 ('staffing.features','1X','A029-B remains 1.x until Wave 4');
create table ecos_meta.principal_domain(
 principal_id uuid primary key, domain text not null references ecos_meta.domain_authority,
 execution_mode text not null check(execution_mode in ('synthetic','shadow','production')),
 authority_epoch bigint not null check(authority_epoch>0),
 check((execution_mode='synthetic')=(domain='synthetic.acceptance')));
create table ecos_meta.object_domain(
 record_type text not null, record_id uuid not null, domain text not null references ecos_meta.domain_authority,
 primary key(record_type,record_id));
create table ecos_meta.domain_authority_event(
 id bigint generated always as identity primary key, domain text not null,
 old_owner text not null,new_owner text not null,old_epoch bigint not null,new_epoch bigint not null,
 evidence text not null,changed_at timestamptz not null default clock_timestamp());
create function ecos_meta.audit_domain_authority() returns trigger language plpgsql set search_path=pg_catalog as $$
begin
 if new.owner<>old.owner then
  if new.epoch<>old.epoch+1 or new.evidence=old.evidence or length(new.evidence)<20 then raise exception 'domain transfer evidence and epoch required'; end if;
  if exists(select 1 from ecos.work_claim c join ecos_meta.object_domain d on d.record_type='work_occurrence' and d.record_id=c.occurrence_id where d.domain=old.domain and c.state='active' and c.expires_at>clock_timestamp()) then raise exception 'domain claims must drain before transfer' using errcode='23514'; end if;
  insert into ecos_meta.domain_authority_event(domain,old_owner,new_owner,old_epoch,new_epoch,evidence) values(old.domain,old.owner,new.owner,old.epoch,new.epoch,new.evidence);
 elsif new.epoch<>old.epoch then raise exception 'epoch changes require ownership transfer'; end if;
 return new;
end $$;
create trigger domain_authority_audit before update on ecos_meta.domain_authority for each row execute function ecos_meta.audit_domain_authority();
create function ecos_meta.require_domain(principal uuid,operation text) returns void language plpgsql set search_path=pg_catalog as $$
declare b ecos_meta.principal_domain; a ecos_meta.domain_authority;
begin
 select * into b from ecos_meta.principal_domain where principal_id=principal;
 if b.principal_id is null then raise exception 'forbidden' using errcode='42501'; end if;
 -- Hold ownership stable for the complete SQL transaction, including replay.
 select * into a from ecos_meta.domain_authority where domain=b.domain for share;
 if b.execution_mode='production' and (a.owner<>'2X' or b.authority_epoch<>a.epoch) then raise exception 'gate_blocked' using errcode='23514'; end if;
 if b.execution_mode='shadow' and operation not in
  ('executor.register','executor.heartbeat','executor.stop','work.next','work.claim','work.package','work.renew','work.complete','work.fail','work.defer','work.release','recovery.sweep','toast.batch.commit')
 then raise exception 'forbidden' using errcode='42501'; end if;
end $$;
alter function ecos_meta.require_access(uuid,text,uuid) rename to require_access_phase2;
create function ecos_meta.require_access(principal uuid,kind text,entity uuid) returns void language plpgsql stable set search_path=pg_catalog as $$
declare b ecos_meta.principal_domain; d text;
begin
 perform ecos_meta.require_access_phase2(principal,kind,entity);
 select * into b from ecos_meta.principal_domain where principal_id=principal;
 select domain into d from ecos_meta.object_domain where record_type=kind and record_id=entity;
 if b.principal_id is null or (d is not null and d<>b.domain) or (b.execution_mode<>'synthetic' and d is null) then raise exception 'forbidden' using errcode='42501'; end if;
end $$;
alter function ecos_meta.selection(uuid,uuid,timestamptz) rename to selection_phase2;
create function ecos_meta.selection(occurrence uuid,instance uuid,at_ timestamptz) returns jsonb language plpgsql stable set search_path=pg_catalog as $$
declare result_ jsonb; b ecos_meta.principal_domain; a ecos_meta.domain_authority; d text;
begin
 result_:=ecos_meta.selection_phase2(occurrence,instance,at_);
 select pd.* into b from ecos_meta.principal_domain pd join ecos.executor_instance i on i.principal_id=pd.principal_id where i.id=instance;
 select * into a from ecos_meta.domain_authority where domain=b.domain;
 select domain into d from ecos_meta.object_domain where record_type='work_occurrence' and record_id=occurrence;
 if b.principal_id is null or (d is not null and d<>b.domain) or (b.execution_mode<>'synthetic' and d is null)
 or (b.execution_mode='production' and (a.owner<>'2X' or a.epoch<>b.authority_epoch)) then
 result_:=jsonb_set(jsonb_set(result_,'{eligible}','false'),'{reason_codes}',(result_->'reason_codes')||'"domain_authority"'::jsonb);
 end if;
 return result_;
end $$;
create or replace function ecos_meta.apply_operation(op text,ctx jsonb,args jsonb) returns jsonb language plpgsql set search_path=pg_catalog set timezone='UTC' as $$
declare data_ jsonb:='{}'; status_ text:='committed'; inst uuid:=(ctx->>'executor_instance_id')::uuid; principal uuid:=(ctx->>'principal_id')::uuid; corr uuid:=(ctx->>'correlation_id')::uuid; s text; pol ecos_meta.executor_policy; count_ int; c ecos.work_claim; run_ ecos.execution_run; retry_ ecos.retry_policy; until_ timestamptz; w record; n int:=0; proposal_ jsonb; prior ecos.proposal_submission; pressure_ text;
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
  data_:=data_||jsonb_build_object('executor_instance_id',inst,'surface',s,'authority','DOMAIN_SCOPED_PRODUCTION','capabilities',(select coalesce(jsonb_agg(jsonb_build_object('name',capability_name,'version',capability_version)),'[]') from ecos.executor_capability where executor_instance_id=inst and expires_at>clock_timestamp()));
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
  c:=ecos_meta.check_fence(ctx,args->'fence'); proposal_:=args->'proposal';
  if not exists(select 1 from ecos.work_stage_definition where id=c.stage_definition_id and kind='semantic') or proposal_->>'correlation_id'<>corr::text or ecos_meta.content_hash(proposal_)<>proposal_->>'content_hash' then raise exception 'invalid_contract' using errcode='22023'; end if;
  select * into prior from ecos.proposal_submission where proposal_id=(proposal_->>'id')::uuid;
  if found then if prior.content_hash<>proposal_->>'content_hash' or prior.principal_id<>principal or prior.occurrence_id<>c.occurrence_id then raise exception 'idempotency_conflict' using errcode='23505'; end if;
  else insert into ecos.proposal_submission values((proposal_->>'id')::uuid,c.occurrence_id,principal,proposal_,proposal_->>'content_hash',clock_timestamp()); end if;
  data_:=jsonb_build_object('proposal_id',proposal_->'id','content_hash',proposal_->'content_hash');
 elsif op='resource.observe' then
  if (args->>'observed_at')::timestamptz>clock_timestamp()+interval '5 seconds' then raise exception 'invalid_contract' using errcode='22023'; end if;
  insert into ecos.resource_usage_window(provider,metric,observed_at,value,evidence_hash,principal_id) values(args->>'provider',args->>'metric',(args->>'observed_at')::timestamptz,(args->>'value')::bigint,args->>'evidence_hash',principal);
  pressure_:=ecos_meta.resource_pressure(args->>'provider',args->>'metric',clock_timestamp()); data_:=jsonb_build_object('pressure',pressure_);
 elsif op='recovery.sweep' then
  -- Safety net only: bounded, object-scoped work; no global scoring or provider calls.
  for w in select o.id from ecos.work_occurrence o join ecos_meta.object_grant g on g.record_type='work_occurrence' and g.record_id=o.id and g.principal_id=principal where o.state in ('claimed','running') and exists(select 1 from ecos.work_claim claim_ where claim_.occurrence_id=o.id and claim_.state='active' and claim_.expires_at<=clock_timestamp()) order by o.id for update of o skip locked limit (args->>'limit')::int loop
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
create or replace function ecos.control_plane_health() returns jsonb language sql security definer set search_path=pg_catalog as $$
 select jsonb_build_object('as_of',statement_timestamp(),'authority','DOMAIN_SCOPED_PRODUCTION',
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
 perform ecos_meta.require_domain(p.principal_id,operation);
 perform ecos_meta.require_operation_scope(operation,args,p.principal_id);
 hash_:=ecos_meta.content_hash(request);
 perform pg_advisory_xact_lock(hashtextextended(p.principal_id::text||':'||operation||':'||(ctx->>'idempotency_key'),0));
 select * into prior from ecos_meta.operation_receipt r where r.principal_id=p.principal_id and r.operation=operate.operation and r.idempotency_key=ctx->>'idempotency_key';
 if found then if prior.request_hash<>hash_ then raise exception 'idempotency_conflict' using errcode='23505'; end if; if operation='work.claim' and prior.result->'claim'<>'null'::jsonb then perform ecos_meta.require_access(p.principal_id,'work_occurrence',(prior.result->'claim'->>'occurrence_id')::uuid); end if; if operation='work.next' and prior.result->>'status'='CLAIMED' then perform ecos_meta.require_package_scope(p.principal_id,prior.result->'data'->'work_package'); elsif operation='work.package' then perform ecos_meta.require_package_scope(p.principal_id,prior.result->'data'); end if; return prior.result; end if;
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
create or replace function ecos.claim_outbox(lease_seconds integer default 30) returns jsonb language plpgsql security definer set search_path=pg_catalog as $$
declare p ecos_meta.principal_binding; o ecos.outbox_item; tok uuid:=gen_random_uuid();
begin p:=ecos_meta.current_principal(); perform ecos_meta.require_domain(p.principal_id,'provider.result.record');
 if lease_seconds not between 1 and 300 then raise exception 'invalid_contract'; end if;
 if not exists(select 1 from ecos_meta.principal_operation where principal_id=p.principal_id and operation='provider.result.record') then raise exception 'forbidden' using errcode='42501'; end if;
 perform 1 from ecos_meta.control for share; if exists(select 1 from ecos_meta.control where maintenance) then return null; end if;
 select b.* into o from ecos.outbox_item b where b.available_at<=clock_timestamp() and (b.state in ('pending','retry_wait') or (b.state='claimed' and b.lease_expires_at<=clock_timestamp()))
 and ((b.provider_command_id is null and exists(select 1 from ecos.domain_event e join ecos_meta.object_grant g on g.record_type=e.aggregate_type and g.record_id=e.aggregate_id and g.principal_id=p.principal_id where e.id=b.domain_event_id)) or exists(select 1 from ecos_meta.object_grant where principal_id=p.principal_id and record_type='provider_command' and record_id=b.provider_command_id))
 and not exists(select 1 from ecos.provider_command c where c.id=b.provider_command_id and not (c.outcome in ('pending','succeeded') or (c.outcome='reconciled' and exists(select 1 from ecos.provider_result pr where pr.provider_command_id=c.id and pr.reconciled_outcome='succeeded'))))
 order by b.available_at,b.id for update skip locked limit 1;
 if o.id is null then return null; end if;
 if o.provider_command_id is not null then perform ecos_meta.require_access(p.principal_id,'provider_command',o.provider_command_id); end if;
 update ecos.outbox_item set state='claimed',lease_expires_at=clock_timestamp()+make_interval(secs=>lease_seconds),attempt_count=attempt_count+1,record_version=record_version+1 where id=o.id returning * into o;
 insert into ecos_meta.outbox_lease values(o.id,tok,p.principal_id) on conflict(item_id) do update set token=excluded.token,principal_id=excluded.principal_id;
 return jsonb_build_object('item',to_jsonb(o),'lease_token',tok);
end $$;
create or replace function ecos.ack_outbox(item uuid,token uuid) returns void language plpgsql security definer set search_path=pg_catalog as $$
declare p ecos_meta.principal_binding; o ecos.outbox_item;
begin p:=ecos_meta.current_principal(); perform ecos_meta.require_domain(p.principal_id,'provider.result.record'); select * into o from ecos.outbox_item where id=item for update;
 if o.state<>'claimed' or o.lease_expires_at<=clock_timestamp() or not exists(select 1 from ecos_meta.outbox_lease where item_id=item and outbox_lease.token=ack_outbox.token and principal_id=p.principal_id) then raise exception 'expired_fence' using errcode='40001'; end if;
 if o.provider_command_id is not null and not exists(select 1 from ecos.provider_command c where c.id=o.provider_command_id and (c.outcome='succeeded' or (c.outcome='reconciled' and exists(select 1 from ecos.provider_result r where r.provider_command_id=c.id and reconciled_outcome='succeeded')))) then raise exception 'unknown_outcome' using errcode='23514'; end if;
 update ecos.outbox_item set state='delivered',lease_expires_at=null,record_version=record_version+1 where id=item;
end $$;
create or replace function ecos.begin_synthetic_attempt(command uuid,request_hash_ text) returns uuid language plpgsql security definer set search_path=pg_catalog as $$
declare p ecos_meta.principal_binding; c ecos.provider_command; id_ uuid;
begin p:=ecos_meta.current_principal(); perform ecos_meta.require_domain(p.principal_id,'provider.result.record'); perform ecos_meta.require_access(p.principal_id,'provider_command',command);
 select * into c from ecos.provider_command where id=command for update;
 if c.provider<>'synthetic' or c.account_scope<>'development' or c.request_hash<>request_hash_ or c.outcome<>'pending' then raise exception 'unknown_outcome' using errcode='23514'; end if;
 -- Before any simulated effect, hold the command unknown. A consumer crash cannot cause blind resend.
 insert into ecos.provider_attempt(provider_command_id,attempt_number,request_hash,started_at,completed_at,provider_request_id,response_hash,error_class,outcome) values(command,coalesce((select max(attempt_number) from ecos.provider_attempt where provider_command_id=command),0)+1,request_hash_,clock_timestamp(),null,null,null,'ambiguous','unknown_outcome') returning id into id_;
 update ecos.provider_command set outcome='unknown_outcome',record_version=record_version+1 where id=command;
 return id_; end $$;

alter table ecos_meta.domain_authority enable row level security;
alter table ecos_meta.principal_domain enable row level security;
alter table ecos_meta.object_domain enable row level security;
alter table ecos_meta.domain_authority_event enable row level security;
revoke all on ecos_meta.domain_authority,ecos_meta.principal_domain,ecos_meta.object_domain,ecos_meta.domain_authority_event from public,executor,operations_api,provider_adapter;
revoke all on all functions in schema ecos_meta from public;
grant select on ecos_meta.domain_authority,ecos_meta.domain_authority_event to auditor,backup_operator;
reset role;
