# Bounded structural gaps — migration 35

PostgreSQL remains operational authority. This package changes contracts only; it does not migrate held operational records or enable provider sending.

## Accepted contract paths

Each new path passed two consecutive committed synthetic PostgreSQL runs with independent governed readback. Evidence: `docs/evidence/structural/acceptance.json`. Migration 35 is deployed and independently verified. Rollback-only compatibility checks preserved existing governed record representations/hashes and verified the required rejection boundaries.

- `party.put`: create or version-checked update of a preauthorized Party UUID. `party_kind` is explicitly `person` or `organization`. Existing unclassified Parties retain NULL and their existing read representation; no population was relabeled. Existing business IDs and crosswalks remain unchanged. An established kind cannot be silently changed.
- `relationship.put`: create or version-checked status/date/provenance update. Typed source/target references use existing Party, Project or Task UUIDs. Source system and source relationship ID form a unique identity. Identity/endpoints/type remain immutable. `ecos.read_record('relationship', id)` uses existing authorization.
- `approval.request`: create a pending approval bound to the current authorized subject hash. `expiration_mode=never` requires NULL expiry; `expires` requires a timestamp. Missing expiry with default expiring mode is rejected. Existing `approval.decide` retains authorization, version/hash checks and immutable decision evidence. This operation does not import or fabricate historical approvals.
- `sms.continuation.enqueue`: bind a verified Twilio SMS communication version to the existing communication_processing/work_occurrence architecture. The prepared `sms_continuation` definition is disabled. Its ONLINE_SEMANTIC stage requires existing execution, semantic.interpret and governed-operation capabilities.
- `sms.continuation.complete`: requires a valid existing claim fence, unchanged communication source, and a submitted semantic proposal citing that communication/version. It commits through the existing proposal engine and records processing completion. Ordinary governed work.complete finishes the occurrence. No SMS provider-send operation or alternative queue is added.
- `artifact.register`: the ordinary `(provider, provider_object_id)` unique identity remains enforced for records without an attachment discriminator. Only Gmail may carry a nonblank attachment_id; `(provider, provider_object_id, attachment_id)` is unique for those records. Existing UUIDs/crosswalks and legacy reads are preserved. The caller must supply a provider-supported attachment identity, never an inferred filename or guessed ordinal.

All writes go through ecos.operate. Per-operation permission, current principal/domain authority and preauthorized object grants are required. Create operations require a reserved UUID with an existing governed object grant; they do not grant themselves authority. Relationship endpoints and provenance references must also be authorized. No existing executor principal was granted new authority by the migration. Provenance is verified against source versions/hashes; immutable operation receipts retain committed results.

## Operational handoff

Executive Assistant Ada owns all population migration and scope provisioning under existing governance. Schema blockers are removed for the 10 Organizations, 8 Relationships, 47 approval-required records, and identity-resolved attachment Artifacts. Other source/effect/identity holds still apply; dependent Facts are eligible only after their subjects resolve. The 47 approvals must retain actual historical decision evidence; this package does not manufacture a new approval or expiration.

The 19 SMS continuations remain held for a routing decision. The sole enabled production Online principal is bound to gmail.operations; principal_domain has one row per principal. The 27 migrated SMS communications currently have no domain binding. Activating SMS requires an authorized existing executor/domain assignment before scope grants and definition enablement. No reassignment into Gmail and no new executor identity were made.

Gmail closure remains untouched: A001/A035/A010 ledger versions 8, A010 draft boundary only, 72 legacy candidates held, zero external sends. ECOS 1.x, Toast, memory rollover and held populations remain untouched.

## Reproduction

`scripts/structural_acceptance.py --pg-bin <existing PostgreSQL bin directory> --openssl <existing OpenSSL executable>` creates and stops a private disposable PostgreSQL instance, uses only synthetic fixtures, and runs two complete passes. It never connects to production. Do not rerun accepted paths merely for confidence.
