# Phase 2 stopped candidate

**STOPPED_REGRESSION — not accepted, not deployable, do not merge.**

The accepted Phase 1 baseline was independently verified at
`c5731953a29256c013597cb04b938dff41f56de0`: clean local main, local origin/main,
live remote main, and accepted tag all matched. Phase 1 evidence checks passed;
the initial offline regression passed 51 tests with 26 historical placeholders
skipped and no failures. Historical Phase 1 artifacts were not rewritten.

## Regression stop

A private disposable PostgreSQL 17.11 instance rebuilt all 20 migrations and
successfully replayed the migration chain. The Phase 1 31-check transactional
suite then aborted at the first governed work.claim assertion:
`internal_error [42725]` (ambiguous_function). Correlation:
`8f0da50a-6606-4ae7-9fcf-4fc90482ca26`.

The owner's Phase 2 assignment explicitly requires stopping affected work when
Phase 1 regression breaks materially. Implementation stopped at this failure.
No Phase 2 functional checks or independent-session races were reached.
No mechanism has Phase 2 END-TO-END VERIFIED acceptance.

Read-only source inspection found a likely precedence defect at migration 20's
reserve_resources expression `(s->'reason_codes'-'attempt_limit')`. Accepted
migration 10 uses explicit parentheses around the JSON extraction. This is a
candidate explanation, not a repaired or independently verified root cause.
The rejected candidate is preserved as tested; no correction was applied after
the stop. A later authorized repair must review the rest of the draft as well.

## Persistent target and cleanup

Fresh hosted readback still reports migration 18, environment development,
authority non_production, provider_effects_enabled false, zero principal bindings,
and no Phase 2 executor_presence table. Persistent schema/data were not mutated.
Fresh hosted security advisor returned no findings; it does not validate this
unapplied candidate. No canonical password was retrieved or exposed.

The first disposable startup encountered an inherited-output-handle wait. The
exact test server was verified and stopped with pg_ctl. The harness was corrected
to use file-backed subprocess output; the second run stopped its server in finally.
Neither run installed a service or touched the persistent database.

## Draft implementation inventory

- Additive operation contracts in contracts/phase2 and migration 19; existing
  ecos.operate authentication, object scope, idempotency, audit and transaction
  boundary remain the entrypoint.
- Migration 20 drafts registration against pre-enrolled principal/instance
  bindings, presence/heartbeat metadata, configurable surface thresholds,
  resource providers/metrics/budgets/observations, scoped pressure and reservations,
  bounded work packages, durable dependent wakeups and recovery sweep.
- Draft lifecycle operations include register/heartbeat/stop, next/package,
  fail/defer/release/dead_letter, semantic.proposal.submit and resource.observe.
  Existing claim/renew/complete/proposal.commit/provider.result.record remain.
- Stable diagnostic views draft executor, readiness, claims, resource pressure,
  failures, dead letters, aging and health contracts; no dashboard was built.
- scripts/phase2_integration.py is explicitly invoked, synthetic-only test
  infrastructure. It includes draft SQL, semantic, provider and hybrid fixtures;
  these have not passed. It does not run real Online or Resident Ada.

Unknown provider quotas remain UNKNOWN. Heartbeat thresholds are labeled
engineering defaults; launcher cadence is not a database invariant. Normal
post-cutover execution is intended to use PostgreSQL; Sheets remains authoritative
now and was read only for bootstrap. No bulk business migration or cutover occurred.

## Vertical slices and remaining acceptance

| Legacy function | Intended Phase 2 proof | Current result |
|---|---|---|
| A025 readiness/claimability | query-time compatibility and atomic claim | regression failed |
| A008 integrity | expired-claim detection, finding/repair, fenced retry | draft tests not reached |
| A023 -> A053 -> A054 | receipt context, immutable semantic proposal, deterministic commit | draft fixture not reached |
| A027/A028 transport | Notification -> Delivery -> synthetic command/outbox/result | draft fixture not reached |

Each slice still needs complete trigger/object/contract, failure/retry/idempotency,
audit and retirement-prerequisite evidence. No 1.x worker may retire on this draft.
No shadow classification result is claimed; representative read-only comparisons
were not performed. No provider transport, Gmail/Drive/Toast mutation, SMS, 1.x
write, persistent migration, authority switch, merge or Phase 3 work occurred.

Next action requires authorization to resume the stopped candidate repair, then
full Phase 1 regression, Phase 2 checks, 15-session contention, resource/concurrency
review, narrow-package and surface acceptance, synthetic provider reconciliation,
shadow evidence and candidate security review before any persistent application.
Phase 3 is not recommended yet.
