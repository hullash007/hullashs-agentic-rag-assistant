"""Local ingestion service. Explicit parser, provider and repository injection."""
from dataclasses import asdict
import hashlib, json, tempfile, pathlib, threading
from .bounded_process import run_child
from .contracts import SourceDocument
from .plain_text import ingest_plain_text
from .segments import ExtractedDocument, ExtractedSegment, SegmentLocator, chunk_segment
from .embeddings import embed_chunks
from .postgres_repository import DocumentConflict

MAX_BYTES = 2097152
MAX_CHUNKS = 128
CHUNK_CHARS, OVERLAP = 1000, 100
MIMES = {'text/plain': 'plain_text', 'application/pdf': 'pdf',
         'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'docx',
         'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'xlsx'}
PROFILES = {'plain_text': 'utf8-bom-exact-v1', 'pdf': 'pypdf7.1.0-bounded-v1',
            'docx': 'python-docx1.2.0-body-paragraph-v1',
            'xlsx': 'openpyxl3.1.5-controlled-inspected-v1'}


class IngestionRejected(ValueError):
    pass


class IngestionBusy(RuntimeError):
    pass


def validate_metadata(filename, content_type):
    if content_type not in MIMES:
        raise IngestionRejected('unsupported content type')
    if not isinstance(filename, str) or len(filename) > 200 or ':' in filename:
        raise IngestionRejected('invalid filename')
    try:
        SourceDocument('metadata-only', filename, content_type, '0' * 64)
    except ValueError as error:
        raise IngestionRejected('invalid filename') from error


class BoundedParser:
    """Existing parser experiments in their separate, pinned child interpreters."""
    def __init__(self, *, pdf_python, office_python):
        for path in (pdf_python, office_python):
            if not isinstance(path, str) or not pathlib.Path(path).is_absolute() or not pathlib.Path(path).is_file():
                raise ValueError('explicit existing absolute parser interpreter paths required')
        self.pdf_python, self.office_python = pdf_python, office_python
        self.run_child = run_child
        self.executions = []

    def parse(self, raw, source):
        if source.mime_type == 'text/plain':
            text = ingest_plain_text(raw, source_id=source.source_id, filename=source.filename,
                                     mime_type=source.mime_type, max_bytes=MAX_BYTES)
            return ExtractedDocument(source, 'plain_text',
                (ExtractedSegment(0, text.text, SegmentLocator('document')),))
        executable = self.pdf_python if source.mime_type == 'application/pdf' else self.office_python
        with tempfile.TemporaryDirectory(prefix='rag-parser-') as directory:
            path = pathlib.Path(directory) / 'input.bin'
            path.write_bytes(raw)
            metadata, pipes = self.run_child([executable, str(pathlib.Path(__file__).with_name('parser_child.py')),
                                             str(path), json.dumps(asdict(source))])
        self.executions.append(metadata)
        if metadata['exit_code'] != 0 or metadata['kill_reason'] is not None or not metadata['reaped']:
            raise IngestionRejected('parser rejected document')
        try:
            payload = json.loads(pipes['stdout'])
            if set(payload) != {'document', 'network_attempts'} or payload['network_attempts'] != 0:
                raise ValueError('invalid child envelope')
            value = payload['document']
            if set(value) != {'source', 'format', 'segments'} or value['source'] != asdict(source) or value['format'] != MIMES[source.mime_type]:
                raise ValueError('parser source or format mismatch')
            segments = tuple(ExtractedSegment(s['segment_index'], s['text'], SegmentLocator(**s['locator']))
                             for s in value['segments'] if set(s) == {'segment_index', 'text', 'locator'})
            if len(segments) != len(value['segments']):
                raise ValueError('invalid segment keys')
            expected_kind = {'pdf': 'page', 'docx': 'paragraph', 'xlsx': 'sheet'}[value['format']]
            if any(s.locator.kind != expected_kind for s in segments):
                raise ValueError('format locator mismatch')
            return ExtractedDocument(source, value['format'], segments)
        except (ValueError, TypeError, KeyError) as error:
            raise IngestionRejected('invalid parser response') from error


class IngestionService:
    def __init__(self, *, parser, provider, repository):
        if parser is None or provider is None or repository is None:
            raise ValueError('explicit dependencies required')
        self.parser, self.provider, self.repository = parser, provider, repository
        self.gate = threading.Lock()

    def ingest_document(self, raw, *, filename, content_type):
        validate_metadata(filename, content_type)
        if not isinstance(raw, bytes) or len(raw) > MAX_BYTES:
            raise IngestionRejected('original byte cap/type')
        if not self.gate.acquire(blocking=False):
            raise IngestionBusy('ingestion in progress')
        try:
            sha = hashlib.sha256(raw).hexdigest()
            # Server-created identity, never a client path or arbitrary document ID.
            identity = self.repository.source_id_for_sha(sha) if hasattr(self.repository,'source_id_for_sha') else 'sha256:'+sha
            source = SourceDocument(identity, filename, content_type, sha)
            extraction_profile = PROFILES[MIMES[content_type]] + ':chars1000-overlap100'
            existing = self.repository.find_document(source.source_id)
            if existing is not None:
                if (existing.document.source != source or existing.original_bytes != raw or
                    existing.extraction_profile != extraction_profile or
                    existing.embedding_profile != self.repository.embedding_profile):
                    raise DocumentConflict('source metadata or processing profile conflict')
                return self._result(existing, sha)
            try:
                document = self.parser.parse(raw, source)
                if not isinstance(document, ExtractedDocument) or document.source != source or document.format != MIMES[content_type]:
                    raise ValueError('parser contract mismatch')
                required = 0
                for segment in document.segments:
                    if segment.text.strip():
                        length = len(segment.text)
                        required += 1 + max(0, (length-CHUNK_CHARS+CHUNK_CHARS-OVERLAP-1)//(CHUNK_CHARS-OVERLAP))
                    if required > MAX_CHUNKS:
                        raise IngestionRejected('chunk count exceeds local limit')
                located = tuple(c for segment in document.segments for c in chunk_segment(
                    segment, source, max_chars=CHUNK_CHARS, overlap=OVERLAP))
                vectors = embed_chunks(tuple(c.chunk for c in located), self.provider)
            except (ValueError, UnicodeError, TypeError) as error:
                raise IngestionRejected('document ingestion rejected') from error
            result = self.repository.store_document(document, raw, located, vectors,
                extraction_profile=extraction_profile,
                embedding_profile=self.repository.embedding_profile)
            return self._result(result, sha)
        finally:
            self.gate.release()

    @staticmethod
    def _result(result, sha):
        return {'document_id': result.document_id, 'source_sha256': sha,
                'filename': result.document.source.filename,
                'byte_size': len(result.original_bytes),
                'extracted_sha256': result.extracted_sha256,
                'segment_count': len(result.document.segments),
                'chunk_count': len(result.located_chunks),
                'status': 'already_present' if result.already_present else 'stored'}
