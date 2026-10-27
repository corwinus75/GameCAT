"""Pomiar czasów filtrowania wyszukiwarki segmentów (bez renderowania Qt)."""
from __future__ import annotations

import argparse
from time import perf_counter

from gamecat.models.segment import Segment
from gamecat.search.index import SegmentSearchIndex
from gamecat.search.operations import SearchQuery, filter_segments


def main() -> None:
    """Punkt wejścia CLI: wygeneruj segmenty i zmierz czasy filtrowania indeksu."""
    parser = argparse.ArgumentParser()
    parser.add_argument('--segments', type=int, default=50000)
    args = parser.parse_args()
    rows = [Segment(f'Dialogue text for line {i}', i, target=f'Tłumaczenie {i}', id=i)
            for i in range(args.segments)]
    rows[-1].source = 'The unique magical gate'
    needle = SearchQuery('unique magical')
    start = perf_counter()
    index = SegmentSearchIndex(rows)
    prepare_time = perf_counter() - start
    start = perf_counter()
    previous = filter_segments(rows, needle)
    legacy_time = perf_counter() - start
    start = perf_counter()
    matches = index.search(needle)
    indexed_time = perf_counter() - start
    assert [rows[i].id for i in matches] == [segment.id for segment in previous]
    print(f'Rows: {len(rows):,}; matches: {len(matches)}')
    print(f'Index preparation (once/project load): {prepare_time:.4f} s')
    print(f'Legacy synchronous Python filter/sort: {legacy_time:.4f} s')
    print(f'New indexed Python filter/sort:     {indexed_time:.4f} s')
    print('Qt list painting and event-loop latency not included; requires a GUI benchmark.')


if __name__ == '__main__':
    main()
