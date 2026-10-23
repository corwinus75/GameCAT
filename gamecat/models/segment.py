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
    """Single source/target translation unit."""
    source: str
    position: int
    key: str | None = None
    comment: str = ""
    id: int | None = None
    project_id: int | None = None
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)
    _target: str = field(default="", repr=False)
    _status: SegmentStatus = field(default=SegmentStatus.NEW, repr=False)

    def __init__(self, source: str, position: int, key: str | None = None,
                 target: str = "", status: SegmentStatus | str = SegmentStatus.NEW,
                 comment: str = "", id: int | None = None, project_id: int | None = None,
                 created_at: datetime | None = None, updated_at: datetime | None = None):
        self.source = source
        self.position = position
        self.key = key
        self.comment = comment
        self.id = id
        self.project_id = project_id
        self.created_at = created_at or _now()
        self.updated_at = updated_at or _now()
        self._target = ""
        self._status = SegmentStatus.NEW
        self.target = target
        self.status = status

    @property
    def target(self) -> str:
        """Translated text."""
        return self._target

    @target.setter
    def target(self, value: str) -> None:
        if not isinstance(value, str):
            raise TypeError("target must be a string")
        self._target = value
        self.updated_at = _now()

    @property
    def status(self) -> SegmentStatus:
        """Workflow status."""
        return self._status

    @status.setter
    def status(self, value: SegmentStatus | str) -> None:
        try:
            self._status = value if isinstance(value, SegmentStatus) else SegmentStatus(value)
        except ValueError as exc:
            raise ValueError(f"Invalid segment status: {value}") from exc
        self.updated_at = _now()
