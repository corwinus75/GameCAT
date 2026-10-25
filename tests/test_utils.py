from pathlib import Path
import pytest
from gamecat.models.segment import Segment
from gamecat.utils.decorators import measure_time, retry, requires_project
from gamecat.utils.iterators import SegmentIterator
from gamecat.utils.generators import stream_text_lines, filter_segments


def test_measure_time_preserves_metadata():
    @measure_time
    def sample(x):
        "doc"
        return x + 1
    assert sample.__name__ == 'sample'
    assert sample.__doc__ == 'doc'
    assert sample(2) == 3


def test_retry_uses_configured_attempts():
    calls = {'n': 0}
    @retry(attempts=3)
    def flaky():
        calls['n'] += 1
        if calls['n'] < 3:
            raise ValueError('x')
        return 'ok'
    assert flaky() == 'ok'
    assert calls['n'] == 3


def test_requires_project_uses_self():
    class C:
        current_project = None
        @requires_project
        def run(self): return 7
    with pytest.raises(RuntimeError, match='No project is open'):
        C().run()
    c = C(); c.current_project = object(); assert c.run() == 7


def test_segment_iterator_is_exhaustible():
    items = [Segment('a', 1), Segment('b', 2)]
    it = SegmentIterator(items)
    assert [next(it).source, next(it).source] == ['a', 'b']
    with pytest.raises(StopIteration): next(it)


def test_stream_and_filter_are_lazy(tmp_path: Path):
    p = tmp_path / 'x.txt'; p.write_text('a\nb\n', encoding='utf-8')
    g = stream_text_lines(p)
    assert iter(g) is g
    assert list(g) == ['a', 'b']
    segs = (Segment(x, i) for i, x in enumerate(['a', 'bb'], 1))
    assert [s.source for s in filter_segments(segs, lambda s: len(s.source) > 1)] == ['bb']
