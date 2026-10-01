# Operational core runtime hookup

The current eight CONVERT-2X mappings were read from PostgreSQL. No legacy behavior
was rediscovered and no conversion targets were changed.

The existing Online transport now exposes `sms.continuation.complete` and governed
record reads for the mapped SMS context. The same enrolled Online principal has
the completion operation and `task.transition` grant for scoped proposals. No
object grants, executor identities, domains or work-definition enabled flags changed.

Exactly two internal tests passed through the changed transport request boundary,
existing SQL claim/proposal/completion path and independent task/processing/work
readback on a disposable database. These tests establish the internal completion
branch only. They do not establish full A031 functional acceptance, production
notification creation, hosted ChatGPT invocation or semantic quality.

The existing Edge Function deployment succeeded. Full function acceptance remains
pending because the following required runtime primitives are absent:

| Function | Existing primitive retained | Missing minimum integration |
| --- | --- | --- |
| A027 | Resident authenticated HTTP | Governed Twilio receipt/communication intake and exact persisted-item readback operation callable by its Resident handler before ACK |
| A028 | Resident Twilio send and provider result recording | Governed eligible-delivery selection and immutable approved dispatch begin binding, including command/request persistence and ambiguity holds |
| A031 | SMS continuation and semantic proposal SQL | Full mapped outbound notification/delivery creation operation; completion exposure alone cannot implement this conditional branch |
| A036 | Canonical provider.calendar capability | Actual Calendar read adapter exposed to existing Online; governed deduplicated notification/delivery creation and downstream handoff |
| A015 | Semantic proposals and task transitions | Scoped full-population task/context selection and governed production notification/delivery creation |
| A016 | Accepted Gmail evidence path | Scoped outstanding-request/reply selection and governed deduplicated follow-up notification/delivery creation |
| A024 | Existing work/package/proposal/task operations | Scoped backlog/context selection, governed notification/delivery creation and business-task-to-specialized-work handoff |
| A018 | Typed export/backup/restore/artifact records | Callable governed continuity checkpoint/export operation producing and verifying the mapped incremental manifest and recovery-head linkage |

The database contains notification/delivery and continuity tables, but the current
operation catalog has no production notification/delivery creation or continuity
checkpoint operation. The existing notification policy helper creates synthetic
fixture delivery commands; it is not substituted for production notification logic.
No capability was attested solely because its catalog entry exists.

A029, A034, the disabled separate SMS identity and all disabled acceptance definitions
were left unchanged. No provider effects or production backlog processing occurred.
No additional function is marked accepted by this checkpoint.
