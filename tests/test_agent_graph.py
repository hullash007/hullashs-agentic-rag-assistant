from types import SimpleNamespace

import pytest

from backend.agents import graph
from backend.services.llm import LLMConfigurationError


def test_agent_graph_success(monkeypatch):
    class FakeProvider:
        def generate(self, prompt):
            assert prompt == "Explain RAG"
            return "This is a simulated Gemini response."

    monkeypatch.setattr(graph, "get_provider", lambda: FakeProvider())

    result = graph.agent.invoke({"message": "Explain RAG", "answer": ""})

    assert result["answer"] == "This is a simulated Gemini response."


def test_agent_graph_missing_api_key(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", " ")
    monkeypatch.setenv("GEMINI_MODEL", "test-model")

    with pytest.raises(LLMConfigurationError, match="GEMINI_API_KEY"):
        graph.agent.invoke({"message": "Hello", "answer": ""})


def test_agent_graph_missing_model(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_MODEL", "")

    with pytest.raises(LLMConfigurationError, match="GEMINI_MODEL"):
        graph.agent.invoke({"message": "Hello", "answer": ""})


def test_mock_provider_is_default(monkeypatch):
    from backend.services.llm import get_provider, MockLLMProvider

    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "")

    provider = get_provider()

    assert isinstance(provider, MockLLMProvider)
    assert provider.generate("offline test") == "Mock response: offline test"
