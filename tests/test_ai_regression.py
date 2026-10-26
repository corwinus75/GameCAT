from pathlib import Path
from types import SimpleNamespace

import pytest

from gamecat.ai.core import AISettings, BatchTranslator, OpenAITranslator
from gamecat.models.segment import Segment, SegmentStatus
from gamecat.services.project_service import ProjectService


class Responses:
    def __init__(self, value): self.value = value; self.calls = 0
    def create(self, **kwargs):
        self.calls += 1
        if isinstance(self.value, Exception): raise self.value
        return SimpleNamespace(output_text=self.value, usage=SimpleNamespace(input_tokens=50, output_tokens=50))


def test_ai_translation_qa_warns_on_broken_placeholder():
    client = SimpleNamespace(responses=Responses('Witaj, świecie.'))
    result = OpenAITranslator(client).translate('Hello, {name}.', 'en', 'pl', [], [], AISettings())
    assert any('placeholdera' in message for message in result.qa_warnings)


def test_soft_budget_stops_before_request():
    responses = Responses('Hello')
    translator = OpenAITranslator(SimpleNamespace(responses=responses))
    report = BatchTranslator(translator).translate_items(
        [(1, 'Hello', '')], 'en', 'pl', [], [],
        AISettings(input_price_per_million=100.0, output_price_per_million=100.0),
        budget_usd=0.001,
    )
    assert report.budget_exhausted
    assert responses.calls == 0


def test_ai_marker_survives_autosave_then_clears_on_manual_edit(tmp_path: Path):
    project_file = tmp_path / 'legacy.sqlite'
    service = ProjectService(project_file)
    project = service.create_project('Game', 'en', 'pl', 'txt')
    segment = service.segments.create(Segment('Source', 1, project_id=project.id))
    service.apply_ai_translation(project, segment.id, 'Tłumaczenie', 'gpt-5-mini')
    stored = service.list_segments(project.id)[0]
    assert stored.ai_generated
    service.queue_segment_save(stored)
    service.flush_saves()
    assert service.list_segments(project.id)[0].ai_generated
    stored.target = 'Ręcznie'
    service.save_segment(stored)
    assert not service.list_segments(project.id)[0].ai_generated
    service.close()
    reopened = ProjectService(project_file)
    assert not reopened.list_segments(project.id)[0].ai_generated
    reopened.close()


def test_non_matching_project_segment_cannot_be_mutated(tmp_path: Path):
    service = ProjectService(tmp_path / 'projects.sqlite')
    a = service.create_project('One', 'en', 'pl', 'txt')
    b = service.create_project('Two', 'en', 'pl', 'txt')
    segment = service.segments.create(Segment('Source', 1, project_id=b.id))
    with pytest.raises(ValueError, match='does not belong'):
        service.apply_ai_translation(a, segment.id, 'Tłumaczenie', 'gpt-5-mini')
    assert service.segments.get(segment.id).target == ''
    service.close()


def test_ai_source_instructions_not_logged_or_saved_as_key(tmp_path: Path):
    service = ProjectService(tmp_path / 'p.sqlite')
    project = service.create_project('Demo', 'en', 'pl', 'txt')
    service.set_ai_settings(project, AISettings(instructions='Fantasy style'))
    service.close()
    raw = (tmp_path / 'p.sqlite').read_bytes()
    assert b'OPENAI_API_KEY' not in raw
    assert b'sk-test' not in raw


def test_migration_from_09_database_preserves_rows(tmp_path: Path):
    import sqlite3
    db = tmp_path / 'original_09.sqlite'
    raw = sqlite3.connect(db)
    raw.executescript('''
    CREATE TABLE projects (id INTEGER PRIMARY KEY, name TEXT NOT NULL,
       source_language TEXT NOT NULL, target_language TEXT NOT NULL,
       source_format TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
    INSERT INTO projects VALUES (1, 'Demo', 'en', 'pl', 'txt', '2026-01-01', '2026-01-01');
    CREATE TABLE segments (id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL,
       position INTEGER NOT NULL, key TEXT, source TEXT NOT NULL,
       target TEXT NOT NULL DEFAULT '', status TEXT NOT NULL DEFAULT 'NEW',
       comment TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL,
       updated_at TEXT NOT NULL);
    INSERT INTO segments VALUES(1,1,1,NULL,'Hello {name}','Witaj {name}',
       'REVIEWED','', '2026-01-01','2026-01-01');
    ''')
    raw.close()
    service = ProjectService(db)
    project = service.load_project(1)
    assert service.list_segments(project.id)[0].target == 'Witaj {name}'
    assert service.list_segments(project.id)[0].status is SegmentStatus.REVIEWED
    assert not service.list_segments(project.id)[0].ai_generated
    assert service.get_ai_settings(project).model == 'gpt-5-mini'
    service.close()
    service = ProjectService(db)
    assert len(service.list_segments(1)) == 1
    assert service.get_ai_settings(service.load_project(1)).instructions == ''
    service.close()


def test_create_openai_client_passes_key_only_in_memory(monkeypatch):
    import sys
    from gamecat.ai.credentials import create_openai_translator
    captured = {}

    def fake_openai(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(responses=Responses('Dobrze'), models=SimpleNamespace(retrieve=lambda x: x))

    monkeypatch.setitem(sys.modules, 'openai', SimpleNamespace(OpenAI=fake_openai))
    adapter = create_openai_translator('sk-placeholder-not-real')
    assert captured['api_key'] == 'sk-placeholder-not-real'
    assert captured['max_retries'] == 2
    adapter.test_connection('gpt-5-mini')
