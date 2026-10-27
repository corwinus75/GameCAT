"""Regression for GameCAT 1.1 MainWindow missing asynchronous state."""
from __future__ import annotations

import ast
from pathlib import Path


GUI_FILE = Path(__file__).resolve().parents[1] / 'gamecat' / 'gui' / 'main_window.py'
EXPECTED_DEFAULTS = {
    '_closing': False,
    '_tm_generation': 0,
    '_qa_generation': 0,
    '_quality_generation': 0,
    '_content_generation': 0,
    '_tm_future': None,
    '_qa_future': None,
    '_quality_future': None,
    '_pending_qa_jump': None,
}


def test_main_window_initializes_all_async_fields_before_connecting_signals():
    """A newly constructed window must support TM/QA updates and closing."""
    module = ast.parse(GUI_FILE.read_text(encoding='utf-8'))
    cls = next(n for n in module.body if isinstance(n, ast.ClassDef) and n.name == 'MainWindow')
    constructor = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == '__init__')

    # Require unconditional assignments directly in __init__, not lazy initialization
    # in one of the callbacks (which can fire during widget setup).
    defaults = {}
    for statement in constructor.body:
        if not isinstance(statement, (ast.Assign, ast.AnnAssign)):
            continue
        targets = statement.targets if isinstance(statement, ast.Assign) else [statement.target]
        for target in targets:
            if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == 'self':
                try:
                    defaults[target.attr] = (ast.literal_eval(statement.value), statement.lineno)
                except (ValueError, TypeError, SyntaxError):
                    pass

    for field, expected in EXPECTED_DEFAULTS.items():
        assert field in defaults, f'MainWindow.__init__ does not initialize {field}'
        value, lineno = defaults[field]
        assert value == expected, f'{field} should start as {expected!r}, got {value!r}'
        assert lineno < next(
            n.lineno for n in ast.walk(constructor)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and n.func.attr == 'connect'
        ), f'{field} is initialized after signal connections'
