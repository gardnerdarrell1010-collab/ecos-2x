-- Read-only Phase 1 acceptance queries; tables do not exist in Phase 0.
-- Each query must return zero rows after implementation and test injection/recovery.
select occurrence_id, stage_definition_id
from ecos.work_claim where state = 'active'
group by occurrence_id, stage_definition_id having count(*) > 1;

select c.id from ecos.work_claim c
left join ecos.execution_run r on r.claim_id = c.id
where r.id is null;

select id from ecos.task
where (lifecycle_state = 'waiting') <> (wait_reason <> 'none');

select r.id from ecos.memory_record r
join ecos.memory_version v on v.id = r.active_head_version_id
where v.memory_record_id <> r.id or v.scope_id <> r.scope_id;
