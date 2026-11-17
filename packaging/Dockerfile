# Candidate recipe: Render builds succeeded; complete runtime smoke still pending.
# linux/amd64 manifests verified against registry-1.docker.io on 2026-11-17.
FROM --platform=linux/amd64 python:3.12.15-slim-bookworm@sha256:57d96f71de145a98e7ceca18ee4ade77bba4103a33a72dfaea026b23625c6bf0 AS app
COPY requirements.recovery.lock /locks/app.lock
RUN python -m venv /opt/venvs/app && /opt/venvs/app/bin/python -m pip install --no-cache-dir --require-hashes --no-deps --only-binary=:all: -r /locks/app.lock && /opt/venvs/app/bin/python -m pip check

FROM --platform=linux/amd64 python:3.10.12-slim-bookworm@sha256:13cc673c11ee90d6ba92d95f35f4d8e59148937f1e3b4044788e93268bfe9d2e AS pdf
# A venv alone is NOT a Python distribution. Preserve the full 3.10 prefix too.
RUN mkdir -p /opt/python310 && cp -a /usr/local/. /opt/python310/ \
    && cp -L /usr/lib/x86_64-linux-gnu/libexpat.so.1 /opt/python310/lib/libexpat.so.1
COPY packaging/requirements.pdf.lock /locks/pdf.lock
RUN LD_LIBRARY_PATH=/opt/python310/lib /opt/python310/bin/python3.10 -m venv --copies /opt/venvs/pdf && LD_LIBRARY_PATH=/opt/python310/lib /opt/venvs/pdf/bin/python3.10 -m pip install --no-cache-dir --require-hashes --no-deps --only-binary=:all: -r /locks/pdf.lock && LD_LIBRARY_PATH=/opt/python310/lib /opt/venvs/pdf/bin/python3.10 -m pip check
# Keep the loader path scoped to PDF, not global to app/Office.
RUN rm /opt/venvs/pdf/bin/python && printf '#!/bin/sh\nexport LD_LIBRARY_PATH=/opt/python310/lib\nexec /opt/venvs/pdf/bin/python3.10 "$@"\n' > /opt/venvs/pdf/bin/python && chmod 755 /opt/venvs/pdf/bin/python

FROM --platform=linux/amd64 python:3.12.15-slim-bookworm@sha256:57d96f71de145a98e7ceca18ee4ade77bba4103a33a72dfaea026b23625c6bf0 AS office
COPY packaging/requirements.office.lock /locks/office.lock
RUN python -m venv /opt/venvs/office && /opt/venvs/office/bin/python -m pip install --no-cache-dir --require-hashes --no-deps --only-binary=:all: -r /locks/office.lock && /opt/venvs/office/bin/python -m pip check

FROM --platform=linux/amd64 python:3.12.15-slim-bookworm@sha256:57d96f71de145a98e7ceca18ee4ade77bba4103a33a72dfaea026b23625c6bf0 AS runtime
COPY --from=app /opt/venvs/app /opt/venvs/app
COPY --from=pdf /opt/python310 /opt/python310
COPY --from=pdf /opt/venvs/pdf /opt/venvs/pdf
COPY --from=office /opt/venvs/office /opt/venvs/office
WORKDIR /app
# Explicit final-image boundary: no recursive source directory COPY.
# Any new application file needs review and a manifest update.
COPY backend/__init__.py /app/backend/__init__.py
COPY backend/ingestion/__init__.py /app/backend/ingestion/__init__.py
COPY backend/ingestion/answer_boundary.py /app/backend/ingestion/answer_boundary.py
COPY backend/ingestion/answer_config.py /app/backend/ingestion/answer_config.py
COPY backend/ingestion/bounded_process.py /app/backend/ingestion/bounded_process.py
COPY backend/ingestion/chunking.py /app/backend/ingestion/chunking.py
COPY backend/ingestion/contracts.py /app/backend/ingestion/contracts.py
COPY backend/ingestion/demo_auth.py /app/backend/ingestion/demo_auth.py
COPY backend/ingestion/document_management.py /app/backend/ingestion/document_management.py
COPY backend/ingestion/embeddings.py /app/backend/ingestion/embeddings.py
COPY backend/ingestion/evidence.py /app/backend/ingestion/evidence.py
COPY backend/ingestion/gemini_answer.py /app/backend/ingestion/gemini_answer.py
COPY backend/ingestion/google_auth.py /app/backend/ingestion/google_auth.py
COPY backend/ingestion/graph_executor.py /app/backend/ingestion/graph_executor.py
COPY backend/ingestion/hosted_demo.py /app/backend/ingestion/hosted_demo.py
COPY backend/ingestion/hosted_ui.html /app/backend/ingestion/hosted_ui.html
COPY backend/ingestion/ingestion_service.py /app/backend/ingestion/ingestion_service.py
COPY backend/ingestion/langgraph_adapter.py /app/backend/ingestion/langgraph_adapter.py
COPY backend/ingestion/local_startup.py /app/backend/ingestion/local_startup.py
COPY backend/ingestion/local_ui.html /app/backend/ingestion/local_ui.html
COPY backend/ingestion/located_search.py /app/backend/ingestion/located_search.py
COPY backend/ingestion/login_ui.html /app/backend/ingestion/login_ui.html
COPY backend/ingestion/office_adapter.py /app/backend/ingestion/office_adapter.py
COPY backend/ingestion/parser_child.py /app/backend/ingestion/parser_child.py
COPY backend/ingestion/pdf_adapter.py /app/backend/ingestion/pdf_adapter.py
COPY backend/ingestion/pdf_boundary.py /app/backend/ingestion/pdf_boundary.py
COPY backend/ingestion/persisted_answer.py /app/backend/ingestion/persisted_answer.py
COPY backend/ingestion/persisted_query.py /app/backend/ingestion/persisted_query.py
COPY backend/ingestion/plain_text.py /app/backend/ingestion/plain_text.py
COPY backend/ingestion/postgres_repository.py /app/backend/ingestion/postgres_repository.py
COPY backend/ingestion/privacy.html /app/backend/ingestion/privacy.html
COPY backend/ingestion/query_boundary.py /app/backend/ingestion/query_boundary.py
COPY backend/ingestion/retrieval.py /app/backend/ingestion/retrieval.py
COPY backend/ingestion/routing_graph.py /app/backend/ingestion/routing_graph.py
COPY backend/ingestion/segments.py /app/backend/ingestion/segments.py
COPY backend/ingestion/tenant_dispatch.py /app/backend/ingestion/tenant_dispatch.py
COPY backend/ingestion/upload_app.py /app/backend/ingestion/upload_app.py
COPY backend/ingestion/xlsx_inspected.py /app/backend/ingestion/xlsx_inspected.py
COPY backend/services/__init__.py /app/backend/services/__init__.py
COPY packaging/container_smoke.py /app/packaging/container_smoke.py
# Verify the ACTUAL final image, after Dockerignore filtering and final COPY.
RUN /opt/venvs/app/bin/python -B -c "from pathlib import Path; import backend.ingestion.google_auth, backend.ingestion.tenant_dispatch, backend.ingestion.hosted_demo, backend.ingestion.document_management; p=Path('/app/backend/ingestion'); assert all((p/x).is_file() and (p/x).stat().st_size for x in ('google_auth.py','tenant_dispatch.py','document_management.py','login_ui.html','hosted_ui.html','privacy.html')); print('FINAL_IMAGE_GOOGLE_MODULES_AND_ASSETS_OK')"
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1 \
    RAG_PDF_PYTHON=/opt/venvs/pdf/bin/python \
    RAG_OFFICE_PYTHON=/opt/venvs/office/bin/python \
    ANSWER_GENERATION_ENABLED=false
USER 65532:65532
# Safe default performs an offline loopback smoke then exits.
# An approved hosting run would need a separate explicit command and secrets.
CMD ["/opt/venvs/app/bin/python", "/app/packaging/container_smoke.py"]
