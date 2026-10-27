"""Serializowalne profile mapowania formatów (per projekt), bez wykonywalnych wyrażeń."""
from __future__ import annotations

from dataclasses import dataclass, asdict

SUPPORTED_FORMATS = frozenset({'txt', 'csv', 'json', 'tsv', 'xlsx', 'xml'})


@dataclass(frozen=True, slots=True)
class FormatProfile:
    """Deklaratywne mapowanie pól pliku na klucz, Source, Target i komentarz segmentu."""
    format: str
    records_path: str = ''
    key_field: str = 'key'
    source_field: str = 'source'
    target_field: str = 'target'
    sheet_name: str = ''
    comment_field: str = ''  # Optional source context (speaker, location, notes)

    def __post_init__(self) -> None:
        """Zwaliduj profil: obsługiwany format, wymagane pola, poprawne ścieżki JSON.

        :raises ValueError: przy niepoprawnej konfiguracji.
        """
        if self.format not in SUPPORTED_FORMATS:
            raise ValueError(f'Unsupported format: {self.format}')
        if not self.source_field.strip() or not self.target_field.strip():
            raise ValueError('Source and Target fields are required')
        if self.format == 'json':
            for field in (self.records_path, self.key_field, self.source_field, self.target_field, self.comment_field):
                if field and (field.startswith('.') or field.endswith('.') or '..' in field):
                    raise ValueError(f'Invalid JSON mapping path: {field}')

    def to_dict(self) -> dict[str, str]:
        """Zwróć profil jako słownik do zapisu w SQLite (JSON)."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> FormatProfile:
        """Odtwórz profil ze słownika zapisanego w bazie (alternatywny konstruktor)."""
        return cls(**{key: str(value) for key, value in data.items()})
