# GameCAT

GameCAT to desktopowy program CAT (Computer-Assisted Translation) do lokalizacji gier, przygotowany jako projekt zaliczeniowy z przedmiotu **Zaawansowane techniki programowania w języku Python**.

## Funkcje wersji 0.10.0

- projekty tłumaczeniowe i segmenty Source/Target,
- wyszukiwanie Source/Target z regex i sortowaniem, filtry QA/TM, podgląd masowej zamiany Target oraz nawigacja do braków/QA,
- SQLite,
- import i eksport TXT/CSV/JSON,
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

Instalacja:

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
pip3 install -r requirements.txt
python main.py
```

Testy:

```bash
pytest -v
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
| Eksport/import TM 0.8 | `gamecat/tm/exchange.py`, `ProjectService.import_tm_file` | transakcyjny import TM, eksport CSV/JSON |
| Testy | `tests/` (pytest) | |
| Logging | `gamecat/logging_config.py` | plik `gamecat.log` |

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
| Sekwencyjnie | 3.759 | 3.701 | 3.909 | 1.00x |
| Wątki | 3.754 | 3.655 | 4.047 | 1.00x |
| Procesy | 1.796 | 1.745 | 1.942 | 2.09x |

Dane: 600 segmentów × 1200 wpisów TM, 22 workerów, 5 powtórzeń (mediana), seed 2026.  
Środowisko: Python 3.14.0 (CPython), Windows 11, 22 rdzeni logicznych, GIL włączony.

![Wykres benchmarku](benchmarks/gil_benchmark.png)
<!-- BENCHMARK:END -->

## Wnioski z benchmarku GIL

Benchmark mierzy rzeczywistą operację programu – analizę projektu względem TM – w trzech trybach, z przebiegiem rozgrzewkowym, rotowaną kolejnością trybów i medianą z kilku powtórzeń. Fuzzy matching w `gamecat/tm/similarity.py` to obliczenia w czystym Pythonie (tokenizacja, operacje na zbiorach), czyli zadanie CPU-bound. W standardowym CPythonie GIL pozwala w danej chwili wykonywać kod bajtowy tylko jednemu wątkowi, dlatego pula wątków nie skraca czasu analizy – wątki jedynie na zmianę korzystają z jednego „kanału” wykonania, a ich koszt przełączania może wynik minimalnie pogorszyć. Pula procesów uruchamia osobne interpretery z własnym GIL, więc obliczenia rozkładają się na rdzenie CPU. Przyspieszenie procesów jest mniejsze niż liczba rdzeni, ponieważ w czasie pomiaru mieści się start procesów, przekazanie TM do workerów i serializacja wyników (pickle). W tym pomiarze wątki osiągnęły 1.00x względem wykonania sekwencyjnego, a procesy 2.09x na maszynie z 22 rdzeniami logicznymi. Z tego powodu GameCAT używa procesów do analizy TM, a wątków do zadań I/O – importu, eksportu i autosave – gdzie wątek czeka na dysk, a GIL jest wtedy zwalniany. Dla małych projektów analiza jest wykonywana sekwencyjnie, bo narzut uruchomienia puli przewyższa zysk. Na kompilacji free-threading (Python 3.13t/3.14t) ten sam kod w trybie wątków mógłby skalować się podobnie do procesów, bez kosztu serializacji – to możliwe rozszerzenie pomiarów.

## Problemy napotkane podczas realizacji

> Szkic do weryfikacji i przepisania własnymi słowami.

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
