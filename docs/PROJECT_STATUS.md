# Architecture and verification

Status as of November 17, 2026. This page distinguishes implemented code, local evidence and unfinished hosted acceptance.

## Request path

```text
Browser: Google sign-in / sample workspace
  |
  v
GoogleDemoGate
  signed token + audience/issuer/expiry/email/sub/nonce checks
  opaque app session + Origin/CSRF + activation/rate limits
  |
  v
TenantDispatcher
  immutable repository scope from verified Google sub
  |
  +-- Upload -> bounded parser -> located chunks -> synthetic vectors
  |              -> atomic PostgreSQL document/chunk/vector store
  |
  +-- Query -> synthetic query vector -> registered retrieval tool
                 -> compiled LangGraph -> scoped pgvector retrieval
                 -> bounded passages + canonical source citations
```

Google mode does not accept the retained Basic credentials. Legacy shared records are excluded from Google workspaces; the legacy repository also excludes reserved tenant records. No legacy ownership is guessed or migrated. A database operator can still access records.

The current hosted factory rejects generated-answer enablement. Local optional answer composition validates a provider-neutral structured object and resolves known evidence references to original citation objects. Validation proves the shape and reference integrity, not factual entailment or coverage of every answer sentence.

## Why synthetic retrieval is explicit

Constant synthetic vectors make persistence, query dispatch, citation rendering and authorization testable without model calls. They do not measure meaning-based relevance. Similarity scores in this mode must not be presented as confidence or answer quality. Adding a model URL is insufficient: the current query service restricts profiles to synthetic ones, the database vector column has a fixed dimension and the tenant dispatcher does not construct an answer service.

A semantic provider needs separately reviewed document/query formatting, immutable model/profile identity, token limits, bounded transport and a dimension/re-index plan. Existing records must not be overwritten or assigned to users to make a new profile appear populated.

## Verification scope

- The source checkpoint behind this documentation passed a 47-test run that included a real disposable PostgreSQL 16.16 / pgvector 0.8.7 environment. This is a recorded run, not the expected count on every machine.
- Tests cover official Google verifier signature/audience/issuer/expiry negatives with an ephemeral test key, nonce/session/CSRF behavior, scoped repository/quota behavior, identical-file separation and legacy exclusion. Synthetic subjects and test keys are not real Google sign-ins.
- A local HTTPS browser harness exercised CSP, account display, sample upload, passage/citation display and sign-out using a test-double identity. Its workspace screenshot is labeled accordingly.
- Hosted checks established public health/login responses and negative authentication/Origin behavior. A current desktop/mobile capture confirms the public Google button renders. No real two-account hosted isolation acceptance is claimed.
- The container has an explicit final-image import/asset assertion after the final COPY. Its marker was observed in an actual build. Parser smoke/build history is preserved in [packaging/BUILD.md](../packaging/BUILD.md), with historical status distinguished from current deployment.

Ordinary pytest uses a socket/DNS guard during fixture execution, not before all module imports or at the OS boundary. Database tests are opt-in: `tests/ingestion/test_tenant_postgres.py` requires `RAG_TENANT_TEST_SOCKET`, database `rag_tenant_test` and private Unix-socket port 55439. That suite creates/drops its test tables. Use only a fresh disposable local database, never hosted or existing data. The default network guard must be handled deliberately for a private local database run; do not disable network safety globally or claim a skipped test passed.

## Private model work: separate from app readiness

A fixed-profile embedding pilot has been qualified privately on a separate compute host with fabricated text, including boundary rejection, sampled order/repeat checks and same-host client validation. This is not a usable connection from this app. No credential, private endpoint, machine address or operational script is published here.

Open gates include protected app-to-service transport, whole-ingestion request/time budget, actual repository integration, semantic profile/dimension migration, two-real-user hosted checks and privacy/activation review. Embeddings disclose every indexed text chunk to compute; answers disclose the question and selected evidence. The current privacy page says no model transfer and must be revised before such activation.

Generation is a different gate. An existing model produced two valid tiny schema-aware dummy outputs, but its input/output cap and measured latency did not qualify the full RAG answer workload. Earlier instruction-only trials failed exact validation. Neither a greeting, JSON mode nor a valid tiny object establishes grounded multi-passage answers, abstention, injection resistance or useful end-to-end latency.

## Next acceptance milestones

1. Complete real Google sessions and dummy two-user hosted isolation while retaining the data-operations gate until staged validation is authorized.
2. Review semantic profile, transport and ingestion budget before any model-backed repository change. No automatic paid fallback or live inference exposure.
3. Verify retrieval and evidence-answer quality independently, with citations, missing/conflicting evidence and bounded failure handling. Keep generated answers off until qualified.

## Screenshot provenance

| File | Capture scope |
| --- | --- |
| `hosted-login-desktop.png` | Public hosted page, 1440 x 1100 CSS viewport, November 17, 2026. No authenticated account. |
| `hosted-login-mobile.png` | Same public page, 390 x 1100 mobile viewport. No authenticated account. |
| `local-workspace-desktop.png` | Earlier local HTTPS browser test with fabricated sample and test-double identity. Not hosted proof. |

Screenshots were visually inspected for readable layout and for absence of real account identifiers, private documents, credentials and account-recovery screens. The illustration on the login page is labeled as an illustration.
