# Complete worker instructions in work.package

Migration 41 adds one generic, append-only `ecos.work_instruction_version` store.
Each version references an existing work definition and stage. `work.instruction.publish`
requires the existing operations_api role, a principal operation grant, and exact object
grants for both definition and stage. Executors gain no publication authority. A stage
row lock serializes publication; expected_version prevents lost updates. SHA-256 is
verified against the exact UTF-8 instruction text. Prior versions cannot be changed or deleted.

The request is defined in contracts/worker-instructions. Set expected_version to zero
for initial publication, otherwise to the last published version. source_reference must
identify the preserved authoritative source. No trimming, newline conversion, summarizing,
or prompt transformation is performed by storage. Ada must preserve complete instructions;
any later authorized migration transformation requires its own source/equivalence evidence.

Every work.package (including the package inside work.next) now includes
functional_instructions: the entire version record, or null when not yet migrated.
The first package pins the current version to its existing claim, including absence.
Later publication cannot change that active claim's package; a later claim can obtain
the new version. No selector, executor, domain, schedule, or scoring behavior changes.
The original 32 KiB context bound remains; instructions have a separate 256 KiB UTF-8
storage bound (65,536 characters in the request). Package measurements include full text.
Existing Online JSON serialization and Resident package/client handling preserve the field.
Neither executor is granted arbitrary text execution or new handler behavior.

## Bounded evidence

One complete preserved Instructions field, chosen as the longest current TASK-AUTO
source, passed byte-for-byte work.next/work.package retrieval on a private disposable
PostgreSQL database: 15,936 UTF-8 bytes, zero transformations. The existing Resident
GovernedClient retrieved the same version. Append-only versioning, claim pinning, and
executor publication rejection passed in this one bounded check. No worker/provider
execution occurred. Source text was never placed in Git.

Migration 41 was applied and independently read back on the authoritative database.
All executors and definitions remain disabled, with zero live claims. No operational
worker definitions have been bulk migrated; Ada owns the remaining definition migration.
The dedicated Online OAuth transport is not available as a callable tool in this Codex
session, and no existing Online OAuth access/refresh credential was found in its enrollment
directory. Actual authenticated Online HTTP package consumption is therefore unverified;
static pass-through compatibility is not represented as hosted acceptance. No browser used.

The required repository check reported 98 passing tests, 26 skipped, and two unrelated
existing specimen errors (backup ciphertext minimum length and approval expires_at).
The bounded new SQL acceptance passed. Do not reopen accepted runtime parity or provider tests.
