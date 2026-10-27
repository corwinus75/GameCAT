from dataclasses import dataclass


@dataclass(slots=True)
class ImportedSegment:
    position: int
    source: str
    key: str | None = None
    target: str = ""
    comment: str = ""
