# Wyniki benchmarku GIL

| Tryb | Mediana [s] | Min [s] | Max [s] | Przyspieszenie |
|---|---:|---:|---:|---:|
| Sekwencyjnie | 3.794 | 3.753 | 3.872 | 1.00x |
| Wątki | 3.707 | 3.641 | 3.867 | 1.02x |
| Procesy | 2.254 | 2.090 | 2.380 | 1.68x |

Dane: 600 segmentów × 1200 wpisów TM, 22 workerów, 5 powtórzeń (mediana), seed 2026.  
Środowisko: Python 3.14.0 (CPython), Windows 11, 22 rdzeni logicznych, GIL włączony.
