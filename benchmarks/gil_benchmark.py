from __future__ import annotations
import argparse
import sys
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gamecat.tm.similarity import similarity


def workload(pair: tuple[str, str, int]) -> float:
    source, candidate, repeats = pair
    score = 0.0
    for _ in range(repeats):
        score += similarity(source, candidate)
    return score


def run_benchmark(quick: bool = False) -> dict[str, float]:
    repeats = 2000 if quick else 12000
    tasks = [("The old stone gate is firmly closed before the traveler.",
              f"The ancient stone gate was closed before traveler number {i}.", repeats) for i in range(8)]
    results: dict[str, float] = {}
    start = time.perf_counter(); [workload(t) for t in tasks]; results['sequential'] = time.perf_counter() - start
    start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=4) as pool: list(pool.map(workload, tasks))
    results['threads'] = time.perf_counter() - start
    start = time.perf_counter()
    with ProcessPoolExecutor(max_workers=4) as pool: list(pool.map(workload, tasks))
    results['processes'] = time.perf_counter() - start
    return results


def main() -> int:
    parser=argparse.ArgumentParser(); parser.add_argument('--quick', action='store_true'); args=parser.parse_args()
    results=run_benchmark(args.quick)
    print('method,time_s')
    for name, elapsed in results.items(): print(f'{name},{elapsed:.6f}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
