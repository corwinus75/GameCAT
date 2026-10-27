"""Regression tests for project context, streamed QA/export and cached TM."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from gamecat.localization.profiles import FormatProfile
from gamecat.localization.exchange import read_source
from gamecat.models.segment import Segment
from gamecat.models.translation_memory import TranslationMemoryEntry
from gamecat.qa.project_scan import scan_segments
from gamecat.services.project_service import ProjectService


def test_context_import_json_and_xml(tmp_path: Path):
    data = tmp_path / 'dialogues.json'
    data.write_text(json.dumps({'lines': [{'id': 'a', 'en': 'Run!', 'pl': '', 'speaker': 'Guard'}]}), encoding='utf-8')
    profile = FormatProfile('json', records_path='lines', key_field='id', source_field='en',
                            target_field='pl', comment_field='speaker')
    assert list(read_source(data, profile))[0].comment == 'Guard'
    assert FormatProfile.from_dict(profile.to_dict()).comment_field == 'speaker'
    xml = tmp_path / 'dialogues.xml'
    xml.write_text('<root><entry who="Wizard"><id>x</id><en>Hello</en><pl/></entry></root>', encoding='utf-8')
    xp = FormatProfile('xml', './/entry', 'id', 'en', 'pl', comment_field='@who')
    assert list(read_source(xml, xp))[0].comment == 'Wizard'


def test_context_import_table_and_persistence(tmp_path: Path):
    tab = tmp_path / 'a.tsv'
    tab.write_text('id\tsource\ttarget\tcontext\n1\tGo\tIdź\tIn battle\n', encoding='utf-8')
    profile = FormatProfile('tsv', key_field='id', comment_field='context')
    assert list(read_source(tab, profile))[0].comment == 'In battle'
    with_project = ProjectService(tmp_path / 'cat.sqlite')
    try:
        project = with_project.create_project('Demo', 'en', 'pl', 'tsv')
        with_project.set_format_profile(project, profile)
        inserted = with_project._import_file(project, tab)
        assert inserted[0].comment == 'In battle'
        assert with_project.get_segment(inserted[0].id).comment == 'In battle'
        assert with_project.get_format_profile(project, 'tsv').comment_field == 'context'
        assert with_project.count_segments(project.id) == 1
    finally:
        with_project.close()


def test_streaming_qa_counts_generator_items_without_materialization():
    def samples():
        for i in range(1400):
            yield Segment('Hello', i + 1, target='Cześć')
    report = scan_segments(samples())
    assert report.segment_count == 1400
    assert report.issue_segment_count == 0


def test_tm_entries_are_cached_until_modified(tmp_path: Path):
    service = ProjectService(tmp_path / 'demo.sqlite')
    try:
        project = service.create_project('demo', 'en', 'pl', 'txt')
        service.translation_memory.create_unique_many([
            TranslationMemoryEntry('Sword', 'Miecz', 'en', 'pl')
        ])
        repo = service.translation_memory
        with patch.object(repo, 'list_for_languages', wraps=repo.list_for_languages) as spy:
            service.find_tm_matches(project, 'Sword')
            service.find_tm_matches(project, 'Sword')
            assert spy.call_count == 1
            service.invalidate_tm_cache()
            service.find_tm_matches(project, 'Sword')
            assert spy.call_count == 2
    finally:
        service.close()


def test_quality_context_uses_current_segments_and_tm(tmp_path: Path):
    service = ProjectService(tmp_path / 'db.sqlite')
    try:
        project = service.create_project('demo', 'en', 'pl', 'txt')
        segments = service.segments.create_many([
            Segment('Sword', 1, target='', project_id=project.id),
            Segment('Shield', 2, target='Tarcza', project_id=project.id),
        ])
        service.translation_memory.create_unique_many([
            TranslationMemoryEntry('Sword', 'Miecz', 'en', 'pl')
        ])
        result = service.calculate_search_context(project, segments, qa=True, tm=True)
        assert segments[0].id in result['tm_match_ids']
        assert segments[1].id not in result['tm_match_ids']
        assert segments[0].id in result['qa_error_ids']
    finally:
        service.close()


def _controller(name: str, scope: dict):
    import ast
    path = Path(__file__).resolve().parents[1] / 'gamecat/gui/main_window.py'
    tree = ast.parse(path.read_text(encoding='utf-8'))
    cls = next(x for x in tree.body if isinstance(x, ast.ClassDef) and x.name == 'MainWindow')
    function = next(x for x in cls.body if isinstance(x, ast.FunctionDef) and x.name == name)
    function.decorator_list = []
    exec(compile(ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[])), str(path), 'exec'), scope)
    return scope[name]


class _QueuedTimer:
    calls: list = []

    @classmethod
    def singleShot(cls, _delay, callback):
        cls.calls.append(callback)

    @classmethod
    def drain(cls):
        while cls.calls:
            cls.calls.pop(0)()


def test_async_tm_does_not_publish_stale_segment_results():
    from concurrent.futures import Future
    from types import SimpleNamespace
    from gamecat.tm.matcher import TMMatch

    _QueuedTimer.calls = []
    first, second = Future(), Future()
    returned = iter((first, second))
    service = SimpleNamespace(find_tm_matches_async=lambda *_args, **_kwargs: next(returned))
    project = SimpleNamespace(id=42)
    seg_a, seg_b = SimpleNamespace(id=3, source='a'), SimpleNamespace(id=4, source='b')
    visible = [seg_a]
    values = []
    stub = SimpleNamespace(_tm_generation=0, _closing=False, project_service=service,
                           current_project=project,
                           segment_editor=SimpleNamespace(current_segment=lambda: visible[0]),
                           tm_panel=SimpleNamespace(set_matches=values.append),
                           statusBar=lambda: SimpleNamespace(showMessage=lambda *_args: None))
    method = _controller('_update_current_tm', {'QTimer': _QueuedTimer})
    method(stub, seg_a)
    first.set_running_or_notify_cancel()  # Simulate a request already in progress.
    visible[0] = seg_b
    method(stub, seg_b)
    first.set_result(['old'])
    second.set_result(['new'])
    _QueuedTimer.drain()
    assert values == [['new']]


def test_async_quality_context_discards_outdated_result():
    from concurrent.futures import Future
    from types import SimpleNamespace
    _QueuedTimer.calls = []
    first, second = Future(), Future()
    futures = iter((first, second))
    fake = SimpleNamespace(calculate_search_context_async=lambda *_args, **_kwargs: next(futures))
    received = []
    editor = SimpleNamespace(quality_filter=SimpleNamespace(currentData=lambda: 'qa_errors'),
                             all_segments=lambda: [Segment('x', 1, id=8)],
                             set_search_context=lambda **values: received.append(values))
    stub = SimpleNamespace(_quality_generation=0, _closing=False, project_service=fake,
                           current_project=SimpleNamespace(id=9), segment_editor=editor,
                           _pending_qa_jump=None,
                           statusBar=lambda: SimpleNamespace(showMessage=lambda *_args: None))
    method = _controller('_refresh_search_context', {'QTimer': _QueuedTimer})
    method(stub)
    first.set_running_or_notify_cancel()
    method(stub)
    first.set_result({'qa_error_ids': {8}})
    second.set_result({'qa_error_ids': set()})
    _QueuedTimer.drain()
    assert received == [{'qa_error_ids': set()}]


def test_flat_export_streams_ordered_iterator(tmp_path: Path):
    from gamecat.exporters.json_exporter import export_json
    from gamecat.exporters.txt_exporter import export_txt
    from gamecat.localization.exchange import export_translations

    def incoming():
        for i in range(300):
            yield Segment(f'Item {i}', i + 1, target=f'Tłumaczenie {i}', comment='NPC')

    text = tmp_path / 'result.txt'
    export_txt(incoming(), text, ordered=True)
    assert len(text.read_text(encoding='utf-8').splitlines()) == 300
    structured = tmp_path / 'table.tsv'
    profile = FormatProfile('tsv', key_field='', comment_field='comment')
    assert export_translations(incoming(), structured, profile) == 300
    assert 'comment' in structured.read_text(encoding='utf-8-sig').splitlines()[0]
    output = tmp_path / 'out.json'
    export_json(incoming(), output, ordered=True)
    data = json.loads(output.read_text(encoding='utf-8'))
    assert len(data) == 300 and data[-1]['comment'] == 'NPC'


def test_comment_edit_persists_without_changing_review_status(tmp_path: Path):
    from gamecat.models.segment import SegmentStatus
    project_file = tmp_path / 'project.sqlite'
    service = ProjectService(project_file)
    try:
        project = service.create_project('demo', 'en', 'pl', 'txt')
        segment = service.segments.create(Segment('Hello', 1, target='Witaj',
                                                  status=SegmentStatus.APPROVED,
                                                  project_id=project.id))
        segment.comment = 'Speaker: Captain, location: the harbor'
        service.save_segment(segment)
        saved = service.get_segment(segment.id)
        assert saved.comment == 'Speaker: Captain, location: the harbor'
        assert saved.status is SegmentStatus.APPROVED
    finally:
        service.close()
    reopened = ProjectService(project_file)
    try:
        assert reopened.get_segment(segment.id).comment.startswith('Speaker: Captain')
    finally:
        reopened.close()


def test_old_format_profile_without_comment_field_stays_compatible():
    profile = FormatProfile.from_dict({'format': 'json', 'records_path': 'lines',
                                      'key_field': 'id', 'source_field': 'en',
                                      'target_field': 'pl', 'sheet_name': ''})
    assert profile.comment_field == ''


def test_async_single_segment_qa_discards_previous_edit():
    from concurrent.futures import Future
    from types import SimpleNamespace
    _QueuedTimer.calls = []
    first, second = Future(), Future()
    future_values = iter((first, second))
    fake = SimpleNamespace(check_segment_qa_async=lambda *_args: next(future_values))
    selected = SimpleNamespace(id=8, source='Hello', target='A')
    displayed = []
    stub = SimpleNamespace(_qa_generation=0, _qa_future=None, _closing=False,
                           project_service=fake, current_project=SimpleNamespace(id=1),
                           segment_editor=SimpleNamespace(current_segment=lambda: selected),
                           qa_panel=SimpleNamespace(set_issues=displayed.append),
                           statusBar=lambda: SimpleNamespace(showMessage=lambda *_args: None))
    method = _controller('_update_current_qa', {'QTimer': _QueuedTimer})
    method(stub, selected)
    first.set_running_or_notify_cancel()
    selected.target = 'B'
    method(stub, selected)
    first.set_result(['old'])
    second.set_result(['new'])
    _QueuedTimer.drain()
    assert displayed == [['new']]
