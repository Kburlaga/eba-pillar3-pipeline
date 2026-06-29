"""Migrate DPM2 .accdb (Access) to PostgreSQL schema dpm2_ref.

Uses individual SELECT * queries (no JOINs, which Access ODBC doesn't support).
Creates schema dpm2_ref with all 69 tables, preserving data types and primary keys.
"""
import pyodbc
import psycopg2
import psycopg2.extras
import os
import sys
import yaml
from collections import OrderedDict

# ─── CONFIG ───────────────────────────────────────────────────────────────────
_BASE = os.path.dirname(os.path.abspath(__file__))
ACCESS_DB = os.path.join(_BASE, r'master_data\extracted\dpm2\DPM2 Database_v 4_2_20251125.accdb')

# Dane dostępowe z config.yaml (poza repo; wzorzec: config.example.yaml)
with open(os.path.join(_BASE, 'config.yaml'), encoding='utf-8') as _f:
    PG_CONFIG = yaml.safe_load(_f)['database']

SCHEMA = 'dpm2_ref'
BATCH_SIZE = 5000  # rows per INSERT batch

# Type mapping: Access ODBC → PostgreSQL
TYPE_MAP = {
    'INTEGER': 'INTEGER',
    'SMALLINT': 'SMALLINT',
    'VARCHAR': 'TEXT',
    'LONGCHAR': 'TEXT',
    'TEXT': 'TEXT',
    'GUID': 'UUID',
    'DATETIME': 'TIMESTAMP',
    'DOUBLE': 'DOUBLE PRECISION',
    'CURRENCY': 'NUMERIC',
    'BOOLEAN': 'BOOLEAN',
    'BIT': 'BOOLEAN',
    'BYTE': 'SMALLINT',
}

# Tables to skip (empty/system tables)
SKIP_TABLES = {
    'ChangeLog', 'Document', 'DocumentVersion', 'Language',
    'OperationCodePrefix', 'Reference', 'Role', 'Subdivision',
    'SubdivisionType', 'TableLock', 'Translation',
    'User', 'UserRole', 'DPMAttribute', 'VariableCalculation',
}


def get_access_tables(cursor) -> list[str]:
    """Get user tables from Access."""
    tables = []
    for row in cursor.tables():
        if row.table_type == 'TABLE' and row.table_name not in SKIP_TABLES:
            tables.append(row.table_name)
    return sorted(tables)


def get_table_schema(cursor, table_name: str) -> list[tuple]:
    """Get column info: (name, type_name, is_pk)."""
    cols = []
    pk_cols = set()
    try:
        for row in cursor.statistics(table_name):
            if row.index_name and 'PrimaryKey' in (row.index_name or ''):
                pk_cols.add(row.column_name)
    except Exception:
        pass  # Some tables may not have PK info via ODBC

    for row in cursor.columns(table=table_name):
        col_name = row.column_name
        col_type = row.type_name.upper()
        pg_type = TYPE_MAP.get(col_type, 'TEXT')
        is_pk = col_name in pk_cols
        cols.append((col_name, pg_type, is_pk))

    # Deduce PK from column name if not found
    if not pk_cols and cols:
        likely_pk = table_name + 'ID'
        for c in cols:
            if c[0].upper() == likely_pk.upper():
                pk_cols.add(c[0])

    return cols


def create_pg_schema(pg_cur) -> None:
    """Create the dpm2_ref schema if it doesn't exist."""
    pg_cur.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")


def create_pg_table(pg_cur, table_name: str, columns: list[tuple]) -> None:
    """Create table in PostgreSQL matching Access structure."""
    col_defs = []
    pk_cols = []

    for col_name, pg_type, is_pk in columns:
        safe_name = '"' + col_name.replace('"', '""') + '"'
        if is_pk:
            pk_cols.append(safe_name)
            col_defs.append(f"{safe_name} {pg_type} NOT NULL")
        else:
            col_defs.append(f"{safe_name} {pg_type}")

    if pk_cols:
        col_defs.append(f"PRIMARY KEY ({', '.join(pk_cols)})")

    full_name = f"{SCHEMA}.{table_name.lower()}"
    pg_cur.execute(f"DROP TABLE IF EXISTS {full_name} CASCADE")
    pg_cur.execute(f"CREATE TABLE {full_name} ({', '.join(col_defs)})")
    print(f"  Created: {full_name} ({len(columns)} cols)")


def migrate_table(access_cur, pg_cur, table_name: str) -> int:
    """Copy all rows from Access table to PostgreSQL."""
    # Get columns without quoting
    cols_info = get_table_schema(access_cur, table_name)
    col_names = [c[0] for c in cols_info]

    # Read all rows from Access
    quoted = [f"[{c}]" for c in col_names]
    sql = f"SELECT {', '.join(quoted)} FROM [{table_name}]"
    rows = access_cur.execute(sql).fetchall()
    total = len(rows)

    if total == 0:
        return 0

    # Prepare INSERT
    safe_cols = ['"' + c.replace('"', '""') + '"' for c in col_names]
    placeholders = ['%s'] * len(col_names)
    insert_sql = f"INSERT INTO {SCHEMA}.{table_name.lower()} ({', '.join(safe_cols)}) VALUES ({', '.join(placeholders)})"

    # Batch insert using executemany
    for i in range(0, total, BATCH_SIZE):
        batch = rows[i:i + BATCH_SIZE]
        psycopg2.extras.execute_batch(pg_cur, insert_sql, batch, page_size=BATCH_SIZE)

    return total


def main():
    print("=== DPM2 Access → PostgreSQL Migration ===\n")

    # Connect to Access
    print("1. Connecting to Access DPM2 Database...")
    access_conn_str = r'DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};DBQ=' + ACCESS_DB + ';'
    access_conn = pyodbc.connect(access_conn_str)
    access_cur = access_conn.cursor()
    print("   OK")

    # Connect to PostgreSQL
    print("2. Connecting to PostgreSQL...")
    try:
        pg_conn = psycopg2.connect(**PG_CONFIG)
        pg_conn.autocommit = True
        pg_cur = pg_conn.cursor()
        print("   OK")
    except psycopg2.OperationalError as e:
        print(f"\n   ❌ Nie można połączyć z PostgreSQL! Błąd: {e}")
        print("\n   Upewnij się, że:")
        print("   - PostgreSQL jest uruchomiony")
        print("   - Baza 'eba_pillar3' istnieje (CREATE DATABASE eba_pillar3)")
        print("   - Domyślne hasło postgres/posta jest poprawne")
        print("\n   Zatrzymuję skrypt.")
        sys.exit(1)

    # Create schema
    create_pg_schema(pg_cur)
    print(f"\n3. Schema '{SCHEMA}' OK\n")

    # Get all tables
    tables = get_access_tables(access_cur)
    print(f"4. Found {len(tables)} tables to migrate:\n")

    total_rows = 0
    for idx, table_name in enumerate(tables, 1):
        try:
            cols = get_table_schema(access_cur, table_name)
            create_pg_table(pg_cur, table_name, cols)
            count = migrate_table(access_cur, pg_cur, table_name)
            total_rows += count
            print(f"  [{idx}/{len(tables)}] {table_name}: {count:,} rows")
        except Exception as e:
            print(f"  [{idx}/{len(tables)}] {table_name}: ❌ {e}")

    print(f"\n5. Done! {total_rows:,} total rows migrated across {len(tables)} tables.")
    print(f"   Schema: {SCHEMA}")

    access_conn.close()
    pg_conn.close()


if __name__ == '__main__':
    main()