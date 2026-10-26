from collections.abc import Iterable
from gamecat.models.glossary import GlossaryEntry, GlossaryTerm
from gamecat.qa.rules import QAIssue, run_rules


def validate_segment(source: str, target: str, glossary: Iterable[GlossaryTerm | GlossaryEntry] = ()) -> list[QAIssue]:
    """Validate one bilingual segment against all MVP QA rules."""
    return run_rules(source, target, glossary)
