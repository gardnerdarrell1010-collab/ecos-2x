set local role ecos_owner;
create or replace function ecos_meta.check_fence(ctx jsonb,f jsonb) returns ecos.work_claim language plpgsql set search_path=pg_catalog as $$
declare c ecos.work_claim; sel jsonb;
begin
 perform ecos_meta.require_access((ctx->>'principal_id')::uuid,'work_occurrence',(f->>'occurrence_id')::uuid);
 perform 1 from ecos.work_occurrence where id=(f->>'occurrence_id')::uuid for update;
 select * into c from ecos.work_claim where id=(f->>'claim_id')::uuid for update;
 if c.id is null or ecos_meta.fence(to_jsonb(c))<>f or c.executor_instance_id::text is distinct from ctx->>'executor_instance_id' or c.state<>'active' or c.expires_at<=clock_timestamp() then raise exception 'expired_fence' using errcode='40001'; end if;
 sel:=ecos_meta.selection(c.occurrence_id,c.executor_instance_id,clock_timestamp());
 if ((sel->'reason_codes')-'live_claim'-'attempt_limit')<>'[]'::jsonb then raise exception 'gate_blocked' using errcode='23514'; end if;
 return c;
end $$;

reset role;
