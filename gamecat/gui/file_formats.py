from __future__ import annotations

from pathlib import Path

SUPPORTED_FORMATS = {'txt', 'csv', 'json', 'tsv', 'xlsx', 'xml'}


def export_format_from_path(path: Path) -> str:
    """Return a supported export format derived from *path* suffix."""
    format_name = path.suffix.removeprefix('.').casefold()
    if format_name not in SUPPORTED_FORMATS:
        raise ValueError(f'Unsupported export format: {path.suffix or "<none>"}')
    return format_name


def normalized_export_path(path: Path, selected_format: str) -> Path:
    """Append the selected extension only when the user omitted one."""
    selected = selected_format.casefold()
    if selected not in SUPPORTED_FORMATS:
        raise ValueError(f'Unsupported export format: {selected_format}')
    if path.suffix:
        return path
    return path.with_suffix(f'.{selected}')
