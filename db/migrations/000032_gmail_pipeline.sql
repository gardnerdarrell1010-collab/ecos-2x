-- Gmail operations reuse the existing work, communication, approval and provider models.
set local role ecos_owner;
create table ecos.gmail_evidence (
 receipt_id uuid primary key references ecos.provider_receipt,
 communication_id uuid not null unique references ecos.communication,
 processing_id uuid not null unique references ecos.communication_processing,
 account_scope text not null, message_id text not null, thread_id text not null,
 evidence jsonb not null, domain text not null references ecos_meta.domain_authority,
 correlation_id uuid not null, unique(account_scope,message_id)
);
create table ecos.gmail_draft_request (
 command_id uuid primary key references ecos.provider_command,
 processing_id uuid not null references ecos.communication_processing,
 request jsonb not null, request_hash text not null,
 readback jsonb, unique(processing_id)
);
alter table ecos.gmail_evidence enable row level security;
alter table ecos.gmail_draft_request enable row level security;
revoke all on ecos.gmail_evidence,ecos.gmail_draft_request from public,executor,operations_api,provider_adapter;
create trigger immutable before update or delete on ecos.gmail_evidence for each row execute function ecos_meta.forbid_evidence_change();

create function ecos_meta.gmail_grant(kind_ text,id_ uuid,domain_ text) returns void language plpgsql set search_path=pg_catalog as $$
begin
 if exists(select 1 from ecos_meta.object_domain where record_type=kind_ and record_id=id_ and domain<>domain_) then raise exception 'forbidden' using errcode='42501'; end if;
 insert into ecos_meta.object_domain values(kind_,id_,domain_) on conflict do nothing;
 insert into ecos_meta.object_grant select principal_id,kind_,id_ from ecos_meta.principal_domain where domain=domain_ and executor_generation='2X' on conflict do nothing;
end $$;

create function ecos_meta.gmail_enqueue(stage_ text,task_ uuid,input_ jsonb,domain_ text,correlation_ uuid,key_ text) returns uuid language plpgsql set search_path=pg_catalog as $$
declare s ecos.work_stage_definition; o uuid; refs jsonb;
begin
 select * into s from ecos.work_stage_definition where stage_key=stage_ and work_definition_id in (select id from ecos.work_definition where name in ('gmail_intake','gmail_semantic','gmail_dispatch') and definition_version=1);
 if s.id is null then raise exception 'invalid_contract'; end if;
 select id into o from ecos.work_occurrence where work_definition_id=s.work_definition_id and stage_definition_id=s.id and occurrence_key=key_;
 if o is not null then return o; end if;
 insert into ecos.work_occurrence(work_definition_id,stage_definition_id,fulfillment_id,task_id,state,occurrence_key,due_at)
 values(s.work_definition_id,s.id,gen_random_uuid(),task_,'ready',key_,clock_timestamp()) returning id into o;
 perform ecos_meta.gmail_grant('work_occurrence',o,domain_);
 perform ecos_meta.gmail_grant('task',task_,domain_);
 select jsonb_build_array(jsonb_build_object('record_type','task','record_id',t.id,'record_version',t.record_version,'content_hash',ecos_meta.content_hash(to_jsonb(t)),'authority','structured_ecos')) into refs from ecos.task t where id=task_;
 insert into ecos.work_context(occurrence_id,operation,source_references,input) values(o,case stage_ when 'gmail_intake' then 'gmail.intake' when 'gmail_semantic' then 'gmail.process' else 'gmail.dispatch.begin' end,refs,input_);
 perform ecos_meta.wake_work(o,correlation_,'gmail');
 return o;
end $$;

alter function ecos_meta.require_operation_scope(text,jsonb,uuid) rename to require_operation_scope_before_gmail;
create function ecos_meta.require_operation_scope(op text,args jsonb,principal uuid) returns void language plpgsql stable set search_path=pg_catalog as $$
begin
 perform ecos_meta.require_operation_scope_before_gmail(op,args,principal);
 if op like 'gmail.%' then perform ecos_meta.require_access(principal,'work_occurrence',(args->'fence'->>'occurrence_id')::uuid); end if;
end $$;

alter function ecos_meta.apply_operation(text,jsonb,jsonb) rename to apply_operation_before_gmail;
create function ecos_meta.apply_operation(op text,ctx jsonb,args jsonb) returns jsonb language plpgsql set search_path=pg_catalog as $$
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
  if cmd.id is null or cmd.command_type not in ('draft.create','draft.update') or cmd.outcome<>'unknown_outcome' then raise exception 'gate_blocked'; end if;
  select * into e from ecos.gmail_evidence where processing_id=(select processing_id from ecos.gmail_draft_request where command_id=cmd.id);
  v:=args->'readback';
  if v->>'account_scope'<>cmd.account_scope or v->>'thread_id'<>e.thread_id or (v->>'sent')::boolean then raise exception 'invalid_contract'; end if;
  if not exists(select 1 from ecos.provider_attempt where id=(args->>'attempt_id')::uuid and provider_command_id=cmd.id and request_hash=cmd.request_hash) then raise exception 'invalid_contract'; end if;
  insert into ecos.provider_result(provider_command_id,provider_attempt_id,outcome,observed_at,provider_object_id,evidence_hash,reconciled_outcome)
  values(cmd.id,(args->>'attempt_id')::uuid,'reconciled',clock_timestamp(),v->>'draft_id',ecos_meta.content_hash(v),'succeeded');
  update ecos.provider_command set outcome='reconciled',record_version=record_version+1 where id=cmd.id;
  update ecos.gmail_draft_request set readback=v where command_id=cmd.id;
  update ecos.communication_processing set state='succeeded',committed_result_id=cmd.id,record_version=record_version+1 where id=e.processing_id;
  data_:=jsonb_build_object('command_id',cmd.id,'processing_id',e.processing_id,'readback',v);
 else raise exception 'invalid_contract'; end if;
 return jsonb_build_object('schema_version','1.0.0','correlation_id',ctx->>'correlation_id','status','committed','data',data_);
end $$;

create function ecos.gmail_read(occurrence_ uuid) returns jsonb language plpgsql security definer set search_path=pg_catalog as $$
declare p ecos_meta.principal_binding; i jsonb; e ecos.gmail_evidence; d ecos.gmail_draft_request; cmd ecos.provider_command;
begin
 p:=ecos_meta.current_principal();perform ecos_meta.require_domain(p.principal_id,'work.package');perform ecos_meta.require_access(p.principal_id,'work_occurrence',occurrence_);
 select input into i from ecos.work_context where occurrence_id=occurrence_;
 select * into e from ecos.gmail_evidence where processing_id=(i->>'processing_id')::uuid;
 if e.receipt_id is not null then perform ecos_meta.require_access(p.principal_id,'communication',e.communication_id); end if;
 select * into d from ecos.gmail_draft_request where command_id=(i->>'command_id')::uuid;
 if d.command_id is not null then perform ecos_meta.require_access(p.principal_id,'provider_command',d.command_id); select * into cmd from ecos.provider_command where id=d.command_id; end if;
 return jsonb_build_object('input',i,'evidence',to_jsonb(e),'draft_request',to_jsonb(d),'command',to_jsonb(cmd));
end $$;
revoke all on function ecos.gmail_read(uuid) from public;
grant execute on function ecos.gmail_read(uuid) to executor;
revoke all on all functions in schema ecos_meta from public;
insert into ecos_meta.contract_schema values('https://contracts.ecos.invalid/v1/gmail.intake-request.schema.json','{"$schema":"https://json-schema.org/draft/2020-12/schema","$id":"https://contracts.ecos.invalid/v1/gmail.intake-request.schema.json","title":"gmail.intake-request","type":"object","properties":{"schema_version":{"const":"1.0.0"},"context":{"$ref":"https://contracts.ecos.invalid/v1/request_context.schema.json"},"arguments":{"type":"object","properties":{"fence":{"$ref":"https://contracts.ecos.invalid/v1/fence.schema.json"},"evidence":{"type":"object","properties":{"provider":{"const":"gmail"},"account_scope":{"type":"string","minLength":1,"maxLength":200},"message_id":{"type":"string","minLength":1,"maxLength":200},"thread_id":{"type":"string","minLength":1,"maxLength":200},"history_id":{"anyOf":[{"type":"string","minLength":1,"maxLength":200},{"type":"null"}]},"internal_date":{"type":"string","minLength":1,"maxLength":200},"raw":{"type":"string","minLength":1,"maxLength":200000},"raw_sha256":{"type":"string","pattern":"^[a-f0-9]{64}$"},"label_ids":{"type":"array","items":{"type":"string","minLength":1,"maxLength":200},"maxItems":100},"display":{"type":"object","properties":{"subject":{"type":"string","maxLength":1000},"from":{"type":"string","maxLength":1000},"rfc_message_id":{"type":"string","minLength":1,"maxLength":1000},"text":{"type":"string","maxLength":12000}},"required":["subject","from","rfc_message_id","text"],"additionalProperties":false}},"required":["provider","account_scope","message_id","thread_id","history_id","internal_date","raw","raw_sha256","label_ids","display"],"additionalProperties":false},"observed_at":{"type":"string","format":"date-time"}},"required":["fence","evidence","observed_at"],"additionalProperties":false}},"required":["schema_version","context","arguments"],"additionalProperties":false}'::jsonb);
insert into ecos_meta.operation_contract values('gmail.intake','{"name":"gmail.intake","request_schema":"https://contracts.ecos.invalid/v1/gmail.intake-request.schema.json","response_schema":"https://contracts.ecos.invalid/v1/phase2_result.schema.json","required_role":"executor","semantic_proposable":false,"idempotency_scope":"principal_id + operation + idempotency_key","atomicity":"single transaction"}'::jsonb);
insert into ecos_meta.contract_schema values('https://contracts.ecos.invalid/v1/gmail.process-request.schema.json','{"$schema":"https://json-schema.org/draft/2020-12/schema","$id":"https://contracts.ecos.invalid/v1/gmail.process-request.schema.json","title":"gmail.process-request","type":"object","properties":{"schema_version":{"const":"1.0.0"},"context":{"$ref":"https://contracts.ecos.invalid/v1/request_context.schema.json"},"arguments":{"type":"object","properties":{"fence":{"$ref":"https://contracts.ecos.invalid/v1/fence.schema.json"},"proposal_id":{"type":"string","format":"uuid"},"draft_request":{"anyOf":[{"type":"object","properties":{"to":{"type":"array","items":{"type":"string","minLength":1,"maxLength":200},"maxItems":20},"subject":{"type":"string","minLength":1,"maxLength":500},"body":{"type":"string","minLength":1,"maxLength":10000},"thread_id":{"type":"string","minLength":1,"maxLength":200},"source_message_id":{"type":"string","minLength":1,"maxLength":200},"in_reply_to":{"type":"string","minLength":1,"maxLength":200}},"required":["to","subject","body","thread_id","source_message_id","in_reply_to"],"additionalProperties":false},{"type":"null"}]}},"required":["fence","proposal_id","draft_request"],"additionalProperties":false}},"required":["schema_version","context","arguments"],"additionalProperties":false}'::jsonb);
insert into ecos_meta.operation_contract values('gmail.process','{"name":"gmail.process","request_schema":"https://contracts.ecos.invalid/v1/gmail.process-request.schema.json","response_schema":"https://contracts.ecos.invalid/v1/phase2_result.schema.json","required_role":"executor","semantic_proposable":false,"idempotency_scope":"principal_id + operation + idempotency_key","atomicity":"single transaction"}'::jsonb);
insert into ecos_meta.contract_schema values('https://contracts.ecos.invalid/v1/gmail.dispatch.begin-request.schema.json','{"$schema":"https://json-schema.org/draft/2020-12/schema","$id":"https://contracts.ecos.invalid/v1/gmail.dispatch.begin-request.schema.json","title":"gmail.dispatch.begin-request","type":"object","properties":{"schema_version":{"const":"1.0.0"},"context":{"$ref":"https://contracts.ecos.invalid/v1/request_context.schema.json"},"arguments":{"type":"object","properties":{"fence":{"$ref":"https://contracts.ecos.invalid/v1/fence.schema.json"},"command_id":{"type":"string","format":"uuid"}},"required":["fence","command_id"],"additionalProperties":false}},"required":["schema_version","context","arguments"],"additionalProperties":false}'::jsonb);
insert into ecos_meta.operation_contract values('gmail.dispatch.begin','{"name":"gmail.dispatch.begin","request_schema":"https://contracts.ecos.invalid/v1/gmail.dispatch.begin-request.schema.json","response_schema":"https://contracts.ecos.invalid/v1/phase2_result.schema.json","required_role":"executor","semantic_proposable":false,"idempotency_scope":"principal_id + operation + idempotency_key","atomicity":"single transaction"}'::jsonb);
insert into ecos_meta.contract_schema values('https://contracts.ecos.invalid/v1/gmail.dispatch.finish-request.schema.json','{"$schema":"https://json-schema.org/draft/2020-12/schema","$id":"https://contracts.ecos.invalid/v1/gmail.dispatch.finish-request.schema.json","title":"gmail.dispatch.finish-request","type":"object","properties":{"schema_version":{"const":"1.0.0"},"context":{"$ref":"https://contracts.ecos.invalid/v1/request_context.schema.json"},"arguments":{"type":"object","properties":{"fence":{"$ref":"https://contracts.ecos.invalid/v1/fence.schema.json"},"command_id":{"type":"string","format":"uuid"},"attempt_id":{"type":"string","format":"uuid"},"readback":{"type":"object","properties":{"draft_id":{"type":"string","minLength":1,"maxLength":200},"message_id":{"type":"string","minLength":1,"maxLength":200},"thread_id":{"type":"string","minLength":1,"maxLength":200},"readback_sha256":{"type":"string","pattern":"^[a-f0-9]{64}$"},"provider":{"const":"gmail"},"account_scope":{"type":"string","minLength":1,"maxLength":200},"sent":{"const":false}},"required":["draft_id","message_id","thread_id","readback_sha256","provider","account_scope","sent"],"additionalProperties":false}},"required":["fence","command_id","attempt_id","readback"],"additionalProperties":false}},"required":["schema_version","context","arguments"],"additionalProperties":false}'::jsonb);
insert into ecos_meta.operation_contract values('gmail.dispatch.finish','{"name":"gmail.dispatch.finish","request_schema":"https://contracts.ecos.invalid/v1/gmail.dispatch.finish-request.schema.json","response_schema":"https://contracts.ecos.invalid/v1/phase2_result.schema.json","required_role":"executor","semantic_proposable":false,"idempotency_scope":"principal_id + operation + idempotency_key","atomicity":"single transaction"}'::jsonb);
reset role;

