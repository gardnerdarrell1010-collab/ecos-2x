# Identity, naming and types

Use singular snake_case relations/columns in private `ecos` and `ecos_migration` schemas;
`ecos_meta` contains migration metadata. Index names identify relation, keys and invariant.
Migrations are six-digit contiguous versions plus descriptive snake_case filename, immutable
after application. Views use `v_`; procedures use verb_object. No names contain legacy worker IDs.

| Concern | Contract / future SQL constraint |
|---|---|
| Internal identity | UUIDv4 generated independently of provider/legacy IDs; `uuid PRIMARY KEY` |
| Business ID | readable stable string, unique `(entity_type, business_id)` for new canonical records; aliases separate |
| Legacy identity | nonunique legacy string; unique `(source_system, source_family, source_batch_id, source_locator)`; explicit resolution maps to target UUID |
| Provider identity | opaque text unique `(provider, account_scope, object_type, provider_object_id)` where available |
| Correlation | UUID per originating business interaction; propagates across all stages |
| Causation | UUID of immediate event/command; null only for originating action; validate reference type |
| Event | immutable independent UUID, no reuse as aggregate identity; event schema and timestamp required |
| Execution | UUID run per attempt; UUID claim + monotonic bigint claim_version + random UUID fence_token |
| Idempotency | unique `(principal_id, operation, key)` with request hash/result; provider unique `(provider, account_scope, command_type, key)` |
| Occurrence | unique `(work_definition_id, definition_version, stage_definition_id, occurrence_key)` |

Duplicate legacy IDs are not silently dropped, deduped or treated as valid unique source
keys. Preserve every source row by immutable batch/locator/hash; explicitly adjudicate
same-entity aliases versus different entities. Source locators have meaning only within
a frozen batch; spreadsheet row number alone is not durable identity.

PostgreSQL types: `uuid` identities, `timestamptz` instants, `date` business dates,
`text` IANA timezone alongside recurrence, `bigint` counters/versions/byte counts,
`boolean` gates, exact `numeric` financial/scientific values with explicit unit/currency.
Never use floating point money. JSON API decimals use decimal strings when introduced.
JSON contract counts are integers. Null means absent/unknown, never zero or empty string.

Lifecycle fields use `text CHECK` or reference tables generated from controlled vocabulary,
not PostgreSQL enums requiring awkward lifecycle migrations. Core relations, foreign keys,
versions and states are typed columns. `jsonb` is for schema-validated payloads; it does not
replace relational identity or integrity. FKs use RESTRICT for evidence/business records;
no cascading destruction of immutable evidence. Bounded telemetry retention needs owner policy.

All mutable aggregates have positive record_version incremented once per governed change;
optimistic mutations include expected version and compare under row lock. Immutable events,
decisions, results, memory versions and raw extraction batches prohibit UPDATE/DELETE for
application roles. Archive/removal, if approved later, is separately governed and audited.

Hash profile `ecos-json-v1`: exclude only top-level `content_hash`, UTF-8 JSON, no BOM or
whitespace, string keys sorted by Unicode code point, unescaped Unicode, integer numeric
values only, booleans/null preserved. No Unicode normalization. SHA-256 lowercase hex.
This explicit cross-language profile is not RFC 8785. Raw files/provider payloads use
SHA-256 over exact bytes. Preserve original bytes and algorithm/version with evidence.
