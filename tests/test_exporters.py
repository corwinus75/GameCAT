import csv, json
from pathlib import Path
from gamecat.models.segment import Segment
from gamecat.exporters.txt_exporter import export_txt
from gamecat.exporters.csv_exporter import export_csv
from gamecat.exporters.json_exporter import export_json


def sample_segments():
    return [Segment('Hello', 2, key='b', target='Cześć'), Segment('World', 1, key='a', target='Świat')]


def test_txt_export_orders_and_preserves_unicode(tmp_path: Path):
    p=tmp_path/'x.txt'; export_txt(sample_segments(), p)
    assert p.read_text(encoding='utf-8') == 'Świat\nCześć\n'


def test_csv_export(tmp_path: Path):
    p=tmp_path/'x.csv'; export_csv(sample_segments(), p)
    rows=list(csv.DictReader(p.open(encoding='utf-8', newline='')))
    assert [r['key'] for r in rows] == ['a','b']
    assert rows[0]['target']=='Świat'


def test_json_export_dict_and_list_and_empty(tmp_path: Path):
    p=tmp_path/'x.json'; export_json(sample_segments(), p, 'dict')
    assert json.loads(p.read_text(encoding='utf-8')) == {'a':'Świat','b':'Cześć'}
    p2=tmp_path/'l.json'; export_json(sample_segments(), p2, 'list')
    assert json.loads(p2.read_text(encoding='utf-8'))[0]['key']=='a'
    p3=tmp_path/'e.json'; export_json([], p3, 'list')
    assert json.loads(p3.read_text(encoding='utf-8')) == []
