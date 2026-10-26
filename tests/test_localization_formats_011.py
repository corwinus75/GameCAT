"""v0.11 localization exchange: test preservation and safe mapping."""
import json
from pathlib import Path
import xml.etree.ElementTree as ET
import pytest

from gamecat.localization.profiles import FormatProfile
from gamecat.localization.exchange import read_source, read_translations, export_translations
from gamecat.localization.xlsx import write_workbook
from gamecat.models.segment import Segment
from gamecat.services.project_service import ProjectService


def test_nested_json_profile_and_template_preserves_untranslated_fields(tmp_path):
    original = tmp_path / 'game.json'
    original.write_text(json.dumps({'version': 7, 'meta': {'author': 'A'}, 'data': [
        {'id': 'a', 'loc': {'en': 'Good morning', 'pl': ''}, 'effect': [1, 2]},
        {'id': 'b', 'loc': {'en': 'Attack', 'pl': 'Stare'}, 'effect': [3]},
    ]}), encoding='utf-8')
    p = FormatProfile('json', records_path='data', key_field='id', source_field='loc.en', target_field='loc.pl')
    imported = list(read_source(original, p))
    assert [(x.key, x.source, x.target) for x in imported] == [('a', 'Good morning', ''), ('b', 'Attack', 'Stare')]
    result = tmp_path / 'translated.json'
    export_translations([Segment('Good morning', 1, 'a', 'Dzień dobry'), Segment('Attack', 2, 'b', 'Atak')], result, p, template_path=original)
    data = json.loads(result.read_text(encoding='utf-8'))
    assert data == {'version': 7, 'meta': {'author': 'A'}, 'data': [
        {'id': 'a', 'loc': {'en': 'Good morning', 'pl': 'Dzień dobry'}, 'effect': [1, 2]},
        {'id': 'b', 'loc': {'en': 'Attack', 'pl': 'Atak'}, 'effect': [3]},
    ]}
    assert [(t.key, t.target) for t in read_translations(result, p)] == [('a', 'Dzień dobry'), ('b', 'Atak')]


def test_nested_json_rejects_source_mismatch_and_does_not_touch_output(tmp_path):
    original = tmp_path / 'game.json'
    original.write_text('{"dialogues":[{"id":"x","source":"Changed","target":""}]}', encoding='utf-8')
    output = tmp_path / 'out.json'
    output.write_text('KEEP', encoding='utf-8')
    profile = FormatProfile('json', records_path='dialogues', key_field='id')
    with pytest.raises(ValueError, match='Source|źródł'):
        export_translations([Segment('Old', 1, 'x', 'PL')], output, profile, template_path=original)
    assert output.read_text() == 'KEEP'


def test_xml_profile_keeps_attributes_and_other_tags(tmp_path):
    original = tmp_path / 'game.xml'
    original.write_text('<strings version="1"><entry id="q1" emotion="happy"><en>Hello</en><pl>old</pl><sound>abc</sound></entry></strings>', encoding='utf-8')
    profile = FormatProfile('xml', records_path='.//entry', key_field='@id', source_field='en', target_field='pl')
    assert [(x.key, x.source) for x in read_source(original, profile)] == [('q1', 'Hello')]
    result = tmp_path / 'translated.xml'
    export_translations([Segment('Hello', 1, 'q1', 'Witaj')], result, profile, template_path=original)
    root = ET.parse(result).getroot()
    assert root.attrib == {'version': '1'}
    assert root.find('entry').attrib == {'id': 'q1', 'emotion': 'happy'}
    assert root.find('entry/sound').text == 'abc'
    assert root.find('entry/pl').text == 'Witaj'


def test_tsv_utf8_and_quoted_multiline_fields(tmp_path):
    file = tmp_path / 'source.tsv'
    file.write_text('id\tsource\ttarget\n1\t"Hello\nfriend"\t"Witaj\nprzyjacielu"\n', encoding='utf-8-sig')
    profile = FormatProfile('tsv', key_field='id')
    source = list(read_source(file, profile))
    assert (source[0].source, source[0].target) == ('Hello\nfriend', 'Witaj\nprzyjacielu')
    out = tmp_path / 'export.tsv'
    export_translations([Segment(source[0].source, 1, '1', 'Nowy\nwiersz')], out, profile)
    assert list(read_source(out, profile))[0].target == 'Nowy\nwiersz'


def test_xlsx_read_write_unicode_multiple_sheets(tmp_path):
    original = tmp_path / 'original.xlsx'
    write_workbook(original, {'Meta': [['Name', 'Value'], ['title', 'game']], 'Strings': [
        ['id', 'source', 'target'], ['a', 'Hello', ''], ['b', 'Dragon', 'Smok'],
    ]})
    profile = FormatProfile('xlsx', sheet_name='Strings', key_field='id')
    got = list(read_source(original, profile))
    assert [(r.key, r.source, r.target) for r in got] == [('a', 'Hello', ''), ('b', 'Dragon', 'Smok')]
    dest = tmp_path / 'translation.xlsx'
    export_translations([Segment('Hello', 1, 'a', 'Witaj'), Segment('Dragon', 2, 'b', 'Smok')], dest, profile, template_path=original)
    assert [(r.target) for r in read_source(dest, profile)] == ['Witaj', 'Smok']
    assert list(read_source(dest, FormatProfile('xlsx', sheet_name='Meta', key_field='Name', source_field='Value', target_field='Value')))[0].source == 'game'


def test_service_profile_saved_and_imports_extra_formats(tmp_path):
    db = tmp_path / 'prj.db'
    service = ProjectService(db)
    try:
        project = service.create_project('P', 'en', 'pl', 'tsv')
        profile = FormatProfile('tsv', key_field='id')
        service.set_format_profile(project, profile)
        assert service.get_format_profile(project, 'tsv') == profile
        tsv = tmp_path / 'source.tsv'
        tsv.write_text('id\tsource\ttarget\nk\tHello\tCześć\n', encoding='utf-8')
        imported = service.import_file_async(project, tsv).result(timeout=10)
        assert imported[0].target == 'Cześć'
        assert imported[0].key == 'k'
        destination = tmp_path / 'out.tsv'
        assert service.export_project_async(project, destination, 'tsv').result(timeout=10) == 1
        assert list(read_source(destination, profile))[0].target == 'Cześć'
    finally:
        service.close()


def test_translation_only_tsv_does_not_require_source(tmp_path):
    path = tmp_path / 'translated.tsv'
    path.write_text('id\tpolish\na\tPierwszy\nb\tDrugi\n', encoding='utf-8')
    mapping = FormatProfile('tsv', key_field='id', source_field='english', target_field='polish')
    assert [(x.key, x.target) for x in read_translations(path, mapping)] == [('a', 'Pierwszy'), ('b', 'Drugi')]


def test_translation_only_json_nested_does_not_require_source(tmp_path):
    path = tmp_path / 'translated.json'
    path.write_text('{"translation": [{"id": "a", "pl": "Witaj"}]}', encoding='utf-8')
    profile = FormatProfile('json', records_path='translation', key_field='id', source_field='en', target_field='pl')
    assert [(x.key, x.target) for x in read_translations(path, profile)] == [('a', 'Witaj')]


def test_template_export_refuses_duplicate_keys(tmp_path):
    path = tmp_path / 'template.json'
    path.write_text('{"data":[{"key":"dup","source":"Yes"},{"key":"dup","source":"No"}]}', encoding='utf-8')
    with pytest.raises(ValueError, match='Duplicate template key'):
        export_translations([Segment('Yes', 1, 'dup', 'Tak')], tmp_path / 'out.json',
                            FormatProfile('json', records_path='data'), template_path=path)
    assert not (tmp_path / 'out.json').exists()


def test_service_import_translation_mapped_xlsx_matches_keys(tmp_path):
    service = ProjectService(tmp_path / 'p.db')
    try:
        project = service.create_project('P', 'en', 'pl', 'json')
        src = tmp_path / 'src.json'
        src.write_text('[{"key":"a","source":"One"},{"key":"b","source":"Two"}]', encoding='utf-8')
        service.import_file_async(project, src).result(timeout=5)
        table = tmp_path / 'translated.xlsx'
        write_workbook(table, {'Sheet1': [['identifier', 'translation'], ['b', 'Dwa'], ['a', 'Jeden']]})
        service.set_format_profile(project, FormatProfile('xlsx', key_field='identifier',
                                                         source_field='missing', target_field='translation'))
        result = service.import_translation_file_async(project, table).result(timeout=5)
        assert result.updated == 2
        assert [r.target for r in service.list_segments(project.id)] == ['Jeden', 'Dwa']

    finally:
        service.close()


def test_service_export_to_original_template_survives_reopen(tmp_path):
    db = tmp_path / 'project.sqlite'
    base = tmp_path / 'source.json'
    base.write_text('{"unused": 4, "records": [{"id":"one","en":"Hello","pl":"", "speaker":"A"}]}', encoding='utf-8')
    profile = FormatProfile('json', records_path='records', key_field='id', source_field='en', target_field='pl')
    service = ProjectService(db)
    try:
        project = service.create_project('P', 'en', 'pl', 'json')
        service.set_format_profile(project, profile)
        service.import_file_async(project, base).result(timeout=5)
        segment = service.list_segments(project.id)[0]
        segment.target = 'Witaj'
        service.save_segment(segment)
    finally:
        service.close()
    reopened = ProjectService(db)
    try:
        project = reopened.list_projects()[0]
        assert reopened.get_format_profile(project, 'json') == profile
        output = tmp_path / 'game_pl.json'
        assert reopened.export_using_template_async(project, base, output).result(timeout=5) == 1
        assert json.loads(output.read_text(encoding='utf-8')) == {
            'unused': 4, 'records': [{'id': 'one', 'en': 'Hello', 'pl': 'Witaj', 'speaker': 'A'}]
        }
    finally:
        reopened.close()


def test_old_json_import_unchanged_without_profile(tmp_path):
    service = ProjectService(tmp_path / 'project.db')
    try:
        project = service.create_project('P', 'en', 'pl', 'json')
        file = tmp_path / 'legacy.json'
        file.write_text('{"key-1":"Text"}', encoding='utf-8')
        rows = service.import_file_async(project, file).result(timeout=5)
        assert (rows[0].key, rows[0].source) == ('key-1', 'Text')
    finally:
        service.close()


def test_xml_dtd_is_rejected(tmp_path):
    path = tmp_path / 'payload.xml'
    path.write_text('<!DOCTYPE xml [<!ENTITY example "EXPANSION">]><xml><entry><source>&example;</source></entry></xml>', encoding='utf-8')
    with pytest.raises(ValueError, match='DTD'):
        list(read_source(path, FormatProfile('xml', records_path='.//entry', key_field='')))


def test_translation_override_profile_does_not_replace_source_profile(tmp_path):
    service = ProjectService(tmp_path / 'proj.sqlite')
    try:
        project = service.create_project('P', 'en', 'pl', 'json')
        src = tmp_path / 'source.json'
        src.write_text('{"dialogues":[{"id":"a","text":{"en":"Hello","pl":""}}]}',encoding='utf-8')
        source_profile = FormatProfile('json', records_path='dialogues', key_field='id',
                                       source_field='text.en', target_field='text.pl')
        service.set_format_profile(project, source_profile)
        service.import_file_async(project, src).result(timeout=5)
        translated = tmp_path / 'target.json'
        translated.write_text('{"translations":[{"id":"a","translation":"Witaj"}]}',encoding='utf-8')
        translation_profile = FormatProfile('json', records_path='translations', key_field='id',
                                            source_field='unused', target_field='translation')
        result = service.import_translation_file_async(
            project, translated, format_profile=translation_profile
        ).result(timeout=5)
        assert result.updated == 1
        assert service.get_format_profile(project, 'json') == source_profile
        output = tmp_path / 'out.json'
        service.export_using_template_async(project, src, output).result(timeout=5)
        assert json.loads(output.read_text())['dialogues'][0]['text']['pl'] == 'Witaj'
    finally:
        service.close()


def test_import_of_pretranslated_tabular_source_marks_translated(tmp_path):
    from gamecat.models.segment import SegmentStatus
    service = ProjectService(tmp_path / 'project.db')
    try:
        project = service.create_project('P', 'en', 'pl', 'tsv')
        src = tmp_path / 'pretranslated.tsv'
        src.write_text('key\tsource\ttarget\na\tHello\tWitaj\n', encoding='utf-8')
        segments = service.import_file_async(project, src).result(timeout=5)
        assert segments[0].status is SegmentStatus.TRANSLATED
    finally:
        service.close()
