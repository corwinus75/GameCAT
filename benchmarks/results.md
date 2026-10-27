# Wyniki benchmarku GIL

| Tryb | Mediana [s] | Min [s] | Max [s] | Przyspieszenie |
|---|---:|---:|---:|---:|
| Sekwencyjnie | 6.999 | 6.825 | 7.199 | 1.00x |
| Wątki | 6.958 | 6.889 | 7.115 | 1.01x |
| Procesy | 2.317 | 2.277 | 2.490 | 3.02x |

Dane: 800 segmentów × 1600 wpisów TM, 22 workerów, 5 powtórzeń (mediana), seed 2026.  
Środowisko: Python 3.14.0 (CPython), Windows 11, 22 rdzeni logicznych, GIL włączony.
