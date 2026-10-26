from pathlib import Path
import pytest

from gamecat.database.connection import open_database
from gamecat.database.schema import initialize_schema
from gamecat.database.repositories import GlossaryRepository
from gamecat.models.glossary import GlossaryTerm, GlossaryEntry


def _repo(tmp_path: Path):
    conn = open_database(tmp_path/'g.db'); initialize_schema(conn)
    conn.execute("INSERT INTO projects(name,source_language,target_language,source_format,created_at,updated_at) VALUES('P','en','pl','txt','x','x')")
    conn.execute("INSERT INTO projects(name,source_language,target_language,source_format,created_at,updated_at) VALUES('Q','en','pl','txt','x','x')")
    conn.commit()
    return conn, GlossaryRepository(conn)


def test_repository_crud_and_project_isolation(tmp_path: Path):
    conn, repo = _repo(tmp_path)
    a = repo.create_term(GlossaryTerm('sword', ['miecz','ostrze'], project_id=1))
    repo.create_term(GlossaryTerm('shield', ['tarcza'], project_id=2))
    assert a.id is not None
    assert [t.source_term for t in repo.list_terms(1)] == ['sword']
    assert repo.add_variant(a.id, 'miecz') is False
    assert repo.add_variant(a.id, 'szabla') is True
    assert repo.get_term(a.id).targets == ['miecz','ostrze','szabla']
    conn.close()


def test_legacy_flat_create_and_list_are_compatible(tmp_path: Path):
    conn, repo = _repo(tmp_path)
    entry = repo.create(GlossaryEntry('quest','zadanie',project_id=1))
    assert entry.id is not None
    rows = repo.list_for_project(1)
    assert [(r.source_term, r.target_term) for r in rows] == [('quest','zadanie')]
    conn.close()


def test_merge_terms_counts_new_variants_and_duplicates(tmp_path: Path):
    conn, repo = _repo(tmp_path)
    repo.create_term(GlossaryTerm('sword',['miecz'],project_id=1))
    new_terms, new_variants, duplicates = repo.merge_terms(1, [
        GlossaryTerm('sword',['miecz','ostrze']),
        GlossaryTerm('shield',['tarcza']),
    ])
    assert (new_terms, new_variants, duplicates) == (1, 2, 1)
    assert repo.get_by_identity(1,'sword',False).targets == ['miecz','ostrze']
    conn.close()
