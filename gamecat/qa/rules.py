from dataclasses import dataclass
from collections import Counter
from collections.abc import Iterable
from gamecat.models.glossary import GlossaryEntry
from gamecat.qa.patterns import extract_tokens

@dataclass(frozen=True, slots=True)
class QAIssue:
    code: str
    message: str


def run_rules(source: str, target: str, glossary: Iterable[GlossaryEntry] = ()) -> list[QAIssue]:
    issues: list[QAIssue] = []
    source_tokens = Counter(t.value for t in extract_tokens(source))
    target_tokens = Counter(t.value for t in extract_tokens(target))
    if source_tokens != target_tokens:
        issues.append(QAIssue('placeholder-mismatch', 'Placeholder or tag set differs from source.'))
    if target == '':
        issues.append(QAIssue('empty-target', 'Translation is empty.'))
    if source and source == target:
        issues.append(QAIssue('source-equals-target', 'Source and target are identical.'))
    if source.count('\n') != target.count('\n'):
        issues.append(QAIssue('newline-mismatch', 'Newline count differs from source.'))
    if target and target != target.strip():
        issues.append(QAIssue('edge-whitespace', 'Translation has leading or trailing whitespace.'))
    if '  ' in target:
        issues.append(QAIssue('double-space', 'Translation contains repeated spaces.'))
    for entry in glossary:
        src = source if entry.case_sensitive else source.casefold()
        needle = entry.source_term if entry.case_sensitive else entry.source_term.casefold()
        if needle in src:
            tgt = target if entry.case_sensitive else target.casefold()
            required = entry.target_term if entry.case_sensitive else entry.target_term.casefold()
            if required not in tgt:
                issues.append(QAIssue('glossary-term', f'Required glossary term missing: {entry.target_term}'))
    return issues
