import json
from collections.abc import Iterable
from pathlib import Path
from gamecat.models.segment import Segment


def export_json(segments: Iterable[Segment], path: Path, shape: str = 'list') -> None:
    ordered = sorted(segments, key=lambda s: s.position)
    if shape == 'dict':
        data = {(s.key if s.key is not None else str(s.position)): s.target for s in ordered}
    elif shape == 'list':
        data = [{'key': s.key, 'source': s.source, 'target': s.target, 'status': s.status.value, 'position': s.position} for s in ordered]
    else:
        raise ValueError(f'Unsupported JSON shape: {shape}')
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
