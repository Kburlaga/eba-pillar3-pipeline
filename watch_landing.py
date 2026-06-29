"""Watcher strefy lądowania — wrzucasz .zip do bronze/landing/, pipeline rusza SAM.

Jak działa:
  - obserwuje katalog bronze/landing/ (biblioteka watchdog)
  - gdy pojawi się nowy .zip, czeka chwilę aż kopiowanie się skończy (debounce),
    żeby nie złapać pliku w połowie
  - odpala cały flow Prefect (bronze -> silver -> reconcile -> gold)
  - wiele plików wrzuconych naraz = jeden przebieg (zlewa zdarzenia)

Uruchomienie (na komputerze, w katalogu repo):  python watch_landing.py
Zatrzymanie: Ctrl+C. Proces musi działać, żeby auto-przetwarzanie żyło.
"""
import os
import time
import threading

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from pipeline import pipeline

LANDING = os.path.join("bronze", "landing")
DEBOUNCE_S = 5          # sekundy ciszy po ostatnim zdarzeniu zanim ruszymy
_last_event = [0.0]     # znacznik ostatniego zdarzenia
_lock = threading.Lock()


class ZipHandler(FileSystemEventHandler):
    """Reaguje tylko na pliki .zip (utworzone lub przeniesione do katalogu)."""

    def _maybe(self, path: str):
        if path.lower().endswith(".zip"):
            print(f"[watcher] wykryto zmianę: {os.path.basename(path)}")
            with _lock:
                _last_event[0] = time.time()

    def on_created(self, event):
        if not event.is_directory:
            self._maybe(event.src_path)

    def on_moved(self, event):
        if not event.is_directory:
            self._maybe(event.dest_path)


def runner():
    """Pętla: po ucichnięciu zdarzeń (debounce) odpala pipeline raz."""
    while True:
        time.sleep(1)
        with _lock:
            t = _last_event[0]
        if t and (time.time() - t) >= DEBOUNCE_S:
            with _lock:
                _last_event[0] = 0.0       # skonsumowane
            print("\n[watcher] nowe pliki ustabilizowane — uruchamiam pipeline...\n")
            try:
                pipeline()
                print("\n[watcher] pipeline zakończony. Czekam na kolejne pliki...\n")
            except Exception as e:
                print(f"\n[watcher] BŁĄD pipeline'u: {e}\n(czekam dalej)\n")


def main():
    os.makedirs(LANDING, exist_ok=True)
    print(f"[watcher] obserwuję: {os.path.abspath(LANDING)}")
    print("[watcher] wrzuć tu .zip — pipeline ruszy sam. Ctrl+C aby zakończyć.\n")

    # wątek odpalający pipeline (żeby obserwator nie był blokowany podczas przetwarzania)
    threading.Thread(target=runner, daemon=True).start()

    obs = Observer()
    obs.schedule(ZipHandler(), LANDING, recursive=False)
    obs.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[watcher] zatrzymano.")
        obs.stop()
    obs.join()


if __name__ == "__main__":
    main()
