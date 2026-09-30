# Online hosted transport checkpoint

The existing repository had an OpenAPI contract and a Python semantic adapter,
but no hosted operation endpoint. The Supabase project had no Edge Functions,
Auth users, or OAuth clients. This is a missing hosted transport, not an existing
connection needing configuration.

The minimum candidate is `supabase/functions/online-ada-2x`. It uses the official
MCP SDK, validates asymmetric Supabase OAuth tokens, binds the exact OAuth subject
and client to one executor principal/instance, and accepts only the listed governed
operations. PostgreSQL remains responsible for operation grants, capabilities,
authority, claims and idempotency. The database connection refuses administrator
login names. No SQL tool is exposed. No local runtime or HOME-01 is required.

Edge Function version 1 is deployed to:
https://loonpojawpfagzobxoko.supabase.co/functions/v1/online-ada-2x

Independent HTTP verification: unauthenticated call returns 401 with the OAuth
resource-metadata challenge; discovery returns 200. Missing enrollment fails
closed. Gateway JWT checking is disabled because the function validates OAuth
JWTs itself and discovery must be accessible without credentials.

Validation: five local transport policy tests pass; Deno type check passes;
local HTTP discovery/unauthenticated/missing-enrollment tests pass. These are
not authenticated business-operation acceptance.

Supabase dashboard login is verified. Pending: OAuth server configuration and consent UI,
dedicated authenticated user/client and database enrollment, server-side secrets,
authenticated operation acceptance, actual ChatGPT custom-app connection and
scheduled invocation acceptance. Authenticated operation tests and HOME-01-offline
execution have not run. Do not activate production Online launchers yet.

Use existing Supabase Auth as the issuer; do not implement a new OAuth server.
Its OAuth consent frontend requires an HTTPS frontend host. Default Supabase
Edge domains rewrite HTML to plain text; no custom-domain purchase or additional
hosting platform has been authorized or provisioned by this checkpoint.

Server-side configuration names only: ECOS_ONLINE_PRINCIPAL_ID,
ECOS_ONLINE_INSTANCE_ID, ECOS_ONLINE_OAUTH_SUBJECT,
ECOS_ONLINE_OAUTH_CLIENT_ID, ECOS_ONLINE_OAUTH_AUDIENCE,
ECOS_ONLINE_DATABASE_URL, ECOS_ONLINE_DATABASE_CA.
Never put their secret values in Git, prompts, diagnostics or logs.

Resident continuity correction a292a9e is committed locally and applied at
migration 28. The owner separately approved its publication; the exact commit is pushed and
matches the remote branch. Ubuntu and Windows CI both pass.

## GitHub Pages consent deployment

Owner selected GitHub Pages. Commit 11c3bed publishes only the static consent
page and its scoped deployment workflow. Pages deployment 36710744979 passed;
HTTPS and browser rendering were verified. No password form is hosted there.
Site: https://gardnerdarrell1010-collab.github.io/ecos-2x/oauth/consent/
Supabase Site URL and the exact redirect URL are saved; OAuth server is enabled
with /oauth/consent/ and dynamic registration remains disabled. Public issuer
discovery works and JWKS exposes ES256. No Online executor enrollment is implied.
The GitHub sign-in provider is pending owner creation and direct entry of its
OAuth client credential. Setup tabs are prepared. No secret should be pasted
into chat, public Git or diagnostic logs. Production Online scheduling remains
blocked until dedicated enrollment and all live acceptance checks pass.
## Current failure boundary — 2026-09-30
ChatGPT reports authentication succeeded and action discovery failed. Function
logs at 17:09:46 UTC show POST 401 followed by POST 503 at the function root;
public resource metadata GET returns 200. The implementation returns JSON
online_enrollment_unavailable before MCP initialization when server enrollment
is missing. The dashboard independently confirms no custom secrets exist.
OAuth login and the dedicated database enrollment are prepared. The restricted
local enrollment directory contains server-secrets.env, now including the
verified OAuth subject. Owner must enter that file into the project Edge
Function Secrets screen and save it; do not paste it into chat or Git.
Next: retry the existing ChatGPT app connection, then run one synthetic governed
round trip and independent readback. No production launchers are enabled.
No authenticated business-operation acceptance is claimed.
