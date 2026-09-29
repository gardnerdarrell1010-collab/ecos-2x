# Phase 1 PostgreSQL implementation

The database foundation is BUILT on ECOS 2.x Development (`loonpojawpfagzobxoko`),
PostgreSQL 17.6, DEVELOPMENT / SHADOW ONLY. ECOS 1.x remains production authority.
Phase 1 acceptance is incomplete: 15 catalog gates passed, 5 remain pending and 6
belong to later phases. See [results](PHASE1_RESULTS.json) and [verification](PHASE1_VERIFICATION.json).
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

## Remaining Phase 1 gates

| Gate | Remaining evidence |
|---|---|
| C-01 | 100 simultaneous independent PostgreSQL sessions, exactly one winner |
| C-06 | Real racing approval/maintenance changes versus claims/effects |
| TASK-02 | Concurrent dependency-cycle rejection; sequential DST/update checks pass |
| MIG-01 | Clean rebuild of the final full canonical chain on an authorized empty target |
| REST-01 | Logical export and clean standard PostgreSQL restore, counts/hashes/API claim |

HOME-01 has no authorized direct connection and no PostgreSQL server/restore target.
The owner explicitly authorized leaving these connection-dependent checks pending.
No second database/project, password, server, or authentication change was created.
The Phase 1 release gate remains blocked. Do not merge or advance to Phase 2 acceptance.

PORT-01, SURFACE-01, INTEGRITY-01, WATCH-01, SHADOW-01 and MIG-02 are deferred exactly
as the manifest states. Seeded repair/health/quarantine checks here do not constitute those
later complete gates. Overall ECOS 2.x remains DESIGNED; only demonstrated database paths
are END-TO-END VERIFIED. Nothing is SHADOW VERIFIED or PRODUCTION VERIFIED.

## Reproduction and next action

Run `python scripts/check.py` for offline checks. To render an authorized Supabase tool
payload without executing it, run `python scripts/supabase_migration_payload.py --project-ref
loonpojawpfagzobxoko`. Apply through the connected Supabase migration tool only after checking
identity and the live ledger. The tool adapter removes psql transaction directives because
the host wraps migrations. The portable renderer remains `python scripts/migrations.py render`.
Never edit an applied migration or rerun the historical generator to replace it; its `--check`
mode only verifies the initial recipe.

The owner can configure a development-only `ECOS_DEV_DSN` or libpq service reference using
the project's Connect settings, without sharing secrets in chat or Git. The harness needs
100 backend sessions and an authorized fixture/migration login; a session pooler may be used
only if it actually provides 100 distinct server sessions. Client dependency installation is
separate: `python -m pip install -r requirements-phase1.lock` (not performed during this work).
Then run `python scripts/phase1_contention.py --project-ref loonpojawpfagzobxoko --report
test-results/phase1-contention.json`. It checks project host/user, PostgreSQL version and
nonproduction identity, opens all sessions before its barrier, and proves distinct PIDs.
It retains synthetic evidence, removes its binding and disables the fixture executor.
Failure or insufficient session capacity cannot be reported as a passed gate.

REST-01 still needs an explicitly authorized clean restore target and PostgreSQL client
tools, following [the existing restore contract](recovery/RESTORE.md). No target is assumed.
Complete these Phase 1 gates and obtain Ada/owner review before considering Phase 2.

Use `python scripts/phase1_evidence_check.py --require-complete` to verify source/database checksums and the current companion release gate. It returns 2 while the five required gates remain pending.
