-- Governed evidence correlation and immutable, scoped continuity packages.
set local role ecos_owner;
create trigger immutable before update or delete on ecos.export_package
 for each row execute function ecos_meta.forbid_evidence_change();
create trigger continuity_immutable before update or delete on ecos.artifact
 for each row when(old.provider='ecos.continuity') execute function ecos_meta.forbid_evidence_change();
alter function ecos_meta.apply_operation(text,jsonb,jsonb) rename to apply_operation_before_core_evidence;
create function ecos_meta.apply_operation(op text,ctx jsonb,args jsonb) returns jsonb
language plpgsql set search_path=pg_catalog as $$
declare principal uuid:=(ctx->>'principal_id')::uuid; c ecos.work_claim; v jsonb; row_ jsonb;
 refs jsonb:='[]'; rows_ jsonb:='[]'; g record; id_ uuid; artifact_ uuid; backup_ uuid;
 manifest_ jsonb; bytes_ bytea; boundary_ jsonb; prior_ uuid; count_ integer:=0;
 restore_ uuid; verify_ uuid; restore_text text:='Decrypt records.aes-gcm using AES-256-GCM with the governed ecos.continuity.encryption key, stored IV and canonical source boundary as additional authenticated data, then decompress gzip. Verify plaintext SHA-256 and each source reference before restoring into an isolated PostgreSQL target. This package covers explicit object grants only, not a full database.';
 verify_text text:='select version(); -- Verify each typed row against its recorded source UUID, version and hash before any restore. No automatic production writes.';
begin
 if op not in ('runtime.evidence.read','continuity.snapshot','continuity.checkpoint.commit') then
  return ecos_meta.apply_operation_before_core_evidence(op,ctx,args);
 end if;
 if op='runtime.evidence.read' then
  c:=ecos_meta.core_claim(ctx,args,array['outstanding_request_monitor','sms_inbound_process']);
  id_:=(args->>'communication_id')::uuid;
  perform ecos_meta.require_access(principal,'communication',id_);
  row_:=ecos_meta.record_value('communication',id_);
  perform ecos_meta.require_access(principal,'provider_receipt',(row_->>'receipt_id')::uuid);
  v:=jsonb_build_object('communication',row_,'receipt',ecos_meta.record_value('provider_receipt',(row_->>'receipt_id')::uuid),
   'gmail_evidence',(select evidence-'raw' from ecos.gmail_evidence where communication_id=id_));
 elsif op='continuity.snapshot' then
  c:=ecos_meta.core_claim(ctx,args,array['incremental_continuity']);
  for g in select record_type,record_id from ecos_meta.object_grant where principal_id=principal
   and record_type in ('task','project','party','relationship','notification','delivery','memory_record','memory_version','memory_scope')
   order by record_type,record_id loop
   perform ecos_meta.require_access(principal,g.record_type,g.record_id);
   row_:=ecos_meta.record_value(g.record_type,g.record_id,true);
   rows_:=rows_||jsonb_build_array(jsonb_build_object('record_type',g.record_type,'record',row_));
   refs:=refs||jsonb_build_array(jsonb_build_object('record_type',g.record_type,'record_id',g.record_id,
    'record_version',coalesce((row_->>'record_version')::bigint,1),'content_hash',ecos_meta.content_hash(row_),'authority','structured_ecos'));
   count_:=count_+1;
   if count_>10000 or octet_length(rows_::text)>8388608 then raise exception 'invalid_contract'; end if;
  end loop;
  select (r.result->'data'->>'package_id')::uuid into prior_ from ecos_meta.operation_receipt r
   join ecos.stage_result sr on sr.occurrence_id=(r.result->'data'->>'occurrence_id')::uuid
   where r.principal_id=principal and r.operation='continuity.checkpoint.commit'
   order by sr.created_at desc,sr.id desc limit 1;
  v:=jsonb_build_object('records',rows_,'source_references',refs,'source_hash',ecos_meta.content_hash(rows_),
   'previous_package_id',prior_,'observed_at',clock_timestamp(),'record_count',count_);
 else
  c:=ecos_meta.core_claim(ctx,args,array['incremental_continuity']);
  -- The hosted adapter encrypts and verifies a round trip before submitting.
  -- PostgreSQL independently verifies the exact source boundary and ciphertext inventory.
  boundary_:=args->'boundary';
  perform ecos_meta.verify_sources(principal,boundary_->'source_references');
  for g in select value as ref from jsonb_array_elements(boundary_->'source_references') loop
   row_:=ecos_meta.record_value(g.ref->>'record_type',(g.ref->>'record_id')::uuid,true);
   rows_:=rows_||jsonb_build_array(jsonb_build_object('record_type',g.ref->>'record_type','record',row_));
  end loop;
  if ecos_meta.content_hash(rows_) is distinct from boundary_->>'source_hash'
   or jsonb_array_length(rows_)<>(boundary_->>'record_count')::integer then raise exception 'stale_version' using errcode='40001'; end if;
  perform pg_advisory_xact_lock(hashtextextended('continuity:'||principal::text,0));
  select (r.result->'data'->>'package_id')::uuid into prior_ from ecos_meta.operation_receipt r
   join ecos.stage_result sr on sr.occurrence_id=(r.result->'data'->>'occurrence_id')::uuid
   where r.principal_id=principal and r.operation='continuity.checkpoint.commit'
   order by sr.created_at desc,sr.id desc limit 1;
  if prior_ is distinct from (boundary_->>'previous_package_id')::uuid then raise exception 'stale_version' using errcode='40001'; end if;
  bytes_:=decode(args->>'ciphertext','base64');
  if octet_length(bytes_)<16 or encode(sha256(bytes_),'hex')<>args->>'ciphertext_sha256'
   or args->>'verified_plaintext_sha256'<>encode(sha256(convert_to(ecos_meta.canonical_json(rows_),'UTF8')),'hex')
   or octet_length(decode(args->>'iv','base64'))<>12 then raise exception 'invalid_contract'; end if;
  id_:=(args->>'package_id')::uuid; artifact_:=gen_random_uuid();backup_:=gen_random_uuid();
  restore_:=gen_random_uuid();verify_:=gen_random_uuid();
  manifest_:=jsonb_build_object('schema_version','1.0.0','package_id',id_,'created_at',clock_timestamp(),
   'database_schema_version','1.0.0','migration_head',(select max(version)::text from ecos_meta.schema_migration),
   'postgresql_version',current_setting('server_version'),
   'tool_versions',jsonb_build_object('pg_dump','not_used_scoped_json_export','exporter','ecos-continuity-v1'),
   'files',jsonb_build_array(
    jsonb_build_object('path','records.aes-gcm','size_bytes',octet_length(bytes_),'sha256',args->>'ciphertext_sha256','record_count',jsonb_array_length(rows_),'role','data'),
    jsonb_build_object('path','restore.md','size_bytes',octet_length(restore_text),'sha256',encode(sha256(convert_to(restore_text,'UTF8')),'hex'),'record_count',null,'role','restore_instructions'),
    jsonb_build_object('path','verify.sql','size_bytes',octet_length(verify_text),'sha256',encode(sha256(convert_to(verify_text,'UTF8')),'hex'),'record_count',null,'role','verification_queries')),
   'memory_head_ids',coalesce((select jsonb_agg((x->'record'->>'active_head_version_id')::uuid) from jsonb_array_elements(rows_) x where x->>'record_type'='memory_record' and x->'record'->>'active_head_version_id' is not null),'[]'),
   'restore_instructions_path','restore.md','verification_queries_path','verify.sql',
   'secret_reference_names',jsonb_build_array('ecos.continuity.encryption'),
   'plaintext_secrets_included',false,'storage_control','darrell_controlled');
  perform ecos_meta.assert_contract('export_manifest',manifest_);
  insert into ecos.artifact(id,business_id,provider,provider_object_id,uri,content_hash,attachment_id)
   values(artifact_,'CONTINUITY-'||id_::text,'ecos.continuity',id_::text||'/records.aes-gcm',
    'data:application/octet-stream;base64,'||replace(encode(bytes_,'base64'),E'\n',''),args->>'ciphertext_sha256',null);
  insert into ecos.artifact(id,business_id,provider,provider_object_id,uri,content_hash,attachment_id) values
   (restore_,'CONTINUITY-RESTORE-'||id_::text,'ecos.continuity',id_::text||'/restore.md','data:text/plain;base64,'||replace(encode(convert_to(restore_text,'UTF8'),'base64'),E'\n',''),encode(sha256(convert_to(restore_text,'UTF8')),'hex'),null),
   (verify_,'CONTINUITY-VERIFY-'||id_::text,'ecos.continuity',id_::text||'/verify.sql','data:text/plain;base64,'||replace(encode(convert_to(verify_text,'UTF8'),'base64'),E'\n',''),encode(sha256(convert_to(verify_text,'UTF8')),'hex'),null);
  insert into ecos.export_package(id,manifest,content_hash) values(id_,manifest_,ecos_meta.content_hash(manifest_));
  insert into ecos.backup_record(id,kind,started_at,completed_at,artifact_uri,manifest_hash,encrypted,recovery_point_at,restore_test_id)
   values(backup_,'portable_ecos_export',(boundary_->>'observed_at')::timestamptz,clock_timestamp(),
    'ecos:export-package:'||id_::text,ecos_meta.content_hash(manifest_),true,(boundary_->>'observed_at')::timestamptz,null);
  perform ecos_meta.core_inherit(principal,c.occurrence_id,'artifact',artifact_);
  perform ecos_meta.core_inherit(principal,c.occurrence_id,'artifact',restore_);
  perform ecos_meta.core_inherit(principal,c.occurrence_id,'artifact',verify_);
  perform ecos_meta.core_inherit(principal,c.occurrence_id,'export_package',id_);
  perform ecos_meta.core_inherit(principal,c.occurrence_id,'backup_record',backup_);
  v:=jsonb_build_object('package_id',id_,'artifact_id',artifact_,'backup_id',backup_,
   'manifest_hash',ecos_meta.content_hash(manifest_),'source_hash',boundary_->>'source_hash',
   'occurrence_id',c.occurrence_id,'previous_package_id',prior_,'source_boundary',boundary_,
   'cipher','AES-256-GCM','compression','gzip','iv',args->'iv','verified_plaintext_sha256',args->>'verified_plaintext_sha256',
   'files',jsonb_build_object('records.aes-gcm',artifact_,'restore.md',restore_,'verify.sql',verify_));
 end if;
 return jsonb_build_object('schema_version','1.0.0','correlation_id',ctx->'correlation_id','status','committed','data',v);
end $$;
revoke all on all functions in schema ecos_meta from public;
reset role;

set local role ecos_owner;
insert into ecos_meta.contract_schema values('https://contracts.ecos.invalid/v1/runtime.evidence.read-request.schema.json','{"$schema":"https://json-schema.org/draft/2020-12/schema","$id":"https://contracts.ecos.invalid/v1/runtime.evidence.read-request.schema.json","type":"object","properties":{"schema_version":{"const":"1.0.0"},"context":{"$ref":"https://contracts.ecos.invalid/v1/request_context.schema.json"},"arguments":{"type":"object","properties":{"fence":{"$ref":"https://contracts.ecos.invalid/v1/fence.schema.json"},"communication_id":{"type":"string","format":"uuid"}},"required":["fence","communication_id"],"additionalProperties":false}},"required":["schema_version","context","arguments"],"additionalProperties":false}'::jsonb);
insert into ecos_meta.operation_contract values('runtime.evidence.read','{"name":"runtime.evidence.read","request_schema":"https://contracts.ecos.invalid/v1/runtime.evidence.read-request.schema.json","response_schema":"https://contracts.ecos.invalid/v1/phase2_result.schema.json","required_role":"executor","semantic_proposable":false,"idempotency_scope":"principal_id + operation + idempotency_key","atomicity":"single transaction"}'::jsonb);
insert into ecos_meta.contract_schema values('https://contracts.ecos.invalid/v1/continuity.snapshot-request.schema.json','{"$schema":"https://json-schema.org/draft/2020-12/schema","$id":"https://contracts.ecos.invalid/v1/continuity.snapshot-request.schema.json","type":"object","properties":{"schema_version":{"const":"1.0.0"},"context":{"$ref":"https://contracts.ecos.invalid/v1/request_context.schema.json"},"arguments":{"type":"object","properties":{"fence":{"$ref":"https://contracts.ecos.invalid/v1/fence.schema.json"}},"required":["fence"],"additionalProperties":false}},"required":["schema_version","context","arguments"],"additionalProperties":false}'::jsonb);
insert into ecos_meta.operation_contract values('continuity.snapshot','{"name":"continuity.snapshot","request_schema":"https://contracts.ecos.invalid/v1/continuity.snapshot-request.schema.json","response_schema":"https://contracts.ecos.invalid/v1/phase2_result.schema.json","required_role":"executor","semantic_proposable":false,"idempotency_scope":"principal_id + operation + idempotency_key","atomicity":"single transaction"}'::jsonb);
insert into ecos_meta.contract_schema values('https://contracts.ecos.invalid/v1/continuity.checkpoint.commit-request.schema.json','{"$schema":"https://json-schema.org/draft/2020-12/schema","$id":"https://contracts.ecos.invalid/v1/continuity.checkpoint.commit-request.schema.json","type":"object","properties":{"schema_version":{"const":"1.0.0"},"context":{"$ref":"https://contracts.ecos.invalid/v1/request_context.schema.json"},"arguments":{"type":"object","properties":{"fence":{"$ref":"https://contracts.ecos.invalid/v1/fence.schema.json"},"package_id":{"type":"string","format":"uuid"},"boundary":{"type":"object","properties":{"source_references":{"type":"array","minItems":0,"maxItems":10000,"items":{"$ref":"https://contracts.ecos.invalid/v1/source_reference.schema.json"}},"source_hash":{"type":"string","pattern":"^[a-f0-9]{64}$"},"previous_package_id":{"anyOf":[{"type":"string","format":"uuid"},{"type":"null"}]},"observed_at":{"type":"string","format":"date-time"},"record_count":{"type":"integer","minimum":0,"maximum":10000}},"required":["source_references","source_hash","previous_package_id","observed_at","record_count"],"additionalProperties":false},"ciphertext":{"type":"string","minLength":24,"maxLength":16000000},"ciphertext_sha256":{"type":"string","pattern":"^[a-f0-9]{64}$"},"verified_plaintext_sha256":{"type":"string","pattern":"^[a-f0-9]{64}$"},"iv":{"type":"string","minLength":16,"maxLength":16}},"required":["fence","package_id","boundary","ciphertext","ciphertext_sha256","verified_plaintext_sha256","iv"],"additionalProperties":false}},"required":["schema_version","context","arguments"],"additionalProperties":false}'::jsonb);
insert into ecos_meta.operation_contract values('continuity.checkpoint.commit','{"name":"continuity.checkpoint.commit","request_schema":"https://contracts.ecos.invalid/v1/continuity.checkpoint.commit-request.schema.json","response_schema":"https://contracts.ecos.invalid/v1/phase2_result.schema.json","required_role":"executor","semantic_proposable":false,"idempotency_scope":"principal_id + operation + idempotency_key","atomicity":"single transaction"}'::jsonb);
reset role;
