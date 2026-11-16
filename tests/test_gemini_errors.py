from types import SimpleNamespace

import pytest
from google.genai.errors import APIError

from backend.services import gemini
from backend.services.llm import (
    LLMAuthenticationError,
    LLMProviderError,
    LLMQuotaError,
    LLMUnavailableError,
)


def make_api_error(code, status, message):
    return APIError(
        code,
        {
            "error": {
                "code": code,
                "status": status,
                "message": message,
            }
        },
    )


@pytest.mark.parametrize(
    ("code", "status", "message", "expected"),
    [
        (503, "UNAVAILABLE", "high demand", LLMUnavailableError),
        (429, "RESOURCE_EXHAUSTED", "quota exceeded", LLMQuotaError),
        (403, "PERMISSION_DENIED", "permission denied", LLMAuthenticationError),
        (400, "INVALID_ARGUMENT", "invalid request", LLMProviderError),
    ],
)
def test_api_error_classification(code, status, message, expected):
    error = make_api_error(code, status, message)

    classified = gemini.classify_api_error(error)

    assert isinstance(classified, expected)


def test_gemini_provider_uses_bounded_timeout_and_no_retries(monkeypatch):
    captured = {}

    class FakeClient:
        def __init__(self, api_key, http_options):
            captured["api_key"] = api_key
            captured["http_options"] = http_options
            self.models = SimpleNamespace(
                generate_content=lambda **kwargs: SimpleNamespace(text="mocked")
            )

        def close(self):
            pass

    monkeypatch.setattr(gemini.genai, "Client", FakeClient)

    provider = gemini.GeminiProvider(
        api_key="test-only-key",
        model="test-model",
        timeout_ms=15000,
        max_output_tokens=128,
    )

    options = captured["http_options"]

    assert options.timeout == 15000
    assert options.retry_options.attempts == 1
    assert provider.max_output_tokens == 128
    assert provider.generate("test prompt") == "mocked"


def test_gemini_provider_maps_api_error_without_retry(monkeypatch):
    calls = {"count": 0}

    class FakeClient:
        def __init__(self, api_key, http_options):
            self.models = SimpleNamespace(
                generate_content=self.generate_content
            )

        def generate_content(self, **kwargs):
            calls["count"] += 1
            raise make_api_error(503, "UNAVAILABLE", "high demand")

        def close(self):
            pass

    monkeypatch.setattr(gemini.genai, "Client", FakeClient)

    provider = gemini.GeminiProvider(
        api_key="test-only-key",
        model="test-model",
    )

    with pytest.raises(LLMUnavailableError):
        provider.generate("synthetic test")

    assert calls["count"] == 1


def test_gemini_provider_rejects_empty_response(monkeypatch):
    class FakeClient:
        def __init__(self, api_key, http_options):
            self.models = SimpleNamespace(
                generate_content=lambda **kwargs: SimpleNamespace(text=None)
            )

        def close(self):
            pass

    monkeypatch.setattr(gemini.genai, "Client", FakeClient)

    provider = gemini.GeminiProvider(
        api_key="test-only-key",
        model="test-model",
    )

    with pytest.raises(LLMProviderError, match="empty response"):
        provider.generate("synthetic test")
