import logging

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from backend.agents.graph import agent
from backend.services.llm import (
    LLMAuthenticationError,
    LLMConfigurationError,
    LLMProviderError,
    LLMQuotaError,
    LLMUnavailableError,
)

APP_TITLE = "Hullash's agentic rag assistant"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title=APP_TITLE,
    description="Agentic Enterprise RAG Assistant",
    version="0.1.0",
)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=10000)


class ChatResponse(BaseModel):
    answer: str


@app.get("/health")
def health():
    # Deliberately local-only: no provider creation, API key check or network call.
    return {
        "status": "healthy",
        "application": APP_TITLE,
        "version": "0.1.0",
    }


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    try:
        logger.info("Received chat request")
        result = agent.invoke({
            "message": request.message,
            "answer": "",
        })
        return ChatResponse(answer=result["answer"])

    except LLMQuotaError as error:
        logger.warning("Language model quota limit reached")
        raise HTTPException(
            status_code=429,
            detail="The AI service quota or rate limit was reached.",
        ) from error

    except LLMUnavailableError as error:
        logger.warning("Language model temporarily unavailable")
        raise HTTPException(
            status_code=503,
            detail="The AI service is temporarily unavailable.",
        ) from error

    except LLMAuthenticationError as error:
        logger.error("Language model authentication or permission failure")
        raise HTTPException(
            status_code=502,
            detail="The AI service rejected its configured credentials or permissions.",
        ) from error

    except LLMConfigurationError as error:
        logger.error("Language model configuration is incomplete")
        raise HTTPException(
            status_code=503,
            detail="The AI service is not configured.",
        ) from error

    except LLMProviderError as error:
        logger.error("Language model provider request failed")
        raise HTTPException(
            status_code=502,
            detail="The AI provider could not complete the request.",
        ) from error

    except RuntimeError as error:
        logger.error(
            "Agent configuration or execution error (exception_type=%s)",
            type(error).__name__,
        )
        raise HTTPException(
            status_code=503,
            detail="The AI service is not configured or available.",
        ) from error

    except Exception as error:
        logger.error(
            "Unexpected agent execution failure (exception_type=%s)",
            type(error).__name__,
        )
        raise HTTPException(
            status_code=502,
            detail="The AI agent could not complete the request.",
        )
