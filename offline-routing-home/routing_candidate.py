"""Offline routing/storage candidate. SQLite fixture only, no app/network imports.
HOME target: F database control table in same transactional boundary as corpus.
No claim of PostgreSQL/pgvector or authenticated identity qualification.
"""
from dataclasses import dataclass
import hashlib
import json
import math
import sqlite3
import tempfile
from pathlib import Path
from contextlib import contextmanager
from client_policy import PROFILE, DIGEST

SYNTHETIC = 'synthetic-hosted-demo-v1:dimension3'

class Refused(ValueError):
    pass

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)

def vector_ok(vector, dimension):
    if not isinstance(vector, (tuple, list)) or len(vector) != dimension:
        raise Refused('vector_dimension')
    if any(type(x) not in (int, float) or not math.isfinite(x) for x in vector):
        raise Refused('vector_finite')
    if not .999 <= math.hypot(*vector) <= 1.001:
        raise Refused('vector_norm')
    return canonical(list(vector))

@dataclass(frozen=True)
class Manifest:
    namespace: str
    profile: str
    model_digest: str
    dimension: int
    index_generation: str
    schema: str = 'offline-namespaces-v1'
    metric: str = 'cosine'
    extraction: str = 'fabricated-chunks-v1'
    formatting: str = 'raw-to-server-owned-prefix-v1'

    def validate(self):
        if not self.namespace or not self.index_generation or self.schema != 'offline-namespaces-v1' or self.metric != 'cosine':
            raise Refused('manifest')
        if self.extraction != 'fabricated-chunks-v1' or self.formatting != 'raw-to-server-owned-prefix-v1':
            raise Refused('manifest')
        if (self.profile, self.model_digest, self.dimension) not in ((SYNTHETIC, 'synthetic', 3), (PROFILE, DIGEST, 768)):
            raise Refused('profile')

@dataclass(frozen=True)
class Route:
    tenant: str
    epoch: int
    manifest: Manifest

@dataclass(frozen=True)
class BoundRepository:
    """Constructor seam receives verified sub from future gate, never browser input.
    This offline class does NOT verify Google identity itself.
    """
    home: object
    tenant: str

    def route(self):
        return self.home.route(self.tenant)

    def write(self, expected, document, chunks, vectors, checkpoint=None):
        return self.home.write(self.tenant, expected, document, chunks, vectors, checkpoint)

    def freeze(self, expected, frozen=True):
        return self.home.freeze(self.tenant, expected, frozen)

    def stage(self, manifest):
        return self.home.stage(self.tenant, manifest)

    def populate(self, namespace, client, checkpoint=None):
        return self.home.populate(self.tenant, namespace, client, checkpoint)

    def switch(self, expected, namespace, checkpoint=None):
        return self.home.switch(self.tenant, expected, namespace, checkpoint)

    def search(self, expected, query_vector):
        return self.home.search(self.tenant, expected, query_vector)

class Home:
    def __init__(self):
        # Own disposable directory only. No caller path/DSN/hosted DB option.
        self._directory = tempfile.TemporaryDirectory(prefix='rag-routing-fixture-')
        self._path = str(Path(self._directory.name) / 'home.sqlite3')
        self._connect()
        self.db.executescript('''
        CREATE TABLE namespaces(tenant TEXT, name TEXT, manifest TEXT NOT NULL,
          state TEXT NOT NULL CHECK(state IN ('BUILDING','READY','ACTIVE')),
          source_fingerprint TEXT NOT NULL,
          PRIMARY KEY(tenant,name));
        CREATE TABLE routes(tenant TEXT PRIMARY KEY, name TEXT NOT NULL,
          epoch INTEGER NOT NULL, frozen INTEGER NOT NULL CHECK(frozen IN (0,1)),
          FOREIGN KEY(tenant,name) REFERENCES namespaces(tenant,name));
        CREATE TABLE documents(tenant TEXT, namespace TEXT, id TEXT, fingerprint TEXT NOT NULL,
          PRIMARY KEY(tenant,namespace,id),
          FOREIGN KEY(tenant,namespace) REFERENCES namespaces(tenant,name));
        CREATE TABLE chunks(tenant TEXT, namespace TEXT, document TEXT, ordinal INTEGER,
          text TEXT NOT NULL, vector TEXT NOT NULL,
          PRIMARY KEY(tenant,namespace,document,ordinal),
          FOREIGN KEY(tenant,namespace,document) REFERENCES documents(tenant,namespace,id) ON DELETE CASCADE);
        ''')

    @contextmanager
    def tx(self):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            yield
            self.db.execute('COMMIT')
        except BaseException:
            self.db.execute('ROLLBACK')
            raise

    def _connect(self):
        self.db = sqlite3.connect(self._path, isolation_level=None)
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.execute('PRAGMA synchronous=FULL')

    def reopen_local_fixture(self):
        """Simulated process reconnect to our own local file, not crash/PG proof."""
        self.db.close()
        self._connect()

    def close(self):
        self.db.close()
        self._directory.cleanup()

    def bind(self, verified_sub):
        if type(verified_sub) is not str or not verified_sub or len(verified_sub)>255:
            raise Refused('verified_scope_required')
        # Domain separated local identifier, never sent to exchange.
        return BoundRepository(self, hashlib.sha256(('google:'+verified_sub).encode()).hexdigest())

    def initialize(self, bound, manifest):
        manifest.validate()
        if manifest.dimension != 3:
            raise Refused('initial_synthetic_required')
        with self.tx():
            self.db.execute('INSERT INTO namespaces VALUES(?,?,?,?,?)',
                (bound.tenant,manifest.namespace,canonical(manifest.__dict__),'ACTIVE',''))
            self.db.execute('INSERT INTO routes VALUES(?,?,?,?)', (bound.tenant,manifest.namespace,1,0))

    def _route(self, tenant):
        row = self.db.execute('SELECT r.epoch,r.name,n.manifest,n.state,n.name FROM routes r LEFT JOIN namespaces n ON n.tenant=r.tenant AND n.name=r.name WHERE r.tenant=?', (tenant,)).fetchone()
        if not row:
            raise Refused('scope_missing')
        epoch, route_name, raw_manifest, state, row_name = row
        if type(epoch) is not int or epoch <= 0:
            raise Refused('invalid_home_epoch')
        if type(route_name) is not str or not route_name or row_name != route_name or state != 'ACTIVE':
            raise Refused('invalid_home_namespace_state')
        try:
            manifest = Manifest(**json.loads(raw_manifest))
            manifest.validate()
        except (TypeError, ValueError):
            raise Refused('invalid_home_manifest') from None
        if manifest.namespace != row_name:
            raise Refused('invalid_home_manifest_namespace')
        return Route(tenant, epoch, manifest)

    def route(self, tenant):
        with self.tx():
            return self._route(tenant)

    def _check(self, tenant, expected):
        actual = self._route(tenant)
        if expected != actual or expected.tenant != tenant:
            raise Refused('stale_or_foreign_route')
        return actual

    def _fingerprint(self, tenant, namespace):
        rows = self.db.execute('SELECT id,fingerprint FROM documents WHERE tenant=? AND namespace=? ORDER BY id', (tenant,namespace)).fetchall()
        return hashlib.sha256(canonical(rows).encode()).hexdigest()

    def freeze(self, tenant, expected, frozen):
        if type(frozen) is not bool:
            raise Refused('freeze_boolean')
        with self.tx():
            self._check(tenant, expected)
            self.db.execute('UPDATE routes SET frozen=? WHERE tenant=?', (int(frozen), tenant))

    def _insert(self, tenant, namespace, document, chunks, vectors, dimension, checkpoint):
        if type(document) is not str or not document or type(chunks) is not list or not chunks or len(chunks)>128:
            raise Refused('document')
        if any(type(x) is not str or not x.strip() for x in chunks) or len(vectors)!=len(chunks):
            raise Refused('chunk_count')
        encoded = [vector_ok(v,dimension) for v in vectors]
        fingerprint = hashlib.sha256(canonical(chunks).encode()).hexdigest()
        self.db.execute('INSERT INTO documents VALUES(?,?,?,?)', (tenant,namespace,document,fingerprint))
        if checkpoint: checkpoint('document')
        for i,(text,vector) in enumerate(zip(chunks,encoded)):
            self.db.execute('INSERT INTO chunks VALUES(?,?,?,?,?,?)', (tenant,namespace,document,i,text,vector))
            if checkpoint: checkpoint('chunk_vector')

    def write(self, tenant, expected, document, chunks, vectors, checkpoint):
        with self.tx():
            route = self._check(tenant, expected)
            if self.db.execute('SELECT frozen FROM routes WHERE tenant=?', (tenant,)).fetchone()[0]:
                raise Refused('writes_frozen')
            self._insert(tenant,route.manifest.namespace,document,chunks,vectors,route.manifest.dimension,checkpoint)

    def stage(self, tenant, manifest):
        manifest.validate()
        if manifest.dimension != 768:
            raise Refused('semantic_stage_required')
        with self.tx():
            route = self._route(tenant)
            if not self.db.execute('SELECT frozen FROM routes WHERE tenant=?', (tenant,)).fetchone()[0]:
                raise Refused('freeze_before_snapshot')
            fingerprint = self._fingerprint(tenant,route.manifest.namespace)
            self.db.execute('INSERT INTO namespaces VALUES(?,?,?,?,?)',
                (tenant,manifest.namespace,canonical(manifest.__dict__),'BUILDING',fingerprint))

    def populate(self, tenant, namespace, client, checkpoint):
        # Read snapshot atomically, exchange outside transaction. Freeze is checked
        # again before commit and source fingerprint is compared, never assumed.
        with self.tx():
            route = self._route(tenant)
            row = self.db.execute('SELECT manifest,state,source_fingerprint FROM namespaces WHERE tenant=? AND name=?', (tenant,namespace)).fetchone()
            if not row or row[1] != 'BUILDING':
                raise Refused('not_building')
            manifest = Manifest(**json.loads(row[0])); manifest.validate()
            snapshot = row[2]
            source = self.db.execute('SELECT d.id,c.text FROM documents d JOIN chunks c ON c.tenant=d.tenant AND c.namespace=d.namespace AND c.document=d.id WHERE d.tenant=? AND d.namespace=? ORDER BY d.id,c.ordinal', (tenant,route.manifest.namespace)).fetchall()
        # Fabricated fake transport passed by local tests only. No production adapter.
        texts = [text for _,text in source]
        if not texts:
            raise Refused('empty_fixture_snapshot')
        vectors = client.embed('documents', texts)
        groups = {}
        for (doc,text),vector in zip(source,vectors):
            groups.setdefault(doc, ([],[]))[0].append(text)
            groups[doc][1].append(vector)
        if len(vectors)!=len(source):
            raise Refused('embedding_count')
        with self.tx():
            current = self._check(tenant,route)
            if not self.db.execute('SELECT frozen FROM routes WHERE tenant=?',(tenant,)).fetchone()[0]:
                raise Refused('writes_not_frozen')
            if self._fingerprint(tenant,current.manifest.namespace)!=snapshot:
                raise Refused('source_changed')
            state = self.db.execute('SELECT state FROM namespaces WHERE tenant=? AND name=?',(tenant,namespace)).fetchone()
            if not state or state[0]!='BUILDING':
                raise Refused('not_building')
            for doc,(parts,vecs) in groups.items():
                self._insert(tenant,namespace,doc,parts,vecs,manifest.dimension,checkpoint)
            if self._fingerprint(tenant,namespace)!=snapshot:
                raise Refused('coverage')
            if checkpoint: checkpoint('before_ready')
            self.db.execute('UPDATE namespaces SET state=? WHERE tenant=? AND name=?', ('READY',tenant,namespace))

    def switch(self, tenant, expected, namespace, checkpoint):
        # Same operation handles cutover and rollback, only while writes are frozen.
        with self.tx():
            current=self._check(tenant,expected)
            if not self.db.execute('SELECT frozen FROM routes WHERE tenant=?',(tenant,)).fetchone()[0]:
                raise Refused('writes_not_frozen')
            target=self.db.execute('SELECT manifest,state FROM namespaces WHERE tenant=? AND name=?',(tenant,namespace)).fetchone()
            if not target or target[1]!='READY':
                raise Refused('target_not_ready')
            manifest=Manifest(**json.loads(target[0]));manifest.validate()
            if self._fingerprint(tenant,namespace)!=self._fingerprint(tenant,current.manifest.namespace):
                raise Refused('rollback_or_cutover_corpus_mismatch')
            self.db.execute('UPDATE namespaces SET state=? WHERE tenant=? AND name=?',('READY',tenant,current.manifest.namespace))
            if checkpoint: checkpoint('old_inactive')
            self.db.execute('UPDATE namespaces SET state=? WHERE tenant=? AND name=?',('ACTIVE',tenant,namespace))
            self.db.execute('UPDATE routes SET name=?,epoch=epoch+1 WHERE tenant=? AND epoch=?',(namespace,tenant,expected.epoch))
            if checkpoint: checkpoint('route_updated')
            return self._route(tenant)

    def search(self, tenant, expected, query_vector):
        with self.tx():
            route=self._check(tenant,expected)
            vector_ok(query_vector,route.manifest.dimension)
            rows=self.db.execute('SELECT document,ordinal,text,vector FROM chunks WHERE tenant=? AND namespace=? ORDER BY document,ordinal',(tenant,route.manifest.namespace)).fetchall()
            scored=[(sum(a*b for a,b in zip(query_vector,json.loads(v))),d,i,t) for d,i,t,v in rows]
            return {'route':route,'hits':sorted(scored,reverse=True)}
