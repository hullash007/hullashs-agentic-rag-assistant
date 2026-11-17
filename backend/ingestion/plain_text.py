"""Bounded in-memory plain-text byte ingestion. No file/URL/provider I/O."""
from dataclasses import dataclass, replace
import hashlib
from .contracts import SourceDocument


@dataclass(frozen=True)
class IngestedText:
    source: SourceDocument
    text: str


def ingest_plain_text(raw_bytes: bytes, *, source_id: str, filename: str,
                      mime_type: str, max_bytes: int) -> IngestedText:
    if not isinstance(raw_bytes, bytes):
        raise TypeError('raw_bytes must be immutable bytes')
    metadata = SourceDocument(source_id, filename, mime_type, '0' * 64)
    if ':' in filename:
        raise ValueError('filename must be a portable display basename')
    if mime_type != 'text/plain':
        raise ValueError('only text/plain is supported')
    if type(max_bytes) is not int or max_bytes <= 0:
        raise ValueError('max_bytes must be a positive integer')
    if len(raw_bytes) > max_bytes:
        raise ValueError('original byte size exceeds max_bytes')
    digest = hashlib.sha256(raw_bytes).hexdigest()
    text = raw_bytes.decode('utf-8', errors='strict')
    if text.startswith('\ufeff'):
        text = text[1:]
    if '\x00' in text:
        raise ValueError('NUL characters are not plain-text content')
    return IngestedText(replace(metadata, sha256=digest), text)
