# Acceptance harness scope

Run `python scripts/check.py` from the repository. The suite validates generated artifacts,
every schema/reference with strict format checking, exact legacy inventories, API/registry
alignment, safety gating, sibling proposal outcomes, retry policy, source quarantine,
manifest corruption/path safety, migration history and architectural dependency boundaries.
All data is synthetic. `db/fixtures/contract-examples.json` is a machine-readable fixture pack;
`scripts/build_fixtures.py --check` prevents drift.

`tests/acceptance-catalog.json` lists integration gates with phase, assertion, reference and
pending reason. Each appears as a skipped test. `--require-phase1` fails with exit code 2 while
any Phase 1 gate is pending; Phase 0 success must never be presented as Phase 1 completion.
The pending test class is intentionally not an implementation. Phase 1 must replace pending
gates with actual integration tests and retain evidence before changing catalog status.

## Wiring the future PostgreSQL claim driver

Implement PostgreSQLClaimDriver in `concurrency/acceptance.py` using independently acquired
connections for each contender, bounded statement/connection timeouts and an explicitly
authorized disposable database. `claim` returns a committed claim with its six ownership
fields or None; `live_claims` queries actual unexpired active rows using database time and
`execution_runs` queries committed run rows. Never feed synthetic observations to claim a DB pass.

Invoke `assert_hundred_contenders(driver)` for C-01 and `assert_lease_recovery(driver)` for
C-02/C-03. Seed verified prior-stage evidence in the latter's fixture to avoid vacuous
preservation. Add barrier-controlled approval revocation/expiry, stale boot, maintenance,
rollback, unknown-provider and each-stage handoff races for C-05..C-07. Reuse production
claim procedures; do not create test-only ownership logic. Snapshot business/audit/outbox
before rejected operations and prove no changes. No driver is bundled or loaded in Phase 0.

CI configuration targets Windows and Linux with Python 3.12. The local verification report
records only the platform actually tested; an unexecuted CI definition is not portability proof.
