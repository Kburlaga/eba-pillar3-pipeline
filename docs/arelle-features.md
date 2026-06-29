# Arelle — funkcje przydatne w projekcie

[Arelle](https://arelle.org/) to otwarty procesor XBRL. Poza walidacją (którą
wykorzystujemy w `validate_arelle.py`) udostępnia funkcje, które albo dublują to,
co zbudowaliśmy ręcznie (świetne do krzyżowej kontroli „dwie drogi — ten sam
wynik"), albo mogą rozszerzyć pipeline.

| Funkcja | Co robi | Wartość dla projektu | Status |
|---|---|---|---|
| **Walidacja formuł** | uruchamia asercje walidacyjne EBA z taksonomii na xBRL-CSV | rdzeń Etapu A walidacji | ✅ wdrożone (`validate_arelle.py`) |
| **Ekstrakcja faktów z OIM** (`saveLoadableOIM` / dump) | fakt → koncept + wymiary + jednostka + okres, rozwiązane z taksonomii | krzyżowa kontrola srebra (dp→metryka+wymiary z DPM vs Arelle) | ✅ zrobione (`crosscheck_arelle.py`) — wartości 1:1 |
| **Renderowanie tabel** (`saveHtmlEBAtables`) | oficjalny układ tabel EBA (wiersze/kolumny/etykiety/kody) | porównanie layoutu z `gold_render` | ✅ zrobione (layout zgodny; wartości w renderze niewstawiane — #1477) |
| **`xbrlDB` → PostgreSQL** | ładuje fakty do standardowego schematu XBRL (XBRL-US Public DB) | inny model składowania; nauka/porównanie z medallionem | rozważane |
| **Konwersja formatów** (Load/Save OIM) | xBRL-XML ↔ xBRL-CSV ↔ xBRL-JSON ↔ XLSX | ujednolicenie wczytywania (np. stare raporty XML) | rozważane |
| **Introspekcja taksonomii** (API ModelXbrl) | etykiety konceptów, wymiary, struktura tabel programowo | etykiety wprost z taksonomii zamiast `headerversion` z DPM | rozważane |
| **Tryb web service (REST API)** | walidacja/render jako usługa HTTP | mógłby zasilać dashboard / osobny serwis | później |
| **`xule` (język reguł)** | własne reguły/zapytania nad XBRL | niska — reużywamy reguły EBA, nie piszemy | pominięte |
| **Versioning report** | porównanie wersji taksonomii (4.1 vs 4.2) | nisza — przy zmianach frameworku | pominięte |

## Zrealizowane
1. ✅ **Ekstrakcja faktów (Arelle) → krzyżowa kontrola srebra** (`crosscheck_arelle.py`,
   tabela `silver_crosscheck`). Wynik: fakty + wartości numeryczne **1:1 dla wszystkich
   6 raportów**; wymiary zgodne dla 4.2, drobna różnica reprezentacji na 4.1 (prawdopodobnie
   wymiary domyślne). Dowód poprawności mapowania DPM.
2. ✅ **Render tabel Arelle (`saveHtmlEBAtables`) → porównanie z `gold_render`.** Arelle
   generuje oficjalny **układ** wszystkich tabel (wiersze/kolumny/etykiety/kody) — zgodny
   z naszym `gold_render` (ta sama taksonomia/table linkbase). Wartości w renderze Arelle
   nie są wstawiane w tej wersji (#1477), ale zostały zweryfikowane w pkt 1 (1:1).

## Źródła
- https://arelle.org/arelle/
- https://arelle.readthedocs.io/en/latest/plugins/popular/save_loadable_oim.html
- https://arelle.readthedocs.io/en/2.21.0/plugins/popular/load_from_oim.html
- https://github.com/Arelle/Arelle/tree/master/arelle/plugin/xbrlDB
