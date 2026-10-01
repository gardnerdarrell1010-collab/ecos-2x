# Existing operational function hookup

This package implements the governed paths for A015, A016, A018, A024,
A027, A028, A031 and A036 using the existing Online and Resident identities.
Core records use explicit object grants without a domain. Provider paths retain
their existing domain checks. No new executor, queue or scheduler is introduced.

Each path passed two internal end-to-end runs on disposable PostgreSQL, with
independent readback and no external provider effects. These are internal
functional results, not evidence that the production runtime is installed.

| Path | Verified behavior |
|---|---|
| A015 / A016 / A024 | Scoped review, semantic commit, notification deduplication, completion and recurrence |
| A018 | Encrypted scoped export, immutable manifest, decrypted parity, completion and recurrence |
| A027 | Existing queue LIST/GET, receipt and communication persistence, readback before exact ACK |
| A028 | Existing Twilio adapter, admission governance, isolated delivery outcomes, SID readback, ambiguous-effect hold |
| A031 | Communication handoff, semantic proposal, governed mutation, notification, processing completion |
| A036 | Read-only Calendar evidence, governed review and conditional notification |

Completion-relative cadences are preserved: A015 30 minutes, A016 2 hours,
A018 6 hours, A024 4 minutes, A027/A028 5 minutes, A036 15 minutes.
A031 is event-driven. Only successful completion generates the next periodic
occurrence; unresolved provider effects remain held through existing recovery.

Deployment order: checkpoint the source; configure the private continuity
encryption key and deploy the existing Online function; validate the activation
transaction with `--verify-only`; apply the Online phase; install the prepared
release/configuration through the existing Administrator Gmail Resident updater;
then activate the Resident phase and independently read back eligibility.
The updater preserves Toast and existing identity/configuration fields.

The continuity key is a server-side secret named
`ECOS_CONTINUITY_ENCRYPTION_KEY`. Preserve it in restricted recovery material.
The checkpoint is a scoped export, not a full database backup or a completed
restore test. No memory rollover is performed.

Production acceptance must be recorded only after the corresponding runtime
and eligibility checks. Historical held Gmail/SMS effects are not replayed.
