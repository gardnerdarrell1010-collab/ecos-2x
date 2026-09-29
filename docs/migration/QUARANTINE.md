# Typed migration boundary

No production extraction/import occurred in Phase 0. Review-time data-quality evidence:
55 workers, 641 keyed Tasks, 31,572 keyed Run Control rows, 115 duplicate Run IDs,
duplicates in notifications/deliveries/staging, column drift and compound statuses.
Forecast Performance had no populated rows. Verify current values via current bootstrap
governance only when extraction is separately undertaken.

Pipeline: read-only extraction -> immutable raw batch -> typed quarantine -> validation ->
identity reconciliation -> versioned transformation -> governed promotion. Never copy source
rows directly into normalized tables. Raw extracts are sensitive, access-controlled, encrypted
outside Git; every batch pins source registry/schema, field order, export instant/count/hash.

Use the complete family registry in `contracts/migration/legacy-mapping.json`. Preserve all
source rows, including collisions, by batch/locator/hash. Quarantine reason codes distinguish
duplicate legacy ID, missing ID, column drift, invalid type, unknown lifecycle, missing FK,
conflicting evidence and unresolved authority. Unrecognized compound status requires explicit
mapping; no fuzzy success matching. A duplicate of an identical row is still separate source
evidence until an approved reconciliation establishes aliasing or exclusion.

Promotion requires typed schema success, resolved identity/FKs, valid lifecycle, proven
source boundaries, approved transformations and expected target versions. Record target IDs,
transformation version, decisions, counts/hashes and business totals. Promotion key uniquely
binds batch/source locator/transform version; repeat promotion returns original result.
Reject new contradictory source content rather than overwriting a migrated target silently.
Raw/quarantine data is not operational authority and never feeds live effects directly.

Runtime rank, spreadsheet claims and noisy launcher history are rebuilt or archived. Tasks
retain obligations and typed schedules/approvals/evidence. Ingestion checkpoints require
provider proof; unknown sent status stays unknown. Unresolved staging is migrated only after
its own validation. Worker registry is solely a migration/acceptance artifact.

Before cutover: zero unclassified errors, every exclusion approved with evidence, reconciled
counts/financial totals/hashes, delta rehearsal and rollback proof. One authority switch
under explicit owner-approved freeze; never concurrent writers of the same business effect.
