from __future__ import annotations

import csv
import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ImportedTranslation:
    target: str
    key: str | None = None
    position: int | None = None


def import_translation_txt(path: Path) -> Iterator[ImportedTranslation]:
    with path.open('r', encoding='utf-8') as handle:
        for position, line in enumerate(handle, 1):
            yield ImportedTranslation(target=line.rstrip('\r\n'), position=position)


def import_translation_csv(
    path: Path,
    key_column: str | None,
    target_column: str,
) -> Iterator[ImportedTranslation]:
    with path.open('r', encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames or []
        if target_column not in fields:
            raise ValueError(f'Missing CSV column: {target_column}')
        if key_column is not None and key_column not in fields:
            raise ValueError(f'Missing CSV column: {key_column}')
        for position, row in enumerate(reader, 1):
            key = row[key_column] if key_column is not None else None
            yield ImportedTranslation(
                target=row[target_column],
                key=key if key not in (None, '') else None,
                position=None if key_column is not None else position,
            )


def import_translation_json(path: Path) -> Iterator[ImportedTranslation]:
    with path.open('r', encoding='utf-8-sig') as handle:
        data = json.load(handle)

    if isinstance(data, dict):
        for key, target in data.items():
            if not isinstance(target, str):
                raise ValueError('JSON translation dict values must be strings')
            yield ImportedTranslation(target=target, key=str(key))
        return

    if isinstance(data, list):
        for position, record in enumerate(data, 1):
            if isinstance(record, str):
                yield ImportedTranslation(target=record, position=position)
                continue
            if not isinstance(record, dict) or 'target' not in record:
                raise ValueError('JSON translation list items must be strings or objects with target')
            key = None if record.get('key') is None else str(record['key'])
            explicit_position = record.get('position')
            if explicit_position is not None:
                try:
                    explicit_position = int(explicit_position)
                except (TypeError, ValueError) as exc:
                    raise ValueError('JSON translation position must be an integer') from exc
            yield ImportedTranslation(
                target=str(record['target']),
                key=key,
                position=explicit_position if key is None else None,
            )
        return

    raise ValueError('Unsupported JSON translation shape')
