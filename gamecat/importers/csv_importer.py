import csv
from collections.abc import Iterator
from pathlib import Path
from gamecat.importers.base import ImportedSegment


def import_csv(path: Path, key_column: str, source_column: str, target_column: str | None = None) -> Iterator[ImportedSegment]:
    with path.open('r', encoding='utf-8', newline='') as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames or []
        required = [key_column, source_column] + ([target_column] if target_column else [])
        for name in required:
            if name not in fields:
                raise ValueError(f'Missing CSV column: {name}')
        for position, row in enumerate(reader, 1):
            yield ImportedSegment(position, row[source_column], row[key_column], row[target_column] if target_column else '')
