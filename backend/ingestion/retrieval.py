"""Synthetic-vector in-memory retrieval. No provider selection or persistence."""
from dataclasses import dataclass
import math
from .contracts import CitationRef, DocumentChunk


def _unit(vector, dimension=None):
    values = tuple(vector)
    if not values or (dimension is not None and len(values) != dimension):
        raise ValueError('invalid vector dimension')
    if any(isinstance(x, bool) or not isinstance(x, (int, float)) for x in values):
        raise ValueError('vector must contain real numbers')
    values = tuple(float(x) for x in values)
    if not all(math.isfinite(x) for x in values):
        raise ValueError('vector must be finite')
    scale = max(abs(x) for x in values)
    if not scale:
        raise ValueError('zero norm vector')
    scaled = tuple(x / scale for x in values)
    norm = math.sqrt(math.fsum(x*x for x in scaled))
    return tuple(x/norm for x in scaled)


@dataclass(frozen=True)
class RetrievalHit:
    score: float
    text: str
    citation: CitationRef


@dataclass(frozen=True, init=False)
class InMemoryVectorIndex:
    _entries: tuple
    _dimension: int | None

    def __init__(self, entries, *, max_items):
        if type(max_items) is not int or max_items <= 0:
            raise ValueError('max_items must be positive integer')
        rows=[]; seen=set(); dimension=None
        for chunk, vector in entries:
            if len(rows) >= max_items:
                raise ValueError('index exceeds max_items')
            if not isinstance(chunk, DocumentChunk):
                raise ValueError('entry must contain DocumentChunk')
            identity=chunk.citation.chunk_id
            if identity in seen:
                raise ValueError('duplicate chunk ID')
            seen.add(identity)
            unit=_unit(vector, dimension)
            dimension=len(unit)
            rows.append((chunk,unit))
        object.__setattr__(self,'_entries',tuple(rows))
        object.__setattr__(self,'_dimension',dimension)

    def search(self, query_vector, *, top_k):
        if type(top_k) is not int or top_k <= 0:
            raise ValueError('top_k must be positive integer')
        if not self._entries:
            return ()
        query=_unit(query_vector,self._dimension)
        hits=[]
        for chunk,vector in self._entries:
            score=max(-1.,min(1.,math.fsum(a*b for a,b in zip(query,vector))))
            hits.append(RetrievalHit(score,chunk.text,chunk.citation))
        # Existing contract has exact start offset, not a separate chunk_index.
        # Source-position tie-break avoids silently inventing a new contract.
        hits.sort(key=lambda h:(-h.score,h.citation.source.source_id,h.citation.start,h.citation.chunk_id))
        return tuple(hits[:top_k])
