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
