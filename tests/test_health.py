from fastapi.testclient import TestClient

from apps.api.main import APP_TITLE, app

client = TestClient(app)


def test_health_endpoint():
    response = client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["application"] == "Hullash's agentic rag assistant"
    assert data["version"] == "0.1.0"


def test_health_does_not_invoke_agent(monkeypatch):
    from apps.api import main

    def forbidden_invoke(state):
        raise AssertionError("Health must not invoke the agent.")

    monkeypatch.setattr(main.agent, "invoke", forbidden_invoke)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["application"] == APP_TITLE


def test_application_title_is_exact():
    assert app.title == "Hullash's agentic rag assistant"
