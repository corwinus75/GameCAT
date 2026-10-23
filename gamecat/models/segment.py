from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


def _now() -> datetime:
    return datetime.now(timezone.utc)


class SegmentStatus(str, Enum):
    NEW = "NEW"
    TRANSLATED = "TRANSLATED"
    REVIEWED = "REVIEWED"
    APPROVED = "APPROVED"


@dataclass(slots=True)
class Segment:
    """Wersja początkowa: proste pola, bez właściwości i walidacji setterów."""
    source: str
    position: int
    key: str | None = None
    target: str = ""
    status: SegmentStatus | str = SegmentStatus.NEW
    comment: str = ""
    id: int | None = None
    project_id: int | None = None
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)

    def __post_init__(self):
        # W bazie status jest tekstem; ujednolicamy go do enum.
        self.status = SegmentStatus(self.status)
