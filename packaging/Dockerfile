# Candidate source recipe, NOT built or approved for deployment.
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
COPY backend /app/backend
COPY packaging/container_smoke.py /app/packaging/container_smoke.py
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1 \
    RAG_PDF_PYTHON=/opt/venvs/pdf/bin/python \
    RAG_OFFICE_PYTHON=/opt/venvs/office/bin/python \
    ANSWER_GENERATION_ENABLED=false
USER 65532:65532
# Safe default performs an offline loopback smoke then exits.
# An approved hosting run would need a separate explicit command and secrets.
CMD ["/opt/venvs/app/bin/python", "/app/packaging/container_smoke.py"]
