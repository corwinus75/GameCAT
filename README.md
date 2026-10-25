# GameCAT

GameCAT to desktopowy program CAT (Computer-Assisted Translation) do lokalizacji gier, przygotowany jako projekt zaliczeniowy z przedmiotu **Zaawansowane techniki programowania w języku Python**.

## Funkcje wersji 0.4

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

## QA w GUI (v0.3)

- Panel **QA → Bieżący** aktualizuje się automatycznie po wybraniu segmentu i po każdej zmianie pola Target.
- Sprawdzane są m.in. brakujące i dodatkowe placeholdery/tagi, puste tłumaczenie, `Source == Target`, liczba nowych linii, spacje brzegowe, podwójne spacje oraz wymagane terminy z glosariusza.
- Tokeny lokalizacyjne `{g|...}`, `{d|...}` i `{mf|...}` są porównywane strukturalnie, dzięki czemu przetłumaczona zawartość wewnątrz tokenu nie jest błędnie zgłaszana jako brak placeholdera.
- Polecenie **QA → Sprawdź cały projekt** (`Ctrl+Shift+Q`) skanuje wszystkie segmenty i zapisuje wyniki w zakładce **Projekt**.
- Dwukrotne kliknięcie wyniku QA projektu przenosi do odpowiedniego segmentu; jeśli segment był ukryty przez filtr lub wyszukiwanie, edytor automatycznie go ujawnia.
- Panel glosariusza jest wczytywany razem z projektem i te same wpisy są używane przy walidacji pojedynczego segmentu i pełnego projektu.

W v0.3 usunięto także wyścig przy jednoczesnym zapisie do SQLite z wątku autosave i z głównego wątku. Dostęp transakcyjny do współdzielonego połączenia jest serializowany blokadą `RLock`.

## Translation Memory i import tłumaczeń (v0.4)

### Import tłumaczenia do istniejącego projektu

Po zaimportowaniu tekstu źródłowego wybierz **Plik → Importuj tłumaczenie…**. Operacja aktualizuje wyłącznie pole **Target** istniejących segmentów — tekst **Source** pozostaje bez zmian.

- **TXT** — kolejne linie są dopasowywane do segmentów według pozycji (`1 → 1`, `2 → 2`, itd.). Jeżeli plik ma więcej linii niż projekt, import zostaje przerwany, aby uniknąć przesunięcia tłumaczeń.
- **CSV** — pojawia się okno mapowania. Można wybrać kolumnę **Klucz / ID** i kolumnę **Tłumaczenie**. Jeśli klucz nie zostanie wskazany, wiersze są dopasowywane według kolejności.
- **JSON** — słownik `{ "KEY": "tłumaczenie" }` jest dopasowywany po kluczu. Lista może zawierać napisy (dopasowanie pozycyjne) albo obiekty z `target` oraz opcjonalnym `key` lub `position`.

Niepuste zaimportowane tłumaczenie zmienia status segmentu `NEW` na `TRANSLATED`. Pasek stanu pokazuje liczbę zaktualizowanych i niedopasowanych pozycji.

### Translation Memory w GUI

Panel **TM** jest teraz aktywny. Po wybraniu segmentu program wyszukuje do pięciu podobnych wpisów pamięci dla pary językowej projektu. Dwukrotne kliknięcie sugestii wstawia jej Target do bieżącego segmentu.

Aby zasilić pamięć tłumaczeniową, wybierz **TM → Dodaj tłumaczenia projektu do pamięci**. Do TM trafiają wyłącznie segmenty z niepustym Target. Identyczne pary Source/Target dla tej samej pary językowej nie są dodawane ponownie.