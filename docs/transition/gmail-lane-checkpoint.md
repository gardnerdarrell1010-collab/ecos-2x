# Gmail completion candidate: activation blocked by topology decision

The owner renewed Gmail OAuth. One credential verification and mailbox identity check passed without printing credential values. This replaces the prior invalid_grant blocker.

Migration 32, four Gmail operation contracts, an Online tool module, and a Resident draft handler are prepared. The migration compiled in a rolled-back transaction; it is NOT applied. The Online module is NOT registered or deployed, and the Resident handler is NOT installed. Prepared definitions remain disabled. These are implementation candidates, not functional acceptance.

The candidate uses existing claims, provider receipts, communications, processing, semantic proposals, approvals, provider commands/attempts/results and completion. Dependencies gate semantic work on intake completion and draft work on semantic completion. The handler supports draft.create only, journals uncertain effects, and has no send path. Draft approval and provider readback remain unproven end to end.

Fresh PostgreSQL configuration shows maximum_instances=1 for RESIDENT_DETERMINISTIC_PROVIDER. The production Resident principal is bound to toast.acquisition; principal_domain permits one domain per principal. Gmail cannot be enrolled as another domain on that principal without changing this model. No policy, principal binding, Toast runtime or accepted executor was changed. Owner decision requested: permit a second Gmail-only profile of the existing Resident runtime and maximum_instances=2, or retain one instance and provide architecture direction.

Pass 1 and Pass 2 have NOT run. A001, A035 and A010 remain pending; A017 remains retired and untouched. No Gmail mutation, external send or backlog release occurred. The existing backlog predicate remains only a predicate; exact eligibility and migration/re-enqueue remain unfinished. Only Gmail ledger checkpoint metadata is updated; no function is marked accepted. Do not apply or activate this candidate until the topology decision and remaining integration validation are complete.
