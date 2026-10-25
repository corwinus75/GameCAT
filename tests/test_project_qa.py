from gamecat.models.glossary import GlossaryEntry
from gamecat.models.segment import Segment
from gamecat.qa.project_scan import scan_segments


def test_scan_segments_returns_only_segments_with_issues_and_counts_them():
    segments = [
        Segment('Hello {name}', 1, target='Witaj {name}'),
        Segment('Take {amount} gold.', 2, target='Weź złoto.'),
        Segment('Quest', 3, target='Misja'),
    ]
    glossary = [GlossaryEntry('Quest', 'Zadanie')]

    report = scan_segments(segments, glossary)

    assert report.segment_count == 3
    assert report.issue_segment_count == 2
    assert report.issue_count >= 2
    assert [item.segment.position for item in report.results] == [2, 3]
    assert any(issue.code == 'placeholder-missing' for issue in report.results[0].issues)
    assert any(issue.code == 'glossary-term' for issue in report.results[1].issues)


def test_scan_segments_empty_project_is_valid():
    report = scan_segments([])
    assert report.segment_count == 0
    assert report.issue_segment_count == 0
    assert report.issue_count == 0
    assert report.results == []
