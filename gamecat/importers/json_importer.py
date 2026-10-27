"""Importer źródeł z prostego JSON."""
import json
from collections.abc import Iterator
from pathlib import Path
from gamecat.importers.base import ImportedSegment


def import_json(path: Path) -> Iterator[ImportedSegment]:
    """Generator segmentów z JSON: słownika ``klucz: source`` lub listy obiektów z ``source``.

    :raises ValueError: nieobsługiwana struktura lub wartość niebędąca napisem.
    """
    with path.open('r', encoding='utf-8') as handle:
        data = json.load(handle)
    if isinstance(data, dict):
        for position, (key, source) in enumerate(data.items(), 1):
            if not isinstance(source, str):
                raise ValueError('JSON dict values must be strings')
            yield ImportedSegment(position, source, str(key))
        return
    if isinstance(data, list):
        for position, record in enumerate(data, 1):
            if not isinstance(record, dict) or 'source' not in record:
                raise ValueError('JSON list items must be objects with source')
            yield ImportedSegment(position, str(record['source']), None if record.get('key') is None else str(record.get('key')), str(record.get('target', '')))
        return
    raise ValueError('Unsupported JSON shape')
