from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from backend.services.llm import get_provider


class AgentState(TypedDict):
    message: str
    answer: str


def generate_answer(state: AgentState) -> dict:
    provider = get_provider()
    answer = provider.generate(state["message"])

    if not answer:
        raise RuntimeError("The language model returned an empty answer.")

    return {"answer": answer}


workflow = StateGraph(AgentState)
workflow.add_node("generate_answer", generate_answer)
workflow.add_edge(START, "generate_answer")
workflow.add_edge("generate_answer", END)

agent = workflow.compile()
