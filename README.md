# GameCAT

GameCAT to desktopowy program CAT (Computer-Assisted Translation) do lokalizacji gier, przygotowany jako projekt zaliczeniowy z przedmiotu **Zaawansowane techniki programowania w języku Python**.

## Funkcje wersji 0.2

- projekty tłumaczeniowe i segmenty Source/Target,
- SQLite,
- import i eksport TXT/CSV/JSON,
- statusy `NEW`, `TRANSLATED`, `REVIEWED`, `APPROVED`,
- QA placeholderów, tagów, spacji i terminologii,
- glosariusz,
- Translation Memory z fuzzy matching,
- matcher równoległy `ProcessPoolExecutor`,
- zadania I/O przez `ThreadPoolExecutor`,
- autosave z `Queue` i `Lock`,
- GUI PySide6,
- benchmark GIL: sequential / threads / processes.

## Wymagania

- Python 3.12+
- PySide6
- pytest
- matplotlib

Instalacja:

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

Testy:

```bash
pytest -v
```

Benchmark:

```bash
python benchmarks/gil_benchmark.py
```

## Mapowanie wymagań zaliczeniowych

| Zagadnienie | Gdzie w kodzie |
|---|---|
| Dekorator funkcji | `gamecat/utils/decorators.py -> measure_time()` |
| Dekorator z parametrami | `gamecat/utils/decorators.py -> retry(attempts, delay)` |
| Dekorator metody korzystający z `self` | `gamecat/utils/decorators.py -> requires_project()` + `gamecat/gui/main_window.py` |
| `@property` + setter | `gamecat/models/segment.py -> Segment.target`, `Segment.status` |
| Iterator | `gamecat/utils/iterators.py -> SegmentIterator` |
| Generator / wyrażenie generujące | `gamecat/utils/generators.py`, importer TXT, matcher TM |
| Regex z grupami nazwanymi | `gamecat/qa/patterns.py -> BRACE_RE`, `PRINTF_OR_TAG_RE` |
| Wątki | `gamecat/concurrency/io_workers.py -> ThreadPoolExecutor` |
| Synchronizacja Queue/Lock | `gamecat/concurrency/save_queue.py -> SaveQueue` |
| Procesy | `gamecat/tm/parallel_matcher.py -> ProcessPoolExecutor` |
| GIL | `benchmarks/gil_benchmark.py` |
| GUI | `gamecat/gui/` |
| Testy | `tests/` |
| Logging | `gamecat/logging_config.py` |

## Wnioski z benchmarku GIL

Benchmark wykazał, że najwydajniejszą spośród badanych metod była wieloprocesowość, osiągając niemal dwukrotne przyspieszenie względem wykonywania sekwencyjnego.

Wyniki są zgodne z możliwością omijania ograniczeń GIL przez wykorzystanie osobnych procesów. W standardowym Pythonie GIL ogranicza równoległe wykonywanie kodu Pythona przez wątki w obrębie jednego interpretera.


## Import i eksport w GUI (v0.2)

1. Wybierz **Plik → Nowy projekt** i wskaż plik bazy projektu `.sqlite`, albo otwórz istniejący projekt przez **Plik → Otwórz**.
2. Wybierz **Plik → Import** i wskaż plik `.txt`, `.csv` lub `.json`.
   - TXT: każda linia staje się osobnym segmentem.
   - JSON: obsługiwany jest słownik `key: source` albo lista obiektów zawierających `source` oraz opcjonalnie `key` i `target`.
   - CSV: program wyświetla okno mapowania kolumn: **Klucz / ID**, **Tekst źródłowy** i opcjonalne **Tłumaczenie**.
3. Po zakończeniu importu lista segmentów odświeża się automatycznie, a pasek stanu pokazuje liczbę zaimportowanych pozycji.
4. Wybierz **Plik → Eksport**, aby zapisać tłumaczenie jako TXT, CSV lub JSON. Format jest określany na podstawie rozszerzenia pliku.

Import i eksport są wykonywane przez pulę wątków I/O, natomiast GUI odpytuje stan operacji przez `QTimer`, dzięki czemu interfejs nie jest aktualizowany bezpośrednio z wątku roboczego.
