"""Wyszukiwanie dopasowań fuzzy w pamięci tłumaczeniowej."""
from dataclasses import dataclass
from collections.abc import Iterable
from gamecat.models.translation_memory import TranslationMemoryEntry
from gamecat.tm.similarity import similarity

@dataclass(frozen=True, slots=True)
class TMSegmentReference:
    """Segment *aktywnego projektu* używający dokładnie tej pary dwujęzycznej.

    ID wpisu TM i ID segmentu pochodzą z różnych tabel i nie wolno ich mylić.
    ``position`` to numer linii wyświetlany w edytorze segmentów.
    """
    id: int
    position: int


@dataclass(frozen=True, slots=True)
class TMMatch:
    """Dopasowanie TM: wpis, podobieństwo, odwołania do segmentów projektu i znacznik bieżącego segmentu."""
    entry: TranslationMemoryEntry
    score: float
    segment_references: tuple[TMSegmentReference, ...] = ()
    is_current_segment: bool = False


def find_matches(source: str, entries: Iterable[TranslationMemoryEntry], limit: int = 5, threshold: float = 0.5) -> list[TMMatch]:
    """Zwróć najlepiej ocenione dopasowania TM powyżej progu (najwyżej *limit*)."""
    matches = (TMMatch(entry, similarity(source, entry.source)) for entry in entries)
    filtered = [m for m in matches if m.score >= threshold]
    filtered.sort(key=lambda m: m.score, reverse=True)
    return filtered[:limit]
