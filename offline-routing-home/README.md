# Offline routing HOME and 768 namespace candidate

Prepared November 17, 2026. SOURCE/LOCAL review only. Not deployed, published to GitHub, wired into the app, or connected to a model/network service. Fabricated fake transport only. Generation HOLD, real-mail AI OFF, hosted operations OFF. The protected free cross-host route is the FIRST live gate and remains UNQUALIFIED. No Tailscale suitability, commercial terms, overlay support, identity persistence or public ingress is assumed here.

## Pinned HOME before cutover design

The proposed production HOME is an F-owned transactional routing-control table in the SAME PostgreSQL database/transaction boundary as F's document and vector namespaces. It is not an environment flag, browser/session value, A's model service or an eventually consistent external config store. A route is one tenant-bound, versioned tuple:

- verified-sub-derived local tenant scope;
- monotonically increasing routing epoch;
- namespace and schema generation;
- immutable model digest, embedding profile and dimension;
- extraction/chunk formatting contract, metric and index generation.

A database row points to an immutable namespace manifest. The tuple is read and checked in the same transaction as retrieval or mutation; a previously read tuple must still match in full. Version increments at every cutover AND rollback, so switching back never makes old work current again. Future network query embeddings must carry the captured route and fail if it changed before local retrieval. Do not separately flip repository/profile/index environment flags.

`routing_candidate.py` is the local analogue: a SQLite file in its own temporary directory, with foreign keys and FULL synchronous transactions. It accepts NO caller file path/DSN and removes its own temporary database at close. The reconnect test reads the saved HOME after closing/reopening the local connection. This is not PostgreSQL locking, fsync/power-loss, multi-process concurrency, hosted backup or pgvector index qualification.

## What is implemented locally

- Frozen `BoundRepository`, `Route` and `Manifest` values. The binding seam takes the upstream verified-sub value; it does not authenticate Google itself. The production integration must pass only the authenticated middleware value, never a client tenant selector. No global current tenant.
- Distinct synthetic3 and semantic768 logical namespaces with independent document/chunk/vector rows and complete manifest metadata. Every primary key, join and lookup includes tenant and namespace. Same fabricated bytes in two scopes stay separate. No tenant, document ID, filename or Google/session identity is sent to the fake exchange.
- Existing embedding `client_policy.py` reused byte-for-byte. Pinned profile `hermes-nomic-v1.5-768-512-v1`, pinned digest, raw text/query operation, batching, validation and no-retry policy are not rebuilt. The existing benchmark/eval is not rerun or modified. Tests inject the fabricated `FakeExchange` only; no service/client transport is supplied.
- Atomic local writes validate every vector and insert document plus chunk/vector rows in one transaction. Failure after a document or chunk insert rolls everything back.
- Writes must be frozen before staging. A BUILDING namespace captures the current tenant corpus fingerprint. All fake embedding batches finish and validate before any staging insert. The commit rechecks route, freeze, source fingerprint and state; then it stores the full staged corpus and transitions to READY in one transaction. A failed later batch or injected storage failure leaves the namespace BUILDING and empty.
- Cutover requires a READY target, writes frozen and exact source corpus equality. It changes old namespace ACTIVE to READY, target READY to ACTIVE and HOME epoch/namespace atomically. Injected failures at either state/routing step roll back the whole change. No partial routing tuple can be observed in this single-connection fixture.
- Reads return their route/profile metadata and use only the active namespace/dimension. Stale/foreign routes and vector3 queries on semantic768 fail rather than fall back. Ranking is an explicitly local exact cosine/dot scan over validated unit vectors. There is no ANN index implementation or new retrieval quality claim.
- Rollback uses the SAME versioned switch transaction. It preserves both namespace datasets, stops if writes are not frozen and refuses if the old namespace's corpus differs from the current one. A semantic-only postcutover write makes old-vector3 rollback refuse, not silently hide the new document. No automatic data deletion, reconciliation, backfill or legacy reassignment exists.

## State machine

1. Initial synthetic3 namespace ACTIVE, HOME epoch1, writes unfrozen.
2. Freeze writes against expected route. Create semantic768 BUILDING with source snapshot fingerprint.
3. Fake embedding preparation outside DB transaction. Revalidate snapshot and store all staged rows plus READY atomically.
4. Switch exact HOME tuple to READY target; old becomes READY, target ACTIVE, epoch increments. Writes remain frozen until an explicit local unfreeze.
5. If later writes are unfrozen, they are atomic in the new active namespace only. To roll back, freeze again and require exact corpus equality. A mismatch blocks until a separately reviewed reconciliation policy exists. No unsafe automatic fallback.

The candidate intentionally chooses a short write-freeze/snapshot design rather than pretending asynchronous dual writes are solved. There is no production freeze endpoint or automatic operator action. A startup/request must fail closed if HOME is absent or its manifest is invalid. Loss of HOME is not permission to guess a profile or select vector3 by default.

## Physical PostgreSQL follow-through, NOT implemented

The current app has hardcoded table names and a fixed vector3 column. Production semantic768 therefore needs a separately reviewed PostgreSQL schema/table namespace with vector(768), tenant constraints and a pinned index generation/metric; existing vector3 tables and the four protected hosted documents remain untouched. The local fixture uses namespace-qualified JSON vectors and shared relational table definitions for portability. This proves only the proposed logical namespace/state policy, not physical PG3/768 coexistence or query planner/RLS behavior. The production HOME pointer and namespace writes need real database locking/CAS and multi-connection failure tests before use.

Actual app wiring must also update the synthetic-only query guard and truthful response/privacy UI under review. Do not remove those guards now. Existing source provenance and tenant ownership are not inferred from a legacy shared document. No current hosted data is loaded or copied by this package.

## Remaining gates and exact limits

- No protected cross-host wrapper, ingress, credentials, VM install/config, real documents, model calls, provider activation or spend.
- Fake remaining-time handling is NOT a real network deadline, cancellation or quarantine test. Actual bounded DNS/TLS/read cancellation, ambiguous compute completion and no-retry transport remain later qualification against a reviewed protected route.
- This fixture models only fabricated source chunks and new document insertion. It is not a full extraction/original-file/lifecycle/deletion implementation, nor does it reconcile postcutover documents automatically.
- No real pgvector index, production schema migration, production durable HOME provisioning, multi-process races or whole corpus upload budget is qualified. SQLite transactions do not replace those checks.
- Existing same-host benchmark evidence remains descriptive and does not prove F cross-host latency/security. Known wrong-branch retrieval and absent calibrated score threshold remain unchanged.
- Auth execution-channel capability is unresolved; no FedCM source, Google login or accepted image/Google matrix rerun is part of this work.

## Review and reproduce

Run `python -m unittest -v` in this directory. All tests use fabricated fixtures and a temporary local DB. `TEST_RESULTS.txt` records the actual focused run. `BASELINE_SHA256.json` records the unchanged client identity; `MANIFEST_SHA256.json` inventories this delivery. The source ZIP is for focused review, not an approved app patch or deployment artifact.
