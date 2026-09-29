# Four separate recovery contracts

A. Managed database backup/PITR: host-specific service plus audited restore; verify encrypted
coverage and restore point. Supabase procedures remain isolated under config/hosts. Proposed
RPO <=15m is not yet approved. Never infer availability of a tier or RPO from this repository.

B. Independent logical PostgreSQL backup: pg_dump custom format, schema and sanitized role/
grant reconstruction without passwords. Record server/tool versions and compatibility. Store
encrypted copies on Darrell-controlled storage and an independent off-provider location.
Proposed daily35/monthly13/annual7 retention and <=24h export RPO need owner approval.

C. Portable ECOS export: migration source/head, schema/data, functions/triggers/views,
materialization definitions, controlled config, capabilities, OpenAPI/JSON Schemas, memory
versions/heads, external artifact/provider reference inventory, dependencies, restore runbook,
verification queries and file inventory. Manifest includes package UUID/time/schema/tool
versions, relative paths, byte sizes, SHA-256, record counts and memory head IDs. Never include
plaintext credentials. Secret reference names and recovery/rotation instructions only.
Provider-authoritative bytes may require separately backed-up artifacts or authorized provider
access; the inventory must state availability/coverage, not promise impossible reconstruction.

D. Restore verification: a backup is verified only by a recorded successful restore test.
Portable manifest and backup/restore schemas are under contracts/recovery. Phase 0 checks
synthetic package integrity/path safety; it has not performed a database restore.

## Clean-room acceptance

1. Provision a separately authorized clean standard PostgreSQL target outside the live host.
   No provider credentials or external side-effect executors are enabled during restore.
2. Verify package inventory, hashes, sizes, counts, signature/provenance and encryption before
   reading SQL/data. Reject corruption, missing files, duplicate/case-colliding paths, absolute
   paths, traversal and links escaping the package. Quarantine tampered packages.
3. Reconstruct roles without passwords; apply matching schema/migration history and load data
   in FK order/consistent snapshot. Verify migrations/schema/tool compatibility and no secrets.
4. Rebuild derived projections and compare record counts, source/business totals and artifact
   hashes. Check FKs, unique claims/identities, memory heads/supersession and event/outbox links.
5. Start the ordinary operations API against the isolated restored database. Claim/complete
   a synthetic occurrence, submit/replay a proposal, validate audit and unknown-provider holds.
   Exercise bootstrap retrieval with a replacement executor; no provider send is allowed.
6. Record restore_test with exact package hash, queries, results, operator, target host class,
   measured RPO/RTO and evidence hashes. Compare approved targets; report gaps explicitly.
7. Repeat after schema/recovery changes and proposed quarterly cadence. A005 replacement
   retirement additionally requires two successful restore cycles and production verification.

An independent copy must survive primary-host/account loss. Document key escrow and secret
recovery references outside Git; restore encrypted payloads only in the authorized test target.
Cutover/failback remain separate decisions; recovering a copy does not grant write authority.

## Phase 1 implementation note

Phase 1 REST-01 is pending: no authorized direct export connection, clean PostgreSQL restore target or local server was supplied. No second database was created. Package corruption checks remain offline evidence only; do not infer a successful restore.
