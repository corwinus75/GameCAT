"""Szybka walidacja etapu. Uruchom: python smoke_check.py"""
from pathlib import Path
from tempfile import TemporaryDirectory
from gamecat.services.project_service import ProjectService
from gamecat.models.segment import SegmentStatus

with TemporaryDirectory(prefix='gamecat_smoke_') as tmp:
    root = Path(tmp)
    inp = root / 'in.txt'; inp.write_text('Hello {name}\nWorld\n', encoding='utf-8')
    db = root / 'p.sqlite'
    svc = ProjectService(db)
    project = svc.create_project('Demo', 'en', 'pl', 'txt')
    added = svc.import_file(project, inp)

    assert len(added) == 2
    added[0].target = 'Cześć {name}'
    added[0].status = SegmentStatus.TRANSLATED
    svc.save_segment(added[0])
    svc.close()
    reopened = ProjectService(db)
    p2 = reopened.load_project(project.id)
    listed = reopened.list_segments(p2.id)
    assert listed[0].target == 'Cześć {name}'
    dest = root / 'out.txt'
    reopened.export_file(listed, dest, 'txt')
    assert dest.read_text(encoding='utf-8').startswith('Cześć {name}')

    reopened.close()
print('OK: etap sprawdzony')
