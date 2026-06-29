"""Master data — uzupełnij nazwy banków z GLEIF (oficjalny rejestr LEI) dla LEI obecnych w bronze.

Dla każdego LEI z bronze_report pobiera nazwę prawną + kraj z api.gleif.org i upsertuje do tabeli bank.
Wymaga internetu (publiczne API, bez klucza). Uruchom raz / gdy dojdą nowe banki.
"""
import requests
import yaml
import psycopg2

GLEIF = "https://api.gleif.org/api/v1/lei-records/{}"


def main():
    cfg = yaml.safe_load(open("config.yaml", encoding="utf-8"))["database"]
    conn = psycopg2.connect(host=cfg["host"], port=cfg["port"], user=cfg["user"],
                            password=cfg["password"], dbname=cfg["dbname"])
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT lei FROM bronze_report WHERE lei IS NOT NULL ORDER BY lei")
    leis = [r[0] for r in cur.fetchall()]

    done = 0
    for lei in leis:
        try:
            r = requests.get(GLEIF.format(lei), timeout=15)
            if r.status_code != 200:
                print(f"  {lei}: GLEIF HTTP {r.status_code} — pomijam")
                continue
            ent = r.json()["data"]["attributes"]["entity"]
            nazwa = ent["legalName"]["name"]
            kraj = ent["legalAddress"]["country"]
            # upsert po LEI; nie nadpisujemy kategorii istniejących wpisów
            cur.execute("""
                INSERT INTO bank (lei, nazwa, kraj, kategoria)
                VALUES (%s, %s, %s, 'nieokreślona')
                ON CONFLICT (lei) DO UPDATE SET nazwa = EXCLUDED.nazwa, kraj = EXCLUDED.kraj
            """, (lei, nazwa, kraj))
            print(f"  {lei}  ->  {nazwa} [{kraj}]")
            done += 1
        except Exception as e:
            print(f"  {lei}: BŁĄD {str(e)[:80]}")

    conn.commit()
    print(f"OK: uzupełniono {done}/{len(leis)} banków")
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
