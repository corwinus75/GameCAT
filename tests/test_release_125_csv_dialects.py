"""Regression for semicolon CSV localization files (Id;Loca)."""
from pathlib import Path

import pytest

from gamecat.importers.csv_format import detect_csv_delimiter, read_csv_headers, suggest_source_columns
from gamecat.importers.csv_importer import import_csv
from gamecat.importers.translation_importer import import_translation_csv
from gamecat.localization.exchange import read_source, export_translations
from gamecat.localization.profiles import FormatProfile
from gamecat.services.project_service import ProjectService
from gamecat.models.segment import Segment, SegmentStatus


SAMPLE = ('Id;Loca\r\n'
          'InvasionAlchemist.Loca;Palos, the alchemist\r\n'
          'Invasion_Falirson_Leader.Description;[fluff]You led your clan.[/]\\n\\n[yellow]Warleader[/]\\nLead your army.\r\n'
          'Invasion_Falirson_Hunter.Name;Ranged Beastmaster\r\n')


def test_header_semicolon_comma_inside_source_and_escaped_newlines(tmp_path: Path):
    path = tmp_path / 'fg2.csv'
    path.write_bytes(SAMPLE.encode('utf-8'))
    assert detect_csv_delimiter(path) == ';'
    assert read_csv_headers(path) == ['Id', 'Loca']
    assert suggest_source_columns(read_csv_headers(path)) == ('Id', 'Loca', None)
    rows = list(import_csv(path, 'Id', 'Loca'))
    assert len(rows) == 3
    assert rows[0].source == 'Palos, the alchemist'
    assert rows[1].source == '[fluff]You led your clan.[/]\\n\\n[yellow]Warleader[/]\\nLead your army.'
    assert rows[2].key == 'Invasion_Falirson_Hunter.Name'
    assert all(not row.target for row in rows)


def test_project_service_auto_columns_on_semicolon_csv(tmp_path: Path):
    service = ProjectService(tmp_path / 'project.db')
    try:
        project = service.create_project('FG2', 'en', 'pl', 'csv')
        path = tmp_path / 'invasion.csv'
        path.write_bytes(SAMPLE.encode('utf-8'))
        rows = service.import_file_async(project, path).result(timeout=8)
        assert len(rows) == 3
        assert [s.key for s in rows] == [
            'InvasionAlchemist.Loca', 'Invasion_Falirson_Leader.Description',
            'Invasion_Falirson_Hunter.Name'
        ]
        assert [s.position for s in rows] == [1, 2, 3]
        assert all(s.status is SegmentStatus.NEW for s in rows)
    finally:
        service.close()


def test_translation_semicolon_csv_and_quoted_field(tmp_path: Path):
    path = tmp_path / 'pl.csv'
    path.write_text('Id;Polish\nX1;"Witaj; podróżniku"\n', encoding='utf-8-sig')
    assert [(r.key, r.target) for r in import_translation_csv(path, 'Id', 'Polish')] == [
        ('X1', 'Witaj; podróżniku')
    ]


def test_mapped_csv_and_template_export_preserve_semicolon(tmp_path: Path):
    original = tmp_path / 'source.csv'
    original.write_text('Id;Loca;Notes\nA;Hello;meta\nB;World;other\n', encoding='utf-8')
    profile = FormatProfile('csv', key_field='Id', source_field='Loca', target_field='Polish')
    rows = list(read_source(original, profile))
    assert [(r.key, r.source, r.target) for r in rows] == [('A','Hello',''), ('B','World','')]
    target = tmp_path / 'translation.csv'
    export_translations([Segment('Hello', 1, 'A', 'Cześć'), Segment('World', 2, 'B', 'Świat')],
                        target, profile, template_path=original)
    assert target.read_text(encoding='utf-8-sig') == 'Id;Loca;Notes;Polish\nA;Hello;meta;Cześć\nB;World;other;Świat\n'


def test_commas_quoted_fields_and_bom_unchanged(tmp_path: Path):
    file = tmp_path / 'standard.csv'
    file.write_text('id,source,target\na,"One, two",Dwa\n', encoding='utf-8-sig')
    assert detect_csv_delimiter(file) == ','
    assert [(r.key, r.source, r.target) for r in import_csv(file, 'id', 'source', 'target')] == [('a','One, two','Dwa')]


def test_malformed_csv_has_clear_failure_instead_of_dropping_columns(tmp_path: Path):
    file = tmp_path / 'bad.csv'
    file.write_text('Id;Loca\nA;Hello;unexpected\n', encoding='utf-8')
    with pytest.raises(ValueError, match='Malformed CSV record'):
        list(import_csv(file, 'Id', 'Loca'))


def test_empty_csv_header_is_rejected(tmp_path: Path):
    file = tmp_path / 'empty.csv'
    file.write_text('', encoding='utf-8')
    with pytest.raises(ValueError, match='pusty'):
        read_csv_headers(file)


def test_keyless_source_target_csv_gets_positional_keys(tmp_path: Path):
    path = tmp_path / 'keyless.csv'
    path.write_text('source;target\nHello;Witaj\nWorld;Świat\n', encoding='utf-8')
    mapping = suggest_source_columns(read_csv_headers(path))
    assert mapping == (None, 'source', 'target')
    assert [(r.key, r.source, r.target) for r in import_csv(path, *mapping)] == [
        (None, 'Hello', 'Witaj'), (None, 'World', 'Świat')
    ]


def test_single_source_column_works_without_keys(tmp_path: Path):
    path = tmp_path / 'single.csv'
    path.write_text('source\nHello\nWorld\n', encoding='utf-8')
    mapping = suggest_source_columns(read_csv_headers(path))
    assert mapping == (None, 'source', None)
    assert [row.source for row in import_csv(path, *mapping)] == ['Hello', 'World']
