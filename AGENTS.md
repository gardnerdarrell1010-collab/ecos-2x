> **Owner correction 2026-09-29:** ECOS 2.x is production infrastructure.
> Authority transfers per functional domain; historical non-production descriptions below
> are superseded by [the production authority decision](docs/PRODUCTION_AUTHORITY.md).
> A029/A047 remain 1X until Wave 1 acceptance and transfer; A029-B remains 1X.

# ECOS 2.x development boundary

This directory is an isolated Phase 0 repository. Read README.md, docs/architecture/BASELINE.md,
and docs/PHASE1_MANIFEST.json before changing scope. ECOS 1.x remains production authority.
Never run providers, SQL, provisioning, deployment, imports, or live acceptance tests as part
of the default harness. No database exists for this repository in Phase 0.

All fixtures must be synthetic. Never copy credentials, production rows, raw exports, or
backups into Git. Preserve the approved baseline snapshots and their SHA-256 provenance.
Worker dispositions are migration evidence, never a dispatcher routing table.

Run `python scripts/check.py`. Schema generator changes require `python scripts/build_contracts.py`.
Maintain explicit pending integration gates; passing pure reference tests is not database
or production verification. Do not mark owner decisions approved without owner evidence.
