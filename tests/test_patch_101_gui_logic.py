"""Exercise selected GUI controller methods without requiring Qt bindings.

These tests execute the actual method bodies extracted via AST with fake widget
adapters. Full widget/signal coverage remains in test_patch_101_gui.py.
"""
from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

from gamecat.ai.core import AISettings
from gamecat.services.project_service import ProjectService


def gui_method(name: str):
    path = Path(__file__).resolve().parents[1] / 'gamecat/gui/main_window.py'
    root = ast.parse(path.read_text(encoding='utf-8'))
    main_window = next(node for node in root.body if isinstance(node, ast.ClassDef) and node.name == 'MainWindow')
    function = next(node for node in main_window.body if isinstance(node, ast.FunctionDef) and node.name == name)
    function.decorator_list = []
    scope: dict = {}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[])), str(path), 'exec'), scope)
    return scope[name]


def test_gui_tm_suggestions_respect_project_threshold(tmp_path: Path):
    service = ProjectService(tmp_path / 'project.sqlite')
    project = service.create_project('Demo', 'en', 'pl', 'txt')
    service.set_tm_threshold(project, 0.91)
    thresholds = []
    real_find = service.find_tm_matches

    def capturing_find(*args, **kwargs):
        thresholds.append(kwargs.get('threshold'))
        return real_find(*args, **kwargs)

    service.find_tm_matches = capturing_find
    matches = []
    stub = SimpleNamespace(project_service=service, current_project=project,
                           tm_panel=SimpleNamespace(set_matches=lambda value: matches.append(value)))
    try:
        gui_method('_update_current_tm')(stub, SimpleNamespace(source='Test'))
        assert thresholds == [None], 'The controller must defer to the persisted project threshold'
        assert matches == [[]]
    finally:
        service.close()


def test_switching_tm_backend_does_not_touch_ai_panel_settings(tmp_path: Path):
    service = ProjectService(tmp_path / 'project.sqlite')
    project = service.create_project('Demo', 'en', 'pl', 'txt')
    expected = AISettings(model='gpt-5-mini', instructions='Use my proper nouns')
    service.set_ai_settings(project, expected)
    panel_changes = []
    panel = SimpleNamespace(set_settings=lambda settings: panel_changes.append(settings))
    tm_paths = []
    statuses = []
    stub = SimpleNamespace(
        project_service=service, current_project=project, ai_panel=panel,
        tm_panel=SimpleNamespace(set_storage_path=lambda p: tm_paths.append(p)),
        _ai_preview_context='previous',
        _refresh_tm_context=lambda: None, _refresh_search_context=lambda: None,
        statusBar=lambda: SimpleNamespace(showMessage=lambda *args: statuses.append(args)),
    )
    try:
        gui_method('_safe_use_project_tm_database')(stub)
        assert tm_paths == [None]
        assert panel_changes == []
        assert service.get_ai_settings(project).instructions == 'Use my proper nouns'
        assert stub._ai_preview_context is None
        assert statuses
    finally:
        service.close()
