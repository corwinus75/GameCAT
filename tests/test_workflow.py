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
