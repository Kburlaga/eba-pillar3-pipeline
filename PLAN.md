# 🏦 EBA Pillar 3 Data Pipeline — Plan Projektu

> **Projekt edukacyjny:** Data pipeline do pobierania, walidacji i analizy ujawnień
> Filaru III (dyscyplina rynkowa) banków Unii Europejskiej.
>
> **Data rozpoczęcia:** 2026-06-26

---

## 🎯 Cel projektu

Stworzenie end-to-end data pipeline'u który:

1. **Pobiera** sprawozdania Filaru III banków UE (XBRL z EBA, PDF z banków)
2. **Waliduje** kompletność i spójność danych wg taksonomii EBA
3. **Ładuje** do relacyjnej bazy danych
4. **Analizuje** — porównuje wskaźniki między bankami, śledzi trendy
5. **Wizualizuje** wyniki na dashboardzie

### Kontekst domenowy (dlaczego ten projekt)

- **Krzysztof** pracował w sprawozdawczości regulacyjnej banków (taksonomie XBRL, modelowanie danych, SQL)
- To **projekt bliski mu domenowo** — od razu rozumie dane, może skupić się na nauce pipeline'u
- **Jest to projekt startowy** — po jego ukończeniu będziemy go komplikować (nowe źródła, streaming)
  lub rozpocząć kolejne projekty dodające nowe funkcjonalności data engineering

---

## 📐 Architektura warstwowa (Medallion)

```
┌─────────────────────────────────────────────────────┐
│ BRONZE — surowe dane                                 │
│  • Pobranie XBRL z API EBA                          │
│  • Pobranie PDF ze stron banków                     │
│  • Zapis "as-is" — dokładnie jak w źródle           │
├─────────────────────────────────────────────────────┤
│ SILVER — zwalidowane, ustandaryzowane                │
│  • Walidacja kompletności (czy wszystkie szablony?)  │
│  • Walidacja spójności (reguły EBA)                 │
│  • Normalizacja jednostek (PLN→EUR, tys→jedn)      │
│  • Wykrywanie outlierów                             │
│  • Rekoncyliacja PDF vs XBRL                        │
│  • Mapowanie wersji taksonomii                      │
├─────────────────────────────────────────────────────┤
│ GOLD — agregacje analityczne                         │
│  • Wskaźniki: CET1, LCR, NSFR, dźwignia            │
│  • Porównania między bankami                        │
│  • Trendy w czasie                                  │
│  • Benchmark vs. średnia sektorowa                  │
└─────────────────────────────────────────────────────┘
```

---

## 🛠️ Stack technologiczny (100% open source / darmowy)

| Warstwa | Narzędzie | Dlaczego |
|---|---|---|
| **Baza danych** | PostgreSQL | Relacyjna, wspiera JSON, idealna do danych analitycznych |
| **Backend / ETL** | Python 3.10+ | Główny język pipeline'u |
| **Ekstrakcja PDF** | `camelot-py`, `tabula-py` | Wyciąganie tabel z PDF |
| **Ekstrakcja XLSX/CSV** | `pandas`, `openpyxl` | Standard |
| **Ekstrakcja XBRL** | `arelle` | Open source XBRL processor |
| **Transformacje** | `pandas`, `pydantic` | Czyszczenie, mapowanie, walidacja |
| **Orkiestracja** | **Prefect** (open source) | Planowanie, retry, monitoring |
| **Dashboard** | **Streamlit** | Szybka wizualizacja bez frontendu |
| **Konteneryzacja** | Docker + Docker Compose | Uruchomienie jednym poleceniem |

---

## 🗄️ Model danych (oparty na taksonomii EBA)

```sql
-- Master data
bank (id, lei, nazwa, kraj, kategoria, url_disclosures)
reporting_period (id, okres, data_od, data_do, status)
eba_template (id, template_code, nazwa, wersja_taksonomii, kategoria_banku)

-- Raporty i dane
report (id, bank_id, period_id, data_publikacji, status, source_type)
  └── disclosure_table (id, report_id, template_id, nazwa_tabeli)
       └── disclosure_data_point (id, table_id, row_code, column_code, wartość, jednostka)

-- Walidacja
validation_rule (id, template_id, nazwa, regula, typ)
validation_result (id, report_id, rule_id, passed, wartość_oczekiwana, wartość_rzeczywista)
```

> **Analogia dla Krzysztofa:** To jest jak tworzenie taksonomii XBRL w SQL — encje odpowiadają
> elementom schematu EBA, relacje odzwierciedlają hierarchię raportowania.

---

## 📋 Plan realizacji (8 faz)

### Faza 0: Setup projektu
- [x] Utworzenie katalogu `eba-pillar3-pipeline`
- [ ] Inicjalizacja repozytorium Git
- [ ] `docker-compose.yml` (PostgreSQL + Prefect + Streamlit)
- [ ] `requirements.txt`
- [ ] Struktura katalogów (bronze/, silver/, gold/)
- [ ] Plik `PLAN.md` (ten dokument)

**Czego się nauczysz:** Infrastruktura kontenerowa, struktura projektu data pipeline

---

### Faza 1: Master Data — taksonomia i spis banków
- [ ] Pobranie taksonomii EBA (lista szablonów, datapointów)
- [ ] Utworzenie spisu banków raportujących (LEI, nazwa, kraj, URL)
- [ ] Mapowanie szablonów EBA na tabele w bazie
- [ ] Definicja reguł walidacyjnych EBA w SQL
- [ ] Inicjalizacja schematu bazy danych (`init.sql`)

**Czego się nauczysz:** Modelowanie danych regulacyjnych, praca z dokumentacją EBA, data governance

---

### Faza 2: Bronze — pobieranie danych
- [ ] Pobieranie XBRL z API EBA dla wybranych banków
- [ ] Zapis surowych plików XBRL i PDF do katalogu `bronze/`
- [ ] Rejestracja pobrania w bazie (report, status)
- [ ] Obsługa błędów pobierania (bank nie opublikował, timeout)

**Czego się nauczysz:** Praca z API, obsługa XBRL, error handling w pipeline

---

### Faza 3: Silver — walidacja i normalizacja
- [ ] Parsowanie XBRL → ekstrakcja datapointów do bazy
- [ ] Walidacja kompletności (sprawdzenie czy bank zaraportował wszystkie wymagane szablony)
- [ ] Walidacja spójności (reguły EBA: sumy cząstkowe = suma całkowita, aktywa = pasywa)
- [ ] Wykrywanie i normalizacja jednostek (tysiące → jednostki, różne waluty)
- [ ] Identyfikacja i oznaczanie brakujących datapointów

**Czego się nauczysz:** Data quality framework, business rules, reguły walidacyjne

---

### Faza 4: Silver — outliery i rekoncyliacja
- [ ] Wykrywanie outlierów (>3σ od mediany sektorowej)
- [ ] Rekoncyliacja PDF vs XBRL (jeśli bank publikuje oba formaty)
- [ ] Mapowanie między wersjami taksonomii (v3.2 ↔ v3.4)
- [ ] Generowanie raportu walidacyjnego (które banki przeszły, które nie)

**Czego się nauczysz:** Anomaly detection, data reconciliation, versioning

---

### Faza 5: Gold — agregacje analityczne
- [ ] Obliczanie kluczowych wskaźników: CET1 ratio, LCR, NSFR, dźwignia
- [ ] Agregacje wg kraju, kategorii banku, okresu
- [ ] Trendy czasowe (czy sektor się dokapitalizowuje?)
- [ ] Benchmark: bank X vs. średnia sektorowa
- [ ] Zapis widoków analitycznych w PostgreSQL (materialized views)

**Czego się nauczysz:** SQL analityczny, wskaźniki regulacyjne, analiza trendów

---

### Faza 6: Orkiestracja (Prefect)
- [ ] Definicja flow Prefect dla całego pipeline'u
- [ ] Harmonogram (banki publikują kwartalnie)
- [ ] Retry policy dla błędów
- [ ] Logowanie każdego kroku
- [ ] Dashboard Prefect z historią uruchomień

**Czego się nauczysz:** Orkiestracja procesów, scheduling, monitoring pipeline'u

---

### Faza 7: Dashboard (Streamlit)
- [ ] Strona główna: przegląd sektora (średnie wskaźniki, mapa)
- [ ] Widok banku: szczegóły, trend, porównanie do sektora
- [ ] Widok walidacji: które banki przeszły/nie przeszły
- [ ] Widok jakości danych: kompletność, outliery
- [ ] Eksport do CSV/XLSX

**Czego się nauczysz:** Wizualizacja danych, dashboarding, komunikacja wyników

---

## 🔮 Co dalej — ścieżka rozwoju

To jest **projekt startowy**. Po jego ukończeniu:

### Opcja A: Komplikujemy ten pipeline
- Dodanie danych z historycznych PDF (starsze raporty, przed XBRL)
- Dodanie web scrapingu dla banków które nie używają API EBA
- Streaming danych (Kafka/Redpanda) zamiast batch
- Data quality checks z użyciem Great Expectations
- Własny model ML do przewidywania trendów wskaźników

### Opcja B: Nowe projekty rozszerzające
- **Pipeline dla FINREP/COREP** — bardziej złożone raportowanie (więcej tabel, inne reguły)
- **Data catalog** — Amundsen/DataHub do katalogowania danych
- **Real-time monitoring** — monitorowanie zmian w danych banków w czasie rzeczywistym

---

## 👤 Kontekst użytkownika

- **Krzysztof Burłaga** — domain expert (sprawozdawczość regulacyjna, XBRL, SQL, modelowanie danych)
- **Nie jest programistą** — uczy się data engineering przez realizację projektów
- **Model współpracy:** Krzysztof = decyzje funkcjonalne + logika biznesowa, Cline = implementacja + wyjaśnienia
- **Cel:** Zrozumieć data pipeline na poziomie technicznym menedżera danych

---

> **Ostatnia aktualizacja:** 2026-06-26