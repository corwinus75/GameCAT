"""Eksport segmentów do JSON."""
import json
from collections.abc import Iterable
from pathlib import Path
from gamecat.models.segment import Segment


def export_json(segments: Iterable[Segment], path: Path, shape: str = 'list', *, ordered: bool = False) -> None:
    """Zapisz segmenty do JSON jako listę obiektów albo słownik ``klucz: Target``.

    Przy ``ordered=True`` dane są zapisywane przyrostowo (bez budowy całej
    struktury w pamięci) w kolejności z bazy; w przeciwnym razie segmenty
    są sortowane według pozycji.

    :raises ValueError: nieobsługiwany kształt JSON.
    """
    if shape not in {'dict', 'list'}:
        raise ValueError(f'Unsupported JSON shape: {shape}')
    items = segments if ordered else sorted(segments, key=lambda s: (s.position, s.id or 0))
    with path.open('w', encoding='utf-8') as fp:
        fp.write('[\n' if shape == 'list' else '{\n')
        first = True
        for segment in items:
            if not first:
                fp.write(',\n')
            first = False
            if shape == 'list':
                data = {'key': segment.key, 'source': segment.source, 'target': segment.target,
                        'status': segment.status.value, 'position': segment.position,
                        'comment': segment.comment}
                fp.write('  ' + json.dumps(data, ensure_ascii=False))
            else:
                key = segment.key if segment.key is not None else str(segment.position)
                fp.write('  ' + json.dumps(key, ensure_ascii=False) + ': ' +
                         json.dumps(segment.target, ensure_ascii=False))
        fp.write('\n]\n' if shape == 'list' else '\n}\n')
