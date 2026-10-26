from pathlib import Path

import pytest

from gamecat.gui.file_formats import export_format_from_path, normalized_export_path


def test_export_format_from_path_is_case_insensitive():
    assert export_format_from_path(Path('translation.JSON')) == 'json'


def test_export_format_from_path_rejects_unknown_extension():
    with pytest.raises(ValueError, match='Unsupported export format'):
        export_format_from_path(Path('translation.yaml'))


def test_normalized_export_path_adds_selected_extension_when_missing():
    assert normalized_export_path(Path('translation'), 'csv') == Path('translation.csv')


def test_normalized_export_path_keeps_supported_existing_extension():
    assert normalized_export_path(Path('translation.txt'), 'json') == Path('translation.txt')


def test_export_format_from_path_accepts_new_formats():
    assert [export_format_from_path(Path("a." + e)) for e in ("tsv", "xlsx", "xml")] == ["tsv", "xlsx", "xml"]
