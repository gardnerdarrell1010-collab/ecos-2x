-- Immutable producer output on the existing fenced occurrence model.
-- Internal SQL component; no executor grant, dispatch, provider effect or new queue.
set local role ecos_owner;
create table ecos.producer_snapshot (
 id uuid primary key default gen_random_uuid(),
 staging_id text not null unique default ('STG-'||gen_random_uuid()::text),
 occurrence_id uuid not null unique references ecos.work_occurrence,
 execution_run_id uuid not null references ecos.execution_run,
 stage_definition_id uuid not null references ecos.work_stage_definition,
 producer_id text not null,
 generated_at timestamptz not null,
 source_timestamp timestamptz,
 payload jsonb not null check(jsonb_typeof(payload)='object' and length(payload::text)<40000),
 payload_sha256 text not null check(payload_sha256=encode(sha256(convert_to(payload::text,'UTF8')),'hex')),
 source_references jsonb not null check(jsonb_typeof(source_references)='array'),
 created_at timestamptz not null default clock_timestamp()
);
create trigger immutable before update or delete on ecos.producer_snapshot
 for each row execute function ecos_meta.forbid_evidence_change();
alter table ecos.producer_snapshot enable row level security;
revoke all on ecos.producer_snapshot from public,anon,authenticated,service_role,executor,operations_api;

create function ecos_meta.persist_producer_snapshot(ctx jsonb,fence_ jsonb,payload_ jsonb)
returns jsonb language plpgsql set search_path=pg_catalog as $$
declare claim_ ecos.work_claim; context_ ecos.work_context; run_ ecos.execution_run;
 stored_ ecos.producer_snapshot; producer_ text; hash_ text;
begin
 claim_:=ecos_meta.check_fence(ctx,fence_);
 select * into strict context_ from ecos.work_context where occurrence_id=claim_.occurrence_id;
 producer_:=context_.input->>'source_worker_id';
 if producer_ is null or producer_ !~ '^TASK-AUTO-[0-9]{6}(-B)?$'
  or jsonb_typeof(payload_) is distinct from 'object'
  or payload_->>'producer_id' is distinct from producer_
  or payload_->>'occurrence_id' is distinct from claim_.occurrence_id::text
  or not (payload_ ?& array['run_id','generated_at','source_timestamp','freshness','availability','html_fragment','content_sha256'])
  or jsonb_typeof(payload_->'html_fragment') is distinct from 'string'
  or jsonb_typeof(payload_->'generated_at') is distinct from 'string'
  or length(payload_::text)>=40000 then raise exception 'invalid_contract' using errcode='22023'; end if;
 select * into strict run_ from ecos.execution_run where claim_id=claim_.id and state='started';
 if payload_->>'run_id' is distinct from run_.id::text
  or payload_->>'content_sha256' is distinct from encode(sha256(convert_to(payload_->>'html_fragment','UTF8')),'hex')
  or (payload_->>'generated_at')::timestamptz>clock_timestamp()
  or (payload_->>'source_timestamp')::timestamptz>(payload_->>'generated_at')::timestamptz
 then raise exception 'invalid_evidence' using errcode='22023'; end if;
 hash_:=encode(sha256(convert_to(payload_::text,'UTF8')),'hex');
 -- Lock the existing occurrence via check_fence: one immutable snapshot per occurrence.
 select * into stored_ from ecos.producer_snapshot where occurrence_id=claim_.occurrence_id;
 if found then
  if stored_.payload is distinct from payload_ or stored_.source_references is distinct from context_.source_references
   then raise exception 'snapshot_replay_conflict' using errcode='23505'; end if;
  return to_jsonb(stored_);
 end if;
 insert into ecos.producer_snapshot(occurrence_id,execution_run_id,stage_definition_id,producer_id,
  generated_at,source_timestamp,payload,payload_sha256,source_references)
 values(claim_.occurrence_id,run_.id,claim_.stage_definition_id,producer_,
  (payload_->>'generated_at')::timestamptz,(payload_->>'source_timestamp')::timestamptz,
  payload_,hash_,context_.source_references) returning * into stored_;
 return to_jsonb(stored_);
end $$;
revoke all on function ecos_meta.persist_producer_snapshot(jsonb,jsonb,jsonb) from public;
reset role;
