"""Punkt wejścia walidacji pojedynczego segmentu."""
from collections.abc import Iterable
from gamecat.models.glossary import GlossaryEntry, GlossaryTerm
from gamecat.qa.rules import QAIssue, run_rules


def validate_segment(source: str, target: str, glossary: Iterable[GlossaryTerm | GlossaryEntry] = ()) -> list[QAIssue]:
    """Sprawdź segment dwujęzyczny wszystkimi regułami QA i zwróć listę problemów."""
    return run_rules(source, target, glossary)
