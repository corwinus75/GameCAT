"""Pula wątków dla zadań I/O-bound (import, eksport, zapytania do bazy)."""
from concurrent.futures import Future, ThreadPoolExecutor
from collections.abc import Callable
from typing import Any


class IOWorkerPool:
    """Cienka nakładka na ``ThreadPoolExecutor`` dla zadań I/O aplikacji."""

    def __init__(self, max_workers: int = 4):
        """Utwórz pulę z *max_workers* nazwanymi wątkami ``gamecat-io``."""
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix='gamecat-io')

    def submit(self, callable_: Callable[..., Any], *args: Any, **kwargs: Any) -> Future[Any]:
        """Zleć wykonanie funkcji w puli i zwróć ``Future`` z wynikiem."""
        return self._executor.submit(callable_, *args, **kwargs)

    def close(self) -> None:
        """Zamknij pulę, czekając na zakończenie zleconych zadań."""
        self._executor.shutdown(wait=True)
