# Hosted prototype: configuration and limits

Status, November 17, 2026: the HTTPS sign-in preview is deployed at https://hullash-rag-demo.onrender.com/. Google mode is configured; document operations remain disabled during real-session and two-account validation. This is not an open upload demo or completed sign-in rollout. Synthetic retrieval and AI answers OFF remain explicit.

This page replaces earlier deployment-attempt notes that said no app URL existed. [packaging/BUILD.md](packaging/BUILD.md) preserves the earlier image-smoke history; historical checkpoints are not the current deployment state.

## Hosting model

The app process runs on Render and sample records use a separate Neon PostgreSQL/pgvector database. Free hosting can sleep or suspend; the prototype has no uptime/capacity guarantee. Do not assume a free plan permits unlimited use, and do not enable a paid upgrade, attach a card or add paid fallback as part of setup. Check current vendor quotas directly rather than relying on historical numbers in a repository.

- https://render.com/docs/free
- https://neon.com/docs/introduction/plans
- https://neon.com/docs/extensions/pgvector

## Explicit hosted entrypoint

`python -m backend.ingestion.hosted_demo` accepts the platform PORT, binds one worker and disables access logs. The container's default command deliberately runs an offline loopback smoke and exits; it is not the hosted service command. Do not expose the unauthenticated local startup or original development `/chat` API instead.

Operator-managed configuration, with secrets supplied outside the repository:

| Setting | Purpose |
| --- | --- |
| `DEMO_AUTH_MODE=google` | Google gate, no Basic fallback accepted. |
| `GOOGLE_CLIENT_ID` | Dedicated web client matching the exact app origin. No client secret is needed for this identity-token flow. |
| `GOOGLE_AUDIENCE` | Explicit application audience. `any_google` is not evidence that hosted isolation has passed. |
| `GOOGLE_OPERATIONS_ENABLED=false` | Permit login/status/logout validation while rejecting document actions. Keep false until staged acceptance permits otherwise. |
| `DEMO_ORIGIN` | Exact HTTPS origin, without path/trailing slash. |
| `DATABASE_URL` | Secret `postgresql+psycopg` URL with `sslmode=verify-full&sslrootcert=system`. Never log it or use an existing unrelated database. |
| `RAG_PDF_PYTHON`, `RAG_OFFICE_PYTHON` | Existing absolute paths to the separate pinned parser interpreters. |
| `ANSWER_GENERATION_ENABLED=false` | Mandatory retrieval-only hosted mode; the factory refuses answer enablement. |

`GOOGLE_ALLOWED_EMAILS` is used only with allowlist audience mode. A test-user list in Google Cloud is not app authorization. For restricted staged data testing, explicitly use the reviewed app audience policy; do not assume the Cloud list restricts basic identity scopes.

Remove retained Basic secrets from live configuration only after the completed replacement validation and rollback decision. Do not print their values. Missing/invalid auth configuration must fail startup rather than open access. See [GOOGLE_SIGNIN.md](GOOGLE_SIGNIN.md) for exact token/session/scoping design.

## Storage and request limits

Uploads are at most 2 MiB. Application quotas are 20 documents / 5 MiB per scoped user and 100 documents / 25 MiB globally. Limits are prototype controls, not vendor quota or denial-of-service guarantees. Rate, session and concurrency state is process-local; use one worker. Original bytes, extracted text, citations and vectors persist in the database until operator removal. No automatic expiry or self-service delete is implemented. Stopping the app does not erase uploads or vendor history/backups.

Only disposable nonconfidential samples are appropriate. Binary parsers have subprocess limits but are not a hostile-file OS sandbox. PDF has no OCR; DOCX supports body paragraphs rather than general table extraction; controlled XLSX has typed row locations and rejects unsupported structures.

The data routes are `POST /documents`, `POST /query` and `POST /answer`, with `/capabilities` reporting the configured mode. Negative tests must exercise the real route names, not a nonexistent `/upload` alias. Mutating authenticated requests require exact Origin and the Google session CSRF header. Public health is `GET /healthz`; health does not prove authenticated upload/query or external model readiness.

## Remaining hosted acceptance

Real Google sessions and two-account dummy isolation are incomplete. Do not call the prototype fully multi-user validated because local subject-scoping tests passed. Keep legacy shared records excluded and never guess their owners. Do not widen access, enable inference, migrate vectors or connect compute as a side effect of UI/deployment work.

Any future model integration must separately qualify protected transport, scoped credentials, token/profile identity, whole-operation budgets, atomic persistence and privacy copy. Every indexed text chunk would leave the app for embeddings; selected evidence and questions would leave for answers. None of that is active in this hosted version.
