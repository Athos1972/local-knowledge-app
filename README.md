# local-knowledge-app

`local-knowledge-app` ist der Ingestion-, Retrieval- und Antwortvorbereitungs-Teil eines lokalen Knowledge-Setups.
Die App lädt Markdown-Dateien aus einem separaten Daten-Repo, normalisiert Inhalte,
chunkt Texte und bietet lokale Suche, Ask-/Prompt-Aufbereitung sowie eine **optionale** LLM-Ausführung (Ollama).

## Pipeline (aktueller Stand)

Markdown-Ingestion  
→ Frontmatter + Normalisierung  
→ Markdown-aware Chunking  
→ Chunk-Storage + Manifest/Processing-State  
→ Keyword Retrieval / Vector Retrieval / Hybrid Retrieval  
→ Ask-Pipeline (Kontextaufbau)  
→ Prompt-/Answer-Vorbereitung  
→ Optional: LLM-Ausführung via Ollama

## Funktionsumfang

### Ingestion
- Laden von Markdown-Dateien aus dem Filesystem (`~/local-knowledge-data/domains`)
- Frontmatter-Parsing und Normalisierung in ein einheitliches Dokumentmodell
- Markdown-aware Chunking entlang von Überschriften (inkl. robustem Fallback)
- Schreiben von:
  - normalisierten Dokumenten
  - Metadaten
  - Chunk-JSONL
  - Run-Manifest und Processing-State für inkrementelle Läufe

### Retrieval
- Lokale Keyword-Suche über `processed/chunks/*.jsonl`
- Lokale Vector-Suche über SQLite-Index (`index/vector_index.sqlite`)
- Hybrid-Suche mit kombinierter Keyword- und Vector-Bewertung

### Ask / Prompt / Answer Preparation
- Ask-Pipeline zum Erzeugen eines strukturierten Kontextblocks
- Answer-Pipeline zur Erstellung eines QA-Payloads:
  - Query
  - Trefferliste
  - Kontext
  - strukturierter Prompt
  - Quellenobjekte (`source_number`, `doc_id`, `chunk_id`, `title`, `source_ref`, `score`, optional `section_header`)

### Optionale LLM-Ausführung
- Schlanke LLM-Provider-Schicht (`llm/`)
- Aktuell implementierter Provider: **Ollama** (`/api/generate`, non-streaming)
- `AnswerExecutor` kombiniert bestehende `AnswerPipeline` mit einem LLM-Provider
- Keine UI, keine Agenten, kein schweres Orchestrierungs-Framework

## Projektstruktur (grob)

- `common/` – Konfiguration und Logging
- `sources/` – Source-Modelle und Loader (aktuell Filesystem)
- `processing/` – Normalisierung, Chunking, State/Manifest, Output
- `retrieval/` – Chunk-Laden, Keyword-/Vector-/Hybrid-Suche, Kontext-/Prompt-/Answer-Pipelines
- `llm/` – Provider-Interface, Response-Modell und Ollama-Provider
- `scripts/` – ausführbare Skripte für Ingestion, Retrieval und Antwort-CLI
- `config/` – App-Konfiguration (`app.toml`)

## Beispielbefehle

```bash
python ./scripts/run_ingestion.py
python ./scripts/build_vector_index.py
python ./scripts/search_chunks.py "event mesh"
python ./scripts/ask.py "event mesh kyma"
python ./scripts/prepare_answer.py "event mesh kyma"
python ./scripts/answer.py "event mesh kyma" --provider ollama --model llama3.1:8b
```

Weitere Retrieval-Beispiele:

```bash
python ./scripts/search_chunks.py "event mesh kyma" --mode keyword
python ./scripts/search_chunks.py "event mesh kyma" --mode vector
python ./scripts/search_chunks.py "event mesh kyma" --mode hybrid --top-k 10
```

Hinweis: Ingestion und Suche erwarten das separate Daten-Repo unter
`~/local-knowledge-data`.

## Lokale Ollama-Nutzung

Für `scripts/answer.py` muss lokal ein Ollama-Server laufen, z. B.:

```bash
ollama serve
ollama run llama3.1:8b
```

Standard-Endpunkt ist `http://localhost:11434`.
Falls Ollama nicht erreichbar ist, liefert das Script eine klare Fehlermeldung mit Exit-Code ungleich 0.
