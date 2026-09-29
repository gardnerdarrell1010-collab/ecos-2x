# Current Phase 1 status

Database foundation: **BUILT**. Specific demonstrated database paths: **END-TO-END VERIFIED**.
Phase 1 release acceptance is **incomplete**: 15 of 20 required gates pass; 5 remain pending.
No global shadow or production verification is claimed. Current implementation, coverage,
remaining gates and evidence are in [PHASE1_IMPLEMENTATION.md](PHASE1_IMPLEMENTATION.md),
[PHASE1_RESULTS.json](PHASE1_RESULTS.json), and [PHASE1_VERIFICATION.json](PHASE1_VERIFICATION.json).
Core migrations 000002-000018 implement the typed model, all ten contracted operations,
governed claims/proposals/outbox/memory, scoped roles and synthetic repair/health/quarantine.

The text below is the historical Phase 0 handoff, retained without rewriting its evidence.

---

# Phase 0 implementation coverage

Every artifact is local to `C:\ECOS\ecos-2x`. No 1.x, provider, dashboard, runtime or
production database state was modified. Only the supplied architecture review snapshots
were copied as baseline evidence. No sensitive production row export or credential is present.

| Required deliverable | Implemented evidence |
|---|---|
| 1. Canonical decisions | docs/adr/ADR-001.md through ADR-016.md; unresolved choices in architecture/owner-decisions.json |
| 2. Vocabulary/lifecycles | config/vocabulary.json and lifecycle-transitions.json, generated enum schemas and transition checks |
| 3. Repository foundation | isolated Git repository, .gitignore/.gitattributes, Python package/dependency pins, README/AGENTS, CI definition |
| 4. Migration framework | scripts/migrations.py plan/render, db/migrations/000001_foundation.sql, transactional ledger/checksum/drift tests |
| 5. Naming/types/identity | architecture/IDENTITY_AND_TYPES.md, strict UUID/time/version/hash schemas, legacy_identity schema |
| 6. Operation/API framework | contracts/api/openapi.json, operations registry and typed request/response/error schemas, operations/API.md |
| 7. JSON Schema framework | scripts/build_contracts.py, offline ContractStore with reference/format checks, synthetic positive/negative fixtures |
| 8. Executor/capability vocabulary | config/capabilities.json, executor/instance/attestation/requirement/heartbeat schemas and protocols |
| 9. Task/work/execution | task/work entity schemas, db/schemas/model.json, architecture/MODEL.md, scoring oracle and claim acceptance driver |
| 10. Events/outbox | versioned envelopes, typed payloads, outbox schema and crash-recovery specifications |
| 11. Provider commands | command/attempt/result/receipt schemas, boundaries registry, retry/reconciliation oracle and negative tests |
| 12. Memory/continuity | five memory entity schemas, bootstrap package schema, scoped head/supersession/compaction contract |
| 13. Backup/export/restore | recovery schemas, SHA-256/path-safe inventory verifier, corruption fixtures and clean-room runbook |
| 14. Migration/quarantine | raw batch/quarantine/alias schemas, duplicate/drift classifier, migration runbook and promotion invariants |
| 15. Legacy mapping | 30-family contracts/migration/legacy-mapping.json; required families and review governance included |
| 16. Worker dispositions | 55 exact review IDs, original source cells/line/hash, normalized fields, retired records and subordinate preservation |
| 17. Executable acceptance | scripts/check.py; contract/architecture/migration/concurrency/recovery/portability tests; explicit pending integration catalog |
| 18. Phase 1 manifest | docs/PHASE1_MANIFEST.json: ordered dependencies, contract paths, acceptance gates and unresolved owner choices |

The 100-contender algorithm and observation assertions are executable in
`tests/concurrency/acceptance.py`, ready for a future PostgreSQL driver. Only its oracle
is unit-tested here. Real contention, lease recovery, SQL execution, clean restore,
provider calls, watchdog alerts and production/shadow verification remain pending.

All review-listed later concerns are carried into the acceptance catalog: DST/recurrence,
dependency races, approval revocation, staged handoffs, sibling isolation, unknown outcomes,
provider event ordering, sensitivity, independent monitoring and forecast/dashboard parity.
The worker registry preserves detailed per-worker acceptance including 2,587 feature baseline,
41/41 renderer bindings, source unknowns and two restore cycles for A005 retirement.

Phase 0 owner review can now inspect concrete contracts. It is not signed automatically.
Region/tier, RPO/RTO/retention, Gmail send authority, watchdog recipients and cutover policy
are explicitly unresolved; none was used to authorize new effects.
