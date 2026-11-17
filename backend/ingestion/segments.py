"""Future parser output contracts. Synthetic locator claims are not parser proof."""
from dataclasses import dataclass, asdict
import hashlib
import json
from .contracts import SourceDocument, DocumentChunk
from .chunking import chunk_text


def _integer(value, minimum):return type(value) is int and value>=minimum


@dataclass(frozen=True)
class SegmentLocator:
    kind: str
    page_number: int | None = None
    paragraph_index: int | None = None
    sheet_name: str | None = None
    row_start: int | None = None
    row_end: int | None = None

    def __post_init__(self):
        values=(self.page_number,self.paragraph_index,self.sheet_name,self.row_start,self.row_end)
        valid=False
        if self.kind=='document':valid=all(v is None for v in values)
        elif self.kind=='page':valid=_integer(self.page_number,1) and all(v is None for v in values[1:])
        elif self.kind=='paragraph':valid=_integer(self.paragraph_index,0) and all(v is None for v in (self.page_number,self.sheet_name,self.row_start,self.row_end))
        elif self.kind=='sheet':
            valid=(self.page_number is None and self.paragraph_index is None and isinstance(self.sheet_name,str) and bool(self.sheet_name.strip()) and _integer(self.row_start,1) and _integer(self.row_end,1) and self.row_end>=self.row_start)
        if not valid:raise ValueError('locator fields do not match declared kind')


@dataclass(frozen=True)
class ExtractedSegment:
    segment_index: int
    text: str
    locator: SegmentLocator

    def __post_init__(self):
        if not _integer(self.segment_index,0) or not isinstance(self.text,str) or not isinstance(self.locator,SegmentLocator):
            raise ValueError('invalid extracted segment')


@dataclass(frozen=True)
class ExtractedDocument:
    source: SourceDocument
    format: str
    segments: tuple[ExtractedSegment, ...]

    def __post_init__(self):
        if not isinstance(self.source,SourceDocument) or self.format not in ('plain_text','pdf','docx','xlsx'):
            raise ValueError('invalid extracted document metadata')
        if not isinstance(self.segments,tuple) or not all(isinstance(s,ExtractedSegment) and s.segment_index==i for i,s in enumerate(self.segments)):
            raise ValueError('segments must be ordered tuple with contiguous indices from zero')


@dataclass(frozen=True)
class LocatedChunk:
    chunk: DocumentChunk
    segment_index: int
    locator: SegmentLocator
    located_id: str


def chunk_segment(segment, source, *, max_chars, overlap):
    if not isinstance(segment,ExtractedSegment) or not isinstance(source,SourceDocument):
        raise ValueError('expected segment and source')
    result=[]
    for chunk in chunk_text(segment.text,source,max_chars=max_chars,overlap=overlap):
        # Existing chunk IDs are segment-local and can collide for identical segments.
        # Keep old contracts intact; use this wrapper ID for future located indexing.
        identity=json.dumps(['located-v1',chunk.citation.chunk_id,segment.segment_index,asdict(segment.locator)],sort_keys=True,ensure_ascii=False,separators=(',',':'))
        located_id=hashlib.sha256(identity.encode()).hexdigest()
        result.append(LocatedChunk(chunk,segment.segment_index,segment.locator,located_id))
    return tuple(result)
