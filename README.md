> **Owner correction 2026-09-29:** ECOS 2.x is production infrastructure.
> Authority transfers per functional domain; historical non-production descriptions below
> are superseded by [the production authority decision](docs/PRODUCTION_AUTHORITY.md).
> A029/A047 remain 1X until Wave 1 acceptance and transfer; A029-B remains 1X.

# ECOS 2.x — Phase 1 development branch

Portable PostgreSQL database foundation implemented in the authorized **development-only**
Supabase project. Phase 1 acceptance remains incomplete. Start with
[implementation and pending gates](docs/PHASE1_IMPLEMENTATION.md),
[verification evidence](docs/PHASE1_VERIFICATION.json), and
[security/portability](docs/PHASE1_SECURITY_PORTABILITY.md).
ECOS 1.x remains production authority. No real provider or production effect is enabled.
The default check harness remains offline. Do not merge this branch automatically.

The following Phase 0 repository introduction is historical:

---

# ECOS 2.x â€” Phase 0

Portable PostgreSQL modular-monolith contracts and an **offline executable acceptance
foundation**. Repository: `C:\ECOS\ecos-2x`. No application server, database, provider
integration, deployment, migration/import, or production write has been performed.
ECOS 1.x remains production authority. Operational maturity is **DESIGNED**; the local
contract foundation is **BUILT**. A passing offline suite is not E2E/shadow/production proof.

## Run the offline checks

Python 3.12+; Windows, Linux or macOS. From the repository root:

```sh
python -m venv .venv
# Activate .venv using your shell, then:
python -m pip install -r requirements.lock
python scripts/check.py
python scripts/migrations.py plan
```

Windows can use `.venv\Scripts\python.exe` directly. No database environment variables,
network connections, production reads, or credentials are required for the checks after
dependency installation. `python scripts/check.py --require-phase1` deliberately fails
while any Phase 1 integration gate is pending. Pending tests are reported separately.

## Start here

- [Baseline and authority](docs/architecture/BASELINE.md), [ADRs](docs/adr/README.md),
  [model and invariants](docs/architecture/MODEL.md), [identity/types](docs/architecture/IDENTITY_AND_TYPES.md).
- [Phase 1 manifest](docs/PHASE1_MANIFEST.json), [acceptance catalog](tests/acceptance-catalog.json),
  [owner choices](docs/architecture/owner-decisions.json).
- [API contract](contracts/api/openapi.json), [operation rules](docs/operations/API.md),
  [schemas](contracts), [55-worker registry](contracts/migration/worker-dispositions.json).
- [Quarantine](docs/migration/QUARANTINE.md), [provider boundaries](contracts/providers/boundaries.json),
  [restore runbook](docs/recovery/RESTORE.md).

`scripts/build_contracts.py`, `build_worker_registry.py`, `build_foundation_data.py`, and `build_fixtures.py`
are editable sources for generated JSON. Each supports `--check`; check.py rejects drift.
Schema IDs use a reserved `.invalid` domain as identifiers; all references resolve offline.
The standard-library unittest harness includes pure decision oracles, negative fixtures,
architecture checks, and a PostgreSQL driver acceptance interface. It is not a live runtime.

The requested directory tree uses `src/ecos/{core,dispatcher,executors,adapters}` as a
single Python namespace, avoiding four unrelated packages. Database `functions`/`views`
hold Phase 1 implementation contracts; Phase 0 migrations contain framework DDL only.
There are no empty placeholder directories.

The pasted assignment ended after the first two provider-boundary field bullets. All
visible requirements are covered; reconciliation, portability and secret boundaries
were also recorded from the two supplied baselines. See [coverage](docs/REQUIREMENTS.md).
