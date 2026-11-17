"""Explicit synthetic-call routing using actual LangGraph. No LLM selection."""
import json
from typing import TypedDict
from pydantic import ValidationError
from langchain_core.messages import AIMessage,ToolMessage
from langgraph.graph import StateGraph,START,END
from langgraph.prebuilt import ToolNode
from langgraph.prebuilt.tool_node import ToolInvocationError


def _error(exc):
    if isinstance(exc,(ValidationError,ValueError,ToolInvocationError)):
        category='validation_error'
    elif isinstance(exc,RuntimeError):
        category='retrieval_error'
    else:
        category='unexpected_error'
    return json.dumps({'kind':'tool_error','category':category},separators=(',',':'))


class RetrievalGraphState(TypedDict,total=False):
    calls:list[dict]
    messages:list
    rejected:dict
    outcomes:tuple


def build_retrieval_graph(sdk_tool):
    node=ToolNode([sdk_tool],handle_tool_errors=_error)
    def prepare(state):
        calls=state['calls'];accepted=[];rejected={};seen=set()
        for call in calls:
            cid=call.get('id')
            if not isinstance(cid,str) or not cid or cid in seen:
                raise ValueError('unique nonempty call IDs required')
            seen.add(cid)
            if call.get('name')!='retrieve_evidence':
                rejected[cid]=ToolMessage(content=json.dumps({'kind':'tool_error','category':'unknown_tool'}),tool_call_id=cid,status='error')
            else:accepted.append({'name':'retrieve_evidence','args':call.get('args',{}),'id':cid,'type':'tool_call'})
        return {'messages':[AIMessage(content='',tool_calls=accepted)],'rejected':rejected}
    def route(state):
        by_id=dict(state.get('rejected',{}))
        for message in state['messages']:
            if isinstance(message,ToolMessage):by_id[message.tool_call_id]=message
        outcomes=[]
        for call in state['calls']:
            message=by_id[call['id']]
            if message.status=='error':
                data=json.loads(message.content)
                outcomes.append({'call_id':call['id'],'status':'error','category':data['category'],'artifact':None})
            else:
                if message.artifact is None:raise ValueError('successful evidence artifact missing')
                outcomes.append({'call_id':call['id'],'status':'success','category':None,'artifact':message.artifact})
        return {'outcomes':tuple(outcomes)}
    workflow=StateGraph(RetrievalGraphState)
    workflow.add_node('prepare',prepare);workflow.add_node('tools',node);workflow.add_node('route',route)
    workflow.add_edge(START,'prepare');workflow.add_edge('prepare','tools');workflow.add_edge('tools','route');workflow.add_edge('route',END)
    return workflow.compile()
