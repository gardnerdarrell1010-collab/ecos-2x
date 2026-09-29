# Governed operations and proposal boundary

OpenAPI 3.1.1 in `contracts/api/openapi.json` and strict JSON Schema 2020-12 payloads
define one operations contract shared by Online, Resident and Interactive executors.
Phase 0 serves no endpoint. No endpoint accepts table names, SQL, arbitrary column patches
or credentials. Schema extension requires explicit versioning, tests and an allowlist entry.

Every call is authenticated. The API derives principal and executor instance from verified
credentials; supplied context must match, never authorize itself. Role checks are only a
coarse gate: enforce object/sensitivity scope, capability attestation, actor authority,
current approval, subject hash/version and fences in the deterministic transaction.
Interactive human presence is evidence, not bypass authority. Use least-privilege DB roles:
ecos_owner, migration_runner, operations_api, executor, provider_adapter, auditor,
backup_operator and read_only_analytics. Executors receive no table-owner credentials.
Application roles cannot directly UPDATE governed tables or edit immutable evidence.

Request idempotency is unique by principal + operation + key. Persist canonical request hash,
durable operation result and events in the same transaction. Same key and bytes returns
original outcome; different bytes returns 409 idempotency_conflict. A no-candidate claim is
also an idempotent result: polling again requires a new key. Never retire keys while a
provider effect or retained request could still replay; production retention is unresolved.

Responses are versioned. Invalid shape/format -> 400; missing/invalid credential -> 401;
insufficient authority/scope -> 403; stale version, invalid transition, fence or policy
conflict -> 409; unexpected failure -> 500 with no secret disclosure. Machine reason codes
and correlation IDs accompany failures. Retryability is explicit, not inferred from prose.

## Semantic proposal processing

The immutable proposal includes source refs, expected versions, governed operations, evidence,
confidence in integer basis points or null, ambiguity, correlation ID and content hash.
The hash fixes the whole proposal (minus its hash field) before deterministic validation.
Only the allowlisted proposal subset can be proposed; approval decisions, arbitrary mutation,
provider sends and memory activation are not automatically semantic authority.

Validate envelope/size/schema/hash first. Envelope corruption rejects the entire proposal.
Structurally malformed items reject the envelope; partial acceptance applies to independent
schema-valid items with differing business validity. For an envelope-valid batch, validate
each item (operation allowlist, authority,
references/expected-version coverage, conflicting/unverified evidence, and ambiguity).
Each item and all its governed operations are atomic. Independent valid siblings may commit
even if another is stale/invalid; item dependency DAGs block dependents of rejected siblings.
Item IDs are unique and dependency cycles/unknown references fail. Store item results under
proposal ID + item ID + immutable proposal hash; lock target rows and recheck source versions
inside each commit. Accepted operations, audit, history, outbox and item checkpoint commit
together. Preserve expected versions for every read that affects a decision; do not treat
the top-level list as permission to omit an item's actual dependencies.
The top-level expected-version list must equal the union of per-item dependencies.

The Phase 0 pure preflight oracle classifies freshness/ambiguity/conflicts/replays only.
It is not authorization, full business validation or a commit engine; Phase 1 implements
and tests these transaction checks. Restart uses stored proposal and per-item checkpoint;
committed items return evidence without fresh semantic reinterpretation. Changing evidence
requires a new proposal linked to the original, not overwriting a verified output.

A023 receipt/package -> A053 proposal -> A054 deterministic commit/ACK is one application
of the generic stages. Commit creates an ACK provider_command only after durable result;
provider ACK success with persistence failure is reconciled by the same command identity.

## Phase 1 implementation note

Phase 1 SQL entrypoint is ecos.operate(text,jsonb), preserving all ten registry names. Context is authenticated by bound SQL role, never by request principal alone. Object/sensitivity authorization is checked before replay; scoped readback is ecos.read_record. See ../PHASE1_IMPLEMENTATION.md and ../PHASE1_SECURITY_PORTABILITY.md.
