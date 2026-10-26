from pathlib import Path
import json
import pytest

from gamecat.database.connection import open_database
from gamecat.database.schema import initialize_schema
from gamecat.database.repositories import GlossaryRepository
from gamecat.glossary.importers import import_glossary_csv, import_glossary_json
from gamecat.glossary.exporters import export_glossary_csv, export_glossary_json
from gamecat.models.glossary import GlossaryTerm


def _repo(tmp_path: Path):
    conn=open_database(tmp_path/'g.db'); initialize_schema(conn)
    conn.execute("INSERT INTO projects(name,source_language,target_language,source_format,created_at,updated_at) VALUES('P','en','pl','txt','x','x')"); conn.commit()
    return conn, GlossaryRepository(conn)


def test_csv_import_merges_variants_and_accepts_utf8_sig(tmp_path: Path):
    conn, repo = _repo(tmp_path)
    repo.create_term(GlossaryTerm('sword',['miecz'],project_id=1))
    path=tmp_path/'g.csv'
    path.write_text('source,target,description,case_sensitive\nsword,miecz,Broń,false\nsword,ostrze,Broń,false\nshield,tarcza,,false\n,brak,,false\n',encoding='utf-8-sig')
    result=import_glossary_csv(path,repo,1)
    assert (result.new_terms,result.new_variants,result.duplicates,result.invalid_rows)==(1,2,1,1)
    assert repo.get_by_identity(1,'sword',False).targets==['miecz','ostrze']
    conn.close()


def test_json_import_and_canonical_exports(tmp_path: Path):
    conn, repo=_repo(tmp_path)
    path=tmp_path/'g.json'
    path.write_text(json.dumps([{'source':'XP','targets':['PD','punkty doświadczenia'],'description':'Stat','case_sensitive':True}],ensure_ascii=False),encoding='utf-8')
    result=import_glossary_json(path,repo,1)
    assert (result.new_terms,result.new_variants)==(1,2)
    terms=repo.list_terms(1)
    csv_out=tmp_path/'out.csv'; json_out=tmp_path/'out.json'
    assert export_glossary_csv(csv_out,terms)==2
    assert export_glossary_json(json_out,terms)==1
    assert csv_out.read_text(encoding='utf-8').splitlines()[0]=='source,target,description,case_sensitive'
    payload=json.loads(json_out.read_text(encoding='utf-8'))
    assert payload==[{'source':'XP','targets':['PD','punkty doświadczenia'],'description':'Stat','case_sensitive':True}]
    conn.close()


def test_structural_errors_do_not_modify_database(tmp_path: Path):
    conn, repo=_repo(tmp_path)
    bad_csv=tmp_path/'bad.csv'; bad_csv.write_text('foo,target\nx,y\n',encoding='utf-8')
    with pytest.raises(ValueError): import_glossary_csv(bad_csv,repo,1)
    assert repo.list_terms(1)==[]
    bad_json=tmp_path/'bad.json'; bad_json.write_text('{"source":"x"}',encoding='utf-8')
    with pytest.raises(ValueError): import_glossary_json(bad_json,repo,1)
    assert repo.list_terms(1)==[]
    conn.close()


def test_json_entry_with_blank_variant_is_invalid_as_a_whole(tmp_path: Path):
    conn, repo=_repo(tmp_path)
    path=tmp_path/'invalid-entry.json'
    path.write_text(json.dumps([{'source':'sword','targets':['miecz','']}]),encoding='utf-8')
    result=import_glossary_json(path,repo,1)
    assert result.invalid_rows == 1
    assert repo.list_terms(1) == []
    conn.close()
