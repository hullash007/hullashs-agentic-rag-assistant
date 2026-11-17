"""Offline provenance contracts. Offsets are Unicode character indexes, not bytes/pages."""
from dataclasses import dataclass
import re


def _label(value, name):
    if not isinstance(value, str) or not value.strip() or any(ord(c) < 32 for c in value):
        raise ValueError(name + ' must be nonempty text without control characters')


@dataclass(frozen=True)
class SourceDocument:
    source_id: str
    filename: str
    mime_type: str
    sha256: str
    title: str | None = None

    def __post_init__(self):
        for name in ('source_id', 'filename', 'mime_type'):
            _label(getattr(self, name), name)
        if self.filename in ('.', '..') or '/' in self.filename or '\\' in self.filename:
            raise ValueError('filename is a display basename, not a path')
        if not isinstance(self.sha256, str) or not re.fullmatch('[0-9a-f]{64}', self.sha256):
            raise ValueError('sha256 must fingerprint original bytes as lowercase hex')
        if self.title is not None:
            _label(self.title, 'title')


@dataclass(frozen=True)
class CitationRef:
    source: SourceDocument
    chunk_id: str
    start: int
    end: int

    def __post_init__(self):
        if not isinstance(self.source, SourceDocument):
            raise ValueError('source must be SourceDocument')
        _label(self.chunk_id, 'chunk_id')
        if type(self.start) is not int or type(self.end) is not int or not 0 <= self.start < self.end:
            raise ValueError('invalid character offsets')


@dataclass(frozen=True)
class DocumentChunk:
    citation: CitationRef
    text: str

    def __post_init__(self):
        if not isinstance(self.citation, CitationRef) or not isinstance(self.text, str):
            raise ValueError('invalid chunk contract')
        if len(self.text) != self.citation.end - self.citation.start:
            raise ValueError('text length must match source range')
