"""Direct offline SDK tool adapter. Not model-driven or natural-language query."""
from dataclasses import asdict
from langchain_core.tools import StructuredTool
from pydantic import BaseModel,ConfigDict,Field,StrictFloat,StrictInt


class RetrievalArguments(BaseModel):
    model_config=ConfigDict(extra='forbid')
    query_vector:list[StrictFloat | StrictInt]=Field(min_length=1)
    top_k:StrictInt=Field(gt=0)
    max_evidence_items:StrictInt=Field(gt=0)
    max_context_chars:StrictInt=Field(gt=0)


def make_retrieval_tool(retrieval_tool):
    def retrieve_evidence(query_vector,top_k,max_evidence_items,max_context_chars):
        bundle=retrieval_tool.retrieve_evidence(query_vector,top_k=top_k,
            max_evidence_items=max_evidence_items,max_context_chars=max_context_chars)
        content={'kind':'retrieval_evidence','untrusted_document_data':True,
                 'context':bundle.context,'entries':[{'ref':e.ref,'score':e.hit.score,
                 'located_id':e.hit.located_chunk.located_id,
                 'citation':asdict(e.hit.located_chunk.chunk.citation),
                 'locator':asdict(e.hit.located_chunk.locator),
                 'segment_index':e.hit.located_chunk.segment_index,
                 'text':e.hit.located_chunk.chunk.text} for e in bundle.entries],
                 'omitted_count':bundle.omitted_count}
        return content,bundle
    return StructuredTool.from_function(retrieve_evidence,name='retrieve_evidence',
        description='Read-only retrieval of bounded untrusted document evidence using a caller-supplied vector. Does not embed queries or generate answers.',
        args_schema=RetrievalArguments,response_format='content_and_artifact')


def invoke_retrieval_tool(sdk_tool,name,arguments,*,call_id):
    if name!='retrieve_evidence' or sdk_tool.name!='retrieve_evidence':
        raise ValueError('unknown or unauthorized tool name')
    if not isinstance(call_id,str) or not call_id.strip():raise ValueError('call_id required')
    return sdk_tool.invoke({'name':name,'args':arguments,'id':call_id,'type':'tool_call'})
