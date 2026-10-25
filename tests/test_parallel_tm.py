from gamecat.models.translation_memory import TranslationMemoryEntry
from gamecat.tm.matcher import find_matches
from gamecat.tm.parallel_matcher import find_matches_parallel


def test_parallel_matches_sequential():
    entries=[TranslationMemoryEntry(f'The gate is closed {i}', f'Brama jest zamknięta {i}', 'en','pl') for i in range(20)]
    expected=find_matches('The gate is closed 7', entries, limit=5, threshold=0.1)
    actual=find_matches_parallel('The gate is closed 7', entries, limit=5, threshold=0.1, workers=2)
    assert [(m.entry.source, round(m.score,8)) for m in actual] == [(m.entry.source, round(m.score,8)) for m in expected]
