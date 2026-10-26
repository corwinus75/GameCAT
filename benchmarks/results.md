# Wyniki benchmarku GIL

| Tryb | Mediana [s] | Min [s] | Max [s] | Przyspieszenie |
|---|---:|---:|---:|---:|
| Sekwencyjnie | 0.260 | 0.237 | 0.269 | 1.00x |
| Wątki | 0.244 | 0.233 | 0.264 | 1.06x |
| Procesy | 1.152 | 1.139 | 1.223 | 0.23x |

Dane: 160 segmentów × 240 wpisów TM, 2 workerów, 3 powtórzeń (mediana), seed 2026.  
Środowisko: Python 3.13.5 (CPython), Linux 6.18.55, 5 rdzeni logicznych, GIL włączony.
