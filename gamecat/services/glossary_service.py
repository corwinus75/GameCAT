from __future__ import annotations

from gamecat.database.repositories import GlossaryRepository
from gamecat.glossary.matching import contains_term
from gamecat.models.glossary import GlossaryTerm


class GlossaryService:
    """Project-scoped glossary workflow and invariants."""

    def __init__(self, repository: GlossaryRepository, project_id: int | None):
        self.repository = repository
        self.project_id = project_id

    def _project_id(self) -> int:
        if self.project_id is None:
            raise ValueError('project_id is required for project glossary operations')
        return self.project_id

    def list_terms(self) -> list[GlossaryTerm]:
        return self.repository.list_terms(self._project_id())

    def find_terms(self, source: str) -> list[GlossaryTerm]:
        return [
            term for term in self.list_terms()
            if contains_term(source, term.source_term, case_sensitive=term.case_sensitive)
        ]

    def create_term(self, term: GlossaryTerm) -> GlossaryTerm:
        project_id = self._project_id()
        term.project_id = project_id
        existing = self.repository.get_by_identity(project_id, term.source_term, term.case_sensitive)
        if existing is not None:
            self.repository.merge_terms(project_id, [term])
            return self.repository.get_term(existing.id)
        return self.repository.create_term(term)

    def save_term(self, term: GlossaryTerm) -> GlossaryTerm:
        if term.id is None:
            return self.create_term(term)
        project_id = self._project_id()
        current = self.repository.get_term(term.id)
        if current.project_id != project_id:
            raise ValueError('term does not belong to current project')
        collision = self.repository.get_by_identity(project_id, term.source_term, term.case_sensitive)
        if collision is not None and collision.id != term.id:
            merged_targets = list(collision.targets)
            for target in term.targets:
                if target not in merged_targets:
                    merged_targets.append(target)
            description = collision.description or term.description
            self.repository.update_term_fields(collision.id, collision.source_term, description, collision.case_sensitive)
            for target in merged_targets:
                self.repository.add_variant(collision.id, target)
            self.repository.delete_term(term.id)
            return self.repository.get_term(collision.id)

        self.repository.update_term_fields(term.id, term.source_term, term.description, term.case_sensitive)
        desired = set(term.targets)
        for target in desired:
            self.repository.add_variant(term.id, target)
        for target in current.targets:
            if target not in desired:
                self.repository.remove_variant(term.id, target)
        return self.repository.get_term(term.id)

    def delete_term(self, term_id: int) -> None:
        term = self.repository.get_term(term_id)
        if term.project_id != self._project_id():
            raise ValueError('term does not belong to current project')
        self.repository.delete_term(term_id)

    def add_variant(self, term_id: int, target: str) -> bool:
        term = self.repository.get_term(term_id)
        if term.project_id != self._project_id():
            raise ValueError('term does not belong to current project')
        return self.repository.add_variant(term_id, target)

    def remove_variant(self, term_id: int, target: str) -> None:
        term = self.repository.get_term(term_id)
        if term.project_id != self._project_id():
            raise ValueError('term does not belong to current project')
        if target.strip() in term.targets and len(term.targets) <= 1:
            raise ValueError('cannot remove the last target variant; delete the whole term instead')
        self.repository.remove_variant(term_id, target)

    def search(self, query: str) -> list[GlossaryTerm]:
        return self.repository.search_terms(self._project_id(), query)
