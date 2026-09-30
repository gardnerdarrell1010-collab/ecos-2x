-- Extend the existing domain authority; preserve accepted migrations and APIs.
set local role ecos_owner;
insert into ecos.capability(name,version,description) values
 ('ecos.2x.execute',1,'Authorization to consume PostgreSQL-native ECOS 2.x work; not connectivity or business authority')
 on conflict(name,version) do nothing;
alter table ecos_meta.principal_domain add column executor_generation text not null default '2X'
 check(executor_generation in ('1X','2X'));
alter function ecos_meta.require_domain(uuid,text) rename to require_domain_epoch23;
create function ecos_meta.require_domain(principal uuid,operation text) returns void
 language plpgsql set search_path=pg_catalog as $$
begin
 if not exists(select 1 from ecos_meta.principal_domain where principal_id=principal and executor_generation='2X') then
  raise exception 'forbidden' using errcode='42501';
 end if;
 perform ecos_meta.require_domain_epoch23(principal,operation);
 if exists(select 1 from ecos.executor_instance i join ecos.executor e on e.id=i.executor_id
  where i.principal_id=principal and i.id=(ecos_meta.current_principal()).executor_instance_id and e.surface in ('ONLINE_SEMANTIC','RESIDENT_DETERMINISTIC_PROVIDER'))
 and not exists(select 1 from ecos.executor_instance i join ecos.executor_capability c on c.executor_instance_id=i.id
  where i.principal_id=principal and i.id=(ecos_meta.current_principal()).executor_instance_id and c.capability_name='ecos.2x.execute' and c.capability_version>=1 and c.expires_at>clock_timestamp()) then
  raise exception 'gate_blocked' using errcode='23514';
 end if;
end $$;

create table ecos_meta.domain_effect_target(target text primary key, domain text not null references ecos_meta.domain_authority);
insert into ecos_meta.domain_effect_target values('toast.compatibility','toast.acquisition'),('toast.dashboard','toast.acquisition');
create table ecos_meta.domain_effect_scope(
 principal_id uuid not null, target text not null references ecos_meta.domain_effect_target, primary key(principal_id,target));
create table ecos_meta.domain_effect_binding(
 command_id uuid primary key references ecos.provider_command,
 principal_id uuid not null, domain text not null references ecos_meta.domain_authority,
 generation text not null check(generation in ('1X','2X')), epoch bigint not null,
 execution_key text not null, target text not null,
 unique(domain,generation,execution_key,target));

-- Existing provider command/attempt/result records retain ambiguous outcomes.
-- A lost SQL connection must NOT release permission to transfer while HTTP may
-- still finish. Unresolved effects block transfer until governed reconciliation.
create function ecos_meta.block_unresolved_domain_effect() returns trigger
 language plpgsql set search_path=pg_catalog as $$
begin
 if new.owner<>old.owner and exists(select 1 from ecos_meta.domain_effect_binding b
  join ecos.provider_command c on c.id=b.command_id where b.domain=old.domain
  and c.outcome not in ('succeeded','failed','reconciled')) then
  raise exception 'domain_effect_reconciliation_required' using errcode='23514';
 end if;
 return new;
end $$;
create trigger domain_effect_drain before update on ecos_meta.domain_authority
 for each row execute function ecos_meta.block_unresolved_domain_effect();

create function ecos_meta.effect_authority(principal uuid,target_ text,epoch_ bigint)
 returns ecos_meta.principal_domain language plpgsql set search_path=pg_catalog as $$
declare b ecos_meta.principal_domain; a ecos_meta.domain_authority;
begin
 select * into b from ecos_meta.principal_domain where principal_id=principal;
 if b.principal_id is null or b.execution_mode<>'production' or not exists(
  select 1 from ecos_meta.domain_effect_scope s join ecos_meta.domain_effect_target t on t.target=s.target
  where s.principal_id=principal and s.target=target_ and t.domain=b.domain) then
  raise exception 'forbidden' using errcode='42501';
 end if;
 select * into a from ecos_meta.domain_authority where domain=b.domain for share;
 if a.owner<>b.executor_generation or a.epoch<>epoch_ or b.authority_epoch<>epoch_ then
  raise exception 'stale_authority_epoch' using errcode='23514';
 end if;
 if b.executor_generation='2X' then perform ecos_meta.require_domain(principal,'provider.result.record'); end if;
 return b;
end $$;

create function ecos.domain_effect_grant(target_ text) returns jsonb
 language plpgsql security definer set search_path=pg_catalog as $$
declare p ecos_meta.principal_binding; b ecos_meta.principal_domain;
begin
 p:=ecos_meta.current_principal();
 select * into b from ecos_meta.principal_domain where principal_id=p.principal_id;
 b:=ecos_meta.effect_authority(p.principal_id,target_,b.authority_epoch);
 return jsonb_build_object('domain',b.domain,'generation',b.executor_generation,'epoch',b.authority_epoch,'target',target_);
end $$;

create function ecos.domain_effect_begin(target_ text,epoch_ bigint,execution_key_ text,request_hash_ text)
 returns jsonb language plpgsql security definer set search_path=pg_catalog as $$
declare p ecos_meta.principal_binding; b ecos_meta.principal_domain; prior ecos_meta.domain_effect_binding;
 c ecos.provider_command; command_ uuid:=gen_random_uuid(); attempt_ uuid;
begin
 p:=ecos_meta.current_principal(); b:=ecos_meta.effect_authority(p.principal_id,target_,epoch_);
 if length(execution_key_) not between 1 and 256 or request_hash_ !~ '^[a-f0-9]{64}$' then raise exception 'invalid_contract'; end if;
 perform pg_advisory_xact_lock(hashtextextended(b.domain||':'||b.executor_generation||':'||execution_key_||':'||target_,0));
 select * into prior from ecos_meta.domain_effect_binding where domain=b.domain and generation=b.executor_generation
  and execution_key=execution_key_ and target=target_;
 if found then
  select * into c from ecos.provider_command where id=prior.command_id;
  if prior.principal_id<>p.principal_id or prior.epoch<>epoch_ or c.request_hash<>request_hash_ then raise exception 'effect_replay_conflict'; end if;
  if c.outcome<>'reconciled' or not exists(select 1 from ecos.provider_result where provider_command_id=c.id and reconciled_outcome='succeeded') then raise exception 'domain_effect_reconciliation_required' using errcode='23514'; end if;
  return jsonb_build_object('command_id',c.id,'already_completed',true);
 end if;
 insert into ecos.provider_command(id,provider,account_scope,command_type,idempotency_key,request_schema_id,
  request_artifact_uri,request_hash,correlation_id,causation_id,outcome,reconciliation_strategy)
 values(command_,'compatibility',b.domain,target_,execution_key_,'domain-effect-v1',
  'ecos:domain-effect:'||command_::text,request_hash_,command_,command_,'unknown_outcome','manual_only');
 insert into ecos.provider_attempt(provider_command_id,attempt_number,request_hash,started_at,outcome)
 values(command_,1,request_hash_,clock_timestamp(),'unknown_outcome') returning id into attempt_;
 insert into ecos_meta.domain_effect_binding values(command_,p.principal_id,b.domain,b.executor_generation,epoch_,execution_key_,target_);
 insert into ecos_meta.object_domain values('provider_command',command_,b.domain);
 return jsonb_build_object('command_id',command_,'attempt_id',attempt_,'already_completed',false);
end $$;

create function ecos.domain_effect_finish(command_ uuid,epoch_ bigint,evidence_hash_ text) returns void
 language plpgsql security definer set search_path=pg_catalog as $$
declare p ecos_meta.principal_binding; b ecos_meta.domain_effect_binding; a uuid; c ecos.provider_command;
begin
 p:=ecos_meta.current_principal();
 select * into b from ecos_meta.domain_effect_binding where command_id=command_;
 if b.principal_id is distinct from p.principal_id or b.epoch is distinct from epoch_ then raise exception 'forbidden' using errcode='42501'; end if;
 perform ecos_meta.effect_authority(p.principal_id,b.target,epoch_);
 select * into c from ecos.provider_command where id=command_ for update;
 if evidence_hash_ !~ '^[a-f0-9]{64}$' then raise exception 'invalid_contract'; end if;
 if c.outcome='reconciled' then
  if not exists(select 1 from ecos.provider_result where provider_command_id=command_ and evidence_hash=evidence_hash_) then raise exception 'effect_replay_conflict'; end if;
  return;
 end if;
 select id into a from ecos.provider_attempt where provider_command_id=command_ and attempt_number=1;
 insert into ecos.provider_result(provider_command_id,provider_attempt_id,outcome,observed_at,evidence_hash,reconciled_outcome)
 values(command_,a,'reconciled',clock_timestamp(),evidence_hash_,'succeeded');
 update ecos.provider_command set outcome='reconciled',record_version=record_version+1 where id=command_;
end $$;

alter table ecos_meta.domain_effect_scope enable row level security;
alter table ecos_meta.domain_effect_target enable row level security;
alter table ecos_meta.domain_effect_binding enable row level security;
revoke all on ecos_meta.domain_effect_scope,ecos_meta.domain_effect_binding,ecos_meta.domain_effect_target from public,executor,operations_api,provider_adapter;
revoke all on all functions in schema ecos_meta from public;
revoke all on function ecos.domain_effect_grant(text),ecos.domain_effect_begin(text,bigint,text,text),ecos.domain_effect_finish(uuid,bigint,text) from public;
grant execute on function ecos.domain_effect_grant(text),ecos.domain_effect_begin(text,bigint,text,text),ecos.domain_effect_finish(uuid,bigint,text) to provider_adapter;
reset role;
