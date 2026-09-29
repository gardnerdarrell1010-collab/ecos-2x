# Phase 1 PostgreSQL implementation

The database foundation is BUILT on ECOS 2.x Development (`loonpojawpfagzobxoko`),
PostgreSQL 17.6, DEVELOPMENT / SHADOW ONLY. ECOS 1.x remains production authority.
Phase 1 database acceptance is complete: 20 required catalog gates passed; 6
belong to later phases. Ada/owner acceptance and merge review remain required. See [results](PHASE1_RESULTS.json) and [verification](PHASE1_VERIFICATION.json).
The original Phase 0 verification, baseline snapshots, catalog and manifest are preserved.

The canonical migration head is `000018_replay_authorization_scope.sql`: 74 tables,
47 functions, private schemas `ecos`, `ecos_meta`, `ecos_migration`. Migrations are
append-only and checksum guarded; forward corrections preserve the observed history.
No extension is required. Database identity prohibits production authority and provider effects.

## Operations and authorization

`ecos.operate(operation, request_json)` implements all ten existing registry names:
`task.transition`, `task.evidence.attach`, `fact.record`, `approval.decide`, `work.claim`,
`work.renew`, `work.complete`, `proposal.commit`, `provider.result.record`, `memory.activate`.
Request/result schemas remain the Phase 0 contracts. Context binds the verified SQL
role to a principal and executor, checks operation and object grants, sensitivity and
memory role scope, and carries correlation/idempotency/version evidence. Replays recheck
authorization. Proposal suboperations require their own operation grants.
Successful operations atomically retain immutable request/result hashes and audit rows;
rejected operations return structured errors and leave no partial mutation or success audit.
SQL functions enforce all registry schema keywords used here; they are not advertised as
a general implementation of every JSON Schema dialect feature.

`ecos.read_record` provides scoped content/hash readback. `ecos.bootstrap_package` returns
typed context, active memory, granted findings, operation bindings and all 73 schemas.
An actual returned package passed the independent Phase 0 Python verifier.
`ecos.record_heartbeat`, `ecos.claim_outbox`, `ecos.ack_outbox` and
`ecos.begin_synthetic_attempt` are the bounded support interfaces. Outbox commands with
unknown outcomes cannot dispatch; reconciled success can reacquire a lease for ACK without
resending. `ecos.health_summary` exposes only aggregates to analytics.

The eight ECOS roles are NOLOGIN, NOSUPERUSER, NOBYPASSRLS. Executor/API/adapter roles
have function access, no direct operational table mutation. Auditor/backup roles can read
sensitive evidence and are privileged roles. All temporary fixture principal bindings were
removed. There is no configured live Ada/Resident login or provider worker in this phase.
Operator-only configuration, recurrence materialization, repair, watchdog and quarantine
helpers are private; they do not create competing operation names.

## Verification

The offline suite has 77 tests: 51 pass, 26 catalog placeholders are intentionally skipped.
These historical skips do not override the separate observed Phase 1 result companion.
The live transactional suite has 31 named checks, all passing. It rolls back synthetic
fixtures and temporary role membership. Main checks cover all ten operations, denial and
scope revocation, states/versions/idempotency, claims/fences/recovery, immutable stage hashes,
five stage kinds on one obligation, semantic siblings, approvals, memory heads, health and
four malformed legacy rows. No provider transport is invoked.

Six committed durability stages preserve one clearly synthetic fixture. A consumer exit
after commit did not lose its outbox; lease attempt 2 recovered attempt 1 with a different
token. A stale token failed. An unknown provider outcome survived a separate readback,
blocked resend, and then reconciled. Final readback: one attempt, one result, one delivery
attempt, both outbox items delivered. No logical duplicate remained selectable.
The observed SQL files include exact fixture IDs; do not rerun them blindly. On a fresh
authorized fixture, derive IDs from the seed readback and retain the same assertions.

Seven EXPLAIN ANALYZE/BUFFERS plans are captured in evidence. Capability, dependency,
heartbeat and active-memory probes use indexes. Empty/tiny ready-work, claim and outbox
relations can prefer sequential scans. Relevant partial/FK indexes exist; these probes
are not performance or volume acceptance.

## Completion acceptance

C-06 and TASK-02 passed actual independent-session races. MIG-01 rebuilt all 18
canonical migrations on clean PostgreSQL 17.11, repeated the chain, and matched the
development schema. REST-01 restored a PostgreSQL-native custom dump, matched all
74 table counts/hashes and schema objects, and passed governed claim/completion.
Remote development, clean rebuild and restored database each passed 31 SQL checks.
Four independent race checks passed. Offline: 51 passed, 26 historical placeholders
skipped, zero failures. Historical evidence is retained in evidence/phase1/history/29998d9.

C-01 passed under the [current capacity basis](decisions/2026-09-29-phase1-capacity-basis.md):
10 designed simultaneous executors and 15 independent DB sessions, a 50% stress margin.
Test A: 1 winner, 14 valid losers, one live claim/run. Test B: 15 distinct valid claims,
all claim calls returned before any commit. Both used genuine independent backend PIDs
and barriers. All 16 occurrences subsequently completed with one immutable result each;
fences, capability, readiness and cleanup reconciled. No pool or compute changes.

The connection is Supabase Shared Pooler Session Mode with SSL. The canonical secret
reference is Google Drive file ID `1x8dB_y3doSdGOxVLhWG7gmQ4SAcTjVLf`; its value is
read only into runtime memory. See security documentation for the temporary download
reference disclosure in the tool trace, separately from the clean repository scan.
The isolated recovery server used loopback port 55432, installed no service, and is
stopped. Recovery packages remain ignored in `.local/phase1-completion`; the final
package path, manifest and hashes are in completion-recovery.json. They contain
synthetic development data only and are not a second authoritative database.

## Reproduction and remaining action

Run `python scripts/check.py` for offline checks and
`python scripts/phase1_evidence_check.py --require-complete` for evidence integrity
and release acceptance (exit 0 with all required gates passed). Current live entrypoint:
`python scripts/phase1_live_completion.py --gates concurrency --secret-materialization
<verified-governed-artifact-path> --report <report-path>`. No password belongs in arguments.
The harness fixes 15 sessions, verifies independent backend PIDs and uses common start
and precommit barriers. It retains immutable synthetic evidence and removes fixture access.

`scripts/phase1_recovery_completion.py --help` describes explicit client/runtime paths.
It uses canonical migrations, native snapshot export, manifest verification and restore
into a new private disposable runtime directory. Supply a fresh directory for each run.
Schema hashing normalizes line endings; row hashing fixes UTC and C sort collation.
The corrected health/result assertions are scoped to their own synthetic fixtures.

All 20 required gates pass; no Phase 1 blocker remains. Ready for Ada/owner acceptance
and merge review; no automatic merge or Phase 2 implementation. The six later gates
remain deferred. Global maturity remains DESIGNED; foundation BUILT and demonstrated
database paths END-TO-END VERIFIED. No global SHADOW/PRODUCTION VERIFIED claim.

CAP-01 is a required forward capability documented in
[Capacity / Quota / Bandwidth Governance](architecture/CAPACITY_QUOTA_BANDWIDTH_GOVERNANCE.md)
and [Phase 2 planning](PHASE2_PLANNING.md), without adding a Phase 1 telemetry project.
