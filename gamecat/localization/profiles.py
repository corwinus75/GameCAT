"""Serializable per-project format mapping, with no executable expressions."""
from __future__ import annotations

from dataclasses import dataclass, asdict

SUPPORTED_FORMATS = frozenset({'txt', 'csv', 'json', 'tsv', 'xlsx', 'xml'})


@dataclass(frozen=True, slots=True)
class FormatProfile:
    format: str
    records_path: str = ''
    key_field: str = 'key'
    source_field: str = 'source'
    target_field: str = 'target'
    sheet_name: str = ''

    def __post_init__(self) -> None:
        if self.format not in SUPPORTED_FORMATS:
            raise ValueError(f'Unsupported format: {self.format}')
        if not self.source_field.strip() or not self.target_field.strip():
            raise ValueError('Source and Target fields are required')
        if self.format == 'json':
            for field in (self.records_path, self.key_field, self.source_field, self.target_field):
                if field and (field.startswith('.') or field.endswith('.') or '..' in field):
                    raise ValueError(f'Invalid JSON mapping path: {field}')

    def to_dict(self) -> dict[str, str]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> FormatProfile:
        return cls(**{key: str(value) for key, value in data.items()})
