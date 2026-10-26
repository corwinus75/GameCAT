# GameCAT 1.0 — test akceptacyjny GUI (Windows/PySide6)

**Status:** do wykonania na komputerze z zainstalowaną biblioteką PySide6. W środowisku wydania 1.0 testy PySide6 nie mogły zostać uruchomione. Ten dokument nie jest protokołem już wykonanego testu.

## Środowisko i przygotowanie

- [ ] Sprawdzić `python --version` (≥3.12), `python -m pip install -r requirements.txt` oraz `python -c "import PySide6"`.
- [ ] Uruchomić `python -m pytest -q` i zapisać wynik; testy GUI nie powinny być pomijane, jeśli PySide6 jest zainstalowane.
- [ ] Otworzyć `python main.py`; okno główne pokazuje edytor i panele QA, TM, glosariusz, OpenAI.
- [ ] W testach wykorzystać wyłącznie kopie plików z `sample_data` i kopię bazy projektu.

## Lista czynności

- [ ] **Nowy projekt:** utworzyć `Demo.sqlite`, zamknąć program i ponownie otworzyć bazę.
- [ ] **Import:** TXT/CSV/JSON; dla CSV wskazać prawidłowe kolumny; sprawdzić liczbę segmentów.
- [ ] **Formaty 0.11:** TSV/XLSX/XML i zagnieżdżony JSON z profilem; zachować ID i dodatkowe metadane.
- [ ] **Tłumaczenie:** zmienić Target, `Ctrl+S`, otworzyć bazę ponownie; zapis pozostał.
- [ ] **Statusy:** `Ctrl+1..4`, filtr i zaznaczanie wielu segmentów; postęp powinien aktualizować się zgodnie ze statusem.
- [ ] **Glosariusz:** utworzyć `sword → miecz | ostrze`, sprawdzić podpowiedź dla segmentu i wykrywanie brakującego wariantu.
- [ ] **QA:** wprowadzić brak placeholdera `{name}`, `Ctrl+Shift+Q`, dwuklik wyniku przenosi do właściwego segmentu; poprawienie Target usuwa problem.
- [ ] **TM:** dodać poprawny Target do TM, sprawdzić sugestię oraz analizę projektu względem TM.
- [ ] **Zamiana:** `Ctrl+H`, podgląd przed wykonaniem, ochrona `REVIEWED`/`APPROVED`; niepoprawny regex nie może zmieniać bazy.
- [ ] **Import Target:** zmienić tłumaczenie z `APPROVED`, sprawdzić cofnięcie statusu do `TRANSLATED`; identyczna wartość zachowuje status.
- [ ] **Eksport:** TXT/CSV/JSON i eksport wg oryginalnego szablonu; sprawdzić, czy nie zostały zmienione pola nietłumaczone.
- [ ] **AI:** bez wydawania środków sprawdzić widoczność panelu OpenAI, komunikaty braku klucza i zabezpieczenia przed nadpisaniem. Płatne wywołanie tylko za świadomą zgodą.
- [ ] **Zamknięcie:** wpisać tekst i od razu zamknąć aplikację, a po ponownym uruchomieniu sprawdzić autosave.

## Protokół

Data: __________  System: __________  Python: __________  PySide6: __________

Wynik: PASS / FAIL (zaznaczyć)  Uwagi i zgłoszone błędy: ________________________
