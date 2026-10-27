"""Regression: large-project indexing stays equivalent to legacy search."""
import threading
import pytest

from gamecat.models.segment import Segment, SegmentStatus
from gamecat.search.index import SegmentSearchIndex
from gamecat.search.operations import SearchQuery, filter_segments


def sample():
    return [
        Segment('Witch: {g|Varnhold}Varnhold{/g}', 8, target='Wiedźma', status='APPROVED', id=1),
        Segment('SWORD', 1, target='Miecz i\nTarcza', status='TRANSLATED', id=2),
        Segment('Swordsmith', 5, target='', id=3),
        Segment('wolf', 4, target='Wilk', status='REVIEWED', id=4),
        Segment('Another sword', 3, target='Inny miecz', status='TRANSLATED', id=5),
    ]


@pytest.mark.parametrize('query', [
    SearchQuery(), SearchQuery('sword'), SearchQuery('Sword', case_sensitive=True),
    SearchQuery('miecz', scope='target'), SearchQuery(r'\bSword\b', regex=True),
    SearchQuery('wolf', status='REVIEWED'), SearchQuery(quality='untranslated'),
    SearchQuery(quality='qa_errors'), SearchQuery(quality='tm_match', descending=True),
    SearchQuery(sort='source'), SearchQuery(sort='status', descending=True),
    SearchQuery('Varnhold', scope='source', regex=True),
])
def test_index_matches_legacy_for_all_filters(query):
    rows = sample()
    qa, tm = {1, 4}, {2, 5}
    legacy = filter_segments(rows, query, qa_error_ids=qa, tm_match_ids=tm)
    result = SegmentSearchIndex(rows).search(query, qa_error_ids=qa, tm_match_ids=tm)
    assert [rows[i].id for i in result] == [s.id for s in legacy]


def test_index_is_snapshot_and_incremental_updates():
    rows = sample()
    idx = SegmentSearchIndex(rows)
    rows[0].source = 'new name'
    assert idx.search(SearchQuery('Varnhold')) == [0]
    updated = idx.updated(rows[0])
    assert updated.search(SearchQuery('Varnhold')) == []
    assert idx.search(SearchQuery('Varnhold')) == [0]
    rows[0].status = SegmentStatus.NEW
    updated = updated.updated(rows[0])
    assert updated.search(SearchQuery(status='NEW')) == [2, 0]


def test_index_invalid_regex_and_cancellation():
    idx = SegmentSearchIndex(sample())
    with pytest.raises(ValueError, match='regex'):
        idx.search(SearchQuery('(', regex=True))
    done = threading.Event()
    done.set()
    assert idx.search(SearchQuery('sword'), cancel=done) is None


def test_large_project_result_is_small_and_cancellable():
    rows = [Segment(f'ordinary dialogue {i}', i, target='Ok', id=i) for i in range(45000)]
    rows[34721].source = 'Unique Needle text'
    index = SegmentSearchIndex(rows)
    assert index.search(SearchQuery('unique needle', scope='source')) == [34721]
    assert index.search(SearchQuery('not present')) == []
    done = threading.Event(); done.set()
    assert index.search(SearchQuery('unique'), cancel=done) is None
