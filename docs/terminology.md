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

## Validator

CLI:

```bash
python scripts/validate_terminology.py --config-dir config/terminology --format text
python scripts/validate_terminology.py --config-dir config/terminology --format json --strict
```

Validiert u. a.:

- YAML lesbar/strukturell gültig
- Pflichtfelder je Term
- eindeutige `id` und `canonical`
- Alias-Kollisionen zwischen Terms
- Referenzziele in Relationen (`target_term_id`, `target_id`, `target`)
- erlaubte Mengen für `term_class`, `annotate_policy`, `block_policy`
- erlaubte `applies_to` Source-Typen
- Warnungen für Personenterms mit aktiver Annotation und potenziell mehrdeutige Kurzformen (z. B. `PM`, `CI`, `PO`)

## Kandidaten-Review (CSV-first)

Datei: `reports/terminology_candidates.csv`

Spalten:

- `source_type`
- `term`
- `count`
- `first_seen_file`
- `example_context`
- `already_known`
- `suggested_action`
- `selected_term_id`
- `reviewer_status`
- `reviewer_note`

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

XLSX-Sheets:

1. `terms`
2. `aliases`
3. `relations`
4. `sources`
5. `candidates` (falls CSV vorhanden)

Eigenschaften:

- Header-Freeze, Autofilter, sinnvolle Spaltenbreite
- Deterministisches Schreiben nach YAML
- Dry-Run-Unterstützung und optionales Backup
- Vor dem finalen Schreiben Validierung der importierten Daten

## Neuen Begriff ergänzen

1. In `config/terminology/terms.yml` einen Eintrag unter `terms:` hinzufügen.
2. Pflichtfelder setzen: `id`, `canonical`, `label`, `description`, `term_class`.
3. `applies_to` auf relevante Sources begrenzen.
4. `annotate_policy` / `block_policy` setzen.
5. Für echte Schreibvarianten `aliases` verwenden.
6. Für fachlich verwandte Begriffe `relations` mit `type: related_to` nutzen.

## Relationen: alias vs abbreviation_of vs related_to

- `alias`: Praktisch gleichbedeutende Schreibvariante (z. B. `ISU` und `IS-U`).
- `abbreviation_of`: Abkürzung referenziert eine Vollform; keine automatische Gleichsetzung mit anderen Begriffen.
- `related_to`: Nur fachliche Verwandtschaft (z. B. `EDA` und `PONTON`), **kein Synonym**.

## Warum `scrape` standardmäßig deaktiviert ist

Scrape-Inhalte sind oft heterogen und enthalten viele zufällige Uppercase-Tokens. Dadurch steigt in V1 das Risiko für unerwünschte Annotationen und Kandidaten-Rauschen. Deshalb ist `scrape` in `sources.yml` auf `off` gesetzt.

## Source of Truth

YAML unter `config/terminology/` bleibt die Source of Truth. XLSX dient ausschließlich als Pflege- und Review-Hilfe.
