from __future__ import annotations

import csv
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from gamecat.database.repositories import GlossaryRepository
from gamecat.models.glossary import GlossaryTerm


@dataclass(frozen=True, slots=True)
class GlossaryImportResult:
    new_terms: int = 0
    new_variants: int = 0
    duplicates: int = 0
    invalid_rows: int = 0


def _parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or '').strip().casefold()
    if text in {'', '0', 'false', 'no', 'nie'}:
        return False
    if text in {'1', 'true', 'yes', 'tak'}:
        return True
    raise ValueError(f'invalid boolean value: {value!r}')


def _aggregate(rows: list[tuple[str, str, str, bool]]) -> tuple[list[GlossaryTerm], int]:
    groups: dict[tuple[str, bool], dict[str, Any]] = {}
    duplicates = 0
    for source, target, description, case_sensitive in rows:
        key = (source, case_sensitive)
        state = groups.setdefault(key, {'targets': [], 'description': ''})
        if description and not state['description']:
            state['description'] = description
        if target in state['targets']:
            duplicates += 1
        else:
            state['targets'].append(target)
    terms = [
        GlossaryTerm(source, state['targets'], state['description'], case_sensitive)
        for (source, case_sensitive), state in groups.items()
    ]
    return terms, duplicates


def import_glossary_csv(path: Path, repository: GlossaryRepository, project_id: int) -> GlossaryImportResult:
    """Merge a canonical CSV glossary into one project."""
    rows: list[tuple[str, str, str, bool]] = []
    invalid = 0
    with path.open('r', encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or not {'source', 'target'} <= set(reader.fieldnames):
            raise ValueError('CSV must contain source and target columns')
        for row in reader:
            source = (row.get('source') or '').strip()
            target = (row.get('target') or '').strip()
            if not source or not target:
                invalid += 1
                continue
            try:
                case_sensitive = _parse_bool(row.get('case_sensitive', ''))
            except ValueError:
                invalid += 1
                continue
            rows.append((source, target, (row.get('description') or '').strip(), case_sensitive))
    terms, input_duplicates = _aggregate(rows)
    new_terms, new_variants, db_duplicates = repository.merge_terms(project_id, terms)
    return GlossaryImportResult(new_terms, new_variants, input_duplicates + db_duplicates, invalid)


def import_glossary_json(path: Path, repository: GlossaryRepository, project_id: int) -> GlossaryImportResult:
    """Merge a canonical JSON glossary into one project."""
    payload = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(payload, list):
        raise ValueError('JSON glossary root must be a list')
    rows: list[tuple[str, str, str, bool]] = []
    invalid = 0
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError('each JSON glossary entry must be an object')
        source = str(item.get('source') or '').strip()
        targets = item.get('targets')
        if not isinstance(targets, list):
            raise ValueError('targets must be a list')
        try:
            case_sensitive = _parse_bool(item.get('case_sensitive', False))
        except ValueError:
            invalid += 1
            continue
        description = str(item.get('description') or '').strip()
        if (
            not source
            or not targets
            or any(not isinstance(target, str) or not target.strip() for target in targets)
        ):
            invalid += 1
            continue
        valid_targets = [target.strip() for target in targets]
        for target in valid_targets:
            rows.append((source, target, description, case_sensitive))
    terms, input_duplicates = _aggregate(rows)
    new_terms, new_variants, db_duplicates = repository.merge_terms(project_id, terms)
    return GlossaryImportResult(new_terms, new_variants, input_duplicates + db_duplicates, invalid)
