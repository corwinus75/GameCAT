from dataclasses import dataclass


@dataclass(slots=True)
class GlossaryEntry:
    """Required terminology mapping."""
    source_term: str
    target_term: str
    description: str = ""
    case_sensitive: bool = False
    id: int | None = None
    project_id: int | None = None
