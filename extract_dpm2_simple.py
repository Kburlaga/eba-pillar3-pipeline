"""Extract DPM2 Pillar 3 data using parameterized queries."""
import pyodbc
import os

DB = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   r'master_data\extracted\dpm2\DPM2 Database_v 4_2_20251125.accdb')
conn = pyodbc.connect(r'DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};DBQ=' + DB + ';')
c = conn.cursor()

LATEST_MVS = [443, 444, 447, 448, 449, 450, 451, 455]

# 1. Modules
print("=== MODULES ===")
for r in c.execute("SELECT ModuleVID, [Code], [Name], FromReferenceDate, ToReferenceDate FROM ModuleVersion WHERE ModuleVID IN (443,444,447,448,449,450,451,455)"):
    print(f"  MV{r[0]}: {r[1]} - {r[2]} ({r[3]} to {r[4]})")

# 2. Tables
print("\n=== TABLES ===")
for mvid in LATEST_MVS:
    mv = c.execute(f"SELECT [Code] FROM ModuleVersion WHERE ModuleVID = {mvid}").fetchone()
    rows = c.execute(f"SELECT [Code], [Name] FROM TableVersion WHERE ModuleVID = {mvid} ORDER BY [Code]").fetchall()
    for r in rows:
        print(f"  [{mv[0]}] {r[0]}: {r[1][:70] if r[1] else 'N/A'}")

# 3. Variables per module
print("\n=== VARIABLES count per module ===")
for mvid in LATEST_MVS:
    mv = c.execute(f"SELECT [Code] FROM ModuleVersion WHERE ModuleVID = {mvid}").fetchone()
    cnt = c.execute(f"""
        SELECT COUNT(v.VariableID)
        FROM (Variable v
              INNER JOIN TableVersionCell tvc ON v.CellID = tvc.CellID
              INNER JOIN TableVersion tv ON tvc.TableVID = tv.TableVID)
        WHERE tv.ModuleVID = {mvid}
    """).fetchone()[0]
    print(f"  {mv[0]}: {cnt} variables")

# 4. Operations per module
print("\n=== OPERATIONS per module ===")
for mvid in LATEST_MVS:
    mv = c.execute(f"SELECT [Code] FROM ModuleVersion WHERE ModuleVID = {mvid}").fetchone()
    ops = c.execute(f"""
        SELECT op.[Code], op.[Name]
        FROM (OperationScope os
              INNER JOIN Operation op ON os.OperationID = op.OperationID)
        WHERE os.ModuleVID = {mvid}
        ORDER BY op.[Code]
    """).fetchall()
    print(f"  [{mv[0]}] {len(ops)} operations")
    for op in ops[:3]:
        print(f"    {op[0]}: {op[1][:60] if op[1] else 'N/A'}")
    if len(ops) > 3:
        print(f"    ... and {len(ops)-3} more")

conn.close()
print("\nDone!")