-- Portable validators, private identities, immutable evidence and relational guards.
create function ecos_meta.canonical_json(v jsonb) returns text language plpgsql immutable set search_path=pg_catalog as $$
declare t text; r text;
begin
 t:=jsonb_typeof(v);
 if t='object' then select '{'||coalesce(string_agg(to_jsonb(key)::text||':'||ecos_meta.canonical_json(value),',' order by key collate "C"),'')||'}' into r from jsonb_each(v); return r;
 elsif t='array' then select '['||coalesce(string_agg(ecos_meta.canonical_json(value),',' order by ord),'')||']' into r from jsonb_array_elements(v) with ordinality a(value,ord); return r;
 elsif t='number' and v::text !~ '^-?[0-9]+$' then raise exception 'invalid_contract' using errcode='22023';
 else return v::text; end if;
end $$;
create function ecos_meta.content_hash(v jsonb) returns text language sql immutable set search_path=pg_catalog as $$ select encode(sha256(convert_to(ecos_meta.canonical_json(v-'content_hash'),'UTF8')),'hex') $$;

create function ecos_meta.valid_json(s jsonb,v jsonb,depth integer default 0) returns boolean language plpgsql stable set search_path=pg_catalog as $$
declare x jsonb; k text; p jsonb; n integer; ref text; doc jsonb; t text; st text;
begin
 if depth>64 or v is null then return false; end if;
 if s ? '$ref' then
  ref:=s->>'$ref'; select document into doc from ecos_meta.contract_schema where schema_id=split_part(ref,'#',1);
  if doc is null then return false; end if;
  if position('#' in ref)>0 then doc:=doc #> string_to_array(trim(leading '/' from split_part(ref,'#',2)),'/'); end if;
  return ecos_meta.valid_json(doc,v,depth+1);
 end if;
 if s ? 'const' and v<>s->'const' then return false; end if;
 if s ? 'enum' and not exists(select 1 from jsonb_array_elements(s->'enum') e where e=v) then return false; end if;
 if s ? 'not' and ecos_meta.valid_json(s->'not',v,depth+1) then return false; end if;
 if s ? 'allOf' then for x in select value from jsonb_array_elements(s->'allOf') loop if not ecos_meta.valid_json(x,v,depth+1) then return false; end if; end loop; end if;
 if s ? 'anyOf' then n:=0; for x in select value from jsonb_array_elements(s->'anyOf') loop if ecos_meta.valid_json(x,v,depth+1) then n:=n+1; end if; end loop; if n=0 then return false; end if; end if;
 if s ? 'oneOf' then n:=0; for x in select value from jsonb_array_elements(s->'oneOf') loop if ecos_meta.valid_json(x,v,depth+1) then n:=n+1; end if; end loop; if n<>1 then return false; end if; end if;
 if s ? 'if' then
  if ecos_meta.valid_json(s->'if',v,depth+1) then if s ? 'then' and not ecos_meta.valid_json(s->'then',v,depth+1) then return false; end if;
  else if s ? 'else' and not ecos_meta.valid_json(s->'else',v,depth+1) then return false; end if; end if;
 end if;
 t:=jsonb_typeof(v); st:=s->>'type';
 if st is not null and not(t=st or(st='integer' and t='number' and v::text ~ '^-?[0-9]+$')) then return false; end if;
 if t='object' then
  for k in select jsonb_array_elements_text(coalesce(s->'required','[]')) loop if not v ? k then return false; end if; end loop;
  for k,x in select key,value from jsonb_each(v) loop
   p:=s->'properties'->k;
   if p is null and s->'additionalProperties'='false'::jsonb then return false; end if;
   if p is not null and not ecos_meta.valid_json(p,x,depth+1) then return false; end if;
  end loop;
 elsif t='array' then
  n:=jsonb_array_length(v);
  if n<coalesce((s->>'minItems')::int,0) or n>coalesce((s->>'maxItems')::int,2147483647) then return false; end if;
  if s->>'uniqueItems'='true' and n<>(select count(distinct value) from jsonb_array_elements(v)) then return false; end if;
  if s ? 'items' then for x in select value from jsonb_array_elements(v) loop if not ecos_meta.valid_json(s->'items',x,depth+1) then return false; end if; end loop; end if;
 elsif t='string' then
  ref:=v#>>'{}'; n:=length(ref);
  if n<coalesce((s->>'minLength')::int,0) or n>coalesce((s->>'maxLength')::int,2147483647) then return false; end if;
  if s ? 'pattern' and ref !~ (s->>'pattern') then return false; end if;
  if s->>'format'='uuid' then if ref !~* '^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$' then return false; end if; perform ref::uuid; end if;
  if s->>'format'='date-time' then if ref !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}[Tt][0-9]{2}:[0-9]{2}:[0-9]{2}([.][0-9]+)?([Zz]|[+-][0-9]{2}:[0-9]{2})$' then return false; end if; perform ref::timestamptz; end if;
 elsif t='number' then
  if s ? 'minimum' and (v::text)::numeric<(s->>'minimum')::numeric then return false; end if;
  if s ? 'maximum' and (v::text)::numeric>(s->>'maximum')::numeric then return false; end if;
 end if;
 return true;
exception when others then return false;
end $$;
create function ecos_meta.assert_contract(name text,v jsonb) returns void language plpgsql stable set search_path=pg_catalog as $$
declare s jsonb;
begin select document into s from ecos_meta.contract_schema where schema_id='https://contracts.ecos.invalid/v1/'||name||'.schema.json';
 if s is null or not ecos_meta.valid_json(s,v) then raise exception 'invalid_contract' using errcode='22023'; end if;
end $$;
create function ecos_meta.fence(r jsonb) returns jsonb language sql immutable set search_path=pg_catalog as $$
 select jsonb_build_object('claim_id',coalesce(r->'claim_id',r->'id'),'occurrence_id',r->'occurrence_id','stage_definition_id',r->'stage_definition_id','claim_version',r->'claim_version','fence_token',r->'fence_token','executor_instance_id',r->'executor_instance_id') $$;
create function ecos_meta.run_wire(r jsonb) returns jsonb language sql immutable set search_path=pg_catalog as $$
 select (r-array['claim_id','occurrence_id','stage_definition_id','claim_version','fence_token','executor_instance_id'])||jsonb_build_object('fence',ecos_meta.fence(r)) $$;
create function ecos_meta.guard_entity() returns trigger language plpgsql set search_path=pg_catalog as $$
declare v jsonb; oldv jsonb; immutable_ boolean; policy text; field_ text; edges jsonb;
begin
 select immutable into immutable_ from ecos_meta.entity_contract where name=tg_table_name;
 if tg_op in ('UPDATE','DELETE') and immutable_ then raise exception 'immutable_evidence' using errcode='23514'; end if;
 if tg_op='DELETE' then return old; end if;
 v:=to_jsonb(new); if tg_table_name='execution_run' then v:=ecos_meta.run_wire(v); end if;
 perform ecos_meta.assert_contract(tg_table_name,v);
 if tg_op='UPDATE' then
  oldv:=to_jsonb(old);
  if v->'id'<>oldv->'id' or v->'created_at'<>oldv->'created_at' or v->'schema_version'<>oldv->'schema_version' then raise exception 'immutable_identity' using errcode='23514'; end if;
  if new.record_version<>old.record_version+1 then raise exception 'stale_version' using errcode='40001'; end if;
  policy:=case tg_table_name when 'task' then 'task_lifecycle' when 'work_occurrence' then 'work_occurrence' when 'work_claim' then 'claim' when 'approval_request' then 'approval' when 'provider_command' then 'provider_outcome' when 'delivery' then 'delivery' end;
  field_:=case tg_table_name when 'task' then 'lifecycle_state' when 'provider_command' then 'outcome' else 'state' end;
  if policy is not null and v->>field_<>oldv->>field_ then
   select tp.edges into edges from ecos_meta.transition_policy tp where name=policy;
   if not coalesce((edges->(oldv->>field_)) ? (v->>field_),false) then raise exception 'invalid_transition' using errcode='23514'; end if;
  end if;
  if tg_table_name='provider_command' and (v-array['outcome','record_version'])<>(oldv-array['outcome','record_version']) then raise exception 'immutable_command' using errcode='23514'; end if;
  if tg_table_name='execution_run' and (v->'selection_evidence'<>oldv->'selection_evidence') then raise exception 'immutable_selection' using errcode='23514'; end if;
 end if;
 return new;
end $$;
do $$ declare r record; begin for r in select name from ecos_meta.entity_contract loop
 execute format('create trigger guard_entity before insert or update or delete on %I.%I for each row execute function ecos_meta.guard_entity()',case when r.name in ('raw_migration_batch','quarantine_item','legacy_identity') then 'ecos_migration' else 'ecos' end,r.name);
end loop; end $$;
create function ecos_meta.forbid_evidence_change() returns trigger language plpgsql set search_path=pg_catalog as $$ begin raise exception 'immutable_evidence' using errcode='23514'; end $$;
do $$ declare n text; begin foreach n in array array['operation_receipt','operation_audit','proposal_item_result'] loop execute format('create trigger immutable before update or delete on ecos_meta.%I for each row execute function ecos_meta.forbid_evidence_change()',n); end loop; end $$;
create trigger immutable before update or delete on ecos.repair_action for each row execute function ecos_meta.forbid_evidence_change();
create trigger immutable before update or delete on ecos.integrity_finding for each row execute function ecos_meta.forbid_evidence_change();
create trigger immutable before update or delete on ecos_migration.raw_source_row for each row execute function ecos_meta.forbid_evidence_change();

create function ecos_meta.graph_guard() returns trigger language plpgsql set search_path=pg_catalog as $$
declare a uuid; b uuid; cycle_ boolean; from_ text; to_ text;
begin
 perform pg_advisory_xact_lock(684026,10);
 if tg_table_name='task_dependency' then from_:='task_id'; to_:='prerequisite_task_id'; else from_:='occurrence_id'; to_:='prerequisite_occurrence_id'; end if;
 a:=(to_jsonb(new)->>from_)::uuid; b:=(to_jsonb(new)->>to_)::uuid;
 execute format('with recursive path(id) as (select $1::uuid union select d.%I from ecos.%I d join path p on d.%I=p.id where d.id<>$3) select exists(select 1 from path where id=$2)',to_,tg_table_name,from_) into cycle_ using b,a,new.id;
 if cycle_ then raise exception 'dependency_cycle' using errcode='23514'; end if;
 return new;
end $$;
create trigger cycle_guard before insert or update on ecos.task_dependency for each row execute function ecos_meta.graph_guard();
create trigger cycle_guard before insert or update on ecos.work_dependency for each row execute function ecos_meta.graph_guard();
create function ecos_meta.assignment_guard() returns trigger language plpgsql set search_path=pg_catalog as $$
begin perform pg_advisory_xact_lock(684026,11);
 if exists(select 1 from ecos.task_assignment a where a.id<>new.id and a.task_id=new.task_id and a.role=new.role and tstzrange(a.effective_from,a.effective_to,'[)') && tstzrange(new.effective_from,new.effective_to,'[)')) then raise exception 'overlapping_assignment' using errcode='23514'; end if; return new; end $$;
create trigger assignment_guard before insert or update on ecos.task_assignment for each row execute function ecos_meta.assignment_guard();
create function ecos_meta.current_principal() returns ecos_meta.principal_binding language plpgsql stable set search_path=pg_catalog as $$
declare p ecos_meta.principal_binding; role_ name;
begin role_:=coalesce(nullif(current_setting('role',true),'none'),session_user);
 select * into p from ecos_meta.principal_binding where role_name=role_ and enabled;
 if not found then raise exception 'unauthenticated' using errcode='28000'; end if; return p; end $$;
create function ecos_meta.require_access(principal uuid,kind text,entity uuid) returns void language plpgsql stable set search_path=pg_catalog as $$
begin if not exists(select 1 from ecos_meta.object_grant where principal_id=principal and record_type=kind and record_id=entity) then raise exception 'forbidden' using errcode='42501'; end if; end $$;
create function ecos_meta.record_value(kind text,entity uuid,lock_ boolean default false) returns jsonb language plpgsql set search_path=pg_catalog as $$
declare v jsonb;
begin
 if kind not in ('task','project','party','artifact','fact','memory_record','memory_version','work_occurrence','provider_receipt','communication','approval_request') then raise exception 'invalid_contract' using errcode='22023'; end if;
 execute format('select to_jsonb(t) from ecos.%I t where id=$1%s',kind,case when lock_ then ' for update' else '' end) into v using entity;
 if v is null then raise exception 'missing_reference' using errcode='23503'; end if; return v;
end $$;
create function ecos_meta.verify_sources(principal uuid,refs jsonb) returns void language plpgsql set search_path=pg_catalog as $$
declare r jsonb; v jsonb;
begin for r in select value from jsonb_array_elements(refs) order by value->>'record_type',value->>'record_id' loop
 perform ecos_meta.require_access(principal,r->>'record_type',(r->>'record_id')::uuid);
 v:=ecos_meta.record_value(r->>'record_type',(r->>'record_id')::uuid,true);
 if coalesce((v->>'record_version')::bigint,1)<>(r->>'record_version')::bigint or ecos_meta.content_hash(v)<>r->>'content_hash' then raise exception 'stale_version' using errcode='40001'; end if;
 if r->>'authority'='conversation_evidence' then raise exception 'gate_blocked' using errcode='23514'; end if;
end loop; end $$;
create function ecos_meta.verify_evidence(principal uuid,ev jsonb) returns void language plpgsql set search_path=pg_catalog as $$
declare e jsonb;
begin for e in select value from jsonb_array_elements(ev) loop
 if e->>'verification'<>'verified' then raise exception 'gate_blocked' using errcode='23514'; end if;
 perform ecos_meta.verify_sources(principal,jsonb_build_array(e->'source'));
end loop; end $$;
create function ecos_meta.insert_wire(kind text,v jsonb) returns void language plpgsql set search_path=pg_catalog as $$
declare ns text;
begin
 if not exists(select 1 from ecos_meta.entity_contract where name=kind) then raise exception 'invalid_contract'; end if;
 ns:=case when kind in ('raw_migration_batch','quarantine_item','legacy_identity') then 'ecos_migration' else 'ecos' end;
 perform ecos_meta.assert_contract(kind,v);
 execute format('insert into %I.%I select * from jsonb_populate_record(null::%I.%I,$1)',ns,kind,ns,kind) using v;
end $$;
