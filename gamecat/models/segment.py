"""Model segmentu (jednostki tłumaczenia) i statusów workflow."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


def _now() -> datetime:
    """Zwróć bieżący czas UTC (domyślna wartość pól dat)."""
    return datetime.now(timezone.utc)


class SegmentStatus(str, Enum):
    """Statusy workflow segmentu: nowy, przetłumaczony, zrecenzowany, zatwierdzony."""
    NEW = "NEW"
    TRANSLATED = "TRANSLATED"
    REVIEWED = "REVIEWED"
    APPROVED = "APPROVED"


@dataclass(slots=True)
class Segment:
    """Pojedyncza jednostka tłumaczenia: tekst źródłowy (Source) i tłumaczenie (Target).

    Pola ``target`` i ``status`` są właściwościami (``@property``) z setterami,
    które walidują typ i wartość oraz aktualizują znacznik ``updated_at``.
    """
    source: str
    position: int
    key: str | None = None
    comment: str = ""
    id: int | None = None
    project_id: int | None = None
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)
    ai_generated: bool = False
    _target: str = field(default="", repr=False)
    _status: SegmentStatus = field(default=SegmentStatus.NEW, repr=False)

    def __init__(self, source: str, position: int, key: str | None = None,
                 target: str = "", status: SegmentStatus | str = SegmentStatus.NEW,
                 comment: str = "", id: int | None = None, project_id: int | None = None,
                 created_at: datetime | None = None, updated_at: datetime | None = None,
                 ai_generated: bool = False):
        """Utwórz segment; Target i status przechodzą przez walidujące settery."""
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
        self.ai_generated = bool(ai_generated)

    @property
    def target(self) -> str:
        """Tekst tłumaczenia (Target)."""
        return self._target

    @target.setter
    def target(self, value: str) -> None:
        """Ustaw tłumaczenie po sprawdzeniu typu.

        Ręczna zmiana usuwa oznaczenie pochodzenia z AI i aktualizuje ``updated_at``.

        :raises TypeError: gdy wartość nie jest napisem.
        """
        if not isinstance(value, str):
            raise TypeError("target must be a string")
        self._target = value
        self.ai_generated = False  # manual edits invalidate the provenance mark
        self.updated_at = _now()

    @property
    def status(self) -> SegmentStatus:
        """Status workflow segmentu."""
        return self._status

    @status.setter
    def status(self, value: SegmentStatus | str) -> None:
        """Ustaw status, akceptując ``SegmentStatus`` lub jego nazwę tekstową.

        :raises ValueError: gdy nazwa statusu jest nieznana.
        """
        try:
            self._status = value if isinstance(value, SegmentStatus) else SegmentStatus(value)
        except ValueError as exc:
            raise ValueError(f"Invalid segment status: {value}") from exc
        self.updated_at = _now()
