from pathlib import Path
import json

from gamecat.models.glossary import GlossaryTerm
from gamecat.services.project_service import ProjectService


def test_project_service_glossary_crud_import_export_is_project_only(tmp_path: Path):
    service=ProjectService(tmp_path/'p.db')
    p=service.create_project('P','en','pl','txt')
    q=service.create_project('Q','en','pl','txt')
    try:
        term=service.create_glossary_term(p.id, GlossaryTerm('sword',['miecz']))
        service.create_glossary_term(q.id, GlossaryTerm('shield',['tarcza']))
        assert [t.source_term for t in service.list_glossary(p.id)]==['sword']
        service.add_glossary_variant(p.id,term.id,'ostrze')
        assert service.list_glossary(p.id)[0].targets==['miecz','ostrze']

        incoming=tmp_path/'in.json'; incoming.write_text(json.dumps([{'source':'sword','targets':['ostrze','szabla']},{'source':'quest','targets':['zadanie']}]),encoding='utf-8')
        result=service.import_glossary_file_async(p.id,incoming).result(timeout=5)
        assert (result.new_terms,result.new_variants,result.duplicates)==(1,2,1)
        out=tmp_path/'out.json'
        count=service.export_glossary_file_async(p.id,out).result(timeout=5)
        assert count==2
        assert {x['source'] for x in json.loads(out.read_text(encoding='utf-8'))}=={'sword','quest'}
    finally:
        service.close()
