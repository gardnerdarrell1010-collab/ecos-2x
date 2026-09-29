-- Append-only correction for migration 20 SQLSTATE 42725; preserve all other behavior.
set local role ecos_owner;
create or replace function ecos_meta.reserve_resources() returns trigger language plpgsql set search_path=pg_catalog as $$
declare r record; s jsonb;
begin
 for r in select * from ecos.stage_resource_requirement where stage_definition_id=new.stage_definition_id order by provider,metric loop
  perform 1 from ecos.resource_budget where provider=r.provider and metric=r.metric for update;
 end loop;
 s:=ecos_meta.selection(new.occurrence_id,new.executor_instance_id,clock_timestamp());
 if ((s->'reason_codes')-'attempt_limit')<>'[]'::jsonb then raise exception 'gate_blocked' using errcode='23514'; end if;
 return new;
end $$;
reset role;
