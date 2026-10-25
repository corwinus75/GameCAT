# GameCAT — raport projektu zaliczeniowego

## 1. Cel

GameCAT jest aplikacją CAT wspomagającą lokalizację gier. Projekt łączy realny scenariusz pracy tłumacza z wymaganiami przedmiotu „Zaawansowane techniki programowania w języku Python”.

## 2. Architektura

Kod podzielono na modele domenowe, bazę SQLite, import/eksport, QA, Translation Memory, współbieżność, usługi aplikacyjne oraz GUI PySide6. Dzięki temu ciężkie operacje i baza danych nie są trwale sprzężone z widgetami.

## 3. Zaawansowane elementy Pythona

Projekt wykorzystuje własne dekoratory funkcji i metod, `@property`, własny iterator, generatory, wyrażenia generujące, regex z grupami nazwanymi, `ThreadPoolExecutor`, `Queue`, `Lock` i `ProcessPoolExecutor`. Benchmark w katalogu `benchmarks/` ilustruje wpływ GIL na zadanie CPU-bound.

## 4. Testowanie

Testy jednostkowe i integracyjne znajdują się w `tests/`. Obejmują modele, SQLite, import/eksport, QA, glosariusz, TM, współbieżność oraz pełny workflow projektu. Testy PySide6 są uruchamiane tylko wtedy, gdy biblioteka jest dostępna.

## 5. Uruchomienie

1. Python 3.12+.
2. `pip install -r requirements.txt`.
3. `python main.py`.
4. Testy: `pytest -v`.
5. Benchmark: `python benchmarks/gil_benchmark.py`.
