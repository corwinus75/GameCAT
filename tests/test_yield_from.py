"""Testy generatorów delegujących przez ``yield from`` (import lokalizacji i reguły QA)."""
from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from gamecat.localization.exchange import read_source, read_translations
from gamecat.localization.profiles import FormatProfile
from gamecat.qa.rules import iter_issues, run_rules


def test_read_source_is_lazy_dispatcher(tmp_path: Path) -> None:
    """Dyspozytor jest generatorem: błąd formatu pojawia się dopiero przy pobraniu elementu."""
    path = tmp_path / 'demo.txt'
    path.write_text('Jeden\nDwa\n', encoding='utf-8')
    assert inspect.isgeneratorfunction(read_source)
    stream = read_source(path, FormatProfile('json'))  # niezgodny profil – jeszcze bez błędu
    with pytest.raises(ValueError):
        next(stream)
    assert [item.source for item in read_source(path, FormatProfile('txt'))] == ['Jeden', 'Dwa']


def test_read_translations_delegates_to_format_reader(tmp_path: Path) -> None:
    """Tłumaczenia z TSV są delegowane do czytnika tabel i zachowują klucze."""
    path = tmp_path / 'demo.tsv'
    path.write_text('key\tsource\ttarget\na\tHello\tCześć\n', encoding='utf-8')
    items = list(read_translations(path, FormatProfile('tsv')))
    assert [(item.key, item.target) for item in items] == [('a', 'Cześć')]


def test_qa_rule_groups_are_chained_in_order() -> None:
    """``iter_issues`` łączy grupy reguł: placeholdery, potem treść."""
    issues = iter_issues('Hello {name}', 'Witaj  ')
    assert inspect.isgenerator(issues)
    codes = [issue.code for issue in issues]
    assert codes == ['placeholder-missing', 'edge-whitespace', 'double-space']
    assert [i.code for i in run_rules('Hello {name}', 'Witaj  ')] == codes
