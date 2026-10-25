from gamecat.models.glossary import GlossaryEntry
from gamecat.qa.patterns import extract_tokens
from gamecat.qa.validator import validate_segment


def codes(issues): return {i.code for i in issues}


def test_extracts_placeholders_tags_and_game_tokens():
    text = '{name} %s %d %1$s <b>x</b> {g|foo} {d|bar} {mf|his|her}'
    values = [t.value for t in extract_tokens(text)]
    for expected in ['{name}','%s','%d','%1$s','<b>','</b>','{g|foo}','{d|bar}','{mf|his|her}']:
        assert expected in values


def test_placeholder_mismatch():
    issues = validate_segment('Take {amount} gold.', 'Weź złoto.')
    assert 'placeholder-mismatch' in codes(issues)


def test_basic_qa_rules():
    assert 'empty-target' in codes(validate_segment('Hello', ''))
    assert 'source-equals-target' in codes(validate_segment('Hello', 'Hello'))
    assert 'newline-mismatch' in codes(validate_segment('A\nB', 'AB'))
    assert 'edge-whitespace' in codes(validate_segment('Hello', ' Hej'))
    assert 'double-space' in codes(validate_segment('Hello', 'Hej  tam'))


def test_glossary_required_term():
    glossary=[GlossaryEntry('quest','zadanie')]
    assert 'glossary-term' in codes(validate_segment('Complete the quest.', 'Ukończ misję.', glossary))
    assert 'glossary-term' not in codes(validate_segment('Complete the quest.', 'Ukończ zadanie.', glossary))
