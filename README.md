# GameCAT — wersja 0.0.1

Wersja 0.0.1 jest pierwszą wersją aplikacji GameCAT. Wersja ta zawiera podstawowe funkcje importu, listowania, tłumaczenia i eksportu danych w formacie tekstowym.
Wymagania wdrożone w tej wersji: **Dekorator funkcji** — @measure_time — mierzenie importu danych.
Kod dodany w: `gamecat/utils/decorators.py`.


## Uruchomienie

- Python >=3.12.
- Do interfejsu CLI: brak zewnętrznych zależności (w etapach bez GUI).
- Dla GUI od 0.0.12: `pip install -r requirements.txt`.
- Wywołanie pomocy: `python -m gamecat.cli --help`.


## Przygotowanie środowiska wirtualnego i instalacja zależności:
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

```bash
python -m gamecat.cli --db demo.sqlite new Demo
python -m gamecat.cli --db demo.sqlite import 1 sample_data/sample.txt
python -m gamecat.cli --db demo.sqlite list 1
python -m gamecat.cli --db demo.sqlite translate 1 1 "Witaj!"
python -m gamecat.cli --db demo.sqlite export 1 tlumaczenie.txt
```



## Mapowanie wymagań i kolejnych etapów

| Etap | Wymaganie | Wdrożone | Główne miejsce |
|---:|---|:---:|---|
| 1 | Dekorator funkcji | TAK | gamecat/utils/decorators.py |
| 2 | Dekorator z parametrami | — | — |
| 3 | Dekorator metody z self | — | — |
| 4 | @property i setter | — | — |
| 5 | Iterator | — | — |
| 6 | Generatory | — | — |
| 7 | Regex z nazwanymi grupami | — | — |
| 8 | Wątki / ThreadPoolExecutor | — | — |
| 9 | Queue / Lock | — | — |
| 10 | Procesy / ProcessPoolExecutor | — | — |
| 11 | GIL | — | — |
| 12 | GUI / PySide6 | — | — |
| 13 | Testy | — | — |
| 14 | Logging | — | — |

## Sprawdzanie

`python smoke_check.py` — szybki test funkcjonalny tego etapu bez Qt.
Testy pytest zostaną dodane w etapie/wersji 0.0.13.


