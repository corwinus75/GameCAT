from __future__ import annotations
from concurrent.futures import ProcessPoolExecutor
from gamecat.models.translation_memory import TranslationMemoryEntry
from gamecat.tm.matcher import TMMatch, find_matches


def _match_chunk(args: tuple[str, list[TranslationMemoryEntry], int, float]) -> list[TMMatch]:
    source, entries, limit, threshold = args
    return find_matches(source, entries, limit=limit, threshold=threshold)


def find_matches_parallel(source: str, entries: list[TranslationMemoryEntry], limit: int = 5,
                          threshold: float = 0.5, workers: int | None = None) -> list[TMMatch]:
    """Search TM entries in separate processes and merge top results."""
    if not entries:
        return []
    worker_count = workers or min(4, len(entries))
    worker_count = max(1, min(worker_count, len(entries)))
    chunk_size = (len(entries) + worker_count - 1) // worker_count
    chunks = [entries[i:i + chunk_size] for i in range(0, len(entries), chunk_size)]
    with ProcessPoolExecutor(max_workers=worker_count) as pool:
        partial = pool.map(_match_chunk, [(source, chunk, limit, threshold) for chunk in chunks])
    merged = [match for matches in partial for match in matches]
    merged.sort(key=lambda m: m.score, reverse=True)
    return merged[:limit]
