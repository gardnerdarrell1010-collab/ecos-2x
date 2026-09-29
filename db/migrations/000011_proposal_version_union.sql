set local role ecos_owner;
create or replace function ecos_meta.commit_proposal(ctx jsonb,p jsonb) returns jsonb language plpgsql set search_path=pg_catalog as $$
declare stored jsonb; item jsonb; dep jsonb; exp jsonb; op jsonb; r jsonb; v jsonb; results jsonb:='[]'; done jsonb:='{}'; state_ text; reason text; events jsonb; progress boolean; principal uuid:=(ctx->>'principal_id')::uuid;
begin
 if ecos_meta.content_hash(p)<>p->>'content_hash' or p->>'correlation_id'<>ctx->>'correlation_id' then raise exception 'invalid_contract' using errcode='22023'; end if;
 if (select count(*)<>count(distinct value->>'item_id') from jsonb_array_elements(p->'items')) then raise exception 'invalid_contract' using errcode='22023'; end if;
 if exists(select 1 from jsonb_array_elements(p->'items') i cross join lateral jsonb_array_elements_text(i->'depends_on_item_ids') d where not exists(select 1 from jsonb_array_elements(p->'items') j where j->>'item_id'=d)) then raise exception 'invalid_contract' using errcode='22023'; end if;
 if (select coalesce(jsonb_agg(x order by x::text),'[]') from (select distinct e.value x from jsonb_array_elements(p->'items') i cross join lateral jsonb_array_elements(i->'expected_record_versions') e) u)<>(select coalesce(jsonb_agg(x order by x::text),'[]') from (select distinct value x from jsonb_array_elements(p->'expected_record_versions')) u) then raise exception 'invalid_contract' using errcode='22023'; end if;
 perform pg_advisory_xact_lock(hashtextextended(p->>'id',0));
 select to_jsonb(s) into stored from ecos.semantic_proposal s where id=(p->>'id')::uuid;
 if stored is not null and stored->>'content_hash'<>p->>'content_hash' then raise exception 'idempotency_conflict' using errcode='23505'; end if;
 if stored is null then perform ecos_meta.insert_wire('semantic_proposal',p); end if;
 while (select count(*) from jsonb_object_keys(done))<jsonb_array_length(p->'items') loop
  progress:=false;
  for item in select value from jsonb_array_elements(p->'items') loop
   if done ? (item->>'item_id') or exists(select 1 from jsonb_array_elements_text(item->'depends_on_item_ids') d where not done ? d) then continue; end if;
   progress:=true;
   select result into r from ecos_meta.proposal_item_result where proposal_id=(p->>'id')::uuid and item_id=(item->>'item_id')::uuid;
   if r is null then
    state_:='committed'; reason:='committed'; events:='[]';
    begin
     if exists(select 1 from jsonb_array_elements_text(item->'depends_on_item_ids') d where done->>d<>'committed') then state_:='blocked';
     elsif jsonb_array_length(item->'unresolved_ambiguity')>0 then state_:='ambiguous';
     elsif exists(select 1 from jsonb_array_elements(item->'evidence') e where e->>'verification'='conflicting') then state_:='conflicting';
     elsif exists(select 1 from jsonb_array_elements(item->'evidence') e where e->>'verification'<>'verified') then state_:='invalid'; end if;
     if state_='committed' then
      for exp in select value from jsonb_array_elements(item->'expected_record_versions') order by value->>'record_type',value->>'record_id' loop
       perform ecos_meta.require_access(principal,exp->>'record_type',(exp->>'record_id')::uuid);
       v:=ecos_meta.record_value(exp->>'record_type',(exp->>'record_id')::uuid,true);
       if coalesce((v->>'record_version')::bigint,1)<>(exp->>'record_version')::bigint then raise exception 'stale_version' using errcode='40001'; end if;
      end loop;
      perform ecos_meta.verify_sources(principal,item->'source_references'); perform ecos_meta.verify_evidence(principal,item->'evidence');
      for op in select value from jsonb_array_elements(item->'proposed_operations') loop
       if not exists(select 1 from ecos_meta.principal_operation where principal_id=principal and operation=op->>'operation') then raise exception 'forbidden' using errcode='42501'; end if;
       if op->>'operation' like 'task.%' and not exists(select 1 from jsonb_array_elements(item->'expected_record_versions') e where e->>'record_type'='task' and e->>'record_id'=op->'arguments'->>'task_id' and e->>'record_version'=op->'arguments'->>'expected_version') then raise exception 'invalid_contract' using errcode='22023'; end if;
       v:=ecos_meta.apply_operation(op->>'operation',ctx,op->'arguments'); events:=events||(v->'event_ids');
      end loop;
     end if;
    exception when serialization_failure then state_:='stale'; reason:='stale_version'; events:='[]';
      when insufficient_privilege then state_:='invalid'; reason:='forbidden'; events:='[]';
      when check_violation or invalid_parameter_value or foreign_key_violation then state_:='invalid'; reason:='invalid_contract'; events:='[]';
    end;
    r:=jsonb_build_object('item_id',item->'item_id','state',state_,'reason_code',case when state_='committed' then reason else state_ end,'committed_event_ids',events,'result_hash',case when state_='committed' then ecos_meta.content_hash(jsonb_build_object('events',events)) else null end);
    insert into ecos_meta.proposal_item_result values((p->>'id')::uuid,(item->>'item_id')::uuid,p->>'content_hash',r);
   end if;
   done:=done||jsonb_build_object(item->>'item_id',r->>'state'); results:=results||jsonb_build_array(r);
  end loop;
  if not progress then raise exception 'invalid_contract' using errcode='22023'; end if;
 end loop;
 return jsonb_build_object('proposal_id',p->'id','proposal_hash',p->'content_hash','schema_version','1.0.0','correlation_id',ctx->'correlation_id','items',results);
end $$;

reset role;
