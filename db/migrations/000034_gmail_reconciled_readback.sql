-- Preserve a verified existing Gmail draft after a failed readback; no provider replay.
set local role ecos_owner;
create or replace function ecos_meta.apply_operation_before_gmail_approval(op text,ctx jsonb,args jsonb) returns jsonb language plpgsql set search_path=pg_catalog as $$
declare c ecos.work_claim; w ecos.work_occurrence; b ecos_meta.principal_domain; stage_ text; surface_ text;
 e ecos.gmail_evidence; p ecos.communication_processing; cmd ecos.provider_command; a ecos.approval_request;
 data_ jsonb; v jsonb; proposal_ jsonb; committed_ jsonb; request_ jsonb; h text; raw_ bytea;
 receipt_ uuid; communication_ uuid; processing_ uuid; occurrence_ uuid; command_ uuid; approval_ uuid; attempt_ uuid;
begin
 if op not like 'gmail.%' then return ecos_meta.apply_operation_before_gmail(op,ctx,args); end if;
 c:=ecos_meta.check_fence(ctx,args->'fence');
 select * into w from ecos.work_occurrence where id=c.occurrence_id;
 select * into b from ecos_meta.principal_domain where principal_id=(ctx->>'principal_id')::uuid;
 if b.domain<>'gmail.operations' or b.execution_mode<>'production' then raise exception 'forbidden' using errcode='42501'; end if;
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
end $$;

reset role;
