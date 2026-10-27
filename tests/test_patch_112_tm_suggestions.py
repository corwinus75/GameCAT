"""Testy regresyjne odwołań do segmentów i wyróżniania bieżącej sugestii TM."""
from __future__ import annotations

import importlib.util
import os

import pytest

from gamecat.models.segment import Segment
from gamecat.models.translation_memory import TranslationMemoryEntry
from gamecat.services.project_service import ProjectService
from gamecat.tm.matcher import TMMatch, TMSegmentReference
from gamecat.tm.presentation import display_tm_match


def test_tm_matches_link_actual_segments_and_prioritize_selected_pair(tmp_path):
    service = ProjectService(tmp_path / 'project.sqlite')
    try:
        project = service.create_project('Dialogues', 'en', 'pl', 'txt')
        other = service.create_project('Other', 'en', 'pl', 'txt')
        first, duplicate, differing = service.segments.create_many([
            Segment('Guard!', 12, target='Straż!', project_id=project.id),
            Segment('Guard!', 18, target='Straż!', project_id=project.id),
            Segment('Guard!', 19, target='Warta!', project_id=project.id),
        ])
        service.segments.create(Segment('Guard!', 4, target='Straż!', project_id=other.id))
        # Six exact-source TM options before the selected segment's translation.
        for number in range(6):
            service.translation_memory.create(TranslationMemoryEntry('Guard!', f'Inna wersja {number}', 'en', 'pl'))
        selected_entry = service.translation_memory.create(TranslationMemoryEntry('Guard!', 'Straż!', 'en', 'pl'))
        alternative = service.translation_memory.create(TranslationMemoryEntry('Guard!', 'Warta!', 'en', 'pl'))
        results = service.find_tm_matches(project, 'Guard!', limit=5,
                                         current_segment_id=first.id,
                                         current_target='Straż!', current_position=12)
        assert len(results) == 5
        assert results[0].entry.id == selected_entry.id
        assert results[0].score == 1.0
        assert results[0].is_current_segment
        assert [(ref.id, ref.position) for ref in results[0].segment_references] == [
            (first.id, 12), (duplicate.id, 18),
        ]
        # Same Source but another Target must not be mistaken for the current item.
        alt = service.find_tm_matches(project, 'Guard!', limit=10,
                                     current_segment_id=first.id,
                                     current_target='Straż!', current_position=12)
        differing_match = next(m for m in alt if m.entry.id == alternative.id)
        assert not differing_match.is_current_segment
        assert differing_match.segment_references == (TMSegmentReference(differing.id, 19),)
        unrelated = next(m for m in alt if m.entry.target == 'Inna wersja 0')
        assert unrelated.segment_references == ()
    finally:
        service.close()


def test_tm_references_without_selected_segment_remain_backward_compatible(tmp_path):
    service = ProjectService(tmp_path / 'database.sqlite')
    try:
        project = service.create_project('P', 'en', 'pl', 'txt')
        segment = service.segments.create(Segment('Hello', 42, target='Cześć', project_id=project.id))
        service.translation_memory.create(TranslationMemoryEntry('Hello', 'Cześć', 'en', 'pl'))
        ordinary = service.find_tm_matches(project, 'Hello')
        assert ordinary[0].segment_references == ()
        assert not ordinary[0].is_current_segment
        annotated = service.find_tm_matches(project, 'Hello', current_segment_id=segment.id,
                                            current_target='Cześć', current_position=42)
        assert annotated[0].is_current_segment
        assert annotated[0].segment_references == (TMSegmentReference(segment.id, 42),)
        # During autosave the edited target may not yet be persisted in SQLite.
        changed = service.find_tm_matches(project, 'Hello', current_segment_id=segment.id,
                                          current_target='Inny tekst', current_position=42)
        assert not changed[0].is_current_segment
        assert changed[0].segment_references == ()  # stale SQLite state during autosave
    finally:
        service.close()


def test_tm_match_presentation_avoids_confusing_tm_id_and_segment_id():
    entry = TranslationMemoryEntry('Hello', 'Cześć', 'en', 'pl', id=555)
    current = TMMatch(entry, 1.0, (TMSegmentReference(12, 5), TMSegmentReference(99, 7)), True)
    label, tooltip = display_tm_match(current)
    assert 'BIEŻĄCY' in label
    assert '100%' in label and '101%' not in label
    assert 'ID seg.: 12 (poz. 5), 99 (poz. 7)' in label
    assert 'TM ID: 555' in tooltip
    external_label, external_tooltip = display_tm_match(TMMatch(entry, .82))
    assert '82%' in external_label
    assert 'brak ID segmentu' in external_label
    assert 'TM ID: 555' in external_label
    assert 'BIEŻĄCY' not in external_tooltip


@pytest.mark.skipif(importlib.util.find_spec('PySide6') is None, reason='PySide6 unavailable')
def test_tm_panel_renders_current_suggestion_bold_and_keeps_double_click():
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtWidgets import QApplication
    from gamecat.gui.tm_panel import TMPanel

    app = QApplication.instance() or QApplication([])
    panel = TMPanel()
    try:
        match = TMMatch(TranslationMemoryEntry('Hello', 'Cześć', 'en', 'pl', id=9), 1.0,
                        (TMSegmentReference(123, 6),), True)
        panel.set_matches([match])
        row = panel.list_widget.item(0)
        assert row.font().bold()
        assert 'ID seg.: 123' in row.text()
        assert 'BIEŻĄCY' in row.text()
        assert '100%' in row.text()
        selected = []
        panel.target_selected.connect(selected.append)
        panel._use_match(row)
        assert selected == ['Cześć']
    finally:
        panel.close()


def test_tm_references_large_duplicate_group_reveals_all_ids_in_tooltip():
    entry = TranslationMemoryEntry('Go', 'Idź', 'en', 'pl', id=901)
    match = TMMatch(entry, 1.0, tuple(TMSegmentReference(index, index * 5) for index in range(1, 7)))
    label, tooltip = display_tm_match(match)
    assert 'ID seg.: 1 (poz. 5), 2 (poz. 10), 3 (poz. 15)' in label
    assert '+3;' in label
    assert '6 (poz. 30)' in tooltip


def test_current_pair_not_fabricated_when_translation_missing_from_tm(tmp_path):
    service = ProjectService(tmp_path / 'db.sqlite')
    try:
        project = service.create_project('P', 'en', 'pl', 'txt')
        segment = service.segments.create(Segment('Hello', 8, target='Cześć', project_id=project.id))
        service.translation_memory.create(TranslationMemoryEntry('Hello', 'Witaj', 'en', 'pl'))
        result = service.find_tm_matches(project, 'Hello', current_segment_id=segment.id,
                                         current_target='Cześć', current_position=8)
        assert len(result) == 1
        assert result[0].entry.target == 'Witaj'
        assert result[0].score == 1.0  # Same source, different translation.
        assert not result[0].is_current_segment
        assert result[0].segment_references == ()
    finally:
        service.close()


def test_async_tm_suggestions_preserve_current_segment_snapshot(tmp_path):
    service = ProjectService(tmp_path / 'db.sqlite')
    try:
        project = service.create_project('P', 'en', 'pl', 'txt')
        segment = service.segments.create(Segment('Hello', 9, target='Cześć', project_id=project.id))
        service.translation_memory.create(TranslationMemoryEntry('Hello', 'Cześć', 'en', 'pl'))
        result = service.find_tm_matches_async(project, 'Hello', current_segment_id=segment.id,
                                                current_target='Cześć', current_position=9).result(timeout=5)
        assert result[0].is_current_segment
        assert result[0].segment_references == (TMSegmentReference(segment.id, 9),)
    finally:
        service.close()


def test_editing_target_debounces_tm_highlight_refresh():
    """Wykonaj rzeczywistą metodę okna głównego z atrapami, bez Qt."""
    import ast
    from types import SimpleNamespace

    from gui_source import find_method
    method, gui_path = find_method('_on_segment_modified')
    method.decorator_list = []
    class Scheduled:
        callbacks = []
        @classmethod
        def singleShot(cls, interval, callback):
            assert interval >= 100
            cls.callbacks.append(callback)
    scope = {'QTimer': Scheduled}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[])), str(gui_path), 'exec'), scope)

    segment = SimpleNamespace(id=12, source='Source', target='First')
    refreshes, clearings = [], []
    stub = SimpleNamespace(
        _content_generation=0, _tm_last_requested=(12, 'Source', 'First'),
        _tm_generation=3, _tm_future=None, _closing=False,
        _pending_qa_jump=None,
        segment_editor=SimpleNamespace(current_segment=lambda: segment,
                                       quality_filter=SimpleNamespace(currentData=lambda: 'all')),
        _save_modified_segment=lambda *_: None,
        _update_current_qa=lambda *_: None,
        _refresh_progress=lambda: None,
        tm_panel=SimpleNamespace(set_matches=clearings.append),
        _update_current_tm=lambda seg: refreshes.append(seg.target),
    )
    on_modify = scope['_on_segment_modified']
    on_modify(stub, segment)  # Comment-only edit -> no TM refresh.
    assert Scheduled.callbacks == []
    segment.target = 'Second'
    on_modify(stub, segment)
    assert clearings == [[]]
    segment.target = 'Third'
    on_modify(stub, segment)
    assert len(Scheduled.callbacks) == 2
    for call in Scheduled.callbacks:
        call()
    assert refreshes == ['Third']
