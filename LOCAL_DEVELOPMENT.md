# Local document workspace

This development branch contains opt-in ingestion, PostgreSQL persistence, a real compiled retrieval graph, and a small local upload/query interface. It is not a hosted assistant or completed milestone. The original application entrypoint is unchanged.

## What works locally

- Raw HTTP upload for UTF-8 text, bounded PDF, DOCX body paragraphs and controlled XLSX.
- Original bytes and full typed extracted provenance stored transactionally in PostgreSQL/pgvector.
- Separate text query through the existing StructuredTool/ToolNode/compiled LangGraph into the persisted database.
- Passage text, source fingerprints and typed document/page/paragraph/sheet-row citations.
- Desktop and mobile upload/query interface with explicit synthetic-retrieval labels.

The local provider uses constant synthetic vectors. It tests the real application path but does not rank passages by meaning or generate answers. No Gemini API key is needed or loaded by this startup.

## Prerequisites

Use the approved replacement Python3.12.15 application environment with unchanged requirements.recovery.lock, not an invented dependency subset. This replacement is not parity with the original unavailable Python3.12.16 environment.

Binary parsing uses separately pinned environments, not added application dependencies:

- PDF: Python3.10, pypdf7.1.0 and typing_extensions4.16.0.
- Office: Python3.12.15, python-docx1.2.0/lxml6.1.3/openpyxl3.1.5/et-xmlfile2.0.0/defusedxml0.7.1/typing_extensions4.16.0.

Prepare a new private local PostgreSQL16.16 database with pgvector0.8.7, peer authentication, no TCP listener and a private Unix socket at port55437. Enable `CREATE EXTENSION vector` only in that disposable database. The startup creates its own application tables; it does not provision a database, install dependencies, change existing databases, or fetch anything automatically.

## Start deliberately

From the repository root, with the application environment activated:

```bash
export RAG_LOCAL_DB_SOCKET=/absolute/path/to/private/socket
export RAG_LOCAL_DATABASE=rag_local_demo
export RAG_PDF_PYTHON=/absolute/path/to/pdf-environment/bin/python
export RAG_OFFICE_PYTHON=/absolute/path/to/office-environment/bin/python
python -m backend.ingestion.local_startup
```

The startup binds only to127.0.0.1:58219. Open that loopback address on the same machine. It is not a remote share link. Stop it with Ctrl-C; dispose of the synthetic database and test cluster after use.

No authentication is implemented. Do not change the bind address, expose a tunnel, add real documents, or deploy this local startup as a public service. A hosted assistant needs deliberate authentication, provider configuration, quota/cost/data handling checks, packaging and deployment work.

## HTTP contract

`POST /documents`: raw file bytes, supported Content-Type, X-Filename display basename. For Unicode filenames send percent-encoded X-Filename plus X-Filename-Encoding:uri. No client embeddings, locators, SQL, tool names or filesystem paths. Returns document identity, SHA/counts, stored/already_present.

`POST /query`: JSON containing query text(max2000chars), optional integer top_k1..10. Returns retrieval evidence, citations, scores and omissions with generated_answer:false, synthetic_vectors:true and explicit_not_model_selected tool selection.

The UI escapes all document text using textContent, not HTML interpolation.

## Important limits

- Body accumulation2MiB checked before extending the application buffer, not a cap on every server/network/OS buffer or a constant-memory guarantee.
- Upload single-flight; receive deadline10seconds. Busy response closes the connection. Provider time is not bounded by that receive deadline.
- Binary parser children AS256MiB/CPU5s/FSIZE1MiB/core0, wall10s and each pipe64KiB. Direct child cleanup, not a hostile-file/process-tree/OS-egress security boundary. Large parser output fails, never truncates successfully.
- PDF no OCR/layout guarantee. DOCX body paragraphs only, known unsupported structures rejected. XLSX rejects merges, uses row-level citations and inert formula text; initial workbook/sharedStrings/styles reads are not covered by worksheet byte meters.
- Serial retry finds existing same-source/profile before parsing/embedding. This avoids repeat provider calls for tested serial retries, not a distributed exactly-once/cost guarantee. Concurrent writers remain untested.
- Repository persists normalized float32 vectors; magnitudes and original vector bit patterns are not retained. It stores the caller's complete supplied chunk set, not proof of full document coverage.
- Local startup uses statement/lock/connect/pool timeouts but is not a production resource policy or migration system. Existing schema dimension must match; production embedding dimension is not inferred from dimension3 fixtures.

Actual integration evidence includes23HTTP/application tests, a separate non-test-startup upload/query run, and rendered desktop/mobile UI screenshots. Separate existing165pure/18querygraph/15full-source regressions pass. This does not establish live Gemini generation, semantic relevance, model-selected tools, production safety or hosted availability.
