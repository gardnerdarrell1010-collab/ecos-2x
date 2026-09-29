# Canonical relational specification

`db/schemas/model.json` indexes the versioned JSON entity contracts. They define complete
wire fields/types; these are Phase 1 SQL targets, not existing tables. Physical SQL may
flatten nested wire objects (notably execution_run.fence into claim_id/occurrence_id,
stage_definition_id, claim_version, fence_token and executor_instance_id). The operation
adapter must prove lossless mapping. No arbitrary table mutation API is permitted.

| Relation | Relationships and uniqueness/invariants |
|---|---|
| task | nullable project_id -> project; unique business_id; lifecycle/wait reason coherent; no claims/rank/attempts |
| task_assignment | task_id -> task, party_id -> party; non-overlapping active owner intervals per task/role |
| task_schedule | task_id -> task; versioned timezone/recurrence, due/follow-up/planned start; occurrence uniqueness prevents DST duplicates |
| task_dependency | both endpoints -> task; unique pair; no self edge or cycles, including concurrent edge insertion |
| approval_request | typed subject + immutable subject_hash; pending until explicit decision; expiry uses database time |
| approval_decision | approval_request_id -> request; append-only actor/evidence, supersedes pointer; approved subject/version must still match |
| task_evidence | task_id -> task; immutable typed source reference/hash |
| work_definition | immutable published definition version; enabled flag controls new occurrences |
| work_stage_definition | definition FK; unique definition/stage_key; stage kind and one execution surface; capability requirements by data |
| work_occurrence | definition/stage FKs agree; nullable task; fulfillment_id groups stages of one obligation; unique occurrence key; runtime only here |
| work_dependency | occurrence FKs, no self/cycle; verified immutable prerequisite result/schema/hash required |
| work_claim | occurrence/stage agree; instance FK; at most one active per occurrence/stage, explicitly close expired before replacement |
| execution_run | claim FK + occurrence/stage/instance fence projection; one run per acquired claim; started event freezes selection evidence |
| execution_event | run FK + constrained versioned payload; immutable causal event ledger |
| stage_result | occurrence/stage/run FKs agree; immutable schema/hash/verified evidence; one accepted result per stage occurrence |
| retry_policy | bounded attempt/backoff/jitter; unknown side effects never qualify for blind retry |
| dead_letter_item | occurrence and last_run FKs; reason + owner review; replay requires new governed authorization |
| executor / executor_instance | definition -> boots; new boot UUID each restart; stale boot cannot inherit a fence |
| capability / executor_capability | unique name/version; attested instance binding expires; grants are server-governed |
| stage_capability_requirement | stage FK and capability FK/version; all requirements must match current attestations |
| heartbeat | immutable server receipt + observed timestamp/boot; availability is derived, not self-asserted permission |
| domain_event / outbox_item | event immutable; outbox FK event and optional command; unique destination/idempotency key; same business transaction |
| provider_command | unique provider/account/type/key; immutable intent/hash even when outcome projection changes |
| provider_attempt / provider_result | command FK; unique command/attempt_number; result points to same command and attempt; immutable evidence |
| provider_receipt | unique provider/account/dedupe_key; provider event ID preferred; raw bytes/hash retained; signature before trusted normalization |
| communication | receipt FK; business thread/content reference; exact normalized body provenance |
| communication_processing | communication/occurrence/proposal FKs; unique communication/source_version/processor contract version |
| notification / delivery | delivery FK notification; unique notification/recipient/channel/policy_key; approval binds exact content/destination |
| delivery_attempt | delivery/provider_attempt FKs agree with command; append-only provider response evidence |
| memory_scope | unique scope_type/scope_id; role/sensitivity boundaries govern retrieval |
| memory_record | scope FK, unique scope/memory_kind; active_head_version_id points to same record/scope |
| memory_version | record/scope FKs; unique record/version_number; immutable, explicit supersedes chain with no cycle |
| memory_reference | version FK + authoritative source version/hash; never promotes chat evidence above structured authority |
| memory_compaction_run | immutable input/output manifest and verification; output version references same scope |
| raw_migration_batch / quarantine_item | immutable raw bytes; batch FK/source locator unique; typed state before reconciliation/promotion |
| legacy_identity | target UUID + immutable source locator/resolution evidence; legacy strings may repeat |
| backup_record / export_package / restore_test | manifest-hashed inventory and restore evidence; usable backup requires passed restore record |

Party/person/organization/project/artifact/fact and forecast/publication objects referenced
by the model are named Phase 1 or later targets in the mapping/worker registries. They are
not secretly implemented by Phase 0. Phase 1 must create concrete target tables and foreign
keys before accepting API operations using those references.

A task is an obligation, including independent tasks without a project. One fulfillment
can have human review -> semantic proposal -> deterministic commit -> provider transport
-> approval/evidence stages. Each executable stage gets an occurrence and bounded claim;
human/approval waits do not hold a lease across days. HYBRID is the staged DAG, never an
executor surface or a duplicate business task. Completion requires verified terminal
stage evidence and business completion conditions, not simply the last executor's claim.

Transition policies live in `config/lifecycle-transitions.json`. A listed edge is necessary
but not sufficient: approval, evidence, authorization, dependencies and fences still apply.
Terminal task reopen is an explicit governed transition with reason/event. Succeeded work
never reopens: new work needs a new occurrence linked to prior evidence. Claim recovery may
move running/claimed to retry_wait only after result/provider reconciliation. Approval
revocation appends a decision and recomputes the request projection; never edits old decisions.

Recurrence uses UTC instants plus IANA timezone, calendar or completion-relative anchor,
explicit DST gap/fold policy and unique occurrence key based on schedule version + logical
local occurrence. Schedule updates cancel/reconcile unfinished future occurrences under
lock; they cannot erase past completion. Dependency cycle checks require serialized graph
mutation or equivalent constraint strategy, not a race-prone read-before-insert check.
