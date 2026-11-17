"""Opt-in PostgreSQL document repository. No provider calls or default-path changes."""
from dataclasses import asdict, dataclass
import hashlib
import json
from sqlalchemy import (MetaData, Table, Column, Text, Integer, LargeBinary,
                        ForeignKey, UniqueConstraint, JSON, select, insert, func, text)
from sqlalchemy.exc import IntegrityError
from pgvector.sqlalchemy import VECTOR
from .contracts import SourceDocument, CitationRef, DocumentChunk
from .segments import ExtractedDocument, ExtractedSegment, SegmentLocator, LocatedChunk
from .located_search import LocatedHit
from .retrieval import _unit

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


class PostgresDocumentRepository:
    def __init__(self, engine, *, dimension, embedding_profile):
        if type(dimension) is not int or not 1 <= dimension <= 16000:
            raise ValueError('explicit fixed vector dimension required')
        if not isinstance(embedding_profile, str) or not embedding_profile.strip():
            raise ValueError('explicit embedding profile required')
        if engine.dialect.name != 'postgresql':
            raise ValueError('PostgreSQL required')
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

    def create_schema(self):
        # Extension creation belongs to disposable-database setup, not this service.
        self.metadata.create_all(self.engine)
        with self.engine.connect() as connection:
            actual = connection.execute(text("SELECT format_type(atttypid, atttypmod) FROM pg_attribute WHERE attrelid = 'rag_chunk_embeddings'::regclass AND attname = 'vector' AND NOT attisdropped")).scalar_one()
        if actual != f'vector({self.dimension})':
            raise ValueError('database vector dimension differs from configured dimension')

    def _prepare(self, document, original_bytes, located_chunks, vectors, extraction_profile, embedding_profile):
        if not isinstance(document, ExtractedDocument) or not isinstance(original_bytes, bytes):
            raise ValueError('ExtractedDocument and original bytes required')
        if digest(original_bytes) != document.source.sha256:
            raise ValueError('original bytes SHA mismatch')
        if not isinstance(extraction_profile, str) or not extraction_profile.strip():
            raise ValueError('explicit extraction profile required')
        if embedding_profile != self.embedding_profile:
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
        chunks, units, payload, fingerprint = self._prepare(document, original_bytes, located_chunks, vectors,
                                                           extraction_profile, embedding_profile)
        document_id = digest(canonical(['document-v1', document.source.source_id]))
        already = False
        try:
            with self.engine.begin() as connection:
                old = connection.execute(select(self.documents.c.fingerprint).where(
                    self.documents.c.document_id == document_id)).scalar_one_or_none()
                if old is not None:
                    if old != fingerprint:
                        raise DocumentConflict('source identity already stores different content/profiles/chunks/vectors')
                    already = True
                else:
                    connection.execute(insert(self.documents).values(document_id=document_id,
                        source_id=document.source.source_id, source=asdict(document.source),
                        original_bytes=original_bytes, extracted=payload,
                        extracted_sha256=digest(canonical(payload)), serialization=SERIALIZATION,
                        extraction_profile=extraction_profile, embedding_profile=embedding_profile,
                        fingerprint=fingerprint, chunk_count=len(chunks)))
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
        except IntegrityError as error:
            # A concurrent identical ingestion may have committed after our lookup.
            with self.engine.connect() as connection:
                old = connection.execute(select(self.documents.c.fingerprint).where(
                    self.documents.c.document_id == document_id)).scalar_one_or_none()
            if old != fingerprint:
                raise DocumentConflict('conflicting concurrent ingestion') from error
            already = True
        return self.load_document(document_id, _already_present=already)

    @staticmethod
    def _located(row, source):
        return LocatedChunk(DocumentChunk(CitationRef(source, row['original_chunk_id'],
            row['start'], row['end']), row['text']), row['segment_index'],
            SegmentLocator(**row['locator']), row['located_id'])

    def load_document(self, document_id, *, _already_present=False):
        with self.engine.connect() as connection:
            row = connection.execute(select(self.documents).where(
                self.documents.c.document_id == document_id)).mappings().one()
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
                      row['extraction_profile'], row['embedding_profile'])
        return StoredDocument(document_id, document, bytes(row['original_bytes']), row['extracted_sha256'],
            row['extraction_profile'], row['embedding_profile'], located, vectors, _already_present)

    def retrieve(self, query_vector, *, top_k):
        if type(top_k) is not int or top_k <= 0:
            raise ValueError('positive integer top_k required')
        query = _unit(query_vector, self.dimension)
        distance = self.embeddings.c.vector.cosine_distance(list(query))
        statement = select(self.chunks, self.documents.c.source, distance.label('distance')).join(
            self.embeddings).join(self.documents).where(self.embeddings.c.profile == self.embedding_profile).order_by(
            distance, self.documents.c.source_id.collate('C'), self.chunks.c.start, self.chunks.c.located_id.collate('C')).limit(top_k)
        with self.engine.connect() as connection:
            rows = connection.execute(statement).mappings().all()
        return tuple(LocatedHit(max(-1., min(1., 1.-float(row['distance']))),
            self._located(row, SourceDocument(**row['source']))) for row in rows)
