"""Read-only vector retrieval tool; no query embedding, providers or agent SDK."""
from dataclasses import dataclass,replace
from .contracts import DocumentChunk
from .segments import LocatedChunk
from .located_search import LocatedHit
from .retrieval import InMemoryVectorIndex,_unit
from .evidence import assemble_evidence


@dataclass(frozen=True,init=False)
class LocatedRetrievalTool:
    _index: InMemoryVectorIndex
    _originals: tuple
    _dimension: int | None

    def __init__(self,entries,*,max_items):
        # Caller supplies existing located chunks/vectors, not documents/provider.
        entries=tuple(entries)
        if any(not isinstance(c,LocatedChunk) for c,v in entries):raise ValueError('located chunks required')
        aliases=tuple((DocumentChunk(replace(c.chunk.citation,chunk_id=c.located_id),c.chunk.text),v) for c,v in entries)
        index=InMemoryVectorIndex(aliases,max_items=max_items)
        object.__setattr__(self,'_index',index)
        object.__setattr__(self,'_originals',tuple((c.located_id,c) for c,v in entries))
        object.__setattr__(self,'_dimension',index._dimension)

    def retrieve_evidence(self,query_vector,*,top_k,max_evidence_items,max_context_chars):
        for value in (top_k,max_evidence_items,max_context_chars):
            if type(value) is not int or value<=0:raise ValueError('positive integer request limits required')
        query=tuple(query_vector)
        _unit(query,self._dimension)
        hits=self._index.search(query,top_k=top_k)
        originals=dict(self._originals)
        located=tuple(LocatedHit(h.score,originals[h.citation.chunk_id]) for h in hits)
        return assemble_evidence(located,max_items=max_evidence_items,max_chars=max_context_chars)
