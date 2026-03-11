# Einheitliches Markdown-Frontmatter-Schema

Ziel: Ein gemeinsamer, stabiler Metadaten-Kern für alle Quellen (Website, Confluence, JIRA, Filesystem, Mail, ...), ohne übermäßig komplexes Modell.

## Design-Entscheidung für quellspezifische Felder

Quellspezifische Felder liegen gesammelt unter `source_meta` (statt viele Präfix-Felder auf Top-Level).

Warum pragmatisch:
- Top-Level bleibt schlank und stabil.
- Quelle-spezifische Details sind klar abgegrenzt.
- Neue Quellen können ergänzt werden, ohne den Kern aufzublähen.

## Feldkategorien

### 1) Kernfelder

**Pflichtfelder** (müssen für nutzbares, quellenübergreifendes Mapping gesetzt sein):
- `title`
- `source_type` (z. B. `external_website`, `confluence`, `jira`, `file`, `mail`)
- `source_system` (z. B. `confluence_dc`, `jira_dc`, `website`, `filesystem`)
- `source_key` (stabiler Schlüssel im Wissenssystem)

**Empfohlen**:
- `source_url`
- `original_id`
- `original_path`
- `updated_at`
- `imported_at`
- `status` (`raw`, `draft`, `reviewed`, `curated`)
- `visibility` (`internal`, `restricted`, `public`)
- `tags`, `authors`, `language`, `content_hash`

### 2) Struktur-/Ablagefelder (optional)
- `domain`, `scope`, `category`, `subcategory`, `customer`, `project`

### 3) Technische/Prozessfelder (optional)
- `ingestion_source`, `ingestion_job`, `version`, `attachments`, `aliases`

### 4) Quellspezifische Felder (optional)
- `source_meta: { ... }`

Beispiele:
- Confluence: `space_key`, `page_id`, `labels`
- JIRA: `jira_key`, `issue_type`, `fix_versions`
- Website: `source_domain`, `crawl_depth`, `content_type`

## Beispiel-Frontmatter

### Externe Website

```yaml
---
title: "Getting Started"
source_type: "external_website"
source_system: "website"
source_key: "docs-example-com"
source_url: "https://docs.example.com/guide/intro"
original_id: "https://docs.example.com/guide/intro"
original_path: "pages/guide/intro.md"
updated_at: "2026-03-11T10:15:00Z"
imported_at: "2026-03-11T10:45:00Z"
status: "raw"
visibility: "public"
tags:
  - "docs"
source_meta:
  source_domain: "docs.example.com"
  content_type: "documentation"
  crawl_depth: 2
---
```

### Confluence

```yaml
---
title: "Event Mesh Architektur"
source_type: "confluence"
source_system: "confluence_dc"
source_key: "confluence-wstw"
source_url: "https://confluence.example.local/display/RMTOC/Event+Mesh"
original_id: "123456"
status: "draft"
visibility: "internal"
tags:
  - "event-mesh"
  - "integration"
authors:
  - "Bernhard"
updated_at: "2026-03-11T10:15:00Z"
imported_at: "2026-03-11T10:45:00Z"
content_hash: "sha256:..."
source_meta:
  space_key: "RMTOC"
  page_id: 123456
  labels:
    - "event-mesh"
    - "integration"
---
```

### JIRA Issue / User Story

```yaml
---
title: "Als User möchte ich..."
source_type: "jira"
source_system: "jira_dc"
source_key: "jira-prews"
source_url: "https://jira.example.local/browse/PREWS-123"
original_id: "PREWS-123"
status: "reviewed"
visibility: "internal"
project: "prews"
source_meta:
  jira_key: "PREWS-123"
  issue_type: "Story"
  fix_versions:
    - "2026.03"
---
```

### Minimales generisches Markdown-Dokument

```yaml
---
title: "Notiz"
source_type: "file"
source_system: "filesystem"
source_key: "local-files"
---
```

## Python-Utilities

Zentrale Funktionen in `processing/frontmatter_schema.py`:

- `build_frontmatter(...)`: neues Frontmatter aufbauen (inkl. Normalisierung, `imported_at`-Default)
- `normalize_frontmatter(data)`: Typen und Feldstruktur vereinheitlichen
- `validate_frontmatter(data)`: leichte Validierung (liefert Fehlerliste)
- `merge_frontmatter(existing, updates)`: bestehendes Frontmatter aktualisieren, `source_meta` wird zusammengeführt
- `parse_frontmatter(markdown_text)`: YAML-Frontmatter + Body extrahieren
- `render_frontmatter(frontmatter, body_text)`: zurück in lesbares Markdown serialisieren

## Erweiterungsregel für neue Quellen

1. Zuerst Kernfelder befüllen.
2. Nur bei echtem Mehrwert neue Felder in `source_meta` hinzufügen.
3. Keine Duplikate zwischen Kern und `source_meta` anlegen.
4. Keine tief verschachtelten Strukturen.
