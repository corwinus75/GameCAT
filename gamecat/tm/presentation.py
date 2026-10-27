"""Text formatting for contextual TM suggestions (independent of Qt)."""
from __future__ import annotations

from gamecat.tm.matcher import TMMatch


def display_tm_match(match: TMMatch) -> tuple[str, str]:
    """Return (list label, tooltip) without treating TM IDs as segment IDs.

    A TM pair may be shared by multiple project segments. Show up to three
    references in the row and all of them in the tooltip. External entries may
    have no corresponding segment in the currently opened project.
    """
    refs = match.segment_references
    ref_labels = [f'{ref.id} (poz. {ref.position})' for ref in refs]
    if refs:
        visible = ', '.join(ref_labels[:3])
        if len(ref_labels) > 3:
            visible += f' (+{len(ref_labels) - 3}; wszystkie w podpowiedzi)'
        reference_label = f'ID seg.: {visible}'
        all_references = 'ID segmentów projektu: ' + ', '.join(ref_labels)
    else:
        reference_label = 'brak ID segmentu w tym projekcie'
        all_references = 'Brak segmentu o tej samej parze Source/Target w aktywnym projekcie.'
    tm_id = str(match.entry.id) if match.entry.id is not None else '—'
    score = f'{match.score:.0%}'  # The similarity is always genuine: never show 101%.
    current_label = 'BIEŻĄCY · ' if match.is_current_segment else ''
    label = f'{current_label}{score} · {reference_label} · {match.entry.source} → {match.entry.target}'
    tooltip = f'{current_label}{score}\n{all_references}\nTM ID: {tm_id}\nSource: {match.entry.source}\nTarget: {match.entry.target}'
    if not refs:
        # Keep the TM row ID visible even when the origin segment is unknown.
        label = f'{current_label}{score} · {reference_label} · TM ID: {tm_id} · {match.entry.source} → {match.entry.target}'
    return label, tooltip
