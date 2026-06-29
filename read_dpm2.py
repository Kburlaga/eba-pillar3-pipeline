"""Read EBA DPM 2.0 Database (.accdb) and export structure."""
import pyodbc
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 
                        r'master_data\extracted\dpm2\DPM2 Database_v 4_2_20251125.accdb')

conn_str = (
    r'DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};'
    f'DBQ={DB_PATH};'
)

conn = pyodbc.connect(conn_str)
cursor = conn.cursor()

# List all tables
print("=== ALL TABLES ===")
tables = []
for row in cursor.tables():
    if row.table_type in ('TABLE', 'VIEW'):
        tables.append(row.table_name)
        print(f"  {row.table_name} ({row.table_type})")

print(f"\nTotal: {len(tables)} tables/views\n")

# Show row counts for each table
print("=== TABLE ROW COUNTS ===")
for table in sorted(tables):
    try:
        cnt = cursor.execute(f'SELECT COUNT(*) FROM [{table}]').fetchone()[0]
        print(f"  {table}: {cnt} rows")
    except Exception as e:
        print(f"  {table}: ERROR - {e}")

# Show first 5 tables schema
print("\n=== FIRST 5 TABLES SCHEMA ===")
for table in sorted(tables)[:5]:
    print(f"\n--- {table} ---")
    for col in cursor.columns(table=table):
        print(f"  {col.column_name} ({col.type_name})")
    # Show first 3 rows
    try:
        rows = cursor.execute(f'SELECT * FROM [{table}]').fetchmany(3)
        for r in rows:
            print(f"  SAMPLE: {r}")
    except:
        pass

conn.close()