# Durable events, communications and effects

Every event envelope has immutable UUID, type, schema_version, aggregate type/ID, correlation,
causation, created_at and constrained payload. Event types and payload variants are registered
together. API validation never substitutes for database invariants. Domain state, audit event,
outbox and provider command intent commit in one transaction. No network call occurs inside
that transaction. LISTEN/NOTIFY, Realtime and webhooks only accelerate a durable polling sweep.

Outbox consumers claim short leases, checkpoint delivery and use a stable dedupe key. Transport
is at-least-once; logical effects are deduplicated or reconciled. Do not claim universal exactly
once external execution. Per-provider native key semantics/expiry must be verified before use.

| Failure | Required recovery |
|---|---|
| DB commit, consumer crash | pending durable row survives; sweep claims/reclaims; no transient message is required |
| Provider success, DB result failure | mark/recover unknown_outcome; query provider by stable key/ID/history/hash, persist proof, never blindly resend |
| Duplicate webhook | durable receipt unique provider/account/dedupe key; replay returns stored receipt; conflicting same key/hash is quarantined |
| Ambiguous timeout/outcome | retain command intent and attempts; reconcile or owner decision; blocked effects cannot become generic retry |
| Delayed/out-of-order status | append raw evidence, compare provider version/time and legal state; do not regress delivered/succeeded from stale accepted/failed notices |

An attempt is immutable evidence of a request; append later results/status observations rather
than rewriting an old response. `reconciled` is not itself proof of success: retain explicit
reconciled_outcome (succeeded/failed/no_effect) and evidence. A retry after proven no effect
uses the same command/key and new attempt; a new intent requires a new governed command.
Retry policy has capped exponential backoff/jitter and attempt limits. Validation/permission
errors are permanent until corrected; uncertain outcomes are reconciliation work, not transient
failures. Terminal exhaustion creates a dead_letter_item and owner review.

Inbound: verified provider webhook/poll -> durable immutable receipt -> normalization ->
communication_processing -> semantic stage only when required -> deterministic commit ->
downstream obligations/events. Preserve exact text, channel metadata, source ID/time and hash.
ACK receipt ingestion only after durability; business-review ACK only after commit proof.

Outbound: business transaction -> notification -> recipient/channel delivery -> provider
command/outbox -> deterministic transport -> immutable attempt/result -> delivery projection.
Delivery policy binds exact recipient, destination, thread, signature/content and approval.
Gmail remains draft-first pending standing send authority. A010/A027/A028 share this pipeline;
channel-specific evidence and transport rules remain distinct. No three generic queue hops.

Target pickup: provider <5 seconds, semantic <1 minute, schedule/threshold <1 minute,
recovery sweep 1–5 minutes; these are acceptance targets, not measured Phase 0 performance.
Provider-specific boundaries and replacements are in `contracts/providers/boundaries.json`.
