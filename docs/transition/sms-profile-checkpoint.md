# SMS Online profile checkpoint

**Superseded: ABORTED / NOT ACCEPTED / NON-PRODUCTION.** The owner subsequently
directed containment of this separate identity and use of the existing Online and
Resident identities under the authoritative Batch 13 plan. Its executor and login
binding are disabled, capability renewal is disabled, and synthetic work was
reconciled without acceptance. Historical implementation and evidence are retained;
the enrollment scripts below are not instructions to reactivate it. No production
SMS effects or processing of the 19 held continuations were accepted or performed.

The following is the historical pre-abort checkpoint:

Owner authorized ONLINE_ADA_2X_SMS in sms.operations using the existing Online enrollment and hosted OAuth adapter pattern. A dedicated non-administrator SQL role, executor instance, production domain binding, public OAuth client and online-ada-2x-sms Edge Function are enrolled/deployed. Gmail source, configuration and domain remain unchanged.

Exactly three capabilities: ecos.2x.execute, semantic.interpret, db.governed_operations. The existing 24-hour capability lease / 12-hour renewal policy is bound to the SMS deployment evidence hash. No instance capacity increase.

Exactly twelve operations: executor.register, executor.heartbeat, work.next, work.package, work.renew, work.complete, work.fail, work.defer, work.release, semantic.proposal.submit, sms.continuation.complete, task.transition. Scoped read_record access is exposed for assigned communications, processing rows, occurrences, provider receipts and tasks. No approval.decide, provider result/write operation, Gmail operation or sms.continuation.enqueue grant.

Preflight verified the dedicated SQL login, exact capabilities/operation grants, no direct task table read/write or auth-schema access, unauthenticated endpoint rejection and OAuth discovery. Two synthetic fixtures are prepared; only those ten synthetic objects are granted to the new principal. The SMS work definition remains disabled. The 19 held production continuations are untouched.

PENDING: final ChatGPT connection creation / OAuth consent, then exactly two hosted end-to-end acceptance passes and independent PostgreSQL readback. No functional pass is claimed by this checkpoint. No provider calls or production SMS sends occurred. No production continuations may be migrated by this coding lane.

Private enrollment, deployment and fixture receipts remain in the existing restricted .local/sms2x-enrollment mechanism. No credential values are committed. The prepared ChatGPT public OAuth client requests openid, email and offline_access; no client secret is required.
