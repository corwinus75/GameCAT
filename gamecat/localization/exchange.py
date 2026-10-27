"""Import/export game localization data without changing unrelated template fields."""
from __future__ import annotations

import csv
import json
import os
from collections.abc import Iterable, Iterator
from pathlib import Path
from tempfile import NamedTemporaryFile
import xml.etree.ElementTree as ET

from gamecat.importers.base import ImportedSegment
from gamecat.importers.translation_importer import ImportedTranslation
from gamecat.localization.profiles import FormatProfile
from gamecat.localization.xlsx import patch_table, read_table, write_workbook
from gamecat.models.segment import Segment


def _get_path(obj: dict, path: str, *, default=None):
    if not path:
        return default
    cur = obj
    for part in path.split('.'):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur


def _set_path(obj: dict, path: str, value: str) -> None:
    cur = obj
    bits = path.split('.')
    for part in bits[:-1]:
        if not isinstance(cur, dict) or part not in cur or not isinstance(cur[part], dict):
            raise ValueError(f'Target path is missing in template: {path}')
        cur = cur[part]
    if not isinstance(cur, dict):
        raise ValueError(f'Target path is invalid: {path}')
    cur[bits[-1]] = value


def _json_records(root, profile: FormatProfile) -> list[tuple[str | None, dict]]:
    obj = root
    if profile.records_path:
        for part in profile.records_path.split('.'):
            if not isinstance(obj, dict) or part not in obj:
                raise ValueError(f'JSON records_path missing: {profile.records_path}')
            obj = obj[part]
    if isinstance(obj, list):
        if not all(isinstance(item, dict) for item in obj):
            raise ValueError('JSON records must be objects')
        return [(None, item) for item in obj]
    if isinstance(obj, dict):
        if not all(isinstance(item, dict) for item in obj.values()):
            raise ValueError('Mapped JSON dictionary must contain record objects')
        return [(str(key), item) for key, item in obj.items()]
    raise ValueError('Mapped JSON path must point to an array or object')


def _xml_root(path: Path) -> ET.Element:
    raw = path.read_bytes()
    if b'<!DOCTYPE' in raw.upper() or b'<!ENTITY' in raw.upper():
        raise ValueError('XML with DTD/entities is not supported')
    return ET.fromstring(raw)


def _xml_records(root: ET.Element, profile: FormatProfile) -> list[ET.Element]:
    nodes = root.findall(profile.records_path or './/entry')
    if not nodes:
        raise ValueError(f'XML records not found: {profile.records_path or ".//entry"}')
    return nodes


def _xml_value(node: ET.Element, field: str, *, optional: bool = False) -> str | None:
    if not field:
        return None
    if field.startswith('@'):
        val = node.get(field[1:])
        if val is None and not optional:
            raise ValueError(f'Missing XML attribute: {field}')
        return val
    elem = node.find(field)
    if elem is None:
        if optional:
            return None
        raise ValueError(f'Missing XML element: {field}')
    if list(elem):
        # Mixed XML content cannot be safely replaced by plain-text translation.
        return ''.join(elem.itertext())
    return elem.text or ''


def _xml_set(node: ET.Element, field: str, value: str) -> None:
    if field.startswith('@'):
        node.set(field[1:], value)
        return
    elem = node.find(field)
    if elem is None:
        bits = field.split('/')
        if len(bits) != 1:
            raise ValueError(f'Cannot create missing nested XML Target path: {field}')
        elem = ET.SubElement(node, field)
    if list(elem):
        raise ValueError(f'Refusing to overwrite XML Target containing nested markup: {field}')
    elem.text = value


def _table_records(path: Path, profile: FormatProfile) -> list[dict[str, str]]:
    if profile.format == 'xlsx':
        rows = read_table(path, profile.sheet_name)
        if not rows:
            raise ValueError('XLSX has no header')
        names = rows[0]
        return [{name: (row[i] if i < len(row) else '') for i, name in enumerate(names)} for row in rows[1:]]
    with path.open('r', encoding='utf-8-sig', newline='') as fp:
        reader = csv.DictReader(fp, delimiter='\t' if profile.format == 'tsv' else ',')
        if not reader.fieldnames:
            raise ValueError('Empty table')
        return list(reader)


def read_source(path: Path, profile: FormatProfile) -> Iterator[ImportedSegment]:
    """Read source and optional target using a trusted declarative mapping."""
    if path.suffix.lower().lstrip('.') != profile.format:
        raise ValueError('Profile format does not match file extension')
    if profile.format in {'csv', 'tsv', 'xlsx'}:
        for i, row in enumerate(_table_records(path, profile), 1):
            if profile.source_field not in row:
                raise ValueError(f'Missing Source column: {profile.source_field}')
            if profile.key_field and profile.key_field not in row:
                raise ValueError(f'Missing key column: {profile.key_field}')
            target = row.get(profile.target_field, '')
            source = row[profile.source_field]
            if source is None or target is None:
                raise ValueError(f'Missing value in row {i}')
            if profile.comment_field and profile.comment_field not in row:
                raise ValueError(f'Missing context column: {profile.comment_field}')
            comment = row.get(profile.comment_field, '') if profile.comment_field else ''
            if comment is None:
                comment = ''
            yield ImportedSegment(i, source, row.get(profile.key_field) or None, target, str(comment))
        return
    if profile.format == 'json':
        root = json.loads(path.read_text(encoding='utf-8-sig'))
        for i, (outer_key, obj) in enumerate(_json_records(root, profile), 1):
            source = _get_path(obj, profile.source_field)
            target = _get_path(obj, profile.target_field, default='')
            key = _get_path(obj, profile.key_field, default=outer_key)
            if not isinstance(source, str) or not isinstance(target, str):
                raise ValueError(f'JSON text must be a string at position {i}')
            comment = _get_path(obj, profile.comment_field, default='') if profile.comment_field else ''
            if not isinstance(comment, str):
                raise ValueError(f'JSON context must be a string at position {i}')
            yield ImportedSegment(i, source, str(key) if key is not None else None, target, comment)
        return
    if profile.format == 'xml':
        for i, node in enumerate(_xml_records(_xml_root(path), profile), 1):
            key = _xml_value(node, profile.key_field, optional=not bool(profile.key_field))
            source = _xml_value(node, profile.source_field)
            target = _xml_value(node, profile.target_field, optional=True) or ''
            comment = _xml_value(node, profile.comment_field, optional=True) or ''
            yield ImportedSegment(i, source, key, target, comment)
        return
    if profile.format == 'txt':
        with path.open(encoding='utf-8-sig') as fp:
            for i, line in enumerate(fp, 1):
                yield ImportedSegment(i, line.rstrip('\r\n'))
        return
    raise ValueError(f'Unsupported format: {profile.format}')


def read_translations(path: Path, profile: FormatProfile) -> Iterator[ImportedTranslation]:
    """Read translation-only files with Target and optional key (no Source needed)."""
    if path.suffix.lower().lstrip('.') != profile.format:
        raise ValueError('Profile format does not match translation file')
    if profile.format in {'csv', 'tsv', 'xlsx'}:
        for position, row in enumerate(_table_records(path, profile), 1):
            if profile.target_field not in row:
                raise ValueError(f'Missing Target column: {profile.target_field}')
            if profile.key_field and profile.key_field not in row:
                raise ValueError(f'Missing key column: {profile.key_field}')
            target = row[profile.target_field]
            if not isinstance(target, str):
                raise ValueError(f'Invalid Target value at {position}')
            key = row.get(profile.key_field) if profile.key_field else None
            yield ImportedTranslation(target, key=key or None, position=None if key else position)
        return
    if profile.format == 'json':
        root = json.loads(path.read_text(encoding='utf-8-sig'))
        for position, (outer_key, obj) in enumerate(_json_records(root, profile), 1):
            target = _get_path(obj, profile.target_field)
            if not isinstance(target, str):
                raise ValueError(f'Missing or invalid JSON Target at {position}')
            key = _get_path(obj, profile.key_field, default=outer_key)
            yield ImportedTranslation(target, key=str(key) if key is not None else None,
                                      position=None if key is not None else position)
        return
    if profile.format == 'xml':
        for position, node in enumerate(_xml_records(_xml_root(path), profile), 1):
            target = _xml_value(node, profile.target_field)
            key = _xml_value(node, profile.key_field, optional=True)
            yield ImportedTranslation(target or '', key=key,
                                      position=None if key else position)
        return
    if profile.format == 'txt':
        with path.open('r', encoding='utf-8-sig') as fp:
            for position, line in enumerate(fp, 1):
                yield ImportedTranslation(line.rstrip('\r\n'), position=position)
        return
    raise ValueError(f'Unsupported format: {profile.format}')


def _segments_for_template(segments: Iterable[Segment], template: list[ImportedSegment]) -> dict[int, Segment]:
    by_key: dict[str, Segment] = {}
    by_pos: dict[int, Segment] = {}
    for segment in segments:
        if segment.key is not None:
            if segment.key in by_key:
                raise ValueError(f'Duplicate segment key: {segment.key}')
            by_key[segment.key] = segment
        if segment.position in by_pos:
            raise ValueError(f'Duplicate segment position: {segment.position}')
        by_pos[segment.position] = segment
    matches: dict[int, Segment] = {}
    used: set[int] = set()
    template_keys: set[str] = set()
    for row in template:
        if row.key is not None:
            if row.key in template_keys:
                raise ValueError(f'Duplicate template key: {row.key}')
            template_keys.add(row.key)
        match = by_key.get(row.key) if row.key is not None else by_pos.get(row.position)
        if match is None:
            continue  # unimported template entries remain unchanged
        if match.source != row.source:
            raise ValueError(f'Source mismatch for key {row.key or row.position}')
        matches[row.position] = match
        used.add(match.position)
    if len(used) != len(by_pos):
        raise ValueError('Some project segments are missing in template; export aborted')
    return matches


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(prefix='.gamecat-', dir=path.parent, delete=False) as file:
        temp = Path(file.name)
        file.write(payload)
    try:
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def export_translations(segments: Iterable[Segment], path: Path, profile: FormatProfile,
                        *, template_path: Path | None = None) -> int:
    """Export flat files or patch a copy of a matching source template.

    Never updates a template in place. Project Source values are compared to the
    template before writing any output; unrelated fields are retained.
    """
    if path.suffix.lower().lstrip('.') != profile.format:
        raise ValueError('Export extension/profile mismatch')
    # A flat table doesn't need to retain or sort the entire project: the
    # ProjectService iterator already yields database rows in position/id order.
    if template_path is None and profile.format in {'csv', 'tsv'}:
        fields = list(dict.fromkeys([profile.key_field or 'key', profile.source_field,
                                    profile.target_field, 'position'] +
                                    ([profile.comment_field] if profile.comment_field else [])))
        path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(prefix='.gamecat-', dir=path.parent, delete=False) as handle:
            temp = Path(handle.name)
        count = 0
        try:
            with temp.open('w', encoding='utf-8-sig', newline='') as output:
                writer = csv.DictWriter(output, fieldnames=fields,
                                        delimiter='\t' if profile.format == 'tsv' else ',')
                writer.writeheader()
                for segment in segments:
                    row = {profile.key_field or 'key': segment.key or '',
                           profile.source_field: segment.source,
                           profile.target_field: segment.target, 'position': str(segment.position)}
                    if profile.comment_field:
                        row[profile.comment_field] = segment.comment
                    writer.writerow(row)
                    count += 1
            os.replace(temp, path)
        finally:
            temp.unlink(missing_ok=True)
        return count
    if template_path is None and profile.format == 'txt':
        path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(prefix='.gamecat-', dir=path.parent, delete=False) as handle:
            temp = Path(handle.name)
        count = 0
        try:
            with temp.open('w', encoding='utf-8') as output:
                for segment in segments:
                    output.write(segment.target + '\n')
                    count += 1
            os.replace(temp, path)
        finally:
            temp.unlink(missing_ok=True)
        return count

    ordered = list(segments)  # XML/JSON/XLSX/template validation may need materialization
    if template_path is not None:
        template_path = Path(template_path)
        if template_path.resolve() == path.resolve():
            raise ValueError('Output must differ from source template')
        matches = _segments_for_template(ordered, list(read_source(template_path, profile)))
    else:
        matches = {index: s for index, s in enumerate(ordered, 1)}

    if profile.format == 'json':
        if template_path is None:
            data = [{'key': s.key, 'source': s.source, 'target': s.target, 'position': s.position, 'comment': s.comment}
                    for s in ordered]
        else:
            data = json.loads(template_path.read_text(encoding='utf-8-sig'))
            for pos, (_, record) in enumerate(_json_records(data, profile), 1):
                if pos in matches:
                    _set_path(record, profile.target_field, matches[pos].target)
        _atomic_write(path, (json.dumps(data, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
    elif profile.format == 'xml':
        if template_path is None:
            root = ET.Element('gamecat')
            for seg in ordered:
                item = ET.SubElement(root, 'entry')
                for field, value in (('key', seg.key or str(seg.position)), ('source', seg.source), ('target', seg.target), ('comment', seg.comment)):
                    ET.SubElement(item, field).text = value
        else:
            root = _xml_root(template_path)
            for pos, record in enumerate(_xml_records(root, profile), 1):
                if pos in matches:
                    _xml_set(record, profile.target_field, matches[pos].target)
        _atomic_write(path, ET.tostring(root, encoding='utf-8', xml_declaration=True))
    elif profile.format in {'csv', 'tsv'}:
        from io import StringIO
        buffer = StringIO(newline='')
        delimiter = '\t' if profile.format == 'tsv' else ','
        if template_path is not None:
            with template_path.open('r', encoding='utf-8-sig', newline='') as fp:
                reader = csv.DictReader(fp, delimiter=delimiter)
                fields = list(reader.fieldnames or [])
                table = list(reader)
            if profile.target_field not in fields:
                fields.append(profile.target_field)
            for pos, row in enumerate(table, 1):
                if pos in matches:
                    row[profile.target_field] = matches[pos].target
        else:
            fields = [profile.key_field or 'key', profile.source_field, profile.target_field, 'position']
            if profile.comment_field:
                fields.append(profile.comment_field)
            fields = list(dict.fromkeys(fields))
            table = [{profile.key_field or 'key': s.key or '', profile.source_field: s.source,
                      profile.target_field: s.target, 'position': str(s.position), **({profile.comment_field: s.comment} if profile.comment_field else {})} for s in ordered]
        writer = csv.DictWriter(buffer, fieldnames=fields, delimiter=delimiter)
        writer.writeheader()
        writer.writerows(table)
        _atomic_write(path, buffer.getvalue().encode('utf-8-sig'))
    elif profile.format == 'xlsx':
        if template_path is not None:
            patch_table(template_path, path, profile.sheet_name, profile.target_field,
                        {pos: seg.target for pos, seg in matches.items()})
        else:
            write_workbook(path, {profile.sheet_name or 'Segments': [
                [profile.key_field or 'key', profile.source_field, profile.target_field, 'position'] + ([profile.comment_field] if profile.comment_field else []),
                *[[s.key or '', s.source, s.target, str(s.position)] + ([s.comment] if profile.comment_field else []) for s in ordered]
            ]})
    elif profile.format == 'txt':
        _atomic_write(path, ''.join(seg.target + '\n' for seg in ordered).encode('utf-8'))
    else:
        raise ValueError(f'Unsupported format: {profile.format}')
    return len(matches)
