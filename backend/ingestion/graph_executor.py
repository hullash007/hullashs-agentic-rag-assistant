"""Explicit graph-backed single tool execution. Not LLM-driven tool selection."""
import json
from langchain_core.messages import ToolMessage
from .evidence import EvidenceBundle
from .routing_graph import build_retrieval_graph

class GraphResultContractError(RuntimeError):pass
class GraphToolFailure(RuntimeError):
    def __init__(self,category,message):
        super().__init__('graph tool failed: '+category)
        self.category=category
        self.tool_message=message


def graph_message(result,call_id):
    if not isinstance(result,dict) or not isinstance(result.get('messages'),list):
        raise GraphResultContractError('graph messages missing')
    messages=result['messages']
    if len(messages)!=1 or not isinstance(messages[0],ToolMessage):
        raise GraphResultContractError('exactly one ToolMessage required')
    message=messages[0]
    if message.tool_call_id!=call_id or message.name!='retrieve_evidence':
        raise GraphResultContractError('unexpected tool message')
    if message.status=='error':
        if message.artifact is not None:raise GraphResultContractError('error result contains unexpected artifact')
        try:
            data=json.loads(message.content)
            if set(data)!={'kind','category'} or data['kind']!='tool_error' or data['category'] not in ('validation_error','retrieval_error','unexpected_error'):
                raise ValueError('unrecognized error envelope')
        except (ValueError,TypeError,KeyError) as exc:
            raise GraphResultContractError('invalid graph error result') from exc
        # The graph's category is preserved, not upgraded to root-cause proof.
        raise GraphToolFailure(data['category'],message)
    if not isinstance(message.artifact,EvidenceBundle):
        raise GraphResultContractError('successful EvidenceBundle missing')
    return message


class GraphToolExecutor:
    def __init__(self,sdk_tool):
        if sdk_tool.name!='retrieve_evidence':raise ValueError('only registered retrieval tool allowed')
        self._sdk_tool=sdk_tool
        self._graph=build_retrieval_graph(sdk_tool)

    def __call__(self,sdk_tool,name,arguments,*,call_id):
        if sdk_tool is not self._sdk_tool or name!='retrieve_evidence':
            raise ValueError('executor bound to a different tool')
        if not isinstance(call_id,str) or not call_id.strip():raise ValueError('call_id required')
        result=self._graph.invoke({'calls':[{'name':name,'args':arguments,'id':call_id}]})
        return graph_message(result,call_id)
