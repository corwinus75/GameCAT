import os
import pytest
from gamecat.ai.credentials import CredentialStore, create_openai_translator

class FakeKeyring:
    def __init__(self): self.v = None
    def get_password(self, service, username): return self.v
    def set_password(self, service, username, value): self.v = value
    def delete_password(self, service, username): self.v = None


def test_api_key_lives_in_keyring_not_sqlite(monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    kr = FakeKeyring()
    store = CredentialStore(kr)
    store.save('sk-test-placeholder')
    assert store.get() == 'sk-test-placeholder'
    store.remove()
    assert store.get() is None


def test_environment_key_has_priority_over_keyring(monkeypatch):
    kr = FakeKeyring()
    kr.v = 'keyring-key'
    monkeypatch.setenv('OPENAI_API_KEY','env-key')
    assert CredentialStore(kr).get() == 'env-key'


def test_no_key_reports_clear_error(monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    with pytest.raises(ValueError, match='OPENAI_API_KEY'):
        create_openai_translator('', credential_store=CredentialStore(FakeKeyring()))
