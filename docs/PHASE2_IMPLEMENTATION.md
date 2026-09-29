# Phase 2 control plane: implemented and verified before cutover

Canonical Phase 2 is migrations **19 and 20**, now applied to the existing project
`loonpojawpfagzobxoko`. Accepted migrations 1-18 are byte-identical. The owner explicitly
authorized consolidating the unreleased migration 21 into migration 20; Git commits
`fb32cfa`, `519f4a7`, `2ffb3f8` and `8ee884b` preserve the original defects and repair.
Original attempt and repair-021 evidence files remain unchanged.

The executor path is PostgreSQL governed work -> external execution -> governed result.
Stored functions perform deterministic transactions/control only. Semantic interpretation
stays outside PostgreSQL; the semantic acceptance input is an explicitly synthetic proposal.
No new permanent database, runtime service, Task Loop, dashboard or provider integration
was created. Main remains the accepted Phase 1 baseline.

## Verification

- Clean PostgreSQL 17.11 migration 1-20 rebuild, exact guarded 18-to-20 application
  transport and full chain repeat passed. `clean-candidate-008.json` is pre-application
  evidence; `clean-candidate-009.json` adds the portable client proof without changing SQL.
- All 31 Phase 1 transactional checks passed on disposable and persistent targets.
  Offline checks: 51 passed, 26 historical pending integration placeholders skipped.
  Accepted Phase 1 evidence/checksum validation passed.
- 38 Phase 2 checks passed, including four surface identities, package scope revocation,
  resource contention/release, fail/defer/dead-letter, recovery, semantic handoff,
  synthetic provider reconciliation, durable audit, connection reuse and bounded backoff.
- Fifteen independent sessions: same work 1 winner/14 valid losers; different work
  15 distinct winners. Both prove results returned before any contender committed.
  A separate two-session budget-1 race produced exactly one reservation.
- Hosted smoke (register -> next/package -> renew -> complete/readback) passed and
  rolled back all test records/grants. Hosted Phase 1 synthetic tests also rolled back.
- Hosted catalog matches the disposable catalog: 104 relations, 59 functions,
  15 view definitions and all 20 ledger checksums. Counts/digests of all 71 preexisting
  non-contract/non-ledger tables are unchanged.
- Hosted security advisor: zero findings. Private helpers, direct table mutation,
  spoofed principals, wrong operation roles and revoked cached-package scope were denied.
  No canonical database credential was retrieved. Secret scan is recorded separately.

## Mechanisms and contracts

Executor registration uses pre-enrolled principal/instance bindings and attested
capability versions. Configured surface limits are 8 Online, 1 Interactive, 1 Resident;
the database service identity has its own limit of 1. No launcher cadence is a DB invariant.
Heartbeat policy carries source/effective time and freshness; dead instances become
unavailable. A stopped instance cannot restart under the same identity.

All surfaces use `ecos.operate(operation, request)` with authenticated SQL roles,
principal/operation/object grants, request context, idempotency key and fenced work.
`contracts/phase2/operations.json` lists the additional contracts. The portable
`scripts/phase2_executor_client.py` reuses one authenticated connection and reconnects
at most twice after 0.25/1.0 seconds, retaining the same request/idempotency key. It does
not schedule work, interpret it, or send provider effects. The caller supplies its
least-privilege connection factory; no owner credential is an executor credential.

Work packages carry occurrence/stage, minimal task context, operation/capabilities,
selected verified sources/memory, deadline/approval context, correlation/fence and
retry/idempotency context. Input is bounded to 16 KiB, package to 32 KiB, selected
source/memory counts to 16/8. Tested package sizes were 2,714-2,749 bytes. The test
client made two calls on one connection, measured 430 response bytes and query latency.
No entire Tasks/Communications/Files/Memory collection is sent to the executor.

Resource providers, metric units, windows, quota provenance/freshness, UNKNOWN state,
observations and scarce-resource reservations are portable PostgreSQL objects.
BLOCKED/THROTTLED affect dependent work. Missing quotas/observations remain UNKNOWN;
requirements explicitly choose whether unknown telemetry blocks admission. Budget rows
serialize only work sharing that budget. Reservations count only active unexpired claims;
completion/release/expiry frees effective usage without deleting evidence. Adapters supply
observed rolling-window values, not fabricated provider quotas. Real pool utilization,
CPU, host bandwidth and costs remain unavailable until measured/configured by their owner.

Stage-result commits create durable dependent wakeups and transient NOTIFY hints.
`recovery.sweep` is a bounded safety-net operation for existing executor/recovery cadence;
missed hints do not strand work. It recovers expired claims, restores pending wakeups,
marks stale presence and reports recoverable outbox. No 1.x schedule was changed.
Read-only views expose executors, claims, readiness/reasons, pressure, failures,
dead letters and aging; `ecos.control_plane_health()` includes connections, lock waits,
claim/outbox age and explicit unknown health metrics. No arbitrary queries/minute ceiling.

## Shadow and maturity limits

Two bounded read-only Task Loop samples were projected into synthetic PostgreSQL
fixtures. The A025 due-time and A027 future-time admission predicates were both
EQUIVALENT. Only hashes, locators and normalized predicates were retained. This is
not full queue eligibility, priority ordering, dependency, notification or global parity.
No ECOS 1.x write occurred, and no legacy worker was retired.

The four required slice categories are proven with real PostgreSQL operations and
synthetic interpretation/provider inputs; see PHASE2_VERTICAL_SLICES.md. No live Online,
Interactive or Resident launcher deployment is claimed. Inherited independent replacement-AI,
live launcher and independent watchdog delivery/outage gates remain unproven rather than
being silently relabeled passed. They must be addressed in owner-authorized operational
acceptance before worker retirement/cutover; they do not invalidate the measured SQL results.

Authority remains **PRE_CUTOVER / NON_AUTHORITATIVE**, schema 1.0.0, architecture 2.x,
provider_effects_enabled=false. Hosted cleanup: zero bindings, active claims, presence
rows and outbox backlog; temporary executor/API SET permission false. Historical synthetic
Phase 1 executor records remain and may appear stale in health summaries.
No production provider effects, ECOS 1.x mutations, global shadow verification,
production acceptance, main merge or Phase 3 start occurred.

## Defect history and bounded review

The SQLSTATE 42725 expression is now `((s->'reason_codes')-'attempt_limit')`.
The unused `work_package` variable `r` was removed; only its retry-policy SQL alias remains.
The bounded new-SQL pass also removed an unused declaration, separated operation-local
proposal/claim identifiers from SQL aliases, and rebound the readiness view to the new
selection function (PostgreSQL views retain OIDs through renames). No accepted migration
was edited and no global PL/pgSQL ambiguity setting was changed.

Integration found and corrected only new-code/test defects: invalid synthetic expiry
ordering, cleanup of terminal fixtures, expected `expired_fence`, lifecycle reason-token
schema alignment, the smoke fixture column list, and cached new-package access checks.
The latter extends the existing authorization-before-replay rule; it does not weaken
security or change Phase 1 operation behavior. Failed run evidence is retained.

The exact executable checks are scripts/phase2_integration.py, phase2_acceptance.py,
phase2_release_check.py and db/tests/phase2_smoke.sql. Current machine-readable outcomes
are PHASE2_VERIFICATION.json and PHASE2_RESULTS.json. Do not begin Phase 3 or merge main
as part of this handoff.
