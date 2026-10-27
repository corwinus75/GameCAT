"""Kontrola jakości (QA) i kontekst wyszukiwania dla całego projektu."""
from __future__ import annotations
from collections.abc import Iterable
from concurrent.futures import Future
from gamecat.models.project import Project
from gamecat.models.segment import Segment
from gamecat.qa.project_scan import ProjectQAReport, scan_segments
from gamecat.qa.rules import QAIssue
from gamecat.qa.validator import validate_segment
from gamecat.utils.decorators import measure_time


class QualitySearchMixin:
    """Kontrola jakości (QA) i kontekst wyszukiwania dla całego projektu."""

    def calculate_search_context(
        self, project: Project, segments: Iterable[Segment], *, qa: bool = False, tm: bool = False,
    ) -> dict[str, set[int]]:
        """Policz zbiory ID segmentów z błędami QA i z dokładnym dopasowaniem w TM."""
        snapshot = tuple((segment.id, segment.source, segment.target) for segment in segments
                         if segment.id is not None)
        return self._calculate_search_snapshot(project, snapshot, qa, tm)

    def _calculate_search_snapshot(
        self, project: Project, snapshot: tuple[tuple[int, str, str], ...], qa: bool, tm: bool,
    ) -> dict[str, set[int]]:
        """Policz filtry jakości na niemutowalnej migawce (ID, Source, Target) – bez dostępu do Qt."""
        result: dict[str, set[int]] = {}
        if qa:
            glossary = self.list_glossary(project.id)
            result['qa_error_ids'] = {sid for sid, source, target in snapshot
                                      if validate_segment(source, target, glossary)}
        if tm:
            sources = self.tm_sources(project)
            result['tm_match_ids'] = {sid for sid, source, _ in snapshot if source in sources}
        return result

    def calculate_search_context_async(
        self, project: Project, segments: Iterable[Segment], *, qa: bool = False, tm: bool = False,
    ) -> Future[dict[str, set[int]]]:
        """Zrób migawkę stanu edytora w wątku GUI i policz filtry jakości w puli wątków.

        Do wątku roboczego trafiają tylko niemutowalne krotki, nie obiekty ``Segment``.
        """
        # Copy only immutable fields on the UI thread; no costly Segment objects.
        snapshot = tuple((s.id, s.source, s.target) for s in segments if s.id is not None)
        return self.io.submit(self._calculate_search_snapshot, project, snapshot, qa, tm)

    def run_project_qa_async(self, project: Project) -> Future[ProjectQAReport]:
        """Zleć QA całego projektu w puli wątków I/O."""
        return self.io.submit(self.run_project_qa, project)

    def check_segment_qa_async(self, project: Project, source: str, target: str) -> Future[list[QAIssue]]:
        """Sprawdź niezapisany stan edytora regułami QA poza wątkiem GUI."""
        def check() -> list[QAIssue]:
            return validate_segment(source, target, self.list_glossary(project.id))
        return self.io.submit(check)

    @measure_time
    def run_project_qa(self, project: Project) -> ProjectQAReport:
        """Sprawdź cały projekt, czytając segmenty strumieniowo z bazy."""
        if project.id is None:
            raise ValueError('project must be persisted before QA')
        return scan_segments(self.iter_segments(project.id), self.list_glossary(project.id))
