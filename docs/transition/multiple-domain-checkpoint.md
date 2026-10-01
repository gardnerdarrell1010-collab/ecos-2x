# Multiple functional domains on existing principals

Migration 36 removes the one-domain-per-principal primary key and resolves access,
selection and provider-effect authority against the relevant explicit domain binding.
Object grants and operation grants remain separate from capability-based execution fit.
Existing identity, epoch, claim and provider-effect checks remain in force. The general
epoch gate conservatively checks every binding held by the principal.

The existing Online and Gmail Resident principals now also have an explicit
`sms.operations` binding. No object, operation or capability grants were added by
this deployment. Toast bindings and all existing principal bindings were preserved.
The abandoned separate SMS identity remains disabled; its acceptance is aborted.

Two internal PostgreSQL round trips passed on a disposable database. One principal
claimed work in each of two domains, retrieved its package, transitioned its scoped
task, completed work and independently read back success. Duplicate completion was
idempotent; an object without its own grant was denied. Provider commands remained
zero. Live reads using the existing Online, Gmail Resident and Toast Resident
credentials also passed after deployment. These are access regression checks, not
new Gmail or Toast functional acceptance runs.

This checkpoint accepts only the domain correction. It does not accept Batch 13
functions. A010 retains its previously accepted draft boundary. A027, A028, A031,
A034 replacement coverage and A036 remain pending implementation and acceptance.
No external provider effects or production continuation processing occurred.

Detailed preimage, deployment and independent access receipts remain in restricted
local evidence. No credentials or source business records are included here.
