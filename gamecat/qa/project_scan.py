"""QA całego projektu."""
from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Iterable

from gamecat.models.glossary import GlossaryEntry, GlossaryTerm
from gamecat.models.segment import Segment
from gamecat.qa.rules import QAIssue
from gamecat.qa.validator import validate_segment


@dataclass(frozen=True, slots=True)
class SegmentQAResult:
    """Problemy QA przypisane do jednego segmentu projektu."""

    segment: Segment
    issues: tuple[QAIssue, ...]


@dataclass(frozen=True, slots=True)
class ProjectQAReport:
    """Podsumowanie skanu QA całego projektu."""

    segment_count: int
    results: list[SegmentQAResult]

    @property
    def issue_segment_count(self) -> int:
        """Liczba segmentów z co najmniej jednym problemem."""
        return len(self.results)

    @property
    def issue_count(self) -> int:
        """Łączna liczba problemów we wszystkich segmentach."""
        return sum(len(result.issues) for result in self.results)


def scan_segments(
    segments: Iterable[Segment],
    glossary: Iterable[GlossaryTerm | GlossaryEntry] = (),
) -> ProjectQAReport:
    """Uruchom QA dla wszystkich segmentów (także z generatora) i zachowaj tylko te z problemami."""
    glossary_list = list(glossary)
    results: list[SegmentQAResult] = []
    count = 0
    for segment in segments:
        count += 1
        issues = validate_segment(segment.source, segment.target, glossary_list)
        if issues:
            results.append(SegmentQAResult(segment, tuple(issues)))
    return ProjectQAReport(count, results)
