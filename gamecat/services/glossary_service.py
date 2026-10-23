from gamecat.database.repositories import GlossaryRepository
from gamecat.models.glossary import GlossaryEntry


class GlossaryService:
    """Find glossary entries applicable to source text."""
    def __init__(self, repository: GlossaryRepository, project_id: int | None):
        self.repository = repository
        self.project_id = project_id

    def find_terms(self, source: str) -> list[GlossaryEntry]:
        matches: list[GlossaryEntry] = []
        for entry in self.repository.list_for_project(self.project_id):
            haystack = source if entry.case_sensitive else source.casefold()
            needle = entry.source_term if entry.case_sensitive else entry.source_term.casefold()
            if needle in haystack:
                matches.append(entry)
        return matches
