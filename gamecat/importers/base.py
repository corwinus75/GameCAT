"""Wspólny rekord zwracany przez importery segmentów."""
from dataclasses import dataclass


@dataclass(slots=True)
class ImportedSegment:
    """Segment odczytany z pliku: pozycja, Source, opcjonalnie klucz, Target i komentarz."""
    position: int
    source: str
    key: str | None = None
    target: str = ""
    comment: str = ""
