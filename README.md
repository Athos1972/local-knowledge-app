# local-knowledge-app

`local-knowledge-app` ist der Ingestion-Teil eines lokalen Knowledge-Setups.
Er lädt Markdown-Dateien aus einem separaten Daten-Repo, normalisiert Inhalte,
chunkt Texte und schreibt verarbeitete Artefakte plus Lauf-Metadaten.

## MVP-Funktionsumfang

- Laden von Markdown-Dateien aus dem Filesystem (`~/local-knowledge-data/domains`)
- Frontmatter-Parsing und Normalisierung in ein einheitliches Dokumentmodell
- Einfaches, deterministisches Chunking für spätere Retrieval-Schritte
- Schreiben von:
  - normalisierten Dokumenten
  - Metadaten
  - Chunk-JSONL
  - Run-Manifest und Processing-State für inkrementelle Läufe

## Projektstruktur (grob)

- `common/` – Konfiguration und Logging
- `sources/` – Source-Modelle und Loader (aktuell Filesystem)
- `processing/` – Normalisierung, Chunking, State/Manifest, Output
- `scripts/` – ausführbare Skripte für Ingestion und lokale Smoke-Tests
- `config/` – App-Konfiguration (`app.toml`)

## Lokaler Start

```bash
python ./scripts/run_ingestion.py
python ./scripts/run_ingestion.py --full
```

Hinweis: Die Ingestion erwartet das separate Daten-Repo unter
`~/local-knowledge-data`.
