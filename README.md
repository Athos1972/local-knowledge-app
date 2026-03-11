# local-knowledge-app

`local-knowledge-app` ist der Ingestion-, Retrieval- und Antwortvorbereitungs-Teil eines lokalen Knowledge-Setups.
Die App lädt Markdown-Dateien aus einem separaten Daten-Repo, normalisiert Inhalte,
chunkt Texte und bietet lokale Suche, Ask-/Prompt-Aufbereitung sowie eine **optionale** LLM-Ausführung.

## Offline-first Zielbild (neu)

Die Runtime ist jetzt standardmäßig vollständig lokal über **Ollama**:

- Antworten über Ollama (`/api/generate`) auf `http://localhost:11434`
- Embeddings ebenfalls über Ollama (`/api/embed`)
- Standardmodelle:
  - LLM: `llama3.1:8b`
  - Embeddings: `nomic-embed-text`
- Legacy-Hugging-Face/sentence-transformers ist nur noch optional (explizit aktivierbar)

> **Migration-Hinweis:** Bestehende Vektorindizes müssen nach der Umstellung neu gebaut werden,
> da Embeddings verschiedener Modelle/Provider nicht kompatibel sind.

## Konfiguration

Konfiguration wird aus `config/app.toml` gelesen, ENV-Variablen überschreiben TOML-Werte.

### Relevante ENV-Variablen

- `OLLAMA_BASE_URL` (Default: `http://localhost:11434`)
- `OLLAMA_CHAT_MODEL` (Default: `llama3.1:8b`)
- `OLLAMA_EMBED_MODEL` (Default: `nomic-embed-text`)
- `EMBEDDING_PROVIDER` (`ollama` oder `sentence_transformers`, Default: `ollama`)

### app.toml Defaults

```toml
[ollama]
base_url = "http://localhost:11434"
chat_model = "llama3.1:8b"
embed_model = "nomic-embed-text"

[embeddings]
provider = "ollama"
```

## Lokales Setup mit Ollama

1. Ollama installieren (siehe offizielle Ollama-Dokumentation).
2. Server starten:

```bash
ollama serve
```

3. Modelle laden:

```bash
ollama pull llama3.1:8b
ollama pull nomic-embed-text
# optional
ollama pull bge-m3
```

## Pipeline (kurz)

Confluence-Transform (optional) → Publish → Ingestion → Chunking → Vector-Index → Retrieval (Keyword/Vector/Hybrid) → Prompt → optionale LLM-Antwort.

## Wichtige Befehle

```bash
python ./scripts/run_ingestion.py
python ./scripts/build_vector_index.py
python ./scripts/answer.py "event mesh kyma"
```

Mit expliziter Embedding-Konfiguration:

```bash
python ./scripts/build_vector_index.py \
  --embedding-provider ollama \
  --embedding-model nomic-embed-text \
  --ollama-url http://localhost:11434

python ./scripts/answer.py "event mesh kyma" \
  --model llama3.1:8b \
  --base-url http://localhost:11434 \
  --embedding-provider ollama \
  --embedding-model nomic-embed-text \
  --ollama-url http://localhost:11434
```

## Häufige Fehler

### 1) `Connection refused` auf `localhost:11434`

Ursache: Ollama läuft nicht.

Lösung:

```bash
ollama serve
```

### 2) Modell nicht vorhanden

Typische Meldung: Modell wurde nicht gefunden.

Lösung:

```bash
ollama pull llama3.1:8b
ollama pull nomic-embed-text
```

### 3) Index wurde mit anderem Embedding-Modell gebaut

Typische Meldung:

> „Der Vektorindex wurde mit Modell X erstellt, die Anfrage verwendet aber Modell Y. Bitte Index neu bauen.”

Lösung: Index neu aufbauen (ggf. mit `--rebuild`).

## Legacy-HF-Pfad (optional)

Der sentence-transformers-Pfad bleibt nur für Migrationen erhalten und ist **nicht Standard**.
Aktivierung nur explizit über `EMBEDDING_PROVIDER=sentence_transformers` oder CLI-Flag `--embedding-provider sentence_transformers`.

Optionales Extra installieren:

```bash
pip install .[legacy-hf]
```


## Einheitliches Frontmatter-Schema

Für quellenübergreifende Markdown-Metadaten (Website, Confluence, JIRA, Filesystem, ...) gibt es ein einheitliches Schema und zentrale Utilities in `processing/frontmatter_schema.py`.

Details und Beispiele: `docs/frontmatter_schema.md`.

## scrape2md-Export Import (Transfer-Stufe)

Für die nachgelagerte Überführung von `scrape2md`-Exporten in die lokale Domainstruktur gibt es ein separates Script:

```bash
python scripts/import_scrape2md_export.py --config config/import_scrape2md_example.toml
```

Optional können Werte per CLI übersteuert werden:

```bash
python scripts/import_scrape2md_export.py \
  --config config/import_scrape2md_example.toml \
  --export-root /data/exports/docs.example.com \
  --knowledge-root /data/local-knowledge \
  --target-subpath domains/external/docs-example-com \
  --dry-run
```

Das Tool übernimmt bewusst **kein Crawling** und **keine HTML→Markdown-Konvertierung**. Es importiert Markdown-Dateien aus `pages/`, nutzt Metadaten aus `manifest.json`, setzt/aktualisiert optional Frontmatter und schreibt die Dateien in die konfigurierte Zielstruktur.

## Scraping-Asset Transformationspipeline (neu)

Für bereits gescrapte Dateien unter `exports/scraping/...` gibt es nun einen getrennten, manifestgetriebenen Zwei-Stufen-Flow:

1. **Transformation**: `exports/scraping/...` → `staging/transformed/scraping/...`
2. **Domain-Mapping**: `staging/transformed/...` → `domains/...`

Damit bleiben technische Konvertierung und fachliche Zuordnung strikt entkoppelt.

### 1) Transformation aus `exports/scraping`

```bash
python scripts/run_transform_scraping_exports.py \
  --input-root exports/scraping \
  --output-root staging/transformed \
  --changed-only
```

Optionen:
- `--dry-run`: nur planen, nichts schreiben
- `--limit N`: max. Anzahl verarbeiteter unterstützter Dateien
- `--force`: Artefakte auch bei bestehendem Stand neu schreiben
- `--changed-only`: nur transformieren, wenn Quelle neuer als Zielartefakte ist

Unterstützte MVP-Formate (MarkItDown-Adapter):
- `.pdf`, `.docx`, `.pptx`, `.xlsx`, `.xls`
- `.html`, `.htm`, `.csv`, `.json`, `.xml`, `.epub`

Bewusste MVP-Grenzen:
- keine ZIP-Rekursion
- kein OCR/Bildpfad
- keine Audio-/YouTube-/LLM-Konvertierung

Pro Quelldatei entstehen:
- `<name>.md`
- `<name>.meta.json`

Zusätzlich wird ein Run-Manifest geschrieben (`manifest_*.json`, `manifest.latest.json`).

### 2) Mapping nach `domains/...`

```bash
python scripts/run_map_transformed_to_domains.py \
  --transformed-root staging/transformed \
  --domains-root domains \
  --config config/scraping_domain_mapping.toml
```

Regeln sind in TOML konfigurierbar (Pfadpräfix, Teilstring, Dateiname, Fallback).
Die Mapping-Stufe ergänzt Domain-Metadaten, behält aber technische Transform-Metadaten bei.

Beispielkonfiguration: `config/scraping_domain_mapping.toml`.
