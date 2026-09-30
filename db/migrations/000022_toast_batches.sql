-- Wave 1 normalized batch/checkpoint, scoped by domain and execution mode.
set local role ecos_owner;
create table ecos.toast_batch(
 id uuid primary key default gen_random_uuid(), occurrence_id uuid not null unique references ecos.work_occurrence,
 domain text not null references ecos_meta.domain_authority, execution_mode text not null check(execution_mode in ('shadow','production','synthetic')),
 restaurant_hash text not null, business_date date not null, observation jsonb not null, projection jsonb not null,
 observation_json text not null,projection_json text not null,
 source_hash text not null, content_hash text not null, committed_at timestamptz not null default clock_timestamp());
create table ecos.toast_checkpoint(
 domain text not null, execution_mode text not null, restaurant_hash text not null,
 coverage_through date not null, record_version bigint not null, batch_id uuid not null references ecos.toast_batch,
 primary key(domain,execution_mode,restaurant_hash));
create table ecos.toast_closed_date(
 domain text not null,execution_mode text not null,restaurant_hash text not null,business_date date not null,
 observation jsonb not null,batch_id uuid references ecos.toast_batch,
 primary key(domain,execution_mode,restaurant_hash,business_date));
alter function ecos_meta.apply_operation(text,jsonb,jsonb) rename to apply_operation_domain;
create function ecos_meta.apply_operation(op text,ctx jsonb,args jsonb) returns jsonb language plpgsql set search_path=pg_catalog as $$
declare b ecos_meta.principal_domain; old ecos.toast_batch; checkpoint_ ecos.toast_checkpoint; batch_ ecos.toast_batch;
 content_ text; occurrence_ uuid:=(args->'fence'->>'occurrence_id')::uuid; day_ date; site_ text; observation_ jsonb; projection_ jsonb;
begin
 if op<>'toast.batch.commit' then return ecos_meta.apply_operation_domain(op,ctx,args); end if;
 perform ecos_meta.check_fence(ctx,args->'fence');
 select * into b from ecos_meta.principal_domain where principal_id=(ctx->>'principal_id')::uuid;
 if b.domain not in ('toast.acquisition','synthetic.acceptance') then raise exception 'forbidden' using errcode='42501'; end if;
 day_:=(args->>'business_date')::date;site_:=args->>'restaurant_hash';
 observation_:=(args->>'observation_json')::jsonb;projection_:=(args->>'projection_json')::jsonb;
 if day_>=(clock_timestamp() at time zone 'America/Los_Angeles')::date
 or observation_->>'status' is distinct from 'CLOSED_ACTUALS'
 or observation_->>'business_date' is distinct from args->>'business_date'
 or jsonb_typeof(observation_->'rows') is distinct from 'array'
 or projection_->>'schema_version' is distinct from 'ECOS-TOAST-OPERATING-SNAPSHOT-1'
 or length(args->>'projection_json')>=40000 then raise exception 'invalid_contract' using errcode='22023'; end if;
 content_:=ecos_meta.content_hash(args-'fence'-'expected_checkpoint_version');
 perform pg_advisory_xact_lock(hashtextextended('toast:'||b.domain||':'||b.execution_mode||':'||site_,0));
 select * into old from ecos.toast_batch where occurrence_id=occurrence_;
 if found then
  if old.content_hash<>content_ then raise exception 'idempotency_conflict' using errcode='23505'; end if;
  return jsonb_build_object('schema_version','1.0.0','correlation_id',ctx->>'correlation_id','status','committed','data',jsonb_build_object('id',old.id,'occurrence_id',old.occurrence_id,'content_hash',old.content_hash));
 end if;
 select * into checkpoint_ from ecos.toast_checkpoint where domain=b.domain and execution_mode=b.execution_mode and restaurant_hash=site_ for update;
 if coalesce(checkpoint_.record_version,0)<>(args->>'expected_checkpoint_version')::bigint then raise exception 'stale_version' using errcode='40001'; end if;
 insert into ecos.toast_batch(occurrence_id,domain,execution_mode,restaurant_hash,business_date,observation,projection,observation_json,projection_json,source_hash,content_hash)
 values(occurrence_,b.domain,b.execution_mode,site_,day_,observation_,projection_,args->>'observation_json',args->>'projection_json',args->>'source_hash',content_) returning * into batch_;
 insert into ecos.toast_closed_date values(b.domain,b.execution_mode,site_,day_,observation_,batch_.id)
 on conflict(domain,execution_mode,restaurant_hash,business_date) do update set observation=excluded.observation,batch_id=excluded.batch_id;
 insert into ecos.toast_checkpoint values(b.domain,b.execution_mode,site_,day_,1,batch_.id)
 on conflict(domain,execution_mode,restaurant_hash) do update set coverage_through=greatest(ecos.toast_checkpoint.coverage_through,excluded.coverage_through),record_version=ecos.toast_checkpoint.record_version+1,batch_id=excluded.batch_id;
 return jsonb_build_object('schema_version','1.0.0','correlation_id',ctx->>'correlation_id','status','committed','data',jsonb_build_object('id',batch_.id,'occurrence_id',batch_.occurrence_id,'content_hash',batch_.content_hash));
end $$;
create function ecos.toast_readback(occurrence uuid) returns jsonb language plpgsql security definer set search_path=pg_catalog as $$
declare p ecos_meta.principal_binding;b ecos_meta.principal_domain;v ecos.toast_batch;
begin
 p:=ecos_meta.current_principal();perform ecos_meta.require_access(p.principal_id,'work_occurrence',occurrence);
 select * into b from ecos_meta.principal_domain where principal_id=p.principal_id;
 select * into v from ecos.toast_batch where occurrence_id=occurrence and domain=b.domain and execution_mode=b.execution_mode;
 return to_jsonb(v);
end $$;
create function ecos.toast_checkpoint_read(site text) returns jsonb language plpgsql security definer set search_path=pg_catalog as $$
declare p ecos_meta.principal_binding;b ecos_meta.principal_domain;v ecos.toast_checkpoint;
begin
 p:=ecos_meta.current_principal();select * into b from ecos_meta.principal_domain where principal_id=p.principal_id;
 if b.principal_id is null then raise exception 'forbidden' using errcode='42501';end if;
 select * into v from ecos.toast_checkpoint where domain=b.domain and execution_mode=b.execution_mode and restaurant_hash=site;
 return to_jsonb(v);
end $$;
alter table ecos.toast_batch enable row level security;
alter table ecos.toast_checkpoint enable row level security;
alter table ecos.toast_closed_date enable row level security;
revoke all on ecos.toast_batch,ecos.toast_checkpoint,ecos.toast_closed_date from public,executor,operations_api,provider_adapter;
revoke all on function ecos.toast_readback(uuid),ecos.toast_checkpoint_read(text) from public;
grant execute on function ecos.toast_readback(uuid),ecos.toast_checkpoint_read(text) to executor;
revoke all on all functions in schema ecos_meta from public;
insert into ecos_meta.contract_schema values('https://contracts.ecos.invalid/v1/toast.batch.commit-request.schema.json','{"$schema":"https://json-schema.org/draft/2020-12/schema","$id":"https://contracts.ecos.invalid/v1/toast.batch.commit-request.schema.json","title":"toast.batch.commit-request","type":"object","properties":{"schema_version":{"const":"1.0.0"},"context":{"$ref":"https://contracts.ecos.invalid/v1/request_context.schema.json"},"arguments":{"type":"object","properties":{"fence":{"$ref":"https://contracts.ecos.invalid/v1/fence.schema.json"},"restaurant_hash":{"type":"string","pattern":"^[a-f0-9]{64}$"},"business_date":{"type":"string","format":"date"},"observation_json":{"type":"string","minLength":2,"maxLength":700000},"projection_json":{"type":"string","minLength":2,"maxLength":39999},"source_hash":{"type":"string","pattern":"^[a-f0-9]{64}$"},"expected_checkpoint_version":{"type":"integer","minimum":0}},"required":["fence","restaurant_hash","business_date","observation_json","projection_json","source_hash","expected_checkpoint_version"],"additionalProperties":false}},"required":["schema_version","context","arguments"],"additionalProperties":false}'::jsonb);
insert into ecos_meta.operation_contract values('toast.batch.commit','{"name":"toast.batch.commit","request_schema":"https://contracts.ecos.invalid/v1/toast.batch.commit-request.schema.json","response_schema":"https://contracts.ecos.invalid/v1/phase2_result.schema.json","required_role":"executor","semantic_proposable":false,"idempotency_scope":"principal_id + operation + idempotency_key","atomicity":"single transaction"}'::jsonb);
reset role;
