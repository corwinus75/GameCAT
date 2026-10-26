class GameCATError(Exception):
    """Base class for controlled application errors."""


class ImportFormatError(GameCATError):
    """Raised when an import file cannot be parsed or decoded."""


class DatabaseError(GameCATError):
    """Raised when a database operation fails."""


class NoProjectError(GameCATError, RuntimeError):
    """Raised when an operation requires an open project.

    Dziedziczy także po ``RuntimeError`` dla zgodności z wcześniejszym API.
    """
