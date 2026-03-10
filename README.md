# local-knowledge-app

`local-knowledge-app` ist der Ingestion-, Retrieval- und Antwortvorbereitungs-Teil eines lokalen Knowledge-Setups.
Die App lädt Markdown-Dateien aus einem separaten Daten-Repo, normalisiert Inhalte,
chunkt Texte und bietet lokale Suche, Ask-/Prompt-Aufbereitung sowie eine **optionale** LLM-Ausführung (Ollama).

## Pipeline (aktueller Stand)

Confluence-Export-Transform (optional)  
→ Markdown-Ingestion  
→ Frontmatter + Normalisierung  
→ Markdown-aware Chunking  
→ Chunk-Storage + Manifest/Processing-State  
→ Keyword Retrieval / Vector Retrieval / Hybrid Retrieval  
→ Ask-Pipeline (Kontextaufbau)  
→ Prompt-/Answer-Vorbereitung  
→ Optional: LLM-Ausführung via Ollama

## Funktionsumfang

### Confluence Transform (neu)
- Laden exportierter Confluence-Rohdaten aus `~/local-knowledge-data/exports/confluence`
- Transformation in ingestierbares Markdown mit YAML-Frontmatter
- MVP-Unterstützung für Makros, Tabellen, Links, Anhänge und Basis-HTML-Strukturen
- Key-Value-/Page-Properties-Tabellen werden konservativ erkannt, als Bulletliste gerendert und zusätzlich unter `page_properties` im Frontmatter ergänzt
- Inkrementeller Lauf mit:
  - `latest_transform_state.json`
  - `run_<run_id>.json`
  - `latest_transform_manifest.json`
- Standard-Output nach `~/local-knowledge-data/staging/confluence/<space_key>/...`

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
  - `citation_map` für Mapping `chunk_id -> citation index`

### Optionale LLM-Ausführung
- Schlanke LLM-Provider-Schicht (`llm/`)
- Aktuell implementierter Provider: **Ollama** (`/api/generate`, non-streaming)
- `AnswerExecutor` kombiniert bestehende `AnswerPipeline` mit einem LLM-Provider
- Antwortausgabe wird strukturiert formatiert via `CitationFormatter`:
  - Header `ANSWER`
  - Fließtext mit Inline-Zitationen `[1]`, `[2]`, ...
  - `Sources`-Block mit zugehörigen Quellentiteln
- Keine UI, keine Agenten, kein schweres Orchestrierungs-Framework

## Projektstruktur (grob)

- `common/` – Konfiguration und Logging
- `sources/` – Source-Modelle und Loader (Filesystem + Confluence Export)
- `processing/` – Normalisierung, Chunking, Confluence-Transform, State/Manifest, Output
- `retrieval/` – Chunk-Laden, Keyword-/Vector-/Hybrid-Suche, Kontext-/Prompt-/Answer-Pipelines
- `llm/` – Provider-Interface, Response-Modell und Ollama-Provider
- `scripts/` – ausführbare Skripte für Transform, Ingestion, Retrieval und Antwort-CLI
- `config/` – App-Konfiguration (`app.toml`)


## Antwortformat

Die finale Ausgabe von `scripts/answer.py` folgt einem konsistenten Zitationsschema:

```text
ANSWER

<Event Mesh explanation text mit [1], [2], ...>

Sources
[1] Event Mesh Architektur – Kyma Services
[2] Event Mesh Architektur – Event Topics
```

Damit sind In-Text-Zitationen und Quellenblock eindeutig verknüpft; zusätzlich steht im Payload ein `citation_map` (`chunk_id -> citation index`) für Weiterverarbeitung zur Verfügung.

## Beispielbefehle

```bash
python ./scripts/run_transform_confluence.py
python ./scripts/run_transform_confluence.py --space MYSPACE
python ./scripts/run_transform_confluence.py --full
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

### Beispielstruktur für Confluence-Export (MVP)

```text
~/local-knowledge-data/exports/confluence/
  MYSPACE/
    123456/
      page.json
    789012/
      content.raw.json
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
