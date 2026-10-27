"""Wyjątki aplikacji – kontrolowane błędy zgłaszane użytkownikowi."""
class GameCATError(Exception):
    """Klasa bazowa kontrolowanych błędów aplikacji."""


class ImportFormatError(GameCATError):
    """Plik importu nie daje się zdekodować ani sparsować."""


class DatabaseError(GameCATError):
    """Operacja na bazie SQLite nie powiodła się (oryginał w ``__cause__``)."""


class NoProjectError(GameCATError, RuntimeError):
    """Operacja wymaga otwartego projektu.

    Dziedziczy także po ``RuntimeError`` dla zgodności z wcześniejszym API.
    """
