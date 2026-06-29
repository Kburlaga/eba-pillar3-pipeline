"""Wykonaj plik .sql na bazie z config.yaml. Użycie: python scripts/apply_sql.py <plik.sql>

Po co osobny runner: init.sql działa tylko na pustym wolumenie kontenera.
Zmiany schematu na ŻYWEJ bazie (migracje) wstrzykujemy tędy — bez restartu, bez kasowania danych.
"""
import sys
import yaml
import psycopg2


def main(sql_path: str):
    with open("config.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)["database"]

    with open(sql_path, encoding="utf-8") as f:
        sql = f.read()

    conn = psycopg2.connect(
        host=cfg["host"], port=cfg["port"], user=cfg["user"],
        password=cfg["password"], dbname=cfg["dbname"],
    )
    cur = conn.cursor()
    cur.execute(sql)          # cały plik jako jedna transakcja
    conn.commit()             # zatwierdź dopiero gdy całość przeszła
    cur.close()
    conn.close()
    print(f"OK: wykonano {sql_path}")


if __name__ == "__main__":
    main(sys.argv[1])
