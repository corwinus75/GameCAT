from pathlib import Path
import pytest

from gamecat.database.connection import open_database
from gamecat.database.schema import initialize_schema
from gamecat.database.repositories import GlossaryRepository
from gamecat.models.glossary import GlossaryTerm
from gamecat.services.glossary_service import GlossaryService


def _service(tmp_path: Path):
    conn=open_database(tmp_path/'g.db'); initialize_schema(conn)
    conn.execute("INSERT INTO projects(name,source_language,target_language,source_format,created_at,updated_at) VALUES('P','en','pl','txt','x','x')"); conn.commit()
    return conn, GlossaryService(GlossaryRepository(conn),1)


def test_service_crud_search_and_matching(tmp_path: Path):
    conn, service = _service(tmp_path)
    term=service.create_term(GlossaryTerm('sword',['miecz','ostrze']))
    assert term.project_id == 1 and term.id
    assert [t.source_term for t in service.find_terms('Take the sword.')] == ['sword']
    assert service.find_terms('A swordsman.') == []
    assert [t.source_term for t in service.search('ostrze')] == ['sword']
    assert service.add_variant(term.id,'miecz') is False
    assert service.add_variant(term.id,'szabla') is True
    conn.close()


def test_removing_last_variant_is_rejected(tmp_path: Path):
    conn, service = _service(tmp_path)
    term=service.create_term(GlossaryTerm('quest',['zadanie']))
    with pytest.raises(ValueError):
        service.remove_variant(term.id,'zadanie')
    conn.close()


def test_save_collision_merges_variants_and_removes_redundant_term(tmp_path: Path):
    conn, service = _service(tmp_path)
    first=service.create_term(GlossaryTerm('sword',['miecz']))
    second=service.create_term(GlossaryTerm('blade',['ostrze']))
    second.source_term='sword'; second.targets=['ostrze','szabla']
    merged=service.save_term(second)
    assert merged.id == first.id
    assert merged.targets == ['miecz','ostrze','szabla']
    assert len(service.search('sword')) == 1
    conn.close()
