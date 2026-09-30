-- Renewal retains the existing enrollment, capability rows and governed heartbeat.
set local role ecos_owner;
create table ecos_meta.capability_renewal_policy (
 capability_id uuid primary key references ecos.executor_capability(id),
 attested_by uuid not null,
 evidence_hash text not null check(evidence_hash ~ '^[a-f0-9]{64}$'),
 lease_seconds integer not null check(lease_seconds between 60 and 86400),
 renew_before_seconds integer not null check(renew_before_seconds >= 10 and renew_before_seconds < lease_seconds),
 enabled boolean not null default false,
 authorization_reference text not null check(length(authorization_reference)>0),
 created_at timestamptz not null default clock_timestamp()
);
create table ecos_meta.capability_renewal_receipt (
 capability_id uuid primary key references ecos.executor_capability(id),
 renewed_at timestamptz not null,
 previous_expiry timestamptz not null,
 expires_at timestamptz not null,
 renewal_count bigint not null check(renewal_count>0),
 evidence_hash text not null
);
revoke all on ecos_meta.capability_renewal_policy,ecos_meta.capability_renewal_receipt from public,executor,operations_api,provider_adapter;
alter function ecos_meta.presence_heartbeat(jsonb,jsonb) rename to presence_heartbeat_without_renewal;
create function ecos_meta.presence_heartbeat(ctx jsonb,args jsonb) returns jsonb
language plpgsql set search_path=pg_catalog set timezone='UTC' as $$
declare result_ jsonb; cap_ record; next_ timestamptz; renewed_ integer:=0;
begin
 -- Existing presence/identity/time gates run before any renewal.
 result_:=ecos_meta.presence_heartbeat_without_renewal(ctx,args);
 for cap_ in
  select c.id,c.expires_at,p.lease_seconds,p.evidence_hash
  from ecos.executor_capability c
  join ecos_meta.capability_renewal_policy p on p.capability_id=c.id and p.attested_by=c.attested_by
  join ecos.executor_instance i on i.id=c.executor_instance_id
  join ecos.executor e on e.id=i.executor_id and e.enabled
  where i.id=(ctx->>'executor_instance_id')::uuid
    and i.principal_id=(ctx->>'principal_id')::uuid
    and p.enabled and p.evidence_hash=args->>'evidence_hash'
    and (c.expires_at<=clock_timestamp()+make_interval(secs=>p.renew_before_seconds)
         or not exists(select 1 from ecos_meta.capability_renewal_receipt r where r.capability_id=c.id))
  for update of c,p
 loop
  next_:=clock_timestamp()+make_interval(secs=>cap_.lease_seconds);
  update ecos.executor_capability set expires_at=next_,record_version=record_version+1 where id=cap_.id;
  insert into ecos_meta.capability_renewal_receipt values(cap_.id,clock_timestamp(),cap_.expires_at,next_,1,cap_.evidence_hash)
  on conflict(capability_id) do update set renewed_at=excluded.renewed_at,
   previous_expiry=excluded.previous_expiry,expires_at=excluded.expires_at,
   renewal_count=ecos_meta.capability_renewal_receipt.renewal_count+1,evidence_hash=excluded.evidence_hash;
  renewed_:=renewed_+1;
 end loop;
 return result_||jsonb_build_object('capabilities_renewed',renewed_,
  'capability_expiry',(select min(expires_at) from ecos.executor_capability where executor_instance_id=(ctx->>'executor_instance_id')::uuid));
end $$;
revoke all on function ecos_meta.presence_heartbeat(jsonb,jsonb),ecos_meta.presence_heartbeat_without_renewal(jsonb,jsonb) from public,executor,operations_api,provider_adapter;
reset role;
