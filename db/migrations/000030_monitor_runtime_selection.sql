CREATE OR REPLACE FUNCTION public.ecos_monitor_snapshot() RETURNS jsonb
LANGUAGE sql STABLE SECURITY DEFINER SET search_path=pg_catalog,ecos AS $$
SELECT jsonb_build_object(
'schema_version','2.0.monitor.1','generated_at',statement_timestamp(),
'source','ECOS 2.x PostgreSQL','authority','POSTGRESQL_2X',
'executors',COALESCE((SELECT jsonb_agg(jsonb_build_object(
'executor_name',e.name,'surface',e.surface,'executor_enabled',e.enabled,
'executor_instance_id',i.id,'availability',i.availability,
'presence',(SELECT jsonb_build_object('host',p.host,'runtime',p.runtime,'software_version',p.software_version,'started_at',p.started_at,'stopped_at',p.stopped_at,'status',p.status) FROM ecos.executor_presence p WHERE p.executor_instance_id=i.id),
'heartbeat',(SELECT jsonb_build_object('observed_at',h.observed_at,'valid_until',h.valid_until,'availability',h.availability) FROM ecos.heartbeat h WHERE h.executor_instance_id=i.id ORDER BY h.observed_at DESC LIMIT 1)))
FROM ecos.executor e JOIN ecos.executor_instance i ON i.executor_id=e.id
WHERE EXISTS (SELECT 1 FROM ecos.executor_presence live_presence WHERE live_presence.executor_instance_id=i.id AND live_presence.runtime IN ('online-ada-2x','resident-ada-2x') AND live_presence.stopped_at IS NULL)), '[]'::jsonb),
'active_claims',COALESCE((SELECT jsonb_agg(to_jsonb(c)) FROM (SELECT id,occurrence_id,executor_instance_id,claim_version,state,acquired_at,expires_at FROM ecos.work_claim WHERE state='active' ORDER BY acquired_at DESC LIMIT 30)c),'[]'::jsonb),
'queue',COALESCE((SELECT jsonb_agg(to_jsonb(q)) FROM (SELECT o.id,o.occurrence_key,o.state,o.due_at,o.retry_at,o.attempt_count,o.claim_version,jsonb_build_object('name',d.name) as work_definition,jsonb_build_object('stage_key',s.stage_key,'execution_surface',s.execution_surface) as work_stage_definition FROM ecos.work_occurrence o JOIN ecos.work_definition d ON d.id=o.work_definition_id JOIN ecos.work_stage_definition s ON s.id=o.stage_definition_id WHERE o.state IN ('ready','claimed','running','retry_wait') ORDER BY o.due_at LIMIT 50)q),'[]'::jsonb),
'recent_runs',COALESCE((SELECT jsonb_agg(to_jsonb(r)) FROM (SELECT id,state,created_at,ended_at,occurrence_id,executor_instance_id FROM ecos.execution_run ORDER BY created_at DESC LIMIT 20)r),'[]'::jsonb));
$$;
REVOKE ALL ON FUNCTION public.ecos_monitor_snapshot() FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.ecos_monitor_snapshot() TO service_role;

