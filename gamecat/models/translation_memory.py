from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass(slots=True)
class TranslationMemoryEntry:
    """A reusable bilingual translation pair."""
    source: str
    target: str
    source_language: str
    target_language: str
    origin_project: str | None = None
    id: int | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
