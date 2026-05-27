"""
LLM Client Utilities - Centralized async LLM wrapper for xAI Grok
=================================================================

Single source of truth for all LLM calls in the system.
Uses local resilience helpers for automatic retry with exponential backoff and
cascade failure prevention.

Usage:
    from src.utils.llm_client import call_llm_async, call_llm_batch, call_llm_structured
    
    response = await call_llm_async("What is 2+2?")
    responses = await call_llm_batch(prompts, max_concurrent=8)
    result = await call_llm_structured(prompt, MyPydanticModel, max_retries=3)
"""

import asyncio
import logging

from src.core.exceptions import LLMError
from typing import Optional, List, Dict, Any, Type, TypeVar

import instructor
from openai import AsyncOpenAI
from pydantic import BaseModel

from src.core import get_settings
from src.utils.resilience import CircuitBreaker, async_retry

logger = logging.getLogger(__name__)

T = TypeVar('T', bound=BaseModel)

# Shared circuit breaker for xAI API endpoint
_xai_breaker = CircuitBreaker(failure_threshold=5, reset_timeout=60.0, name="xai-grok")

# Lazy-initialized shared client (created on first use)
_shared_client: Optional[AsyncOpenAI] = None


def _get_client() -> AsyncOpenAI:
    """Get or create the shared AsyncOpenAI client."""
    global _shared_client
    if _shared_client is None:
        settings = get_settings()
        _shared_client = AsyncOpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_host
        )
    return _shared_client


@async_retry(max_attempts=3, base_delay=1.0, max_delay=30.0)
async def call_llm_async(
    prompt: str,
    system_prompt: Optional[str] = None,
    model: Optional[str] = None,
    temperature: float = 0.1,
    max_tokens: Optional[int] = None,
    json_mode: bool = False
) -> str:
    """
    Call xAI Grok LLM asynchronously with automatic retry and circuit breaker.
    
    Args:
        prompt: User prompt text
        system_prompt: Optional system prompt
        model: LLM model name (default: REASONING_LLM_NAME)
        temperature: Sampling temperature (default: 0.1)
        max_tokens: Maximum tokens in response
        json_mode: Force JSON output mode
    
    Returns:
        LLM response text
    """
    settings = get_settings()
    if model is None:
        model = settings.reasoning_llm_name
    
    client = _get_client()
    
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    
    call_kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature
    }
    
    if max_tokens:
        call_kwargs["max_tokens"] = max_tokens
    
    if json_mode:
        call_kwargs["response_format"] = {"type": "json_object"}
    
    # Circuit breaker wraps the actual API call
    _xai_breaker._acquire_permission()
    try:
        response = await client.chat.completions.create(**call_kwargs)
        _xai_breaker.record_success()
        return response.choices[0].message.content
    except Exception as e:
        _xai_breaker.record_failure()
        raise LLMError(f"LLM API call failed", cause=e, model=model)


# ═══════════════════════════════════════════════════════════════════════════════
# REVIEWER role — full-volume single-voice rewriting (Phase 1.0)
# ═══════════════════════════════════════════════════════════════════════════════
# Sits OUTSIDE LightRAG's role_llm_configs (extract/query/keyword/vlm) because
# reviewer passes operate on assembled volumes, not on chunks/queries. Uses the
# reasoning model with a much larger output budget and longer timeout to allow
# it to ingest a full proposal volume and emit a unified-voice rewrite in a
# single call.
# ═══════════════════════════════════════════════════════════════════════════════
@async_retry(max_attempts=2, base_delay=2.0, max_delay=60.0)
async def call_llm_reviewer(
    prompt: str,
    system_prompt: Optional[str] = None,
    model: Optional[str] = None,
    temperature: float = 0.2,
    max_tokens: int = 180000,
    timeout: float = 1800.0,
) -> str:
    """
    Call the reviewer LLM for full-volume single-voice rewriting.

    Distinct from `call_llm_async`:
      - Defaults to the reasoning model (best for synthesis/judgment).
      - 180k max output tokens (vs. 128k default) to fit a full proposal volume.
      - 30 min timeout (vs. default ~10 min) for long synthesis passes.
      - Lower retry count (2 vs. 3) — reviewer calls are expensive.

    Args:
        prompt: Full assembled volume + review instructions.
        system_prompt: Optional reviewer persona / style guide.
        model: Override (default: settings.reasoning_llm_name).
        temperature: Slightly higher than extraction (0.2) for prose smoothing.
        max_tokens: Output budget (default 180000).
        timeout: Per-call timeout in seconds (default 1800).

    Returns:
        Rewritten volume text.
    """
    settings = get_settings()
    if model is None:
        model = settings.reasoning_llm_name

    client = _get_client()

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    call_kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "timeout": timeout,
    }

    _xai_breaker._acquire_permission()
    try:
        response = await client.chat.completions.create(**call_kwargs)
        _xai_breaker.record_success()
        return response.choices[0].message.content
    except Exception as e:
        _xai_breaker.record_failure()
        raise LLMError("Reviewer LLM API call failed", cause=e, model=model)


async def call_llm_batch(
    prompts: List[str],
    system_prompt: Optional[str] = None,
    model: Optional[str] = None,
    temperature: float = 0.1,
    max_concurrent: Optional[int] = None
) -> List[str]:
    """
    Call LLM with multiple prompts in parallel (batched).
    
    Uses asyncio.Semaphore for rate limiting based on MAX_ASYNC env var.
    
    Args:
        prompts: List of user prompts
        system_prompt: Optional system prompt (same for all)
        model: LLM model name
        temperature: Sampling temperature
        max_concurrent: Maximum concurrent API calls (default: from MAX_ASYNC env var)
    
    Returns:
        List of LLM responses (same order as prompts)
    """
    settings = get_settings()
    if max_concurrent is None:
        max_concurrent = settings.get_effective_post_processing_max_async()
    
    # Create semaphore for rate limiting
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def call_with_semaphore(prompt: str) -> str:
        async with semaphore:
            return await call_llm_async(
                prompt=prompt,
                system_prompt=system_prompt,
                model=model,
                temperature=temperature
            )
    
    # Execute all prompts in parallel (up to max_concurrent)
    tasks = [call_with_semaphore(prompt) for prompt in prompts]
    responses = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Convert exceptions to error messages
    results = []
    for i, response in enumerate(responses):
        if isinstance(response, Exception):
            logger.error(f"Batch prompt {i+1}/{len(prompts)} failed: {response}")
            results.append(f"ERROR: {str(response)}")
        else:
            results.append(response)
    
    return results


async def call_llm_structured(
    prompt: str,
    response_model: Type[T],
    system_prompt: Optional[str] = None,
    model: Optional[str] = None,
    temperature: float = 0.1,
    max_tokens: Optional[int] = None,
    max_retries: int = 3
) -> T:
    """
    Call LLM with Pydantic schema enforcement using Instructor library.
    
    Uses Instructor's MD_JSON mode for automatic JSON extraction + Pydantic validation.
    Instructor handles retries with error feedback internally.
    """
    settings = get_settings()
    if model is None:
        model = settings.reasoning_llm_name
    
    if max_tokens is None:
        max_tokens = settings.llm_max_output_tokens
    
    client = instructor.from_openai(_get_client(), mode=instructor.Mode.MD_JSON)
    
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    
    result = await client.chat.completions.create(
        model=model,
        response_model=response_model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        max_retries=max_retries,
    )
    
    return result


def get_llm_config() -> Dict[str, Any]:
    """
    Get current LLM configuration from centralized settings.
    Useful for logging configuration at startup.
    """
    settings = get_settings()
    return {
        "model": settings.reasoning_llm_name,
        "extraction_model": settings.extraction_llm_name,
        "post_processing_model": settings.post_processing_llm_name,
        "api_host": settings.llm_host,
        "api_key_set": bool(settings.llm_api_key),
        "llm_max_async": settings.get_effective_llm_max_async(),
        "post_processing_max_async": settings.get_effective_post_processing_max_async(),
        "max_retries": settings.llm_max_retries
    }

