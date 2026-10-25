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
    assert 'placeholder-missing' in codes(issues)


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


def test_reports_missing_and_extra_tokens_separately():
    issues = validate_segment('Take {amount} gold and %s.', 'Weź {wrong} złota i %s.')
    issue_codes = [issue.code for issue in issues]
    assert 'placeholder-missing' in issue_codes
    assert 'placeholder-extra' in issue_codes
    assert any('{amount}' in issue.message for issue in issues if issue.code == 'placeholder-missing')
    assert any('{wrong}' in issue.message for issue in issues if issue.code == 'placeholder-extra')


def test_preserves_game_localization_tokens_and_printf_positions():
    source = '{g|king|queen} {d|hero} {mf|his|her} %1$s <b>text</b>'
    target = '{g|król|królowa} {d|bohater} {mf|jego|jej} %1$s <b>tekst</b>'
    # Game tokens are control structures whose complete token text may legitimately differ
    # in translated alternatives, but their token type/count must be preserved.
    issue_codes = codes(validate_segment(source, target))
    assert 'placeholder-missing' not in issue_codes
    assert 'placeholder-extra' not in issue_codes
