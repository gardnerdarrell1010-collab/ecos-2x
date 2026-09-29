-- Read-only plan probes; tiny synthetic data is not a throughput benchmark.
-- ready_work
explain (analyze,buffers,format json) select id from ecos.work_occurrence w where state in ('pending','ready','retry_wait','claimed','running') and (due_at<=now() or ready_override_at<=now()) and (retry_at is null or retry_at<=now()) and (ecos_meta.selection(w.id,'00000000-0000-0000-0000-000000000000',now())->>'eligible')::boolean order by due_at,created_at,id limit 1;
-- capability
explain (analyze,buffers,format json) select * from ecos.executor_capability where executor_instance_id='00000000-0000-0000-0000-000000000000' and capability_name='db.governed_operations' and capability_version>=1 and expires_at>now();
-- dependency
explain (analyze,buffers,format json) select d.occurrence_id from ecos.work_dependency d where d.occurrence_id='00000000-0000-0000-0000-000000000000' and not exists(select 1 from ecos.stage_result r where r.occurrence_id=d.prerequisite_occurrence_id and r.result_schema_id=d.required_result_schema_id);
-- live_claim
explain (analyze,buffers,format json) select id from ecos.work_claim where occurrence_id='00000000-0000-0000-0000-000000000000' and state='active' and expires_at>now();
-- outbox
explain (analyze,buffers,format json) select id from ecos.outbox_item where available_at<=now() and (state in ('pending','retry_wait') or (state='claimed' and lease_expires_at<=now())) order by available_at,id limit 1;
-- heartbeat
explain (analyze,buffers,format json) select executor_instance_id from ecos.heartbeat where valid_until<=now();
-- memory_head
explain (analyze,buffers,format json) select v.* from ecos.memory_record m join ecos.memory_version v on v.id=m.active_head_version_id where m.scope_id='00000000-0000-0000-0000-000000000000' and m.memory_kind='continuity';
