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


def test_project_service_builds_tm_from_translated_segments_and_finds_matches(tmp_path):
    from pathlib import Path
    from gamecat.services.project_service import ProjectService

    service = ProjectService(Path(tmp_path) / 'tm.sqlite')
    project = service.create_project('Demo', 'en', 'pl', 'txt')
    source = Path(tmp_path) / 'source.txt'
    source.write_text('Open the gate\nClose the gate\n', encoding='utf-8')
    rows = service.import_file_async(project, source).result(timeout=5)
    rows[0].target = 'Otwórz bramę'
    rows[1].target = 'Zamknij bramę'
    service.save_segment(rows[0])
    service.save_segment(rows[1])
    try:
        assert service.sync_project_to_tm(project) == 2
        assert service.sync_project_to_tm(project) == 0
        matches = service.find_tm_matches(project, 'Open gate', limit=5, threshold=0.2)
        assert matches
        assert matches[0].entry.target == 'Otwórz bramę'
    finally:
        service.close()
