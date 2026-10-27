"""Integracja z OpenAI API: tłumaczenie pojedyncze i wsadowe z podglądem."""
from __future__ import annotations

from queue import Empty

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QMessageBox

from gamecat.ai.core import AIResult, BatchReport, BatchTranslator
from gamecat.ai.credentials import create_openai_translator
from gamecat.models.project import Project
from gamecat.models.segment import SegmentStatus



class AIMixin:
    """Integracja z OpenAI API: tłumaczenie pojedyncze i wsadowe z podglądem."""

    def _save_ai_settings(self) -> None:
        """Zapisz ustawienia AI projektu i – na życzenie – klucz API w systemowym magazynie."""
        if self.project_service is None or self.current_project is None:
            QMessageBox.warning(self, 'GameCAT', 'Najpierw otwórz projekt.')
            return
        try:
            settings = self.ai_panel.get_settings()
            if self.ai_panel.remember_key.isChecked() and self.ai_panel.api_key.text().strip():
                self._credentials.save(self.ai_panel.api_key.text())
                self.ai_panel.api_key.clear()
            self.project_service.set_ai_settings(self.current_project, settings)
            self.statusBar().showMessage('Zapisano ustawienia AI (bez klucza w SQLite).', 5000)
        except Exception as exc:
            QMessageBox.warning(self, 'OpenAI', f'Nie zapisano konfiguracji: {exc}')

    def _ai_translator(self):
        """Utwórz tłumacza OpenAI z klucza sesyjnego lub zapisanego w systemie."""
        return create_openai_translator(self.ai_panel.api_key.text(), credential_store=self._credentials)

    def _ai_submit(self, function, callback) -> None:
        """Uruchom funkcję w wątku OpenAI, blokując inne operacje, i obsłuż wynik w wątku GUI."""
        if self._busy or self._ai_running:
            QMessageBox.information(self, 'OpenAI', 'Inna operacja nadal trwa.')
            return
        self._ai_running = True
        self._busy = True
        self._sync_actions()
        self.ai_panel.set_running(True)
        future = self._ai_executor.submit(function)

        def poll() -> None:
            while True:
                try:
                    current, total = self._ai_progress_queue.get_nowait()
                except Empty:
                    break
                self.ai_panel.progress_label.setText(f'OpenAI: {current}/{total} segmentów…')
            if not future.done():
                QTimer.singleShot(100, poll)
                return
            self._ai_running = False
            self._busy = False
            self._sync_actions()
            self.ai_panel.set_running(False)
            try:
                result = future.result()
            except Exception as exc:
                QMessageBox.warning(self, 'OpenAI API', f'Operacja nie powiodła się: {exc}')
                return
            callback(result)
        QTimer.singleShot(80, poll)

    def _test_ai_connection(self) -> None:
        """Sprawdź w tle połączenie z OpenAI API dla wybranego modelu."""
        try:
            settings = self.ai_panel.get_settings()
            translator = self._ai_translator()
            self._ai_submit(lambda: translator.test_connection(settings.model),
                            lambda _: self.statusBar().showMessage('Połączenie z OpenAI API działa.', 6000))
        except Exception as exc:
            QMessageBox.warning(self, 'OpenAI', str(exc))

    def _translate_ai_current(self) -> None:
        """Przetłumacz bieżący segment przez AI i pokaż propozycję do zatwierdzenia."""
        if self.current_project is None or self.project_service is None:
            QMessageBox.warning(self, 'OpenAI', 'Najpierw otwórz projekt.')
            return
        segment = self.segment_editor.current_segment()
        if segment is None or segment.id is None:
            QMessageBox.warning(self, 'OpenAI', 'Wybierz segment.')
            return
        try:
            self.project_service.flush_saves()
            settings = self.ai_panel.get_settings()
            translator = self._ai_translator()
            glossary = self.project_service.list_glossary(self.current_project.id)
            tm = [match.entry for match in self.project_service.find_tm_matches(
                self.current_project, segment.source, limit=5, threshold=0.35)]
            snapshot = (self.current_project.id, segment.id, segment.source, segment.target)
            source_lang = self.current_project.source_language
            target_lang = self.current_project.target_language
            self.ai_panel.progress_label.setText('OpenAI: tłumaczenie bieżącego segmentu…')
            self._ai_submit(
                lambda: translator.translate(snapshot[2], source_lang, target_lang, glossary, tm, settings),
                lambda result: self._ai_show_preview(snapshot, result),
            )
        except Exception as exc:
            QMessageBox.warning(self, 'OpenAI', str(exc))

    def _ai_show_preview(self, snapshot, result: AIResult) -> None:
        """Pokaż propozycję AI, zapamiętując stan segmentu do późniejszego sprawdzenia konfliktów."""
        self._ai_preview_context = (snapshot[0], snapshot[1], snapshot[2], snapshot[3], result)
        self.ai_panel.display_result(snapshot[1], result)
        self.ai_panel.progress_label.setText('Propozycja gotowa. Zweryfikuj QA przed zastosowaniem.')

    def _translate_ai_batch(self) -> None:
        """Uruchom tłumaczenie wsadowe pustych segmentów z limitem kosztu i liczby pozycji."""
        if self.current_project is None or self.project_service is None:
            QMessageBox.warning(self, 'OpenAI', 'Najpierw otwórz projekt.')
            return
        try:
            settings = self.ai_panel.get_settings()
            translator = self._ai_translator()
            # Batch is strictly opt-in, costs and size explicitly bounded.
            project = self.current_project
            self.project_service.flush_saves()
            candidates = (self.segment_editor.selected_segments()
                          if self.ai_panel.batch_scope.currentData() == 'selected'
                          else self.segment_editor.all_segments())
            candidates = [s for s in candidates if s.id is not None and not s.target.strip()
                          and s.status not in {SegmentStatus.REVIEWED, SegmentStatus.APPROVED}]
            candidates = candidates[:self.ai_panel.batch_count.value()]
            if not candidates:
                QMessageBox.information(self, 'OpenAI', 'Brak pustych Target w wybranym zakresie.')
                return
            budget = self.ai_panel.batch_budget.value()
            from gamecat.ai.core import estimate_cost, AIUsage
            estimate_cost(AIUsage(1, 1), settings)
            reply = QMessageBox.question(
                self, 'OpenAI API',
                f'Wysłać do OpenAI maksymalnie {len(candidates)} segmentów? '
                f'Limit szacowanego kosztu: {budget:.3f} USD. '
                'To NIE jest twardy limit wydatków naliczanych przez API. '
                'Bezproblemowe wyniki QA zostaną automatycznie zapisane, pozostałe trafią do podglądu.',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            glossary = self.project_service.list_glossary(project.id)
            tm = self.project_service.get_tm_entries(project)
            tuples = [(s.id, s.source, s.target) for s in candidates]
            self._ai_cancel.clear()
            self.ai_panel.progress_label.setText('OpenAI: przygotowywanie wsadu…')
            runner = BatchTranslator(translator)
            self._ai_submit(
                lambda: runner.translate_items(
                    tuples, project.source_language, project.target_language, glossary, tm, settings,
                    budget_usd=budget, max_items=len(tuples), cancel=self._ai_cancel,
                    on_progress=lambda current, total, report: self._ai_progress_queue.put((current, total))
                ),
                lambda report: self._ai_batch_finished(project, report),
            )
        except Exception as exc:
            QMessageBox.warning(self, 'OpenAI', str(exc))

    def _cancel_ai_batch(self) -> None:
        """Poproś o zatrzymanie wsadu po bieżącym żądaniu HTTP."""
        self._ai_cancel.set()
        self.ai_panel.progress_label.setText(
            'Zatrzymywanie: bieżącego zapytania HTTP nie można przerwać natychmiast…'
        )

    def _ai_batch_finished(self, project: Project, report: BatchReport) -> None:
        """Wyświetl wyniki wsadu i wstaw do pustych segmentów propozycje bez ostrzeżeń QA."""
        if report.errors:
            QMessageBox.warning(self, 'OpenAI — błędy wsadu',
                                'Część żądań nie powiodła się:\n' + '\n'.join(report.errors[:5]))
        self._ai_batch_results = list(report.results)
        self.ai_panel.show_batch(report)
        if self.current_project is None or self.project_service is None or project.id != self.current_project.id:
            return
        from gamecat.qa.validator import validate_segment
        current_glossary = self.project_service.list_glossary(project.id)
        applied = 0
        failed = 0
        for item in report.results:
            if item.result.qa_warnings or validate_segment(
                item.original_source, item.result.translation, current_glossary
            ):
                continue
            try:
                self.project_service.apply_ai_translation(
                    project, item.segment_id, item.result.translation, item.result.model,
                    expected_source=item.original_source, expected_target=item.original_target,
                )
                applied += 1
            except ValueError:
                failed += 1
        self._reload_segments()
        self.ai_panel.progress_label.setText(
            self.ai_panel.progress_label.text() +
            f' Automatycznie zapisano: {applied}; konflikty: {failed}; '
            f'do ręcznego sprawdzenia QA: {sum(bool(i.result.qa_warnings) for i in report.results)}.'
        )

    def _preview_ai_batch_item(self, index: int) -> None:
        """Pokaż w podglądzie wybraną pozycję z wyników wsadu."""
        if not 0 <= index < len(self._ai_batch_results) or self.current_project is None:
            return
        item = self._ai_batch_results[index]
        self._ai_show_preview((self.current_project.id, item.segment_id,
                               item.original_source, item.original_target), item.result)

    def _apply_ai_preview(self) -> None:
        """Wstaw (ewentualnie poprawioną) propozycję AI do segmentu po kontroli konfliktów."""
        if self.current_project is None or self.project_service is None or self._ai_preview_context is None:
            return
        project_id, segment_id, source, old_target, result = self._ai_preview_context
        if project_id != self.current_project.id:
            QMessageBox.warning(self, 'OpenAI', 'Wynik pochodzi z innego projektu.')
            return
        text = self.ai_panel.preview.toPlainText()
        if not text.strip():
            QMessageBox.warning(self, 'OpenAI', 'Puste tłumaczenie nie może zostać zastosowane.')
            return
        from gamecat.qa.validator import validate_segment
        qa_issues = validate_segment(source, text, self.project_service.list_glossary(project_id))
        if qa_issues:
            reply = QMessageBox.warning(
                self, 'OpenAI — ostrzeżenia QA',
                'Wykryto problemy QA:\n' + '\n'.join(i.message for i in qa_issues[:10]) +
                '\nZastosować mimo błędów?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        segment = self.project_service.get_segment(segment_id)
        replace = bool(segment.target.strip())
        protected = segment.status in {SegmentStatus.REVIEWED, SegmentStatus.APPROVED}
        if replace:
            reply = QMessageBox.question(
                self, 'OpenAI — nadpisanie',
                f'Segment #{segment_id} ma już tłumaczenie. Nadpisać je wynikiem AI?'
                + (' Status po recenzji zostanie cofnięty do TRANSLATED.' if protected else ''),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        try:
            self.project_service.apply_ai_translation(
                self.current_project, segment_id, text, result.model,
                replace=replace, include_reviewed=protected,
                expected_source=source,
                expected_target=old_target,
            )
        except Exception as exc:
            QMessageBox.warning(self, 'OpenAI', f'Nie zastosowano propozycji: {exc}')
            return
        self._reload_segments()
        self.segment_editor.select_segment_by_id(segment_id, reveal=True)
        self._ai_preview_context = None
        self.ai_panel.apply_button.setEnabled(False)
        self.statusBar().showMessage(f'Zapisano tłumaczenie AI segmentu #{segment_id}.', 5000)
