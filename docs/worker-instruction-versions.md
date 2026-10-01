# Worker instruction configuration

Migration 42 removes `work.instruction.publish` from the active operation catalog,
revokes its grants, and removes its dispatcher implementation. The historical request
schema is deprecated. Immutable instruction versions, claim pins, operation receipts,
and automatic `work.package.functional_instructions` retrieval are preserved.

Worker instructions are configuration data. Use the same authenticated administrative
connection and configuration lock as existing definition/stage migration scripts.
No new runtime operation, connector, permission, executor, domain, or approval is needed.
Administrative writes record the actual database role plus a configuration correlation ID;
historical principal attribution is preserved. No executor identity is fabricated.

## Deterministic bulk path for Ada migration tooling

Create a private JSON mapping array with one item per approved existing stage:
`source_worker_id`, `work_definition_id`, `stage_definition_id`.
Use exact preserved Task Loop worker IDs and existing PostgreSQL UUIDs; do not infer mappings.

Prepare without writes:

```powershell
& C:\ECOS\ecos-2x\.venv\Scripts\python.exe C:\ECOS\ecos-2x\scripts\configure_worker_instructions.py --mapping C:\path\mapping.json --plan C:\path\instruction-plan.json
```

Apply the exact saved plan through existing migration authority:

```powershell
& C:\ECOS\ecos-2x\.venv\Scripts\python.exe C:\ECOS\ecos-2x\scripts\configure_worker_instructions.py --plan C:\path\instruction-plan.json --apply
```

The plan pins source batch/locator, full instruction SHA-256, definition/stage record
versions, current instruction version, and capability-requirement hash. Apply resolves
text from preserved PostgreSQL source, checks every item before writing, and commits
the entire batch atomically. It increments each definition configuration record version
once, each affected stage record version once, and appends one immutable instruction
version per stage. It changes no routing, capabilities, schedules, or enabled flags.
An exact plan replay produces no duplicate version; drift fails closed. Independent
readback checks complete text, versions, linkage, attribution, capabilities, and all-off state.
A committed write with failed readback must be reconciled by replaying that same plan.

For existing creation/configuration scripts, `plan(db, mapping)` and
`configure(db, document)` can run in the same transaction immediately after their normal
work_definition/work_stage_definition/stage_capability_requirement writes. Run
`readback(db, document)` through a separate connection after commit. No separate publish step.
The CLI attaches instructions to existing definitions; it does not invent missing definitions.

The bulk path preserves exact source text, including whitespace and Unicode. By default
it stores that text unchanged. The optional `--postgresql-access` planning flag prepends
one fixed operational-storage binding while retaining the full original body byte-for-byte.
The plan pins both the original and stored SHA-256. This binding changes only ECOS
operational access; it removes no responsibility and claims no SQL equivalence.
Missing/ambiguous mappings or absent complete source text fail closed. Keep plans and
source evidence private. No path enables production.

The owner-authorized missing-definition configuration is implemented in
`scripts/create_missing_worker_definitions.py`. It creates only the bounded 25 missing
canonical definitions from preserved source and current approved conversion targets,
with instructions in the same transaction. Definitions remain disabled. Capability
requirements do not grant executor attestations or provider authority. Missing handlers,
source retry defaults, and SQL equivalence remain explicit runtime gaps; configuration
readback is not functional acceptance.

Current bounded readback established 37 distinct instruction-linked definitions (12
previous and 25 newly configured), with 62 immutable instruction rows. The new 25
current versions also passed exact `work.package` retrieval in isolated fixtures.
No production launcher or provider was run. The 15 SQL-native functions remain
incomplete; migration 43 supplies only the A041 execution-activity projection component.
A008/A022 retain SQL_NATIVE as primary targets; owner-authorized delegation is limited
to their retained semantic/provider steps and is not yet implemented or accepted.

## Verification

Bounded disposable PostgreSQL acceptance passed configuration plus independent readback,
append-only versions, exact replay, current-version work.package retrieval, and removal
of the separate operation. Zero provider/business effects. Production remains off.
The earlier migration-41 lossless proof of the complete 15,936-byte legacy instruction
is historical evidence only; its script explicitly tests that historical migration boundary.
