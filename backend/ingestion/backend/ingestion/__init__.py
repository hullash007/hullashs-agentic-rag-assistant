"""Offline ingestion preparation. Not connected to the application graph."""
from .contracts import SourceDocument, CitationRef, DocumentChunk
from .chunking import chunk_text
from .embeddings import EmbeddingProvider, embed_chunks
__all__ = ['SourceDocument', 'CitationRef', 'DocumentChunk', 'chunk_text', 'EmbeddingProvider', 'embed_chunks']
