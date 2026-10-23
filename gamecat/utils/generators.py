from collections.abc import Callable, Iterable, Iterator
from pathlib import Path
from typing import TypeVar

T = TypeVar('T')


def stream_text_lines(path: Path) -> Iterator[str]:
    """Yield UTF-8 text file lines without newline characters."""
    with path.open('r', encoding='utf-8') as handle:
        for line in handle:
            yield line.rstrip('\r\n')


def filter_segments(segments: Iterable[T], predicate: Callable[[T], bool]) -> Iterator[T]:
    """Lazily yield elements accepted by *predicate*."""
    return (segment for segment in segments if predicate(segment))
