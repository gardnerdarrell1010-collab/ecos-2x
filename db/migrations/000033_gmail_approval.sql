-- Complete the existing owner approval operation for Gmail draft request hashes.
set local role ecos_owner;
create or replace function ecos_meta.gmail_grant(kind_ text,id_ uuid,domain_ text) returns void language plpgsql set search_path=pg_catalog as $$
begin
 if exists(select 1 from ecos_meta.object_domain where record_type=kind_ and record_id=id_ and domain<>domain_) then raise exception 'forbidden' using errcode='42501'; end if;
 insert into ecos_meta.object_domain values(kind_,id_,domain_) on conflict do nothing;
 insert into ecos_meta.object_grant select d.principal_id,kind_,id_ from ecos_meta.principal_domain d
 where d.domain=domain_ and d.executor_generation='2X'
 and exists(select 1 from ecos.executor_instance i join ecos.executor e on e.id=i.executor_id where i.principal_id=d.principal_id and e.enabled)
 on conflict do nothing;
end $$;
alter function ecos_meta.apply_operation(text,jsonb,jsonb) rename to apply_operation_before_gmail_approval;
create function ecos_meta.apply_operation(op text,ctx jsonb,args jsonb) returns jsonb
language plpgsql set search_path=pg_catalog as $$
declare a ecos.approval_request; c ecos.provider_command; d ecos.gmail_draft_request;
 principal uuid:=(ctx->>'principal_id')::uuid; result_ jsonb;
begin
 if op<>'approval.decide' then return ecos_meta.apply_operation_before_gmail_approval(op,ctx,args); end if;
 select * into a from ecos.approval_request where id=(args->>'approval_request_id')::uuid;
 if a.subject_type<>'provider_command' or not exists(select 1 from ecos.gmail_draft_request where command_id=a.subject_id) then
  return ecos_meta.apply_operation_before_gmail_approval(op,ctx,args);
 end if;
 perform ecos_meta.require_access(principal,'approval_request',a.id);
 perform ecos_meta.require_access(principal,'provider_command',a.subject_id);
 select * into a from ecos.approval_request where id=a.id for update;
 select * into c from ecos.provider_command where id=a.subject_id for update;
 select * into d from ecos.gmail_draft_request where command_id=c.id for share;
 if a.record_version is distinct from (args->>'expected_version')::bigint then raise exception 'stale_version' using errcode='40001'; end if;
 if a.state<>'pending' or c.provider<>'gmail' or c.command_type<>'draft.create' or c.outcome<>'pending'
  or a.subject_hash<>args->>'subject_hash' or a.subject_hash<>c.request_hash
  or c.request_hash<>d.request_hash or d.request_hash<>ecos_meta.content_hash(d.request)
  or a.expires_at<=clock_timestamp() then raise exception 'gate_blocked' using errcode='23514'; end if;
 insert into ecos.approval_decision(approval_request_id,decision,actor_id,reason_code,evidence,supersedes_decision_id)
 values(a.id,args->>'decision',principal,args->>'reason_code','[]',null);
 update ecos.approval_request set state=args->>'decision',record_version=record_version+1 where id=a.id;
 result_:=jsonb_build_object('schema_version','1.0.0','operation_id',gen_random_uuid(),'correlation_id',ctx->'correlation_id','status','committed','event_ids','[]'::jsonb,'record_versions',jsonb_build_array(jsonb_build_object('record_type','approval_request','record_id',a.id,'record_version',a.record_version+1)));
 return result_||jsonb_build_object('result_hash',ecos_meta.content_hash(result_));
end $$;
revoke all on function ecos_meta.apply_operation(text,jsonb,jsonb),ecos_meta.apply_operation_before_gmail_approval(text,jsonb,jsonb) from public,executor,operations_api,provider_adapter;
reset role;
