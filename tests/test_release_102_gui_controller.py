"""Exercise actual project-open controller logic without Qt in CI."""
from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

from gamecat.models.translation_memory import TranslationMemoryEntry
from gamecat.services.project_service import ProjectService


def open_method():
    path = Path(__file__).resolve().parents[1] / 'gamecat/gui/main_window.py'
    root = ast.parse(path.read_text(encoding='utf-8'))
    cls = next(n for n in root.body if isinstance(n, ast.ClassDef) and n.name == 'MainWindow')
    function = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'open_project_dialog')
    scope = {'Path': Path, 'ProjectService': ProjectService}
    return function, scope, path


def test_open_dialog_selects_second_project_and_its_external_tm(tmp_path: Path):
    db = tmp_path / 'projects.sqlite'
    svc = ProjectService(db)
    p1 = svc.create_project('First', 'en', 'pl', 'txt')
    svc.attach_tm_database(p1, tmp_path / 'first.sqlite')
    svc.translation_memory.create(TranslationMemoryEntry('First', 'Pierwszy', 'en', 'pl'))
    p2 = svc.create_project('Second', 'en', 'pl', 'txt')
    svc.attach_tm_database(p2, tmp_path / 'second.sqlite')
    svc.translation_memory.create(TranslationMemoryEntry('Second', 'Drugi', 'en', 'pl'))
    svc.close()
    picked = []
    function, scope, path = open_method()
    scope.update({
        'QFileDialog': SimpleNamespace(getOpenFileName=lambda *args, **kwargs: (str(db), '')),
        'QInputDialog': SimpleNamespace(getItem=lambda parent, title, question, labels, index, editable:
                                        (picked.append(labels) or labels[1], True)),
        'QMessageBox': SimpleNamespace(critical=lambda *args: (_ for _ in ()).throw(AssertionError('unexpected error'))),
    })
    exec(compile(ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[])), str(path), 'exec'), scope)
    chosen = {}
    window = SimpleNamespace(
        _ai_running=False, project_service=None, current_project=None, project_path=None,
        _replace_service=lambda service: chosen.setdefault('service', service),
        glossary_panel=SimpleNamespace(set_terms=lambda value: None),
        tm_panel=SimpleNamespace(set_matches=lambda value: None, set_threshold=lambda value: None,
                                 set_storage_path=lambda value: chosen.setdefault('storage', value)),
        ai_panel=SimpleNamespace(set_settings=lambda value: None),
        qa_panel=SimpleNamespace(clear_project_report=lambda: None),
        segment_editor=SimpleNamespace(clear_filters=lambda: None, set_segments=lambda value: None),
        _refresh_progress=lambda: None, _sync_actions=lambda: None,
        setWindowTitle=lambda value: None,
        statusBar=lambda: SimpleNamespace(showMessage=lambda *args: None),
    )
    try:
        scope['open_project_dialog'](window)
        assert len(picked[0]) == 2 and 'ID:' in picked[0][1]
        assert window.current_project.id == p2.id
        assert chosen['service'].active_project_id == p2.id
        assert [entry.source for entry in chosen['service'].translation_memory.list_all()] == ['Second']
        assert chosen['storage'] == tmp_path / 'second.sqlite'
    finally:
        chosen.get('service') and chosen['service'].close()


def test_cancel_project_selection_keeps_current_project(tmp_path: Path):
    db = tmp_path / 'two.sqlite'
    svc = ProjectService(db)
    svc.create_project('First', 'en', 'pl', 'txt')
    svc.create_project('Second', 'en', 'pl', 'txt')
    svc.close()
    function, scope, path = open_method()
    scope.update({
        'QFileDialog': SimpleNamespace(getOpenFileName=lambda *args, **kwargs: (str(db), '')),
        'QInputDialog': SimpleNamespace(getItem=lambda *args: ('', False)),
        'QMessageBox': SimpleNamespace(critical=lambda *args: (_ for _ in ()).throw(AssertionError('unexpected error'))),
    })
    exec(compile(ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[])), str(path), 'exec'), scope)
    old = object()
    window = SimpleNamespace(
        _ai_running=False, current_project=old, project_service=old,
        _replace_service=lambda service: (_ for _ in ()).throw(AssertionError('should not replace')),
    )
    scope['open_project_dialog'](window)
    assert window.current_project is old and window.project_service is old
