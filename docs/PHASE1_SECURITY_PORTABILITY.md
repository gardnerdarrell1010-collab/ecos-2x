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

Core migrations rebuilt and a native development export restored successfully on standard PostgreSQL 17.11.
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
No production rows or business-provider secrets were used. The explicitly authorized development database credential was resolved at runtime. One attempted
diagnostic direct call to a private mutation helper was rejected by automatic approval
review before execution; debugging continued through governed operations and read-only checks.

Client reference: [Psycopg installation](https://www.psycopg.org/psycopg3/docs/basic/install.html).
The pinned Psycopg 3.2.10 client connected over SSL; portable PostgreSQL 17.11 binaries supplied native dump/restore and a disposable loopback acceptance server, now stopped.

Final privilege readback found platform-managed admin-only membership grants from
`supabase_admin` to `postgres`. These have SET=false and INHERIT=false; they are not
temporary executor access and were left intact. Executable temporary service memberships,
principal bindings, active claims and undelivered outbox counts are all zero. The direct
client harness checks `pg_has_role(..., 'SET')` before temporary fixture grants, because
MEMBER alone does not establish permission to switch roles on PostgreSQL 17.


## Completion security review

Fresh security advisor: zero findings. See completion-advisors.json for current
performance INFO notices and remediation URLs. Fresh cleanup: zero principal bindings,
zero active claims, maintenance false, executor/API SET permission false. The live
31-check suite re-proved operation denial and scope boundaries after completion work.
The exact-password scan checks tracked/nonignored untracked files and Git diff without
printing secret bytes; its result is in completion-final-readback.json.

Incident: a short-lived signed download reference to the restricted credential artifact
was inadvertently included in a tool result. The password value was not printed. The
reference was not written to repository files/evidence; its configured expiry was
2026-09-29T16:29:08Z. Expiry has elapsed, but access/revocation was not verified. This
is separate from the clean repository secret scan. The reference is expired and was not reused or persisted. No actual password-value
exposure was observed; the secret was not modified.

Automatic approval review rejected a proposed broad diagnostic capture before execution.
The replacement records only schema object identities/hashes, table counts and digests;
no database row payload was added to committed discrepancy evidence.

Portable comparison normalizes schema CRLF/LF and fixes UTC/C collation for row digests.
All 74 table digests match after restore. Core requires no Supabase extension or service.
The export intentionally includes only ecos/ecos_meta/ecos_migration, not platform auth
or host schemas. Eight NOLOGIN roles are supplied as portable configuration. TLS private
keys and generated local credentials are confined to the private disposable runtime;
the initial password file was removed. No Windows service or production runtime changed.

Final C-01: both 15-session tests passed. Current security advisor and cleanup are in concurrency-15-advisors.json and concurrency-15-readback.json. No schema or permission design changed. Twenty required gates passed; no Phase 1 blocker remains. Capacity basis and forward CAP-01 are documented without implementing Phase 2.
