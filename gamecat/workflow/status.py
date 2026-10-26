from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Mapping

from gamecat.models.segment import SegmentStatus


def confirmed_translation_status(status: SegmentStatus) -> SegmentStatus:
    """Promote a newly translated segment without downgrading later workflow states."""
    return SegmentStatus.TRANSLATED if status is SegmentStatus.NEW else status


def status_after_target_edit(status: SegmentStatus, before: str, after: str) -> SegmentStatus:
    """Invalidate previous review on a real manual edit; empty translations become NEW."""
    if before == after:
        return status
    if not after.strip():
        return SegmentStatus.NEW
    return SegmentStatus.TRANSLATED


@dataclass(frozen=True, slots=True)
class ProjectProgress:
    """Exclusive status counts plus cumulative workflow completion metrics."""

    new: int = 0
    translated: int = 0
    reviewed: int = 0
    approved: int = 0

    @classmethod
    def from_counts(cls, counts: Mapping[SegmentStatus, int]) -> 'ProjectProgress':
        return cls(
            new=int(counts.get(SegmentStatus.NEW, 0)),
            translated=int(counts.get(SegmentStatus.TRANSLATED, 0)),
            reviewed=int(counts.get(SegmentStatus.REVIEWED, 0)),
            approved=int(counts.get(SegmentStatus.APPROVED, 0)),
        )

    @property
    def total(self) -> int:
        return self.new + self.translated + self.reviewed + self.approved

    @property
    def translated_or_better(self) -> int:
        return self.translated + self.reviewed + self.approved

    @property
    def reviewed_or_better(self) -> int:
        return self.reviewed + self.approved

    @staticmethod
    def _percent(value: int, total: int) -> float:
        return 0.0 if total == 0 else round(value * 100.0 / total, 1)

    @property
    def translation_percent(self) -> float:
        return self._percent(self.translated_or_better, self.total)

    @property
    def review_percent(self) -> float:
        return self._percent(self.reviewed_or_better, self.total)

    @property
    def approval_percent(self) -> float:
        return self._percent(self.approved, self.total)
