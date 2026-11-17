# Google identity and isolated sample workspaces

Development status, 2026-11-17: Google mode has genuine two-account session/logout evidence and independently reviewed bounded fabricated-fixture separation. Document operations were restored to disabled after the restricted test. The exact two-tester application allowlist remains; this is not a general Google-account rollout. See [current verification scope](docs/PROJECT_STATUS.md).

## Scope

Replace the hosted shared Basic login with current Google Identity Services and polish the UI. Google mode serves only tenant-scoped document operations. No Gmail/Drive permissions, Google API access tokens, refresh tokens, client secret, model calls or automatic schema changes. Synthetic retrieval remains explicitly non-semantic and generated answers remain off.

## Identity and sessions

The GIS JavaScript popup callback posts its credential with a browser-bound, single-use nonce to the same origin. An HttpOnly Secure SameSiteStrict challenge cookie, exact Origin, outstanding challenge and verified token nonce must agree. This is a custom callback flow, not Google's automatic login_uri POST flow. The latter's g_csrf_token protocol must not be substituted for this callback without adapting the server.

The official google-auth verifier validates the signature against Google's certificates, exact configured web-client audience, issuer and expiry. Server checks also require a verified email, well-formed stable provider sub and nonce. Tenant identity comes from verified sub, never email or a client header/body tenant field. The temporary display email is not an ownership key.

Random opaque app sessions stay in bounded process memory and use HttpOnly Secure SameSiteStrict cookies. A restart logs everyone out. Sessions last at most one hour and not beyond the sign-in token's expiry. Sign-out revokes the app session, not the Google account session. Every mutating app operation also requires exact Origin and a per-session CSRF header. Duplicate/missing/foreign/null Origin, duplicate session cookies, forged identity, invalid nonce and stale sessions fail closed. No token or cookie value should be logged.

## Repository isolation

Each request constructs an immutable repository scope from the authenticated subject. A domain-separated hash prefixes its server-created source IDs. This makes identical bytes owned by two users separate source/document/chunk/vector identities while preserving the original file hash and citation offsets. Store, dedup lookup, load and retrieval all enforce the scope. There is no global mutable current-user variable.

Legacy shared records have no tenant prefix and are excluded from Google mode. In the reverse direction, retained legacy/Basic repositories exclude all reserved tenant- records in SQL and reject direct tenant-ID store/find; Basic rollback cannot see Google workspaces. They are not deleted or silently assigned. No migration or DDL is required. Application-level isolation is not PostgreSQL row-level security or separate physical databases. Database operators retain access.

## Bounded free demo

Each upload is at most2MiB. Scoped accounts may store20documents or5MiB; the service permits100documents or25MiB in total. Quota checks and insert share a transaction/advisory lock. Dedup within an existing owner remains possible at quota. Sessions/nonces and operation concurrency are bounded. A global30protected operations/minute limit and120total non-health requests/minute limit apply. Vendor quotas may still suspend service. There is no uptime or capacity guarantee.

Original files, extracted text, citations and vectors persist until operator removal. No automatic expiry or self-service delete. Nonconfidential samples only. The privacy page explains hosting, operator access, account data and support/removal requests.

## Configuration and rollout

Google mode is currently restricted to the two approved testers with data operations disabled. Preserve that gate; the bounded test is not broader-release approval. Google mode requires:

- DEMO_AUTH_MODE=google
- GOOGLE_CLIENT_ID: the dedicated project's web client ID
- GOOGLE_AUDIENCE=allowlist for the current restricted stage; GOOGLE_ALLOWED_EMAILS contains only the two approved testers, managed outside this repository. any_google is a separate rollout configuration, not the current state
- GOOGLE_OPERATIONS_ENABLED=false in the restored current state; any later enablement requires a coordinated rollout decision, not merely a successful login
- DEMO_ORIGIN: exact HTTPS origin without trailing slash/path
- Existing verified-TLS database URL and parser paths
- ANSWER_GENERATION_ENABLED=false

Remove DEMO_USERNAME/DEMO_PASSWORD from live configuration only at the completed Google switch. No Basic fallback is accepted in Google mode. Missing Google settings fail startup. The legacy Basic implementation remains for local regression/rollback, not a second production login.

Verify source hashes against the tested tree before deployment. Verify the actual configured Google flow and hosted negative/tenant paths before claiming replacement success. A local test-double login or an ephemeral certificate signature test is not a real Google sign-in. Keep main unchanged. Do not widen legacy record access, enable inference, attach billing or connect another compute service as part of this rollout.

## Local evidence

The full suite includes official verifier signature/audience/issuer/expiry negatives with an ephemeral test key, nonce/CSRF/session tests, real disposable PostgreSQL/pgvector two-subject isolation and scoped quotas, identical-file independent ownership, legacy exclusion and concurrency. Local HTTPS real-browser tests check CSP, account loading, sample upload/query/citation display and sign-out; identity is explicitly a test double. Runtime GUI desktop/mobile inspection is separate from hosted proof.

## Current source documents

- https://developers.google.com/identity/gsi/web/guides/get-google-api-clientid
- https://developers.google.com/identity/gsi/web/guides/verify-google-id-token
- https://developers.google.com/identity/gsi/web/reference/js-reference
- https://developers.google.com/identity/gsi/web/guides/integrate
- https://support.google.com/cloud/answer/15549945?hl=en
- https://developers.google.com/terms/api-services-user-data-policy
- https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
- https://render.com/docs/free

Basic identity scopes/Sign in with Google are exempt from Google's Testing test-user list and seven-day authorization expiry. A test-user list is not a substitute for application authorization or isolation. This app manages its own shorter session lifetime.
