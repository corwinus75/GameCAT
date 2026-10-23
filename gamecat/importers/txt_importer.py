from collections.abc import Iterator
from pathlib import Path
from gamecat.importers.base import ImportedSegment


def import_txt(path: Path) -> Iterator[ImportedSegment]:
    with path.open('r', encoding='utf-8') as handle:
        for position, line in enumerate(handle, 1):
            yield ImportedSegment(position=position, source=line.rstrip('\r\n'))
