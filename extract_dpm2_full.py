"""Full extract: Pillar 3 tables, variables, operations from DPM2."""
import pyodbc, os, sys

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   r'master_data\extracted\dpm2\DPM2 Database_v 4_2_20251125.accdb')
conn = pyodbc.connect(r'DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};DBQ=' + DB + ';')
c = conn.cursor()

# Latest module versions (v2.0.0, Release 5)
# ModuleVIDs: CODIS=443, FINDIS=444, REMDIS=448, ESGDIS=449, GSIIDIS=447, MRELTLACDIS=450, IRRBBDIS=451, P3DH=455
LATEST_MVS = [443, 444, 447, 448, 449, 450, 451, 455]

# 1. Get module info
print("=== MODULES (latest) ===")
ids = ','.join(str(x) for x in LATEST_MVS)
sql = f"SELECT ModuleVID, Code, Name, FromReferenceDate, ToReferenceDate FROM ModuleVersion WHERE ModuleVID IN ({ids})"
for r in c.execute(sql):
    print(f"  MV{r[0]}: {r[1]} - {r[2]} ({r[3]} to {r[4]})")

# 2. Tables per module
print("\n=== TABLES ===")
for mvid in LATEST_MVS:
    # Get module code
    mv = c.execute(f"SELECT Code, Name FROM ModuleVersion WHERE ModuleVID = {mvid}").fetchone()
    mod_code = mv[0]
    # Get tables for this module version
    sql_tables = f"SELECT Code, Name FROM TableVersion WHERE ModuleVID = {mvid} ORDER BY Code"
    rows = c.execute(sql_tables).fetchall()
    for r in rows:
        print(f"  [{mod_code}] {r[0]}: {r[1][:70] if r[1] else 'N/A'}")

# 3. Operations (validation rules) per module  
print("\n=== OPERATIONS (validation rules) per module ===")
# OperationScope has ModuleVID
sql = f"""
SELECT mv.Code, op.Code, op.Name
FROM (OperationScope os
      INNER JOIN Operation op ON os.OperationID = op.OperationID
      INNER JOIN ModuleVersion mv ON os.ModuleVID = mv.ModuleVID)
WHERE mv.ModuleVID IN ({ids})
ORDER BY mv.Code, op.Code
"""
ops = c.execute(sql).fetchall()
print(f"Total: {len(ops)} operations")
for r in ops[:20]:
    print(f"  [{r[0]}] {r[1]}: {r[2][:70] if r[2] else 'N/A'}")
if len(ops) > 20:
    print(f"  ... and {len(ops)-20} more")

# 4. Variables count
print("\n=== VARIABLES count ===")
sql = f"""
SELECT mv.Code, COUNT(v.VariableID) as cnt
FROM ((Variable v
       INNER JOIN TableVersionCell tvc ON v.CellID = tvc.CellID)
      INNER JOIN TableVersion tv ON tvc.TableVID = tv.TableVID)
INNER JOIN ModuleVersion mv ON tv.ModuleVID = mv.ModuleVID
WHERE mv.ModuleVID IN ({ids})
GROUP BY mv.Code
ORDER BY mv.Code
"""
for r in c.execute(sql):
    print(f"  {r[0]}: {r[1]} variables")

# 5. Sample variable details
print("\n=== SAMPLE VARIABLES (first 5) ===")
sql = f"""
SELECT TOP 5 v.Code, v.Name, tv.Code as TableCode, mv.Code as ModuleCode
FROM ((Variable v
       INNER JOIN TableVersionCell tvc ON v.CellID = tvc.CellID)
      INNER JOIN TableVersion tv ON tvc.TableVID = tv.TableVID)
INNER JOIN ModuleVersion mv ON tv.ModuleVID = mv.ModuleVID
WHERE mv.ModuleVID IN ({ids})
ORDER BY mv.Code, tv.Code
"""
for r in c.execute(sql):
    print(f"  [{r[3]}/{r[2]}] {r[0]}: {r[1][:70] if r[1] else 'N/A'}")

conn.close()