from pathlib import Path
from gamecat.importers.base import ImportedSegment


def import_txt(path: Path) -> list[ImportedSegment]:
    """Wersja 0.0.1: wczytywanie całego pliku, przed generatorami."""
    lines = path.read_text(encoding='utf-8').splitlines()
    return [ImportedSegment(position, line) for position, line in enumerate(lines, 1)]
