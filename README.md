# local-knowledge-app

`local-knowledge-app` ist der Ingestion-Teil eines lokalen Knowledge-Setups.
Er lädt Markdown-Dateien aus einem separaten Daten-Repo, normalisiert Inhalte,
chunkt Texte und stellt lokalen Retrieval-Support bereit.

## Pipeline

Markdown
→ Chunking
→ Keyword Retrieval
→ Vector Retrieval
→ Hybrid Retrieval

## MVP-Funktionsumfang

- Laden von Markdown-Dateien aus dem Filesystem (`~/local-knowledge-data/domains`)
- Frontmatter-Parsing und Normalisierung in ein einheitliches Dokumentmodell
- Markdown-aware Chunking entlang von Überschriften (inkl. robustem Fallback)
- Schreiben von:
  - normalisierten Dokumenten
  - Metadaten
  - Chunk-JSONL
  - Run-Manifest und Processing-State für inkrementelle Läufe
- Lokale Keyword-Suche über `processed/chunks/*.jsonl`
- Lokale Vector-Suche über SQLite-Index (`index/vector_index.sqlite`)
- Hybrid-Suche mit kombinierter Keyword- und Vector-Bewertung

## Projektstruktur (grob)

- `common/` – Konfiguration und Logging
- `sources/` – Source-Modelle und Loader (aktuell Filesystem)
- `processing/` – Normalisierung, Chunking, State/Manifest, Output
- `retrieval/` – Chunk-Laden, Keyword-, Vector- und Hybrid-Suche
- `scripts/` – ausführbare Skripte für Ingestion und lokale CLI-Tools
- `config/` – App-Konfiguration (`app.toml`)

## Lokaler Start

```bash
python scripts/run_ingestion.py
python scripts/run_ingestion.py --full
```

## Retrieval ausführen

```bash
python scripts/build_vector_index.py
python scripts/search_chunks.py "event mesh kyma"
python scripts/search_chunks.py "event mesh kyma" --mode keyword
python scripts/search_chunks.py "event mesh kyma" --mode vector
python scripts/search_chunks.py "event mesh kyma" --mode hybrid --top-k 10
```

Hinweis: Ingestion und Suche erwarten das separate Daten-Repo unter
`~/local-knowledge-data`.
