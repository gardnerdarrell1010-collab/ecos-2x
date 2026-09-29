# Governed semantic continuity

AI Memory remains. It is neither the operational database nor a backup. Stable memory_record
identifies scope/kind/business identity; immutable memory_version holds semantic statement,
operational meaning, provenance/effective date, sensitivity, retention reference, authoritative
references, explicit supersession, hash and compaction linkage. Active head is a mutable pointer
on memory_record, changed by compare-and-swap under lock; old versions are never modified.
Enforce one record/head per scope_type/scope_id/memory_kind and head belongs to same record/scope.

Future rolling continuity preserves the MEM-ECOS-000036 alias. Review-time v94 is evidence,
not a default new active head. Migrate verified current head/history only through quarantine.
Compaction reads current structured authority first, then applicable prior memory, then any
residual chat evidence. Manifest lists inputs, outputs, omitted refs/reasons and verifier.
Contradictions, missing refs, token/size limits and retrieval tests must pass before activation.
Do not reclassify an old narrative as an authoritative current business fact.

Bootstrap Package contains DB/schema version, governed context plus actual typed context
records, scoped active heads, unresolved exceptions, operation bindings and a bundled
closure of request/response JSON Schemas, capability vocabulary and relevant work. Schema
IDs alone are insufficient; bundle hashes and every transitive reference must resolve
offline. `verify_bootstrap` checks this boundary without contacting a schema host.
Apply principal/role/sensitivity filters to every included record and reference; a restricted
memory must not leak through its title, provenance or exception summary. Hash package bytes,
record as-of/version evidence and revalidate relevant versions when committing later.

Replacement-AI acceptance starts with only this package plus portable contracts, no ChatGPT
history or proprietary session. It must select valid work, submit a governed synthetic
proposal, commit/read back through the API and verify audit. This integration gate is pending.
