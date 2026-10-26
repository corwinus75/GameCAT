"""Credentials are kept in OS keyring, transient memory or environment, NEVER project SQLite."""
from __future__ import annotations

import os
from typing import Any

from gamecat.ai.core import OpenAITranslator

_SERVICE = 'GameCAT OpenAI API'
_ACCOUNT = 'default'


class CredentialStore:
    def __init__(self, keyring_module: Any | None = None):
        self._keyring = keyring_module

    def _backend(self):
        if self._keyring is not None:
            return self._keyring
        try:
            import keyring
        except ImportError as exc:
            raise RuntimeError('Zainstaluj pakiet keyring do przechowywania klucza w systemie') from exc
        return keyring

    def get(self) -> str | None:
        if os.getenv('OPENAI_API_KEY', '').strip():
            return os.environ['OPENAI_API_KEY'].strip()
        try:
            return self._backend().get_password(_SERVICE, _ACCOUNT) or None
        except Exception:  # no secure backend: caller may supply session key
            return None

    def save(self, key: str) -> None:
        if not key.strip():
            raise ValueError('Klucz OpenAI API nie może być pusty')
        try:
            self._backend().set_password(_SERVICE, _ACCOUNT, key.strip())
        except Exception as exc:
            raise RuntimeError('Brak działającego systemowego magazynu poświadczeń. Użyj OPENAI_API_KEY.') from exc

    def remove(self) -> None:
        try:
            self._backend().delete_password(_SERVICE, _ACCOUNT)
        except Exception:
            pass


def create_openai_translator(session_key: str = '', *, credential_store: CredentialStore | None = None) -> OpenAITranslator:
    store = credential_store or CredentialStore()
    key = session_key.strip() or store.get()
    if not key:
        raise ValueError('Ustaw OPENAI_API_KEY lub wpisz klucz w zakładce AI')
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError('Brakuje biblioteki openai. Uruchom pip install -r requirements.txt') from exc
    return OpenAITranslator(OpenAI(api_key=key, timeout=60.0, max_retries=2))
