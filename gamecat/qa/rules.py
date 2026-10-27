"""Reguły kontroli jakości (QA) dla pojedynczego segmentu.

Każda grupa reguł jest generatorem zgłaszającym problemy (``QAIssue``),
a :func:`iter_issues` łączy je w jeden strumień przez ``yield from``.
Dodanie nowej grupy reguł sprowadza się do dopisania kolejnego generatora.
"""
from dataclasses import dataclass
from collections import Counter
from collections.abc import Iterable, Iterator

from gamecat.models.glossary import GlossaryEntry, GlossaryTerm
from gamecat.qa.patterns import QAToken, extract_tokens
from gamecat.glossary.matching import contains_term

GlossaryItems = Iterable[GlossaryTerm | GlossaryEntry]


@dataclass(frozen=True, slots=True)
class QAIssue:
    """Pojedynczy problem QA: stały kod reguły i komunikat dla użytkownika."""
    code: str
    message: str


def _token_signature(token: QAToken) -> str:
    """Zwróć niezmienną część tokenu lokalizacyjnego używaną do porównania Source/Target.

    Dla tokenów ``{g|…}``, ``{d|…}`` i ``{mf|…}`` liczy się tylko prefiks,
    bo ich zawartość jest tłumaczona.
    """
    if token.kind == 'brace':
        for prefix in ('{g|', '{d|', '{mf|'):
            if token.value.startswith(prefix):
                return prefix
    return token.value


def _display_token(signature: str) -> str:
    """Zwróć czytelną postać sygnatury tokenu do komunikatu QA."""
    if signature in {'{g|', '{d|', '{mf|'}:
        return f'{signature}…}}'
    return signature


def _token_counter(text: str) -> Counter[str]:
    """Policz wystąpienia sygnatur placeholderów i tagów w tekście."""
    return Counter(_token_signature(token) for token in extract_tokens(text))


def _placeholder_issues(source: str, target: str) -> Iterator[QAIssue]:
    """Generuj problemy z brakującymi i nadmiarowymi placeholderami oraz tagami."""
    source_tokens = _token_counter(source)
    target_tokens = _token_counter(target)
    for token, count in (source_tokens - target_tokens).items():
        suffix = f' (x{count})' if count > 1 else ''
        yield QAIssue('placeholder-missing', f'Brak placeholdera lub tagu: {_display_token(token)}{suffix}')
    for token, count in (target_tokens - source_tokens).items():
        suffix = f' (x{count})' if count > 1 else ''
        yield QAIssue('placeholder-extra', f'Dodatkowy placeholder lub tag: {_display_token(token)}{suffix}')


def _text_issues(source: str, target: str) -> Iterator[QAIssue]:
    """Generuj problemy z treścią: puste tłumaczenie, kopia Source, nowe linie i spacje."""
    if target == '':
        yield QAIssue('empty-target', 'Tłumaczenie jest puste.')
    if source and source == target:
        yield QAIssue('source-equals-target', 'Source i Target są identyczne.')
    if source.count('\n') != target.count('\n'):
        yield QAIssue('newline-mismatch', 'Liczba znaków nowej linii różni się od Source.')
    if target and target != target.strip():
        yield QAIssue('edge-whitespace', 'Tłumaczenie ma spację na początku lub końcu.')
    if '  ' in target:
        yield QAIssue('double-space', 'Tłumaczenie zawiera podwójne spacje.')


def _glossary_issues(source: str, target: str, glossary: GlossaryItems) -> Iterator[QAIssue]:
    """Generuj problemy z terminologią: termin z Source bez dozwolonego wariantu w Target."""
    for entry in glossary:
        if not contains_term(source, entry.source_term, case_sensitive=entry.case_sensitive):
            continue
        targets = entry.targets if isinstance(entry, GlossaryTerm) else [entry.target_term]
        if not any(contains_term(target, variant, case_sensitive=entry.case_sensitive) for variant in targets):
            allowed = ', '.join(targets)
            yield QAIssue('glossary-term', f'Brak wymaganego terminu: {entry.source_term}. Dozwolone: {allowed}')


def iter_issues(source: str, target: str, glossary: GlossaryItems = ()) -> Iterator[QAIssue]:
    """Generuj leniwie wszystkie problemy QA segmentu, delegując do grup reguł przez ``yield from``.

    Kolejność zgłoszeń: placeholdery i tagi, treść, terminologia.
    """
    yield from _placeholder_issues(source, target)
    yield from _text_issues(source, target)
    yield from _glossary_issues(source, target, glossary)


def run_rules(source: str, target: str, glossary: GlossaryItems = ()) -> list[QAIssue]:
    """Uruchom wszystkie reguły QA dla segmentu i zwróć listę problemów."""
    return list(iter_issues(source, target, glossary))
