# Historyczny benchmark 0.5.1 — Windows 11

Poniższe wartości pochodzą z pierwotnego wydania użytkownika 0.5.1. **Nie są pomiarem wykonanym w środowisku wydania 1.0.** Zachowano je, ponieważ pokazują wpływ wielkości danych i kosztu uruchamiania procesów.

| Tryb | Mediana [s] | Min [s] | Max [s] | Przyspieszenie |
|---|---:|---:|---:|---:|
| Sekwencyjnie | 3.759 | 3.701 | 3.909 | 1.00× |
| Wątki | 3.754 | 3.655 | 4.047 | 1.00× |
| Procesy | 1.796 | 1.745 | 1.942 | 2.09× |

Konfiguracja: 600 segmentów, 1200 wpisów TM, 22 workerów, 5 powtórzeń, seed 2026. CPython 3.14.0, Windows 11, 22 logiczne CPU, GIL włączony. Wyniki dotyczą funkcji analizy TM i obejmują koszt startu procesów. Nie wolno ich traktować jako gwarantowanego przyspieszenia na innym komputerze.
