"""Model wpisu pamięci tłumaczeniowej (TM)."""
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass(slots=True)
class TranslationMemoryEntry:
    """Para dwujęzyczna Source/Target wielokrotnego użytku wraz z parą języków."""
    source: str
    target: str
    source_language: str
    target_language: str
    origin_project: str | None = None
    id: int | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
