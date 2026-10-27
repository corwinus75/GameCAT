"""Fasada ``ProjectService`` – jedyny punkt wejścia GUI do logiki aplikacji."""
from __future__ import annotations
from pathlib import Path
from threading import RLock
from gamecat.concurrency.io_workers import IOWorkerPool
from gamecat.concurrency.save_queue import SaveQueue
from gamecat.database.connection import open_database
from gamecat.database.schema import initialize_schema, backup_duplicate_tm
from gamecat.database.repositories import GlossaryRepository, ProjectRepository, SegmentRepository, TranslationMemoryRepository
from gamecat.models.project import Project
from gamecat.models.translation_memory import TranslationMemoryEntry
from gamecat.services.project.files import FileExchangeMixin
from gamecat.services.project.glossary import GlossaryOperationsMixin
from gamecat.services.project.quality import QualitySearchMixin
from gamecat.services.project.segments import SegmentOperationsMixin
from gamecat.services.project.settings import ProjectSettingsMixin
from gamecat.services.project.tm import TranslationMemoryMixin


class ProjectService(
    ProjectSettingsMixin,
    SegmentOperationsMixin,
    FileExchangeMixin,
    TranslationMemoryMixin,
    QualitySearchMixin,
    GlossaryOperationsMixin,
):
    """Fasada logiki aplikacji, niezależna od GUI.

    Łączy repozytoria SQLite, kolejkę zapisów w tle (:class:`SaveQueue`)
    i pulę wątków I/O. Poszczególne obszary (ustawienia, segmenty, pliki,
    TM, QA, glosariusz) są zaimplementowane w mixinach z pakietu
    :mod:`gamecat.services.project`; tutaj pozostaje cykl życia usługi
    i wybór aktywnego projektu.
    """

    def __init__(
        self,
        database_path: Path,
        max_io_workers: int = 4,
        autosave_debounce_seconds: float = 0.20,
    ) -> None:
        """Otwórz (lub utwórz) bazę projektu i uruchom wątki robocze.

        :param database_path: plik ``.sqlite`` z projektami.
        :param max_io_workers: rozmiar puli wątków dla importu i eksportu.
        :param autosave_debounce_seconds: okno scalania szybkich zapisów.
        """
        self.database_path = Path(database_path).resolve()
        self.connection = open_database(self.database_path)
        try:
            backup_duplicate_tm(self.connection, self.database_path)
            initialize_schema(self.connection)
        except BaseException:
            self.connection.close()
            raise
        self.projects = ProjectRepository(self.connection)
        self.segments = SegmentRepository(self.connection)
        self.glossary = GlossaryRepository(self.connection)
        self._internal_tm = TranslationMemoryRepository(self.connection)
        self.translation_memory = self._internal_tm
        self._external_tm_connection = None
        # Do not select an arbitrary project's external TM on database open.
        self._active_tm_project_id: int | None = None
        self.io = IOWorkerPool(max_io_workers)
        self.save_queue = SaveQueue(self.segments, autosave_debounce_seconds)
        self._tm_cache_lock = RLock()
        self._tm_entries_cache: dict[tuple[str, str], tuple[TranslationMemoryEntry, ...]] = {}

    def create_project(self, name: str, source_language: str, target_language: str, source_format: str) -> Project:
        """Utwórz nowy projekt w bazie i ustaw go jako aktywny."""
        project = self.projects.create(Project(name, source_language, target_language, source_format))
        # Newly created projects become the active project in the caller.
        self.select_project(project)
        return project

    def load_project(self, project_id: int | None) -> Project:
        """Wczytaj projekt o podanym ID; brak ID jest błędem."""
        if project_id is None:
            raise ValueError('project_id is required')
        return self.projects.get(project_id)

    def list_projects(self) -> list[Project]:
        """Zwróć projekty z bazy; jedyny projekt w pliku zostaje od razu wybrany."""
        projects = self.projects.list_all()
        # Preserve 1.0.1 semantics for files that contain exactly one project.
        # With several projects, an explicit selection is mandatory.
        if len(projects) == 1 and self._active_tm_project_id is None:
            self.select_project(projects[0])
        return projects

    @property
    def active_project_id(self) -> int | None:
        """ID projektu, dla którego załadowano magazyn TM (``None`` – brak wyboru)."""
        return self._active_tm_project_id

    def select_project(self, project: Project) -> None:
        """Aktywuj projekt i jego magazyn TM; przy nieudanym otwarciu stan się nie zmienia."""
        with self._tm_cache_lock:
            project_id = self._tm_project_id(project)
            self.projects.get(project_id)  # project must belong to this database
            if project_id == self._active_tm_project_id:
                return
            setting = self._tm_setting(project)
            external = setting['external_path'] if setting is not None else None
            if external:
                self._select_tm_storage(Path(external), create_new=False)
            else:
                self.translation_memory = self._internal_tm
                if self._external_tm_connection is not None:
                    self._external_tm_connection.close()
                    self._external_tm_connection = None
            self._active_tm_project_id = project_id
            self.invalidate_tm_cache()

    def close(self) -> None:
        """Zamknij usługę: opróżnij kolejkę zapisów, pulę wątków i połączenia SQLite."""
        # Zamykamy dopiero, gdy każda zakolejkowana edycja trafiła do SQLite.
        self.save_queue.close()
        self.io.close()
        if self._external_tm_connection is not None:
            self._external_tm_connection.close()
            self._external_tm_connection = None
        self.connection.close()
