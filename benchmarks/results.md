# Wyniki benchmarku GIL

| Tryb | Mediana [s] | Min [s] | Max [s] | Przyspieszenie |
|---|---:|---:|---:|---:|
| Sekwencyjnie | 3.759 | 3.701 | 3.909 | 1.00x |
| Wątki | 3.754 | 3.655 | 4.047 | 1.00x |
| Procesy | 1.796 | 1.745 | 1.942 | 2.09x |

Dane: 600 segmentów × 1200 wpisów TM, 22 workerów, 5 powtórzeń (mediana), seed 2026.  
Środowisko: Python 3.14.0 (CPython), Windows 11, 22 rdzeni logicznych, GIL włączony.
