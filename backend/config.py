import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    llm_provider: str
    gemini_api_key: str
    gemini_model: str
    gemini_timeout_ms: int
    gemini_max_output_tokens: int


def get_settings() -> Settings:
    """Read configuration when needed, without making external requests."""
    provider = os.getenv("LLM_PROVIDER", "mock").strip().lower()

    if provider not in {"mock", "gemini"}:
        raise ValueError("LLM_PROVIDER must be mock or gemini.")

    try:
        timeout_ms = int(os.getenv("GEMINI_TIMEOUT_MS", "15000"))
        max_tokens = int(os.getenv("GEMINI_MAX_OUTPUT_TOKENS", "128"))
    except ValueError as error:
        raise ValueError("Gemini timeout and output limit must be integers.") from error

    if not 1000 <= timeout_ms <= 60000:
        raise ValueError("GEMINI_TIMEOUT_MS must be between 1000 and 60000.")

    if not 1 <= max_tokens <= 1024:
        raise ValueError("GEMINI_MAX_OUTPUT_TOKENS must be between 1 and 1024.")

    return Settings(
        llm_provider=provider,
        gemini_api_key=os.getenv("GEMINI_API_KEY", "").strip(),
        gemini_model=os.getenv("GEMINI_MODEL", "").strip(),
        gemini_timeout_ms=timeout_ms,
        gemini_max_output_tokens=max_tokens,
    )
