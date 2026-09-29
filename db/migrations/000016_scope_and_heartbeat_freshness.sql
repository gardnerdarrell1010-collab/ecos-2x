set local role ecos_owner;
-- A delayed heartbeat cannot make a dead executor appear fresh.
create or replace function ecos.record_heartbeat(observed timestamptz,evidence_hash text) returns uuid language plpgsql security definer set search_path=pg_catalog as $$
declare p ecos_meta.principal_binding; id_ uuid;
begin p:=ecos_meta.current_principal(); if p.executor_instance_id is null or observed>clock_timestamp()+interval '5 seconds' then raise exception 'forbidden' using errcode='42501'; end if;
 insert into ecos.heartbeat(executor_instance_id,observed_at,received_at,valid_until,availability,evidence_hash) values(p.executor_instance_id,observed,clock_timestamp(),least(observed,clock_timestamp())+interval '60 seconds','available',evidence_hash) returning id into id_; return id_; end $$;
create or replace function ecos_meta.require_access(principal uuid,kind text,entity uuid) returns void language plpgsql stable set search_path=pg_catalog as $$
declare sensitivity_ text:='internal'; ceiling_ text; scope_ uuid; roles_ jsonb; p ecos_meta.principal_binding;
begin
 if not exists(select 1 from ecos_meta.object_grant where principal_id=principal and record_type=kind and record_id=entity) then raise exception 'forbidden' using errcode='42501'; end if;
 select ceiling into ceiling_ from ecos_meta.principal_clearance where principal_id=principal; ceiling_:=coalesce(ceiling_,'internal');
 if kind='fact' then select sensitivity into sensitivity_ from ecos.fact where id=entity;
 elsif kind='memory_scope' then scope_:=entity;
 elsif kind='memory_record' then select scope_id into scope_ from ecos.memory_record where id=entity;
 elsif kind='memory_version' then select scope_id into scope_ from ecos.memory_version where id=entity; end if;
 if scope_ is not null then
  select sensitivity,authorized_role_names into sensitivity_,roles_ from ecos.memory_scope where id=scope_;
  p:=ecos_meta.current_principal(); if not roles_ ? p.role_name::text then raise exception 'forbidden' using errcode='42501'; end if;
 end if;
 if array_position(array['public','internal','confidential','restricted'],coalesce(sensitivity_,'internal'))>array_position(array['public','internal','confidential','restricted'],ceiling_) then raise exception 'forbidden' using errcode='42501'; end if;
end $$;
reset role;
