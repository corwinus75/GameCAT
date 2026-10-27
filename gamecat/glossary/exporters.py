"""Eksport glosariusza do CSV i JSON."""
from __future__ import annotations

import csv
import json
from collections.abc import Iterable
from pathlib import Path

from gamecat.models.glossary import GlossaryTerm


def export_glossary_csv(path: Path, terms: Iterable[GlossaryTerm]) -> int:
    """Zapisz glosariusz do CSV (jeden wiersz na wariant tłumaczenia) i zwróć liczbę wierszy."""
    count = 0
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(['source', 'target', 'description', 'case_sensitive'])
        for term in terms:
            for target in term.targets:
                writer.writerow([term.source_term, target, term.description, str(term.case_sensitive).lower()])
                count += 1
    return count


def export_glossary_json(path: Path, terms: Iterable[GlossaryTerm]) -> int:
    """Zapisz glosariusz do JSON (jeden obiekt na termin źródłowy) i zwróć liczbę terminów."""
    data = [
        {
            'source': term.source_term,
            'targets': list(term.targets),
            'description': term.description,
            'case_sensitive': term.case_sensitive,
        }
        for term in terms
    ]
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return len(data)
