# Phase 1 security and portability evidence

Security advisor: zero findings at the recorded verification time. This is a hosted
advisor result, not a penetration test or proof that every concurrency race is safe.
Private schemas are not a Supabase Data API surface. Functions use fixed search_path,
bound SQL roles, explicit grants and transactional checks; PUBLIC execution is revoked.
No auth.uid(), Supabase Auth, Realtime, Storage, Edge Functions, extensions, hosted queue,
cron, Google Sheet or provider runtime is required by core migrations.

| Dependency | Reason | Replacement |
|---|---|---|
| Supabase connected execute_sql/apply_migration | Authorized development transport | Standard authenticated PostgreSQL client; canonical migration renderer |
| Supabase migration ledger/advisors | Host deployment/diagnostics | ecos_meta.schema_migration plus PostgreSQL catalogs/EXPLAIN |
| Supabase project host/ref in the live harness | Prevent accidental wrong-target tests | Explicit owner-authorized alternative host identity adapter in the later portability gate |
| PostgreSQL 17 | JSONB, PL/pgSQL, row/advisory locks, catalog privileges, native UUID/SHA-256 | PostgreSQL 17+; no extension installation |

Core migrations are valid PostgreSQL; the full off-host restore has not been performed.
Roles must be created by an appropriately authorized migration login. No credential is
stored in this repository. The existing eight NOLOGIN roles need explicit least-privilege
bindings before any real executor connection is authorized. A Supabase service key or
user-controlled JSON principal must never be treated as the SQL-role authentication boundary.

Performance advisor reports six INFO composite-FK covering-index notices and 57 INFO
unused-index notices at the snapshot. Existing indexes cover a selective leading UUID on
each flagged relationship (claim, head, memory record, attempt, run, stage); broad duplicate
composite indexes were not added solely to remove lints. Empty development workloads do not
justify removing correctness or control-plane indexes. See the full finding/index names and
seven query plans in [observations](evidence/phase1/database-observations.json).
[FK advisor guidance](https://supabase.com/docs/guides/database/database-linter?lint=0001_unindexed_foreign_keys)
and [unused-index guidance](https://supabase.com/docs/guides/database/database-linter?lint=0005_unused_index).

The suite deliberately expires only synthetic leases, simulates consumer loss after commit,
and submits duplicate/stale/invalid inputs through the authenticated operations boundary.
No executor credentials, production rows or provider secrets were used. One attempted
diagnostic direct call to a private mutation helper was rejected by automatic approval
review before execution; debugging continued through governed operations and read-only checks.

Client reference: [Psycopg installation](https://www.psycopg.org/psycopg3/docs/basic/install.html).
The optional pinned client has not been installed or connected on HOME-01 in this phase.
