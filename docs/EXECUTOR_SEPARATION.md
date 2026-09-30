# Autonomous executor separation

Implemented source validation; live scheduler/enrollment acceptance is pending.
This does not constitute Wave 1 transfer or Online Ada 2.x acceptance.

| Identity | Autonomous work source | Required generation capability |
|---|---|---|
| ONLINE_ADA_1X | SHEETS_TASK_LOOP | ecos.2x.execute forbidden |
| ONLINE_ADA_2X | POSTGRESQL | ecos.2x.execute required |
| RESIDENT_ADA_1X_HOME01 | SHEETS_TASK_LOOP | ecos.2x.execute forbidden |
| RESIDENT_ADA_2X_HOME01 | POSTGRESQL | ecos.2x.execute required |

`runtime/executor_profiles.py` rejects mixed work sources, unknown/ambiguous
autonomous identities, invalid capability versions, and generation-capability
violations. It also validates distinct resolved Resident resource paths and exact
business-capability subsets. No aliasing or fallback between control planes is
permitted. Interactive Ada is outside this autonomous validator; interactive
business mutations still require current domain authority and fencing.

Resident 2.x invokes the validator at construction, before state creation or
database connection. Its heartbeat now includes generation, control plane,
generation-specific display name, and domain. Existing SQL domain/epoch checks
remain authoritative and unchanged. Local validation does not grant SQL access.
The synthetic and Wave 1 shadow enrollment scripts now explicitly declare the
SQL-only work source and attest the generation capability through their existing
enrollment paths. Those scripts have not been run against production as part of
this source change. Existing saved configurations without these fields fail
closed and require governed re-enrollment/configuration before restart.

Eight new offline test methods cover all four profile invariants, cross-source
rejection, aliases, exact business capability subsets/versions, resource path
collisions, generation labels, and Resident rejection before I/O. Full offline
suite: 71 passed, 26 historical integration placeholders skipped. These are not
actual cross-generation SQL claim attempts or a live coexistence proof.

## Separate Online 2.x entry point

`ONLINE_ADA_2X_ENTRYPOINT.md` is the prepared launcher instruction. It is not a
scheduled job and contains no fabricated principal, executor UUID, credential,
registration receipt, heartbeat, or semantic completion evidence. Bind it only
to a separately enrolled Online 2.x principal with accepted operation access and
verified current capabilities. No local reasoning substitute is authorized.

Use the existing ChatGPT Online scheduler. The desired timing is one opportunity
per four minutes, with distinct generations each receiving an eight-minute
interval and the 2.x anchor four minutes after the 1.x anchor. Keep the phase
continuous across hour boundaries: 60 is not divisible by eight, so fixed hourly
minute lists do not produce strict continuous alternation. Actual provider
schedule support and existing launcher identities must be inspected before
incremental changes; no recurrence rule has been fabricated or installed.

First introduce a separately identifiable 2.x launcher restricted to synthetic
or explicitly migrated domains. Verify identity/profile/registration/heartbeat,
work.next, work.package, semantic completion and recovery before relying on it
for a migrated semantic domain. Transition existing 1.x launchers incrementally
only after exact provider readback. Never mass-disable the existing set.

## Current live evidence and blockers

Fresh active pointer: Resident 1.x remains 1.0.011 at the existing D-drive slot.
Current 1.x Settings still name the profiles SCHEDULED_ADA and RESIDENT_ADA.
Those live profiles/entry points have not yet been renamed or given new guards.
The 2.x runtime directory exists separately at C:/ECOS/ecos-2x/runtime/resident2x.
Source separation is not proof of two healthy simultaneous running processes.

No callable canonical ChatGPT automation administration tool is exposed in this
session. The available Codex automation tool manages a different scheduler.
Browser fallback reaches a logged-out ChatGPT session. Therefore existing Online
launchers, actual cadence and offsets could not be inventoried or changed.
No substitute Codex/Windows/Make scheduler was created.

The user refers to a preceding instruction titled CAPABILITY ROUTING + DOMAIN
AUTHORITY EPOCH that is absent from this chat. Its exact requirements were
requested before dependent integration. The previous claim/disable commit race
remains open; see docs/claim-admission/CLAIM_ADMISSION_FINDINGS.md. Online 2.x
semantic acceptance is not itself a prerequisite for Resident-only Wave 1.

Pending: authoritative 1.x profile/entry-point enforcement; separately enrolled
Online 2.x principal and connector entry point; canonical scheduler configuration;
live SQL cross-generation attempts; resolved runtime resource coexistence proof;
live monitoring readback; missing routing/epoch instruction; prior Wave 1 gates.
