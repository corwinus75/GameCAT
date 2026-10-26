from dataclasses import dataclass
from collections import Counter
from collections.abc import Iterable

from gamecat.models.glossary import GlossaryEntry, GlossaryTerm
from gamecat.qa.patterns import QAToken, extract_tokens
from gamecat.glossary.matching import contains_term


@dataclass(frozen=True, slots=True)
class QAIssue:
    code: str
    message: str


def _token_signature(token: QAToken) -> str:
    """Return the invariant part of a localization token for QA comparison."""
    if token.kind == 'brace':
        for prefix in ('{g|', '{d|', '{mf|'):
            if token.value.startswith(prefix):
                return prefix
    return token.value


def _display_token(signature: str) -> str:
    if signature in {'{g|', '{d|', '{mf|'}:
        return f'{signature}…}}'
    return signature


def _token_counter(text: str) -> Counter[str]:
    return Counter(_token_signature(token) for token in extract_tokens(text))


def run_rules(source: str, target: str, glossary: Iterable[GlossaryTerm | GlossaryEntry] = ()) -> list[QAIssue]:
    issues: list[QAIssue] = []
    source_tokens = _token_counter(source)
    target_tokens = _token_counter(target)

    for token, count in (source_tokens - target_tokens).items():
        suffix = f' (x{count})' if count > 1 else ''
        issues.append(QAIssue('placeholder-missing', f'Brak placeholdera lub tagu: {_display_token(token)}{suffix}'))
    for token, count in (target_tokens - source_tokens).items():
        suffix = f' (x{count})' if count > 1 else ''
        issues.append(QAIssue('placeholder-extra', f'Dodatkowy placeholder lub tag: {_display_token(token)}{suffix}'))

    if target == '':
        issues.append(QAIssue('empty-target', 'Tłumaczenie jest puste.'))
    if source and source == target:
        issues.append(QAIssue('source-equals-target', 'Source i Target są identyczne.'))
    if source.count('\n') != target.count('\n'):
        issues.append(QAIssue('newline-mismatch', 'Liczba znaków nowej linii różni się od Source.'))
    if target and target != target.strip():
        issues.append(QAIssue('edge-whitespace', 'Tłumaczenie ma spację na początku lub końcu.'))
    if '  ' in target:
        issues.append(QAIssue('double-space', 'Tłumaczenie zawiera podwójne spacje.'))

    for entry in glossary:
        if not contains_term(source, entry.source_term, case_sensitive=entry.case_sensitive):
            continue
        targets = entry.targets if isinstance(entry, GlossaryTerm) else [entry.target_term]
        if not any(contains_term(target, variant, case_sensitive=entry.case_sensitive) for variant in targets):
            allowed = ', '.join(targets)
            issues.append(
                QAIssue('glossary-term', f'Brak wymaganego terminu: {entry.source_term}. Dozwolone: {allowed}')
            )
    return issues
