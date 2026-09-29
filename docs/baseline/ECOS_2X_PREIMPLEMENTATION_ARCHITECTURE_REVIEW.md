# ECOS 2.x Pre-Implementation Architecture & Build Plan

**Review date:** 2026-09-28  
**Assignment:** Read-only architecture/design review  
**Current production authority:** ECOS 1.x, Google Sheets spreadsheet `1LF0isNKZBgEbr8E_pzekSWJ8-iXGfGn3e3xteKuivu0`  
**Target:** Portable PostgreSQL architecture, initially hosted on Supabase  
**Cutover rule:** No dual-master state. ECOS 1.x remains authoritative until a separately approved cutover.

## Executive decision

ECOS is not a spreadsheet, a collection of prompts, or a Task Loop. It is a governed personal/business operating system that:

1. records obligations, projects, parties, evidence, communications, decisions, facts, approvals, schedules, and continuity;
2. turns provider evidence and human direction into governed obligations and work;
3. selects executable work, assigns it to a capable executor, proves ownership, records effects, and recovers after interruption;
4. separates semantic judgment from deterministic state transition and provider transport;
5. publishes operational views, briefings, forecasts, notifications, and files;
6. preserves auditable state and enough semantic continuity for a replacement AI to resume safely;
7. detects degraded execution and routes recovery or owner attention.

The best ECOS 2.x architecture is a **modular PostgreSQL monolith with a small executor/adapter plane**, not a spreadsheet port and not a microservice estate. PostgreSQL owns authoritative operational state, invariants, readiness, claims, schedules, dependencies, approvals, audit, outbox, and deterministic reconciliation. External executors own semantic reasoning, provider calls, local-machine operations, and rendering. All executors use the same governed operations contract.

The current provisional strategy is directionally correct, but it understates four requirements:

- an independent watchdog outside both Ada and the primary database host;
- explicit provider-side reconciliation for the `provider succeeded / database acknowledgement failed` window;
- first-class schema/version contracts for work packages and semantic outputs;
- a cutover data-quality gate, because live 1.x contains duplicate identifiers, column drift, and uncontrolled lifecycle vocabularies that must not be imported as clean state.

## Authoritative review basis

The review fresh-read the active System Bootstrap first, then the current Sheet Registry, Command Registry, Data Dictionary, Validation Lists, Settings, Workflow Dependencies, Tasks, Projects, Contacts, Organizations, Relationships, Communications, Notification Queue, Notification Deliveries, Artifacts, Authoritative Files, Facts, Task Loop, Run Control, Exceptions, Integrity Checks, Ingestion State, Staging Records, Forecast Performance, Forecast Data Audit, AI Memory, Recovery Map, Ingestion Log, and Activity Log.

The active bootstrap is `BOOTSTRAP-PRIMARY`, schema `ECOS-2026-08-03-APPROVAL1`, memory version `AI-MEMORY-3`. `MEM-ECOS-000036` is active at Rolling Version 94. Structured current records were treated as stronger authority than continuity text.

### Live-state findings that materially affect 2.x

The following are evidence, not inferred design preferences:

| Finding | Live evidence | 2.x consequence |
|---|---:|---|
| Worker inventory | 55 populated Task Loop records, including `TASK-AUTO-000029-B`, A053, and A054 | Worker-by-worker disposition is required; IDs are migration aliases, not future architecture boundaries. |
| Task model overload | Tasks has 80 columns mixing obligation, scoring, schedule, recurrence, approval, claim, execution, and audit | Normalize obligation from executable work and occurrences. |
| Populated Tasks | 641 keyed records | Migrate business obligations selectively; rebuild runtime columns. |
| Run history bloat | 31,572 keyed Run Control rows | Retain curated historical evidence; do not import all launcher/runtime noise into the hot operational schema. |
| Duplicate identifiers | 115 duplicate Run IDs; duplicates also observed in Notification Queue, Notification Deliveries, and Staging Records | Quarantine duplicates and resolve identity before enforced unique constraints and cutover. |
| Lifecycle vocabulary explosion | Hundreds of distinct free-text Run Control statuses | Replace with small enums plus structured reason codes and append-only events. |
| Apparent column drift | Task rows contain values in fields inconsistent with the field contract; Run Control also shows shifted narrative values | Use a typed quarantine importer; never direct-copy rows into target tables. |
| Communications | 184 keyed Communications: 127 Processed, 36 Retry, 21 Pending | Keep provider evidence and processing lifecycle, but split immutable receipt from processing attempts. |
| Notifications | 353 keyed notifications and 528 deliveries, with duplicate IDs and many compound statuses | Normalize Notification, Delivery, and Delivery Attempt; make retry state structural. |
| Forecast Performance | schema exists but zero populated rows in the fresh read | Treat forecast accountability as a required new operational capability, not a completed migration. |
| Repeated executor-local persistence failures | Current Tasks, worker notes, Exceptions, and Rolling Version 94 repeatedly report writes rejected before Google Sheets | A principal 2.x acceptance test is reliable transactional persistence from both Online Ada and HOME-01. |
| Integrity false confidence | A008 has reported verified integrity while end-to-end chains remained blocked | Integrity must assert business invariants and flow freshness, not only sheet/worker completion. |

## Architecture principles

1. **One authority:** exactly one authoritative writer for each business fact at a time.
2. **Database invariants before agent instructions:** use types, constraints, foreign keys, exclusion constraints, and procedures.
3. **No network calls inside business transactions:** commit state and outbox atomically; perform provider calls afterward.
4. **Idempotency is designed, not hoped for:** every externally consequential command has a stable idempotency key and reconciliation strategy.
5. **Claims are leases, not truth:** ownership expires; verified stage evidence survives.
6. **Business Tasks are not routing records:** a Task expresses an obligation; work stages express how it is fulfilled.
7. **Semantic judgment produces proposals/evidence:** deterministic procedures validate and commit governed effects.
8. **Portable core:** PostgreSQL DDL, SQL functions, migrations, and OpenAPI/JSON Schema contracts are canonical. Supabase features are replaceable adapters.
9. **Hot state stays lean:** verbose telemetry and reconstructable provider payloads have bounded retention or archive policies.
10. **Independent verification:** completion requires evidence separate from the executor's assertion.

## Target topology

```text
Interactive Ada / Online Ada / Resident Ada / deterministic services
                         |
              ECOS Operations API / MCP
                         |
       PostgreSQL transaction + governed procedures
       |                 |                    |
 business state      audit/events        durable outbox
                                              |
                                  dispatcher / adapter workers
                                  | Gmail | Twilio | Toast
                                  | Drive | Vercel | local render
                                              |
                                     provider result + evidence

Independent DB-host watchdog  ---> direct emergency alert path
External uptime watchdog      ---> monitors DB/API/watchdog itself
```

Deploy initially as one PostgreSQL database, one operations API, one generic dispatcher, one semantic executor interface, and a small set of provider/local adapters. Do not create a service per worker.

## Execution-surface allocation

### DATABASE_DETERMINISTIC

Own:

- identifiers, foreign keys, state transitions, approvals, dependency readiness, schedules, recurrence expansion;
- query-time scoring, atomic claiming, lease expiry, retry eligibility, dead-letter transitions;
- notification/delivery creation, durable outbox creation, deduplication, audit events;
- SLA/aging calculations, integrity assertions, deterministic repairs, aggregate facts and materialized views;
- transactionally committing semantic proposals after validation;
- backup/export manifests and restore-verification records.

Use triggers only for local, bounded invariant/audit/outbox work. Do not put HTTP calls, AI calls, rendering, or broad reconciliation in triggers.

### RESIDENT_DETERMINISTIC_PROVIDER

Own:

- local filesystem/process execution and canonical file materialization;
- transports or provider capabilities available only on HOME-01;
- authenticated provider calls intentionally placed on the resident host;
- exact-byte/hash readback for local or Drive materialization;
- adapter reconciliation when provider APIs require local credentials/capabilities.

### ONLINE_SEMANTIC

Own:

- interpretation, classification, drafting, planning, qualitative reconciliation, forecast explanation, and semantic memory compaction;
- structured proposals conforming to versioned schemas;
- no direct mutation outside governed operations.

### INTERACTIVE_ADA

Uses the same operations API, commands, proposal schemas, approvals, and audit as autonomous Ada. Interactive work may have human-presence authorization, but it does not bypass invariants or create a second authority model.

### HYBRID

Use only as a staged workflow: for example provider receipt -> semantic interpretation -> deterministic commit -> provider response. Each stage has its own occurrence, evidence, and capability set. Never use one long cross-surface claim.

## Normalized domain model

### Business core

- `party`, `person`, `organization`, `party_identifier`, `party_relationship`
- `project`
- `task` — one actionable business obligation; `project_id` nullable
- `task_assignment` — owner, delegate, role, effective interval
- `task_schedule` — due, follow-up, planned start, recurrence specification
- `task_dependency` — task-to-task business prerequisite
- `approval_request`, `approval_decision`
- `task_evidence` — links to communications, artifacts, facts, provider evidence
- `fact`, `decision`, `risk`

Do not store worker claims, recurrence runtime, or attempt counters on `task`.

### Work/execution core

- `work_definition` — reusable capability or task fulfillment plan
- `work_stage_definition` — ordered/DAG stage with owner surface and required capabilities
- `work_occurrence` — one due/event-triggered unit of executable work
- `work_dependency` — occurrence/stage prerequisite and verified-output rules
- `work_claim` — lease/fence token; one live claim per occurrence/stage
- `execution_run` — bounded executor attempt
- `execution_event` — append-only structured lifecycle evidence
- `stage_result` — immutable output/evidence with schema version and content hash
- `retry_policy`, `dead_letter_item`

A business Task may reference one fulfillment plan whose stages include human work, Ada semantic work, deterministic database work, Resident work, and approval. No duplicate business Tasks are created merely to route those stages.

### Evidence and communications

- `artifact` and `artifact_version`; binaries remain in Drive/object storage, with URI, provider ID, hash, size, and provenance in PostgreSQL
- `provider_receipt` — immutable inbound provider envelope and exact evidence/hash
- `communication` — business-level normalized communication/thread relationship
- `communication_processing` — semantic/deterministic processing state and attempts
- `notification` — why/what should be communicated
- `delivery` — recipient/channel/destination intent
- `delivery_attempt` — each provider attempt and exact response evidence
- `provider_command` — stable idempotent external-side-effect command

### Memory and recovery

- `memory_record`, `memory_version`, `memory_scope`, `memory_reference`, `memory_compaction_run`
- `backup_record`, `export_package`, `restore_test`, `continuity_checkpoint`

AI semantic continuity, database backup, and portable export are separate subsystems.

## Task state model

Use small orthogonal states rather than compound strings:

- `task.lifecycle_state`: draft, open, waiting, completed, cancelled
- `task.wait_reason`: dependency, owner, external, approval, scheduled, none
- `approval_request.state`: pending, approved, rejected, changes_requested, expired
- `work_occurrence.state`: pending, ready, claimed, running, succeeded, retry_wait, failed, dead_lettered, cancelled
- `delivery.state`: planned, ready, held, sending, delivered, failed, acknowledged, cancelled

Narrative detail belongs in reason codes and append-only events. Enforce legal transitions with procedures such as `task_transition(...)`, `claim_work(...)`, `complete_stage(...)`, and `record_delivery_result(...)`.

## Selection, scoring, and claims

Do not migrate continuously rewritten Dispatch Rank.

Candidate selection is a database query over authoritative inputs:

```text
enabled definition
AND due occurrence
AND not terminal
AND retry_at <= now
AND explicit dependencies satisfied
AND required capabilities <@ executor capabilities
AND no unexpired claim
ORDER BY owner_run_now DESC,
         sla_breach DESC,
         deadline_pressure DESC,
         business_impact DESC,
         recurrence_relative_age DESC,
         created_at ASC
```

`RUN NOW` survives as two fields with distinct meaning:

- `ready_override_at`: makes the occurrence immediately ready;
- `priority_override`: bounded owner priority, with actor, reason, and expiry.

It does not bypass dependencies, approvals, capability requirements, maintenance, or idempotency gates.

Atomic claim pattern:

```sql
with candidate as (
  select wo.id
  from work_occurrence wo
  join work_stage_definition ws on ws.id = wo.stage_definition_id
  where ecos.is_claimable(wo.id, :executor_id, now())
  order by ecos.effective_priority(wo.id, now()) desc, wo.id
  for update skip locked
  limit 1
)
update work_occurrence wo
set state = 'claimed', claim_version = claim_version + 1
from candidate c
where wo.id = c.id
returning wo.id, wo.claim_version;
```

Insert `work_claim` and `execution_run` in the same transaction. Require `(occurrence_id, stage_id)` to have at most one live claim via a partial unique index. Every state-changing completion procedure checks occurrence ID, claim version, executor ID, and unexpired fence.

Recovery proof:

- two executors cannot own the same stage because the row lock and unique live-claim constraint serialize winners;
- dead executors lose only the lease, not stage evidence;
- a recovery sweep transitions expired claims to retryable only after examining stage results and provider commands;
- completed stage results are immutable and content-addressed;
- a capability mismatch excludes only that executor/occurrence pair;
- a HYBRID handoff creates the next stage occurrence after the prior stage result commits.

Snapshot the selected score components and explanation in the immutable `execution_run` start event. Do not persist rank as mutable task state.

## Event, outbox, and provider-command model

Use relational event tables, not a generic untyped bus:

- `domain_event`: durable fact that a governed business transition occurred;
- `outbox_item`: delivery work created in the same transaction as the transition;
- `provider_command`: externally consequential intent with stable idempotency key;
- `provider_attempt`: request/response timing, hash, status, error class;
- `provider_result`: normalized verified result and provider ID;
- `execution_event`: executor lifecycle evidence.

All payloads have `event_type`, `schema_version`, `aggregate_type`, `aggregate_id`, `correlation_id`, `causation_id`, and a constrained JSON payload validated at the API boundary.

### Failure proof

**DB commit succeeds; consumer never executes:** the committed outbox row remains `pending`; a dispatcher uses `FOR UPDATE SKIP LOCKED`; leases expire; recovery sweeps retry. `LISTEN/NOTIFY` or Supabase Realtime is only a latency hint. Correctness comes from the durable row and periodic sweep.

**Provider succeeds; result persistence fails:** never blindly resend. Before retry, reconcile using the provider idempotency key, provider request ID, message SID, Gmail draft/message identity, Drive file ID/version/hash, or a provider query bounded by correlation metadata. Persist an `unknown_outcome` state when the provider cannot prove either result; require reconciliation or human decision for non-idempotent effects.

Use exponential backoff with jitter, explicit retryability classes, maximum attempts, and dead-letter review. Provider 4xx validation failures are not transient retries.

## Trigger and latency policy

| Function | Trigger | Target latency | Mechanism |
|---|---|---:|---|
| invariant/state transition | synchronous transaction | synchronous | constraint/procedure |
| readiness/dependency release | committed state change | sub-second | procedure inserts occurrence/outbox; NOTIFY hint |
| provider transport | committed delivery/provider command | <5 seconds | dispatcher/queue consumer |
| inbound webhook | provider webhook | <5 seconds | durable receipt first, then process |
| semantic processing | committed semantic work item | <1 minute | generic semantic executor |
| fixed business schedule | schedule threshold | <1 minute from due | portable scheduler table + dispatcher; `pg_cron` may wake |
| SLA/follow-up detection | deadline threshold | <1 minute | indexed scheduled query |
| reconciliation/recovery | periodic sweep | 1–5 minutes or scheduled | database job/worker |
| heavy aggregates | source commit or scheduled | seconds/minutes | incremental SQL/materialized view refresh |

Prefer a portable scheduler table and worker. `pg_cron` may invoke a wake-up procedure. Supabase Database Webhooks, Edge Functions, and Realtime are replaceable accelerators, not correctness dependencies. `LISTEN/NOTIFY` is never the only delivery mechanism.

## Communications architecture

### Inbound

```text
provider webhook/poll delta
-> immutable provider_receipt (commit and dedupe)
-> deterministic normalization
-> semantic work occurrence only when judgment is required
-> validated business transaction
-> task/fact/notification/downstream event
```

Preserve exact provider text, headers/metadata needed for proof, provider IDs, timestamps, and hashes. Large/raw blobs may remain at the provider or artifact store if a stable, auditable reference and hash are retained.

### Outbound

```text
business transaction
-> notification
-> one or more deliveries
-> provider_command + outbox
-> deterministic transport
-> delivery_attempt/provider ID
-> verified delivery result/status webhook
```

A010, A027, and A028 collapse into this shared delivery pipeline. Channel adapters remain distinct, but queues and dispatcher semantics do not. Transport should normally start within five seconds of a committed actionable Delivery. Draft-first Gmail approval remains a policy expressed as a delivery hold/approval prerequisite, not prompt-only behavior.

## AI memory and continuity

AI Memory remains a first-class governed capability.

`memory_record` identifies stable scope and purpose. `memory_version` is immutable and contains statement, operational meaning, provenance, effective interval, sensitivity, retention class, authoritative references, and content hash. A unique constraint permits only one active head per `(scope_type, scope_id, memory_kind)`. Supersession is explicit.

Rolling continuity becomes a compaction product:

1. read current structured authority;
2. select applicable prior memory versions;
3. capture only residual semantic context not represented in stronger records;
4. produce a new version with references and a compaction manifest;
5. validate token/size, provenance, contradictions, and retrieval tests;
6. activate new head and supersede prior head atomically.

Bootstrap retrieval is deterministic by executor, user, domain, task, and sensitivity. A replacement AI receives an `ECOS Bootstrap Package` containing schema/version, current governed context, applicable memory heads, operation schemas, capability vocabulary, and unresolved exceptions. Conversation history is optional evidence, never authority.

## Backup, disaster recovery, and portable export

### A. Managed database recovery

- production managed backups and PITR sized to approved RPO/RTO;
- encrypted storage, least-privilege restore roles, and restore audit;
- documented Supabase-specific steps isolated from provider-neutral recovery steps.

### B. Independent logical backup

- scheduled `pg_dump` in custom format plus a globals/roles reconstruction script without secrets;
- encrypted copy on Darrell-controlled local storage and a second off-provider location;
- retention proposal: daily 35 days, monthly 13 months, annual 7 years, subject to legal/business approval;
- manifests with SHA-256, sizes, database/schema versions, migration head, export time, and tool versions.

### C. Portable ECOS system export

Package:

- migration source and schema dump;
- data dump or ordered table exports;
- functions, procedures, triggers, views, materialized-view definitions;
- controlled configuration, capability definitions, executor contracts, JSON Schemas/OpenAPI;
- active AI Memory and continuity state;
- provider/artifact reference inventory;
- restore runbook, dependency versions, verification queries, checksums, and manifest;
- secret reference names and rotation/recovery instructions, never plaintext secrets.

Quarterly, restore into a clean standard PostgreSQL instance outside the live Supabase project, run migrations and verification, exercise the operations API, claim/complete a synthetic occurrence, rebuild materializations, and compare manifest counts/hashes. A backup is valid only after a recorded restore test.

Target initial objectives: operational RPO <= 15 minutes with PITR, logical-export RPO <= 24 hours, and rehearsed RTO <= 4 hours. Confirm cost and business tolerance before production.

## Security and portability

- PostgreSQL roles: `ecos_owner`, `migration_runner`, `operations_api`, `executor`, `provider_adapter`, `auditor`, `backup_operator`, `read_only_analytics`.
- Executors never receive table-owner credentials. They invoke allow-listed operations.
- Use row-level security only where it adds a genuine tenant/sensitivity boundary; do not substitute RLS for API authorization.
- Provider secrets live in an external secret manager or platform function secrets. Tables contain secret references and rotation metadata only.
- Every call carries actor, executor, correlation ID, capability attestation, and request idempotency key.
- Canonical contracts: SQL migrations, OpenAPI, JSON Schema, and conformance tests in source control.
- Supabase Auth, Realtime, Edge Functions, Vault, and webhooks must have documented replacements. The core system must restore on standard supported PostgreSQL plus a conventional API/worker runtime.

## Integrity and watchdogs

Replace A008/A009's sheet-centric checks with three layers:

1. **continuous invariants:** constraints, uniqueness, FK, transition procedures;
2. **flow health:** no ready occurrence stranded past SLA, outbox lag, dead-letter count, stale heartbeats, provider receipt backlog, unacknowledged unknown outcomes;
3. **semantic audits:** contradictions, unsupported conclusions, stale narrative, and evidence quality.

Database-host watchdog: a minimal scheduled check independent of normal Ada and notification processing monitors critical heartbeats and queues and can call a separate emergency SMS/email function. External watchdog: monitors database/API/watchdog availability from outside Supabase. Test both by deliberately withholding a heartbeat and proving a real alert.

## Reporting, dashboards, and forecasting

System Status A037–A043 should become SQL views/materialized views plus one publication/materialization stage. Life & Business A045–A051 should become typed source snapshots and SQL health/aggregation, retaining semantic producers only for executive interpretation and forecasts. A044/A052 remain deterministic renderers.

Forecast architecture:

- ingest normalized half-hour Toast facts once;
- keep source exports in Drive as evidence/backfill;
- calculate rolling features and accuracy in SQL;
- persist immutable forecast snapshots before the forecast period;
- reconcile actuals after close;
- compute MAE, bias, WAPE/approved metrics by interval/daypart/horizon;
- require sample counts and exact source-set identity;
- semantic workers explain and recommend; they do not fabricate missing actuals or overwrite forecasts.

## Migration classifications

| Area | Classification | Rule |
|---|---|---|
| Contacts, Organizations, Relationships | MIGRATE after identity validation | quarantine malformed/duplicate relationships |
| Projects, Tasks | MIGRATE CURRENT STATE | preserve business obligation; rebuild schedule/approval/execution projections |
| Artifacts, Authoritative Files, Facts | MIGRATE | preserve IDs, provenance, hashes, external references |
| Communications | MIGRATE provider evidence/current processing | split receipt and processing; archive excess raw payload by policy |
| Notifications/Deliveries | MIGRATE CURRENT STATE + selected history | repair duplicate IDs; derive delivery attempts where evidence supports it |
| Settings/registries | REBUILD as typed configuration | preserve approved semantics, not sheet layouts |
| Workflow Dependencies | REBUILD | convert to typed stage/occurrence dependencies |
| Task Loop | REBUILD | migrate capability intent and schedules, not rows wholesale |
| Run Control | ARCHIVE REFERENCE + curated evidence | do not hot-import launcher noise or malformed rows |
| Staging Records | ARCHIVE/MIGRATE unresolved only | content-addressed quarantine; preserve unresolved source evidence |
| Integrity Checks | REBUILD | express as constraints, assertions, and audit queries |
| Ingestion State | MIGRATE CURRENT VERIFIED CHECKPOINTS | prove each boundary against provider state |
| Forecast audit/performance | REBUILD | schema exists but accountability data is not populated |
| AI Memory | MIGRATE with version governance | preserve active heads/history and references |
| Recovery Map/backups | ARCHIVE + REPLACE | retain evidence; replace mechanisms with PostgreSQL DR/export |

## Build plan and acceptance gates

### Phase 0 — freeze contracts, not production

- create architecture decision records, canonical vocabulary, lifecycle enums, IDs, operation schemas, and migration classifications;
- export/read-only profile current 1.x data quality and resolve duplicate identity policy;
- define volumes, retention, RPO/RTO, region, and cost model for 1/3/5/10–15 years.

Exit: signed schema/operations baseline and no unresolved authority ambiguity.

### Phase 1 — portable PostgreSQL foundation

- migrations, roles, business core, work/execution core, audit, outbox, provider command, memory, backup metadata;
- constraints and transition procedures;
- operations API/MCP and conformance test harness.

Exit: clean PostgreSQL deploy; rollback/forward migrations; synthetic end-to-end task and claim tests.

### Phase 2 — prove execution surfaces

Required first demonstrations from Rolling Version 94:

1. Online Ada commits a DB transaction, reads it back, and verifies audit.
2. HOME-01 uses the same operations contract and database.
3. A deterministic procedure detects and repairs a seeded reversible defect.
4. A stale heartbeat triggers a real independent SMS alert.
5. A replacement executor with only the bootstrap package completes a governed synthetic operation.

Exit: Designed -> Built -> End-to-End Verified.

### Phase 3 — shadow vertical slices

Implement in risk-reducing order:

1. task/work/claim lifecycle;
2. inbound SMS receipt -> semantic proposal -> deterministic commit;
3. outbound Notification -> Delivery -> Twilio -> verified result;
4. Gmail receipt/draft approval flow;
5. Toast normalized facts -> staffing features -> immutable forecast -> actual reconciliation;
6. dashboards/status views -> deterministic materialization/publication;
7. memory compaction and portable export.

Shadow reads 1.x and writes only 2.x. Compare expected outcomes; never write the same business effect from both.

Exit per slice: Shadow Verified with reconciliation report and failure-injection tests.

### Phase 4 — migration rehearsal and clean restore

- run typed importer into quarantine, validate, transform, and promote;
- resolve duplicate IDs and malformed rows explicitly;
- complete clean-room restore and replacement-AI bootstrap test;
- rehearse delta migration and rollback.

Exit: zero unclassified migration errors; signed cutover runbook.

### Phase 5 — controlled cutover

1. announce and enforce brief 1.x write freeze;
2. capture final delta and reconcile counts/hashes/business totals;
3. switch one authoritative writer;
4. verify critical vertical slices and dashboards;
5. keep 1.x read-only for rollback evidence;
6. rollback if acceptance threshold fails—never enable concurrent masters.

### Phase 6 — retire 1.x mechanics

Only after Production Verified maturity: retire polling workers, continuous rank rewrites, spreadsheet leases, repeated reparsing, and sheet-copy backup machinery. Retain archival evidence and documented redirects.

## Required test catalog

- concurrency: 100 contenders, exactly one valid claim;
- lease expiry during every stage boundary;
- DB commit then consumer crash;
- provider success then DB write failure;
- duplicate webhook/provider event;
- delayed/out-of-order provider status;
- semantic proposal schema violation and stale expected version;
- partial HYBRID completion and executor handoff;
- capability mismatch isolation;
- recurrence/DST/time-zone transitions;
- task dependency cycle detection;
- approval revocation and expiry;
- backup corruption detection and clean restore;
- Supabase outage and standard-PostgreSQL recovery;
- AI-platform substitution/bootstrap;
- watchdog independent alert;
- dashboard/forecast parity and freshness degradation;
- PII/sensitivity access and audit.

## Pre-implementation decisions still requiring owner approval

These are genuine decisions, not blockers to architecture work:

1. Supabase production region and paid backup/PITR tier after cost review.
2. Final RPO/RTO and retention periods.
3. Which Gmail operations have standing autonomous send authority versus draft approval.
4. Emergency watchdog channel/provider and escalation recipients.
5. Legal retention requirements for communications, employee records, financial evidence, and logs.
6. Cutover rollback window and success thresholds.

## Final recommendation

Proceed to implementation only after Phase 0 artifacts are approved. Do not create the Supabase project as the first step. First create the portable migration repository, SQL/operation contracts, data-quality quarantine rules, and executable acceptance suite. Then provision Supabase as the initial host and prove the five first functional milestones. The architecture is ready to build when the worker dispositions in the companion appendix are accepted and the six owner decisions above are resolved or explicitly deferred with defaults.

