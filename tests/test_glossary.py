from pathlib import Path
from gamecat.database.connection import open_database
from gamecat.database.schema import initialize_schema
from gamecat.database.repositories import GlossaryRepository
from gamecat.models.glossary import GlossaryEntry
from gamecat.services.glossary_service import GlossaryService
from gamecat.qa.validator import validate_segment


def test_glossary_matching_case_modes(tmp_path: Path):
    conn=open_database(tmp_path/'g.db'); initialize_schema(conn)
    conn.execute("INSERT INTO projects(name,source_language,target_language,source_format,created_at,updated_at) VALUES('P','en','pl','txt','x','x')")
    pid=conn.execute('SELECT id FROM projects').fetchone()[0]
    repo=GlossaryRepository(conn)
    repo.create(GlossaryEntry('quest','zadanie',case_sensitive=False, project_id=pid))
    repo.create(GlossaryEntry('XP','PD',case_sensitive=True, project_id=pid))
    service=GlossaryService(repo, pid)
    assert [e.source_term for e in service.find_terms('Complete QUEST for XP')] == ['quest','XP']
    assert [e.source_term for e in service.find_terms('Complete quest for xp')] == ['quest']


def test_glossary_matches_integrate_with_qa(tmp_path: Path):
    conn=open_database(tmp_path/'g.db'); initialize_schema(conn)
    # Need a project row for FK
    conn.execute("INSERT INTO projects(name,source_language,target_language,source_format,created_at,updated_at) VALUES('P','en','pl','txt','x','x')")
    pid=conn.execute('SELECT id FROM projects').fetchone()[0]
    repo=GlossaryRepository(conn); repo.create(GlossaryEntry('quest','zadanie',project_id=pid))
    terms=GlossaryService(repo,pid).find_terms('Complete the quest')
    assert any(i.code=='glossary-term' for i in validate_segment('Complete the quest','Ukończ misję',terms))
