from gamecat.glossary.spans import term_spans
from gamecat.models.glossary import GlossaryTerm


def test_glossary_spans_match_whole_phrases_and_prefer_longest():
    terms = [GlossaryTerm('sword',['miecz']), GlossaryTerm('long sword',['długi miecz']),
             GlossaryTerm('C++',['C plus plus'])]
    text = 'The long sword, swordsmanship and C++ are here. Sword!'
    spans = term_spans(text, terms)
    assert [(text[a:b], term.targets) for a,b,term in spans] == [
        ('long sword', ['długi miecz']), ('C++',['C plus plus']), ('Sword',['miecz'])]


def test_span_case_sensitive():
    terms = [GlossaryTerm('King',['Król'],case_sensitive=True)]
    text = 'king King'
    assert [(a,b) for a,b,_ in term_spans(text,terms)] == [(5,9)]
