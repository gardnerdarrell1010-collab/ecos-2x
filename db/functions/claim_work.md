# Phase 1 transaction specification

This is a specification, not a deployed function. Use one short PostgreSQL transaction
at READ COMMITTED. Derive actor/instance from authenticated credentials, never trust a
client capability list. Serialize gates and dependent approval/dependency mutations in
the same lock order; final gates are rechecked before effects and at completion.

1. Read database time once for selection; select claimable stage occurrences using
   `FOR UPDATE OF wo SKIP LOCKED LIMIT 1`, deterministic priority tuple and UUID tie.
2. Lock/recheck the occurrence and applicable gate/version rows. Availability requires
   non-expired server-received heartbeat and capability attestations. Exclude unresolved
   provider outcomes; a ready override only changes the due gate.
3. Close an expired active claim under that same occurrence lock before replacement.
   Increment `work_occurrence.claim_version`; generate a new UUID fence token. Never
   reuse a fence, even for the same executor. Insert claim and execution_run atomically.
4. A partial unique index on `(occurrence_id, stage_definition_id) WHERE state = 'active'`
   proves at most one active row. Do not put `now()` in the index predicate. An expired
   active row stays unique until explicitly closed under lock.
5. Append selection inputs, versions, policy and score tuple to immutable execution_event;
   commit before returning the claim. Claims and runs both exist or neither exists.
6. Renew/complete requires all six fence fields, active claim, matching instance boot,
   and `expires_at > clock_timestamp()` after row-lock acquisition. A renewal cannot
   resurrect an expired claim. A stale completion writes no domain mutation or result.
7. Complete stores verified immutable stage_result, closes claim/run and enqueues next
   stage occurrence + domain event/outbox atomically. A repeated completion with identical
   idempotency key/content returns its durable original result; conflicting bytes fail.

Recovery locks the occurrence, inspects verified stage results and provider commands,
and expires abandoned claims. Preserve succeeded stages and their hashes. Unknown
provider outcomes route to reconciliation, never automatic re-send. Retry only unfinished
safe stages. A claim grants internal ownership; it cannot guarantee an external provider
stops a request already in flight. Stable command keys and reconciliation cover that gap.

Future SQL must prove C-01..C-07 through `tests/concurrency/acceptance.py`. A Python lock
or in-memory ownership simulation does not satisfy the PostgreSQL gate.
