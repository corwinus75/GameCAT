from pathlib import Path
from gamecat.services.project_service import ProjectService
from gamecat.models.segment import SegmentStatus


def test_end_to_end_project_import_edit_reopen_export(tmp_path: Path):
    db=tmp_path/'project.sqlite'; src=tmp_path/'source.txt'; out=tmp_path/'out.txt'
    src.write_text('Hello\nWorld\n', encoding='utf-8')
    service=ProjectService(db)
    project=service.create_project('Demo','en','pl','txt')
    future=service.import_file_async(project, src)
    segments=future.result(timeout=5)
    assert [s.source for s in segments]==['Hello','World']
    segments[0].target='Cześć'; segments[0].status=SegmentStatus.TRANSLATED
    service.save_segment(segments[0])
    service.close()

    reopened=ProjectService(db)
    loaded=reopened.load_project(project.id)
    rows=reopened.list_segments(loaded.id)
    assert rows[0].target=='Cześć'
    reopened.export_file_async(rows, out, 'txt').result(timeout=5)
    assert out.read_text(encoding='utf-8').startswith('Cześć\n')
    reopened.close()


def test_csv_import_accepts_user_selected_columns(tmp_path: Path):
    db = tmp_path / 'project.sqlite'
    src = tmp_path / 'source.csv'
    src.write_text('string_id,english,polish\nA1,Hello,Cześć\nA2,World,Świat\n', encoding='utf-8')
    service = ProjectService(db)
    project = service.create_project('CSV Demo', 'en', 'pl', 'csv')
    try:
        segments = service.import_file_async(
            project,
            src,
            csv_columns=('string_id', 'english', 'polish'),
        ).result(timeout=5)
        assert [(s.key, s.source, s.target) for s in segments] == [
            ('A1', 'Hello', 'Cześć'),
            ('A2', 'World', 'Świat'),
        ]
    finally:
        service.close()


def test_service_lists_projects_after_reopen(tmp_path: Path):
    db = tmp_path / 'project.sqlite'
    service = ProjectService(db)
    created = service.create_project('Demo', 'en', 'pl', 'txt')
    service.close()

    reopened = ProjectService(db)
    try:
        projects = reopened.list_projects()
        assert [(p.id, p.name) for p in projects] == [(created.id, 'Demo')]
    finally:
        reopened.close()


def test_service_exposes_project_glossary_for_qa(tmp_path: Path):
    from gamecat.models.glossary import GlossaryEntry

    service = ProjectService(tmp_path / 'project.sqlite')
    project = service.create_project('Demo', 'en', 'pl', 'txt')
    try:
        service.glossary.create(GlossaryEntry('quest', 'zadanie', project_id=project.id))
        entries = service.list_glossary(project.id)
        assert [(entry.source_term, entry.targets) for entry in entries] == [
            ('quest', ['zadanie']),
        ]
    finally:
        service.close()
