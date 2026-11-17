"""Pure integration of offline preparation components; no adapter selection."""
from .plain_text import IngestedText
from .chunking import chunk_text
from .embeddings import embed_chunks
from .retrieval import InMemoryVectorIndex, _unit


def prepare_and_search(ingested_text, provider, query_vector, *, max_chars,
                       overlap, max_chunks, top_k):
    if not isinstance(ingested_text, IngestedText):
        raise ValueError('ingested_text must be IngestedText')
    if type(max_chunks) is not int or max_chunks <= 0:
        raise ValueError('max_chunks must be a positive integer')
    if type(top_k) is not int or top_k <= 0:
        raise ValueError('top_k must be a positive integer')
    if type(max_chars) is not int or type(overlap) is not int or not 0 <= overlap < max_chars:
        raise ValueError('require integer max_chars > overlap >= 0')
    length=len(ingested_text.text)
    if ingested_text.text.strip():
        required=1 + max(0, (length-max_chars+max_chars-overlap-1)//(max_chars-overlap))
        if required>max_chunks:
            raise ValueError('input exceeds max_chunks before chunk allocation')
    chunks=chunk_text(ingested_text.text,ingested_text.source,
                      max_chars=max_chars,overlap=overlap)
    if len(chunks)>max_chunks:
        raise ValueError('input exceeds max_chunks; no truncation performed')
    if not chunks:
        return ()
    query=tuple(query_vector)
    _unit(query)  # Reject independently invalid query before injected provider work.
    vectors=embed_chunks(chunks,provider)
    index=InMemoryVectorIndex(zip(chunks,vectors),max_items=max_chunks)
    return index.search(query,top_k=top_k)
