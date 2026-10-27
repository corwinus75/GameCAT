"""CSV source importer supporting commas, semicolons, tabs and pipes."""
import csv
from collections.abc import Iterator
from pathlib import Path

from gamecat.importers.base import ImportedSegment
from gamecat.importers.csv_format import detect_csv_delimiter, read_csv_headers


def import_csv(path: Path, key_column: str | None, source_column: str, target_column: str | None = None,
               comment_column: str | None = None) -> Iterator[ImportedSegment]:
    # Validate once before inserting anything: import_file batches writes in a
    # transaction, so any malformed later record causes rollback.
    fields = read_csv_headers(path)
    required = ([key_column] if key_column else []) + [source_column] + ([target_column] if target_column else []) + ([comment_column] if comment_column else [])
    for name in required:
        if name not in fields:
            raise ValueError(f'Missing CSV column: {name}; available: {", ".join(fields)}')
    with path.open('r', encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle, delimiter=detect_csv_delimiter(path))
        for position, row in enumerate(reader, 1):
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f'Malformed CSV record at row {position + 1}: wrong column count')
            yield ImportedSegment(position, row[source_column], row[key_column] if key_column else None,
                                  row[target_column] if target_column else '',
                                  row[comment_column] if comment_column else '')
