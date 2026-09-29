# Authority and scope

The two immutable review snapshots in `docs/baseline/` were read completely before
implementation. `baseline-provenance.json` pins their exact bytes by SHA-256. They describe
the 2026-09-28 review, including MEM-ECOS-000036 Rolling Version 94; these are review-time
facts, not a fresh assertion about current ECOS. No live ECOS read was necessary to build
contracts. No AI Memory or conversation text supersedes current structured authority.

Before future current-state verification/extraction: load ECOS 1.x read-only, read System
Bootstrap first, follow the current Sheet/Command Registry governance, and request only
the minimum needed record families. Never write governed 1.x records during migration design.

One PostgreSQL operational core, one governed operations API, one generic deterministic
dispatcher, a generic semantic executor interface and a small provider adapter plane are
the approved direction. SQL, JSON Schema, OpenAPI and ordinary source/tests are canonical.
There are no worker-specific services or platform-specific capability names.

The existing `ECOS-Platform` tree is an ECOS Runtime Phase 1 POC/node installer, not this
portable 2.x repository. It and all runtime, credentials, production files, dashboards,
provider state and parent directories were left outside this implementation.

Phase 0 elaborations (UUIDv4, schema version 1.0.0, integer hash profile, ordering policy
v1, development heartbeat defaults) are explicit engineering contracts for review. They
are not claimed to be inherited production settings. Owner decisions remain unresolved
in `owner-decisions.json`; conservative defaults do not constitute approval.

No production or shadow database exists here. Baseline signoff is pending owner review.
Phase 1 must prove database constraints and operations; later phases prove actual execution
surfaces, provider behavior, shadow parity and cutover. No 1.x retirement is authorized.

## Standards references

- [PostgreSQL SELECT/row locking](https://www.postgresql.org/docs/current/sql-select.html)
  supports the future queue claim pattern; SKIP LOCKED alone is not a business invariant.
- [JSON Schema 2020-12 validation](https://json-schema.org/draft/2020-12/json-schema-validation)
  supplies schema semantics; the harness explicitly enables format checks.
- [OpenAPI 3.1.1](https://spec.openapis.org/oas/v3.1.1.html) describes the governed HTTP contract.
- [python-jsonschema validation](https://python-jsonschema.readthedocs.io/en/stable/validate/)
  documents the offline validator used here.
- [Supabase changelog](https://supabase.com/changelog) was checked for host guidance;
  this repository implements no Supabase-specific feature or extension dependency.
