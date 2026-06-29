"""Orkiestracja całego pipeline'u (Prefect 3) — jedno polecenie odpala cały łańcuch.

Kroki (zależności):
    bronze_ingest (wczytaj nowe paczki z landing)
        -> silver_build (rozszyfrowanie: metryka + wymiary)
              -> silver_reconcile (DQ: fakt <-> komórka)
              -> gold_build (prezentacja: gold_cell)

Uruchomienie (na komputerze, w katalogu repo):  python pipeline.py
Prefect daje: kolejność, ponowienia przy błędzie (retry), logi każdego kroku.
Działa lokalnie (ephemeral) — nie wymaga serwera Prefect.
"""
from prefect import flow, task

# importujemy istniejące skrypty jako moduły (każdy ma main())
import bronze_ingest_csv
import silver_build
import silver_reconcile
import gold_build


@task(retries=2, retry_delay_seconds=10, log_prints=True)
def ingest_bronze():
    """Krok 1: wczytaj nowe paczki xBRL-CSV ze strefy lądowania (idempotentne)."""
    bronze_ingest_csv.main()


@task(retries=2, retry_delay_seconds=10, log_prints=True)
def build_silver():
    """Krok 2: przebuduj warstwę znaczeniową (silver_fact + silver_fact_dimension)."""
    silver_build.main()


@task(retries=2, retry_delay_seconds=10, log_prints=True)
def reconcile_silver():
    """Krok 3a: kontrola jakości — czy każdy fakt ma komórkę w definicji szablonu."""
    silver_reconcile.main()


@task(retries=2, retry_delay_seconds=10, log_prints=True)
def build_gold():
    """Krok 3b: przebuduj warstwę prezentacji (gold_cell)."""
    gold_build.main()


@flow(name="eba-pillar3-pipeline", log_prints=True)
def pipeline():
    # .submit() uruchamia zadanie; wait_for wymusza kolejność (zależności)
    b = ingest_bronze.submit()
    s = build_silver.submit(wait_for=[b])
    r = reconcile_silver.submit(wait_for=[s])
    g = build_gold.submit(wait_for=[s])
    # poczekaj na końcowe zadania, żeby flow zakończył się dopiero po wszystkim
    r.result()
    g.result()


if __name__ == "__main__":
    pipeline()
