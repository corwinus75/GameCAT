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

