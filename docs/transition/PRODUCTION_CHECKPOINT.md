# Production acquisition and source preservation

Owner-confirmed 1.x freeze was independently corroborated by absence of the Resident 1.x process. Online 1.x launchers remain owner-confirmed disabled. No 1.x files, releases, logs or schedules were deleted or changed.

## Live 2.x evidence

The existing Resident enrollment now runs exact committed candidate `0524766661253489d9228b3b7f665f2fab34ecbe` in production mode. No new executor service or alternate architecture was introduced. Its idle prior process was replaced only after a rollback-only enrollment preflight. Existing SQL authorization was updated to reflect the owner-confirmed freeze; no compatibility publication or provider business write was performed.

Occurrence `daffc056-41c7-476b-927c-ef2bbd81dfd0` completed in one attempt under Resident PID 36432. Real Toast data for September 29 was acquired, normalized and committed through `toast.batch.commit`; an independent restricted connection verified the batch and completion. The executor remained available. Capability attestation was renewed for a bounded 24-hour window; continuous attestation renewal and automatic restart are not yet accepted.

The existing canonical normalized staffing artifact was retrieved by its governed ID and matched its authoritative SHA-256. All 88 closed dates, July 1 through September 28, were imported without changing their observation values or the newly acquired September 29 date. Original source IDs, source hash and source_architecture=1X are retained in the restricted migration tables. Independent readback verified every date.

The SQL staffing calculation matched 555,870 statistics against the existing verified 2,647-row historical feature dataset. The full 2,664-row export remains expensive. Migration 26 adds a bounded date-window reader that retains historical samples while returning only requested feature dates. Current-day acceptance returned 17 rows in 0.937 seconds. Synthetic acceptance passed 25,200 comparisons, bounded/full equivalence and executor denial on the private helper. The migration was applied and independently verified through the existing ledger.

## Operational state and history

The fresh frozen source snapshot contains 36,015 preserved rows across 16 families in the existing restricted SQL raw migration tables. Every committed row was independently read back and its content hash recomputed. This includes Tasks, Projects, Task Loop, Run Control, dependencies, Exceptions, Artifacts, Facts, memory, ingestion checkpoints, authoritative file pointers, Communications, notifications/deliveries, Forecast Performance and staging. Original duplicate IDs remain distinct source locators. This is source preservation, not a claim that all rows have been promoted into operational typed objects.

Three old ownership references remain: A016, A024 and A031. Their exact run/claim evidence is preserved; reservation-time zero-effects statements do not establish the final provider outcome. All three are held in SQL quarantine for reconciliation, with zero automatic replays. No completed outcome was invented.

## Remaining functional work

Acquisition and staffing statistics are live components. Complete A029/A047 recurrence, complete provider-family persistence and downstream consumption, and full A029-B acceptance remain unfinished. No entire implementation batch is claimed complete. The remaining current operational records require typed validation, identity resolution, approvals/dependencies and promotion before execution.

Online semantic adapter tests are not an authenticated Online deployment. The available ChatGPT browser is logged out; owner sign-in has been requested while independent work continues. Exact 2.x-only launcher definitions are in ONLINE2X_LAUNCHERS.md. Host integration and independent semantic proposal readback must pass before enabling them. No 1.x scheduler access is requested.

The original 55 target dispositions and 13 implementation batches are unchanged. TARGET, IMPLEMENTED, TESTED and PRODUCTION_ACTIVE are tracked separately in function-status.json; live component acceptance is distinct from whole-function acceptance.
