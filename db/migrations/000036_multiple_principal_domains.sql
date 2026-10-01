-- Existing principals may hold multiple explicit functional-domain bindings.
-- Object grants, operation grants, capabilities, epochs and provider scopes remain separate.
set local role ecos_owner;
alter table ecos_meta.principal_domain drop constraint principal_domain_pkey;
alter table ecos_meta.principal_domain add primary key(principal_id,domain);

CREATE OR REPLACE FUNCTION ecos_meta.apply_operation(op text, ctx jsonb, args jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO 'pg_catalog'
AS $function$
declare principal uuid:=(ctx->>'principal_id')::uuid; id_ uuid:=(args->>'id')::uuid; v jsonb; prior jsonb; ver bigint; kind_ text;
 c ecos.communication; p ecos.communication_processing; claim_ ecos.work_claim; stage_ ecos.work_stage_definition;
 domain_ text; occurrence_ uuid; processing_ uuid; refs jsonb; proposal_ jsonb; committed_ jsonb;
begin
 if op not in ('party.put','relationship.put','artifact.register','approval.request','sms.continuation.enqueue','sms.continuation.complete') then return ecos_meta.apply_operation_before_structural(op,ctx,args); end if;
 if args ? 'provenance' then perform ecos_meta.verify_sources(principal,args->'provenance'); end if;
 if op='party.put' then
  select to_jsonb(t) into prior from ecos.party t where id=id_ for update;
  if coalesce((prior->>'record_version')::bigint,0)<>(args->>'expected_version')::bigint then raise exception 'stale_version' using errcode='40001'; end if;
  if prior is null then insert into ecos.party(id,business_id,name,party_kind) values(id_,args->>'business_id',args->>'name',args->>'party_kind');
  else
   if prior->>'business_id'<>args->>'business_id' or (prior->>'party_kind' is not null and prior->>'party_kind'<>args->>'party_kind') then raise exception 'invalid_contract'; end if;
   update ecos.party set name=args->>'name',party_kind=args->>'party_kind',record_version=record_version+1 where id=id_;
  end if;
  v:=ecos_meta.record_value('party',id_);
 elsif op='relationship.put' then
  perform ecos_meta.record_value(args->>'source_type',(args->>'source_id')::uuid,true);
  perform ecos_meta.record_value(args->>'target_type',(args->>'target_id')::uuid,true);
  select to_jsonb(t) into prior from ecos.relationship t where id=id_ for update;
  if coalesce((prior->>'record_version')::bigint,0)<>(args->>'expected_version')::bigint then raise exception 'stale_version' using errcode='40001'; end if;
  if prior is null then
   insert into ecos.relationship(id,source_system,source_relationship_id,source_type,source_id,target_type,target_id,relationship_type,status,effective_from,effective_to,provenance)
   values(id_,args->>'source_system',args->>'source_relationship_id',args->>'source_type',(args->>'source_id')::uuid,args->>'target_type',(args->>'target_id')::uuid,args->>'relationship_type',args->>'status',(args->>'effective_from')::timestamptz,(args->>'effective_to')::timestamptz,args->'provenance');
  else
   if (prior-array['record_version','status','effective_from','effective_to','provenance'])<>(args-array['expected_version','status','effective_from','effective_to','provenance']) then raise exception 'invalid_contract'; end if;
   update ecos.relationship set status=args->>'status',effective_from=(args->>'effective_from')::timestamptz,effective_to=(args->>'effective_to')::timestamptz,provenance=args->'provenance',record_version=record_version+1 where id=id_;
  end if;
  v:=ecos_meta.record_value('relationship',id_);
 elsif op='artifact.register' then
  insert into ecos.artifact(id,business_id,provider,provider_object_id,uri,content_hash,attachment_id) values(id_,args->>'business_id',args->>'provider',args->>'provider_object_id',args->>'uri',args->>'content_hash',args->>'attachment_id');
  v:=ecos_meta.record_value('artifact',id_);
 elsif op='approval.request' then
  v:=ecos_meta.record_value(args->>'subject_type',(args->>'subject_id')::uuid,true);
  if ecos_meta.content_hash(v)<>args->>'subject_hash' then raise exception 'stale_version' using errcode='40001'; end if;
  insert into ecos.approval_request(id,task_id,subject_type,subject_id,subject_hash,state,expires_at,expiration_mode) values(id_,null,args->>'subject_type',(args->>'subject_id')::uuid,args->>'subject_hash','pending',(args->>'expires_at')::timestamptz,args->>'expiration_mode');
  v:=ecos_meta.record_value('approval_request',id_);
 elsif op='sms.continuation.enqueue' then
  select * into c from ecos.communication where id=(args->>'communication_id')::uuid for update;
  if c.id is null or c.record_version<>(args->>'source_version')::bigint or c.channel<>'sms' or not exists(select 1 from ecos.provider_receipt where id=c.receipt_id and provider='twilio') then raise exception 'gate_blocked'; end if;
  if exists(select 1 from ecos.communication_processing where communication_id=c.id and source_version=c.record_version) then raise exception 'idempotency_conflict' using errcode='23505'; end if;
  select * into stage_ from ecos.work_stage_definition where stage_key='sms_continuation' and work_definition_id in(select id from ecos.work_definition where name='sms_continuation' and definition_version=1);
  if stage_.id is null then raise exception 'gate_blocked'; end if;
  select domain into domain_ from ecos_meta.object_domain where record_type='communication' and record_id=c.id;
  domain_:=coalesce(domain_,'synthetic.acceptance');
  if not exists(select 1 from ecos_meta.principal_domain where principal_id=principal and domain=domain_) then raise exception 'forbidden' using errcode='42501'; end if;
  occurrence_:=gen_random_uuid(); processing_:=gen_random_uuid();
  insert into ecos.work_occurrence(id,work_definition_id,stage_definition_id,fulfillment_id,task_id,state,occurrence_key,due_at) values(occurrence_,stage_.work_definition_id,stage_.id,gen_random_uuid(),(args->>'task_id')::uuid,'ready','sms:'||c.id::text||':'||c.record_version::text,clock_timestamp());
  insert into ecos.communication_processing(id,communication_id,source_version,state,occurrence_id) values(processing_,c.id,c.record_version,'ready',occurrence_);
  insert into ecos_meta.object_domain values('work_occurrence',occurrence_,domain_),('communication_processing',processing_,domain_);
  insert into ecos_meta.object_grant values(principal,'work_occurrence',occurrence_),(principal,'communication_processing',processing_);
  refs:=jsonb_build_array(jsonb_build_object('record_type','communication','record_id',c.id,'record_version',c.record_version,'content_hash',ecos_meta.content_hash(to_jsonb(c)),'authority','structured_ecos'));
  insert into ecos.work_context(occurrence_id,operation,source_references,input) values(occurrence_,'sms.continuation.complete',refs,jsonb_build_object('processing_id',processing_,'communication_id',c.id));
  v:=jsonb_build_object('processing_id',processing_,'occurrence_id',occurrence_);
 elsif op='sms.continuation.complete' then
  claim_:=ecos_meta.check_fence(ctx,args->'fence');
  if not exists(select 1 from ecos.work_stage_definition where id=claim_.stage_definition_id and stage_key='sms_continuation' and execution_surface='ONLINE_SEMANTIC') then raise exception 'forbidden' using errcode='42501'; end if;
  select * into p from ecos.communication_processing where occurrence_id=claim_.occurrence_id for update;
  perform ecos_meta.require_access(principal,'communication',p.communication_id);
  if p.id is null or p.state<>'ready' then raise exception 'gate_blocked'; end if;
  select proposal into proposal_ from ecos.proposal_submission where proposal_id=(args->>'proposal_id')::uuid and occurrence_id=claim_.occurrence_id and principal_id=principal;
  if proposal_ is null then raise exception 'gate_blocked'; end if;
  perform ecos_meta.verify_sources(principal,(select source_references from ecos.work_context where occurrence_id=claim_.occurrence_id));
  if not exists(select 1 from jsonb_array_elements(proposal_->'source_references') ref where ref->>'record_type'='communication' and ref->>'record_id'=p.communication_id::text and (ref->>'record_version')::bigint=p.source_version) then raise exception 'invalid_contract'; end if;
  committed_:=ecos_meta.commit_proposal(ctx,proposal_);
  if exists(select 1 from jsonb_array_elements(committed_->'items') i where i->>'state'<>'committed') then raise exception 'gate_blocked'; end if;
  update ecos.communication_processing set state='running',proposal_id=(args->>'proposal_id')::uuid,record_version=record_version+1 where id=p.id;
  update ecos.communication_processing set state='succeeded',record_version=record_version+1 where id=p.id;
  v:=ecos_meta.record_value('communication_processing',p.id);
 end if;
 return jsonb_build_object('schema_version','1.0.0','correlation_id',ctx->'correlation_id','status','committed','data',v);
end $function$;

CREATE OR REPLACE FUNCTION ecos_meta.selection(occurrence uuid, instance uuid, at_ timestamp with time zone)
 RETURNS jsonb
 LANGUAGE plpgsql
 STABLE
 SET search_path TO 'pg_catalog'
AS $function$
declare result_ jsonb; b ecos_meta.principal_domain; a ecos_meta.domain_authority; d text;
begin
 result_:=ecos_meta.selection_phase2(occurrence,instance,at_);
 select domain into d from ecos_meta.object_domain where record_type='work_occurrence' and record_id=occurrence;
 select pd.* into b from ecos_meta.principal_domain pd join ecos.executor_instance i on i.principal_id=pd.principal_id where i.id=instance and pd.domain=coalesce(d,'synthetic.acceptance');
 select * into a from ecos_meta.domain_authority where domain=b.domain;
 if b.principal_id is null or (d is not null and d<>b.domain) or (b.execution_mode<>'synthetic' and d is null)
 or (b.execution_mode='production' and (a.owner<>'2X' or a.epoch<>b.authority_epoch)) then
 result_:=jsonb_set(jsonb_set(result_,'{eligible}','false'),'{reason_codes}',(result_->'reason_codes')||'"domain_authority"'::jsonb);
 end if;
 return result_;
end $function$;

CREATE OR REPLACE FUNCTION ecos_meta.apply_operation_before_gmail(op text, ctx jsonb, args jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO 'pg_catalog'
AS $function$
declare b ecos_meta.principal_domain; old ecos.toast_batch; checkpoint_ ecos.toast_checkpoint; batch_ ecos.toast_batch;
 content_ text; occurrence_ uuid:=(args->'fence'->>'occurrence_id')::uuid; day_ date; site_ text; observation_ jsonb; projection_ jsonb;
begin
 if op<>'toast.batch.commit' then return ecos_meta.apply_operation_domain(op,ctx,args); end if;
 perform ecos_meta.check_fence(ctx,args->'fence');
 select * into b from ecos_meta.principal_domain where principal_id=(ctx->>'principal_id')::uuid and domain=coalesce((select domain from ecos_meta.object_domain where record_type='work_occurrence' and record_id=occurrence_),'synthetic.acceptance');
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
end $function$;

CREATE OR REPLACE FUNCTION ecos_meta.require_domain_epoch23(principal uuid, operation text)
 RETURNS void
 LANGUAGE plpgsql
 SET search_path TO 'pg_catalog'
AS $function$
declare b ecos_meta.principal_domain; a ecos_meta.domain_authority;
begin
 if not exists(select 1 from ecos_meta.principal_domain where principal_id=principal) then raise exception 'forbidden' using errcode='42501'; end if;
 for b in select * from ecos_meta.principal_domain where principal_id=principal order by domain loop
 -- Hold ownership stable for the complete SQL transaction, including replay.
 select * into a from ecos_meta.domain_authority where domain=b.domain for share;
 if b.execution_mode='production' and (a.owner<>'2X' or b.authority_epoch<>a.epoch) then raise exception 'gate_blocked' using errcode='23514'; end if;
 if b.execution_mode='shadow' and operation not in
  ('executor.register','executor.heartbeat','executor.stop','work.next','work.claim','work.package','work.renew','work.complete','work.fail','work.defer','work.release','recovery.sweep','toast.batch.commit')
 then raise exception 'forbidden' using errcode='42501'; end if;
 end loop;
end $function$;

CREATE OR REPLACE FUNCTION ecos_meta.effect_authority(principal uuid, target_ text, epoch_ bigint)
 RETURNS ecos_meta.principal_domain
 LANGUAGE plpgsql
 SET search_path TO 'pg_catalog'
AS $function$
declare b ecos_meta.principal_domain; a ecos_meta.domain_authority;
begin
 select pd.* into b from ecos_meta.principal_domain pd join ecos_meta.domain_effect_target t on t.domain=pd.domain where pd.principal_id=principal and t.target=target_;
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
end $function$;

CREATE OR REPLACE FUNCTION ecos_meta.require_operation_scope_before_gmail(op text, args jsonb, principal uuid)
 RETURNS void
 LANGUAGE plpgsql
 STABLE
 SET search_path TO 'pg_catalog'
AS $function$
declare occurrence_ uuid; task_ uuid; b ecos_meta.principal_domain; prior ecos.toast_batch;
begin
 perform ecos_meta.require_operation_scope_domain(op,args,principal);
 if op='toast.batch.commit' then
  occurrence_:=(args->'fence'->>'occurrence_id')::uuid;
  perform ecos_meta.require_access(principal,'work_occurrence',occurrence_);
  select task_id into task_ from ecos.work_occurrence where id=occurrence_;
  perform ecos_meta.require_access(principal,'task',task_);
  select * into b from ecos_meta.principal_domain where principal_id=principal and domain=coalesce((select domain from ecos_meta.object_domain where record_type='work_occurrence' and record_id=occurrence_),'synthetic.acceptance');
  select * into prior from ecos.toast_batch where occurrence_id=occurrence_;
  if prior.id is not null and (prior.domain<>b.domain or prior.execution_mode<>b.execution_mode) then
   raise exception 'forbidden' using errcode='42501';
  end if;
 end if;
end $function$;

CREATE OR REPLACE FUNCTION ecos.toast_readback(occurrence uuid)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog'
AS $function$
declare p ecos_meta.principal_binding;b ecos_meta.principal_domain;v ecos.toast_batch;
begin
 p:=ecos_meta.current_principal();perform ecos_meta.require_access(p.principal_id,'work_occurrence',occurrence);
 select * into b from ecos_meta.principal_domain where principal_id=p.principal_id and domain=coalesce((select domain from ecos_meta.object_domain where record_type='work_occurrence' and record_id=occurrence),'synthetic.acceptance');
 select * into v from ecos.toast_batch where occurrence_id=occurrence and domain=b.domain and execution_mode=b.execution_mode;
 return to_jsonb(v);
end $function$;

CREATE OR REPLACE FUNCTION ecos.toast_checkpoint_read(site text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog'
AS $function$
declare p ecos_meta.principal_binding;b ecos_meta.principal_domain;v ecos.toast_checkpoint;
begin
 p:=ecos_meta.current_principal();select * into b from ecos_meta.principal_domain where principal_id=p.principal_id and domain in ('toast.acquisition','synthetic.acceptance') order by (domain='toast.acquisition') desc limit 1;
 if b.principal_id is null then raise exception 'forbidden' using errcode='42501';end if;
 select * into v from ecos.toast_checkpoint where domain=b.domain and execution_mode=b.execution_mode and restaurant_hash=site;
 return to_jsonb(v);
end $function$;

CREATE OR REPLACE FUNCTION ecos.domain_effect_grant(target_ text)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'pg_catalog'
AS $function$
declare p ecos_meta.principal_binding; b ecos_meta.principal_domain;
begin
 p:=ecos_meta.current_principal();
 select pd.* into b from ecos_meta.principal_domain pd join ecos_meta.domain_effect_target t on t.domain=pd.domain where pd.principal_id=p.principal_id and t.target=target_;
 b:=ecos_meta.effect_authority(p.principal_id,target_,b.authority_epoch);
 return jsonb_build_object('domain',b.domain,'generation',b.executor_generation,'epoch',b.authority_epoch,'target',target_);
end $function$;

CREATE OR REPLACE FUNCTION ecos.staffing_features_read(site text)
 RETURNS jsonb
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO 'pg_catalog'
AS $function$
declare p ecos_meta.principal_binding; b ecos_meta.principal_domain;
begin
 p:=ecos_meta.current_principal();
 select * into b from ecos_meta.principal_domain where principal_id=p.principal_id and domain in ('toast.acquisition','staffing.features') order by (domain='toast.acquisition') desc limit 1;
 if b.domain not in ('toast.acquisition','staffing.features') or b.principal_id is null then
   raise exception 'forbidden' using errcode='42501';
 end if;
 return ecos_meta.staffing_statistics('toast.acquisition',b.execution_mode,site);
end $function$;

CREATE OR REPLACE FUNCTION ecos.staffing_features_read(site text, from_date date, through_date date)
 RETURNS jsonb
 LANGUAGE plpgsql
 STABLE SECURITY DEFINER
 SET search_path TO 'pg_catalog'
 SET jit TO 'off'
AS $function$
declare p ecos_meta.principal_binding; b ecos_meta.principal_domain;
begin
 if from_date is null or through_date is null or through_date<from_date or through_date-from_date>30 then
  raise exception 'bounded_staffing_date_window_required' using errcode='22023';
 end if;
 p:=ecos_meta.current_principal();
 select * into b from ecos_meta.principal_domain where principal_id=p.principal_id and domain in ('toast.acquisition','staffing.features') order by (domain='toast.acquisition') desc limit 1;
 if b.domain not in ('toast.acquisition','staffing.features') or b.principal_id is null then
  raise exception 'forbidden' using errcode='42501';
 end if;
 return ecos_meta.staffing_statistics('toast.acquisition',b.execution_mode,site,from_date,through_date);
end $function$;

CREATE OR REPLACE FUNCTION ecos_meta.require_access(principal uuid, kind text, entity uuid)
 RETURNS void
 LANGUAGE plpgsql
 STABLE
 SET search_path TO 'pg_catalog'
AS $function$
declare b ecos_meta.principal_domain; d text;
begin
 perform ecos_meta.require_access_phase2(principal,kind,entity);
 select domain into d from ecos_meta.object_domain where record_type=kind and record_id=entity;
 select * into b from ecos_meta.principal_domain where principal_id=principal and domain=coalesce(d,'synthetic.acceptance');
 if b.principal_id is null or (d is not null and d<>b.domain) or (b.execution_mode<>'synthetic' and d is null) then raise exception 'forbidden' using errcode='42501'; end if;
end $function$;

CREATE OR REPLACE FUNCTION ecos_meta.apply_operation_before_gmail_approval(op text, ctx jsonb, args jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO 'pg_catalog'
AS $function$
declare c ecos.work_claim; w ecos.work_occurrence; b ecos_meta.principal_domain; stage_ text; surface_ text;
 e ecos.gmail_evidence; p ecos.communication_processing; cmd ecos.provider_command; a ecos.approval_request;
 data_ jsonb; v jsonb; proposal_ jsonb; committed_ jsonb; request_ jsonb; h text; raw_ bytea;
 receipt_ uuid; communication_ uuid; processing_ uuid; occurrence_ uuid; command_ uuid; approval_ uuid; attempt_ uuid;
begin
 if op not like 'gmail.%' then return ecos_meta.apply_operation_before_gmail(op,ctx,args); end if;
 c:=ecos_meta.check_fence(ctx,args->'fence');
 select * into w from ecos.work_occurrence where id=c.occurrence_id;
 select * into b from ecos_meta.principal_domain where principal_id=(ctx->>'principal_id')::uuid and domain='gmail.operations';
 if b.principal_id is null or b.domain<>'gmail.operations' or b.execution_mode<>'production' then raise exception 'forbidden' using errcode='42501'; end if;
 select stage_key,execution_surface into stage_,surface_ from ecos.work_stage_definition where id=c.stage_definition_id;
 if op='gmail.intake' then
  if stage_<>'gmail_intake' or surface_<>'ONLINE_SEMANTIC' then raise exception 'forbidden' using errcode='42501'; end if;
  v:=args->'evidence';
  if v->>'message_id' is distinct from (select input->>'message_id' from ecos.work_context where occurrence_id=w.id)
   or v->>'account_scope' is distinct from (select input->>'account_scope' from ecos.work_context where occurrence_id=w.id) then raise exception 'invalid_contract'; end if;
  raw_:=decode(translate(v->>'raw','-_','+/')||repeat('=',(4-length(v->>'raw')%4)%4),'base64');
  if encode(sha256(raw_),'hex')<>v->>'raw_sha256' then raise exception 'invalid_contract'; end if;
  perform pg_advisory_xact_lock(hashtextextended('gmail:'||(v->>'account_scope')||':'||(v->>'message_id'),0));
  select * into e from ecos.gmail_evidence where account_scope=v->>'account_scope' and message_id=v->>'message_id';
  if e.receipt_id is not null then
   if e.evidence->>'raw_sha256'<>v->>'raw_sha256' or e.thread_id<>v->>'thread_id' then raise exception 'idempotency_conflict'; end if;
   data_:=jsonb_build_object('receipt_id',e.receipt_id,'communication_id',e.communication_id,'processing_id',e.processing_id,'duplicate',true);
  else
   if exists(select 1 from ecos.provider_receipt where provider='gmail' and account_scope=v->>'account_scope' and provider_object_id=v->>'message_id') then raise exception 'unknown_outcome'; end if;
   receipt_:=gen_random_uuid();communication_:=gen_random_uuid();processing_:=gen_random_uuid();
   insert into ecos.provider_receipt(id,provider,account_scope,provider_event_id,dedupe_key,provider_object_id,provider_occurred_at,received_at,raw_artifact_uri,raw_content_hash,signature_verified,correlation_id)
   values(receipt_,'gmail',v->>'account_scope',v->>'history_id',v->>'message_id',v->>'message_id',to_timestamp((v->>'internal_date')::numeric/1000),clock_timestamp(),'ecos:gmail-evidence:'||receipt_,v->>'raw_sha256',false,(ctx->>'correlation_id')::uuid);
   insert into ecos.communication(id,receipt_id,channel,provider_thread_id,direction,body_artifact_uri,body_hash)
   values(communication_,receipt_,'email',v->>'thread_id','inbound','ecos:gmail-evidence:'||receipt_,v->>'raw_sha256');
   perform ecos_meta.gmail_grant('provider_receipt',receipt_,b.domain);
   perform ecos_meta.gmail_grant('communication',communication_,b.domain);
   occurrence_:=ecos_meta.gmail_enqueue('gmail_semantic',w.task_id,jsonb_build_object('receipt_id',receipt_,'communication_id',communication_,'processing_id',processing_,'account_scope',v->>'account_scope','message_id',v->>'message_id','thread_id',v->>'thread_id'),b.domain,(ctx->>'correlation_id')::uuid,'gmail:'||receipt_||':semantic');
   insert into ecos.work_dependency(occurrence_id,prerequisite_occurrence_id,required_result_schema_id) select occurrence_,w.id,result_schema_id from ecos.work_stage_definition where id=w.stage_definition_id;
   insert into ecos.communication_processing(id,communication_id,source_version,state,occurrence_id) values(processing_,communication_,1,'ready',occurrence_);
   perform ecos_meta.gmail_grant('communication_processing',processing_,b.domain);
   insert into ecos.gmail_evidence values(receipt_,communication_,processing_,v->>'account_scope',v->>'message_id',v->>'thread_id',v,b.domain,(ctx->>'correlation_id')::uuid);
   data_:=jsonb_build_object('receipt_id',receipt_,'communication_id',communication_,'processing_id',processing_,'semantic_occurrence_id',occurrence_,'duplicate',false);
  end if;
 elsif op='gmail.process' then
  if stage_<>'gmail_semantic' or surface_<>'ONLINE_SEMANTIC' then raise exception 'forbidden' using errcode='42501'; end if;
  select * into p from ecos.communication_processing where occurrence_id=w.id for update;
  select * into e from ecos.gmail_evidence where processing_id=p.id;
  if p.id is null or p.state<>'ready' or e.domain<>b.domain then raise exception 'gate_blocked'; end if;
  select proposal into proposal_ from ecos.proposal_submission where proposal_id=(args->>'proposal_id')::uuid and occurrence_id=w.id and principal_id=(ctx->>'principal_id')::uuid;
  if proposal_ is null then raise exception 'gate_blocked'; end if;
  committed_:=ecos_meta.commit_proposal(ctx,proposal_);
  if exists(select 1 from jsonb_array_elements(committed_->'items') i where i->>'state'<>'committed') then raise exception 'gate_blocked'; end if;
  perform ecos_meta.gmail_grant('fact',ev.aggregate_id,b.domain)
   from jsonb_array_elements(committed_->'items') i
   cross join lateral jsonb_array_elements_text(i->'committed_event_ids') event_id
   join ecos.domain_event ev on ev.id=event_id::uuid where ev.aggregate_type='fact';
  update ecos.communication_processing set state='running',proposal_id=(args->>'proposal_id')::uuid,record_version=record_version+1 where id=p.id;
  if args->'draft_request'='null'::jsonb then
   update ecos.communication_processing set state='succeeded',record_version=record_version+1 where id=p.id;
   data_:=jsonb_build_object('processing_id',p.id,'state','succeeded');
  else
   request_:=args->'draft_request';h:=ecos_meta.content_hash(request_);command_:=gen_random_uuid();approval_:=gen_random_uuid();
   if request_->>'thread_id'<>e.thread_id or request_->>'source_message_id'<>e.message_id then raise exception 'invalid_contract'; end if;
   insert into ecos.approval_request(id,task_id,subject_type,subject_id,subject_hash,state,expires_at) values(approval_,w.task_id,'provider_command',command_,h,'pending',clock_timestamp()+interval '1 day');
   insert into ecos.provider_command(id,provider,account_scope,command_type,idempotency_key,request_schema_id,request_artifact_uri,request_hash,correlation_id,causation_id,outcome,reconciliation_strategy,approval_request_id)
   values(command_,'gmail',e.account_scope,'draft.create','gmail:'||p.id||':draft','ecos.gmail.draft.v1','ecos:gmail-draft:'||command_,h,e.correlation_id,p.id,'pending','provider_lookup',approval_);
   insert into ecos.gmail_draft_request values(command_,p.id,request_,h,null);
   perform ecos_meta.gmail_grant('provider_command',command_,b.domain);perform ecos_meta.gmail_grant('approval_request',approval_,b.domain);
   occurrence_:=ecos_meta.gmail_enqueue('gmail_draft',w.task_id,jsonb_build_object('command_id',command_,'processing_id',p.id),b.domain,e.correlation_id,'gmail:'||p.id||':draft');
   insert into ecos.work_dependency(occurrence_id,prerequisite_occurrence_id,required_result_schema_id) select occurrence_,w.id,result_schema_id from ecos.work_stage_definition where id=w.stage_definition_id;
   insert into ecos.command_occurrence values(command_,occurrence_);
   insert into ecos.work_approval values(occurrence_,approval_,h);
   data_:=jsonb_build_object('processing_id',p.id,'command_id',command_,'approval_request_id',approval_,'subject_hash',h,'draft_occurrence_id',occurrence_);
  end if;
 elsif op='gmail.dispatch.begin' then
  if stage_ not in ('gmail_draft','gmail_send') or surface_<>'RESIDENT_DETERMINISTIC_PROVIDER' then raise exception 'forbidden' using errcode='42501'; end if;
  select q.* into cmd from ecos.provider_command q join ecos.command_occurrence co on co.provider_command_id=q.id where co.occurrence_id=w.id and q.id=(args->>'command_id')::uuid for update of q;
  if cmd.id is null or cmd.provider<>'gmail' or cmd.command_type not in ('draft.create','draft.update','send') then raise exception 'forbidden' using errcode='42501'; end if;
  if (stage_='gmail_send')<>(cmd.command_type='send') then raise exception 'invalid_contract'; end if;
  select * into a from ecos.approval_request where id=cmd.approval_request_id for share;
  if a.id is null or a.state<>'approved' or a.expires_at<=clock_timestamp() or a.subject_hash<>cmd.request_hash or a.subject_id<>cmd.id
   or not exists(select 1 from ecos.work_approval where occurrence_id=w.id and approval_request_id=a.id and expected_subject_hash=cmd.request_hash)
   or not exists(select 1 from ecos.approval_decision where approval_request_id=a.id and decision='approved') then raise exception 'gate_blocked'; end if;
  if cmd.outcome<>'pending' then raise exception 'unknown_outcome'; end if;
  insert into ecos.provider_attempt(provider_command_id,attempt_number,request_hash,started_at,outcome) values(cmd.id,1,cmd.request_hash,clock_timestamp(),'unknown_outcome') returning id into attempt_;
  update ecos.provider_command set outcome='unknown_outcome',record_version=record_version+1 where id=cmd.id;
  data_:=jsonb_build_object('command_id',cmd.id,'attempt_id',attempt_,'request_hash',cmd.request_hash,'disposition','dispatch');
 elsif op='gmail.dispatch.finish' then
  if stage_<>'gmail_draft' or surface_<>'RESIDENT_DETERMINISTIC_PROVIDER' then raise exception 'forbidden' using errcode='42501'; end if;
  select q.* into cmd from ecos.provider_command q join ecos.command_occurrence co on co.provider_command_id=q.id where co.occurrence_id=w.id and q.id=(args->>'command_id')::uuid for update of q;
  if cmd.id is null or cmd.command_type not in ('draft.create','draft.update') or cmd.outcome not in ('unknown_outcome','reconciled') then raise exception 'gate_blocked'; end if;
  select * into e from ecos.gmail_evidence where processing_id=(select processing_id from ecos.gmail_draft_request where command_id=cmd.id);
  v:=args->'readback';
  if v->>'account_scope'<>cmd.account_scope or v->>'thread_id'<>e.thread_id or (v->>'sent')::boolean then raise exception 'invalid_contract'; end if;
  if not exists(select 1 from ecos.provider_attempt where id=(args->>'attempt_id')::uuid and provider_command_id=cmd.id and request_hash=cmd.request_hash) then raise exception 'invalid_contract'; end if;
  if cmd.outcome='reconciled' then
   if not exists(select 1 from ecos.provider_result where provider_command_id=cmd.id and provider_attempt_id=(args->>'attempt_id')::uuid and outcome='reconciled' and reconciled_outcome='succeeded' and provider_object_id=v->>'draft_id' and evidence_hash=ecos_meta.content_hash(v)) then raise exception 'gate_blocked'; end if;
  else
   insert into ecos.provider_result(provider_command_id,provider_attempt_id,outcome,observed_at,provider_object_id,evidence_hash,reconciled_outcome)
   values(cmd.id,(args->>'attempt_id')::uuid,'reconciled',clock_timestamp(),v->>'draft_id',ecos_meta.content_hash(v),'succeeded');
  end if;
  update ecos.provider_command set outcome='reconciled',record_version=record_version+1 where id=cmd.id;
  update ecos.gmail_draft_request set readback=v where command_id=cmd.id;
  update ecos.communication_processing set state='succeeded',committed_result_id=cmd.id,record_version=record_version+1 where id=e.processing_id;
  data_:=jsonb_build_object('command_id',cmd.id,'processing_id',e.processing_id,'readback',v);
 else raise exception 'invalid_contract'; end if;
 return jsonb_build_object('schema_version','1.0.0','correlation_id',ctx->>'correlation_id','status','committed','data',data_);
end $function$;

revoke all on all functions in schema ecos_meta from public;
reset role;
