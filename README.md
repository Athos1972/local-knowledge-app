# local-knowledge-app

`local-knowledge-app` ist der Ingestion- und Retrieval-Teil eines lokalen Knowledge-Setups.
Die App lädt Markdown-Dateien aus einem separaten Daten-Repo, normalisiert Inhalte,
chunkt Texte und stellt lokale Such- sowie Ask-/Answer-Vorbereitungspipelines bereit.

## Pipeline (Stand jetzt)

Markdown-Ingestion
→ Frontmatter + Normalisierung
→ Markdown-aware Chunking
→ Chunk-Storage + Manifest/Processing-State
→ Keyword Retrieval / Vector Retrieval / Hybrid Retrieval
→ Ask-Pipeline (Kontextaufbau)
→ Answer-Vorbereitung (Prompt + Quellen, ohne LLM-Call)

## Funktionsumfang

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
- Ask-Pipeline zum Erzeugen eines strukturierten Kontextblocks
- Answer-Pipeline-Vorstufe zur Erstellung eines QA-Payloads:
  - Query
  - Trefferliste
  - Kontext
  - strukturierter Prompt
  - Quellenobjekte (source_number, doc_id, chunk_id, title, source_ref, score, optional section_header)

## Projektstruktur (grob)

- `common/` – Konfiguration und Logging
- `sources/` – Source-Modelle und Loader (aktuell Filesystem)
- `processing/` – Normalisierung, Chunking, State/Manifest, Output
- `retrieval/` – Chunk-Laden, Keyword-/Vector-/Hybrid-Suche, Kontext- und Prompt-Bausteine
- `scripts/` – ausführbare Skripte für Ingestion und lokale CLI-Tools
- `config/` – App-Konfiguration (`app.toml`)

## Beispiele

```bash
python ./scripts/run_ingestion.py
python ./scripts/build_vector_index.py
python ./scripts/search_chunks.py "event mesh"
python ./scripts/ask.py "event mesh kyma"
python ./scripts/prepare_answer.py "event mesh kyma"
```

Weitere Retrieval-Beispiele:

```bash
python ./scripts/search_chunks.py "event mesh kyma" --mode keyword
python ./scripts/search_chunks.py "event mesh kyma" --mode vector
python ./scripts/search_chunks.py "event mesh kyma" --mode hybrid --top-k 10
```

Hinweis: Ingestion und Suche erwarten das separate Daten-Repo unter
`~/local-knowledge-data`.

## Ask-Pipeline

`ask.py` kombiniert Hybrid-Retrieval mit `ContextBuilder` und gibt Query,
Top-Treffer und generierten Kontext aus. Es wird **kein** LLM aufgerufen.

## Answer-Vorbereitung (ohne LLM)

`prepare_answer.py` erweitert den Flow um:

- strukturierte Quellenliste für Zitierbarkeit/Debugging
- kompakten Prompt mit klaren QA-Instruktionen
- klares Ausgabeformat (`Antwort` + `Quellen`) für eine spätere LLM-Anbindung
- vollständiges Payload für eine spätere LLM-Integration

Auch hier wird **kein** LLM-Call durchgeführt.
