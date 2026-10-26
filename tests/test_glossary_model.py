import pytest

from gamecat.models.glossary import GlossaryTerm


def test_glossary_term_normalizes_and_rejects_blank_values():
    term = GlossaryTerm(' sword ', [' miecz ', 'ostrze', 'miecz'], ' Broń ', False)
    assert term.source_term == 'sword'
    assert term.targets == ['miecz', 'ostrze']
    assert term.description == 'Broń'

    with pytest.raises(ValueError):
        GlossaryTerm('   ', ['miecz'])
    with pytest.raises(ValueError):
        GlossaryTerm('sword', [])
    with pytest.raises(ValueError):
        GlossaryTerm('sword', [' '])
