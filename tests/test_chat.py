from fastapi.testclient import TestClient

from apps.api import main
from backend.services.llm import (
    LLMQuotaError,
    LLMUnavailableError,
)

client = TestClient(main.app)


def test_chat_success(monkeypatch):
    def fake_invoke(state):
        assert state["message"] == "Hello agent"
        return {"message": "Hello agent", "answer": "Hello! How can I help?"}

    monkeypatch.setattr(main.agent, "invoke", fake_invoke)

    response = client.post("/chat", json={"message": "Hello agent"})

    assert response.status_code == 200
    assert response.json() == {"answer": "Hello! How can I help?"}


def test_chat_configuration_error(monkeypatch):
    def fake_invoke(state):
        raise RuntimeError("Missing configuration")

    monkeypatch.setattr(main.agent, "invoke", fake_invoke)

    response = client.post("/chat", json={"message": "Hello"})

    assert response.status_code == 503


def test_chat_unexpected_error(monkeypatch):
    def fake_invoke(state):
        raise ValueError("Internal test error")

    monkeypatch.setattr(main.agent, "invoke", fake_invoke)

    response = client.post("/chat", json={"message": "Hello"})

    assert response.status_code == 502


def test_chat_rejects_empty_message():
    response = client.post("/chat", json={"message": ""})
    assert response.status_code == 422


def test_chat_rejects_missing_message():
    response = client.post("/chat", json={})
    assert response.status_code == 422


def test_chat_rejects_oversized_message():
    response = client.post("/chat", json={"message": "A" * 10001})
    assert response.status_code == 422


def test_chat_maps_quota_error_to_429(monkeypatch):
    def fake_invoke(state):
        raise LLMQuotaError("test quota")

    monkeypatch.setattr(main.agent, "invoke", fake_invoke)

    response = client.post("/chat", json={"message": "Hello"})

    assert response.status_code == 429
    assert "quota" in response.json()["detail"].lower()


def test_chat_maps_unavailable_error_to_503(monkeypatch):
    def fake_invoke(state):
        raise LLMUnavailableError("test unavailable")

    monkeypatch.setattr(main.agent, "invoke", fake_invoke)

    response = client.post("/chat", json={"message": "Hello"})

    assert response.status_code == 503
    assert "unavailable" in response.json()["detail"].lower()
