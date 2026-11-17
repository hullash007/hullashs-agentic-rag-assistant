"""Injected provider interface only. No live adapter, credentials, retries or I/O."""
import math
from typing import Protocol, Sequence
from .contracts import DocumentChunk


class EmbeddingProvider(Protocol):
    def embed_documents(self, texts: Sequence[str]) -> Sequence[Sequence[float]]: ...


def embed_chunks(chunks: Sequence[DocumentChunk], provider: EmbeddingProvider) -> tuple[tuple[float, ...], ...]:
    if not chunks:
        return ()
    if not all(isinstance(c, DocumentChunk) for c in chunks):
        raise ValueError('expected DocumentChunk values')
    raw = provider.embed_documents([c.text for c in chunks])
    if len(raw) != len(chunks):
        raise ValueError('one vector required per chunk')
    vectors = []
    dimension = None
    for row in raw:
        if not row:
            raise ValueError('empty embedding vector')
        if any(isinstance(x, bool) or not isinstance(x, (int, float)) for x in row):
            raise ValueError('embedding components must be real numbers')
        vector = tuple(float(x) for x in row)
        if not all(math.isfinite(x) for x in vector):
            raise ValueError('embedding components must be finite')
        if dimension is not None and len(vector) != dimension:
            raise ValueError('inconsistent embedding dimensions')
        dimension = len(vector)
        vectors.append(vector)
    return tuple(vectors)
