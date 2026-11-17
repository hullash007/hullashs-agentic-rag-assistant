# Protected retrieval demo - preparation, not deployment approval

Status: local source only. No hosted URL, account, resource or deployment has been created. Do not run this entrypoint on an internet-facing machine until the owner has approved the protected deployment and its audience/data retention. A source checkpoint is not a working app link.

## Proposed route

Render Free web service for the FastAPI process and Neon Free Postgres with pgvector. Keep answer generation off. This is an interim retrieval demo with synthetic vectors, not the finished semantic RAG assistant.

Current vendor documentation:

- https://render.com/docs/free
- https://render.com/docs/deploy-fastapi
- https://neon.com/docs/introduction/plans
- https://neon.com/docs/extensions/pgvector

Render Free sleeps after 15 minutes of inactivity and can take about a minute to wake. Its filesystem is ephemeral. Monthly bandwidth/build limits can trigger charges if a payment method is attached; without a payment method the documented alternative is suspension/build disabling. The actual account, plan and billing settings have not been inspected. Do not promise zero cost from the plan name alone. Do not use Render Free Postgres for persistence: it expires after 30 days.

Neon Free currently includes 100 CU-hours per project/month, 1 GB Postgres storage per project and 5 GB public transfer per project/month. These are quotas, not unlimited capacity. pgvector is included on every plan. Actual account eligibility and usage remain unverified.

## Entrypoint and protection

`python -m backend.ingestion.hosted_demo` is separate from the local loopback startup. It accepts the platform `PORT`, binds one process, disables access logs and refuses answer-model enablement. Do not run it as a tunnel or substitute it for the private local startup during development.

Required operator configuration:

- `DEMO_USERNAME` and a randomly generated `DEMO_PASSWORD` of 32..256 characters, collected through secure secret storage, never chat or source.
- `DEMO_ORIGIN` set to the exact HTTPS origin of the approved app (no path or trailing slash). Every authenticated mutation must send exactly one matching Origin header. Missing, null, duplicate or foreign Origin is rejected before the app or body is processed. Non-browser clients must deliberately send that exact Origin and credentials. Origin is a browser CSRF defense, not a substitute for authentication.
- `DATABASE_URL` using `postgresql+psycopg`, explicit database credentials, `sslmode=verify-full&sslrootcert=system`. Do not log the URL. The platform needs an installed system CA bundle. TLS has not yet been tested against a real hosted database.
- Existing absolute `RAG_PDF_PYTHON` and `RAG_OFFICE_PYTHON` paths to their separately pinned interpreters.
- `ANSWER_GENERATION_ENABLED=false`.

The ASGI gate authenticates every application route, including the HTML, upload, query, answer and capability routes, before passing the request to the application. Only `GET /healthz` is public and returns a constant status. Authentication uses browser HTTP Basic and must be served exclusively through the host's verified HTTPS URL. It is not multi-user identity management, MFA, per-user authorization, logout/session management, or a general internet-abuse solution. The application does not terminate TLS itself.

Authenticated requests have a shared 30-per-minute process-local limit; mutating requests share one operation slot. Limits reset on process restart, are not distributed, and do not cap unauthenticated network traffic or all memory use. Use one worker only. A free host may still suspend the service under traffic.

Responses use no-store, nosniff and frame-denial headers. Parser subprocesses receive a minimal environment without database/auth/model secrets. The parser limits and Python socket stubs are not an OS sandbox; use sample/nonconfidential files only. The prototype has no multi-user corpus isolation. Do not share one demo password with an open audience.

## Database and retention

The hosted factory does not create an account, project, database, extension or schema. Separately approved provisioning must enable pgvector, establish the version/three-dimensional synthetic profile, and create the existing repository tables deliberately. Do not repoint it at an existing non-demo database. Confirm deletion/retention and supported cancellation/removal routes before uploading any user data.

No Gemini key is needed for this demo. The live answer adapter and its UI exist separately, but neither an approved deployment nor a successful Gemini answer has been established by that source code.

## Packaging and evidence

The unchanged application lock contains 63 exact hash-checked packages and uses the approved replacement Python 3.12.15, not the unavailable original 3.12.16. The PDF environment uses Python 3.10 with pypdf 7.1.0 and typing_extensions 4.16.0. The Office environment uses Python 3.12.15 with the six documented exact parser package versions. Regenerated parser lockfiles reproduce those versions, not a claim of parity with lost prior lock hashes.

Fresh local installation succeeded for all three environments. Actual PDF/DOCX/XLSX parser-child smoke tests succeeded with typed locations and reaped children. App environment disk size and idle module-import RSS measurements are not container size, peak concurrency memory, cold-start time, or proof of fit on Render Free. Docker/Podman are unavailable here; no container image has been built or deployed. Do not call packaging verified until the actual image/build and parser runtime are tested on a permitted builder.

Before an owner deployment choice can be executed: verify the exact account's free plan and no-charge behavior, build/package the two interpreter versions without dependency drift, verify image/runtime resource use, test HTTPS/private authentication and negative authorization paths on the intended platform, and inspect the actual app URL after deployment. No URL should be invented in advance.
