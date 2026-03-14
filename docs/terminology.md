# Terminologie-Komponente (V1)

Die Terminologie-Komponente verbessert die Konsistenz von Begriffen bei der Transformation von Quelldaten nach Markdown.

## Was die Komponente macht

- Lädt zentrale Terminologie-Konfiguration aus YAML unter `config/terminology/`.
- Arbeitet source-spezifisch (`confluence`, `jira`, `mail`, `teams`, `scrape`) statt global.
- Annotiert optional nur die **erste** Nennung eines Begriffs im Text.
- Fügt optional einen `## Terminologie`-Block am Dokumentende hinzu.
- Erzeugt optional Kandidaten für unbekannte Begriffe in `reports/terminology_candidates.csv`.

## Konfigurationsdateien

- `config/terminology/settings.yml` – globale Engine-Settings (Matching, Block-Schwelle, Kandidaten-Regex).
- `config/terminology/sources.yml` – Aktivierung und Modus pro Source-Type.
- `config/terminology/terms.yml` – Terminologie-Datenmodell mit Begriffen, Aliasen und Relationen.

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
