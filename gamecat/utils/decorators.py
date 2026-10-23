from __future__ import annotations
import functools
import time
from collections.abc import Callable
from typing import Any, ParamSpec, TypeVar

P = ParamSpec('P')
R = TypeVar('R')


def measure_time(func: Callable[P, R]) -> Callable[P, R]:
    """Measure and print function execution time while preserving metadata."""
    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        start = time.perf_counter()
        try:
            return func(*args, **kwargs)
        finally:
            elapsed = time.perf_counter() - start
            print(f"[{func.__name__}] {elapsed:.6f} s")
    return wrapper


def retry(attempts: int = 3, delay: float = 0.0):
    """Retry a function up to *attempts* times before re-raising the last error."""
    if attempts < 1:
        raise ValueError('attempts must be >= 1')
    if delay < 0:
        raise ValueError('delay must be >= 0')

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            last: Exception | None = None
            for attempt in range(attempts):
                try:
                    return func(*args, **kwargs)
                except Exception as exc:  # retry is intentionally generic
                    last = exc
                    if attempt + 1 < attempts and delay:
                        time.sleep(delay)
            assert last is not None
            raise last
        return wrapper
    return decorator


def requires_project(method: Callable[P, R]) -> Callable[P, R]:
    """Guard methods that require ``self.current_project``."""
    @functools.wraps(method)
    def wrapper(self: Any, *args: Any, **kwargs: Any) -> R:
        if getattr(self, 'current_project', None) is None:
            raise RuntimeError('No project is open')
        return method(self, *args, **kwargs)
    return wrapper  # type: ignore[return-value]
