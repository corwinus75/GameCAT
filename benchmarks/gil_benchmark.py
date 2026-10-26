"""Benchmark GIL na rzeczywistej operacji GameCAT: analizie projektu względem TM.

Ta sama funkcja ``gamecat.tm.analysis.analyze`` jest uruchamiana w trzech
trybach: sekwencyjnie, w puli wątków i w puli procesów. Procedura:

* przebieg rozgrzewkowy każdego trybu (nie jest liczony),
* *repeats* rund pomiarowych; kolejność trybów jest rotowana w każdej rundzie,
  żeby żaden tryb nie był systematycznie mierzony jako pierwszy,
* raportowana jest mediana (odporna na pojedyncze zakłócenia), min i max,
* czas obejmuje start puli – tyle samo kosztuje to użytkownika w programie,
* przed pomiarem sprawdzana jest zgodność wyników wszystkich trybów.

Uruchomienie::

    python benchmarks/gil_benchmark.py                 # pełny pomiar + wykres
    python benchmarks/gil_benchmark.py --update-readme  # dodatkowo tabela w README
    python benchmarks/gil_benchmark.py --quick         # szybki test działania
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import sys
import sysconfig
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from benchmarks.dataset import generate_dataset  # noqa: E402
from gamecat.tm.analysis import ExecutionMode, analyze  # noqa: E402

README_START = '<!-- BENCHMARK:START -->'
README_END = '<!-- BENCHMARK:END -->'
MODE_LABELS = {
    ExecutionMode.SEQUENTIAL: 'Sekwencyjnie',
    ExecutionMode.THREADS: 'Wątki',
    ExecutionMode.PROCESSES: 'Procesy',
}


@dataclass(slots=True)
class ModeResult:
    mode: str
    times: list[float]

    @property
    def median(self) -> float:
        return statistics.median(self.times)


def environment() -> dict[str, object]:
    """Opis środowiska – bez niego wyników nie da się porównać ani powtórzyć."""
    gil_enabled = sys._is_gil_enabled() if hasattr(sys, '_is_gil_enabled') else True
    return {
        'python': platform.python_version(),
        'implementation': platform.python_implementation(),
        'system': f'{platform.system()} {platform.release()}',
        'processor': platform.processor() or platform.machine(),
        'cpu_count': os.cpu_count(),
        'free_threading_build': bool(sysconfig.get_config_var('Py_GIL_DISABLED')),
        'gil_enabled': gil_enabled,
        'switch_interval_s': sys.getswitchinterval(),
    }


def run_once(segments, tm, mode: ExecutionMode, workers: int):
    start = time.perf_counter()
    report = analyze(segments, tm, mode=mode, workers=workers)
    return time.perf_counter() - start, report


def run_benchmark(n_segments: int, n_tm: int, repeats: int, workers: int, seed: int,
                  log=print) -> dict[str, object]:
    segments, tm = generate_dataset(n_segments, n_tm, seed)
    modes = list(ExecutionMode)

    log(f'Dane: {n_segments} segmentów x {n_tm} wpisów TM, workerów: {workers}, powtórzeń: {repeats}')
    log('Rozgrzewka i kontrola zgodności wyników...')
    reference = None
    for mode in modes:
        _, report = run_once(segments, tm, mode, workers)
        if reference is None:
            reference = report.matches
        elif report.matches != reference:
            raise RuntimeError(f'Tryb {mode} zwrócił inne wyniki niż sekwencyjny')

    results = {mode: ModeResult(mode.value, []) for mode in modes}
    for round_no in range(repeats):
        order = modes[round_no % len(modes):] + modes[:round_no % len(modes)]
        for mode in order:
            elapsed, _ = run_once(segments, tm, mode, workers)
            results[mode].times.append(elapsed)
        log(f'  runda {round_no + 1}/{repeats}: ' + ', '.join(
            f'{m.value}={results[m].times[-1]:.3f}s' for m in modes))

    baseline = results[ExecutionMode.SEQUENTIAL].median
    rows = []
    for mode in modes:
        r = results[mode]
        rows.append({
            'mode': mode.value,
            'label': MODE_LABELS[mode],
            'median_s': r.median,
            'min_s': min(r.times),
            'max_s': max(r.times),
            'speedup': baseline / r.median if r.median else float('nan'),
            'times_s': r.times,
        })
    return {
        'environment': environment(),
        'parameters': {'segments': n_segments, 'tm_entries': n_tm, 'repeats': repeats,
                       'workers': workers, 'seed': seed,
                       'similarity_calls_upper_bound': n_segments * n_tm},
        'results': rows,
    }


def markdown_table(data: dict[str, object]) -> str:
    env = data['environment']; params = data['parameters']
    lines = [
        '| Tryb | Mediana [s] | Min [s] | Max [s] | Przyspieszenie |',
        '|---|---:|---:|---:|---:|',
    ]
    for row in data['results']:
        lines.append(f"| {row['label']} | {row['median_s']:.3f} | {row['min_s']:.3f} | "
                     f"{row['max_s']:.3f} | {row['speedup']:.2f}x |")
    lines += [
        '',
        f"Dane: {params['segments']} segmentów × {params['tm_entries']} wpisów TM, "
        f"{params['workers']} workerów, {params['repeats']} powtórzeń (mediana), seed {params['seed']}.  ",
        f"Środowisko: Python {env['python']} ({env['implementation']}), {env['system']}, "
        f"{env['cpu_count']} rdzeni logicznych, GIL {'włączony' if env['gil_enabled'] else 'wyłączony'}"
        f"{', kompilacja free-threading' if env['free_threading_build'] else ''}.",
    ]
    return '\n'.join(lines)


def save_plot(data: dict[str, object], path: Path) -> None:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    rows = data['results']
    labels = [r['label'] for r in rows]
    medians = [r['median_s'] for r in rows]
    lower = [r['median_s'] - r['min_s'] for r in rows]
    upper = [r['max_s'] - r['median_s'] for r in rows]
    env = data['environment']; params = data['parameters']

    fig, ax = plt.subplots(figsize=(7, 4.2))
    bars = ax.bar(labels, medians, yerr=[lower, upper], capsize=6,
                  color=['#7f8c8d', '#e67e22', '#2e86c1'])
    for bar, row in zip(bars, rows):
        ax.annotate(f"{row['median_s']:.2f} s\n{row['speedup']:.2f}x",
                    (bar.get_x() + bar.get_width() / 2, row['max_s']),
                    xytext=(0, 4), textcoords='offset points', ha='center', va='bottom', fontsize=9)
    ax.set_ylabel('Czas analizy TM [s] (mediana, słupki: min–max)')
    ax.set_title(f"Analiza TM: {params['segments']} segm. × {params['tm_entries']} wpisów TM, "
                 f"{params['workers']} workerów\nPython {env['python']}, "
                 f"GIL {'on' if env['gil_enabled'] else 'off'}, {env['cpu_count']} CPU", fontsize=10)
    ax.set_ylim(0, max(r['max_s'] for r in rows) * 1.3)
    ax.grid(axis='y', alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def update_readme(readme: Path, table: str) -> bool:
    text = readme.read_text(encoding='utf-8')
    if README_START not in text or README_END not in text:
        return False
    head, rest = text.split(README_START, 1)
    _, tail = rest.split(README_END, 1)
    block = f'{README_START}\n{table}\n\n![Wykres benchmarku](benchmarks/gil_benchmark.png)\n{README_END}'
    readme.write_text(head + block + tail, encoding='utf-8')
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='Benchmark GIL: analiza TM sekwencyjnie / wątki / procesy.')
    parser.add_argument('--segments', type=int, default=600)
    parser.add_argument('--tm', type=int, default=1200, help='liczba wpisów TM')
    parser.add_argument('--repeats', type=int, default=5)
    parser.add_argument('--workers', type=int, default=os.cpu_count() or 1)
    parser.add_argument('--seed', type=int, default=2026)
    parser.add_argument('--quick', action='store_true', help='mały zestaw danych do sprawdzenia działania')
    parser.add_argument('--no-plot', action='store_true')
    parser.add_argument('--update-readme', action='store_true',
                        help='wstaw tabelę wyników do README.md między znacznikami BENCHMARK')
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'benchmarks')
    args = parser.parse_args(argv)
    if args.quick:
        args.segments, args.tm, args.repeats = 120, 240, 3

    data = run_benchmark(args.segments, args.tm, args.repeats, args.workers, args.seed)
    table = markdown_table(data)
    print()
    print(table)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / 'results.json').write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')
    (args.output_dir / 'results.md').write_text('# Wyniki benchmarku GIL\n\n' + table + '\n', encoding='utf-8')
    if not args.no_plot:
        save_plot(data, args.output_dir / 'gil_benchmark.png')
    if args.update_readme:
        if update_readme(ROOT / 'README.md', table):
            print('\nZaktualizowano tabelę w README.md')
        else:
            print('\nW README.md brak znaczników BENCHMARK – pominięto.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
