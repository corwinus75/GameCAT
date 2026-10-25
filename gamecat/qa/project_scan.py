from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Iterable

from gamecat.models.glossary import GlossaryEntry
from gamecat.models.segment import Segment
from gamecat.qa.rules import QAIssue
from gamecat.qa.validator import validate_segment


@dataclass(frozen=True, slots=True)
class SegmentQAResult:
    """QA issues assigned to one project segment."""

    segment: Segment
    issues: tuple[QAIssue, ...]


@dataclass(frozen=True, slots=True)
class ProjectQAReport:
    """Summary of a full-project QA scan."""

    segment_count: int
    results: list[SegmentQAResult]

    @property
    def issue_segment_count(self) -> int:
        return len(self.results)

    @property
    def issue_count(self) -> int:
        return sum(len(result.issues) for result in self.results)


def scan_segments(
    segments: Iterable[Segment],
    glossary: Iterable[GlossaryEntry] = (),
) -> ProjectQAReport:
    """Run QA for all segments and retain only segments that have issues."""
    segment_list = list(segments)
    glossary_list = list(glossary)
    results: list[SegmentQAResult] = []
    for segment in segment_list:
        issues = validate_segment(segment.source, segment.target, glossary_list)
        if issues:
            results.append(SegmentQAResult(segment, tuple(issues)))
    return ProjectQAReport(len(segment_list), results)
