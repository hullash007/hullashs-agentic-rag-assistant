from typing import Protocol


class LLMError(Exception):
    """Base class for application-level language model errors."""


class LLMConfigurationError(LLMError):
    pass


class LLMUnavailableError(LLMError):
    pass


class LLMQuotaError(LLMError):
    pass


class LLMAuthenticationError(LLMError):
    pass


class LLMProviderError(LLMError):
    pass


class LLMProvider(Protocol):
    def generate(self, prompt: str) -> str:
        ...


class MockLLMProvider:
    """Deterministic offline provider. Never contacts an external service."""

    def generate(self, prompt: str) -> str:
        return f"Mock response: {prompt}"


def get_provider() -> LLMProvider:
    """Create the configured provider only when a chat operation needs it."""
    from backend.config import get_settings

    settings = get_settings()

    if settings.llm_provider == "mock":
        return MockLLMProvider()

    if settings.llm_provider == "gemini":
        if not settings.gemini_api_key:
            raise LLMConfigurationError("GEMINI_API_KEY is not configured.")

        if not settings.gemini_model:
            raise LLMConfigurationError("GEMINI_MODEL is not configured.")

        from backend.services.gemini import GeminiProvider

        return GeminiProvider(
            api_key=settings.gemini_api_key,
            model=settings.gemini_model,
            timeout_ms=settings.gemini_timeout_ms,
            max_output_tokens=settings.gemini_max_output_tokens,
        )

    raise LLMConfigurationError("Unsupported language model provider.")
