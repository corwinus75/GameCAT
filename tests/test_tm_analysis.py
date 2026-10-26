from pathlib import Path

import pytest

from gamecat.models.translation_memory import TranslationMemoryEntry
from gamecat.services.project_service import ProjectService
from gamecat.tm.analysis import ExecutionMode, analyze, band_for, best_match

TM = [
    ('The gate is closed.', 'Brama jest zamknięta.'),
    ('Open the gate.', 'Otwórz bramę.'),
    ('The old stone gate is firmly closed.', 'Stara kamienna brama jest mocno zamknięta.'),
]
SEGMENTS = [
    (1, 'The gate is closed.'),
    (2, 'The gate is now closed.'),
    (3, 'Buy a sword from the smith.'),
    (4, 'Open the gate.'),
]


def test_band_boundaries():
    assert band_for(1.0) == '100%'
    assert band_for(0.95) == '95–99%'
    assert band_for(0.9499) == '85–94%'
    assert band_for(0.75) == '75–84%'
    assert band_for(0.5) == '50–74%'
    assert band_for(0.1) == 'Brak'


def test_best_match_prefers_exact_and_handles_empty_tm():
    assert best_match('Open the gate.', TM)[0] == 1.0
    assert best_match('anything', []) == (0.0, None, None)


@pytest.mark.parametrize('mode', list(ExecutionMode))
def test_all_modes_give_identical_results(mode):
    expected = analyze(SEGMENTS, TM, mode=ExecutionMode.SEQUENTIAL)
    actual = analyze(SEGMENTS, TM, mode=mode, workers=2)
    assert actual.matches == expected.matches
    assert actual.mode is mode


def test_report_statistics():
    report = analyze(SEGMENTS, TM, mode='sequential')
    assert report.segment_count == 4
    assert report.band_segments['100%'] == 2
    assert report.band_segments['Brak'] >= 1
    assert sum(report.band_segments.values()) == 4
    assert report.total_words == sum(m.words for m in report.matches)
    assert {m.segment_id for m in report.exact_matches()} == {1, 4}


def test_small_input_falls_back_to_sequential():
    report = analyze(SEGMENTS, TM, mode='processes', min_parallel=100)
    assert report.mode is ExecutionMode.SEQUENTIAL and report.workers == 1


def test_empty_tm_is_sequential_and_all_no_match():
    report = analyze(SEGMENTS, [], mode='processes')
    assert report.mode is ExecutionMode.SEQUENTIAL
    assert report.band_segments['Brak'] == 4


def test_service_analysis_and_pretranslation(tmp_path: Path):
    src = tmp_path / 'src.txt'
    src.write_text('\n'.join(s for _, s in SEGMENTS) + '\n', encoding='utf-8')
    service = ProjectService(tmp_path / 'p.sqlite')
    project = service.create_project('P', 'en', 'pl', 'txt')
    try:
        service.import_file_async(project, src).result(timeout=5)
        for source, target in TM:
            service.translation_memory.create(TranslationMemoryEntry(source, target, 'en', 'pl'))
        report = service.analyze_project_tm_async(project, mode='processes', workers=2, min_parallel=0).result(timeout=60)
        assert report.mode is ExecutionMode.PROCESSES
        assert report.band_segments['100%'] == 2
        assert service.apply_exact_matches(project, report) == 2
        targets = [s.target for s in service.list_segments(project.id)]
        assert targets[0] == 'Brama jest zamknięta.' and targets[3] == 'Otwórz bramę.'
        assert targets[1] == ''
        # Ponowne zastosowanie nie nadpisuje istniejących tłumaczeń.
        assert service.apply_exact_matches(project, report) == 0
    finally:
        service.close()
