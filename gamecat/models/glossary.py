from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class GlossaryEntry:
    """Legacy flat glossary row kept for 0.6 compatibility during migration."""

    source_term: str
    target_term: str
    description: str = ""
    case_sensitive: bool = False
    id: int | None = None
    project_id: int | None = None


@dataclass(slots=True)
class GlossaryTerm:
    """Project glossary term with one or more equivalent target variants."""

    source_term: str
    targets: list[str] = field(default_factory=list)
    description: str = ""
    case_sensitive: bool = False
    id: int | None = None
    project_id: int | None = None

    def __post_init__(self) -> None:
        self.source_term = self.source_term.strip()
        self.description = self.description.strip()
        if not self.source_term:
            raise ValueError("source term cannot be blank")

        normalized: list[str] = []
        seen: set[str] = set()
        for target in self.targets:
            value = target.strip()
            if not value:
                raise ValueError("target variant cannot be blank")
            if value not in seen:
                normalized.append(value)
                seen.add(value)
        if not normalized:
            raise ValueError("glossary term requires at least one target variant")
        self.targets = normalized
