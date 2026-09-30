# ECOS 2.x dependency-aware migration waves

Planning only. **13 functional waves, followed by T14 shared-support retirement.** No worker is paused, no provider effect is enabled, and production authority remains 1.x. This plan applies the existing 55-worker disposition; it does not replace or regenerate that analysis.

## Evidence and limits

Planning source HEAD: `2426e73bd63970a5f7f92d36b3fccc23375034a8`. Source artifact: [`contracts/migration/worker-dispositions.json`](../contracts/migration/worker-dispositions.json). All 55 IDs are assigned: 42 functional-wave workers, 10 support-only workers (A003 plus the nine-worker global cohort), and three historical candidates. Classification labels below are copied from the registry; explanations here concern sequencing only.

The appendix and architecture review already document the business chains. The previously retrieved Workflow Dependencies add ordering, soft-input, freshness and mutual-exclusion semantics. The JSON contains normalized relationship evidence and SHA-256 source pins, not raw production rows. The repository does not contain a complete live consumer graph. Therefore explicit edges are distinguished from conservative support closure: every non-retired-at-review worker is retained as a potential consumer of global support. Unknown finite Tasks, manual commands or external consumers veto retirement; no Enabled state is inferred.

Current readiness is bounded by [Resident disposition delta](RESIDENT2X_DISPOSITION_DELTA.md) and [Phase 2 slices](PHASE2_VERTICAL_SLICES.md): SQL control mechanics and three synthetic Resident capability classes passed; real provider adapters, a deployed Online semantic runtime, missing projections and operational cutover have not passed. Migration 20 line 346 still enforces development / non_production / provider-effects-disabled.

## Recommended first three

| Rank | Domain | Evidence difference |
|---|---|---|
| 1 | Toast acquisition (A029/A047) | Deterministic provider reads, reusable normalization, small source-output ownership; no Online dependency. Preserve A029-B rather than absorb it early. |
| 2 | Canonical publication (A032) | Narrow one-owner deterministic boundary and existing hash/readback, but public alias changes increase side-effect risk. |
| 3 | Social planning (A033) | Small functional scope and no publication approval implied, but actual Online executor and shared Task ownership are still missing. |

**Wave 1 is A029 + A047, not A029-B.** Keep the existing feature producer and its staffing consumers in 1.x until W4. The new acquisition owner must reproduce their exact verified input artifact. This is a real business acquisition function, not another Hello World acceptance. If that interface cannot be preserved, W1 is blocked or must merge with W4; do not improvise a parallel data authority.

## Transfer gates applying to every wave

**G1.** Production authority boundary: current ecos.operate rejects anything except development/non_production/provider-effects-disabled (migration 20 line 346). Separately authorize and accept a production-safe operation boundary, enrollment and deployment; never remove the guard as a shortcut or treat a flag flip as acceptance.

**G2.** Domain ownership: map every affected record/artifact/provider target and entry point to one executor authority. Enforce at selection, claim and pre-effect/commit, including generic A024, direct commands and stale queued work. Shared Tasks must have a single versioned write owner; cross-domain requests go to that owner, never to two writable replicas. Missing object-scope partition or an unenumerated mutator blocks that transfer.

**G3.** Input/output coexistence: preserve exact artifact/schema/hash/freshness contracts with read-only consumers. Where commands cross architectures, use an accepted idempotent handoff to the sole domain owner with committed result read-back; no dual-write control store. These adapters are required build work, not existing implementation claims. If handoff cannot be proved, defer or merge the affected waves.

**G4.** Operational runtime: supervise Resident and deploy Online only when required; capability/operation/object scope attestation, expiring credentials, heartbeat, recurrence creation, recovery cadence and independent outage alert must be accepted. Hello World and loopback HTTP prove foundations only.

**G5.** Transfer: exact preimage/config/code hashes and backups; stop admission for complete legacy functional set and drain claims/attempts. Reconcile UNKNOWN effects and disable all legacy side-effect paths. Establish the sole new owner, enable complete new stage set, independently verify committed/provider output. No overlap; do not force-kill a valid owner.

**G6.** Acceptance/rollback: satisfy this wave and existing disposition tests, representative schedule window and all downstream compatibility tests. Failed acceptance stops/drains new effects, reconciles outcomes and reverses ownership as one domain. Rollback is version-aware, never a blind provider replay or database downgrade.

**G7.** Dependency/retirement refresh: immediately before each transfer, verify current bounded consumer/entry-point inventory and provider/config versions. This plan is source-bounded, not proof of live Enabled state. Any additional consumer blocks retirement or moves its last-consumer wave later. All shared 1.x infrastructure stays until the conservative closure and non-worker workloads are drained.

## Sequence overview

| Wave | Capability domain | Complete functional pause set | Risk |
|---|---|---|---|
| W1 | Toast closed-actual acquisition and dashboard source facts | A029, A047 | Low provider-effect risk; medium data/compatibility risk. No live-transfer acceptance yet. |
| W2 | Canonical artifact publication | A032 | Medium: externally visible releases, but narrow deterministic ownership. |
| W3 | Social content planning | A033 | Low transport risk; medium semantic and shared-record risk. |
| W4 | Staffing features, forecasts, near-term analysis and feedback | A029-B, A019, A020, A021 | Medium: operational staffing decisions, longitudinal acceptance required. |
| W5 | Mail and Drive intake, classification and filing | A001, A002, A007, A035 | High: many shared objects and provider mutations. |
| W6 | Task owner review receipt, interpretation and commit/ACK | A023, A053, A054 | High: business writes and irreversible ACK. |
| W7 | Governed documentation and review | A006 | High: controlled documents and recipient distribution. |
| W8 | Life and Business dashboard sources, assembly and canonical materialization | A026, A045, A046, A048, A049, A050, A051, A052 | High: financial interpretation, privacy and canonical artifacts. |
| W9 | System status projection, package and canonical rendering | A022, A037, A038, A039, A040, A041, A042, A043, A044 | Medium: false confidence/outage visibility and publication correctness. |
| W10 | Executive briefing | A004 | Medium: executive interpretation and delivery duplication. |
| W11 | Incremental semantic continuity | A018 | High: recovery knowledge and mixed backup boundary. |
| W12 | Task coverage, owner routing and request follow-up | A015, A016 | High: broad Task and communication coupling. |
| W13 | Inbound SMS, calendar reminders and shared notification delivery | A010, A027, A028, A031, A036 | High: irreversible communications and provider ACK. |

Every wave retains **A005, A008, A009, A011, A012, A013, A014, A024 and A025 through T14**. In particular, SQL-native ranking/readiness does not authorize stopping A025, generic finite-task support A024, or integrity/recovery while any legacy functional consumer remains. A003 stays through the complete W5 intake transfer. Domain projections retire with their actual consuming domain, as listed below.

## Dependency semantics preserved

- **E1 (ordering_barrier):** Wait only while the relevant upstream occurrence is validly running; not a perpetual completed-once prerequisite.
- **E2 (ordered_verified_handoff):** A023 package -> A053 immutable proposal -> A054 deterministic commit/ACK.
- **E3 (handoff_then_preferred_input):** A029 verified closed actuals -> A029-B; A020/A021 summary input is soft and preserves governed fallback.
- **E4 (freshness):** Canonical build freshness matters; A032 deployment lag does not block A004.
- **E5 (separate_artifact_chains):** Appendix specifies status producers -> A022 -> A044, dashboard producers -> A026 -> A052; A032 consumes their verified canonical files. This is not a Cartesian set of edges.
- **E6 (mutual_live_run_exclusion):** Backup and continuity exclude each other while running; preserve across migration, do not invent an acyclic dependency.
- **E7 (verified_handoff):** A027 -> A031 -> A028; A036 -> A028. Inactive A028 prerequisite on A023 is excluded.

Pre-W13 migrated business producers may create delivery obligations only through a verified handoff to the still-authoritative 1.x transport domain. They may not call providers themselves. Conversely, after W13 residual 1.x support alerts must hand off to sole 2.x transport. These coexistence adapters are explicit build/acceptance gates, not claimed existing capabilities. Canonical file consumers use read-only verified artifacts; this preserves one writer without moving their whole consumer domain early.

## Detailed waves

### W1 — Toast closed-actual acquisition and dashboard source facts

**Included1xWorkers:**

- A029
- A047

**DispositionOfEach:** A029: KEEP; A047: CONSOLIDATE WITH A029 DATA ACQUISITION. Exact source pointers are in the JSON.

**OnlineAda2xComponents:** None. Acquisition and normalization remain deterministic; staffing judgment remains with 1.x.

**ResidentAda2xComponents:** One Toast acquisition adapter, existing closed-date normalization, verified cache/artifact output and dashboard source snapshot adapter. A047 consumes A029 facts; no second Toast fetch.

**ExistingCapabilitiesReused:**

- Resident SQL client, fencing, journal and bounded local execution foundation
- Existing A029 acquisition/date-boundary/normalization logic
- Existing A047 snapshot contract; unchanged provider HTTP/binding primitive

**CapabilitiesStillToAdapt:**

- Separate Sheets control from the existing A029 business logic; bind approved inputs and secrets to scoped SQL packages
- Implement governed POS batch/checkpoint persistence and deterministic A047 projection; fact.record is available but is not proof that POS import semantics exist
- Retain exact verified closed-actual artifact interface for 1.x A029-B and A026; one owner writes each output, read-only consumers remain 1.x
- Operational supervision, due-occurrence driver, least-privilege enrollment and common authority gates G1-G7

**SQLNativeFunctionsUsed:**

- executor.register
- executor.heartbeat
- work.next
- work.package
- work.renew
- work.complete
- work.fail
- work.defer
- work.release
- recovery.sweep
- fact.record and task.evidence.attach where their existing schemas fit; POS-specific commit mapping still to adapt

**ProviderSideEffects:** Toast reads only. Canonical normalized cache and dashboard-source artifact writes are real output effects and transfer as one unit. No SMS, account mutation, forecasting or public deployment.

**CrossDomainDependencies:**

- A029 -> A029-B is a verified-output handoff (E3); A029-B stays 1.x through W4
- A047 -> A026/A049 reads preserve the current source contract through W8; unavailable source remains explicit
- Use approved source labels/checkpoints as bounded inputs; no control-table replication or second system of record

**1xFunctionalWorkersPausedAtTransfer:**

- A029
- A047

**1xInfrastructureThatMustRemain:**

- A003
- A005
- A008
- A009
- A010
- A011
- A012
- A013
- A014
- A015
- A016
- A022
- A024
- A025
- A026
- A027
- A028
- A029-B
- A036
- A037
- A038
- A039
- A040
- A041
- A042
- A043
- A045
- A047
- A051

**AcceptanceTests:**

- Frozen closed-date replay: exact totals, IDs, labor intervals, timezone and source hashes; exclude partial/open day
- Unchanged batch is a no-op; crash before/after governed commit produces one batch/checkpoint and no duplicate artifact
- Independent SQL and canonical artifact read-back; run unchanged 1.x A029-B against the output and verify its accepted feature baseline; do not replace A029-B yet
- A047 consumes the same actuals, with freshness/unknown states and no duplicate provider fetch
- Drain both 1.x execution paths and prove stale old-owner attempts rejected; restore checkpoint/output and reverse ownership in rehearsal

**RollbackUnit:** A029 + A047 acquisition ownership, checkpoint and exact output versions together. Stop/drain 2.x before restoring 1.x; reconcile committed import watermark first. A029-B never changes owner in this wave.

**Risk:** Low provider-effect risk; medium data/compatibility risk. No live-transfer acceptance yet.

**ExpectedComplexity:** Medium

**ReadyToBuildNow:** YES for bounded synthetic adapter build using existing logic. NO for live cutover until G1-G7 and consumer compatibility pass.

**ReadyToTransferNow:** NO. G1-G7 plus every referenced original disposition acceptance test apply.

**Infrastructure retention timing:** MUST_REMAIN_1X includes this wave through its transfer acceptance. Workers in the complete pause set then stop functional execution; future-wave/global infrastructure stays active. Retained legacy evidence does not authorize an old effect path.

**1.x infrastructure still executing after successful acceptance:** A003, A005, A008, A009, A010, A011, A012, A013, A014, A015, A016, A022, A024, A025, A026, A027, A028, A029-B, A036, A037, A038, A039, A040, A041, A042, A043, A045, A051.

### W2 — Canonical artifact publication

**Included1xWorkers:**

- A032

**DispositionOfEach:** A032: KEEP. Exact source pointers are in the JSON.

**OnlineAda2xComponents:** None.

**ResidentAda2xComponents:** Existing Drive-read/Vercel publication capability behind SQL work and result adapters.

**ExistingCapabilitiesReused:**

- Existing A032 hash-based publication and alias/read-back behavior
- Resident HTTP, artifact/hash, claim/fence and idempotency foundation

**CapabilitiesStillToAdapt:**

- Publication target, release, attempt and artifact identity mapping
- Scoped Drive/Vercel credentials and provider outcome reconciliation
- Read existing 1.x A044/A052 canonical outputs without acquiring their production ownership; later accept 2.x outputs under the same contract

**SQLNativeFunctionsUsed:**

- executor.register
- executor.heartbeat
- work.next
- work.package
- work.renew
- work.complete
- work.fail
- work.defer
- work.release
- recovery.sweep
- provider.result.record; governed publication-command creation/attempt mapping requires adaptation

**ProviderSideEffects:** Public deployment and alias changes. Same hash must not redeploy.

**CrossDomainDependencies:**

- A044 and A052 remain 1.x producers until W9/W8; publication consumes verified immutable versions
- A004 depends on canonical A026 build freshness, not A032 delivery success (E4)

**1xFunctionalWorkersPausedAtTransfer:**

- A032

**1xInfrastructureThatMustRemain:**

- A003
- A005
- A008
- A009
- A010
- A011
- A012
- A013
- A014
- A015
- A016
- A022
- A024
- A025
- A026
- A027
- A028
- A029-B
- A036
- A037
- A038
- A039
- A040
- A041
- A042
- A043
- A045
- A051

**AcceptanceTests:**

- Same hash no-op; exact Drive source bytes and public alias/read-back match
- Deploy timeout/unknown result reconciles before retry; failed deployment preserves previous release
- One publisher across both architectures; both current publication targets and rollback rehearsed

**RollbackUnit:** Entire publisher and its targets. Drain deployments, reconcile actual aliases, then return sole publication authority to A032; artifact producers keep their current owners.

**Risk:** Medium: externally visible releases, but narrow deterministic ownership.

**ExpectedComplexity:** Medium

**ReadyToBuildNow:** YES for synthetic/read-only adapter work; G1-G7 and release rollback block transfer.

**ReadyToTransferNow:** NO. G1-G7 plus every referenced original disposition acceptance test apply.

**Infrastructure retention timing:** MUST_REMAIN_1X includes this wave through its transfer acceptance. Workers in the complete pause set then stop functional execution; future-wave/global infrastructure stays active. Retained legacy evidence does not authorize an old effect path.

**1.x infrastructure still executing after successful acceptance:** A003, A005, A008, A009, A010, A011, A012, A013, A014, A015, A016, A022, A024, A025, A026, A027, A028, A029-B, A036, A037, A038, A039, A040, A041, A042, A043, A045, A051.

**Legacy evidence/rollback support retained after functional pause:** A047. No competing side effects.

### W3 — Social content planning

**Included1xWorkers:**

- A033

**DispositionOfEach:** A033: KEEP. Exact source pointers are in the JSON.

**OnlineAda2xComponents:** Content planning from bounded calendar/event/state packages; produce versioned plans, scoped tasks and drafts.

**ResidentAda2xComponents:** Artifact persistence only if required by the existing plan contract. Publication is a separately approved downstream action.

**ExistingCapabilitiesReused:**

- Existing A033 planning policy
- Phase 2 semantic proposal and deterministic commit contracts; work packages

**CapabilitiesStillToAdapt:**

- Deploy and attest Online Ada 2.x
- Content plan/draft schema and object scopes
- Read-only authoritative calendar/business inputs; explicit ownership of plan-created Tasks and drafts

**SQLNativeFunctionsUsed:**

- executor.register
- executor.heartbeat
- work.next
- work.package
- work.renew
- work.complete
- work.fail
- work.defer
- work.release
- recovery.sweep
- semantic.proposal.submit
- proposal.commit
- task.evidence.attach

**ProviderSideEffects:** Plans/tasks/drafts are business mutations. No automatic social post or notification transport.

**CrossDomainDependencies:**

- Calendar/events remain externally or 1.x owned inputs
- Shared Task identifiers must have one write owner under G2; unresolved task-scope overlap blocks transfer

**1xFunctionalWorkersPausedAtTransfer:**

- A033

**1xInfrastructureThatMustRemain:**

- A003
- A005
- A008
- A009
- A010
- A011
- A012
- A013
- A014
- A015
- A016
- A022
- A024
- A025
- A026
- A027
- A028
- A029-B
- A036
- A037
- A038
- A039
- A040
- A041
- A042
- A043
- A045
- A051

**AcceptanceTests:**

- One plan chain per occurrence; immutable inputs and evidence
- Duplicate proposal/restart cannot create duplicate tasks or publish
- Replacement semantic executor can resume from package; draft/publication approval separation proven

**RollbackUnit:** Plan version and all Tasks/drafts created by that occurrence; preserve committed evidence and reconcile versions before returning A033 authority.

**Risk:** Low transport risk; medium semantic and shared-record risk.

**ExpectedComplexity:** Medium

**ReadyToBuildNow:** YES for schemas/shadow build; Online runtime and shared Task ownership are outstanding.

**ReadyToTransferNow:** NO. G1-G7 plus every referenced original disposition acceptance test apply.

**Infrastructure retention timing:** MUST_REMAIN_1X includes this wave through its transfer acceptance. Workers in the complete pause set then stop functional execution; future-wave/global infrastructure stays active. Retained legacy evidence does not authorize an old effect path.

**1.x infrastructure still executing after successful acceptance:** A003, A005, A008, A009, A010, A011, A012, A013, A014, A015, A016, A022, A024, A025, A026, A027, A028, A029-B, A036, A037, A038, A039, A040, A041, A042, A043, A045, A051.

**Legacy evidence/rollback support retained after functional pause:** A047. No competing side effects.

### W4 — Staffing features, forecasts, near-term analysis and feedback

**Included1xWorkers:**

- A029-B
- A019
- A020
- A021

**DispositionOfEach:** A029-B: ABSORB INTO DATABASE; A019: KEEP/IMPROVE; A020: KEEP/IMPROVE; A021: KEEP/IMPROVE. Exact source pointers are in the JSON.

**OnlineAda2xComponents:** Distinct forecast, deep-dive and actual-feedback stages, retaining their independent schedules and evidence.

**ResidentAda2xComponents:** Existing staffing artifact/output adapters; deterministic SQL feature refresh after verified actuals.

**ExistingCapabilitiesReused:**

- W1 actuals and existing staffing calculation/renderer rules
- Phase 2 dependency release, packages and immutable stage results

**CapabilitiesStillToAdapt:**

- A029-B SQL feature calculations and affected-window refresh
- Forecast snapshots, qualitative observations and performance reconciliation
- Semantic staffing adapters and governed document outputs

**SQLNativeFunctionsUsed:**

- executor.register
- executor.heartbeat
- work.next
- work.package
- work.renew
- work.complete
- work.fail
- work.defer
- work.release
- recovery.sweep
- semantic.proposal.submit
- proposal.commit
- fact.record
- work dependency release; staffing feature projections still to implement

**ProviderSideEffects:** Forecast/feedback records and planning artifacts; no Toast provider writes. Any delivery request stays with the single transport owner until W13.

**CrossDomainDependencies:**

- W1 actuals; A020/A021 preferred A029-B inputs are soft, not hard prerequisites (E3)
- A021 uses the latest valid forecast; feedback must not overwrite its pre-horizon version
- Staffing qualitative labels/observations require authoritative input mapping

**1xFunctionalWorkersPausedAtTransfer:**

- A029-B
- A019
- A020
- A021

**1xInfrastructureThatMustRemain:**

- A003
- A005
- A008
- A009
- A010
- A011
- A012
- A013
- A014
- A015
- A016
- A022
- A024
- A025
- A026
- A027
- A028
- A029-B
- A036
- A037
- A038
- A039
- A040
- A041
- A042
- A043
- A045
- A051

**AcceptanceTests:**

- Match accepted 2,587-feature baseline or governed approved sample; unchanged inputs no-op
- Preserve missing-summary fallback and pending reconciliation rather than inventing a hard block
- Full forecast-to-actual-to-feedback cycle; frozen forecasts, source counts and no hindsight overwrite
- Pause all four 1.x feature/forecast/feedback paths as one transfer unit

**RollbackUnit:** Feature source-set/version plus forecast, deep-dive and feedback stages together; retain immutable prior forecasts and exact output pointers.

**Risk:** Medium: operational staffing decisions, longitudinal acceptance required.

**ExpectedComplexity:** High

**ReadyToBuildNow:** YES after W1 contract is stable for build; full forecast cycle blocks transfer.

**ReadyToTransferNow:** NO. G1-G7 plus every referenced original disposition acceptance test apply.

**Infrastructure retention timing:** MUST_REMAIN_1X includes this wave through its transfer acceptance. Workers in the complete pause set then stop functional execution; future-wave/global infrastructure stays active. Retained legacy evidence does not authorize an old effect path.

**1.x infrastructure still executing after successful acceptance:** A003, A005, A008, A009, A010, A011, A012, A013, A014, A015, A016, A022, A024, A025, A026, A027, A028, A036, A037, A038, A039, A040, A041, A042, A043, A045, A051.

**Legacy evidence/rollback support retained after functional pause:** A047. No competing side effects.

### W5 — Mail and Drive intake, classification and filing

**Included1xWorkers:**

- A001
- A002
- A007
- A035

**DispositionOfEach:** A001: MODIFY; A002: MODIFY; A007: MODIFY; A035: KEEP/MODIFY. Exact source pointers are in the JSON.

**OnlineAda2xComponents:** Independent Gmail mailroom and deep-review stages; Drive classification/correlation and duplicate review.

**ResidentAda2xComponents:** Gmail history/delta, Drive identity/change and approved filing adapters; provider reconciliation.

**ExistingCapabilitiesReused:**

- Existing Gmail/Drive business rules and identity resolution
- Receipt/proposal/commit foundations and reusable provider HTTP primitive

**CapabilitiesStillToAdapt:**

- Real provider receipt/checkpoint and mutation outcome mappings
- Contact-context/artifact ownership, expected provider versions and duplicate-case scopes
- A003 assertions and provider-quality sampling replacement; no loss of verification

**SQLNativeFunctionsUsed:**

- executor.register
- executor.heartbeat
- work.next
- work.package
- work.renew
- work.complete
- work.fail
- work.defer
- work.release
- recovery.sweep
- semantic.proposal.submit
- proposal.commit
- provider.result.record; real filing operation mappings pending

**ProviderSideEffects:** Labels/read/archive, canonical artifact registration, rename/move; destructive consolidation remains explicitly approved. Gmail draft sending stays with delivery authority.

**CrossDomainDependencies:**

- A003 audits A001/A002 with ordering barriers (E1); retain it through this transfer and retire only after replacement verification
- A001 independence from A035 is preserved: a shared cutover window does not introduce a runtime prerequisite
- Shared contact context and filing objects justify the conservative joint window; split only after object-scope non-overlap is proved

**1xFunctionalWorkersPausedAtTransfer:**

- A001
- A002
- A007
- A035

**1xInfrastructureThatMustRemain:**

- A003
- A005
- A008
- A009
- A010
- A011
- A012
- A013
- A014
- A015
- A016
- A022
- A024
- A025
- A026
- A027
- A028
- A036
- A037
- A038
- A039
- A040
- A041
- A042
- A043
- A045
- A051

**AcceptanceTests:**

- One disposition per message version/Drive ID; unreadable item and stale version isolated
- Provider success/DB failure reconciles actual IDs; no blind repeat
- Seed checkpoint/label mismatch and detect with independent provider sampling
- Approved moves only; all four legacy writers drained, A003 ordering safety preserved

**RollbackUnit:** All overlapping Gmail/Drive filing writers, checkpoints and object ownership together; reconcile irreversible provider moves instead of replaying old commands.

**Risk:** High: many shared objects and provider mutations.

**ExpectedComplexity:** High

**ReadyToBuildNow:** YES for scoped adapters/shadow; ownership, semantic runtime and provider reconciliation block transfer.

**ReadyToTransferNow:** NO. G1-G7 plus every referenced original disposition acceptance test apply.

**Infrastructure retention timing:** MUST_REMAIN_1X includes this wave through its transfer acceptance. Workers in the complete pause set then stop functional execution; future-wave/global infrastructure stays active. Retained legacy evidence does not authorize an old effect path.

**1.x infrastructure still executing after successful acceptance:** A005, A008, A009, A010, A011, A012, A013, A014, A015, A016, A022, A024, A025, A026, A027, A028, A036, A037, A038, A039, A040, A041, A042, A043, A045, A051.

**Legacy evidence/rollback support retained after functional pause:** A047. No competing side effects.

### W6 — Task owner review receipt, interpretation and commit/ACK

**Included1xWorkers:**

- A023
- A053
- A054

**DispositionOfEach:** A023: MODIFY; A053: KEEP SEMANTIC STAGE / GENERALIZE; A054: KEEP DETERMINISTIC STAGE / SIMPLIFY. Exact source pointers are in the JSON.

**OnlineAda2xComponents:** Interpret immutable review package and submit versioned proposals; no direct task mutation.

**ResidentAda2xComponents:** Existing review queue authentication/receipt packaging and deterministic commit/ACK adapters.

**ExistingCapabilitiesReused:**

- Existing three-stage review chain
- Phase 2 synthetic semantic-to-commit slice and proposal reuse

**CapabilitiesStillToAdapt:**

- Real queue transaction identity, attachment/hash and recipient scope
- Authoritative Task version mapping and bounded commit schema
- ACK-after-commit and provider unknown-outcome reconciliation

**SQLNativeFunctionsUsed:**

- executor.register
- executor.heartbeat
- work.next
- work.package
- work.renew
- work.complete
- work.fail
- work.defer
- work.release
- recovery.sweep
- semantic.proposal.submit
- proposal.commit
- task.evidence.attach
- provider.result.record

**ProviderSideEffects:** Real Task changes and irreversible queue ACK. Outbound obligation creation is separate from transport.

**CrossDomainDependencies:**

- Exact A023 -> A053 -> A054 handoffs (E2)
- The old A023 -> A028 hard dependency is INACTIVE; completion must not wait for SMS
- Shared Tasks across unmigrated domains require G2; a second writable Task copy is forbidden

**1xFunctionalWorkersPausedAtTransfer:**

- A023
- A053
- A054

**1xInfrastructureThatMustRemain:**

- A005
- A008
- A009
- A010
- A011
- A012
- A013
- A014
- A015
- A016
- A022
- A024
- A025
- A026
- A027
- A028
- A036
- A037
- A038
- A039
- A040
- A041
- A042
- A043
- A045
- A051

**AcceptanceTests:**

- Duplicate receipt produces one package; exact source hashes/versions
- Stale proposal sibling isolation; restart reuses committed interpretation
- Independent committed Task/evidence read-back before ACK; provider success reconciliation and no loss on crash

**RollbackUnit:** All three stages and the receipt/ACK watermark as one unit. Already ACKed transactions are reconciled, never reintroduced into the queue.

**Risk:** High: business writes and irreversible ACK.

**ExpectedComplexity:** High

**ReadyToBuildNow:** YES for synthetic adapter build; real task authority and ACK acceptance block transfer.

**ReadyToTransferNow:** NO. G1-G7 plus every referenced original disposition acceptance test apply.

**Infrastructure retention timing:** MUST_REMAIN_1X includes this wave through its transfer acceptance. Workers in the complete pause set then stop functional execution; future-wave/global infrastructure stays active. Retained legacy evidence does not authorize an old effect path.

**1.x infrastructure still executing after successful acceptance:** A005, A008, A009, A010, A011, A012, A013, A014, A015, A016, A022, A024, A025, A026, A027, A028, A036, A037, A038, A039, A040, A041, A042, A043, A045, A051.

**Legacy evidence/rollback support retained after functional pause:** A047. No competing side effects.

### W7 — Governed documentation and review

**Included1xWorkers:**

- A006

**DispositionOfEach:** A006: KEEP BUSINESS / MODIFY. Exact source pointers are in the JSON.

**OnlineAda2xComponents:** Existing document drafting, revision and review interpretation.

**ResidentAda2xComponents:** Docs/Drive versioned mutation and approval evidence; transport remains owned by the delivery domain.

**ExistingCapabilitiesReused:**

- Existing controlled-document workflow
- Artifact/version, approval and proposal contracts

**CapabilitiesStillToAdapt:**

- Document/source version mapping, approval correlation and restart-safe distribution intent
- Semantic documentation adapter; transport handoff to current sole delivery owner

**SQLNativeFunctionsUsed:**

- executor.register
- executor.heartbeat
- work.next
- work.package
- work.renew
- work.complete
- work.fail
- work.defer
- work.release
- recovery.sweep
- semantic.proposal.submit
- proposal.commit
- task.evidence.attach; document mutation adapter pending

**ProviderSideEffects:** Controlled Docs/Drive versions and approved distribution obligations.

**CrossDomainDependencies:**

- W5 canonical filing/identity; approval and Task ownership G2
- A010 remains email transport until W13; no direct send by the new documentation executor

**1xFunctionalWorkersPausedAtTransfer:**

- A006

**1xInfrastructureThatMustRemain:**

- A005
- A008
- A009
- A010
- A011
- A012
- A013
- A014
- A015
- A016
- A022
- A024
- A025
- A026
- A027
- A028
- A036
- A037
- A038
- A039
- A040
- A041
- A042
- A043
- A045
- A051

**AcceptanceTests:**

- Expected version and approval required; stale revision fails
- Restart cannot redistribute; artifact and delivery evidence independently reconciled

**RollbackUnit:** Documentation occurrence, version and approval/distribution intent; retain published versions and reverse ownership only after pending effects reconcile.

**Risk:** High: controlled documents and recipient distribution.

**ExpectedComplexity:** Medium-high

**ReadyToBuildNow:** YES for build after intake identity and delivery handoff contracts are stable.

**ReadyToTransferNow:** NO. G1-G7 plus every referenced original disposition acceptance test apply.

**Infrastructure retention timing:** MUST_REMAIN_1X includes this wave through its transfer acceptance. Workers in the complete pause set then stop functional execution; future-wave/global infrastructure stays active. Retained legacy evidence does not authorize an old effect path.

**1.x infrastructure still executing after successful acceptance:** A005, A008, A009, A010, A011, A012, A013, A014, A015, A016, A022, A024, A025, A026, A027, A028, A036, A037, A038, A039, A040, A041, A042, A043, A045, A051.

**Legacy evidence/rollback support retained after functional pause:** A047. No competing side effects.

### W8 — Life and Business dashboard sources, assembly and canonical materialization

**Included1xWorkers:**

- A026
- A045
- A046
- A048
- A049
- A050
- A051
- A052

**DispositionOfEach:** A026: KEEP BUSINESS / SIMPLIFY; A045: CONSOLIDATE/MODIFY; A046: KEEP PROVIDER FUNCTION / MODIFY; A048: KEEP BUSINESS / MODIFY; A049: KEEP SEMANTIC / MODIFY; A050: KEEP/MODIFY; A051: ABSORB INTO DATABASE; A052: KEEP. Exact source pointers are in the JSON.

**OnlineAda2xComponents:** Financial/cash exception interpretation, financial forecast and privacy-scoped personal synthesis; optional executive narrative only.

**ResidentAda2xComponents:** Financial snapshot adapter, deterministic source projections, package assembly and unchanged canonical renderer/Drive materializer.

**ExistingCapabilitiesReused:**

- W1 A047 Toast facts; existing independent producer semantics and A052 renderer
- SQL package/fence/artifact foundations; W2 publisher

**CapabilitiesStillToAdapt:**

- Executive/cash/source-health projections and financial account field mapping
- Forecast and privacy-scoped snapshots; immutable source versions
- A026 package and A052 adapter including Live/Sample handling; read-only Task/Project snapshots while W12 remains 1.x

**SQLNativeFunctionsUsed:**

- executor.register
- executor.heartbeat
- work.next
- work.package
- work.renew
- work.complete
- work.fail
- work.defer
- work.release
- recovery.sweep
- semantic.proposal.submit
- proposal.commit
- fact.record; executive/source-health/financial projections pending

**ProviderSideEffects:** Finance reads; sensitive forecast/snapshot and canonical Live/Sample Drive writes. No banking transaction. Public release belongs only to W2 publisher.

**CrossDomainDependencies:**

- A045-A051 -> A026 -> A052; A047 already owns only source acquisition (E5)
- A049 consumes finance/Toast/cash; A050 consumes financial B; A051 observes A-F
- A004 still 1.x reads verified canonical build with explicit freshness through W10

**1xFunctionalWorkersPausedAtTransfer:**

- A026
- A045
- A046
- A048
- A049
- A050
- A051
- A052

**1xInfrastructureThatMustRemain:**

- A005
- A008
- A009
- A010
- A011
- A012
- A013
- A014
- A015
- A016
- A022
- A024
- A025
- A026
- A027
- A028
- A036
- A037
- A038
- A039
- A040
- A041
- A042
- A043
- A045
- A051

**AcceptanceTests:**

- 41/41 bindings, privacy/sample isolation, structural twin and exact-byte independent read-back
- Missing Toast or account is unknown/degraded and does not erase independent sections
- Immutable forecast inputs and provider IDs; last verified artifact preserved on failure
- One canonical materializer and source writer per scope

**RollbackUnit:** All listed sources, assembler and both canonical outputs together, preserving W1 acquisition and W2 publication ownership. Restore exact prior artifact/source pointers before resuming 1.x.

**Risk:** High: financial interpretation, privacy and canonical artifacts.

**ExpectedComplexity:** High

**ReadyToBuildNow:** YES for shadow build after W1/W2; privacy, finance and renderer acceptance block transfer.

**ReadyToTransferNow:** NO. G1-G7 plus every referenced original disposition acceptance test apply.

**Infrastructure retention timing:** MUST_REMAIN_1X includes this wave through its transfer acceptance. Workers in the complete pause set then stop functional execution; future-wave/global infrastructure stays active. Retained legacy evidence does not authorize an old effect path.

**1.x infrastructure still executing after successful acceptance:** A005, A008, A009, A010, A011, A012, A013, A014, A015, A016, A022, A024, A025, A027, A028, A036, A037, A038, A039, A040, A041, A042, A043.

**Legacy evidence/rollback support retained after functional pause:** A047. No competing side effects.

### W9 — System status projection, package and canonical rendering

**Included1xWorkers:**

- A022
- A037
- A038
- A039
- A040
- A041
- A042
- A043
- A044

**DispositionOfEach:** A022: CONSOLIDATE/REDESIGN; A037: ABSORB INTO DATABASE; A038: ABSORB INTO DATABASE; A039: ABSORB INTO DATABASE; A040: ABSORB INTO DATABASE; A041: ABSORB INTO DATABASE; A042: CONSOLIDATE; A043: ABSORB/MODIFY; A044: KEEP. Exact source pointers are in the JSON.

**OnlineAda2xComponents:** None for deterministic core status.

**ResidentAda2xComponents:** Status snapshot/package and existing HTML/Drive materializer; threshold obligations handed to the current delivery owner.

**ExistingCapabilitiesReused:**

- Implemented executor/work health views
- Existing A044 template/materialization logic and W2 publisher

**CapabilitiesStillToAdapt:**

- Missing header, activity and rolling-24h projections
- Explicitly labelled read-only 1.x health input during coexistence; SQL health alone cannot assert whole-system health
- Deterministic package/version/notification policy and independent watchdog observation

**SQLNativeFunctionsUsed:**

- executor.register
- executor.heartbeat
- work.next
- work.package
- work.renew
- work.complete
- work.fail
- work.defer
- work.release
- recovery.sweep
- v_node_health
- v_ready_work
- v_blocked_work
- v_current_claims
- v_recent_failures
- v_dead_letters
- v_work_aging
- control_plane_health; remaining business status projections pending

**ProviderSideEffects:** Canonical status file and deduped health obligations; W2 owns publication, W13 later owns transport.

**CrossDomainDependencies:**

- A037-A043 -> A022 -> A044 (E5)
- 1.x support and residual domains continue after this wave: preserve read-only visibility and label source/freshness
- A042 alert delivery still relies on A010/A028 until W13

**1xFunctionalWorkersPausedAtTransfer:**

- A022
- A037
- A038
- A039
- A040
- A041
- A042
- A043
- A044

**1xInfrastructureThatMustRemain:**

- A005
- A008
- A009
- A010
- A011
- A012
- A013
- A014
- A015
- A016
- A022
- A024
- A025
- A027
- A028
- A036
- A037
- A038
- A039
- A040
- A041
- A042
- A043

**AcceptanceTests:**

- Exact ready/claim/retry/dead-letter and boundary/timezone counts
- Rebuild projections from event ledger; stale heartbeat visible and independent alert delivery proven
- Both architectures visible without double counting; no false healthy from missing input
- Deterministic golden HTML, changed-byte detection and prior-file preservation

**RollbackUnit:** All status producers, package verification and materializer together; publisher authority remains W2, 1.x control/recovery is never stopped by this wave.

**Risk:** Medium: false confidence/outage visibility and publication correctness.

**ExpectedComplexity:** Medium-high

**ReadyToBuildNow:** YES for missing projections and shadow rendering; mixed-state status and watchdog tests block transfer.

**ReadyToTransferNow:** NO. G1-G7 plus every referenced original disposition acceptance test apply.

**Infrastructure retention timing:** MUST_REMAIN_1X includes this wave through its transfer acceptance. Workers in the complete pause set then stop functional execution; future-wave/global infrastructure stays active. Retained legacy evidence does not authorize an old effect path.

**1.x infrastructure still executing after successful acceptance:** A005, A008, A009, A010, A011, A012, A013, A014, A015, A016, A024, A025, A027, A028, A036.

**Legacy evidence/rollback support retained after functional pause:** A026. No competing side effects.

### W10 — Executive briefing

**Included1xWorkers:**

- A004

**DispositionOfEach:** A004: KEEP/IMPROVE. Exact source pointers are in the JSON.

**OnlineAda2xComponents:** Versioned synthesis of bounded Task/Project/calendar/financial and verified dashboard inputs.

**ResidentAda2xComponents:** Briefing artifact adapter; delivery requests to the sole transport owner.

**ExistingCapabilitiesReused:**

- Existing briefing required sections/policy
- W8 canonical dashboard and Phase 2 semantic package contracts

**CapabilitiesStillToAdapt:**

- Snapshot input contract and briefing schema
- Scheduled semantic execution with deadline guarantees; governed delivery correlation

**SQLNativeFunctionsUsed:**

- executor.register
- executor.heartbeat
- work.next
- work.package
- work.renew
- work.complete
- work.fail
- work.defer
- work.release
- recovery.sweep
- semantic.proposal.submit
- proposal.commit
- task.evidence.attach

**ProviderSideEffects:** Briefing artifact and approved delivery obligations.

**CrossDomainDependencies:**

- W8 canonical build freshness; W2 publication lag must not block briefing (E4)
- W12 Task operations still 1.x: bounded read-only inputs required
- A010/A028 remain sole delivery executors through W13

**1xFunctionalWorkersPausedAtTransfer:**

- A004

**1xInfrastructureThatMustRemain:**

- A005
- A008
- A009
- A010
- A011
- A012
- A013
- A014
- A015
- A016
- A024
- A025
- A027
- A028
- A036

**AcceptanceTests:**

- Frozen inputs reproduce required sections; stale/unknown state disclosed
- Canonical dashboard freshness gate is independent of public deployment
- Both scheduled occurrences meet deadline without duplicate delivery

**RollbackUnit:** Briefing occurrence/input snapshot and delivery idempotency key; drain semantic output and pending obligations before reverse ownership.

**Risk:** Medium: executive interpretation and delivery duplication.

**ExpectedComplexity:** Medium

**ReadyToBuildNow:** YES after W8 input contract; semantic scheduling and delivery evidence required.

**ReadyToTransferNow:** NO. G1-G7 plus every referenced original disposition acceptance test apply.

**Infrastructure retention timing:** MUST_REMAIN_1X includes this wave through its transfer acceptance. Workers in the complete pause set then stop functional execution; future-wave/global infrastructure stays active. Retained legacy evidence does not authorize an old effect path.

**1.x infrastructure still executing after successful acceptance:** A005, A008, A009, A010, A011, A012, A013, A014, A015, A016, A024, A025, A027, A028, A036.

**Legacy evidence/rollback support retained after functional pause:** A026. No competing side effects.

### W11 — Incremental semantic continuity

**Included1xWorkers:**

- A018

**DispositionOfEach:** A018: KEEP CAPABILITY / REPLACE MECHANICS. Exact source pointers are in the JSON.

**OnlineAda2xComponents:** Existing continuity compaction and contradiction/reference checks.

**ResidentAda2xComponents:** Verified memory-head activation/export adapter; independent full backup remains 1.x.

**ExistingCapabilitiesReused:**

- Memory version/head contracts and existing continuity policy
- Existing package/evidence/commit foundations

**CapabilitiesStillToAdapt:**

- Semantic compaction and current-source reference mapping
- Portable export; mutual exclusion with still-live A005 backup across the boundary

**SQLNativeFunctionsUsed:**

- executor.register
- executor.heartbeat
- work.next
- work.package
- work.renew
- work.complete
- work.fail
- work.defer
- work.release
- recovery.sweep
- governed memory activation/export mapping to existing contracts; no new operation assumed implemented

**ProviderSideEffects:** Active continuity-head and verified export changes.

**CrossDomainDependencies:**

- A005 <-> A018 mutual live-run ordering barriers (E6), not a DAG to topologically sort
- A005/A012 remain for still-active 1.x data and rollback; a SQL memory head does not replace backups

**1xFunctionalWorkersPausedAtTransfer:**

- A018

**1xInfrastructureThatMustRemain:**

- A005
- A008
- A009
- A010
- A011
- A012
- A013
- A014
- A015
- A016
- A024
- A025
- A027
- A028
- A036

**AcceptanceTests:**

- Replacement AI bootstraps from committed head; contradictions/missing references rejected
- Crash cannot expose two active heads; portable export restores independently
- Backup/continuity exclusion holds in both directions while A005 remains 1.x

**RollbackUnit:** Continuity head and export pointer as one fenced unit; preserve immutable versions and verify replacement-AI bootstrap before reverse ownership.

**Risk:** High: recovery knowledge and mixed backup boundary.

**ExpectedComplexity:** Medium-high

**ReadyToBuildNow:** YES for synthetic build; cross-boundary backup exclusion and bootstrap acceptance block transfer.

**ReadyToTransferNow:** NO. G1-G7 plus every referenced original disposition acceptance test apply.

**Infrastructure retention timing:** MUST_REMAIN_1X includes this wave through its transfer acceptance. Workers in the complete pause set then stop functional execution; future-wave/global infrastructure stays active. Retained legacy evidence does not authorize an old effect path.

**1.x infrastructure still executing after successful acceptance:** A005, A008, A009, A010, A011, A012, A013, A014, A015, A016, A024, A025, A027, A028, A036.

### W12 — Task coverage, owner routing and request follow-up

**Included1xWorkers:**

- A015
- A016

**DispositionOfEach:** A015: KEEP BUSINESS / REDESIGN; A016: MODIFY. Exact source pointers are in the JSON.

**OnlineAda2xComponents:** Semantic uncovered-task judgments and consolidated follow-up drafts/escalations.

**ResidentAda2xComponents:** Deterministic coverage/deadline/response cancellation projections and proposal commit adapters.

**ExistingCapabilitiesReused:**

- Existing communication/coverage policy
- SQL Task/work and approval contracts; generic dispatcher foundation

**CapabilitiesStillToAdapt:**

- Coverage/SLA projections and legacy priority input mapping
- Scoped Task authority reconciliation and task-origin routing
- Occurrence creation, RUN NOW interface and consolidated recipient/delivery policies

**SQLNativeFunctionsUsed:**

- executor.register
- executor.heartbeat
- work.next
- work.package
- work.renew
- work.complete
- work.fail
- work.defer
- work.release
- recovery.sweep
- semantic.proposal.submit
- proposal.commit
- selection
- work dependency release; coverage projections and public schedule/RUN NOW adapters pending

**ProviderSideEffects:** Task changes and follow-up obligations. Actual channel effects stay with W13 transport.

**CrossDomainDependencies:**

- Consumes Tasks/communications/deadlines across previous domains; all shared-record ownership conflicts must now be reconciled
- A024 remains as cross-cutting 1.x finite-task support for residual workloads until T14; migration registry never becomes runtime routing

**1xFunctionalWorkersPausedAtTransfer:**

- A015
- A016

**1xInfrastructureThatMustRemain:**

- A005
- A008
- A009
- A010
- A011
- A012
- A013
- A014
- A015
- A016
- A024
- A025
- A027
- A028
- A036

**AcceptanceTests:**

- 100% scoped coverage and one route per recipient
- Reply transaction cancels/satisfies deadline obligation; retries do not duplicate drafts
- Multiple finite-task types and incompatible-capability isolation; preserve business priority semantics explicitly

**RollbackUnit:** Coverage/follow-up domain and its Task versions/obligations; do not restore stale Task state or restart already satisfied requests.

**Risk:** High: broad Task and communication coupling.

**ExpectedComplexity:** High

**ReadyToBuildNow:** YES for bounded fixtures; wide Task ownership and scheduling gates block transfer.

**ReadyToTransferNow:** NO. G1-G7 plus every referenced original disposition acceptance test apply.

**Infrastructure retention timing:** MUST_REMAIN_1X includes this wave through its transfer acceptance. Workers in the complete pause set then stop functional execution; future-wave/global infrastructure stays active. Retained legacy evidence does not authorize an old effect path.

**1.x infrastructure still executing after successful acceptance:** A005, A008, A009, A010, A011, A012, A013, A014, A024, A025, A027, A028, A036.

### W13 — Inbound SMS, calendar reminders and shared notification delivery

**Included1xWorkers:**

- A010
- A027
- A028
- A031
- A036

**DispositionOfEach:** A010: REPLACE WORKER; A027: CONSOLIDATE/REPLACE; A028: KEEP TRANSPORT / REPLACE MECHANICS; A031: KEEP/IMPROVE; A036: ABSORB MOSTLY. Exact source pointers are in the JSON.

**OnlineAda2xComponents:** Inbound SMS interpretation and only ambiguous calendar importance; channel policy remains explicit.

**ResidentAda2xComponents:** Durable receipt/ACK, Calendar threshold/update/cancel and Gmail/Twilio delivery/result/reconciliation adapters.

**ExistingCapabilitiesReused:**

- Existing SMS/Gmail/Calendar business/provider logic
- Phase 2 synthetic outbox/result/ACK slice and W1-W12 governed producer contracts

**CapabilitiesStillToAdapt:**

- Production-safe real provider command/attempt lifecycle; synthetic helper is not a real send API
- All producer obligations, pending/UNKNOWN deliveries, provider IDs and idempotency watermarks
- Calendar DST/all-day/cancel policy; whole inbound/outbound receipt and response chain
- Rebind remaining infrastructure alerts to the single 2.x transport owner before legacy delivery workers stop

**SQLNativeFunctionsUsed:**

- executor.register
- executor.heartbeat
- work.next
- work.package
- work.renew
- work.complete
- work.fail
- work.defer
- work.release
- recovery.sweep
- semantic.proposal.submit
- proposal.commit
- provider.result.record; real provider begin/claim/ACK command boundary adaptation required

**ProviderSideEffects:** SMS sends, Gmail draft/send, inbound ACK, real Task/Fact writes and calendar reminder obligations. Highest irreversible-effect risk.

**CrossDomainDependencies:**

- A027 -> A031 -> A028 and A036 -> A028 verified handoffs (E7)
- A010/A027/A028 share transport mechanics, not channel approval/provider evidence (appendix preservation rule)
- All functional producer waves W1-W12 precede this transfer; residual T14 support alerts require explicit handoff acceptance

**1xFunctionalWorkersPausedAtTransfer:**

- A010
- A027
- A028
- A031
- A036

**1xInfrastructureThatMustRemain:**

- A005
- A008
- A009
- A010
- A011
- A012
- A013
- A014
- A024
- A025
- A027
- A028
- A036

**AcceptanceTests:**

- Exact inbound text preserved; durable receipt before queue ACK
- Provider success/DB failure and UNKNOWN outcomes reconcile SID/message ID, never blind resend
- Draft-first, recipients/thread/signature and approval tests; exactly one reminder per policy key with DST/all-day/update/cancel
- Reconcile every pre-transfer pending/UNKNOWN obligation; late webhook handled once; prove no active legacy send path including infrastructure alerts

**RollbackUnit:** Entire inbound/calendar/email/SMS transport ownership and ledgers. Stop both old and new sending during ambiguity; reconcile actual provider outcomes before any reverse transfer.

**Risk:** High: irreversible communications and provider ACK.

**ExpectedComplexity:** High

**ReadyToBuildNow:** YES for synthetic adapter work; last functional transfer, real transport authority and reconciliation unproven.

**ReadyToTransferNow:** NO. G1-G7 plus every referenced original disposition acceptance test apply.

**Infrastructure retention timing:** MUST_REMAIN_1X includes this wave through its transfer acceptance. Workers in the complete pause set then stop functional execution; future-wave/global infrastructure stays active. Retained legacy evidence does not authorize an old effect path.

**1.x infrastructure still executing after successful acceptance:** A005, A008, A009, A011, A012, A013, A014, A024, A025.

**Legacy evidence/rollback support retained after functional pause:** A015, A016. No competing side effects.

## Retirement tail and backward calculation

The JSON explicitly enumerates every consumer ID for each row. `LastConsumerWave` is the maximum assigned consumer wave. For global support, the conservative set contains all 52 non-retired-at-review workers except self, including the remaining support cohort; its maximum is **T14**. The last functional wave is W13. Drain the residual mutually observing cohort together, after replacement support is operational, rather than stopping one support worker while another still depends on it. Backup retention can remain longer.

A026 and transport illustrate the difference between a functional pause and final retirement: new sole ownership can start only after unchanged interfaces or accepted handoffs preserve still-legacy consumers. Legacy evidence, queue reconciliation and rollback support remain until their last consumer exits. If a consumer still needs an old executable path, transfer is blocked; do not leave that path producing duplicate effects.

| 1.x worker | Final 2.x replacement | Remaining 1.x consumers | Last consumer wave | Final retirement window and condition |
|---|---|---|---|---|
| A005 | Portable backup operator, logical dump/PITR, export manifest and independently verified restore; not SQL alone | All other 51 non-retired-at-review workers; full ID list in JSON (conservative) | 14 | 14: All W1-W13 domains accepted; zero remaining 1.x finite Tasks, ad-hoc work, claims, retries, provider outcomes or unclassified consumers. Residual support cohort drains together in T14; equivalent 2.x checks stay active. Preserve audit/retention and independently rehearse restore/rollback. Two successful clean-room restore cycles and approved RPO/RTO required; retain legacy backup while any 1.x recovery obligation remains. |
| A008 | SQL constraints/fences and bounded recovery.sweep plus flow assertions and independent watchdog | All other 51 non-retired-at-review workers; full ID list in JSON (conservative) | 14 | 14: All W1-W13 domains accepted; zero remaining 1.x finite Tasks, ad-hoc work, claims, retries, provider outcomes or unclassified consumers. Residual support cohort drains together in T14; equivalent 2.x checks stay active. Preserve audit/retention and independently rehearse restore/rollback. Do not stop because SQL replacement tests pass. |
| A009 | SQL business/flow assertion views plus retained semantic/provider audit samples | All other 51 non-retired-at-review workers; full ID list in JSON (conservative) | 14 | 14: All W1-W13 domains accepted; zero remaining 1.x finite Tasks, ad-hoc work, claims, retries, provider outcomes or unclassified consumers. Residual support cohort drains together in T14; equivalent 2.x checks stay active. Preserve audit/retention and independently rehearse restore/rollback. Do not stop because SQL replacement tests pass. |
| A011 | Transactional Task completion, required evidence, events and provider exception reconciliation | All other 51 non-retired-at-review workers; full ID list in JSON (conservative) | 14 | 14: All W1-W13 domains accepted; zero remaining 1.x finite Tasks, ad-hoc work, claims, retries, provider outcomes or unclassified consumers. Residual support cohort drains together in T14; equivalent 2.x checks stay active. Preserve audit/retention and independently rehearse restore/rollback. Do not stop because SQL replacement tests pass. |
| A012 | Content-addressed backup/export manifest verification and restore linkage | All other 51 non-retired-at-review workers; full ID list in JSON (conservative) | 14 | 14: All W1-W13 domains accepted; zero remaining 1.x finite Tasks, ad-hoc work, claims, retries, provider outcomes or unclassified consumers. Residual support cohort drains together in T14; equivalent 2.x checks stay active. Preserve audit/retention and independently rehearse restore/rollback. Do not stop because SQL replacement tests pass. |
| A013 | Immutable event/audit replay and projection conformance | All other 51 non-retired-at-review workers; full ID list in JSON (conservative) | 14 | 14: All W1-W13 domains accepted; zero remaining 1.x finite Tasks, ad-hoc work, claims, retries, provider outcomes or unclassified consumers. Residual support cohort drains together in T14; equivalent 2.x checks stay active. Preserve audit/retention and independently rehearse restore/rollback. Do not stop because SQL replacement tests pass. |
| A014 | CI plus operational capability/operation conformance; tests remain, scheduled Sheets worker retires | All other 51 non-retired-at-review workers; full ID list in JSON (conservative) | 14 | 14: All W1-W13 domains accepted; zero remaining 1.x finite Tasks, ad-hoc work, claims, retries, provider outcomes or unclassified consumers. Residual support cohort drains together in T14; equivalent 2.x checks stay active. Preserve audit/retention and independently rehearse restore/rollback. Do not stop because SQL replacement tests pass. |
| A024 | Generic SQL dispatcher plus Online semantic executor and preserved finite-task business capabilities | All other 51 non-retired-at-review workers; full ID list in JSON (conservative) | 14 | 14: All W1-W13 domains accepted; zero remaining 1.x finite Tasks, ad-hoc work, claims, retries, provider outcomes or unclassified consumers. Residual support cohort drains together in T14; equivalent 2.x checks stay active. Preserve audit/retention and independently rehearse restore/rollback. Do not stop because SQL replacement tests pass. |
| A025 | selection/claim_work, claim uniqueness/fencing and lease/recovery sweep | All other 51 non-retired-at-review workers; full ID list in JSON (conservative) | 14 | 14: All W1-W13 domains accepted; zero remaining 1.x finite Tasks, ad-hoc work, claims, retries, provider outcomes or unclassified consumers. Residual support cohort drains together in T14; equivalent 2.x checks stay active. Preserve audit/retention and independently rehearse restore/rollback. Do not stop because SQL replacement tests pass. |
| A003 | Ingestion invariants and flow assertions, provider sampling and semantic quality audit | A001, A002, A007, A035 | 5 | 5: W5 entire filing unit accepted; seeded mismatch detected and current consumers/ordering barriers reconciled. |
| A029-B | SQL staffing feature projections/materializations | A019, A020, A021 | 4 | 4: W4 transfers all feature/forecast/feedback stages, preserves fallback and proves feature parity. Keep A029-B in 1.x during W1-W3. |
| A036 | Calendar threshold/recurrence policy plus transport and semantic exception adapter | A028 | 13 | 13: W13 jointly transfers reminder obligations and transport after cancellation/DST/dedup acceptance. |
| A037 | SQL status projection/snapshot/versioning and retained notification policy (not all implemented) | A022, A042, A043, A044 | 9 | 9: W9 complete status unit accepted, including remaining 1.x health visibility; notification transport remains 1.x until W13. |
| A038 | SQL status projection/snapshot/versioning and retained notification policy (not all implemented) | A022, A042, A043, A044 | 9 | 9: W9 complete status unit accepted, including remaining 1.x health visibility; notification transport remains 1.x until W13. |
| A039 | SQL status projection/snapshot/versioning and retained notification policy (not all implemented) | A022, A042, A043, A044 | 9 | 9: W9 complete status unit accepted, including remaining 1.x health visibility; notification transport remains 1.x until W13. |
| A040 | SQL status projection/snapshot/versioning and retained notification policy (not all implemented) | A022, A042, A043, A044 | 9 | 9: W9 complete status unit accepted, including remaining 1.x health visibility; notification transport remains 1.x until W13. |
| A041 | SQL status projection/snapshot/versioning and retained notification policy (not all implemented) | A022, A042, A043, A044 | 9 | 9: W9 complete status unit accepted, including remaining 1.x health visibility; notification transport remains 1.x until W13. |
| A042 | SQL status projection/snapshot/versioning and retained notification policy (not all implemented) | A022, A044 | 9 | 9: W9 complete status unit accepted, including remaining 1.x health visibility; notification transport remains 1.x until W13. |
| A043 | SQL status projection/snapshot/versioning and retained notification policy (not all implemented) | A022, A044 | 9 | 9: W9 complete status unit accepted, including remaining 1.x health visibility; notification transport remains 1.x until W13. |
| A045 | SQL executive/source-health projection and typed snapshot (still to adapt) | A026, A049, A050, A052 | 8 | 8: W8 complete dashboard assembly/materialization unit accepted; no independent producer erased by missing input. |
| A051 | SQL executive/source-health projection and typed snapshot (still to adapt) | A026, A049, A050, A052 | 8 | 8: W8 complete dashboard assembly/materialization unit accepted; no independent producer erased by missing input. |
| A022 | Deterministic SQL status snapshot/package with separate Resident renderer | A044 | 9 | 9: W9 package and renderer accepted together. |
| A026 | Typed dashboard snapshot/package plus optional semantic narrative | A004, A052 | 10 | 10: Do not retire legacy assembly until A052 and still-1.x A004 independently accept the exact canonical build produced by W8. E4 freshness behavior and prior artifact preservation are mandatory. |
| A047 | A029-owned acquisition plus deterministic POS dashboard projection | A026, A049 | 8 | 8: W1 may pause the duplicate acquisition only after the exact canonical source interface is independently accepted by both remaining legacy consumers. Retain adapter contract, evidence and rollback support through W8. |
| A015 | SQL coverage/deadline predicates plus retained semantic routing/follow-up business stages | A001, A002, A003, A004, A005, A006, A007, A008, A009, A010, A011, A012, A013, A014, A016, A018, A019, A020, A021, A022, A023, A024, A025, A026, A027, A028, A029, A029-B, A031, A032, A033, A035, A036, A037, A038, A039, A040, A041, A042, A043, A044, A045, A046, A047, A048, A049, A050, A051, A052, A053, A054 | 14 | 14: W12 functional transfer requires residual consumers to use the sole new coverage/follow-up owner and satisfied requests to remain satisfied. Legacy coverage/reconciliation evidence and rollback support remain through T14; no competing task mutation or notification creation. |
| A016 | SQL coverage/deadline predicates plus retained semantic routing/follow-up business stages | A001, A002, A003, A004, A005, A006, A007, A008, A009, A010, A011, A012, A013, A014, A015, A018, A019, A020, A021, A022, A023, A024, A025, A026, A027, A028, A029, A029-B, A031, A032, A033, A035, A036, A037, A038, A039, A040, A041, A042, A043, A044, A045, A046, A047, A048, A049, A050, A051, A052, A053, A054 | 14 | 14: W12 functional transfer requires residual consumers to use the sole new coverage/follow-up owner and satisfied requests to remain satisfied. Legacy coverage/reconciliation evidence and rollback support remain through T14; no competing task mutation or notification creation. |
| A010 | Shared SQL delivery/outbox state plus channel-specific Resident adapters and provider reconciliation | A001, A002, A004, A005, A006, A007, A008, A009, A011, A012, A013, A014, A015, A016, A018, A019, A020, A021, A022, A023, A024, A025, A026, A027, A028, A029, A031, A033, A035, A036, A042, A046, A048, A049, A050, A053, A054 | 14 | 14: W13 functional transfer requires reconciliation of every old obligation and verified rebinding of T14 support alerts to sole 2.x transport; no retained infrastructure may invoke legacy sends. Final legacy queue/mechanics removal waits for T14 consumer drain. |
| A027 | Shared SQL delivery/outbox state plus channel-specific Resident adapters and provider reconciliation | A001, A002, A004, A005, A006, A007, A008, A009, A010, A011, A012, A013, A014, A015, A016, A018, A019, A020, A021, A022, A023, A024, A025, A026, A028, A029, A031, A033, A035, A036, A042, A046, A048, A049, A050, A053, A054 | 14 | 14: W13 functional transfer requires reconciliation of every old obligation and verified rebinding of T14 support alerts to sole 2.x transport; no retained infrastructure may invoke legacy sends. Final legacy queue/mechanics removal waits for T14 consumer drain. |
| A028 | Shared SQL delivery/outbox state plus channel-specific Resident adapters and provider reconciliation | A001, A002, A004, A005, A006, A007, A008, A009, A010, A011, A012, A013, A014, A015, A016, A018, A019, A020, A021, A022, A023, A024, A025, A026, A027, A029, A031, A033, A035, A036, A042, A046, A048, A049, A050, A053, A054 | 14 | 14: W13 functional transfer requires reconciliation of every old obligation and verified rebinding of T14 support alerts to sole 2.x transport; no retained infrastructure may invoke legacy sends. Final legacy queue/mechanics removal waits for T14 consumer drain. |

**Historical-only A017/A030/A034:** preserve their finite/retired evidence; current terminal state, dependencies and unmatched obligations must be reconciled before archival. This plan neither reactivates nor newly disables them.

## Alternating Online launchers

**Supported:** architecturally compatible, not implemented or operationally accepted.

1.x at t=0,8,16 minutes; 2.x at t=4,12,20 minutes: four-minute total opportunity, eight-minute opportunity for each architecture. This is a proposed pattern, not a freshly verified schedule.

ADR-009 capability routing and Phase 2 executor policies/claims do not require one global launcher or four-minute per-surface cadence; no live 2.x semantic launcher exists in Resident acceptance.

Required implementation:

- Deploy separate scoped Online2x entry point and identity; use narrow SQL packages
- Add domain/object ownership admission to both launchers and every downstream effect path, including A024 and Resident; cadence alone provides no ownership fence
- Review/change actual launcher schedule and preserve instance/capacity/claim fences and retry semantics; long runs may overlap only across independently owned work
- Provide due-occurrence/recovery drivers and safe restart/missed-launch handling
- Measure end-to-end semantic queue age against target SLAs; eight-minute opportunities cannot guarantee <1m semantic latency or <5m briefing latency; use existing event/wakeup design or separately approved cadence where required
- Prove ownership rejection, stale-owner rejection, unknown resource denial, launch loss/restart and no duplicate effects

Restore verified launcher schedule independently of domain ownership. Never re-enable migrated domains merely because 1.x launch frequency increases.

The eight-minute semantic opportunity is not equivalent to the existing target latencies. Deterministic Resident dispatch and SQL wakeups need not wait for an Online launch; semantic stages do. Do not claim sub-minute semantic acceptance on this schedule without a separately accepted event/launch path.

## Build readiness, blockers and validation

**ReadyToBeginWave1:** yes for a subsequent bounded synthetic/shadow adapter build; no for live transfer. Remaining work: reuse A029 logic behind SQL packages, implement governed batch/checkpoint and A047 projection, preserve A029-B/A026 source interfaces, prove exact independent read-back and restart behavior, then meet G1-G7. No migration implementation is included here.

**Highest effect risk:** intake/filing W5; review ACK W6; controlled documentation W7; privacy/financial dashboard W8; communications W13. **Main cross-domain blockers:** W1 legacy source compatibility; W3/W5/W6/W12 shared Task ownership; W4 forecast/actual lifecycle; W8 source/privacy coupling; W9 mixed-system observability; W11 backup exclusion; W13 all producer/legacy-outcome reconciliation.

Document validation checks 55 unique assignments, all 18 required wave fields, consumer IDs, computed retirement maxima, retirement no earlier than the last consumer, and global infrastructure retention in every wave. `python -B scripts/check.py` passed at 2026-09-30T01:31:18Z: 61 passed, zero failures/errors, 26 historical integration placeholders skipped. Baseline hashes and the unchanged 55-worker registry conversion passed. These are planning/offline checks, not new production or database acceptance.
