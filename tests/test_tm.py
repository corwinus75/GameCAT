from gamecat.models.translation_memory import TranslationMemoryEntry
from gamecat.tm.similarity import similarity
from gamecat.tm.matcher import find_matches


def entry(source, target):
    return TranslationMemoryEntry(source, target, 'en', 'pl')


def test_similarity_identity_and_difference():
    assert similarity('The gate is closed.', 'The gate is closed.') == 1.0
    assert similarity('The gate is closed.', 'Bananas fly silently.') < 0.5


def test_find_matches_orders_limits_and_threshold():
    entries=[entry('The gate is closed.','Brama jest zamknięta.'), entry('The gate was closed.','Brama była zamknięta.'), entry('Bananas fly silently.','Banany latają.')]
    matches=find_matches('The gate is closed.', entries, limit=2, threshold=0.2)
    assert len(matches)==2
    assert matches[0].entry.source=='The gate is closed.'
    assert matches[0].score >= matches[1].score
    assert all(m.score >= 0.2 for m in matches)
