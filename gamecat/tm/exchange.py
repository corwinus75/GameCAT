"""Lossless CSV/JSON exchange of Translation Memory entries.

All rows are validated before any database mutation. Exports are staged in a
temporary file and atomically replaced to avoid producing truncated exports.
"""
from __future__ import annotations

import csv
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from gamecat.models.translation_memory import TranslationMemoryEntry

_FIELDS = ('source', 'target', 'source_language', 'target_language', 'origin_project', 'created_at')
_REQUIRED = _FIELDS[:4]


def _entry(row: object, index: int) -> TranslationMemoryEntry:
    if not isinstance(row, dict):
        raise ValueError(f'TM entry {index}: expected an object')
    values: dict[str, str] = {}
    for name in _REQUIRED:
        value = row.get(name)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f'TM entry {index}: {name} must be a non-empty string')
        values[name] = value
    origin = row.get('origin_project')
    if origin is not None and not isinstance(origin, str):
        raise ValueError(f'TM entry {index}: origin_project must be a string or null')
    raw_date = row.get('created_at')
    if raw_date is None or raw_date == '':
        created_at = datetime.now(timezone.utc)
    elif isinstance(raw_date, str):
        try:
            created_at = datetime.fromisoformat(raw_date)
        except ValueError as exc:
            raise ValueError(f'TM entry {index}: invalid created_at') from exc
    else:
        raise ValueError(f'TM entry {index}: invalid created_at')
    return TranslationMemoryEntry(**values, origin_project=origin or None, created_at=created_at)


def read_tm(path: Path) -> list[TranslationMemoryEntry]:
    """Read and validate the full exchange file; no partial imports."""
    path = Path(path)
    suffix = path.suffix.casefold()
    if suffix == '.json':
        with path.open('r', encoding='utf-8-sig') as stream:
            data = json.load(stream)
        if not isinstance(data, list):
            raise ValueError('TM JSON must contain an array of entries')
    elif suffix == '.csv':
        with path.open('r', encoding='utf-8-sig', newline='') as stream:
            reader = csv.DictReader(stream)
            if not reader.fieldnames or any(key not in reader.fieldnames for key in _REQUIRED):
                raise ValueError('TM CSV requires source,target,source_language,target_language')
            data = list(reader)
            if any(None in row for row in data):
                raise ValueError('TM CSV row contains extra columns')
    else:
        raise ValueError(f'Unsupported TM format: {suffix or "<none>"}')
    return [_entry(row, i) for i, row in enumerate(data, 1)]


def write_tm(path: Path, entries: list[TranslationMemoryEntry]) -> int:
    """Save all entries of the selected TM storage as CSV/JSON atomically."""
    path = Path(path)
    suffix = path.suffix.casefold()
    if suffix not in {'.csv', '.json'}:
        raise ValueError(f'Unsupported TM format: {suffix or "<none>"}')
    rows = [{
        'source': e.source,
        'target': e.target,
        'source_language': e.source_language,
        'target_language': e.target_language,
        'origin_project': e.origin_project,
        'created_at': e.created_at.isoformat(),
    } for e in entries]
    tmp: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', newline='',
                                         dir=path.parent, prefix=f'.{path.name}.',
                                         suffix='.tmp', delete=False) as out:
            tmp = Path(out.name)
            if suffix == '.json':
                json.dump(rows, out, ensure_ascii=False, indent=2)
                out.write('\n')
            else:
                writer = csv.DictWriter(out, fieldnames=_FIELDS)
                writer.writeheader()
                writer.writerows(rows)
        os.replace(tmp, path)
    finally:
        if tmp is not None and tmp.exists():
            tmp.unlink()
    return len(rows)
