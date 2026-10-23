from collections.abc import Iterable
from pathlib import Path
from gamecat.models.segment import Segment


def export_txt(segments: Iterable[Segment], path: Path) -> None:
    ordered = sorted(segments, key=lambda s: s.position)
    path.write_text(''.join(f'{s.target}\n' for s in ordered), encoding='utf-8')
