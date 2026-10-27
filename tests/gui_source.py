"""Pomocnicze wyszukiwanie metod okna głównego w kodzie źródłowym (bez Qt).

Od wersji 1.2.6 metody ``MainWindow`` są rozdzielone na mixiny w pakiecie
``gamecat.gui.window``. Testy wykonujące rzeczywiste ciała metod przez AST
szukają ich we wszystkich plikach tworzących okno główne.
"""
from __future__ import annotations

import ast
from pathlib import Path

GUI_DIR = Path(__file__).resolve().parents[1] / 'gamecat' / 'gui'
SOURCES = (GUI_DIR / 'main_window.py', *sorted((GUI_DIR / 'window').glob('*.py')))


def find_method(name: str) -> tuple[ast.FunctionDef, Path]:
    """Zwróć węzeł AST metody *name* z ``MainWindow`` lub jego mixinu oraz ścieżkę pliku."""
    for path in SOURCES:
        tree = ast.parse(path.read_text(encoding='utf-8'))
        for cls in tree.body:
            if not isinstance(cls, ast.ClassDef):
                continue
            if cls.name != 'MainWindow' and not cls.name.endswith('Mixin'):
                continue
            for node in cls.body:
                if isinstance(node, ast.FunctionDef) and node.name == name:
                    return node, path
    raise LookupError(f'Nie znaleziono metody okna głównego: {name}')
