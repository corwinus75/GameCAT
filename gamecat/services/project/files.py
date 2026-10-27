"""Import i eksport segmentów oraz tłumaczeń (zadania I/O w puli wątków)."""
from __future__ import annotations
from pathlib import Path
from collections.abc import Iterable
from concurrent.futures import Future
from dataclasses import dataclass
from gamecat.exporters.txt_exporter import export_txt
from gamecat.exporters.csv_exporter import export_csv
from gamecat.exporters.json_exporter import export_json
from gamecat.importers.txt_importer import import_txt
from gamecat.importers.csv_importer import import_csv
from gamecat.importers.csv_format import read_csv_headers, suggest_source_columns
from gamecat.importers.json_importer import import_json
from gamecat.importers.translation_importer import (
    import_translation_csv,
    import_translation_json,
    import_translation_txt,
)
from gamecat.models.project import Project
from gamecat.models.segment import Segment, SegmentStatus
from gamecat.exceptions import ImportFormatError
from gamecat.utils.decorators import measure_time
from gamecat.localization.profiles import FormatProfile
from gamecat.localization.exchange import read_source, read_translations, export_translations

@dataclass(frozen=True, slots=True)
class TranslationImportResult:
    """Wynik importu tłumaczeń: liczba wierszy, zaktualizowanych segmentów i niedopasowanych wpisów."""
    total: int
    updated: int
    unmatched: int


class _CountingIterator:
    """Przezroczysta nakładka zliczająca elementy przechodzące przez iterator.

    Implementuje protokół iteratora (``__iter__``/``__next__``) i pozwala
    policzyć wyeksportowane segmenty bez materializowania listy w pamięci.
    """

    def __init__(self, inner: Iterable[Segment]):
        """Opakuj dowolny obiekt iterowalny i wyzeruj licznik."""
        self._inner = iter(inner)
        self.count = 0

    def __iter__(self) -> _CountingIterator:
        """Zwróć samego siebie – iterator jest jednorazowy."""
        return self

    def __next__(self) -> Segment:
        """Zwróć kolejny element i zwiększ licznik; ``StopIteration`` kończy iterację."""
        item = next(self._inner)
        self.count += 1
        return item


class FileExchangeMixin:
    """Import i eksport segmentów oraz tłumaczeń (zadania I/O w puli wątków)."""

    @measure_time
    def _import_file(
        self,
        project: Project,
        path: Path,
        csv_columns: tuple[str | None, str, str | None] | None = None,
    ) -> list[Segment]:
        """Zaimportuj plik źródłowy jako nowe segmenty projektu w jednej transakcji.

        Importer (generator) jest wybierany według rozszerzenia i profilu formatu,
        a segmenty powstają leniwie w wyrażeniu generującym. Czas operacji mierzy
        dekorator ``measure_time``.

        :raises ValueError: projekt niezapisany lub nieobsługiwany format.
        :raises ImportFormatError: błąd dekodowania lub struktury pliku.
        """
        if project.id is None:
            raise ValueError('project must be persisted before import')
        suffix = path.suffix.casefold()
        if suffix == '.txt':
            imported = import_txt(path)
        elif suffix == '.csv':
            key_column, source_column, target_column = (
                csv_columns if csv_columns is not None else suggest_source_columns(read_csv_headers(path))
            )
            imported = import_csv(path, key_column, source_column, target_column,
                                  self.get_format_profile(project, 'csv').comment_field)
        elif suffix == '.json' and not self.has_format_profile(project, 'json'):
            imported = import_json(path)
        elif suffix in {'.json', '.tsv', '.xlsx', '.xml'}:
            imported = read_source(path, self.get_format_profile(project, suffix.lstrip('.')))
        else:
            raise ValueError(f'Unsupported import format: {suffix}')
        # Wyrażenie generujące: parsowanie pliku i budowa segmentów odbywa się
        # leniwie, wewnątrz jednej transakcji – błąd w połowie pliku cofa całość.
        segments = (
            Segment(item.source, item.position, item.key, item.target, project_id=project.id,
                    status=SegmentStatus.TRANSLATED if item.target.strip() else SegmentStatus.NEW,
                    comment=item.comment)
            for item in imported
        )
        try:
            return self.segments.create_many(segments)
        except (UnicodeError, ValueError, KeyError) as exc:
            raise ImportFormatError(f'Cannot import {path.name}: {exc}') from exc

    def import_file_async(
        self,
        project: Project,
        path: Path,
        csv_columns: tuple[str | None, str, str | None] | None = None,
    ) -> Future[list[Segment]]:
        """Zleć import pliku źródłowego w puli wątków I/O i zwróć ``Future`` z segmentami."""
        return self.io.submit(self._import_file, project, path, csv_columns)

    @measure_time
    def _import_translation_file(
        self,
        project: Project,
        path: Path,
        csv_columns: tuple[str | None, str] | None = None,
        format_profile: FormatProfile | None = None,
        legacy_json: bool = False,
    ) -> TranslationImportResult:
        """Zaimportuj tłumaczenia i przypisz je segmentom po kluczu albo pozycji.

        Wszystkie wiersze są najpierw dopasowywane w pamięci, a zapis następuje
        jednym ``update_many``. Nowy Target unieważnia wcześniejszą recenzję lub
        zatwierdzenie.

        :raises ValueError: nieobsługiwany format, nadmiarowe wpisy TXT lub
            niejednoznaczny klucz segmentu.
        """
        if project.id is None:
            raise ValueError('project must be persisted before translation import')
        segments = self.list_segments(project.id)
        suffix = path.suffix.casefold()
        if suffix == '.txt':
            imported = list(import_translation_txt(path))
            if len(imported) > len(segments):
                raise ValueError('Plik tłumaczenia zawiera więcej wpisów niż projekt.')
        elif suffix == '.csv':
            key_column, target_column = csv_columns or ('id', 'target')
            imported = list(import_translation_csv(path, key_column, target_column))
        elif suffix == '.json' and (legacy_json or (format_profile is None and not self.has_format_profile(project, 'json'))):
            imported = list(import_translation_json(path))
        elif suffix in {'.json', '.tsv', '.xlsx', '.xml'}:
            mapping = format_profile or self.get_format_profile(project, suffix.lstrip('.'))
            imported = list(read_translations(path, mapping))
        else:
            raise ValueError(f'Unsupported translation import format: {suffix}')

        by_position = {segment.position: segment for segment in segments}
        by_key: dict[str, Segment] = {}
        duplicate_keys: set[str] = set()
        for segment in segments:
            if segment.key is None:
                continue
            if segment.key in by_key:
                duplicate_keys.add(segment.key)
            else:
                by_key[segment.key] = segment
        for key in duplicate_keys:
            by_key.pop(key, None)

        changed: list[Segment] = []
        unmatched = 0
        # Najpierw dopasowanie w pamięci, dopiero potem jeden zapis: błąd
        # (np. niejednoznaczny klucz) nie zostawia częściowo zaimportowanego pliku.
        for item in imported:
            segment: Segment | None = None
            if item.key is not None:
                if item.key in duplicate_keys:
                    raise ValueError(f'Niejednoznaczny klucz segmentu w projekcie: {item.key}')
                segment = by_key.get(item.key)
            elif item.position is not None:
                segment = by_position.get(item.position)
            if segment is None:
                unmatched += 1
                continue
            if segment.target != item.target:
                # An imported revision invalidates prior human review/approval.
                # Never leave REVIEWED/APPROVED attached to a different Target.
                segment.target = item.target
                segment.status = (SegmentStatus.TRANSLATED if item.target.strip()
                                  else SegmentStatus.NEW)
            elif item.target.strip() and segment.status is SegmentStatus.NEW:
                segment.status = SegmentStatus.TRANSLATED
            elif not item.target.strip() and segment.status is SegmentStatus.TRANSLATED:
                segment.status = SegmentStatus.NEW
            changed.append(segment)
        updated = self.segments.update_many(changed)
        return TranslationImportResult(total=len(imported), updated=updated, unmatched=unmatched)

    def import_translation_file_async(
        self,
        project: Project,
        path: Path,
        csv_columns: tuple[str | None, str] | None = None,
        *, format_profile: FormatProfile | None = None,
        legacy_json: bool = False,
    ) -> Future[TranslationImportResult]:
        """Zleć import tłumaczeń w puli wątków I/O."""
        return self.io.submit(self._import_translation_file, project, path, csv_columns,
                              format_profile, legacy_json)

    @staticmethod
    @measure_time
    def _export_file(segments: Iterable[Segment], path: Path, format_name: str, *, ordered: bool = False) -> None:
        """Zapisz segmenty prostym eksporterem TXT, CSV lub JSON (metoda statyczna).

        :raises ValueError: nieobsługiwany format.
        """
        if format_name == 'txt':
            export_txt(segments, path, ordered=ordered)
        elif format_name == 'csv':
            export_csv(segments, path, ordered=ordered)
        elif format_name == 'json':
            export_json(segments, path, 'list', ordered=ordered)
        else:
            raise ValueError(f'Unsupported export format: {format_name}')

    def export_file_async(self, segments: list[Segment], path: Path, format_name: str) -> Future[None]:
        """Zleć eksport listy segmentów w puli wątków I/O."""
        return self.io.submit(self._export_file, segments, path, format_name)

    def _export_project(self, project: Project, path: Path, format_name: str) -> int:
        """Wyeksportuj cały projekt, czytając segmenty partiami z bazy; zwraca ich liczbę.

        Dla prostych formatów liczbę zapisanych segmentów zlicza iterator
        ``_CountingIterator`` bez budowania listy w pamięci.
        """
        if project.id is None:
            raise ValueError('project must be persisted before export')
        iterator = self.iter_segments(project.id)
        if format_name in {'tsv', 'xlsx', 'xml'}:
            return export_translations(iterator, path, self.get_format_profile(project, format_name))
        counted = _CountingIterator(iterator)
        self._export_file(counted, path, format_name, ordered=True)
        return counted.count

    def _export_using_template(self, project: Project, template: Path, destination: Path) -> int:
        """Wyeksportuj tłumaczenia do kopii oryginalnego pliku (szablonu) w tym samym formacie.

        :raises ValueError: różne formaty, format bez obsługi szablonu lub brak profilu.
        """
        if project.id is None:
            raise ValueError('project must be persisted before export')
        if template.suffix.lower() != destination.suffix.lower():
            raise ValueError('Original file and output file must use the same format')
        fmt = template.suffix.lower().lstrip('.')
        if fmt not in {'csv', 'tsv', 'xlsx', 'json', 'xml'}:
            raise ValueError(f'Template export does not support: {fmt}')
        if not self.has_format_profile(project, fmt):
            raise ValueError('First import a source file with a saved format profile')
        return export_translations(
            self.iter_segments(project.id), destination, self.get_format_profile(project, fmt),
            template_path=template,
        )

    def export_using_template_async(self, project: Project, template: Path, destination: Path) -> Future[int]:
        """Zleć eksport według szablonu w puli wątków I/O."""
        return self.io.submit(self._export_using_template, project, template, destination)

    def export_project_async(self, project: Project, path: Path, format_name: str) -> Future[int]:
        """Eksportuj projekt w wątku I/O, czytając segmenty partiami z bazy."""
        return self.io.submit(self._export_project, project, path, format_name)
