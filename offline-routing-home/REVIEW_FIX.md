# Focused HOME review correction

Acceptance remains subject to the same review. This package replaces the earlier local candidate, not an app/deployment artifact.

The authoritative HOME read now selects route name, actual namespace row name and state using LEFT JOIN. It refuses missing namespace rows, any state other than ACTIVE, manifest.namespace unequal to the actual row name, and epochs whose persisted SQLite value is not a strict positive Python integer. Malformed or invalid manifests are mapped to a typed refusal. Read/search cannot silently use an absent namespace or a BUILDING/READY target.

Four new focused tests passed in 0.026s. See REVIEW_FIX_RESULTS.txt. They cover BUILDING/READY rejection, manifest namespace mismatch including a constructed search tuple, zero/negative/noninteger persisted epochs, and a missing referenced namespace row created only by explicit FK bypass in this disposable fixture. SQLite INTEGER affinity can normalize some inserted numeric strings/bools to integers; the check is on the authoritative persisted value, not its pre-storage Python input type. Production PostgreSQL schema/type and corruption handling remain separate review work.

Only routing_candidate.py and test_routing_candidate.py changed in executable source. REVIEW_FIX.patch is the exact delta from prior ZIP SHA256 7873375d1555eea6325afb7699f58b125b66f8be314d8576a92d7ad7c3b70f60. py_compile passed. The original TEST_RESULTS.txt records the earlier 25-test run, not a rerun of the revised 29-test file; only the four focused new tests ran for this correction, as requested. No broad fake matrix expansion or rerun.

client_policy.py remains identical to this agent's prior local baseline and package hash. The independent reviewer established internal artifact hash consistency only, not an independent historical acceptance/provenance chain. Do not treat the copied file or this note as proof of external approval. Existing review evidence and authority remain with the originating coordination.

No hosted app/DB, model/network transport, credentials, provider, VM ingress, schema deployment, source publication, Google/FedCM work or protected source records were accessed or changed. Protected free route remains first live gate and UNQUALIFIED. Auth capability unresolved, candidate38a377b OFF. Future local PostgreSQL/two-connection work needs separate reviewed schema prep and is not launched by this correction.
