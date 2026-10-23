import argparse
from pathlib import Path
from gamecat.services.project_service import ProjectService
from gamecat.models.segment import SegmentStatus
from gamecat.utils.iterators import SegmentIterator
from gamecat.utils.generators import filter_segments

FORMATS = ['txt', 'csv', 'json']


def parser_for_version():
    parser = argparse.ArgumentParser(description='GameCAT — etapowa wersja CLI')
    parser.add_argument('--db', type=Path, default=Path('gamecat.sqlite'), help='ścieżka bazy projektu')
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('new', help='utwórz nowy projekt')
    p.add_argument('name')
    p.add_argument('--source', default='en')
    p.add_argument('--target', default='pl')
    p.add_argument('--format', default='txt', choices=FORMATS)
    sub.add_parser('projects', help='pokaż projekty')
    p = sub.add_parser('import', help='zaimportuj plik do projektu')
    p.add_argument('project_id', type=int); p.add_argument('file', type=Path)
    p = sub.add_parser('list', help='lista segmentów projektu')
    p.add_argument('project_id', type=int)
    p.add_argument('--status', default='ALL', choices=['ALL', *[s.value for s in SegmentStatus]])
    p = sub.add_parser('translate', help='ustaw tłumaczenie segmentu')
    p.add_argument('project_id', type=int); p.add_argument('segment_id', type=int); p.add_argument('target')
    p = sub.add_parser('export', help='eksport tłumaczeń')
    p.add_argument('project_id', type=int); p.add_argument('file', type=Path)

    return parser


def main(argv=None) -> int:
    args = parser_for_version().parse_args(argv)

    service = ProjectService(args.db)
    try:
        if args.command == 'new':
            project = service.create_project(args.name, args.source, args.target, args.format)
            print(f'Projekt utworzony: id={project.id}, name={project.name}')
        elif args.command == 'projects':
            for p in service.projects.list_all():
                print(f'{p.id}: {p.name} ({p.source_language}->{p.target_language})')
        else:
            project = service.load_project(args.project_id)
            if args.command == 'import':
                added = service.import_file(project, args.file)

                print(f'Zaimportowano: {len(added)} segmentów')
            elif args.command == 'list':
                segments = service.list_segments(project.id)
                segments = SegmentIterator(segments)
                segments = filter_segments(segments, lambda s: args.status == 'ALL' or s.status.value == args.status)

                for s in segments:
                    print(f'{s.id} [{s.status.value}] {s.source} -> {s.target}')
            elif args.command == 'translate':
                segment = service.segments.get(args.segment_id)
                if segment.project_id != project.id:
                    raise ValueError('Segment nie należy do wybranego projektu')
                segment.target = args.target
                segment.status = SegmentStatus.TRANSLATED
                service.save_segment(segment)
                print(f'Zapisano segment: {segment.id}')
            elif args.command == 'export':
                segments = service.list_segments(project.id)
                service.export_file(segments, args.file, args.file.suffix.lstrip('.').lower())
                print(f'Wyeksportowano: {args.file}')

    finally:
        service.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
