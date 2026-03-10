# local-knowledge-app

`local-knowledge-app` ist der Ingestion-Teil eines lokalen Knowledge-Setups.
Er lädt Markdown-Dateien aus einem separaten Daten-Repo, normalisiert Inhalte,
chunkt Texte und stellt einen ersten lokalen Retrieval-MVP bereit.

## MVP-Funktionsumfang

- Laden von Markdown-Dateien aus dem Filesystem (`~/local-knowledge-data/domains`)
- Frontmatter-Parsing und Normalisierung in ein einheitliches Dokumentmodell
- Markdown-aware Chunking entlang von Überschriften (inkl. robustem Fallback)
- Schreiben von:
  - normalisierten Dokumenten
  - Metadaten
  - Chunk-JSONL
  - Run-Manifest und Processing-State für inkrementelle Läufe
- Lokale Keyword-Suche über `processed/chunks/*.jsonl` (ohne Embeddings/Vector DB)

## Projektstruktur (grob)

- `common/` – Konfiguration und Logging
- `sources/` – Source-Modelle und Loader (aktuell Filesystem)
- `processing/` – Normalisierung, Chunking, State/Manifest, Output
- `retrieval/` – Laden von Chunks + lokale Keyword-Suche
- `scripts/` – ausführbare Skripte für Ingestion und lokale CLI-Tools
- `config/` – App-Konfiguration (`app.toml`)

## Lokaler Start

```bash
python ./scripts/run_ingestion.py
python ./scripts/run_ingestion.py --full
```

## Retrieval-MVP ausführen

```bash
python ./scripts/search_chunks.py "event mesh"
python ./scripts/search_chunks.py "event mesh kyma" --top-k 10
python ./scripts/search_chunks.py "event mesh" --root ~/local-knowledge-data
```

Hinweis: Die Ingestion und die Suche erwarten das separate Daten-Repo unter
`~/local-knowledge-data`.
