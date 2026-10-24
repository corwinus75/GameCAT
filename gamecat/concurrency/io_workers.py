from concurrent.futures import Future, ThreadPoolExecutor
from collections.abc import Callable
from typing import Any


class IOWorkerPool:
    """Small ThreadPoolExecutor wrapper for I/O-bound application tasks."""
    def __init__(self, max_workers: int = 4):
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix='gamecat-io')

    def submit(self, callable_: Callable[..., Any], *args: Any, **kwargs: Any) -> Future[Any]:
        return self._executor.submit(callable_, *args, **kwargs)

    def close(self) -> None:
        self._executor.shutdown(wait=True)
