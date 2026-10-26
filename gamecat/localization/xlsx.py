"""Small XLSX table adapter using only ZIP and Office Open XML.

Reads inline/shared strings and numeric values; formula cells are not used as
translation targets. Template exports leave all other ZIP entries intact.
"""
from __future__ import annotations

from pathlib import Path
from tempfile import NamedTemporaryFile
from zipfile import ZipFile, ZIP_DEFLATED
import os
import re
import xml.etree.ElementTree as ET

S = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
P = 'http://schemas.openxmlformats.org/package/2006/relationships'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
ET.register_namespace('', S)


def _col_to_index(col: str) -> int:
    n = 0
    for letter in col:
        n = n * 26 + ord(letter.upper()) - ord('A') + 1
    return n - 1


def _index_to_col(index: int) -> str:
    index += 1
    result = ''
    while index:
        index, mod = divmod(index - 1, 26)
        result = chr(65 + mod) + result
    return result


def _sheet_path(zip_file: ZipFile, sheet_name: str) -> tuple[str, str]:
    book = ET.fromstring(zip_file.read('xl/workbook.xml'))
    sheets = book.find(f'{{{S}}}sheets')
    if sheets is None or not list(sheets):
        raise ValueError('XLSX contains no sheets')
    choice = next((e for e in sheets if e.get('name') == sheet_name), None) if sheet_name else list(sheets)[0]
    if choice is None:
        raise ValueError(f'XLSX sheet not found: {sheet_name}')
    relationships = ET.fromstring(zip_file.read('xl/_rels/workbook.xml.rels'))
    rid = choice.get(f'{{{R}}}id')
    target = next((e.get('Target') for e in relationships if e.get('Id') == rid), None)
    if target is None:
        raise ValueError('Missing XLSX sheet relationship')
    # Office targets may be /xl/worksheets/sheet1.xml or worksheets/sheet1.xml.
    import posixpath
    target = target.lstrip('/') if target.startswith('/') else posixpath.normpath(posixpath.join('xl', target))
    if target not in zip_file.namelist() or not target.startswith('xl/worksheets/'):
        raise ValueError('Unsafe or missing XLSX worksheet path')
    return target, choice.get('name') or ''


def _shared_strings(zip_file: ZipFile) -> list[str]:
    if 'xl/sharedStrings.xml' not in zip_file.namelist():
        return []
    root = ET.fromstring(zip_file.read('xl/sharedStrings.xml'))
    return [''.join(t.text or '' for t in entry.iter(f'{{{S}}}t')) for entry in root]


def _cell_value(cell: ET.Element, shared: list[str]) -> str:
    if cell.get('t') == 'inlineStr':
        return ''.join(t.text or '' for t in cell.iter(f'{{{S}}}t'))
    v = cell.find(f'{{{S}}}v')
    if v is None or v.text is None:
        return ''
    if cell.get('t') == 's':
        return shared[int(v.text)]
    return v.text


def read_table(path: Path, sheet_name: str = '') -> list[list[str]]:
    with ZipFile(path) as z:
        sheet, _ = _sheet_path(z, sheet_name)
        root = ET.fromstring(z.read(sheet))
        shared = _shared_strings(z)
        rows: list[list[str]] = []
        for row in root.iter(f'{{{S}}}row'):
            values: dict[int, str] = {}
            for cell in row.findall(f'{{{S}}}c'):
                ref = cell.get('r', '')
                match = re.match(r'[A-Z]+', ref)
                index = _col_to_index(match.group()) if match else len(values)
                values[index] = _cell_value(cell, shared)
            if values:
                rows.append([values.get(i, '') for i in range(max(values) + 1)])
            else:
                rows.append([])
        return rows


def _new_cell(ref: str, text: str) -> ET.Element:
    cell = ET.Element(f'{{{S}}}c', {'r': ref, 't': 'inlineStr'})
    text_el = ET.SubElement(ET.SubElement(cell, f'{{{S}}}is'), f'{{{S}}}t')
    if text.startswith(' ') or text.endswith(' ') or '\n' in text:
        text_el.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
    text_el.text = text
    return cell


def _set_cell(row: ET.Element, col: int, value: str, row_number: int) -> None:
    address = f'{_index_to_col(col)}{row_number}'
    cells = row.findall(f'{{{S}}}c')
    existing = next((c for c in cells if c.get('r') == address), None)
    if existing is not None:
        if existing.find(f'{{{S}}}f') is not None:
            raise ValueError(f'Refusing to overwrite spreadsheet formula: {address}')
        existing.attrib['t'] = 'inlineStr'
        for child in list(existing):
            existing.remove(child)
        inner = _new_cell(address, value).find(f'{{{S}}}is')
        existing.append(inner)
    else:
        cell = _new_cell(address, value)
        for idx, candidate in enumerate(cells):
            col_ref = re.match(r'[A-Z]+', candidate.get('r', ''))
            if col_ref and _col_to_index(col_ref.group()) > col:
                row.insert(idx, cell)
                break
        else:
            row.append(cell)


def patch_table(template: Path, destination: Path, sheet_name: str, target_field: str,
                targets: dict[int, str]) -> None:
    """Update Target for 1-based *data* row positions, retain remaining XLSX payload."""
    with ZipFile(template) as source:
        sheet, _ = _sheet_path(source, sheet_name)
        root = ET.fromstring(source.read(sheet))
        data = root.find(f'{{{S}}}sheetData')
        if data is None:
            raise ValueError('XLSX has no sheetData')
        all_rows = list(data.findall(f'{{{S}}}row'))
        if not all_rows:
            raise ValueError('XLSX has no header')
        shared = _shared_strings(source)
        header = { _cell_value(c, shared): _col_to_index(re.match(r'[A-Z]+', c.get('r', 'A')).group())
                  for c in all_rows[0].findall(f'{{{S}}}c')}
        target_col = header.get(target_field, max(header.values(), default=-1) + 1)
        if target_field not in header:
            _set_cell(all_rows[0], target_col, target_field, int(all_rows[0].get('r', '1')))
        for position, target in targets.items():
            if position <= 0 or position >= len(all_rows):
                raise ValueError(f'XLSX row missing: {position}')
            row = all_rows[position]
            _set_cell(row, target_col, target, int(row.get('r', str(position + 1))))
        output_bytes = ET.tostring(root, encoding='utf-8', xml_declaration=True)
        with NamedTemporaryFile(prefix='.gamecat-', suffix='.xlsx', dir=destination.parent, delete=False) as temp:
            tmp_path = Path(temp.name)
        try:
            with ZipFile(tmp_path, 'w') as dest:
                for entry in source.infolist():
                    dest.writestr(entry, output_bytes if entry.filename == sheet else source.read(entry.filename))
            os.replace(tmp_path, destination)
        finally:
            tmp_path.unlink(missing_ok=True)


def write_workbook(path: Path, sheets: dict[str, list[list[str]]]) -> None:
    """Create a plain, editable XLSX table for GameCAT exchanges."""
    def xml(value: ET.Element) -> bytes:
        return ET.tostring(value, encoding='utf-8', xml_declaration=True)

    types = ET.Element('{http://schemas.openxmlformats.org/package/2006/content-types}Types')
    ET.SubElement(types, '{http://schemas.openxmlformats.org/package/2006/content-types}Default', Extension='rels', ContentType='application/vnd.openxmlformats-package.relationships+xml')
    ET.SubElement(types, '{http://schemas.openxmlformats.org/package/2006/content-types}Default', Extension='xml', ContentType='application/xml')
    ET.SubElement(types, '{http://schemas.openxmlformats.org/package/2006/content-types}Override', PartName='/xl/workbook.xml', ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml')
    rootrels = ET.Element(f'{{{P}}}Relationships')
    ET.SubElement(rootrels, f'{{{P}}}Relationship', Id='rId1', Type=f'{R}/officeDocument', Target='xl/workbook.xml')
    book = ET.Element(f'{{{S}}}workbook')
    book_sheets = ET.SubElement(book, f'{{{S}}}sheets')
    rels = ET.Element(f'{{{P}}}Relationships')
    with ZipFile(path, 'w', ZIP_DEFLATED) as z:
        for number, (name, rows) in enumerate(sheets.items(), 1):
            if not rows:
                raise ValueError('Each XLSX sheet needs a header')
            fname = f'xl/worksheets/sheet{number}.xml'
            ET.SubElement(types, '{http://schemas.openxmlformats.org/package/2006/content-types}Override', PartName=f'/{fname}', ContentType='application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml')
            ET.SubElement(book_sheets, f'{{{S}}}sheet', {'name': name, 'sheetId': str(number), f'{{{R}}}id': f'rId{number}'})
            ET.SubElement(rels, f'{{{P}}}Relationship', Id=f'rId{number}', Type=f'{R}/worksheet', Target=f'worksheets/sheet{number}.xml')
            sheet = ET.Element(f'{{{S}}}worksheet')
            body = ET.SubElement(sheet, f'{{{S}}}sheetData')
            for rowno, values in enumerate(rows, 1):
                row = ET.SubElement(body, f'{{{S}}}row', r=str(rowno))
                for col, text in enumerate(values):
                    row.append(_new_cell(f'{_index_to_col(col)}{rowno}', str(text)))
            z.writestr(fname, xml(sheet))
        z.writestr('[Content_Types].xml', xml(types))
        z.writestr('_rels/.rels', xml(rootrels))
        z.writestr('xl/workbook.xml', xml(book))
        z.writestr('xl/_rels/workbook.xml.rels', xml(rels))
