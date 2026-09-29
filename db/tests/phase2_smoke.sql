-- Explicit Phase 2 synthetic smoke; every record and temporary role grant rolls back.
begin;
set local timezone='UTC';
set local plpgsql.check_asserts=on;
set local statement_timeout='45s';
do $$ begin execute format('grant operations_api,executor,provider_adapter to %I',current_user); end $$;
do $$
declare p uuid:=gen_random_uuid(); inst uuid:=gen_random_uuid(); ex uuid:=gen_random_uuid(); tid uuid:=gen_random_uuid(); tid2 uuid:=gen_random_uuid(); party uuid:=gen_random_uuid(); retry uuid:=gen_random_uuid(); def uuid:=gen_random_uuid(); stage uuid:=gen_random_uuid(); oid uuid:=gen_random_uuid(); ctx jsonb; req jsonb; r jsonb; f jsonb; claim_ jsonb; result_ jsonb; checks jsonb:='[]';
begin
 insert into ecos.party values(party,'SYNTHETIC-PARTY-'||party,'Synthetic recipient',1);
 insert into ecos.task(id,business_id,title,project_id,lifecycle_state,wait_reason,description) values(tid,'SYNTHETIC-TASK-'||tid,'Synthetic obligation',null,'open','none','Fixture'),(tid2,'SYNTHETIC-TASK-'||tid2,'Synthetic sibling',null,'open','none','Fixture');
 insert into ecos.executor(id,name,surface,enabled) values(ex,'synthetic_executor','DATABASE_DETERMINISTIC',true);
 insert into ecos.executor_instance(id,executor_id,boot_id,availability,principal_id) values(inst,ex,gen_random_uuid(),'available',p);
 insert into ecos_meta.principal_binding values('operations_api',p,inst,true),('executor',p,inst,true),('provider_adapter',p,inst,true);
 insert into ecos_meta.principal_operation select p,name from ecos_meta.operation_contract;
 insert into ecos_meta.object_grant values(p,'task',tid),(p,'task',tid2);

 insert into ecos.retry_policy(id,max_attempts,initial_delay_seconds,max_delay_seconds,backoff_multiplier,jitter_basis_points,retryable_error_classes) values(retry,3,1,30,2,0,'["transient"]');
 insert into ecos.work_definition(id,name,definition_version,enabled,fulfillment_kind,retry_policy_id) values(def,'phase2_smoke',1,true,'staged',retry);
 insert into ecos.work_stage_definition(id,work_definition_id,stage_key,kind,execution_surface,input_schema_id,result_schema_id,requires_approval) values(stage,def,'smoke','deterministic','DATABASE_DETERMINISTIC','synthetic.input.v1','synthetic.result.v1',false);
 insert into ecos.stage_capability_requirement(stage_definition_id,capability_name,minimum_version) values(stage,'db.governed_operations',1);
 insert into ecos.executor_capability(executor_instance_id,capability_name,capability_version,attested_by,expires_at) values(inst,'db.governed_operations',1,p,clock_timestamp()+interval '1 hour');
 insert into ecos.work_occurrence(id,work_definition_id,stage_definition_id,fulfillment_id,task_id,state,occurrence_key,due_at) values(oid,def,stage,gen_random_uuid(),tid,'ready','SYNTHETIC-PHASE2-'||oid,clock_timestamp()-interval '1 second');
 insert into ecos_meta.object_grant values(p,'work_occurrence',oid);
 insert into ecos.work_context(occurrence_id,operation,input) values(oid,'work.complete','{"synthetic":true}');
 ctx:=jsonb_build_object('principal_id',p,'executor_instance_id',inst,'correlation_id',gen_random_uuid(),'causation_id',null,'idempotency_key','register');
 req:=jsonb_build_object('schema_version','1.0.0','context',ctx,'arguments',jsonb_build_object('host','SYNTHETIC-HOST','runtime','smoke','software_version','phase2','evidence_hash',repeat('a',64)));
 perform set_config('role','executor',true);r:=ecos.operate('executor.register',req);perform set_config('role','postgres',true);assert r->>'status'='committed',r::text;checks:=checks||'"register"';
 req:=jsonb_build_object('schema_version','1.0.0','context',ctx||'{"idempotency_key":"next"}','arguments',jsonb_build_object('executor_instance_id',inst,'lease_seconds',120));
 perform set_config('role','executor',true);r:=ecos.operate('work.next',req);perform set_config('role','postgres',true);assert r->>'status'='CLAIMED',r::text;claim_:=r;f:=r->'data'->'work_package'->'fence';assert r->'data'->'claim'->>'occurrence_id'=oid::text;checks:=checks||'"next_package_claim"';
 req:=jsonb_build_object('schema_version','1.0.0','context',ctx||'{"idempotency_key":"renew"}','arguments',jsonb_build_object('fence',f,'lease_seconds',120));
 perform set_config('role','executor',true);r:=ecos.operate('work.renew',req);perform set_config('role','postgres',true);assert not r ? 'code',r::text;checks:=checks||'"renew"';
 result_:=jsonb_build_object('id',gen_random_uuid(),'schema_version','1.0.0','created_at',clock_timestamp(),'occurrence_id',oid,'stage_definition_id',stage,'execution_run_id',claim_->'data'->'execution_run'->'id','result_schema_id','synthetic.result.v1','content_hash',repeat('b',64),'artifact_uri','synthetic:phase2-smoke','verified_at',clock_timestamp(),'verified_by',p,'source_references','[]'::jsonb);
 req:=jsonb_build_object('schema_version','1.0.0','context',ctx||'{"idempotency_key":"complete"}','arguments',jsonb_build_object('fence',f,'result',result_));
 perform set_config('role','executor',true);r:=ecos.operate('work.complete',req);perform set_config('role','postgres',true);assert r->>'status'='committed',r::text;assert (select state='succeeded' from ecos.work_occurrence where id=oid);checks:=checks||'"complete_readback"';
 perform set_config('ecos.phase2_smoke',checks::text,true);
end $$;
select current_setting('ecos.phase2_smoke')::jsonb as passed_checks;
rollback;
