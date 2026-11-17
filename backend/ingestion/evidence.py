"""Bounded citation-preserving evidence, not instructions or answer support claims."""
from dataclasses import dataclass, asdict
import json,math
from .located_search import LocatedHit
from .segments import LocatedChunk,SegmentLocator
from .contracts import DocumentChunk,CitationRef,SourceDocument


@dataclass(frozen=True)
class EvidenceEntry:
    ref: str
    hit: LocatedHit


@dataclass(frozen=True)
class EvidenceBundle:
    context: str
    entries: tuple[EvidenceEntry,...]
    omitted_count: int


def _validate(hit):
    if not isinstance(hit,LocatedHit) or not isinstance(hit.located_chunk,LocatedChunk):raise ValueError('LocatedHit required')
    c=hit.located_chunk
    if not isinstance(c.chunk,DocumentChunk) or not isinstance(c.chunk.citation,CitationRef) or not isinstance(c.chunk.citation.source,SourceDocument) or not isinstance(c.locator,SegmentLocator):raise ValueError('complete citation and locator required')
    if isinstance(hit.score,bool) or not isinstance(hit.score,(int,float)) or not math.isfinite(hit.score) or not -1<=hit.score<=1:raise ValueError('finite cosine score required')
    if type(c.segment_index) is not int or c.segment_index<0 or not isinstance(c.located_id,str) or not c.located_id:raise ValueError('located identity required')


def assemble_evidence(located_hits, *, max_items, max_chars):
    if type(max_items) is not int or max_items<=0 or type(max_chars) is not int or max_chars<=0:raise ValueError('positive integer limits required')
    hits=tuple(located_hits)
    for hit in hits:_validate(hit)
    entries=[];blocks=[];length=0
    for hit in hits[:max_items]:
        ref='E'+str(len(entries)+1);c=hit.located_chunk;citation=c.chunk.citation
        # JSON Lines separates records and escapes embedded newlines/quotes. Text
        # and labels are untrusted evidence data, never agent instructions.
        block=json.dumps({'ref':ref,'source':asdict(citation.source),'locator':asdict(c.locator),'segment_index':c.segment_index,'located_id':c.located_id,'chunk_id':citation.chunk_id,'start':citation.start,'end':citation.end,'score':hit.score,'text':c.chunk.text},ensure_ascii=False,separators=(',',':'),allow_nan=False)
        needed=len(block)+(1 if blocks else 0)
        if length+needed>max_chars:break
        entries.append(EvidenceEntry(ref,hit));blocks.append(block);length+=needed
    return EvidenceBundle('\n'.join(blocks),tuple(entries),len(hits)-len(entries))
