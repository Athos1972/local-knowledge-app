# Terminologie-Komponente (V1)

Die Terminologie-Komponente verbessert die Konsistenz von Begriffen bei der Transformation von Quelldaten nach Markdown.

## Was die Komponente macht

- Lädt zentrale Terminologie-Konfiguration aus YAML unter `config/terminology/`.
- Arbeitet source-spezifisch (`confluence`, `jira`, `mail`, `teams`, `scrape`) statt global.
- Annotiert optional nur die **erste** Nennung eines Begriffs im Text.
- Fügt optional einen `## Terminologie`-Block am Dokumentende hinzu.
- Erzeugt optional Kandidaten für unbekannte Begriffe in `reports/terminology_candidates.csv`.
- Prüft Konfigurationsqualität via Validator (Errors/Warnings/Stats).
- Unterstützt XLSX-Export/Import als Pflegeformat bei weiterem YAML-Source-of-Truth.

## Maßgebliche Dateien

- `config/terminology/settings.yml` – globale Engine-Settings (Matching, Block-Schwelle, Kandidaten-Regex).
- `config/terminology/sources.yml` – Aktivierung und Modus pro Source-Type.
- `config/terminology/terms.yml` – Terminologie-Datenmodell mit Begriffen, Aliasen und Relationen.
- Dateinamen für Terminology-YAMLs können über `config/app.toml` überschrieben werden. Defaults bleiben `settings.yml`, `sources.yml`, `terms.yml` (optional auch `candidate_exclude.yml`).
- `config/terminology/candidate_exclude.yml` – Ignore-/Exclude-Liste für Kandidaten (`*` als Wildcard, case-insensitive).

## Validator

CLI:

```bash
python scripts/validate_terminology.py --config-dir config/terminology --format text
python scripts/validate_terminology.py --config-dir config/terminology --format json --strict
```

## Kandidaten-Review (CSV-first)

Datei: `reports/terminology_candidates.csv` (oder explizit via `config/app.toml` unter `[terminology] reports_dir`)

Die Candidate-Erzeugung ist für **Confluence und Jira** über `sources.yml` aktiviert (`candidates_enabled: true`).

Wichtig:

- Es gibt nur noch **einen** Schreibpfad: in-memory Aggregation pro Run und genau ein CSV-Write beim Finalize.
- Confluence- und Jira-Transform finalisieren den Report explizit am Run-Ende.
- Falls `candidates_enabled` in `sources.yml` fehlt, wird defensiv `mode != off` als Default verwendet.

### Aggregationslogik

- Kandidaten werden nicht mehr pro Dokument angehängt, sondern in-memory über den gesamten Run aggregiert.
- `reports/terminology_candidates.csv` wird erst beim expliziten Finalize am Run-Ende geschrieben (einmal pro Run, auch wenn 0 Seiten verarbeitet wurden).
- Aggregationsschlüssel: `(source_type, normalized(term))`.
- `normalized(term)` ist case-insensitive (intern lowercased + Whitespace-Normalisierung).
- Sichtbarer CSV-Wert `term` bleibt in der zuerst gesehenen Form erhalten.
- `count` enthält die aufsummierte Anzahl aller Treffer innerhalb derselben Aggregat-Zeile.

### Merge-Regeln bei bestehender CSV

Beim nächsten Lauf wird eine vorhandene CSV eingelesen und gemerged:

- `count` wird aufsummiert.
- `first_seen_file` bleibt bestehen (nur gesetzt, wenn leer).
- `last_seen_file` wird auf die zuletzt gesehene Quelle aktualisiert.
- `example_context` wird nur ergänzt, wenn noch leer.
- Review-Spalten bleiben unangetastet:
  - `already_known`
  - `suggested_action`
  - `selected_term_id`
  - `reviewer_status`
  - `reviewer_note`

Legacy-CSV-Format (z. B. ohne `last_seen_file`) wird defensiv eingelesen; beim nächsten Write entsteht automatisch das neue, vollständige Spaltenlayout.

### Logging / Diagnose

Beim Start (INFO):

- Terminology geladen / nicht geladen
- globales `candidate_detection_enabled`
- Source-Mode + `candidates_enabled` je Source
- absoluter Zielpfad des Candidate-Reports

Während des Laufs (DEBUG):

- Candidate-Erkennung pro Dokument ausgeführt ja/nein
- falls nein: expliziter Grund (`config_unavailable`, `terminology_global_disabled`, `source_mode_disabled`, `source_mode_candidates_disabled`, ...)
- pro Dokument: erkannte und ausgeschlossene Kandidaten

Am Ende (INFO):

- `docs_seen`
- `docs_detection_executed`
- `docs_with_candidates` / `docs_without_candidates`
- `unique_candidates`
- `aggregated_candidate_occurrences`
- `excluded_occurrences`
- finaler Report-Pfad

### Spalten

- `source_type`
- `term`
- `count`
- `first_seen_file`
- `last_seen_file`
- `example_context`
- `already_known`
- `suggested_action`
- `selected_term_id`
- `reviewer_status`
- `reviewer_note`

### Exclude-/Ignore-Liste

Konfigurationsdatei: `config/terminology/candidate_exclude.yml`

Beispiel:

```yaml
candidate_exclude:
  - INFO
  - API
  - URL
  - BSBX*
```

Regeln:

- Matching ist standardmäßig case-insensitive.
- `*` matcht beliebige Zeichenfolgen (z. B. `BSBX*` matcht `BSBX123` und `BSBX-TEST`).
- Excludes greifen **vor** Zählen und Schreiben.
- Ausgeschlossene Kandidaten landen nicht in der CSV.

CLI:

```bash
python scripts/review_terminology_candidates.py --config-dir config/terminology --candidates reports/terminology_candidates.csv
```

Das Skript reichert bestehende Kandidaten gegen bekannte Canonicals/Aliase an und setzt rudimentäre Empfehlungen (`new_term`, `add_alias`, `needs_review`).

## XLSX-Export / Import

Export:

```bash
python scripts/export_terminology_xlsx.py --config-dir config/terminology --reports-dir reports --output reports/terminology.xlsx
```

Import:

```bash
python scripts/import_terminology_xlsx.py --input reports/terminology.xlsx --config-dir config/terminology --dry-run
python scripts/import_terminology_xlsx.py --input reports/terminology.xlsx --config-dir config/terminology --backup
```

## Source of Truth

YAML unter `config/terminology/` bleibt die Source of Truth. XLSX dient ausschließlich als Pflege- und Review-Hilfe.
