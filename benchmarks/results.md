# Wyniki benchmarku GIL

| Tryb | Mediana [s] | Min [s] | Max [s] | Przyspieszenie |
|---|---:|---:|---:|---:|
| Sekwencyjnie | 3.757 | 3.593 | 3.831 | 1.00x |
| Wątki | 3.675 | 3.604 | 3.758 | 1.02x |
| Procesy | 2.995 | 2.811 | 3.160 | 1.25x |

Dane: 600 segmentów × 1200 wpisów TM, 22 workerów, 5 powtórzeń (mediana), seed 2026.  
Środowisko: Python 3.14.0 (CPython), Windows 11, 22 rdzeni logicznych, GIL włączony.
