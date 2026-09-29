# Phase 2 vertical-slice evidence

These are representative replacements of control-plane mechanics, not retirement
acceptance for complete legacy workers. Business payloads, interpretations and provider
responses are synthetic. The operations execute against real PostgreSQL transactions.

| Required field | A025-style readiness | A008-style fast integrity |
|---|---|---|
| Legacy function | Claimability/readiness/priority selection | Expired execution integrity and safe recovery |
| Business outcome | One compatible owner receives due work | Abandoned work becomes recoverable without corrupting results |
| Legacy 1.x mechanism | Task Loop scoring/ready fields and worker claim records | Periodic integrity checks and repair handoff |
| 2.x surface | DATABASE_DETERMINISTIC | DATABASE_DETERMINISTIC |
| Trigger | Executor requests work | Bounded recovery cadence / discovered expiry |
| DB objects | work_occurrence, capability requirements/attestations, resource budgets/reservations, work_claim, execution_run | work_claim, execution_run, integrity_finding, repair_action, work_wakeup, executor_presence |
| Operation contract | work.next / existing work.claim; renew; complete | recovery.sweep; existing fenced completion/repair primitives |
| Work package | Occurrence/stage, minimal task, selected refs, operation and fence | Same bounded package on reclaimed work; no whole-table export |
| Failure behavior | Incompatible/blocked pair receives no claim; errors roll back | Old fence rejected; unrelated work remains available |
| Retry behavior | Later eligible request, governed retry_at and lease | Reclaim with larger claim version; bounded sweep restores wakeups |
| Idempotency | Same operation key returns same scoped result; duplicate owner prevented | Durable finding/repair records and work wakeup generation |
| Audit evidence | operation_audit, execution_event, immutable control_plane_event | integrity_finding, repair_action and recovery operation audit |
| Acceptance test | capability_compatible_atomic_claim, incompatible_capability_no_claim, both 15-session races | executor_loss_expired_fence_repair_readback, lost_transient_wakeup_recovered, Phase 1 expiry/five-stage crash tests |
| Retirement prerequisite | Broader readiness/order shadow parity and actual worker cutover approval | Full legacy integrity coverage, watchdog gates and explicit worker retirement approval |

| Required field | A023 -> A053 -> A054-style handoff | A027/A028-style transport |
|---|---|---|
| Legacy function | Receipt -> semantic interpretation -> deterministic commit | Outbound notification obligation/delivery |
| Business outcome | Interpretation becomes an audited governed business change | One logical notification/delivery result despite replay |
| Legacy 1.x mechanism | Staged records and scheduled semantic/deterministic worker handoff | Notification Queue/Deliveries, communications/provider workers |
| 2.x surface | ONLINE_SEMANTIC then DATABASE_DETERMINISTIC; explicit staged work | Deterministic synthetic adapter; Resident contract separately tested |
| Trigger | Synthetic receipt work, followed by committed semantic result/dependency | Committed governed task transition with synthetic notification policy |
| DB objects | work_context, stage_result, proposal_submission, work_dependency, work_wakeup, proposal/commit evidence | notification, delivery, provider_command, outbox_item, provider_attempt, provider_result |
| Operation contract | work.next, semantic.proposal.submit, work.complete, proposal.commit | claim_outbox, begin_synthetic_attempt, provider.result.record, ack_outbox |
| Work package | Minimal task/version refs; proposal.commit contract and prerequisite result hash on commit stage | Scoped synthetic command/request artifact references and stable idempotency key |
| Failure behavior | Proposal submission does not mutate task; invalid/stale/ambiguous items remain isolated | Unknown outcome requires reconciliation; no blind resend; provider calls are synthetic |
| Retry behavior | Immutable proposal/result can be reused; only incomplete stage is retried | Governed outbox lease recovery; reconciliation precedes acknowledged success |
| Idempotency | Proposal content hash and operation receipts; deterministic commit after matching result hash | Duplicate provider result produces one result/delivery; ACK only after durable result |
| Audit evidence | proposal_submission, immutable stage_result, proposal item commit evidence, task domain_event, operation_audit | notification/delivery, command/outbox/attempt/result and operation audit |
| Acceptance test | semantic_submission_immutable_no_business_mutation, semantic_to_deterministic_commit_hybrid_handoff | synthetic_notification_delivery_provider_outbox, synthetic_provider_duplicate_idempotency, synthetic_adapter_ack_after_durable_result |
| Retirement prerequisite | Real semantic executor/independent replacement-AI acceptance, representative business shadow and owner-approved cutover | Explicit real-provider authority, provider-specific reconciliation acceptance and worker cutover approval |

The integration source is scripts/phase2_integration.py; surface/security/resource/client
coverage is scripts/phase2_acceptance.py. Final clean evidence is clean-candidate-009.json.
Actual business interpretation is not embedded in SQL. No real SMS, Gmail, Drive, Toast,
Calendar, financial operation or production artifact deployment was performed.
