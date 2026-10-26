from gamecat.glossary.matching import contains_term


def test_matches_whole_word_but_not_substring():
    assert contains_term('Take the sword.', 'sword')
    assert not contains_term('The swordsman attacks.', 'sword')


def test_matches_whole_phrase():
    assert contains_term('A magic sword lies here.', 'magic sword')
    assert not contains_term('A magical sword lies here.', 'magic sword')


def test_case_sensitive_mode():
    assert contains_term('Gain XP now.', 'XP', case_sensitive=True)
    assert not contains_term('Gain xp now.', 'XP', case_sensitive=True)
    assert contains_term('Gain xp now.', 'XP', case_sensitive=False)


def test_regex_metacharacters_are_literal_and_boundaries_are_contextual():
    assert contains_term('Learn C++ today.', 'C++')
    assert contains_term("Use the king's sword.", "king's sword")
    assert contains_term('Found a +1 sword!', '+1 sword')
    assert not contains_term('Found a +1 swordsman!', '+1 sword')
