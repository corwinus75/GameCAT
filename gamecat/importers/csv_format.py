"""Wspólne rozpoznawanie dialektu i nagłówków CSV dla importu źródeł i tłumaczeń.

Separator jest ustalany na podstawie *rekordu nagłówka*, a nie przypadkowych
przecinków w tekście lokalizacji. ``Id;Loca`` to więc CSV z dwiema kolumnami,
nawet jeśli wartości Source zawierają przecinki lub sekwencje ``\\n``.
"""
from __future__ import annotations

import csv
from pathlib import Path

# Restrict sniffing to established separators, not letters/punctuation from text.
DELIMITERS = (',', ';', '\t', '|')


def detect_csv_delimiter(path: Path) -> str:
    """Rozpoznaj separator (``,``, ``;``, tab, ``|``) na podstawie pierwszego rekordu.

    :raises ValueError: gdy plik jest pusty.
    """
    with path.open('r', encoding='utf-8-sig', newline='') as handle:
        sample = handle.read(65536)
    if not sample.strip():
        raise ValueError('Plik CSV jest pusty.')

    # Sniffer is useful when a header has an ambiguous separator, but can be
    # confused by natural-language commas in subsequent localization strings.
    try:
        sniffed = csv.Sniffer().sniff(sample, delimiters=''.join(DELIMITERS)).delimiter
    except csv.Error:
        sniffed = ','

    from io import StringIO
    columns: dict[str, int] = {}
    for delimiter in DELIMITERS:
        try:
            record = next(csv.reader(StringIO(sample, newline=''), delimiter=delimiter))
            columns[delimiter] = len(record)
        except (csv.Error, StopIteration):
            columns[delimiter] = 0
    best = max(columns.values())
    if best <= 1:
        return sniffed
    candidates = [delimiter for delimiter, count in columns.items() if count == best]
    return sniffed if sniffed in candidates else candidates[0]


def read_csv_headers(path: Path) -> list[str]:
    """Odczytaj nazwy kolumn tak samo jak importer (również dla plików z BOM).

    :raises ValueError: pusty plik, puste lub powtórzone nazwy kolumn.
    """
    with path.open('r', encoding='utf-8-sig', newline='') as handle:
        reader = csv.reader(handle, delimiter=detect_csv_delimiter(path))
        try:
            columns = next(reader)
        except StopIteration as exc:
            raise ValueError('Plik CSV jest pusty.') from exc
    if not columns or not any(col.strip() for col in columns):
        raise ValueError('Plik CSV nie zawiera nagłówków kolumn.')
    if any(not col.strip() for col in columns):
        raise ValueError('Plik CSV zawiera pustą nazwę kolumny.')
    if len(set(columns)) != len(columns):
        raise ValueError('Plik CSV zawiera powtórzone nazwy kolumn.')
    return columns


def suggest_source_columns(fields: list[str]) -> tuple[str | None, str, str | None]:
    """Zaproponuj kolumny klucza, Source i Target na podstawie nagłówków.

    Dla pliku bez znanej kolumny ID nie jest ona wymyślana – segmenty są wtedy
    identyfikowane pozycją.

    :raises ValueError: gdy nie da się ustalić kolumny Source.
    """
    if not fields:
        raise ValueError('Import CSV wymaga nagłówka z tekstem źródłowym.')
    lower = {field.strip().casefold(): field for field in fields}

    def first(*names: str) -> str | None:
        return next((lower[name] for name in names if name in lower), None)

    key = first('id', 'key', 'string_id', 'stringid', 'identifier', 'uid')
    source = first('source', 'english', 'en', 'text', 'loca', 'localization',
                   'original', 'value', 'content', 'string', 'text_en')
    target = first('target', 'polish', 'pl', 'translation', 'text_pl')
    if source is None:
        if key is not None:
            source = next((name for name in fields if name not in (key, target)), None)
        else:
            # Without known names, legacy convention is first = key, second = Source.
            # For a single-column file use positional IDs (key=None).
            key = fields[0] if len(fields) > 1 else None
            source = next((name for name in fields if name not in (key, target)), None)
    if source is None:
        raise ValueError('Nie można ustalić kolumny Source.')
    if target in (key, source):
        target = None
    return key, source, target
