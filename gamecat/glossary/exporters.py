from __future__ import annotations

import csv
import json
from collections.abc import Iterable
from pathlib import Path

from gamecat.models.glossary import GlossaryTerm


def export_glossary_csv(path: Path, terms: Iterable[GlossaryTerm]) -> int:
    """Export one CSV row per target variant and return row count."""
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
    """Export one JSON object per source term and return term count."""
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
