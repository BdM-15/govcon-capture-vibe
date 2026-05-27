"""Small async retry and circuit-breaker helpers for LLM calls."""

from __future__ import annotations

import asyncio
import functools
import time
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar


ResultT = TypeVar("ResultT")


class CircuitBreakerOpenError(RuntimeError):
    """Raised when a circuit breaker is still cooling down."""


class CircuitBreaker:
    def __init__(
        self,
        *,
        failure_threshold: int = 5,
        reset_timeout: float = 60.0,
        name: str = "circuit-breaker",
    ) -> None:
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.name = name
        self.failure_count = 0
        self.last_failure_time: float | None = None

    def _acquire_permission(self) -> None:
        if self.failure_count < self.failure_threshold:
            return
        if self.last_failure_time is None:
            return
        if time.monotonic() - self.last_failure_time >= self.reset_timeout:
            return
        raise CircuitBreakerOpenError(f"Circuit breaker '{self.name}' is open")

    def record_success(self) -> None:
        self.failure_count = 0
        self.last_failure_time = None

    def record_failure(self) -> None:
        self.failure_count += 1
        self.last_failure_time = time.monotonic()


def async_retry(
    *,
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
) -> Callable[[Callable[..., Awaitable[ResultT]]], Callable[..., Awaitable[ResultT]]]:
    def decorate(func: Callable[..., Awaitable[ResultT]]) -> Callable[..., Awaitable[ResultT]]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> ResultT:
            attempt = 1
            while True:
                try:
                    return await func(*args, **kwargs)
                except Exception:
                    if attempt >= max_attempts:
                        raise
                    delay = min(max_delay, base_delay * (2 ** (attempt - 1)))
                    await asyncio.sleep(delay)
                    attempt += 1

        return wrapper

    return decorate