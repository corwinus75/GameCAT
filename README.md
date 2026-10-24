# GameCAT — wersja 0.0.10


Nowość tej wersji: **Procesy / ProcessPoolExecutor** — find_matches_parallel — procesowy matcher TM.
Kod dodany w: `gamecat/tm/parallel_matcher.py`.



## Uruchomienie

- Python >=3.12.
- Do interfejsu CLI: brak zewnętrznych zależności (w etapach bez GUI).
- Dla GUI od 0.0.12: `pip install -r requirements.txt`.
- Wywołanie pomocy: `python -m gamecat.cli --help`.

`python -m gamecat.cli --db demo.sqlite new Demo`

`python -m gamecat.cli --db demo.sqlite import 1 sample_data/sample.txt`

`python -m gamecat.cli --db demo.sqlite list 1`

`python -m gamecat.cli --db demo.sqlite translate 1 1 "Witaj!"`

`python -m gamecat.cli --db demo.sqlite export 1 tlumaczenie.txt`

- CSV/JSON:

`python -m gamecat.cli --db demo.sqlite import 1 sample_data/sample.csv`

`python -m gamecat.cli --db demo.sqlite export 1 wynik.json`

- QA:  oraz słownik:

`python -m gamecat.cli --db demo.sqlite qa 1 1`

`python -m gamecat.cli --db demo.sqlite glossary-add 1 quest zadanie`

- TM: 

`python -m gamecat.cli --db demo.sqlite tm-add 1 "Hello" "Cześć"`

`python -m gamecat.cli --db demo.sqlite tm-search 1 "Hello"`.

## Mapowanie wymagań i kolejnych etapów

| Etap | Wymaganie | Wdrożone | Główne miejsce |
|---:|---|:---:|---|
| 1 | Dekorator funkcji | TAK | gamecat/utils/decorators.py |
| 2 | Dekorator z parametrami | TAK | gamecat/utils/decorators.py |
| 3 | Dekorator metody z self | TAK | gamecat/services/project_service.py |
| 4 | @property i setter | TAK | gamecat/models/segment.py |
| 5 | Iterator | TAK | gamecat/utils/iterators.py |
| 6 | Generatory | TAK | gamecat/utils/generators.py |
| 7 | Regex z nazwanymi grupami | TAK | gamecat/qa/patterns.py |
| 8 | Wątki / ThreadPoolExecutor | TAK | gamecat/concurrency/io_workers.py |
| 9 | Queue / Lock | TAK | gamecat/concurrency/save_queue.py |
| 10 | Procesy / ProcessPoolExecutor | TAK | gamecat/tm/parallel_matcher.py |
| 11 | GIL | — | — |
| 12 | GUI / PySide6 | — | — |
| 13 | Testy | — | — |
| 14 | Logging | — | — |

## Sprawdzanie

`python smoke_check.py` — szybki test funkcjonalny tego etapu bez Qt.
Testy pytest zostaną dodane w etapie 0.0.13.

