import csv
from collections.abc import Iterable
from pathlib import Path
from gamecat.models.segment import Segment


def export_csv(segments: Iterable[Segment], path: Path) -> None:
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=['key','source','target','status','position'])
        writer.writeheader()
        for s in sorted(segments, key=lambda x: x.position):
            writer.writerow({'key': s.key or '', 'source': s.source, 'target': s.target, 'status': s.status.value, 'position': s.position})
