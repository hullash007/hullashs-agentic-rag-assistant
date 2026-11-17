# Portable packaging candidate

Status: SOURCE PREPARATION ONLY. No image built. No deployment or free-host fit claim.
Keep these files local for review. The reviewed source checkpoint predates them.

## Build inputs

Target platform is linux/amd64. Registry manifest lookups on 2026-11-17 confirmed:

- App/Office/final: python:3.12.15-slim-bookworm, amd64 manifest sha256:57d96f71de145a98e7ceca18ee4ade77bba4103a33a72dfaea026b23625c6bf0.
- PDF: python:3.10.12-slim-bookworm, amd64 manifest sha256:13cc673c11ee90d6ba92d95f35f4d8e59148937f1e3b4044788e93268bfe9d2e.

Official registry source: https://registry-1.docker.io/v2/library/python/manifests/3.12.15-slim-bookworm and https://registry-1.docker.io/v2/library/python/manifests/3.10.12-slim-bookworm . These are registry API endpoints, not human-facing documentation.

Locks, unchanged from the reviewed development checkpoint:

- requirements.recovery.lock: 8c5898c4969df3a18d89d1a638620c910b8f5c5c0713b68b2441e8ea6df87d47
- packaging/requirements.pdf.lock: 732184338488c222a0fd9aaaedef151cac43ba0b03d2cf12dfcd85d6b20e250e
- packaging/requirements.office.lock: 120adda104ca96024586bcfd6199b8bd987924af5ee37b867933a3cdbdde1688

Install uses only hash-checked locked binary distributions, no dependency resolution or OS package installation. Bootstrap pip comes from each immutable base image. No uv/lock generator/compiler is added. This pins major inputs, not bit-for-bit image output or vulnerability status. Old exact Python patch versions have not been security-scanned; do not infer a current security-support promise.

App and Office share the same complete Python3.12.15 base but separate virtual environments. PDF needs a real second interpreter: copy the complete Python3.10.12 prefix, not merely a venv pointing back at the wrong /usr/local. A PDF-only launcher supplies its libpython loader path. Parser children still use the existing explicit environment settings and minimal child environment.

All stages use Debian bookworm/amd64. This is necessary but NOT sufficient proof of shared-library compatibility across base image dates. The source environments' ELF NEEDED inspection identified libc/libm/libpthread/librt and app wheel dependencies including bundled psycopg libraries, libgcc_s, libz and the dynamic loader; PDF packages are pure Python. It did not establish the final image's complete interpreter extension, ABI, loader or CA bundle compatibility. Actual final-image imports and parser smoke must pass before treating this recipe as buildable. No guessed apt workaround is included.

## Commands for a permitted local builder

From repository root:

```sh
docker build --platform=linux/amd64 -f packaging/Dockerfile -t rag-packaging-candidate:local .
sh packaging/smoke_image.sh rag-packaging-candidate:local
```

Neither command was executed: Docker, Podman and Buildah executables and Docker/Podman sockets are absent. No hosted builder, CI run or account creation was substituted.

The wrapper accepts only a prebuilt local image, disables network, publishes no ports, mounts no host files or credentials, uses a read-only filesystem plus a bounded temporary directory, drops capabilities, and caps memory at512MB for a candidate smoke. Even a successful smoke under that cap would not prove loaded/concurrent free-host fit. Build output itself still needs size/library inspection and scanning.

Default image command performs the offline smoke and exits. It does NOT start the hosted 0.0.0.0 entrypoint. Hosting requires separate approval and command/configuration; no production secret or real database is present in this recipe. The fake URL used by the smoke points at loopback port1 and engine-connect is forbidden by a tripwire.

## Checks actually performed

The portable Python smoke ran against the existing local source environments with explicit source-only path overrides, not inside an image. Their venvs lack pip, so a source-only uv check override checked63/2/6 compatible packages. The normal image path requires pip check in each venv. No package changed.

Actual result: exact Python3.12.15/3.10.12/3.12.15; parser package isolation; generated synthetic blank PDF, one-paragraph DOCX and one-cell XLSX; all3actual parser children passed and were reaped; loopback protected hosted factory returned constant health200 and five unauthenticated401 responses; model-constructor/DB-connect tripwires untouched; no provider-key settings lookup; server process group reaped and listener refused after stop. This does not test authenticated database or query execution. Source smoke output explicitly records image_default_paths=false.

Python syntax compilation and shell sh -n passed. No Dockerfile parser/linter is installed, so Dockerfile syntax has only source review, not parser/build verification. The smoke suppresses SyntaxWarning in its server child because SDK3.3.0 contains invalid docstring escapes; other warnings/errors remain visible. Uvicorn shutdown may exit0orSIGTERM(-15); both are explicitly accepted after wait/listener checks, not a claim of application-level graceful shutdown.

The synthetic fixtures are created in a temporary directory and removed; none are bundled as user documents. The final image source copy excludes Git history, local evidence, secrets, uploads and venvs through an allowlist .dockerignore. Verify the actual built image, not just the ignore file.

## Remaining boundaries

No actual image, free-plan/account/billing verification, real TLS/reverse proxy, hosted schema/retention, deployed auth negatives, live model answer, semantic retrieval or production identity/isolation is established. Invalid authentication remains unthrottled. Do not deploy or call a provider from this packaging task. After source review, actual artifact validation needs a permitted builder rather than another fixture matrix.
