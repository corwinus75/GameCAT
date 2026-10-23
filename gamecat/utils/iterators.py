from collections.abc import Sequence
from gamecat.models.segment import Segment


class SegmentIterator:
    """Single-use iterator over translation segments."""
    def __init__(self, segments: Sequence[Segment]):
        self._segments = segments
        self._index = 0

    def __iter__(self) -> 'SegmentIterator':
        return self

    def __next__(self) -> Segment:
        if self._index >= len(self._segments):
            raise StopIteration
        value = self._segments[self._index]
        self._index += 1
        return value
