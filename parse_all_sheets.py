"""List all sheets in all XLSX files from table_layout folder."""
import zipfile
import xml.etree.ElementTree as ET
import os

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), r'master_data\extracted\table_layout')
NS = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'

files = sorted([f for f in os.listdir(BASE) if f.endswith('.xlsx')])

for fname in files:
    full = os.path.join(BASE, fname)
    with zipfile.ZipFile(full) as z:
        wb_xml = ET.parse(z.open('xl/workbook.xml'))
        sheets = wb_xml.findall(f'.//{NS}sheet')
        print(f'\n=== {fname} ({len(sheets)} sheets) ===')
        for s in sheets:
            print(f'  {s.get("name")[:80]}')