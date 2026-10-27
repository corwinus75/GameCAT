from dataclasses import dataclass
from collections.abc import Iterable
from gamecat.models.translation_memory import TranslationMemoryEntry
from gamecat.tm.similarity import similarity

@dataclass(frozen=True, slots=True)
class TMSegmentReference:
    """A segment from the *active project* using exactly this bilingual pair.

    TM entry IDs and segment IDs belong to different tables and must not be
    confused. ``position`` is the line number shown by the segment editor.
    """
    id: int
    position: int


@dataclass(frozen=True, slots=True)
class TMMatch:
    entry: TranslationMemoryEntry
    score: float
    segment_references: tuple[TMSegmentReference, ...] = ()
    is_current_segment: bool = False


def find_matches(source: str, entries: Iterable[TranslationMemoryEntry], limit: int = 5, threshold: float = 0.5) -> list[TMMatch]:
    """Return the highest-scoring TM matches."""
    matches = (TMMatch(entry, similarity(source, entry.source)) for entry in entries)
    filtered = [m for m in matches if m.score >= threshold]
    filtered.sort(key=lambda m: m.score, reverse=True)
    return filtered[:limit]
