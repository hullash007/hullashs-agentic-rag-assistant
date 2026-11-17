"""Controlled text-query seam. Caller injects provider; no live adapter/config."""
from .embeddings import EmbeddingProvider
from .retrieval import _unit
from .langgraph_adapter import invoke_retrieval_tool


class QueryEmbeddingFailure(RuntimeError):pass
class QueryEmbeddingResponseError(ValueError):pass


def query_evidence(query, provider: EmbeddingProvider, sdk_tool, *, expected_dimension,
                   max_query_chars,top_k,max_evidence_items,max_context_chars,call_id,executor=None):
    for value in (expected_dimension,max_query_chars,top_k,max_evidence_items,max_context_chars):
        if type(value) is not int or value<=0:raise ValueError('explicit positive integer limits/dimension required')
    if not isinstance(query,str) or not query.strip() or len(query)>max_query_chars:
        raise ValueError('nonempty bounded query required')
    if not isinstance(call_id,str) or not call_id.strip():raise ValueError('call_id required')
    try:raw=provider.embed_documents([query])
    except Exception as exc:raise QueryEmbeddingFailure('query embedding provider failed') from exc
    try:
        if len(raw)!=1:raise ValueError('exactly one query vector required')
        vector=tuple(raw[0]);_unit(vector,expected_dimension)
    except (ValueError,TypeError,OverflowError,KeyError,IndexError) as exc:
        raise QueryEmbeddingResponseError('invalid query embedding response') from exc
    # Existing SDK/vector-only contract remains unchanged. No fallback/retry.
    execute=invoke_retrieval_tool if executor is None else executor
    return execute(sdk_tool,'retrieve_evidence',{
        'query_vector':list(vector),'top_k':top_k,'max_evidence_items':max_evidence_items,
        'max_context_chars':max_context_chars},call_id=call_id)
