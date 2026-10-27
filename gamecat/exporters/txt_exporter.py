"""Eksport tłumaczeń do TXT."""
from collections.abc import Iterable
from pathlib import Path
from gamecat.models.segment import Segment


def export_txt(segments: Iterable[Segment], path: Path, *, ordered: bool = False) -> None:
    """Zapisz same tłumaczenia (Target), po jednym segmencie w linii."""
    with path.open('w', encoding='utf-8', newline='') as output:
        for segment in (segments if ordered else sorted(segments, key=lambda s: (s.position, s.id or 0))):
            output.write(segment.target + '\n')
