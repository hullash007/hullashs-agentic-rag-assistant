"""Explicit startup-only opt-in. Disabled config never reads a key or builds a client."""
from .gemini_answer import GeminiAnswerProvider


def configured_answer_provider(settings):
    flag=settings.get('ANSWER_GENERATION_ENABLED','false')
    if flag not in ('true','false'):
        raise ValueError('ANSWER_GENERATION_ENABLED must be true or false')
    if flag=='false':
        return None
    if settings.get('ANSWER_PROVIDER')!='gemini':
        raise ValueError('explicit ANSWER_PROVIDER=gemini required')
    model=settings.get('ANSWER_MODEL','')
    if not model or len(model)>128 or any(not(c.isalnum() or c in '-._/') for c in model):
        raise ValueError('explicit valid ANSWER_MODEL required')
    key=settings.get('ANSWER_API_KEY','')
    if not key or not key.strip():
        raise ValueError('explicit ANSWER_API_KEY required')
    try:
        timeout=int(settings.get('ANSWER_TIMEOUT_MS','15000'))
        tokens=int(settings.get('ANSWER_MAX_OUTPUT_TOKENS','1024'))
    except (TypeError,ValueError):
        raise ValueError('invalid answer provider limits') from None
    if not 1000<=timeout<=60000 or not 1<=tokens<=1024:
        raise ValueError('invalid answer provider limits')
    return GeminiAnswerProvider.from_api_key(api_key=key,model=model,
        timeout_ms=timeout,max_output_tokens=tokens)
