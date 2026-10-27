"""Model projektu tłumaczeniowego."""
from dataclasses import dataclass, field
from datetime import datetime, timezone


def _now() -> datetime:
    """Zwróć bieżący czas UTC (domyślna wartość pól dat)."""
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class Project:
    """Metadane projektu: nazwa, para językowa i format źródłowy."""
    name: str
    source_language: str
    target_language: str
    source_format: str
    id: int | None = None
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)
