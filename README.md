# Hullash's agentic rag assistant

M1 backend foundation: FastAPI with a single-node LangGraph and a mock-first language-model adapter. It does not yet ingest documents, retrieve context, use tools or return citations. Those belong to later milestones.

## Run locally

Use Python 3.12 in a fresh virtual environment:

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install --require-hashes -r requirements.recovery.lock
python -m pip check
python -m pytest -v
```

The default provider is `mock`. `/health` and tests do not need a Gemini key. To run the development API only on your own machine:

```sh
python -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
```

Do not expose `/chat` publicly. Authentication, rate and concurrency limits, provider-client lifecycle management and deployment security review remain predeployment work. No production deployment is included.

## Configuration

`.env.example` contains placeholders only. Copy it to `.env` for reference when configuring environment variables, but the application does not automatically load that file. Export values in your shell or configure them in your process runner. Never commit `.env`, credentials or API keys.

`LLM_PROVIDER=mock` is the safe default. The optional `gemini` provider requires `GEMINI_API_KEY` and `GEMINI_MODEL`. Its default timeout is 15000 milliseconds, output limit 128 tokens, and SDK attempts=1 disables automatic retries. Live Gemini generation has not succeeded in the recorded project smoke checks; offline tests are not live-integration evidence. Do not make additional live requests without the project's current approval.

## Replacement dependency baseline

`requirements.in` reconstructs the ten direct dependency constraints from the recorded project setup, including the corrected `google-genai>=3.3,<4` constraint. It is not a byte-for-byte recovery of the remote file.

`requirements.recovery.lock` is a NEW hash-pinned dependency baseline generated on 2026-11-16 using Python 3.12.15, pip 26.3 and pip-tools 7.6.2. Its SHA256 is:

```text
8c5898c4969df3a18d89d1a638620c910b8f5c5c0713b68b2441e8ea6df87d47
```

The original remote lockfile was not recovered. This replacement does not establish original transitive-dependency parity. The original environment used Python 3.12.16. The new baseline contains 63 locked packages; the recorded 64-package environment inventory also includes pip.

Two independent clean environments installed this replacement with `--require-hashes`, passed `pip check` and compilation, and produced separate results: original Stage6 source 22 tests passed, hardened source in this repository 28 tests passed. The older source snapshot is not included in this delivery tree.

## Offline test safety

`tests/conftest.py` sets mock configuration and applies an autouse socket/DNS-blocking fixture during tests. A pytest fixture starts after collection/imports, so it does not block network activity during module import. It is not an operating-system network sandbox and cannot cover subprocesses or every possible network API. The recorded clean validation used an additional external runner that stripped keys/tracing settings and applied socket/DNS guards before importing pytest and the application. Use an isolated, network-restricted environment for stronger assurance.

Safety tests check blocked sockets/DNS and ensure request prompts, exception contents and tracebacks are not written to the application error logs. No real credentials are used in these tests.

## Database validation and remaining gates

A separate disposable local PostgreSQL 16.16 instance with pgvector 0.8.7 returned the actual extension/schema row, vector type, distance calculations and two synthetic inserted/read rows. It used a private Unix socket with TCP disabled, then the database was dropped and the server stopped and removed. This is local extension evidence only. It does not verify application SQLAlchemy integration, Codespaces database compatibility or deployment infrastructure.

Reviewer acceptance, CI execution, private-port configuration review and delivery verification remain separate gates. The original remote-only devcontainer and lockfile are excluded from this tree because they were not recovered and fully scanned. No claim of complete current remote-source byte parity or M1/M2 acceptance is made.

## License

MIT. See `LICENSE`.
