"""Reguły przejść statusów i liczniki postępu projektu."""
from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Mapping

from gamecat.models.segment import SegmentStatus


def confirmed_translation_status(status: SegmentStatus) -> SegmentStatus:
    """Podnieś nowy segment do ``TRANSLATED``, nie obniżając późniejszych statusów."""
    return SegmentStatus.TRANSLATED if status is SegmentStatus.NEW else status


def status_after_target_edit(status: SegmentStatus, before: str, after: str) -> SegmentStatus:
    """Ustal status po ręcznej edycji: zmiana unieważnia recenzję, pusty Target daje ``NEW``."""
    if before == after:
        return status
    if not after.strip():
        return SegmentStatus.NEW
    return SegmentStatus.TRANSLATED


@dataclass(frozen=True, slots=True)
class ProjectProgress:
    """Rozłączne liczności statusów oraz skumulowane wskaźniki postępu workflow."""

    new: int = 0
    translated: int = 0
    reviewed: int = 0
    approved: int = 0

    @classmethod
    def from_counts(cls, counts: Mapping[SegmentStatus, int]) -> 'ProjectProgress':
        """Utwórz obiekt postępu ze słownika liczności statusów (alternatywny konstruktor)."""
        return cls(
            new=int(counts.get(SegmentStatus.NEW, 0)),
            translated=int(counts.get(SegmentStatus.TRANSLATED, 0)),
            reviewed=int(counts.get(SegmentStatus.REVIEWED, 0)),
            approved=int(counts.get(SegmentStatus.APPROVED, 0)),
        )

    @property
    def total(self) -> int:
        """Łączna liczba segmentów."""
        return self.new + self.translated + self.reviewed + self.approved

    @property
    def translated_or_better(self) -> int:
        """Liczba segmentów co najmniej przetłumaczonych."""
        return self.translated + self.reviewed + self.approved

    @property
    def reviewed_or_better(self) -> int:
        """Liczba segmentów co najmniej zrecenzowanych."""
        return self.reviewed + self.approved

    @staticmethod
    def _percent(value: int, total: int) -> float:
        """Zwróć udział procentowy zaokrąglony do 0,1 (0 dla pustego projektu)."""
        return 0.0 if total == 0 else round(value * 100.0 / total, 1)

    @property
    def translation_percent(self) -> float:
        """Procent segmentów przetłumaczonych lub dalej w workflow."""
        return self._percent(self.translated_or_better, self.total)

    @property
    def review_percent(self) -> float:
        """Procent segmentów zrecenzowanych lub zatwierdzonych."""
        return self._percent(self.reviewed_or_better, self.total)

    @property
    def approval_percent(self) -> float:
        """Procent segmentów zatwierdzonych."""
        return self._percent(self.approved, self.total)
