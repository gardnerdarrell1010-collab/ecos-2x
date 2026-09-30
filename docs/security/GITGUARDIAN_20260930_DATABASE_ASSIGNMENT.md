# GitGuardian database-assignment alert â€” 2026-09-30

Status: FALSE_POSITIVE / RESOLVED_BY_EVIDENCE. Investigation closed by explicit
owner decision on 2026-09-30. Credential rotation and Git-history rewriting are
not required. GitGuardian dashboard status was not modified by Codex.

Alert timestamp: 2026-09-30 05:50:39 UTC.
Alert commit: `22102337fa676a8ce357d4d6ea1bfabe975468ce`.
Repository: `gardnerdarrell1010-collab/ecos-2x`, PUBLIC, verified through the
authenticated GitHub repository API.
The actual GitGuardian email links to diff anchor
`997f6c97947e40d16ffd29fe25ea03d8895e392061234bd58fa9f84bd71c54a4R134`.
SHA-256 comparison of the changed filenames identifies
`scripts/phase1_recovery_completion.py`, line 134.

## Source classification

This script exports a consistent PostgreSQL snapshot and verifies a disposable
local restore for Phase 1 recovery acceptance. The referenced line invokes the
native dump process. The surrounding line 132 sets its database environment.
AST inspection proves that the password argument is an Attribute expression,
not a string literal. It resolves the password previously loaded by the existing
SessionTarget from the approved restricted artifact materialization. The local
restore password is generated at runtime, not embedded in source.

The surrounding source-expression fingerprint is `6dc85148379892bf` (SHA-256
prefix). No detected value or credential is reproduced here. In-memory comparison
proved this expression differs from the active approved database credential.
An authentication attempt treating this expression as a password was rejected.
This is a diagnostic test of a source expression, NOT proof that a compromised
credential was revoked. Exact GitGuardian matched bytes were unavailable.

## Bounded exposure and continuity checks

The approved restricted-artifact resolver successfully connected using TLS
verify-full to the configured ECOS project `loonpojawpfagzobxoko`. Expected
database and all three ECOS schemas were present. The live migration ledger
was 23; all applied migration names and hashes matched source. The governed
operation entrypoint was present. No live SQL write or enrollment occurred.

In-memory exact comparisons, including URL-encoded credential variants, found
zero occurrences of the active approved credential in current tracked source,
the current diff, or 426 reachable Git history blobs. A bounded database-password
literal/credential-bearing URI scan found zero candidates in those blobs and
current tracked files. These results establish absence of this active credential;
they do not substitute for obtaining the detector's exact finding.

The alerted commit is reachable from main, codex/phase-1-postgres-foundation,
codex/phase-2-control-plane, codex/resident-2x-runtime, codex/wave1-toast and
ecos-2x-phase1-accepted. Remote heads/tags were freshly fetched and enumerated.
Authenticated GitHub secret-scanning alerts returned an empty list; GitHub is
not a substitute for GitGuardian's own incident record.

Fresh continuity verification: 76 offline tests passed (26 historical integration
placeholders skipped). Existing disposable PostgreSQL Phase 1 and Phase 2,
domain-authority, Wave 1 batch, authority-effect and concurrency checks passed.
This executed no live Wave 1 work. Capability and authority source remains intact.

## Final disposition

The owner accepts the runtime password reference/expression as a false positive
based on the completed investigation and provider evidence. Do not reopen absent
new contradictory evidence. No credential rotation, history rewrite, or secret
source change is required or performed.

Fresh advisor verification returned seven INFO rls_enabled_no_policy findings
and no warning/error findings. All seven tables have RLS enabled, no policies,
and no anon/authenticated table privileges. Migrations 21-23 access these internal
tables through accepted governed server-side boundaries. Classification:
EXPECTED_DENY_BY_DEFAULT / NO_REMEDIATION_REQUIRED. No policies were added.

The affected tables are ecos.toast_batch, ecos.toast_checkpoint,
ecos.toast_closed_date, ecos_meta.domain_authority,
ecos_meta.domain_authority_event, ecos_meta.object_domain and
ecos_meta.principal_domain. Advisor reference:
https://supabase.com/docs/guides/database/database-linter?lint=0008_rls_enabled_no_policy

The old HEAD-pinned Administrator preflight is not reusable unchanged. A fresh
read-only preflight follows successful CI at the final clean Wave 1 HEAD.
