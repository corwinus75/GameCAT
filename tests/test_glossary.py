from pathlib import Path
from gamecat.database.connection import open_database
from gamecat.database.schema import initialize_schema
from gamecat.database.repositories import GlossaryRepository
from gamecat.models.glossary import GlossaryTerm
from gamecat.services.glossary_service import GlossaryService


def test_glossary_matching_case_modes(tmp_path: Path):
    conn=open_database(tmp_path/'g.db'); initialize_schema(conn)
    conn.execute("INSERT INTO projects(name,source_language,target_language,source_format,created_at,updated_at) VALUES('P','en','pl','txt','x','x')")
    conn.commit(); pid=conn.execute('SELECT id FROM projects').fetchone()[0]
    service=GlossaryService(GlossaryRepository(conn), pid)
    service.create_term(GlossaryTerm('quest',['zadanie'],case_sensitive=False))
    service.create_term(GlossaryTerm('XP',['PD'],case_sensitive=True))
    assert [e.source_term for e in service.find_terms('Complete QUEST for XP')] == ['quest','XP']
    assert [e.source_term for e in service.find_terms('Complete quest for xp')] == ['quest']
    conn.close()


def test_glossary_service_returns_multi_variant_term(tmp_path: Path):
    conn=open_database(tmp_path/'g.db'); initialize_schema(conn)
    conn.execute("INSERT INTO projects(name,source_language,target_language,source_format,created_at,updated_at) VALUES('P','en','pl','txt','x','x')")
    conn.commit(); pid=conn.execute('SELECT id FROM projects').fetchone()[0]
    service=GlossaryService(GlossaryRepository(conn),pid)
    service.create_term(GlossaryTerm('quest',['zadanie','misja']))
    terms=service.find_terms('Complete the quest')
    assert terms[0].targets == ['zadanie','misja']
    conn.close()
