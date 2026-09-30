> **Owner correction 2026-09-29:** ECOS 2.x is production infrastructure.
> Authority transfers per functional domain; historical non-production descriptions below
> are superseded by [the production authority decision](PRODUCTION_AUTHORITY.md).
> A029/A047 remain 1X until Wave 1 acceptance and transfer; A029-B remains 1X.

# Resident Ada 2.x: implementation delta, not a new worker review

## Evidence and authority

The existing authoritative **development disposition** is
`contracts/migration/worker-dispositions.json`, derived losslessly from
`docs/baseline/ECOS_2X_WORKER_DISPOSITION_APPENDIX.md` at commit
`375f3f61374aeaa52d28dc79fb80d14362c1e8f8`. The appendix SHA-256 is
`841c800b522390917f74abfc189a4d46edf9e22d8455ada87778a8495fcccf89`.
It covers **55 workers**, with 24 carrying a Resident classification and 25
carrying Online Semantic (hybrid classifications overlap). Neither file changed.
The architecture review, BASELINE, ADR-009 and the appendix's subordinate-function
preservation rules remain applicable. Dispositions are migration evidence, never
a runtime routing table. No new 55-worker reconstruction was performed.

Implementation started from clean local AND origin Phase 2 HEAD
`3c7e81fb07b793a085e4c7910ea16f94ba0f3157`. Phase 1 main remains untouched.
`PHASE2_IMPLEMENTATION.md`, `PHASE2_VERTICAL_SLICES.md`, migrations 19–20 and
the final Phase 2 evidence resolve the historical Phase 0/1 documents' maturity
statements. The database ledger remains 20. **ECOS 1.x retains production authority**;
2.x is PRE_CUTOVER / NON_AUTHORITATIVE with provider effects disabled.

## Final SQL control-plane delta

All listed objects already existed before this assignment. No migration,
operation contract, schema, or accepted fixture was edited.

| Responsibility | Implemented mechanism | Execution/recalculation boundary |
|---|---|---|
| Executor enrollment vs presence | Administrative principal/instance/operation/object enrollment; `executor.register` in migration 20 `ecos_meta.apply_operation`; `executor_policy`, `executor_presence` | Registration checks pre-enrolled identity, surface capacity and live attestations. It does not create login credentials or work definitions. |
| Heartbeat | `executor.heartbeat`, `presence_heartbeat`, `heartbeat_load`, `v_node_health` | Rejects future/delayed observations; DB counts active claims. Resident supplies periodic observations. |
| Selection / claim | `work.next` -> existing `claim_work` -> `selection`; `FOR UPDATE SKIP LOCKED`; `work_claim_one_active` | Each request freshly evaluates eligibility and ordering; creates claim and execution run atomically. |
| Narrow package | `work.package`, `work_package`, `require_package_scope` | Exact fence; task/source scope and hashes; 16 KiB input, 32 KiB package; cached replay rechecks scope. |
| Fence / lease | `check_fence`, `work.renew`, claim token/version/instance tuple | Each fenced call revalidates current ownership and expiry. Resident renews during execution. |
| Completion | `work.complete` in `apply_operation_phase1` | Immutable stage result, succeeded occurrence/run and released claim in one transaction. |
| Failure / defer / release | Migration 20 `apply_operation` branches | Retry timing, dead-letter/max-attempt handling, run/event/claim transitions; no client table DML. |
| Dependency release | `release_dependents` AFTER INSERT trigger on `stage_result`; `wake_work`; Phase 1 completion ready override | Durable `work_wakeup`, control-plane event and transient NOTIFY. Matching schema/hash required; incomplete prerequisites remain blocked. |
| Recovery | `recovery.sweep`, `repair_expired_claim`, `recover_occurrence` | Explicit bounded caller cadence. Restores missed wakeups, expires abandoned claims and records stale presence; PostgreSQL does not schedule its own sweep. |
| Resource admission | `resource_pressure`, `selection`, BEFORE INSERT `reserve_resources`, AFTER INSERT `record_reservations` | Live resource/freshness gates plus locked shared budget rows. UNKNOWN is not zero. Release/expiry removes effective usage through active-claim filtering. |
| Visibility | `v_executor_status`, `v_current_claims`, `v_ready_work`, `v_blocked_work`, `v_recent_failures`, `v_dead_letters`, `v_work_aging`, `control_plane_health` | Query-time projection. These are not full legacy business dashboards. |
| Events | Immutable `control_plane_event`; `wake_work` NOTIFY | Transactional evidence; hints can be missed without losing durable wakeups. |

## Exact scoring ownership

There is **no periodic stored-rank recalculation trigger**. `selection_phase1`
(migration 4, renamed by 20) reads current records/time, and migration 20's
`selection` adds resource/presence checks. `claim_work` orders the resulting tuple:
priority override, immediate ready, SLA breach seconds, deadline pressure seconds,
business impact, recurrence-relative age, created time, occurrence UUID.

| Historical responsibility | Classification | Exact replacement / remaining work |
|---|---|---|
| Task Loop persisted score/rank refresh and claimability reconciliation (A025) | ELIMINATED as SQL queue mechanics | Fresh `selection`, `claim_work`, claim uniqueness, fence validation and recovery. No score cells to repair. A025 retirement still needs broader shadow/operational acceptance. |
| Periodic time/aging score refresh | ELIMINATED | `selection_phase1(at_)`: SLA breach, deadline pressure and recurrence-relative age use the request's current time; `v_work_aging`/readiness views use statement time. Writes are immediately visible on the next query; no delayed recomputation job. |
| RUN NOW readiness and priority | PARTIALLY_REPLACED | Native `ready_override_at` and expiring `priority_override` are read by selection. Immediate readiness does not bypass approval, dependency, retry, capability or resource gates. A governed user-facing RUN NOW write operation/adapter is not supplied by Phase 2. |
| Dependency blocking/release | ELIMINATED for implemented work dependencies | `selection_phase1` checks current stage results and task prerequisites. `release_dependents` emits wakeups, and completion sets eligible dependent readiness. Task transitions affect eligibility at the next selection; there is no general transitive business-impact propagation or task-dependency wakeup trigger. |
| Deriving business importance/urgency/complexity into SQL priority inputs | STILL_REQUIRED where the business rule survives | `work_priority.business_impact`, deadlines and recurrence period are inputs. No trigger derives these from legacy Sheets formulas. The accepted SQL ordering policy is not proof of parity with every 1.x formula. |
| Recurring occurrence creation | PARTIALLY_REPLACED | `local_occurrence` handles DST, `materialize_occurrence` deduplicates schedule/version/local-time, `schedule_reconcile` cancels future superseded occurrences. No autonomous recurrence driver or public schedule-materialization operation is implemented by this Resident. A bounded scheduler/controller still must supply due logical times. |
| Retry eligibility | ELIMINATED as recurring score repair | `work.fail` computes bounded exponential backoff; `selection` evaluates retry_at and attempt limit on demand. No claim before retry eligibility. |
| Integrity/coverage/status workers A008/A015/A016/A022/A024/A039 | PARTIALLY_REPLACED | SQL replaces the specific control-plane predicates/projections above. Semantic judgment, communication policy, missing business projections, recurrence driving and external observation are not replaced by these functions. |

Thus **no separate scheduled scoring worker is needed for the implemented SQL
queue**, but recovery cadence, recurrence generation, upstream priority-policy
inputs and unimplemented domain projections remain. Do not confuse these with
obsolete score-cell maintenance.

## Material disposition changes established by this implementation

- A024's generic deterministic execution path now has a real separate SQL-native
  Resident process. This removes the Task 22 discovery gap without changing 1.x.
  Semantic execution remains an external Online Ada responsibility.
- A025's SQL control mechanics are implemented and regression-tested; no new
  Resident scoring worker was created. This is not blanket retirement approval.
- A008 recovery is invoked by the Resident on an expired fence. Independent
  watchdog delivery/outage acceptance and broader integrity/business audits remain.
- A038/A039 have implemented node/work health views. A037/A040/A041/A045/A051
  and A029-B were **targets for absorption**, not proof their complete status,
  executive, dashboard-health, rolling activity or staffing-feature projections
  exist. Their full replacement is not established by final Phase 2 or this run.
- A017/A030/A034 remain the prior retired/finite candidates; no new live worker
  was retired, stopped or reclassified by this assignment.
- A023/A053/A054's receipt -> semantic -> commit/ACK stages and A029 -> features
  -> forecasts -> feedback separation remain required. One engine does not remove
  the business stages or their provider reconciliation requirements.

## Capability reuse and acceptance scope

| Class | Reuse/adaptation | Proof and boundary |
|---|---|---|
| Governed DB client | Unchanged `scripts/phase2_executor_client.py` | Used by the actual child process; stable idempotency journal wraps it. |
| Authenticated HTTP, request binding, response normalization and redaction | Unchanged installed `HttpExecutor` and `request_bindings` imported from pinned 1.x files | Real loopback TLS GET with an isolated bearer token; reflected token redacted. Production providers are not contacted. |
| Secure reference resolution | Thin injected resolver using the existing HttpExecutor seam | Dedicated ACL-protected 2.x token/password files; no production credential is delivered to the child. The administrative harness alone resolves the canonical DB credential from Drive. |
| Deterministic local Python | New small acceptance handler using a fixed Python program, stdin data and timeout | Input is read from PostgreSQL work package; no caller-selected code/command. The existing 1.x business workers embed their execution; no independent safe generic Python primitive was found to reuse unchanged. |
| Filesystem/artifact read | Thin bounded path/hash adapter | Synthetic file under the separate runtime state root, exact SHA-256; no production artifact writes. |
| Twilio primitive | `ecos_capability.sms.send_sms` is independently reusable but disabled | Imported dependency only; no send performed, no claim of 2.x transport acceptance. |
| Gmail/Drive/Docs/Calendar, Toast, Vercel, HTML materializers, finance, backup | Existing business/provider logic must be retained behind scoped SQL adapters | Current worker wrappers depend on Sheets claims/config/staging or provider-specific contracts. They are not registered/attested as completed 2.x capabilities. No duplicated provider implementation was built. |

## Retirement/cutover conclusion

Resident 2.x now proves three representative capability classes through real SQL
claims and completion. It does **not** yet execute all 24 Resident-classified
legacy dispositions. Online Ada has accepted Phase 2 packages/proposal/operation
contracts and synthetic surface tests, but no deployed Online Ada 2.x process or
live semantic acceptance was added here.

Blocking work before operating only 2.x:

1. Adapt the surviving provider/rendering/domain capabilities, schemas and scope
   enrollment; verify real provider idempotency, unknown-outcome reconciliation,
   ACK, delivery, mutation and publication behavior under explicit authorization.
2. Deploy/accept Online Ada execution and preserve semantic-to-deterministic stage
   ownership. Synthetic SQL surface tests are not live semantic-worker acceptance.
3. Complete missing domain/status/feature projections, recurrence driver and
   governed control inputs; establish full eligibility/ordering/domain shadow parity.
4. Governed data migration/reconciliation, current authority/cutover protocol,
   operational watchdog/alert delivery, launcher supervision, restore and rollback
   acceptance. The current `ecos.operate` explicitly rejects any database identity
   outside development/non_production/provider-effects-disabled; production cutover
   therefore needs separately authorized implementation, not a flag flip here.

**A two-hour complete retirement is not supported by the evidence.** The next
work is multiple implementation and acceptance streams plus at least a full
representative schedule/forecast/restore validation cycle. An exact duration
cannot be responsibly estimated until those provider adapters, migration gaps and
acceptance windows are bounded. Installing a synthetic-only Resident launcher is
small; it does not establish readiness to replace 1.x.
