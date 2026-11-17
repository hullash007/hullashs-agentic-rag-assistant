# Hullash's Agentic RAG Assistant

A source-first document workspace built with FastAPI, LangGraph and PostgreSQL/pgvector. Upload a nonconfidential sample, retrieve passages and inspect their source locations.

**Current scope: a retrieval-pipeline prototype, not a finished semantic RAG assistant.** Retrieval uses synthetic vectors. Hosted AI answers are off. Google sign-in and per-user isolation are implemented, but hosted two-account acceptance is still pending and document actions remain disabled during validation.

[Preview the sign-in page](https://hullash-rag-demo.onrender.com/) · [Architecture and verification](docs/PROJECT_STATUS.md) · [Local setup](LOCAL_DEVELOPMENT.md) · [Google identity design](GOOGLE_SIGNIN.md)

![Hosted desktop sign-in preview, no authenticated workspace](docs/screenshots/hosted-login-desktop.png)

*Actual hosted sign-in page, captured November 17, 2026. The Google button is visible; this screenshot is not proof of a completed Google session. Free hosting may sleep.*

## What this project demonstrates

- **Document provenance:** bounded TXT, PDF, DOCX and XLSX ingestion with original bytes, extracted text, source hashes and typed document/page/paragraph/sheet-row citations.
- **A persisted retrieval path:** query embedding seam -> registered retrieval tool -> compiled LangGraph -> PostgreSQL/pgvector -> bounded evidence bundle. Tool selection is explicit, not model-selected.
- **Identity-aware storage:** Google signed-token verification, server-derived tenant scope, nonce-bound login, opaque sessions, CSRF checks and scoped quotas. Real disposable PostgreSQL tests cover two synthetic subjects and legacy-record exclusion; live two-Google-user acceptance remains open.
- **Honest product boundaries:** responsive interface, no generated-answer claims, sample-only retention notice and separate operator-controlled activation gates.

## Works, verified locally, and still in progress

| Area | Evidence and current limit |
| --- | --- |
| Hosted interface | Sign-in page and Google button render on desktop/mobile. Not a completed login or open document demo. |
| Upload, persistence and citations | Local application/browser tests and disposable PostgreSQL checks. Hosted Google data routes remain disabled. |
| Per-user scope | Implemented and locally tested, including identical bytes under separate subjects and reverse legacy exclusion. Two real hosted accounts not yet accepted. |
| Semantic retrieval | Not enabled. Current vectors exercise plumbing, not meaning-based relevance. |
| Generated answers | Hosted factory refuses enablement. Provider-neutral schema/validation and an optional local Gemini adapter exist, not a working hosted answer feature. |
| Private model integration | Separate private embedding qualification exists; no app transport, active semantic profile or index migration. Full-RAG generation quality, capacity and latency remain unresolved. |

## Local development

Use Python 3.12 and the hash-pinned application lock. Python 3.12.15 is the tested replacement baseline, not a claim of parity with an earlier unavailable environment.

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install --require-hashes -r requirements.recovery.lock
python -m pip check
python -m pytest -v
```

The default API is mock-first and requires no model key:

```sh
python -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
```

That entrypoint is the original development API, **not the document workspace**. For the upload/query workspace, first prepare the private disposable PostgreSQL/pgvector and separate parser environments described in [LOCAL_DEVELOPMENT.md](LOCAL_DEVELOPMENT.md), then run `python -m backend.ingestion.local_startup`. It binds only to `127.0.0.1:58219` and has no authentication. Never expose it publicly or use confidential files.

The ordinary pytest run blocks outbound sockets during test execution and skips the explicit disposable-database tests when their socket is not configured. It is not an OS sandbox and does not reproduce all integration checks. See [verification scope](docs/PROJECT_STATUS.md#verification-scope).

## Workspace preview

![Local workspace with a fabricated sample and test-double identity](docs/screenshots/local-workspace-desktop.png)

*Local HTTPS browser test with a fabricated sample and test-double identity. It demonstrates layout, upload/query and citation display, not real Google authentication or hosted tenant acceptance.*

<details>
<summary>Hosted mobile sign-in preview</summary>

![Hosted mobile sign-in preview, no authenticated session](docs/screenshots/hosted-login-mobile.png)

</details>

## Data and safety limits

Use disposable, nonconfidential samples only. Uploads persist in PostgreSQL, including original bytes and extracted text. There is no automatic expiry or self-service delete. Application-level tenant scope is not database row-level security or physical/operator isolation. Parser subprocess restrictions are not a hostile-file OS sandbox.

No paid service, card, subscription upgrade or public inference endpoint is part of this milestone. Current deployment instructions and limits are in [HOSTED_PREPARATION.md](HOSTED_PREPARATION.md). Code and screenshots describe a prototype; they are not security certification, production readiness or uptime guarantees.

## Repository guide

- `backend/ingestion/`: parsing, chunking, provenance, persistence, retrieval, answer contracts, auth gates and UI.
- `apps/api/`: original mock-first development API.
- `tests/`: API/auth/safety tests and opt-in disposable-database tests.
- `packaging/`: pinned multi-interpreter container recipe and offline smoke.
- `docs/`: current architecture, verification boundaries and sanitized screenshots.

## License

MIT. See [LICENSE](LICENSE).
