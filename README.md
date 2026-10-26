# GameCAT

GameCAT to desktopowy program CAT (Computer-Assisted Translation) do lokalizacji gier, przygotowany jako projekt zaliczeniowy z przedmiotu **Zaawansowane techniki programowania w języku Python**.

## Funkcje wersji 1.0.0

- projekty tłumaczeniowe i segmenty Source/Target,
- wyszukiwanie Source/Target z regex i sortowaniem, filtry QA/TM, podgląd masowej zamiany Target oraz nawigacja do braków/QA,
- SQLite,
- import i eksport TXT/CSV/JSON/TSV/XLSX/XML oraz mapowanie pól i eksport według oryginalnego szablonu,
- workflow statusów `NEW`, `TRANSLATED`, `REVIEWED`, `APPROVED` z ręczną i masową zmianą, filtrami, skrótami i licznikiem postępu,
- QA placeholderów, tagów, spacji i terminologii,
- projektowy glosariusz z wieloma równorzędnymi wariantami, edycją GUI oraz importem/eksportem CSV+JSON,
- Translation Memory z fuzzy matching, możliwością korzystania z osobnej bazy SQLite,
  importem/eksportem CSV+JSON, progiem dopasowania i automatycznym dodawaniem zatwierdzonych segmentów,
- analiza projektu względem TM (progi 100% / 95–99 / 85–94 / 75–84 / 50–74 / brak) sekwencyjnie, w wątkach lub w procesach, z wsadową pretranslacją dopasowań ≥50% (domyślnie i bez potwierdzenia tylko 100%),
- zadania I/O przez `ThreadPoolExecutor`,
- nieblokujący autosave z `Queue`, scalaniem szybkich zmian i `Lock`,
- GUI PySide6,
- benchmark GIL: sequential / threads / processes.

## Wymagania

- Python 3.12+
- PySide6
- pytest
- matplotlib
- openai oraz keyring (funkcje OpenAI API z wersji 0.10)

Instalacja:

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
python -m pip install -r requirements.txt
python main.py
```

Testy:

```bash
python -m pytest -v
```

Benchmark (wyniki trafiają do `benchmarks/results.md`, `results.json` i `gil_benchmark.png`):

```bash
python benchmarks/gil_benchmark.py --update-readme   # pełny pomiar + tabela w README
python benchmarks/gil_benchmark.py --quick           # szybkie sprawdzenie działania
```

Dane testowe: przykładowe pliki w `sample_data/`, a dane do benchmarku generuje deterministycznie `benchmarks/dataset.py`.

## Mapowanie wymagań zaliczeniowych

| Zagadnienie | Gdzie w kodzie | Gdzie działa w programie |
|---|---|---|
| Dekorator funkcji + `functools.wraps` | `gamecat/utils/decorators.py → measure_time` | czasy importu, eksportu, QA projektu i analizy TM w logu `gamecat.timing` (`ProjectService`) |
| Dekorator z parametrami | `gamecat/utils/decorators.py → retry(attempts, delay, exceptions, when)` | `SaveQueue._save_batch` – ponowienie zapisu, gdy plik bazy blokuje inny proces (`database is locked`) |
| Dekorator metody korzystający z `self` | `gamecat/utils/decorators.py → requires_project` | metody `MainWindow` wymagające otwartego projektu |
| `@property` z setterem | `gamecat/models/segment.py → Segment.target`, `Segment.status` (walidacja statusu) | każda zmiana tłumaczenia/statusu |
| `@staticmethod` | `SaveQueue._snapshot`, `SaveQueue._coalesce`, `ProjectService._export_file` | autosave, eksport |
| Własny iterator (`__iter__`, `__next__`) | `gamecat/database/segment_iterator.py → SegmentBatchIterator` | QA całego projektu, eksport, analiza TM – segmenty czytane z SQLite partiami |
| Generatory (`yield`) | `gamecat/importers/*.py`, `benchmarks/dataset.py → _sentences` | strumieniowy import TXT/CSV/JSON |
| Wyrażenia generujące | `ProjectService._import_file`, `ProjectService.analyze_project_tm`, `tm/analysis.py` | import w jednej transakcji, przygotowanie danych do analizy |
| Regex z grupami nazwanymi | `gamecat/qa/patterns.py → BRACE_RE`, `PRINTF_OR_TAG_RE` | QA placeholderów i tagów |
| Regex (tokenizacja) | `gamecat/tm/similarity.py → _WORD_RE`, `tm/analysis.py → _WORD_RE` | fuzzy matching TM, liczenie słów w analizie |
| Wątki + `Queue` / `Lock` / `RLock` | `gamecat/concurrency/save_queue.py → SaveQueue`, `concurrency/io_workers.py → IOWorkerPool`, `database/connection.py → ThreadSafeConnection` | autosave w tle, import/eksport bez blokowania GUI |
| Procesy | `gamecat/tm/analysis.py → analyze()` (`ProcessPoolExecutor`, kontekst `spawn`, `initializer`) | **TM → Analiza projektu względem TM** (`Ctrl+Shift+A`) |
| Pomiar GIL | `benchmarks/gil_benchmark.py` | ta sama analiza TM: sekwencyjnie / wątki / procesy |
| Zaawansowane wyszukiwanie i regex (0.9) | `gamecat/search/operations.py` → `filter_segments`, `preview_replacements` | filtry, zamiana Target, sortowanie |
| GUI | `gamecat/gui/` | PySide6 |
| Import/eksport lokalizacji 0.11 | `gamecat/localization/{profiles,exchange,xlsx}.py` | TSV/XLSX/XML, zagnieżdżony JSON, zachowanie struktury szablonu |
| Eksport/import TM 0.8 | `gamecat/tm/exchange.py`, `ProjectService.import_tm_file` | transakcyjny import TM, eksport CSV/JSON |
| Testy | `tests/` (pytest) | |
| Logging | `gamecat/logging_config.py` | plik `gamecat.log` |

W ramach finalizacji poprawiono również bezpieczeństwo importu już przetłumaczonego pliku: nowy Target unieważnia poprzednie zatwierdzenie (`REVIEWED`/`APPROVED`), natomiast import identycznego tekstu nie odbiera statusu. Klucz OpenAI API nie należy do danych projektu.

## Nowości w wersji 0.11

Formaty TSV, XLSX, XML i konfigurowalne JSON oraz profile per projekt — szczegóły, przykłady i zasady bezpiecznego eksportu: **[Dokumentacja 0.11](docs/releases/0.11.md)**.

## Integracja OpenAI API w wersji 0.10

Instrukcje obsługi, API i kosztów: **[Dokumentacja 0.10](docs/releases/0.10.md)**.

## Nowości w wersji 0.9

Skróty: **Ctrl+F** wyszukiwanie, **Ctrl+H** zamiana w Target z podglądem, **F8 / Shift+F8** następny/poprzedni błąd QA, **Ctrl+Alt+strzałka dół/góra** następny/poprzedni segment bez tłumaczenia. Zaawansowane filtry działają łącznie. Szczegóły, zasady ochrony recenzji i zachowania masowego zastępowania: **[Dokumentacja 0.9](docs/releases/0.9.md)**.

## Obsługa TM w wersji 0.8

Dokładny opis formatu CSV/JSON i zasad bezpieczeństwa:
**[Dokumentacja GameCAT 0.8](docs/releases/0.8.md)**.

W menu **TM** można wskazać zewnętrzną bazę `.sqlite` lub powrócić do TM
przechowywanej w pliku projektu. Każdy projekt zapamiętuje swoją aktywną
bazę TM oraz minimalny próg sugestii w panelu TM (domyślnie 45%).
Zmiana magazynu nie scala automatycznie ich zawartości — do przenoszenia par
służą **Eksportuj TM** i **Importuj TM**. Pliki wymiany mogą zawierać wiele
par językowych, lecz podpowiedzi i analiza projektu wybierają wyłącznie
zgodną parę. Zatwierdzenie niepustego segmentu (`APPROVED`) dodaje jego
parę Source/Target do aktywnego magazynu, bez duplikatów.

Dla dużych zbiorów można włączyć **Analizę projektu względem TM** i wybrać
próg pretranslacji (50–100%). Pretranslacja nie nadpisuje istniejącego
Target i ustawia jedynie `TRANSLATED` dla wcześniej nowych segmentów.
Propozycje fuzzy poniżej 100% wymagają ręcznej recenzji i QA.

## Analiza projektu względem TM (od v0.5.1)

**TM → Analiza projektu względem TM…** porównuje każdy segment projektu ze wszystkimi wpisami pamięci tłumaczeniowej dla pary językowej projektu i pokazuje liczbę segmentów oraz słów w progach dopasowania. W oknie można wybrać tryb wykonania (procesy, wątki, sekwencyjnie) i liczbę workerów, co pozwala porównać tryby bezpośrednio w programie. Przycisk **Wstaw dopasowania ≥X%** wpisuje tłumaczenia z TM do pustych segmentów. Domyślny próg 100% można obniżyć po potwierdzeniu ryzyka; istniejące tłumaczenia nie są nadpisywane.

Analiza działa w wątku I/O, który uruchamia pulę procesów, więc GUI pozostaje responsywne. Pamięć tłumaczeniowa jest przekazywana do każdego procesu tylko raz, przez `initializer` puli; dopasowania dokładne są wyszukiwane słownikiem w O(1), a fuzzy matching liczony jest tylko dla pozostałych segmentów. Projekty mniejsze niż 200 segmentów są analizowane sekwencyjnie, bo start puli procesów kosztowałby więcej niż sama praca.

## Wyniki benchmarku GIL

<!-- BENCHMARK:START -->
| Tryb | Mediana [s] | Min [s] | Max [s] | Przyspieszenie |
|---|---:|---:|---:|---:|
| Sekwencyjnie | 3.794 | 3.753 | 3.872 | 1.00x |
| Wątki | 3.707 | 3.641 | 3.867 | 1.02x |
| Procesy | 2.254 | 2.090 | 2.380 | 1.68x |

Dane: 600 segmentów × 1200 wpisów TM, 22 workerów, 5 powtórzeń (mediana), seed 2026.  
Środowisko: Python 3.14.0 (CPython), Windows 11, 22 rdzeni logicznych, GIL włączony.

![Wykres benchmarku](benchmarks/gil_benchmark.png)
<!-- BENCHMARK:END -->

## Wnioski z benchmarku GIL

Pomiar z wydania 1.0 dotyczy tej samej funkcji analizy Translation Memory dla trzech trybów: sekwencyjnego, `ThreadPoolExecutor` i `ProcessPoolExecutor`. Wszystkie tryby przeszły kontrolę identyczności wyników; wykonano rozgrzewkę i trzy rundy pomiarowe z rotacją kolejności. Dla 160 segmentów i 240 wpisów TM mediana wyniosła odpowiednio **0,260 s**, **0,244 s** i **1,152 s** (CPython 3.13.5, Linux, 2 workery). W tak małym zadaniu koszt uruchomienia procesów i przekazania danych jest większy od potencjalnego zysku; dlatego procesy osiągnęły tylko **0,23×** prędkości odniesienia. Minimalna różnica między wątkami a wykonaniem sekwencyjnym przy takich czasach nie dowodzi przyspieszenia pracy CPU przez wątki. Przy włączonym GIL w standardowym CPythonie jednocześnie wykonywać kod Pythona może tylko jeden wątek, więc do CPU-bound wybieramy procesy dopiero dla dostatecznie dużych zadań. **W pomiarze historycznym na Windows 11** z większym zestawem danych (600 × 1200) procesy osiągnęły **2,09×**, a wątki **1,00×**. Różnica nie jest sprzecznością: wydajność zależy od rozmiaru zadania, parametrów maszyny i narzutu komunikacji. Wątki w GameCAT pozostają właściwym wyborem dla I/O (import, eksport, autosave), a dla analizy TM aplikacja może wybrać procesy lub sekwencyjne wykonanie zależnie od wielkości projektu.

Historyczne wyniki: [benchmark 0.5.1 / Windows](benchmarks/history_0.5.1_windows.md). Wynik 1.0: [tabela](benchmarks/results.md), [JSON](benchmarks/results.json), [wykres](benchmarks/gil_benchmark.png). Procedurę można powtórzyć komendą: `python benchmarks/gil_benchmark.py --segments 160 --tm 240 --repeats 3 --workers 2 --update-readme`. Większy zestaw jest opcjonalny i trwa dłużej.

## Problemy napotkane podczas realizacji

- **Wyścig przy zapisie do SQLite (v0.3).** Wątek autosave i wątek GUI korzystały ze wspólnego połączenia, co prowadziło do przeplatania się transakcji. Rozwiązaniem jest `ThreadSafeConnection`, które serializuje transakcje blokadą `RLock`.
- **Zapis przy każdym naciśnięciu klawisza (v0.5).** Synchroniczny zapis spowalniał edytor. `SaveQueue` przenosi zapis do osobnego wątku i scala szybkie zmiany tego samego segmentu (debounce), a `flush()` wyznacza granicę trwałości przed QA, eksportem i zamknięciem projektu.
- **Częściowy import.** Zapis każdego segmentu w osobnej transakcji był wolny, a błąd w połowie pliku zostawiał w bazie część danych. Import działa teraz w jednej transakcji, a import tłumaczeń najpierw dopasowuje wszystkie wiersze w pamięci i zapisuje je jednym `executemany`.
- **Źle dobrana granulacja procesów.** Pierwsza wersja równoległego matchera tworzyła pulę procesów dla pojedynczego zapytania i przesyłała TM z każdym zadaniem; narzut startu procesów był większy niż zysk. Procesy opłacają się dopiero dla analizy całego projektu, z TM przekazaną raz przez `initializer`.
- **Wiarygodność pomiarów.** Pierwszy benchmark mierzył tryby zawsze w tej samej kolejności i bez rozgrzewki, przez co wyniki potrafiły sugerować przyspieszenie wątków, sprzeczne z działaniem GIL. Obecna wersja rozgrzewa każdy tryb, rotuje kolejność i raportuje medianę.

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


## Autosave i współbieżne I/O (v0.5)

Edycja pola **Target** nie wykonuje już synchronicznego zapisu SQLite przy każdym naciśnięciu klawisza. Zamiast tego migawki segmentów trafiają do `SaveQueue` obsługiwanej przez osobny wątek. Szybkie kolejne zmiany tego samego segmentu są scalane po krótkim okresie bezczynności, dzięki czemu do bazy trafia przede wszystkim najnowsza wersja tekstu, a GUI pozostaje responsywne.

Po prawej stronie paska stanu widoczny jest stan autosave: **Autosave: zapisuję… (N)** albo **Autosave: zapisano**. `Ctrl+S` wymusza opróżnienie kolejki i stanowi jawną granicę trwałości. Operacje odczytujące cały projekt (m.in. QA, eksport i synchronizacja TM) również czekają na zapis oczekujących zmian, więc nie pracują na nieaktualnej zawartości SQLite.

Przy zamykaniu projektu `SaveQueue` jest opróżniana przed zamknięciem połączenia z bazą. Jeżeli zapis w tle zakończy się błędem, błąd jest propagowany do GUI zamiast zostać cicho utracony. Import i eksport nadal korzystają z `ThreadPoolExecutor`, natomiast transakcje SQLite są serializowane przez `RLock`.


## Workflow statusów tłumaczenia (v0.6)

Każdy segment ma jeden z czterech statusów: **NEW**, **TRANSLATED**, **REVIEWED** albo **APPROVED**. Status bieżącego segmentu można zmienić z listy **Status segmentu** w edytorze. Menu **Workflow** udostępnia również skróty klawiaturowe:

- `Ctrl+1` → `NEW`,
- `Ctrl+2` → `TRANSLATED`,
- `Ctrl+3` → `REVIEWED`,
- `Ctrl+4` → `APPROVED`.

Lista segmentów pokazuje skrócone oznaczenia `[N]`, `[T]`, `[R]`, `[A]`. Istniejący filtr **Filtr statusu** pozwala wyświetlić tylko segmenty na wybranym etapie pracy. `Ctrl+Enter` potwierdza bieżące tłumaczenie: segment `NEW` przechodzi wtedy do `TRANSLATED`, ale segment oznaczony już jako `REVIEWED` lub `APPROVED` nie jest cofany do wcześniejszego etapu.

### Masowa zmiana statusu

Na liście można zaznaczyć wiele segmentów (`Ctrl`/`Shift`, standardowo jak w Windows), a następnie wybrać status z menu **Workflow** albo użyć `Ctrl+1..4`. Zmiana jest zapisywana do SQLite jedną operacją grupową po wcześniejszym opróżnieniu kolejki autosave, dzięki czemu oczekująca migawka tekstu nie może nadpisać nowszego statusu.

### Postęp projektu

Po prawej stronie paska stanu wyświetlany jest licznik:

`T: translated-or-better / wszystkie | R: reviewed-or-better / wszystkie | A: approved / wszystkie`

Wskaźniki są kumulacyjne: `REVIEWED` i `APPROVED` liczą się także jako ukończone tłumaczenie, a `APPROVED` jako ukończona recenzja. Po najechaniu na licznik tooltip pokazuje liczby dla czterech statusów rozłącznych.


## Glosariusz projektu (v0.7)

Glosariusz jest przypisany wyłącznie do bieżącego projektu. Jeden termin Source może mieć wiele równorzędnych, dopuszczalnych wariantów Target. Panel **Glosariusz** pozwala wyszukiwać terminy, edytować Source, opis i `case_sensitive`, dodawać/usuwać warianty oraz usuwać całe terminy. Dwukrotne kliknięcie wariantu wstawia go do pola Target w miejscu kursora.

Dopasowanie terminologii działa na całych słowach i frazach. Przykładowo `sword` pasuje do `Take the sword.`, ale nie do `swordsman`. Terminy zawierające znaki specjalne, np. `C++` lub `+1 sword`, są traktowane literalnie. Jeżeli `case_sensitive` jest włączone, wielkość liter ma znaczenie zarówno w Source, jak i w dopuszczalnych wariantach Target.

QA uznaje termin za poprawny, jeśli w Target występuje przynajmniej jeden dopuszczalny wariant. Jeśli żaden wariant nie występuje, komunikat zawiera termin Source oraz pełną listę dozwolonych tłumaczeń.

### Import CSV

Kanoniczny format:

```csv
source,target,description,case_sensitive
sword,miecz,Broń biała,false
sword,ostrze,Broń biała,false
XP,PD,Punkty doświadczenia,true
```

Każdy wiersz odpowiada jednemu wariantowi. Wymagane są kolumny `source` i `target`; `description` i `case_sensitive` są opcjonalne. Obsługiwane jest UTF-8 i UTF-8-SIG. Puste Source/Target są liczone jako błędne rekordy i pomijane. Import scala istniejące dane bez usuwania wariantów i bez tworzenia duplikatów.

### Import JSON

Kanoniczny format:

```json
[
  {
    "source": "sword",
    "targets": ["miecz", "ostrze"],
    "description": "Broń biała",
    "case_sensitive": false
  }
]
```

`targets` musi być listą niepustych napisów. Import JSON stosuje tę samą politykę scalania co CSV.

Po imporcie pasek stanu raportuje liczbę nowych terminów, nowych wariantów, duplikatów oraz błędnych rekordów. Błąd strukturalny pliku jest wykrywany przed zapisem, więc nie pozostawia częściowo zaimportowanego glosariusza.

### Eksport

CSV zapisuje jeden wariant na wiersz. JSON zapisuje jeden obiekt na termin z tablicą `targets`. Eksport obejmuje tylko glosariusz aktualnego projektu. Przykładowe pliki znajdują się w `sample_data/glossary_sample.csv` i `sample_data/glossary_sample.json`.

### Migracja projektów 0.6

Przy otwarciu starej bazy GameCAT 0.6 płaska tabela glosariusza jest automatycznie migrowana do relacji `glossary_terms` + `glossary_translations`. Warianty tego samego terminu są scalane, duplikaty usuwane, a wpisy globalne z wcześniejszego modelu nie są przypisywane do projektu. Migracja jest idempotentna i wykonywana transakcyjnie.

## GameCAT 0.10 — OpenAI API

Panel **OpenAI** pozwala tłumaczyć pojedyncze segmenty (skrót `Ctrl+Shift+T`)
i wsadowo puste Target z wykorzystaniem glosariusza, TM i QA.

**Klucz API:** `OPENAI_API_KEY` lub hasło wpisane tymczasowo w panelu;
opcjonalnie zapis w systemowym magazynie poświadczeń za pomocą `keyring`.
**Nie jest zapisywany w bazie projektu.**

Po wygenerowaniu pojedynczego tłumaczenia najpierw sprawdź i ewentualnie
popraw podgląd, a potem kliknij **Zastosuj propozycję do Target**. Zmiana
istniejącego Target wymaga potwierdzenia, a wynik z QA wymaga dodatkowej zgody.
Segmenty oznaczone `[AI]` wymagają sprawdzenia przez tłumacza.

Przy tłumaczeniu wsadowym konieczne są ręcznie ustawione ceny za 1 mln tokenów,
budżet i maksymalna liczba segmentów. Budżet ma charakter **szacunkowy**,
nie jest twardym limitem naliczania opłat. Płatne żądania mogą zostać
naliczone nawet po anulowaniu. Tekst i dopasowania TM/glosariusza są
wysyłane na serwery OpenAI.

Szczegóły: [docs/releases/0.10.md](docs/releases/0.10.md).

Materiały prezentacyjne wydania: [PDF raportu](docs/GameCAT_1.0_raport_zaliczeniowy.pdf) i [PowerPoint do obrony](docs/GameCAT_1.0_obrona.pptx).
