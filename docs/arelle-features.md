# Arelle — funkcje przydatne w projekcie

[Arelle](https://arelle.org/) to otwarty procesor XBRL. Poza walidacją (którą
wykorzystujemy w `validate_arelle.py`) udostępnia funkcje, które albo dublują to,
co zbudowaliśmy ręcznie (świetne do krzyżowej kontroli „dwie drogi — ten sam
wynik"), albo mogą rozszerzyć pipeline.

| Funkcja | Co robi | Wartość dla projektu | Status |
|---|---|---|---|
| **Walidacja formuł** | uruchamia asercje walidacyjne EBA z taksonomii na xBRL-CSV | rdzeń Etapu A walidacji | ✅ wdrożone (`validate_arelle.py`) |
| **Ekstrakcja faktów z OIM** (`saveLoadableOIM` / dump) | fakt → koncept + wymiary + jednostka + okres, rozwiązane z taksonomii | krzyżowa kontrola srebra (dp→metryka+wymiary z DPM vs Arelle) | 🔜 wybrane (pkt 1) |
| **Renderowanie tabel** (table linkbase → HTML) | rysuje oficjalne tabele EBA (wiersze/kolumny/etykiety) z instancji | porównanie z naszym `gold_render`/`gold_cell` | 🔜 wybrane (pkt 2) |
| **`xbrlDB` → PostgreSQL** | ładuje fakty do standardowego schematu XBRL (XBRL-US Public DB) | inny model składowania; nauka/porównanie z medallionem | rozważane |
| **Konwersja formatów** (Load/Save OIM) | xBRL-XML ↔ xBRL-CSV ↔ xBRL-JSON ↔ XLSX | ujednolicenie wczytywania (np. stare raporty XML) | rozważane |
| **Introspekcja taksonomii** (API ModelXbrl) | etykiety konceptów, wymiary, struktura tabel programowo | etykiety wprost z taksonomii zamiast `headerversion` z DPM | rozważane |
| **Tryb web service (REST API)** | walidacja/render jako usługa HTTP | mógłby zasilać dashboard / osobny serwis | później |
| **`xule` (język reguł)** | własne reguły/zapytania nad XBRL | niska — reużywamy reguły EBA, nie piszemy | pominięte |
| **Versioning report** | porównanie wersji taksonomii (4.1 vs 4.2) | nisza — przy zmianach frameworku | pominięte |

## Wybrane do realizacji
1. **Ekstrakcja faktów z wymiarami (Arelle) → krzyżowa kontrola srebra.** Porównać
   nasze `silver_fact` + `silver_fact_dimension` (z DPM) z faktami rozwiązanymi
   przez Arelle z taksonomii. Wykrywa ewentualne błędy mapowania.
2. **Render tabel Arelle → porównanie z `gold_render`.** Sprawdzić, czy nasza
   rekonstrukcja ujawnień = oficjalny layout EBA.

## Źródła
- https://arelle.org/arelle/
- https://arelle.readthedocs.io/en/latest/plugins/popular/save_loadable_oim.html
- https://arelle.readthedocs.io/en/2.21.0/plugins/popular/load_from_oim.html
- https://github.com/Arelle/Arelle/tree/master/arelle/plugin/xbrlDB
