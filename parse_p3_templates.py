"""Parse EBA Pillar 3 annotated table layout XLSX to extract template names."""
import zipfile
import xml.etree.ElementTree as ET
import sys

import os
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FILE = os.path.join(SCRIPT_DIR, r'master_data\extracted\table_layout\20250519 Annotated Table Layout  P3DHPILLAR3 4.1.xlsx')
NS = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'

def get_cell_value(cell, strings):
    """Extract value from a cell XML element."""
    v = cell.find(f'{NS}v')
    if v is None:
        return ''
    if cell.get('t') == 's':
        idx = int(v.text)
        return strings[idx] if idx < len(strings) else ''
    return v.text

with zipfile.ZipFile(FILE) as z:
    # Load shared strings
    shared_xml = ET.parse(z.open('xl/sharedStrings.xml'))
    strings = [t.text if t.text else '' for t in shared_xml.findall(f'.//{NS}t')]
    print(f'Shared strings: {len(strings)}')

    # Parse TOC sheet (sheet1 = TOC)
    sheet = ET.parse(z.open('xl/worksheets/sheet1.xml'))
    rows = sheet.findall(f'.//{NS}row')
    print(f'TOC rows: {len(rows)}')

    for r in rows:
        cells = []
        for c in r.findall(f'{NS}c'):
            cells.append(get_cell_value(c, strings))
        # Print rows that have content in first 3 columns
        if any(cells):
            # Show first 6 columns max
            print(f'Row {r.get("row")}: {cells[:6]}')