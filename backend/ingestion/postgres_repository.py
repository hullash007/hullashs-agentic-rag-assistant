"""Opt-in PostgreSQL document repository. No provider calls or default-path changes."""
from dataclasses import asdict, dataclass
import hashlib
import json
from sqlalchemy import (MetaData, Table, Column, Text, Integer, LargeBinary,
                        ForeignKey, UniqueConstraint, JSON, select, insert, func, text)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql.functions import Function
from sqlalchemy.sql.elements import quoted_name
from .vector_binary import VectorSendBinding, decode_vector_binary
from pgvector.sqlalchemy import VECTOR
from .contracts import SourceDocument, CitationRef, DocumentChunk
from .segments import ExtractedDocument, ExtractedSegment, SegmentLocator, LocatedChunk
from .located_search import LocatedHit
from .retrieval import _unit
from .recovery_equivalence import (Equivalence, RECOVERY_CHUNK_CAP, compare_recovery_rows)

SERIALIZATION = 'extracted-segments-v1'


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')


def digest(value):
    return hashlib.sha256(value).hexdigest()


def extracted_payload(document):
    return {'version': SERIALIZATION, 'format': document.format,
            'segments': [asdict(s) for s in document.segments]}


def decode_document(source, payload):
    if payload['version'] != SERIALIZATION:
        raise ValueError('unknown extracted serialization')
    return ExtractedDocument(SourceDocument(**source), payload['format'], tuple(
        ExtractedSegment(s['segment_index'], s['text'], SegmentLocator(**s['locator']))
        for s in payload['segments']))


@dataclass(frozen=True)
class StoredDocument:
    document_id: str
    document: ExtractedDocument
    original_bytes: bytes
    extracted_sha256: str
    extraction_profile: str
    embedding_profile: str
    located_chunks: tuple
    vectors: tuple
    already_present: bool = False


class DocumentConflict(ValueError):
    pass


class DocumentQuota(ValueError):
    pass


class DocumentCommitUnknown(RuntimeError):
    """Body finished, but transaction exit did not acknowledge completion.

    This is not proof of rollback or persistence. Never automatically retry.
    An existing-document read-only path does not attempt a new write.
    """
    retry_allowed = False

    def __init__(self, *, already_present=False):
        super().__init__('document transaction outcome unconfirmed')
        self.commit_state = 'not_attempted' if already_present else 'unknown'


class DocumentReadbackUnavailable(RuntimeError):
    """Normal transaction exit, but no usable result; never report upload success.

    Acknowledged commit is not independent database durability qualification.
    Readback can fail due to integrity validation, not only availability.
    """
    retry_allowed = False

    def __init__(self, *, already_present=False):
        super().__init__('document result unavailable after transaction')
        self.commit_state = 'not_attempted' if already_present else 'acknowledged'


@dataclass(frozen=True)
class IdentityConstraintBinding:
    """Explicit verified DB identities, never inferred conventional PG names.

    None at the repository disables uniqueness recovery. This metadata gate does
    not qualify persisted-vector equivalence or prove a database race/rollback.
    """
    schema: str
    table: str
    constraints: tuple

    def __post_init__(self):
        if (not isinstance(self.schema, str) or not self.schema.strip() or
            self.table != 'rag_documents' or type(self.constraints) is not tuple or
            not self.constraints or
            any(not isinstance(c, str) or not c.strip() for c in self.constraints) or
            len(set(self.constraints)) != len(self.constraints)):
            raise ValueError('explicit schema/table/identity-constraint binding required')

    def permits(self, error, *, stage):
        if stage != 'document_insert' or not isinstance(error, IntegrityError):
            return False
        original = error.orig
        diagnostic = getattr(original, 'diag', None)
        return (getattr(original, 'sqlstate', None) == '23505' and
                getattr(diagnostic, 'schema_name', None) == self.schema and
                getattr(diagnostic, 'table_name', None) == self.table and
                getattr(diagnostic, 'constraint_name', None) in self.constraints)


class PostgresDocumentRepository:
    def __init__(self, engine, *, dimension, embedding_profile, tenant_subject=None,
                 identity_constraint_binding=None, vector_send_binding=None):
        if type(dimension) is not int or not 1 <= dimension <= 16000:
            raise ValueError('explicit fixed vector dimension required')
        if not isinstance(embedding_profile, str) or not embedding_profile.strip():
            raise ValueError('explicit embedding profile required')
        if engine.dialect.name != 'postgresql':
            raise ValueError('PostgreSQL required')
        if tenant_subject is not None and (not isinstance(tenant_subject,str) or not tenant_subject or len(tenant_subject)>255):
            raise ValueError('verified tenant subject required')
        if identity_constraint_binding is not None and not isinstance(identity_constraint_binding, IdentityConstraintBinding):
            raise ValueError('explicit identity constraint binding required')
        if vector_send_binding is not None and not isinstance(vector_send_binding, VectorSendBinding):
            raise ValueError('explicit verified vector send binding required')
        self.vector_send_binding = vector_send_binding
        self.identity_constraint_binding = identity_constraint_binding
        self.source_prefix=('tenant-v1:'+digest(canonical(['google',tenant_subject]))+':') if tenant_subject is not None else ''
        self.engine, self.dimension = engine, dimension
        self.embedding_profile = embedding_profile
        self.metadata = MetaData()
        self.documents = Table('rag_documents', self.metadata,
            Column('document_id', Text, primary_key=True),
            Column('source_id', Text, nullable=False, unique=True),
            Column('source', JSON, nullable=False),
            Column('original_bytes', LargeBinary, nullable=False),
            Column('extracted', JSON, nullable=False),
            Column('extracted_sha256', Text, nullable=False),
            Column('serialization', Text, nullable=False),
            Column('extraction_profile', Text, nullable=False),
            Column('embedding_profile', Text, nullable=False),
            Column('fingerprint', Text, nullable=False),
            Column('chunk_count', Integer, nullable=False))
        self.chunks = Table('rag_located_chunks', self.metadata,
            Column('located_id', Text, primary_key=True),
            Column('document_id', Text, ForeignKey('rag_documents.document_id', ondelete='CASCADE'), nullable=False),
            Column('ordinal', Integer, nullable=False),
            Column('original_chunk_id', Text, nullable=False),
            Column('segment_index', Integer, nullable=False),
            Column('text', Text, nullable=False),
            Column('start', Integer, nullable=False),
            Column('end', Integer, nullable=False),
            Column('locator', JSON, nullable=False),
            UniqueConstraint('document_id', 'ordinal'))
        self.embeddings = Table('rag_chunk_embeddings', self.metadata,
            Column('located_id', Text, ForeignKey('rag_located_chunks.located_id', ondelete='CASCADE'), primary_key=True),
            Column('vector', VECTOR(dimension), nullable=False),
            Column('profile', Text, nullable=False),
            Column('created_at', Text, nullable=False, server_default=func.current_timestamp()))

    def source_id_for_sha(self, sha):
        if not isinstance(sha,str) or len(sha)!=64 or any(c not in '0123456789abcdef' for c in sha):
            raise ValueError('valid content hash required')
        return self.source_prefix+'sha256:'+sha

    def _scope(self):
        # Empty-prefix legacy scope must never include any present/future tenant records.
        if not self.source_prefix:
            return ~self.documents.c.source_id.startswith('tenant-',autoescape=True)
        return self.documents.c.source_id.startswith(self.source_prefix,autoescape=True)

    def _check_source_scope(self, source_id):
        if not isinstance(source_id,str):raise ValueError('source identity required')
        if self.source_prefix:
            if not source_id.startswith(self.source_prefix+'sha256:'):
                raise ValueError('source belongs to a different tenant')
        elif source_id.startswith('tenant-'):
            raise ValueError('tenant records are not accessible in legacy mode')

    def create_schema(self):
        # Extension creation belongs to disposable-database setup, not this service.
        self.metadata.create_all(self.engine)
        with self.engine.connect() as connection:
            actual = connection.execute(text("SELECT format_type(atttypid, atttypmod) FROM pg_attribute WHERE attrelid = 'rag_chunk_embeddings'::regclass AND attname = 'vector' AND NOT attisdropped")).scalar_one()
        if actual != f'vector({self.dimension})':
            raise ValueError('database vector dimension differs from configured dimension')

    def _prepare(self, document, original_bytes, located_chunks, vectors, extraction_profile, embedding_profile, *, _require_profile=True):
        if not isinstance(document, ExtractedDocument) or not isinstance(original_bytes, bytes):
            raise ValueError('ExtractedDocument and original bytes required')
        if digest(original_bytes) != document.source.sha256:
            raise ValueError('original bytes SHA mismatch')
        if not isinstance(extraction_profile, str) or not extraction_profile.strip():
            raise ValueError('explicit extraction profile required')
        if not isinstance(embedding_profile, str) or not embedding_profile.strip():
            raise ValueError('explicit embedding profile required')
        if _require_profile and embedding_profile != self.embedding_profile:
            raise ValueError('embedding profile does not match repository')
        chunks, vectors = tuple(located_chunks), tuple(vectors)
        if len(chunks) != len(vectors):
            raise ValueError('one vector per located chunk required')
        seen, previous = set(), None
        for c in chunks:
            if not isinstance(c, LocatedChunk) or type(c.segment_index) is not int or not 0 <= c.segment_index < len(document.segments):
                raise ValueError('invalid located chunk')
            segment = document.segments[c.segment_index]
            citation = c.chunk.citation
            # Reconstructing validates every locator field, even frozen objects tampered with elsewhere.
            SegmentLocator(**asdict(c.locator))
            if citation.source != document.source or c.locator != segment.locator:
                raise ValueError('chunk source/locator mismatch')
            if citation.end > len(segment.text) or segment.text[citation.start:citation.end] != c.chunk.text:
                raise ValueError('chunk range/content mismatch')
            identity = canonical(['located-v1', citation.chunk_id, c.segment_index, asdict(c.locator)])
            if c.located_id != digest(identity) or c.located_id in seen:
                raise ValueError('located identity mismatch/duplicate')
            position = (c.segment_index, citation.start)
            if previous is not None and position <= previous:
                raise ValueError('chunks must be in segment/offset order')
            previous = position
            seen.add(c.located_id)
        units = tuple(_unit(v, self.dimension) for v in vectors)
        payload = extracted_payload(document)
        source = asdict(document.source)
        fingerprint = digest(canonical([source, payload, extraction_profile, embedding_profile,
                                         [asdict(c) for c in chunks], units]))
        return chunks, units, payload, fingerprint

    def store_document(self, document, original_bytes, located_chunks, vectors, *,
                       extraction_profile, embedding_profile, _checkpoint=None):
        self._check_source_scope(document.source.source_id)
        chunks, units, payload, fingerprint = self._prepare(document, original_bytes, located_chunks, vectors,
                                                           extraction_profile, embedding_profile)
        document_id = digest(canonical(['document-v1', document.source.source_id]))
        already = False
        document_insert_error = None
        body_completed = False
        try:
            with self.engine.begin() as connection:
                if self.source_prefix:
                    # Serialize scoped quota checks and insert in one transaction.
                    connection.execute(text('SELECT pg_advisory_xact_lock(732514611)'))
                old = connection.execute(select(self.documents.c.fingerprint).where(
                    self.documents.c.document_id == document_id, self._scope())).scalar_one_or_none()
                if old is not None:
                    if old != fingerprint:
                        raise DocumentConflict('source identity already stores different content/profiles/chunks/vectors')
                    already = True
                else:
                    if self.source_prefix:
                        own=connection.execute(select(func.count(),func.coalesce(func.sum(func.octet_length(self.documents.c.original_bytes)),0)).where(self._scope())).one()
                        total=connection.execute(select(func.count(),func.coalesce(func.sum(func.octet_length(self.documents.c.original_bytes)),0))).one()
                        if own[0]>=20 or own[1]+len(original_bytes)>5*1024*1024 or total[0]>=100 or total[1]+len(original_bytes)>25*1024*1024:
                            raise DocumentQuota('sample storage limit reached')
                    try:
                        connection.execute(insert(self.documents).values(document_id=document_id,
                            source_id=document.source.source_id, source=asdict(document.source),
                            original_bytes=original_bytes, extracted=payload,
                            extracted_sha256=digest(canonical(payload)), serialization=SERIALIZATION,
                            extraction_profile=extraction_profile, embedding_profile=embedding_profile,
                            fingerprint=fingerprint, chunk_count=len(chunks)))
                    except IntegrityError as error:
                        # Capture only this exact statement error, not failures
                        # in chunk/vector statements or transaction context exit.
                        document_insert_error = error
                        raise
                    if _checkpoint: _checkpoint('document')
                    for ordinal, (c, vector) in enumerate(zip(chunks, units)):
                        ref = c.chunk.citation
                        connection.execute(insert(self.chunks).values(located_id=c.located_id,
                            document_id=document_id, ordinal=ordinal, original_chunk_id=ref.chunk_id,
                            segment_index=c.segment_index, text=c.chunk.text, start=ref.start,
                            end=ref.end, locator=asdict(c.locator)))
                        if _checkpoint: _checkpoint('chunk')
                        connection.execute(insert(self.embeddings).values(located_id=c.located_id,
                            vector=list(vector), profile=embedding_profile))
                        if _checkpoint: _checkpoint('vector')
                # All body operations finished. Only context exit remains.
                body_completed = True
        except IntegrityError as error:
            if body_completed:
                raise DocumentCommitUnknown(already_present=already) from error
            binding = self.identity_constraint_binding
            # Outer context must have unwound without replacing the original
            # insert error. Cleanup failure or commit-phase errors never recover.
            if (error is not document_insert_error or binding is None or
                    not binding.permits(error, stage='document_insert')):
                raise
            expected = dict(document_id=document_id, source_id=document.source.source_id,
                source=asdict(document.source), original_bytes=original_bytes, extracted=payload,
                extracted_sha256=digest(canonical(payload)), serialization=SERIALIZATION,
                extraction_profile=extraction_profile, embedding_profile=embedding_profile,
                fingerprint=fingerprint, chunk_count=len(chunks))
            expected_chunks = tuple(dict(located_id=c.located_id, document_id=document_id,
                ordinal=i, original_chunk_id=c.chunk.citation.chunk_id,
                segment_index=c.segment_index, text=c.chunk.text,
                start=c.chunk.citation.start, end=c.chunk.citation.end,
                locator=asdict(c.locator)) for i,c in enumerate(chunks))
            try:
                rows = self._recovery_rows(document_id)
                comparison = compare_recovery_rows(rows, expected, expected_chunks, units, self.dimension)
            except Exception:
                # Preserve original insert failure; no automatic retry or fallback.
                raise error
            if comparison is not Equivalence.EQUIVALENT:
                # Both complete mismatch and unresolved read preserve the
                # original identity-insert failure, never recovery success.
                raise error
            # All authoritative persisted fields verified in that single snapshot.
            ordered = sorted(rows, key=lambda r: r['chunk__ordinal']) if chunks else []
            persisted_vectors = tuple(tuple(float(x) for x in r['vector__vector']) for r in ordered)
            return StoredDocument(document_id, document, original_bytes, expected['extracted_sha256'],
                extraction_profile, embedding_profile, chunks, persisted_vectors, True)
        except Exception as error:
            if body_completed:
                raise DocumentCommitUnknown(already_present=already) from error
            raise
        try:
            result = self.load_document(document_id, _already_present=already)
            if result is None:
                raise ValueError('document readback returned no result')
            return result
        except Exception as error:
            raise DocumentReadbackUnavailable(already_present=already) from error

    def _recovery_rows(self, document_id):
        # One statement snapshot, explicit aliases, complete children including
        # vectorless chunks and a null child row for a zero-chunk parent.
        binding = self.vector_send_binding
        if binding is None:
            return []  # Missing trusted codec is unresolved, never text fallback.
        binary = Function(quoted_name(binding.function, True), self.embeddings.c.vector,
            packagenames=(quoted_name(binding.schema, True),), type_=LargeBinary())
        statement = select(
            *(c.label('doc__'+c.name) for c in self.documents.c),
            *(c.label('chunk__'+c.name) for c in self.chunks.c),
            *(c.label('vector__'+c.name) for c in self.embeddings.c if c.name != 'vector'),
            binary.label('vector__binary')
        ).select_from(self.documents.outerjoin(self.chunks,
            self.chunks.c.document_id == self.documents.c.document_id).outerjoin(
            self.embeddings, self.embeddings.c.located_id == self.chunks.c.located_id)
        ).where(self.documents.c.document_id == document_id, self._scope()).order_by(
            self.chunks.c.ordinal).limit(RECOVERY_CHUNK_CAP+1)
        with self.engine.connect() as connection:
            raw_rows = connection.execute(statement).mappings().all()
        rows = []
        try:
            for raw in raw_rows:
                row = dict(raw)
                value = row.pop('vector__binary')
                row['vector__vector'] = None if value is None else decode_vector_binary(value, self.dimension)
                rows.append(row)
        except (KeyError, TypeError, ValueError):
            return []
        return rows

    @staticmethod
    def _located(row, source):
        return LocatedChunk(DocumentChunk(CitationRef(source, row['original_chunk_id'],
            row['start'], row['end']), row['text']), row['segment_index'],
            SegmentLocator(**row['locator']), row['located_id'])

    def load_document(self, document_id, *, _already_present=False):
        with self.engine.connect() as connection:
            row = connection.execute(select(self.documents).where(
                self.documents.c.document_id == document_id, self._scope())).mappings().one()
            document = decode_document(row['source'], row['extracted'])
            if digest(bytes(row['original_bytes'])) != document.source.sha256 or digest(canonical(row['extracted'])) != row['extracted_sha256']:
                raise ValueError('stored document hash mismatch')
            rows = connection.execute(select(self.chunks, self.embeddings.c.vector).join(
                self.embeddings).where(self.chunks.c.document_id == document_id).order_by(
                self.chunks.c.ordinal)).mappings().all()
            if len(rows) != row['chunk_count']:
                raise ValueError('stored chunk/vector set is incomplete')
            if row['serialization'] != SERIALIZATION:
                raise ValueError('unknown stored serialization')
        located = tuple(self._located(r, document.source) for r in rows)
        vectors = tuple(tuple(float(x) for x in r['vector']) for r in rows)
        self._prepare(document, bytes(row['original_bytes']), located, vectors,
                      row['extraction_profile'], row['embedding_profile'], _require_profile=False)
        return StoredDocument(document_id, document, bytes(row['original_bytes']), row['extracted_sha256'],
            row['extraction_profile'], row['embedding_profile'], located, vectors, _already_present)

    def find_document(self, source_id):
        self._check_source_scope(source_id)
        document_id = digest(canonical(['document-v1', source_id]))
        with self.engine.connect() as connection:
            found = connection.execute(select(self.documents.c.document_id).where(
                self.documents.c.document_id == document_id, self._scope())).scalar_one_or_none()
        return None if found is None else self.load_document(found, _already_present=True)

    def _require_lifecycle_scope(self):
        if not self.source_prefix:
            raise ValueError('document management requires tenant scope')

    @staticmethod
    def _summary(row):
        source = row['source']
        return {'document_id': row['document_id'], 'filename': source['filename'],
                'mime_type': source['mime_type'], 'sha256': source['sha256'],
                'byte_size': row['byte_size'], 'chunk_count': row['chunk_count'],
                'extraction_profile': row['extraction_profile'],
                'embedding_profile': row['embedding_profile']}

    def _summary_query(self):
        return select(self.documents.c.document_id, self.documents.c.source,
            func.octet_length(self.documents.c.original_bytes).label('byte_size'),
            self.documents.c.chunk_count, self.documents.c.extraction_profile,
            self.documents.c.embedding_profile).where(self._scope())

    def list_documents(self):
        self._require_lifecycle_scope()
        # A scoped account is quota-bounded to20 records. Never accept caller scope.
        with self.engine.connect() as connection:
            rows = connection.execute(self._summary_query().order_by(
                self.documents.c.document_id)).mappings().all()
        return [self._summary(row) for row in rows]

    def document_details(self, document_id):
        self._require_lifecycle_scope()
        with self.engine.connect() as connection:
            row = connection.execute(self._summary_query().where(
                self.documents.c.document_id == document_id)).mappings().one_or_none()
        return None if row is None else self._summary(row)

    def delete_document(self, document_id, *, _checkpoint=None):
        self._require_lifecycle_scope()
        with self.engine.begin() as connection:
            # Same lock as ingestion: quota/dedup/store and delete cannot interleave.
            connection.execute(text('SELECT pg_advisory_xact_lock(732514611)'))
            found = connection.execute(select(self.documents.c.document_id).where(
                self.documents.c.document_id == document_id, self._scope()).with_for_update()).scalar_one_or_none()
            if found is None:
                return False
            # Explicit ordered child cleanup is atomic even on a pre-existing schema
            # whose foreign keys do not cascade. The parent predicate is scoped too.
            owned_chunks = select(self.chunks.c.located_id).where(self.chunks.c.document_id == found)
            connection.execute(self.embeddings.delete().where(self.embeddings.c.located_id.in_(owned_chunks)))
            if _checkpoint: _checkpoint('vectors_deleted')
            connection.execute(self.chunks.delete().where(self.chunks.c.document_id == found))
            if _checkpoint: _checkpoint('chunks_deleted')
            connection.execute(self.documents.delete().where(
                self.documents.c.document_id == found, self._scope()))
            if _checkpoint: _checkpoint('document_deleted')
        return True

    def retrieve(self, query_vector, *, top_k):
        if type(top_k) is not int or top_k <= 0:
            raise ValueError('positive integer top_k required')
        query = _unit(query_vector, self.dimension)
        distance = self.embeddings.c.vector.cosine_distance(list(query))
        statement = select(self.chunks, self.documents.c.source, distance.label('distance')).join(
            self.embeddings).join(self.documents).where(self.embeddings.c.profile == self.embedding_profile, self._scope()).order_by(
            distance, self.documents.c.source_id.collate('C'), self.chunks.c.start, self.chunks.c.located_id.collate('C')).limit(top_k)
        with self.engine.connect() as connection:
            rows = connection.execute(statement).mappings().all()
        return tuple(LocatedHit(max(-1., min(1., 1.-float(row['distance']))),
            self._located(row, SourceDocument(**row['source']))) for row in rows)
