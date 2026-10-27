"""Testy akceptacyjne pełnego, offline’owego procesu tłumaczenia w GameCAT."""

from __future__ import annotations

import json
from pathlib import Path

from gamecat.localization.profiles import FormatProfile
from gamecat.models.glossary import GlossaryTerm
from gamecat.models.segment import SegmentStatus
from gamecat.services.project_service import ProjectService


def test_game_localization_end_to_end_json_qa_tm_autosave_export_reopen(tmp_path: Path) -> None:
    original = tmp_path / 'source.json'
    original.write_text(json.dumps({
        'version': 3,
        'dialogues': [
            {'id': 'a', 'speaker': 'Guard', 'en': 'Take {count} sword.', 'pl': ''},
            {'id': 'b', 'speaker': 'Guard', 'en': 'Quest completed.', 'pl': ''},
        ],
    }), encoding='utf-8')
    database = tmp_path / 'project.sqlite'
    profile = FormatProfile('json', 'dialogues', 'id', 'en', 'pl')

    service = ProjectService(database, autosave_debounce_seconds=0.5)
    try:
        project = service.create_project('Demo', 'en', 'pl', 'json')
        service.set_format_profile(project, profile)
        imported = service.import_file_async(project, original).result(timeout=10)
        assert len(imported) == 2
        assert [item.key for item in imported] == ['a', 'b']
        service.create_glossary_term(project.id, GlossaryTerm('sword', ['miecz', 'ostrze']))

        imported[0].target = 'Weź {count} miecz.'
        imported[0].status = SegmentStatus.TRANSLATED
        service.queue_segment_save(imported[0])
        # A full-project operation must flush pending edits before reading SQLite.
        qa = service.run_project_qa(project)
        assert qa.segment_count == 2
        assert [row.segment.key for row in qa.results] == ['b']

        service.set_segment_statuses([imported[0]], SegmentStatus.APPROVED)
        matches = service.find_tm_matches(project, imported[0].source, threshold=1.0)
        assert matches and matches[0].entry.target == 'Weź {count} miecz.'

        destination = tmp_path / 'ready.json'
        assert service.export_using_template_async(project, original, destination).result(timeout=10) == 2
        exported = json.loads(destination.read_text(encoding='utf-8'))
        assert exported['version'] == 3
        assert exported['dialogues'][0]['speaker'] == 'Guard'
        assert exported['dialogues'][0]['pl'] == 'Weź {count} miecz.'
        assert exported['dialogues'][1]['pl'] == ''
        project_id = project.id
    finally:
        service.close()

    reopened = ProjectService(database)
    try:
        project = reopened.load_project(project_id)
        assert reopened.get_format_profile(project, 'json') == profile
        segments = reopened.list_segments(project.id)
        assert [(s.key, s.source, s.target, s.status) for s in segments] == [
            ('a', 'Take {count} sword.', 'Weź {count} miecz.', SegmentStatus.APPROVED),
            ('b', 'Quest completed.', '', SegmentStatus.NEW),
        ]
        assert reopened.list_glossary(project.id)[0].targets == ['miecz', 'ostrze']
        assert reopened.project_progress(project.id).approved == 1
    finally:
        reopened.close()


def test_revised_import_of_empty_target_clears_human_approval(tmp_path: Path) -> None:
    service = ProjectService(tmp_path / 'project.sqlite')
    try:
        project = service.create_project('Demo', 'en', 'pl', 'txt')
        source = tmp_path / 'source.txt'
        source.write_text('Hello\n', encoding='utf-8')
        row = service.import_file_async(project, source).result(timeout=5)[0]
        row.target = 'Witaj'
        service.save_segment(row)
        service.set_segment_statuses([row], SegmentStatus.APPROVED)

        imported = tmp_path / 'empty.txt'
        imported.write_text('\n', encoding='utf-8')
        service.import_translation_file_async(project, imported).result(timeout=5)

        changed = service.list_segments(project.id)[0]
        assert changed.target == ''
        assert changed.status is SegmentStatus.NEW
    finally:
        service.close()
