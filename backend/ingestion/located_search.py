"""Located-chunk bridge. Internal indexing aliases never replace original citations."""
from dataclasses import dataclass, replace
from .contracts import DocumentChunk
from .segments import ExtractedDocument, LocatedChunk, chunk_segment
from .embeddings import embed_chunks
from .retrieval import InMemoryVectorIndex, _unit


@dataclass(frozen=True)
class LocatedHit:
    score: float
    located_chunk: LocatedChunk


def search_pdf_segments(document, provider, query_vector, *, max_chars, overlap,
                        max_chunks, top_k):
    if not isinstance(document,ExtractedDocument) or document.format!='pdf':
        raise ValueError('PDF extracted document required')
    if type(max_chunks) is not int or max_chunks<=0 or type(top_k) is not int or top_k<=0:
        raise ValueError('positive integer limits required')
    if type(max_chars) is not int or type(overlap) is not int or not 0<=overlap<max_chars:
        raise ValueError('invalid chunk options')
    required=0
    for segment in document.segments:
        if segment.locator.kind!='page':raise ValueError('PDF segments require established page locators')
        if segment.text.strip():
            required+=1+max(0,(len(segment.text)-overlap-1)//(max_chars-overlap)) if len(segment.text)>max_chars else 1
        if required>max_chunks:raise ValueError('located chunks exceed max_chunks')
    located=tuple(c for segment in document.segments for c in chunk_segment(segment,document.source,max_chars=max_chars,overlap=overlap))
    if not located:return ()
    query=tuple(query_vector);_unit(query)
    vectors=embed_chunks(tuple(c.chunk for c in located),provider)
    # Existing index requires unique chunk IDs, while original segment-local IDs
    # can repeat. Alias ONLY inside the temporary index, then recover originals.
    originals={c.located_id:c for c in located}
    aliases=tuple(DocumentChunk(replace(c.chunk.citation,chunk_id=c.located_id),c.chunk.text) for c in located)
    hits=InMemoryVectorIndex(zip(aliases,vectors),max_items=max_chunks).search(query,top_k=top_k)
    return tuple(LocatedHit(h.score,originals[h.citation.chunk_id]) for h in hits)
