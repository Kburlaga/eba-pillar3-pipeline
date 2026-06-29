"""Extract Pillar 3 templates, variables and validation rules from DPM2."""
import pyodbc, os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        r'master_data\extracted\dpm2\DPM2 Database_v 4_2_20251125.accdb')
conn = pyodbc.connect(r'DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};DBQ=' + DB_PATH + ';')
c = conn.cursor()

# Pillar 3 modules (FrameworkID=16)
print("=== PILLAR3 MODULES ===")
q1 = "SELECT m.ModuleID, m.Code, m.Name FROM Module m WHERE m.FrameworkID = 16 ORDER BY m.Code"
for row in c.execute(q1):
    print(f"  M{row.ModuleID}: {row.Code} - {row.Name[:80]}")

# Tables (szablony) for each Pillar 3 module
print("\n=== PILLAR3 TABLES (templates) ===")
q2 = """
SELECT t.TableID, t.Code, t.Name, m.Code as ModCode
FROM ([Table] t INNER JOIN TableGroup tg ON t.TableGroupID = tg.TableGroupID)
INNER JOIN Module m ON tg.ModuleID = m.ModuleID
WHERE m.FrameworkID = 16
ORDER BY m.Code, t.Code
"""
for row in c.execute(q2):
    print(f"  [{row.ModCode}] {row.Code}: {row.Name[:80]}")

# Count of variables per Pillar 3 module
print("\n=== PILLAR3 VARIABLES per module ===")
q3 = """
SELECT m.Code, COUNT(v.VariableID) as cnt
FROM ((Variable v INNER JOIN TableVersionCell tvc ON v.CellID = tvc.CellID)
     INNER JOIN TableVersion tv ON tvc.TableVID = tv.TableVID)
INNER JOIN ModuleVersion mv ON tv.ModuleVID = mv.ModuleVID
INNER JOIN Module m ON mv.ModuleID = m.ModuleID
WHERE m.FrameworkID = 16
GROUP BY m.Code
ORDER BY m.Code
"""
for row in c.execute(q3):
    print(f"  {row.Code}: {row.cnt} zmiennych")

conn.close()