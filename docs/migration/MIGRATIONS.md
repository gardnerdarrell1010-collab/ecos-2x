# Portable migration framework

`scripts/migrations.py plan` validates contiguous versions and optional exported applied-history
checksums without connecting. `render` prints a reviewed psql transaction: advisory transaction
lock, private schema_migration ledger, unknown-history/drift checks, unapplied SQL and ledger
inserts. It never opens a socket or invokes psql. Phase 0 contains only schema foundation DDL;
domain DDL/functions/constraints are Phase 1 work. SQL has not been executed or DB-verified.

At Phase 1, approve an isolated disposable PostgreSQL target and least-privilege migration
runner separately. The execution adapter must verify target identity and exact reviewed
artifact hash, inspect server version, then apply the rendered script with ON_ERROR_STOP.
An error rolls back the whole transactional batch including ledger changes. Concurrent migration
runners serialize on the advisory lock. No nontransactional DDL may enter this initial framework;
future concurrent-index changes require an explicit separately designed migration mode.

Applied SQL is immutable and pinned by exact-byte SHA-256. Line endings are LF in Git.
Never re-number/delete historical migrations. Corrections use a new forward migration.
Before commit: test clean install, no-op second application, drift rejection, failure rollback,
two concurrent runners and forward correction. A destructive down migration is not an automatic
rollback strategy; rehearse logical restore or a reviewed reversible forward change instead.
Retention/destructive data rollback requires owner policy and backup verification.
