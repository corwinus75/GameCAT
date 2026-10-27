"""Przechowywanie klucza OpenAI: systemowy keyring, sesja lub zmienna środowiskowa – nigdy SQLite projektu."""
from __future__ import annotations

import os
from typing import Any

from gamecat.ai.core import OpenAITranslator

_SERVICE = 'GameCAT OpenAI API'
_ACCOUNT = 'default'


class CredentialStore:
    """Dostęp do klucza OpenAI API w systemowym magazynie poświadczeń."""
    def __init__(self, keyring_module: Any | None = None):
        """Opcjonalnie wstrzyknij moduł zgodny z ``keyring`` (używane w testach)."""
        self._keyring = keyring_module

    def _backend(self) -> Any:
        """Zwróć moduł keyring (wstrzyknięty lub importowany leniwie).

        :raises RuntimeError: gdy pakiet keyring nie jest zainstalowany.
        """
        if self._keyring is not None:
            return self._keyring
        try:
            import keyring
        except ImportError as exc:
            raise RuntimeError('Zainstaluj pakiet keyring do przechowywania klucza w systemie') from exc
        return keyring

    def get(self) -> str | None:
        """Zwróć klucz z ``OPENAI_API_KEY`` lub z keyringu; ``None``, gdy go brak."""
        if os.getenv('OPENAI_API_KEY', '').strip():
            return os.environ['OPENAI_API_KEY'].strip()
        try:
            return self._backend().get_password(_SERVICE, _ACCOUNT) or None
        except Exception:  # no secure backend: caller may supply session key
            return None

    def save(self, key: str) -> None:
        """Zapisz klucz w systemowym magazynie poświadczeń.

        :raises ValueError: pusty klucz.
        :raises RuntimeError: brak działającego magazynu poświadczeń.
        """
        if not key.strip():
            raise ValueError('Klucz OpenAI API nie może być pusty')
        try:
            self._backend().set_password(_SERVICE, _ACCOUNT, key.strip())
        except Exception as exc:
            raise RuntimeError('Brak działającego systemowego magazynu poświadczeń. Użyj OPENAI_API_KEY.') from exc

    def remove(self) -> None:
        """Usuń zapisany klucz; brak klucza lub magazynu nie jest błędem."""
        try:
            self._backend().delete_password(_SERVICE, _ACCOUNT)
        except Exception:
            pass


def create_openai_translator(session_key: str = '', *, credential_store: CredentialStore | None = None) -> OpenAITranslator:
    """Utwórz ``OpenAITranslator`` z kluczem sesyjnym albo zapisanym w systemie.

    :raises ValueError: gdy nie podano żadnego klucza.
    :raises RuntimeError: gdy brakuje biblioteki ``openai``.
    """
    store = credential_store or CredentialStore()
    key = session_key.strip() or store.get()
    if not key:
        raise ValueError('Ustaw OPENAI_API_KEY lub wpisz klucz w zakładce AI')
    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError('Brakuje biblioteki openai. Uruchom pip install -r requirements.txt') from exc
    return OpenAITranslator(OpenAI(api_key=key, timeout=60.0, max_retries=2))
