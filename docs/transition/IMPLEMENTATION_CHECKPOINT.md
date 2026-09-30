> Superseded by [the production checkpoint](PRODUCTION_CHECKPOINT.md). The pending freeze and undeployed-runtime statements below describe the earlier checkpoint only.

# 2.x functionality checkpoint

Owner direction: stop 1.x with existing Windows controls; no drain, pre-stop checkpoint, publication guard, or coexistence bridge. The previously prepared checkpoint freeze is superseded. Its files remain historical evidence.

## Implemented this checkpoint

* The existing Toast acquisition adapter now permits production SQL commits while requiring provider business writes disabled. Existing domain authorization, fences, idempotency and independent committed readback remain enforced. It does not publish a legacy compatibility artifact.
* Migration 25 provides SQL-native staffing statistics over the existing normalized observations: same-weekday 4/8/12 samples; rolling 28/56/84 days; count, source dates, mean, median, min, max and sample standard deviation; prior-year comparables and availability labels. Read access is scoped to the authenticated Toast/staffing principal and execution mode. No operational observation was modified by this migration.
* Online 2.x now has a separate semantic adapter on the existing execution lifecycle. PostgreSQL-only profile validation, registration, heartbeat, selection/package, capability checks, lease renewal, completion/failure/recovery are reused. The Online host must supply actual semantic interpretation; there is no local model substitution. Exact proposals are journaled before submission and reused after interruption. Changed context is rejected.

## Verified

* Real Toast read for September 29: acquisition, normalization (17 intervals), and dashboard projection passed. This was a bounded provider-read acceptance, not an autonomous production completion. Private provider evidence stays outside Git.
* SQL staffing: 25,200 numerical/null/source-date comparisons across 100 synthetic days and 200 feature rows matched the existing Python implementation. The synthetic transaction was rolled back; migration 25 was subsequently applied and its ledger hash/read function independently verified.
* Sixteen targeted Online/Resident/Toast tests passed. Required offline suite passed after implementation. Hosted CI is verified separately for the final commit.

## Not claimed complete

Resident 1.x was still present at the latest process check. Its Administrator stop/disable block is with the owner. Online 1.x launchers are owner-confirmed disabled; already-running occurrences still need evidence reconciliation. No replacement production work was enabled while the Resident stop remains unverified.

Resident 2.x remains running on its prior installed release; the new adapter is not yet deployed. Current production observations and necessary historical staffing inputs still need SQL import/acquisition, followed by complete A029-B feature/forecast-input acceptance. The SQL statistics projection does not itself prove full staffing capability completion.

Online 2.x code is implemented as an adapter, not an authenticated/scheduled ChatGPT deployment. No production semantic execution is claimed. Hosted semantic integration, independent proposal readback, explicit defer handling and scheduler activation remain required before declaring Online 2.x complete.

No implementation batch is declared fully accepted or activated by this checkpoint. The existing 55-function targets and 13 implementation batches remain the scope; all other provider adapters remain unfinished. No 1.x runtime changes, provider sends, historical replay, or coexistence development occurred.
