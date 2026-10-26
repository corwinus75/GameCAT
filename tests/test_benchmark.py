from pathlib import Path

from benchmarks.dataset import generate_dataset
from benchmarks.gil_benchmark import main, markdown_table, run_benchmark, update_readme


def test_dataset_is_deterministic_and_has_exact_matches():
    a = generate_dataset(50, 40, seed=1)
    b = generate_dataset(50, 40, seed=1)
    assert a == b
    segments, tm = a
    tm_sources = {s for s, _ in tm}
    assert len(segments) == 50 and len(tm) == 40
    assert any(source in tm_sources for _, source in segments)


def test_benchmark_runs_and_writes_outputs(tmp_path: Path):
    assert main(['--segments', '20', '--tm', '30', '--repeats', '1', '--workers', '2',
                 '--no-plot', '--output-dir', str(tmp_path)]) == 0
    assert (tmp_path / 'results.json').exists()
    assert '| Procesy |' in (tmp_path / 'results.md').read_text(encoding='utf-8')


def test_update_readme_replaces_only_marked_block(tmp_path: Path):
    data = run_benchmark(10, 10, 1, 1, 0, log=lambda *_: None)
    readme = tmp_path / 'README.md'
    readme.write_text('A\n<!-- BENCHMARK:START -->\nstare\n<!-- BENCHMARK:END -->\nB\n', encoding='utf-8')
    assert update_readme(readme, markdown_table(data))
    text = readme.read_text(encoding='utf-8')
    assert text.startswith('A\n') and text.endswith('B\n') and 'stare' not in text and 'Sekwencyjnie' in text
