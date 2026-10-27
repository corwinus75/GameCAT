"""Ustawienia projektu zapisywane w SQLite: profile formatów, AI i próg TM."""
from __future__ import annotations
import json
import sqlite3
import math
from gamecat.models.project import Project
from gamecat.ai.core import AISettings
from gamecat.localization.profiles import FormatProfile


class ProjectSettingsMixin:
    """Ustawienia projektu zapisywane w SQLite: profile formatów, AI i próg TM."""

    def set_format_profile(self, project: Project, profile: FormatProfile) -> None:
        """Zapisz profil mapowania formatu dla projektu; pliki źródłowe nie są przechowywane."""
        if project.id is None:
            raise ValueError('Project must be persisted')
        with self.connection:
            self.connection.execute(
                'INSERT INTO project_format_profiles(project_id,format,settings_json) VALUES(?,?,?) '
                'ON CONFLICT(project_id,format) DO UPDATE SET settings_json=excluded.settings_json',
                (project.id, profile.format, json.dumps(profile.to_dict(), ensure_ascii=False)),
            )

    def get_format_profile(self, project: Project, format_name: str) -> FormatProfile:
        """Zwróć zapisany profil formatu albo profil domyślny."""
        if project.id is None:
            raise ValueError('Project must be persisted')
        row = self.connection.fetchone(
            'SELECT settings_json FROM project_format_profiles WHERE project_id=? AND format=?',
            (project.id, format_name),
        )
        if row is None:
            return FormatProfile(format_name)
        return FormatProfile.from_dict(json.loads(row['settings_json']))

    def clear_format_profile(self, project: Project, format_name: str) -> None:
        """Usuń zapisany profil formatu projektu."""
        if project.id is None:
            raise ValueError('Project must be persisted')
        with self.connection:
            self.connection.execute('DELETE FROM project_format_profiles WHERE project_id=? AND format=?',
                                    (project.id, format_name))

    def has_format_profile(self, project: Project, format_name: str) -> bool:
        """Sprawdź, czy projekt ma zapisany profil dla formatu."""
        if project.id is None:
            return False
        return self.connection.fetchone(
            'SELECT 1 FROM project_format_profiles WHERE project_id=? AND format=?',
            (project.id, format_name),
        ) is not None

    def get_ai_settings(self, project: Project) -> AISettings:
        """Zwróć ustawienia AI projektu albo wartości domyślne."""
        if project.id is None:
            raise ValueError('Project must be persisted')
        with self.connection:
            row = self.connection.fetchone(
                'SELECT * FROM ai_project_settings WHERE project_id=?', (project.id,)
            )
        if row is None:
            return AISettings()
        return AISettings(row['model'], row['instructions'], row['input_price_per_million'],
                          row['output_price_per_million'], row['max_output_tokens'])

    def set_ai_settings(self, project: Project, settings: AISettings) -> None:
        """Zapisz ustawienia AI projektu (bez klucza API)."""
        if project.id is None:
            raise ValueError('Project must be persisted')
        with self.connection:
            self.connection.execute('''INSERT INTO ai_project_settings
                (project_id,model,instructions,input_price_per_million,output_price_per_million,max_output_tokens)
                VALUES(?,?,?,?,?,?) ON CONFLICT(project_id) DO UPDATE SET
                model=excluded.model, instructions=excluded.instructions,
                input_price_per_million=excluded.input_price_per_million,
                output_price_per_million=excluded.output_price_per_million,
                max_output_tokens=excluded.max_output_tokens''',
                (project.id, settings.model, settings.instructions, settings.input_price_per_million,
                 settings.output_price_per_million, settings.max_output_tokens))

    def _tm_setting(self, project: Project) -> sqlite3.Row | None:
        """Zwróć wiersz ustawień TM projektu (ścieżka zewnętrznej TM, próg) albo ``None``."""
        return self.connection.fetchone(
            'SELECT external_path,threshold FROM tm_project_settings WHERE project_id=?',
            (self._tm_project_id(project),),
        )

    def get_tm_threshold(self, project: Project) -> float:
        """Zwróć próg sugestii TM projektu (domyślnie 0,45)."""
        settings = self._tm_setting(project)
        return float(settings['threshold']) if settings is not None else 0.45

    def set_tm_threshold(self, project: Project, value: float) -> None:
        """Zapisz próg sugestii TM projektu.

        :raises ValueError: gdy wartość jest spoza zakresu [0, 1].
        """
        if not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError('TM threshold must be in [0, 1]')
        with self.connection:
            self.connection.execute(
                'INSERT INTO tm_project_settings(project_id, threshold) VALUES(?,?) '
                'ON CONFLICT(project_id) DO UPDATE SET threshold=excluded.threshold',
                (self._tm_project_id(project), float(value)),
            )
