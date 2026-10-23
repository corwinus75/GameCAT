from dataclasses import dataclass, field
from datetime import datetime, timezone


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class Project:
    """Translation project metadata."""
    name: str
    source_language: str
    target_language: str
    source_format: str
    id: int | None = None
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)
