import json
from pathlib import Path
import pytest
from gamecat.importers.txt_importer import import_txt
from gamecat.importers.csv_importer import import_csv
from gamecat.importers.json_importer import import_json


def test_txt_import_and_empty(tmp_path: Path):
    p = tmp_path/'a.txt'; p.write_text('Hello\nWorld\n', encoding='utf-8')
    rows = list(import_txt(p))
    assert [(r.position, r.source) for r in rows] == [(1,'Hello'),(2,'World')]
    e = tmp_path/'e.txt'; e.write_text('', encoding='utf-8')
    assert list(import_txt(e)) == []


def test_txt_invalid_utf8_is_clear(tmp_path: Path):
    p = tmp_path/'bad.txt'; p.write_bytes(b'\xff\xfe')
    with pytest.raises(UnicodeError): list(import_txt(p))


def test_csv_import_and_missing_columns(tmp_path: Path):
    p = tmp_path/'a.csv'; p.write_text('id,source,target\nk1,Hello,Czesc\n', encoding='utf-8')
    row = list(import_csv(p, 'id', 'source', 'target'))[0]
    assert (row.key,row.source,row.target)==('k1','Hello','Czesc')
    with pytest.raises(ValueError, match='Missing CSV column'):
        list(import_csv(p, 'missing', 'source'))


def test_json_dict_and_list(tmp_path: Path):
    p = tmp_path/'d.json'; p.write_text(json.dumps({'a':'Hello','b':'World'}), encoding='utf-8')
    assert [(r.key,r.source) for r in import_json(p)] == [('a','Hello'),('b','World')]
    p.write_text(json.dumps([{'key':'x','source':'Hi','target':'Hej'}]), encoding='utf-8')
    row = list(import_json(p))[0]
    assert (row.key,row.source,row.target)==('x','Hi','Hej')
