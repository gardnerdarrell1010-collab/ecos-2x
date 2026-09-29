-- Governed database operations, retaining the Phase 0 operation names and wire schemas.
create function ecos_meta.selection(oid uuid,instance uuid,at_ timestamptz) returns jsonb language plpgsql stable set search_path=pg_catalog as $$
declare o ecos.work_occurrence; d ecos.work_definition; s ecos.work_stage_definition; p ecos.work_priority; e ecos.executor_instance; reasons jsonb:='[]'; sources jsonb; n bigint; imm boolean; pri bigint;
begin
 select * into o from ecos.work_occurrence where id=oid; select * into d from ecos.work_definition where id=o.work_definition_id;
 select * into s from ecos.work_stage_definition where id=o.stage_definition_id; select * into p from ecos.work_priority where occurrence_id=oid;
 select * into e from ecos.executor_instance where id=instance;
 imm:=o.ready_override_at is not null and o.ready_override_at<=at_;
 if not d.enabled then reasons:=reasons||'"disabled"'::jsonb; end if;
 if o.state not in ('pending','ready','retry_wait','claimed','running') then reasons:=reasons||'"terminal"'::jsonb; end if;
 if o.due_at>at_ and not imm then reasons:=reasons||'"not_due"'::jsonb; end if;
 if o.retry_at>at_ then reasons:=reasons||'"retry_backoff"'::jsonb; end if;
 if exists(select 1 from ecos.work_claim where occurrence_id=oid and state='active' and expires_at>at_) then reasons:=reasons||'"live_claim"'::jsonb; end if;
 if exists(select 1 from ecos_meta.control where maintenance) then reasons:=reasons||'"maintenance"'::jsonb; end if;
 if e.id is null or not exists(select 1 from ecos.executor where id=e.executor_id and enabled and surface=s.execution_surface)
 or not exists(select 1 from ecos.heartbeat where id=(select id from ecos.heartbeat where executor_instance_id=instance order by received_at desc,id desc limit 1) and valid_until>at_ and availability='available') then reasons:=reasons||'"availability"'::jsonb; end if;
 if exists(select 1 from ecos.stage_capability_requirement r where r.stage_definition_id=o.stage_definition_id and not exists(select 1 from ecos.executor_capability c where c.executor_instance_id=instance and c.capability_name=r.capability_name and c.capability_version>=r.minimum_version and c.expires_at>at_)) then reasons:=reasons||'"capability"'::jsonb; end if;
 if exists(select 1 from ecos.work_dependency w where w.occurrence_id=oid and not exists(select 1 from ecos.stage_result r where r.occurrence_id=w.prerequisite_occurrence_id and r.result_schema_id=w.required_result_schema_id and (w.required_result_hash is null or r.content_hash=w.required_result_hash)))
 or exists(select 1 from ecos.task_dependency td join ecos.task t on t.id=td.prerequisite_task_id where td.task_id=o.task_id and (t.lifecycle_state<>'completed' or (td.satisfaction_rule='approved_evidence' and not exists(select 1 from ecos.task_evidence te where te.task_id=t.id)))) then reasons:=reasons||'"dependency"'::jsonb; end if;
 if (s.requires_approval and not exists(select 1 from ecos.work_approval where occurrence_id=oid)) or exists(select 1 from ecos.work_approval w join ecos.approval_request a on a.id=w.approval_request_id where w.occurrence_id=oid and (a.state<>'approved' or a.expires_at<=at_ or a.subject_hash<>w.expected_subject_hash)) then reasons:=reasons||'"approval"'::jsonb; end if;
 if exists(select 1 from ecos.command_occurrence co join ecos.provider_command c on c.id=co.provider_command_id where co.occurrence_id=oid and c.outcome in ('accepted','unknown_outcome')) then reasons:=reasons||'"idempotency"'::jsonb; end if;
 if o.attempt_count>=(select max_attempts from ecos.retry_policy where id=d.retry_policy_id) then reasons:=reasons||'"attempt_limit"'::jsonb; end if;
 if o.task_id is not null and exists(select 1 from ecos.task where id=o.task_id and lifecycle_state in ('draft','completed','cancelled')) then reasons:=reasons||'"task_state"'::jsonb; end if;
 sources:=jsonb_build_array(jsonb_build_object('record_type','work_occurrence','record_id',o.id,'record_version',o.record_version),jsonb_build_object('record_type','work_definition','record_id',d.id,'record_version',d.record_version),jsonb_build_object('record_type','work_stage_definition','record_id',s.id,'record_version',s.record_version));
 pri:=case when (o.priority_override->>'expires_at')::timestamptz>at_ then (o.priority_override->>'value')::bigint else 0 end;
 return jsonb_build_object('policy_version','lexicographic-v1','evaluated_at',at_,'source_versions',sources,'eligible',jsonb_array_length(reasons)=0,'reason_codes',reasons,'priority_override',pri,'immediate_ready',imm,'sla_breach_seconds',greatest(0,trunc(extract(epoch from at_-p.sla_deadline)))::bigint,'deadline_pressure_seconds',case when p.deadline is null then 0 else greatest(0,86400-trunc(extract(epoch from p.deadline-at_)))::bigint end,'business_impact',coalesce(p.business_impact,0),'recurrence_relative_age_basis_points',floor(greatest(0,trunc(extract(epoch from at_-o.due_at)))*10000/coalesce(p.recurrence_period_seconds,86400))::bigint,'created_at',o.created_at,'occurrence_id',oid);
end $$;
create function ecos_meta.execution_event(run_id uuid,state_ text,reason text,hash_ text default null) returns uuid language plpgsql set search_path=pg_catalog as $$
declare r ecos.execution_run; event_id uuid:=gen_random_uuid();
begin select * into r from ecos.execution_run where id=run_id;
 insert into ecos.execution_event(id,event_type,schema_version,aggregate_type,aggregate_id,correlation_id,causation_id,created_at,payload) values(event_id,'execution.'||state_,'1.0.0','execution_run',r.id,r.correlation_id,null,clock_timestamp(),jsonb_build_object('execution_run_id',r.id,'occurrence_id',r.occurrence_id,'state',state_,'reason_code',reason,'fence',ecos_meta.fence(to_jsonb(r)),'evidence_hash',hash_)); return event_id;
end $$;
create function ecos_meta.recover_occurrence(oid uuid) returns void language plpgsql set search_path=pg_catalog as $$
declare c ecos.work_claim; r ecos.execution_run;
begin
 perform 1 from ecos.work_occurrence where id=oid for update;
 for c in select * from ecos.work_claim where occurrence_id=oid and state='active' and expires_at<=clock_timestamp() for update loop
  update ecos.work_claim set state='expired',record_version=record_version+1 where id=c.id;
  for r in select * from ecos.execution_run where claim_id=c.id and state='started' loop
   update ecos.execution_run set state='abandoned',ended_at=clock_timestamp(),record_version=record_version+1 where id=r.id;
   perform ecos_meta.execution_event(r.id,'abandoned','lease_expired');
  end loop;
  update ecos.work_occurrence set state='retry_wait',record_version=record_version+1 where id=oid and state in ('claimed','running');
 end loop;
end $$;
create function ecos_meta.claim_work(ctx jsonb,args jsonb) returns jsonb language plpgsql set search_path=pg_catalog as $$
declare o ecos.work_occurrence; c ecos.work_claim; r ecos.execution_run; sel jsonb; at_ timestamptz:=clock_timestamp(); instance uuid:=(args->>'executor_instance_id')::uuid; principal uuid:=(ctx->>'principal_id')::uuid;
begin
 if ctx->>'executor_instance_id' is distinct from args->>'executor_instance_id' then raise exception 'forbidden' using errcode='42501'; end if;
 for o in select w.* from ecos.work_occurrence w cross join lateral (select ecos_meta.selection(w.id,instance,at_) s) q
 where (q.s->>'eligible')::boolean and exists(select 1 from ecos_meta.object_grant g where g.principal_id=principal and g.record_type='work_occurrence' and g.record_id=w.id)
 order by (q.s->>'priority_override')::bigint desc,(q.s->>'immediate_ready')::boolean desc,(q.s->>'sla_breach_seconds')::bigint desc,(q.s->>'deadline_pressure_seconds')::bigint desc,(q.s->>'business_impact')::bigint desc,(q.s->>'recurrence_relative_age_basis_points')::bigint desc,w.created_at,w.id for update of w skip locked limit 1 loop
  perform ecos_meta.recover_occurrence(o.id);
  sel:=ecos_meta.selection(o.id,instance,clock_timestamp());
  if not (sel->>'eligible')::boolean then continue; end if;
  update ecos.work_occurrence set state='ready',record_version=record_version+1 where id=o.id and state in ('pending','retry_wait');
  update ecos.work_occurrence set state='claimed',claim_version=claim_version+1,attempt_count=attempt_count+1,record_version=record_version+1 where id=o.id returning * into o;
  insert into ecos.work_claim(occurrence_id,stage_definition_id,executor_instance_id,claim_version,fence_token,state,acquired_at,expires_at,renewed_at) values(o.id,o.stage_definition_id,instance,o.claim_version,gen_random_uuid(),'active',clock_timestamp(),clock_timestamp()+make_interval(secs=>(args->>'lease_seconds')::int),clock_timestamp()) returning * into c;
  insert into ecos.execution_run(claim_id,occurrence_id,stage_definition_id,claim_version,fence_token,executor_instance_id,state,selection_evidence,correlation_id,ended_at) values(c.id,c.occurrence_id,c.stage_definition_id,c.claim_version,c.fence_token,c.executor_instance_id,'started',sel,(ctx->>'correlation_id')::uuid,null) returning * into r;
  perform ecos_meta.execution_event(r.id,'started','selected');
  update ecos.work_occurrence set state='running',record_version=record_version+1 where id=o.id;
  return jsonb_build_object('schema_version','1.0.0','correlation_id',ctx->'correlation_id','claim',to_jsonb(c),'execution_run',ecos_meta.run_wire(to_jsonb(r)));
 end loop;
 return jsonb_build_object('schema_version','1.0.0','correlation_id',ctx->'correlation_id','claim',null,'execution_run',null);
end $$;
create function ecos_meta.check_fence(ctx jsonb,f jsonb) returns ecos.work_claim language plpgsql set search_path=pg_catalog as $$
declare c ecos.work_claim; sel jsonb;
begin
 perform ecos_meta.require_access((ctx->>'principal_id')::uuid,'work_occurrence',(f->>'occurrence_id')::uuid);
 perform 1 from ecos.work_occurrence where id=(f->>'occurrence_id')::uuid for update;
 select * into c from ecos.work_claim where id=(f->>'claim_id')::uuid for update;
 if c.id is null or ecos_meta.fence(to_jsonb(c))<>f or c.executor_instance_id::text is distinct from ctx->>'executor_instance_id' or c.state<>'active' or c.expires_at<=clock_timestamp() then raise exception 'expired_fence' using errcode='40001'; end if;
 sel:=ecos_meta.selection(c.occurrence_id,c.executor_instance_id,clock_timestamp());
 if (sel->'reason_codes'-'live_claim'-'attempt_limit')<>'[]'::jsonb then raise exception 'gate_blocked' using errcode='23514'; end if;
 return c;
end $$;
create function ecos_meta.domain_effect(op text,ctx jsonb,args jsonb,entity uuid,version_ bigint) returns uuid language plpgsql set search_path=pg_catalog as $$
declare eid uuid:=gen_random_uuid();
begin
 insert into ecos.domain_event(id,event_type,schema_version,aggregate_type,aggregate_id,correlation_id,causation_id,created_at,payload) values(eid,case op when 'task.transition' then 'task.transitioned' when 'task.evidence.attach' then 'task.evidence_attached' else 'fact.recorded' end,'1.0.0',case when op='fact.record' then 'fact' else 'task' end,entity,(ctx->>'correlation_id')::uuid,(ctx->>'causation_id')::uuid,clock_timestamp(),jsonb_build_object('operation',op,'arguments',args,'record_version',version_));
 insert into ecos.outbox_item(domain_event_id,provider_command_id,destination,state,idempotency_key,available_at,attempt_count,lease_expires_at,correlation_id) values(eid,null,'domain_events','pending',eid::text,clock_timestamp(),0,null,(ctx->>'correlation_id')::uuid);
 return eid;
end $$;
create function ecos_meta.notify_transition(task_id_ uuid,eid uuid,ctx jsonb) returns void language plpgsql set search_path=pg_catalog as $$
declare p ecos_meta.notification_policy; n uuid:=gen_random_uuid(); cmd uuid:=gen_random_uuid(); key_ text:=eid::text;
begin
 select * into p from ecos_meta.notification_policy where task_id=task_id_; if not found then return; end if;
 insert into ecos.notification(id,business_reason_code,subject_type,subject_id,content_artifact_uri,content_hash,policy_version) values(n,'synthetic_transition','task',task_id_,p.content_artifact_uri,p.content_hash,1);
 insert into ecos.provider_command(id,provider,account_scope,command_type,idempotency_key,request_schema_id,request_artifact_uri,request_hash,correlation_id,causation_id,outcome,reconciliation_strategy,approval_request_id) values(cmd,'synthetic','development','fixture_delivery',key_,'synthetic.delivery.v1',p.content_artifact_uri,p.content_hash,(ctx->>'correlation_id')::uuid,eid,'pending','native_idempotency',null);
 insert into ecos.delivery(notification_id,recipient_party_id,channel,destination_reference,policy_key,state,approval_request_id,provider_command_id) values(n,p.recipient_party_id,p.channel,p.destination_reference,p.policy_key,'ready',null,cmd);
 insert into ecos.outbox_item(domain_event_id,provider_command_id,destination,state,idempotency_key,available_at,attempt_count,lease_expires_at,correlation_id) values(eid,cmd,'synthetic_adapter','pending',key_,clock_timestamp(),0,null,(ctx->>'correlation_id')::uuid);
end $$;
create function ecos_meta.apply_operation(op text,ctx jsonb,args jsonb) returns jsonb language plpgsql set search_path=pg_catalog as $$
declare principal uuid:=(ctx->>'principal_id')::uuid; v jsonb; obj uuid; ver bigint; eid uuid; events jsonb:='[]'; versions jsonb:='[]'; res jsonb; c ecos.work_claim; r ecos.execution_run; t ecos.task; a ecos.approval_request; m ecos.memory_record; cmd ecos.provider_command; prior jsonb;
begin
 if op='work.claim' then return ecos_meta.claim_work(ctx,args);
 elsif op in ('work.renew','work.complete') then
  c:=ecos_meta.check_fence(ctx,args->'fence'); select * into r from ecos.execution_run where claim_id=c.id;
  if op='work.renew' then
   update ecos.work_claim set expires_at=clock_timestamp()+make_interval(secs=>(args->>'lease_seconds')::int),renewed_at=clock_timestamp(),record_version=record_version+1 where id=c.id returning * into c;
   return jsonb_build_object('schema_version','1.0.0','correlation_id',ctx->'correlation_id','claim',to_jsonb(c),'execution_run',ecos_meta.run_wire(to_jsonb(r)));
  end if;
  v:=args->'result';
  if v->>'occurrence_id'<>c.occurrence_id::text or v->>'stage_definition_id'<>c.stage_definition_id::text or v->>'execution_run_id'<>r.id::text or v->>'verified_by'<>principal::text or (v->>'verified_at')::timestamptz>clock_timestamp() or v->>'result_schema_id'<>(select result_schema_id from ecos.work_stage_definition where id=c.stage_definition_id) then raise exception 'invalid_contract' using errcode='22023'; end if;
  perform ecos_meta.verify_sources(principal,v->'source_references'); perform ecos_meta.insert_wire('stage_result',v);
  update ecos.work_occurrence set state='succeeded',record_version=record_version+1 where id=c.occurrence_id;
  update ecos.work_claim set state='released',record_version=record_version+1 where id=c.id;
  update ecos.execution_run set state='succeeded',ended_at=clock_timestamp(),record_version=record_version+1 where id=r.id;
  eid:=ecos_meta.execution_event(r.id,'succeeded','verified_result',v->>'content_hash'); events:=jsonb_build_array(eid);
  update ecos.work_occurrence w set ready_override_at=clock_timestamp(),record_version=w.record_version+1 where w.state in ('pending','ready','retry_wait') and exists(select 1 from ecos.work_dependency d where d.occurrence_id=w.id and d.prerequisite_occurrence_id=c.occurrence_id) and not exists(select 1 from ecos.work_dependency d where d.occurrence_id=w.id and not exists(select 1 from ecos.stage_result sr where sr.occurrence_id=d.prerequisite_occurrence_id and sr.result_schema_id=d.required_result_schema_id and (d.required_result_hash is null or sr.content_hash=d.required_result_hash)));
 elsif op in ('task.transition','task.evidence.attach') then
  obj:=(args->>'task_id')::uuid; perform ecos_meta.require_access(principal,'task',obj); select * into t from ecos.task where id=obj for update;
  if t.record_version is distinct from (args->>'expected_version')::bigint then raise exception 'stale_version' using errcode='40001'; end if;
  if op='task.transition' then
   perform ecos_meta.verify_evidence(principal,args->'evidence');
   if args->>'target_state' in ('open','completed') and (exists(select 1 from ecos.task_dependency d join ecos.task p on p.id=d.prerequisite_task_id where d.task_id=obj and p.lifecycle_state<>'completed') or exists(select 1 from ecos.approval_request where task_id=obj and (state<>'approved' or expires_at<=clock_timestamp()))) then raise exception 'gate_blocked' using errcode='23514'; end if;
   if args->>'target_state'='completed' and (jsonb_array_length(args->'evidence')=0 or exists(select 1 from ecos.work_occurrence where task_id=obj and state not in ('succeeded','cancelled'))) then raise exception 'gate_blocked' using errcode='23514'; end if;
   update ecos.task set lifecycle_state=args->>'target_state',wait_reason=args->>'wait_reason',record_version=record_version+1 where id=obj returning record_version into ver;
  else
   perform ecos_meta.verify_evidence(principal,jsonb_build_array(args->'evidence'));
   insert into ecos.task_evidence(task_id,evidence) values(obj,args->'evidence'); update ecos.task set record_version=record_version+1 where id=obj returning record_version into ver;
  end if;
  eid:=ecos_meta.domain_effect(op,ctx,args,obj,ver); events:=jsonb_build_array(eid); versions:=jsonb_build_array(jsonb_build_object('record_type','task','record_id',obj,'record_version',ver));
  if op='task.transition' then perform ecos_meta.notify_transition(obj,eid,ctx); end if;
 elsif op='fact.record' then
  obj:=(args->>'subject_id')::uuid;
  if not exists(select 1 from ecos_meta.object_grant where principal_id=principal and record_id=obj) then raise exception 'forbidden' using errcode='42501'; end if;
  perform ecos_meta.verify_sources(principal,args->'source_references');
  insert into ecos.fact(subject_id,statement,source_references,sensitivity) values(obj,args->>'statement',args->'source_references',args->>'sensitivity') returning id,record_version into obj,ver;
  insert into ecos_meta.object_grant values(principal,'fact',obj);
  eid:=ecos_meta.domain_effect(op,ctx,args,obj,ver); events:=jsonb_build_array(eid); versions:=jsonb_build_array(jsonb_build_object('record_type','fact','record_id',obj,'record_version',ver));
 elsif op='approval.decide' then
  obj:=(args->>'approval_request_id')::uuid; perform ecos_meta.require_access(principal,'approval_request',obj);
  select * into a from ecos.approval_request where id=obj for update;
  if a.record_version is distinct from (args->>'expected_version')::bigint then raise exception 'stale_version' using errcode='40001'; end if;
  if a.subject_hash<>args->>'subject_hash' or a.expires_at<=clock_timestamp() then raise exception 'gate_blocked' using errcode='23514'; end if;
  v:=ecos_meta.record_value(a.subject_type,a.subject_id,true);
  if ecos_meta.content_hash(v)<>a.subject_hash then raise exception 'stale_version' using errcode='40001'; end if;
  insert into ecos.approval_decision(approval_request_id,decision,actor_id,reason_code,evidence,supersedes_decision_id) values(obj,args->>'decision',principal,args->>'reason_code','[]',null);
  update ecos.approval_request set state=args->>'decision',record_version=record_version+1 where id=obj;
 elsif op='memory.activate' then
  obj:=(args->>'memory_record_id')::uuid; perform ecos_meta.require_access(principal,'memory_record',obj); select * into m from ecos.memory_record where id=obj for update;
  if m.record_version is distinct from (args->>'expected_version')::bigint then raise exception 'stale_version' using errcode='40001'; end if;
  perform ecos_meta.require_access(principal,'memory_scope',m.scope_id); v:=args->'new_version';
  if v->>'memory_record_id'<>obj::text or v->>'scope_id'<>m.scope_id::text or v->>'supersedes_version_id' is distinct from m.active_head_version_id::text or (v->>'version_number')::bigint<>coalesce((select version_number from ecos.memory_version where id=m.active_head_version_id),0)+1 or ecos_meta.content_hash(v)<>v->>'content_hash' then raise exception 'invalid_contract' using errcode='22023'; end if;
  perform ecos_meta.verify_sources(principal,v->'authoritative_references'); perform ecos_meta.verify_sources(principal,v->'provenance');
  perform ecos_meta.insert_wire('memory_version',v); update ecos.memory_record set active_head_version_id=(v->>'id')::uuid,record_version=record_version+1 where id=obj;
 elsif op='provider.result.record' then
  v:=args->'result'; obj:=(v->>'provider_command_id')::uuid; perform ecos_meta.require_access(principal,'provider_command',obj); select * into cmd from ecos.provider_command where id=obj for update;
  select to_jsonb(p) into prior from ecos.provider_result p where id=(v->>'id')::uuid or (provider_attempt_id=(v->>'provider_attempt_id')::uuid and evidence_hash=v->>'evidence_hash') limit 1;
  if prior is not null then if prior<>v then raise exception 'idempotency_conflict' using errcode='23505'; end if;
  else
   perform ecos_meta.insert_wire('provider_result',v);
   if cmd.outcome<>'succeeded' then
    if cmd.outcome='reconciled' then
     if exists(select 1 from ecos.provider_result where provider_command_id=obj and reconciled_outcome='succeeded') then null;
     else raise exception 'unknown_outcome' using errcode='23514'; end if;
    elsif cmd.outcome<>v->>'outcome' then update ecos.provider_command set outcome=v->>'outcome',record_version=record_version+1 where id=obj; end if;
   end if;
   if v->>'outcome'='succeeded' or v->>'reconciled_outcome'='succeeded' then
    update ecos.delivery set state='sending',record_version=record_version+1 where provider_command_id=obj and state='ready';
    update ecos.delivery set state='delivered',record_version=record_version+1 where provider_command_id=obj and state='sending';
    insert into ecos.delivery_attempt(delivery_id,provider_attempt_id,provider_message_id,evidence_hash,provider_status_at) select id,(v->>'provider_attempt_id')::uuid,v->>'provider_object_id',v->>'evidence_hash',(v->>'observed_at')::timestamptz from ecos.delivery where provider_command_id=obj on conflict(delivery_id,provider_attempt_id) do nothing;
   end if;
  end if;
 else raise exception 'invalid_contract' using errcode='22023'; end if;
 res:=jsonb_build_object('schema_version','1.0.0','operation_id',gen_random_uuid(),'correlation_id',ctx->'correlation_id','status','committed','event_ids',events,'record_versions',versions,'result_hash','');
 return res||jsonb_build_object('result_hash',ecos_meta.content_hash(res-'result_hash'));
end $$;

create function ecos_meta.commit_proposal(ctx jsonb,p jsonb) returns jsonb language plpgsql set search_path=pg_catalog as $$
declare stored jsonb; item jsonb; dep jsonb; exp jsonb; op jsonb; r jsonb; v jsonb; results jsonb:='[]'; done jsonb:='{}'; state_ text; reason text; events jsonb; progress boolean; principal uuid:=(ctx->>'principal_id')::uuid;
begin
 if ecos_meta.content_hash(p)<>p->>'content_hash' or p->>'correlation_id'<>ctx->>'correlation_id' then raise exception 'invalid_contract' using errcode='22023'; end if;
 if (select count(*)<>count(distinct value->>'item_id') from jsonb_array_elements(p->'items')) then raise exception 'invalid_contract' using errcode='22023'; end if;
 if exists(select 1 from jsonb_array_elements(p->'items') i cross join lateral jsonb_array_elements_text(i->'depends_on_item_ids') d where not exists(select 1 from jsonb_array_elements(p->'items') j where j->>'item_id'=d)) then raise exception 'invalid_contract' using errcode='22023'; end if;
 if (select coalesce(jsonb_agg(x order by x::text),'[]') from (select distinct value x from jsonb_array_elements(p->'items') i cross join lateral jsonb_array_elements(i->'expected_record_versions')) u)<>(select coalesce(jsonb_agg(x order by x::text),'[]') from (select distinct value x from jsonb_array_elements(p->'expected_record_versions')) u) then raise exception 'invalid_contract' using errcode='22023'; end if;
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
