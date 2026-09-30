# Production authority: owner decision, 2026-09-29

The ECOS 2.x PostgreSQL project `loonpojawpfagzobxoko` is production infrastructure.
Resident Ada 2.x is production-capable; Online Ada 2.x will be production-capable.
There is no development-database promotion or global future production cutover.
Both architectures coexist as production infrastructure during migration.

Exactly one architecture owns each side-effecting functional domain. Toast acquisition
and dashboard source facts (A029/A047) remain owned by 1X until all Wave 1 acceptance,
old-path pause/drain, independent read-back and rollback gates pass. Staffing features
(A029-B) remain owned by 1X until Wave 4. Other domains are not activated by this decision.

The existing AFR-ECOS-000252 compatibility publication and matching registry/hash evidence
are authorized production outputs after Wave 1 transfers. They support unchanged A029-B.
Toast remains provider-read-only. Channel/recipient approval, reconciliation, fencing,
authorization, leases, capability matching and secret protection remain mandatory.

## Implementation

Forward migration 21 replaces the live blanket guard in `ecos.operate` with explicit
`principal_domain` enrollment, `domain_authority` ownership/epoch checks, and object-domain
isolation in addition to existing grants and sensitivity checks. Unknown enrollment fails
closed. Shadow principals can execute control operations and bounded shadow ingestion only;
they cannot invoke general business mutation operations. Production principals require 2X
ownership and the current authority epoch before operation replay as well as new commits.
Selection and existing fence checks reject an occurrence outside its enrolled domain.
Administrative ownership changes require a new epoch and evidence and create an audit event.
Executors cannot mutate the authority tables. Database identity describes infrastructure,
not permission to execute every domain. The legacy effects boolean is descriptive only.

External effects must revalidate the current claim and domain at their provider boundary.
Transfer/rollback must drain in-flight provider calls before changing ownership. No SQL
check can undo an external call already in flight; an unresolved outcome blocks transfer.

Historical migration files and prior acceptance reports retain their original wording as
evidence. The old Phase 2 apply-plan guard is scoped to replaying that historical prefix,
not the current production operating model. This decision supersedes development-only
assumptions in older README, baseline implementation descriptions and migration-plan G1.

Migration 21 does not transfer Toast, start workers, publish Drive files, or migrate A029-B.
Production-capable does not mean every Wave 1 capability has passed acceptance.

## Current verified state

Forward migrations 21–23 are applied to the production database. Toast and staffing
remain owned by 1X; tested Toast shadow work is isolated from production-mode data.
See [Wave 1 acceptance and the reproduced 1.x pause-fence blocker](WAVE1_ACCEPTANCE.md).
