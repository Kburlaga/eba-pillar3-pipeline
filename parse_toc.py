"""Parse TOC sheets from all DISPILLAR3 XLSX files to extract template codes and names."""
import zipfile
import xml.etree.ElementTree as ET
import os

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), r'master_data\extracted\table_layout')
NS = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'

files = sorted([f for f in os.listdir(BASE) if f.endswith('.xlsx') and 'DISPILLAR3' in f])

templates = {}

for fname in files:
    full = os.path.join(BASE, fname)
    module_name = fname.split('Layout  ')[1].replace(' 4.1.xlsx', '')
    print(f'\n=== {module_name} ===')

    with zipfile.ZipFile(full) as z:
        # Load shared strings
        shared_xml = ET.parse(z.open('xl/sharedStrings.xml'))
        strings = [t.text if t.text else '' for t in shared_xml.findall(f'.//{NS}t')]
        
        # Parse TOC sheet (sheet1)
        sheet = ET.parse(z.open('xl/worksheets/sheet1.xml'))
        
        def cell_value(cell):
            v = cell.find(f'{NS}v')
            if v is None:
                return ''
            if cell.get('t') == 's':
                idx = int(v.text)
                return strings[idx] if idx < len(strings) else ''
            return v.text
        
        rows = sheet.findall(f'.//{NS}row')
        for r in rows:
            cells = []
            for c in r.findall(f'{NS}c'):
                cells.append(cell_value(c))
            if any(cells) and cells[0] not in ('Table of Contents', module_name.replace('DISPILLAR3', ''), ''):
                code = cells[0] if len(cells) > 0 else ''
                name = cells[1] if len(cells) > 1 else ''
                templates[code] = {'name': name, 'module': module_name}
                print(f'  {code}: {name[:100]}')

print(f'\n\nTotal templates: {len(templates)}')

# Print unique list ordered by code for init.sql
print('\n--- SQL INSERT template list ---')
for code in sorted(templates.keys()):
    t = templates[code]
    name_escaped = t['name'].replace("'", "''")[:250]
    print(f"  ('{code}', '{name_escaped}', 'v4.1', NULL),")