"""Własne dekoratory GameCAT.

* ``measure_time`` – dekorator funkcji (bez parametrów), loguje czas wykonania.
* ``retry`` – fabryka dekoratorów (dekorator z parametrami) ponawiająca
  operacje kończące się błędem przejściowym, np. zablokowaną bazą SQLite.
* ``requires_project`` – dekorator metody korzystający ze stanu ``self``.
"""
from __future__ import annotations

import functools
import logging
import time
from collections.abc import Callable
from typing import Concatenate, ParamSpec, TypeVar

from gamecat.exceptions import NoProjectError

P = ParamSpec('P')
R = TypeVar('R')
S = TypeVar('S')

timing_logger = logging.getLogger('gamecat.timing')
retry_logger = logging.getLogger('gamecat.retry')


def measure_time(func: Callable[P, R]) -> Callable[P, R]:
    """Zmierz czas wykonania funkcji i zapisz go w logu ``gamecat.timing``.

    Czas jest logowany również wtedy, gdy funkcja zgłosi wyjątek. Dzięki
    ``functools.wraps`` zachowane są nazwa i docstring oryginału.
    """
    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        start = time.perf_counter()
        try:
            return func(*args, **kwargs)
        finally:
            elapsed = time.perf_counter() - start
            timing_logger.info('%s: %.4f s', func.__qualname__, elapsed)
    return wrapper


def retry(
    attempts: int = 3,
    delay: float = 0.0,
    exceptions: tuple[type[BaseException], ...] = (Exception,),
    when: Callable[[BaseException], bool] | None = None,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Ponawiaj wywołanie maksymalnie *attempts* razy.

    :param attempts: łączna liczba prób (co najmniej 1).
    :param delay: odstęp między próbami w sekundach.
    :param exceptions: typy wyjątków, które kwalifikują się do ponowienia.
    :param when: opcjonalny predykat zawężający ponawianie do błędów
        przejściowych (np. tylko ``database is locked``). Pozostałe wyjątki
        są zgłaszane od razu.
    """
    if attempts < 1:
        raise ValueError('attempts must be >= 1')
    if delay < 0:
        raise ValueError('delay must be >= 0')

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            for attempt in range(1, attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as exc:
                    if when is not None and not when(exc):
                        raise
                    if attempt == attempts:
                        raise
                    retry_logger.warning(
                        '%s: próba %d/%d nieudana (%s), ponawiam',
                        func.__qualname__, attempt, attempts, exc,
                    )
                    if delay:
                        time.sleep(delay)
            raise AssertionError('unreachable')  # pragma: no cover
        return wrapper
    return decorator


def requires_project(
    method: Callable[Concatenate[S, P], R],
) -> Callable[Concatenate[S, P], R]:
    """Blokuj wywołanie metody, gdy w obiekcie nie ma otwartego projektu.

    Dekorator odczytuje stan instancji (``self.current_project`` oraz
    opcjonalnie ``self.project_service``) i zgłasza ``NoProjectError``.
    """
    @functools.wraps(method)
    def wrapper(self: S, *args: P.args, **kwargs: P.kwargs) -> R:
        if getattr(self, 'current_project', None) is None:
            raise NoProjectError('No project is open')
        if hasattr(self, 'project_service') and getattr(self, 'project_service') is None:
            raise NoProjectError('No project is open')
        return method(self, *args, **kwargs)
    return wrapper


def is_transient_sqlite_error(exc: BaseException) -> bool:
    """Czy błąd SQLite jest przejściowy (blokada pliku przez inny proces)?"""
    message = str(exc).casefold()
    return 'locked' in message or 'busy' in message


__all__ = ['measure_time', 'retry', 'requires_project', 'is_transient_sqlite_error']
