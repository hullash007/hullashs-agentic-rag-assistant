# Portable packaging candidate

Historical build record: actual Render final-image offline smoke PASSED on 2026-11-17 at checkpoint 648b7f4. That smoke was not a running hosted app or loaded free-host fit proof. A later Google sign-in preview is now deployed with document operations disabled; see [current hosted status](../HOSTED_PREPARATION.md). The chronology below describes earlier checkpoints, not today's deployment state.

## Actual build chronology

- Checkpoint 5fe161c: three build-stage dependency checks and image export succeeded. Final-image runtime failed at the PDF pip check because pyexpat could not load libexpat.so.1. Parser and HTTP checks did not complete.
- Reviewed checkpoint ce6d923: copied libexpat.so.1 from the same immutable PDF base into the private PDF prefix, with the existing PDF-only loader scope. Render built and exported it successfully. All three final-image dependency checks passed. Execution reached the HTTP health block after the parser loop, but there were no per-parser phase logs. The health request failed with ConnectionRefusedError at the 15-second readiness deadline and the smoke exited 1. The server child's captured logs were not emitted on that exception, so its underlying startup cause is unknown. Do not infer RAM exhaustion or a missing library.
- Reviewed diagnostic checkpoint 648b7f4: actual Render image build/export and full credential-free final-image smoke passed, image_default_paths=true. Exact interpreter versions/three dependency checks; explicit PDF/DOCX/XLSX parser success markers (exit0/reaped); loopback health200 after18.427s readiness wait; five unauthorized401 routes; DB/model tripwires untouched; server reaped and listener closed. This concrete run exceeded the former15s readiness deadline, but does not establish the earlier run's root cause.
- Render marked this third deployment failed with "Application exited early" because the safe default smoke command exits. That platform status is expected for an offline smoke and is not a public-service readiness test. Real DB/auth settings and hosted startup remain absent.
- The diagnostic source includes elapsed pre/post phase logs and bounded (64KiB emitted) child-log output on failure after cleanup, preserving the original failure. Capture uses a temporary file, not a disk quota. This log output is safe only for the fixed credential-free smoke environment, never as generic logging for a real application.

This chronology records a strictly free, no-payment-method, login-protected deployment experiment. It does not authorize new deployments, spending, account access or source merges.

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

All stages use Debian bookworm/amd64. This is necessary but NOT sufficient proof of shared-library compatibility across base image dates. The source environments' ELF NEEDED inspection identified libc/libm/libpthread/librt and app wheel dependencies including bundled psycopg libraries, libgcc_s, libz and the dynamic loader; PDF packages are pure Python. It did not establish the final image's complete interpreter extension, ABI, loader or CA bundle compatibility. Actual final-image imports and complete parser/HTTP smoke must pass before treating this recipe as runtime-validated. No guessed apt workaround is included.

## Commands for a permitted local builder

From repository root:

```sh
docker build --platform=linux/amd64 -f packaging/Dockerfile -t rag-packaging-candidate:local .
sh packaging/smoke_image.sh rag-packaging-candidate:local
```

Neither local command was executed. The bounded local-builder route was stopped without changing host isolation. The separately approved Render builder executed the three image builds recorded above.

The wrapper accepts only a prebuilt local image, disables network, publishes no ports, mounts no host files or credentials, uses a read-only filesystem plus a bounded temporary directory, drops capabilities, and caps memory at512MB for a candidate smoke. Even a successful smoke under that cap would not prove loaded/concurrent free-host fit. Build output itself still needs size/library inspection and scanning.

Default image command performs the offline smoke and exits. It does NOT start the hosted 0.0.0.0 entrypoint. Hosting requires separate approval and command/configuration; no production secret or real database is present in this recipe. The fake URL used by the smoke points at loopback port1 and engine-connect is forbidden by a tripwire.

## Checks actually performed

The portable Python smoke ran against the existing local source environments with explicit source-only path overrides, not inside an image. Their venvs lack pip, so a source-only uv check override checked63/2/6 compatible packages. The normal image path requires pip check in each venv. No package changed.

Actual result: exact Python3.12.15/3.10.12/3.12.15; parser package isolation; generated synthetic blank PDF, one-paragraph DOCX and one-cell XLSX; all3actual parser children passed and were reaped; loopback protected hosted factory returned constant health200 and five unauthenticated401 responses; model-constructor/DB-connect tripwires untouched; no provider-key settings lookup; server process group reaped and listener refused after stop. This does not test authenticated database or query execution. Source smoke output explicitly records image_default_paths=false.

Python syntax compilation and shell sh -n passed. No local Dockerfile parser/linter is installed. Actual Render builds verified the executed Dockerfile revisions; the executed diagnostic revision built and passed the offline smoke recorded above. The smoke suppresses SyntaxWarning in its server child because SDK3.3.0 contains invalid docstring escapes; other warnings/errors remain visible. Uvicorn shutdown may exit0orSIGTERM(-15); both are explicitly accepted after wait/listener checks, not a claim of application-level graceful shutdown.

The synthetic fixtures are created in a temporary directory and removed; none are bundled as user documents. The final image source copy excludes Git history, local evidence, secrets, uploads and venvs through an allowlist .dockerignore. Verify the actual built image, not just the ignore file.

## Remaining boundaries

Render Free/Hobby with no card and a separate Neon Free project were verified during the approved attempt. The isolated synthetic-dimension schema was created with pgvector and three repository tables, with no document data. These checks do not establish authenticated external psycopg TLS, real reverse-proxy behavior, retention/deletion follow-through, deployed auth negatives, authenticated DB-backed runtime, loaded free-host fit, live model answers, semantic retrieval or production identity/isolation. Invalid authentication remains unthrottled. Actual image context/layers, size/libraries and vulnerability status have not been independently inspected. No model call or wider sharing is authorized by these packaging notes.
