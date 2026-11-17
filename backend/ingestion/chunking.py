"""Versioned deterministic exact-character chunking, with no text normalization."""
import hashlib
import json
from .contracts import CitationRef, DocumentChunk, SourceDocument


def chunk_text(text: str, source: SourceDocument, *, max_chars: int = 1000,
               overlap: int = 100) -> tuple[DocumentChunk, ...]:
    if not isinstance(text, str) or not isinstance(source, SourceDocument):
        raise ValueError('expected extracted text and source provenance')
    if type(max_chars) is not int or type(overlap) is not int or not 0 <= overlap < max_chars:
        raise ValueError('require integer max_chars > overlap >= 0')
    if not text or not text.strip():
        return ()
    text_hash = hashlib.sha256(text.encode('utf-8')).hexdigest()
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        identity = json.dumps(['chars-v1', source.source_id, source.sha256,
                               text_hash, max_chars, overlap, start, end],
                              ensure_ascii=False, separators=(',', ':'))
        chunk_id = hashlib.sha256(identity.encode('utf-8')).hexdigest()
        chunks.append(DocumentChunk(CitationRef(source, chunk_id, start, end), text[start:end]))
        if end == len(text):
            break
        start = end - overlap
    return tuple(chunks)
