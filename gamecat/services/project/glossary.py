"""Operacje na glosariuszu projektu oraz jego import i eksport."""
from __future__ import annotations
from pathlib import Path
from concurrent.futures import Future
from gamecat.models.glossary import GlossaryTerm
from gamecat.services.glossary_service import GlossaryService
from gamecat.glossary.importers import GlossaryImportResult, import_glossary_csv, import_glossary_json
from gamecat.glossary.exporters import export_glossary_csv, export_glossary_json


class GlossaryOperationsMixin:
    """Operacje na glosariuszu projektu oraz jego import i eksport."""

    def glossary_service(self, project_id: int | None) -> GlossaryService:
        """Utwórz usługę glosariusza powiązaną z projektem."""
        return GlossaryService(self.glossary, project_id)

    def list_glossary(self, project_id: int | None) -> list[GlossaryTerm]:
        """Zwróć terminy glosariusza projektu (pusta lista bez projektu)."""
        if project_id is None:
            return []
        return self.glossary.list_terms(project_id)

    def create_glossary_term(self, project_id: int | None, term: GlossaryTerm) -> GlossaryTerm:
        """Dodaj termin do glosariusza projektu (ze scalaniem duplikatów)."""
        return self.glossary_service(project_id).create_term(term)

    def save_glossary_term(self, project_id: int | None, term: GlossaryTerm) -> GlossaryTerm:
        """Zapisz zmiany terminu glosariusza."""
        return self.glossary_service(project_id).save_term(term)

    def delete_glossary_term(self, project_id: int | None, term_id: int) -> None:
        """Usuń termin z glosariusza projektu."""
        self.glossary_service(project_id).delete_term(term_id)

    def add_glossary_variant(self, project_id: int | None, term_id: int, target: str) -> bool:
        """Dodaj wariant tłumaczenia terminu."""
        return self.glossary_service(project_id).add_variant(term_id, target)

    def remove_glossary_variant(self, project_id: int | None, term_id: int, target: str) -> None:
        """Usuń wariant tłumaczenia terminu."""
        self.glossary_service(project_id).remove_variant(term_id, target)

    def _import_glossary_file(self, project_id: int, path: Path) -> GlossaryImportResult:
        """Zaimportuj glosariusz z CSV lub JSON.

        :raises ValueError: nieobsługiwany format.
        """
        suffix = path.suffix.casefold()
        if suffix == '.csv':
            return import_glossary_csv(path, self.glossary, project_id)
        if suffix == '.json':
            return import_glossary_json(path, self.glossary, project_id)
        raise ValueError(f'Unsupported glossary format: {suffix}')

    def import_glossary_file_async(self, project_id: int | None, path: Path) -> Future[GlossaryImportResult]:
        """Zleć import glosariusza w puli wątków I/O.

        :raises ValueError: brak ID projektu.
        """
        if project_id is None:
            raise ValueError('project_id is required')
        return self.io.submit(self._import_glossary_file, project_id, path)

    def _export_glossary_file(self, project_id: int, path: Path) -> int:
        """Wyeksportuj glosariusz do CSV lub JSON i zwróć liczbę rekordów.

        :raises ValueError: nieobsługiwany format.
        """
        terms = self.glossary.list_terms(project_id)
        suffix = path.suffix.casefold()
        if suffix == '.csv':
            return export_glossary_csv(path, terms)
        if suffix == '.json':
            return export_glossary_json(path, terms)
        raise ValueError(f'Unsupported glossary format: {suffix}')

    def export_glossary_file_async(self, project_id: int | None, path: Path) -> Future[int]:
        """Zleć eksport glosariusza w puli wątków I/O.

        :raises ValueError: brak ID projektu.
        """
        if project_id is None:
            raise ValueError('project_id is required')
        return self.io.submit(self._export_glossary_file, project_id, path)
