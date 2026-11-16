import json
from typing import Any

from google import genai
from google.genai import types
from google.genai.errors import APIError

from backend.services.llm import (
    LLMAuthenticationError,
    LLMProviderError,
    LLMQuotaError,
    LLMUnavailableError,
)


def _error_details(error: APIError) -> str:
    """Read provider error metadata without exposing credentials."""
    payload: Any = getattr(error, "response_json", None)

    try:
        return json.dumps(payload, default=str).lower()
    except (TypeError, ValueError):
        return str(payload).lower()


def classify_api_error(error: APIError):
    """Translate Google API errors into stable application exceptions."""
    code = getattr(error, "code", None)
    details = _error_details(error)

    if code in (401, 403) or any(
        marker in details
        for marker in ("unauthenticated", "permission_denied", "api key not valid")
    ):
        return LLMAuthenticationError(
            "Gemini rejected the project credentials or permissions."
        )

    if code == 429 or any(
        marker in details
        for marker in ("resource_exhausted", "quota", "rate limit")
    ):
        return LLMQuotaError("Gemini quota or rate limit was reached.")

    if code in (500, 502, 503, 504) or any(
        marker in details
        for marker in ("unavailable", "high demand", "overloaded")
    ):
        return LLMUnavailableError("Gemini is temporarily unavailable.")

    return LLMProviderError("Gemini returned an API error.")


class GeminiProvider:
    """Google Gen AI SDK 3.x adapter. Construction makes no model request."""

    def __init__(
        self,
        api_key: str,
        model: str,
        timeout_ms: int = 15000,
        max_output_tokens: int = 128,
    ):
        if not api_key:
            raise ValueError("A Gemini API key is required.")

        if not model:
            raise ValueError("A Gemini model name is required.")

        if not 1000 <= timeout_ms <= 60000:
            raise ValueError("Timeout must be between 1000 and 60000 milliseconds.")

        if not 1 <= max_output_tokens <= 1024:
            raise ValueError("Output token limit must be between 1 and 1024.")

        self.model = model
        self.max_output_tokens = max_output_tokens

        http_options = types.HttpOptions(
            timeout=timeout_ms,
            retry_options=types.HttpRetryOptions(attempts=1),
        )

        self.client = genai.Client(
            api_key=api_key,
            http_options=http_options,
        )

    def generate(self, prompt: str) -> str:
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    max_output_tokens=self.max_output_tokens,
                ),
            )
        except APIError as error:
            raise classify_api_error(error) from error
        except Exception as error:
            raise LLMProviderError(
                "The Gemini request failed before a response was received."
            ) from error

        answer = getattr(response, "text", None)

        if not answer:
            raise LLMProviderError("Gemini returned an empty response.")

        return answer
