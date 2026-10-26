# Wyniki benchmarku GIL

| Tryb | Mediana [s] | Min [s] | Max [s] | Przyspieszenie |
|---|---:|---:|---:|---:|
| Sekwencyjnie | 4.506 | 3.930 | 5.346 | 1.00x |
| Wątki | 4.463 | 4.015 | 4.960 | 1.01x |
| Procesy | 3.092 | 2.990 | 3.846 | 1.46x |

Dane: 600 segmentów × 1200 wpisów TM, 22 workerów, 5 powtórzeń (mediana), seed 2026.  
Środowisko: Python 3.14.0 (CPython), Windows 11, 22 rdzeni logicznych, GIL włączony.
