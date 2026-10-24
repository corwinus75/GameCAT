"""Szybka walidacja etapu. Uruchom: python smoke_check.py"""
from pathlib import Path
from tempfile import TemporaryDirectory
from gamecat.services.project_service import ProjectService
from gamecat.models.segment import SegmentStatus

from multiprocessing import freeze_support


def main() -> None:
    with TemporaryDirectory(prefix='gamecat_smoke_') as tmp:
        root = Path(tmp)
        inp = root / 'in.txt'; inp.write_text('Hello {name}\nWorld\n', encoding='utf-8')
        db = root / 'p.sqlite'
        svc = ProjectService(db)
        project = svc.create_project('Demo', 'en', 'pl', 'txt')
        added = svc.import_file_async(project, inp).result(timeout=10)

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
        reopened.export_file_async(listed, dest, 'txt').result(timeout=10)
        assert dest.read_text(encoding='utf-8').startswith('Cześć {name}')

        from gamecat.utils.decorators import retry
        calls = []
        @retry(attempts=2)
        def intermittent():
            calls.append(1)
            if len(calls) < 2: raise RuntimeError('temporary')
            return 42
        assert intermittent() == 42 and len(calls) == 2

        from gamecat.utils.decorators import requires_project
        class Guard:
            current_project = None
            @requires_project
            def run(self): return 1
        try: Guard().run()
        except RuntimeError: pass
        else: raise AssertionError('project guard did not trigger')

        try: listed[0].target = 123
        except TypeError: pass
        else: raise AssertionError('property target did not validate')

        from gamecat.utils.iterators import SegmentIterator
        assert [s.source for s in SegmentIterator(listed)] == ['Hello {name}', 'World']

        from gamecat.utils.generators import filter_segments
        assert [s.position for s in filter_segments(listed,lambda s: s.status is SegmentStatus.TRANSLATED)] == [1]

        from gamecat.qa.validator import validate_segment
        assert any(x.code == 'placeholder-mismatch' for x in validate_segment('Hello {name}', 'Cześć'))
        from gamecat.models.glossary import GlossaryEntry
        from gamecat.database.repositories import GlossaryRepository
        GlossaryRepository(reopened.connection).create(GlossaryEntry('Hello','Cześć', project_id=p2.id))
        assert len(GlossaryRepository(reopened.connection).list_for_project(p2.id)) == 1

        from gamecat.models.translation_memory import TranslationMemoryEntry
        from gamecat.database.repositories import TranslationMemoryRepository
        from gamecat.tm.parallel_matcher import find_matches_parallel
        tm = TranslationMemoryRepository(reopened.connection)
        tm.create(TranslationMemoryEntry('Hello', 'Cześć', 'en', 'pl'))
        assert find_matches_parallel('Hello', tm.list_all(), workers=1)[0].entry.target == 'Cześć'

        reopened.close()
    print('OK: etap sprawdzony')


if __name__ == "__main__":
    freeze_support()
    main()
