# Confluence Transformer

Dieser Bereich enthält die Transformation von Confluence-Exportseiten nach Markdown.

## Aufbau

- `transformer.py`: Orchestrierung der Transformationsschritte pro Seite.
- `macro_transformer.py`: Auflösung/Entfernung bekannter Makros.
- `table_transformer.py`: Extraktion und Klassifikation von Tabellen.
- `page_properties.py`: Regeln für Seiteneigenschaften und Frontmatter-Promotion.
- `markdown_renderer.py`: Endgültiges Markdown inkl. Frontmatter.
- `writer.py`: Ausgabe von Hauptdokumenten und ausgelagerten Tabellen.

## Erweiterungsmuster

1. **Neues Makro hinzufügen**
   - In `MacroTransformer._transform_known_macros` einen dedizierten Schritt ergänzen.
   - Unknown-Makros bleiben durch `_unwrap_unsupported_macros` weiterhin sichtbar und auditierbar.

2. **Neue Seiteneigenschaft promoten**
   - In `config/app.toml` unter `[confluence_transform].page_properties_frontmatter_keys` ergänzen.
   - Falls Alias/Typ speziell ist: `DEFAULT_PROPERTY_PROMOTION` in `page_properties.py` erweitern.

3. **Spezielle Tabellenbehandlung ergänzen**
   - In `TableTransformer._render_table` neue Klassifikationsregel vor generischer Markdown-Konvertierung einfügen.

4. **Container-Makros ohne Eigenwert entpacken**
   - Makros wie `section`, `column`, `multiexcerpt`, `macrosuite-panel`, `macrosuite-cards`, `classifications-combined-taxonomy` werden als Hülle entfernt und ihr `rich-text-body` weiterverarbeitet.

## Konfiguration

Aus `config/app.toml`:

- `minimum_number_of_raw_characters_in_page`: Seiten unterhalb dieser Rohzeichenanzahl werden übersprungen.
- `page_properties_frontmatter_keys`: alphabetisch sortierte Whitelist der zu promotenden Seiteneigenschaften.

## Designprinzipien

- Kleine, fokussierte Methoden mit klaren Verantwortlichkeiten.
- Pattern-basierte Erweiterung statt monolithischer Sonderlogik.
- Konservative Extraktion: lieber stabiler Fallback als aggressive Vermutung.


## Task-Behandlung (Open vs Completed)

Confluence-Tasks werden nicht pauschal entfernt. Stattdessen werden sie strukturiert extrahiert, klassifiziert und als eigene Abschnitte gerendert:

- `## Open Tasks`
- `## Completed Tasks`

### Heuristik

- **Keine harte Mindestlänge** als Keep/Drop-Regel.
- Triviale Kommunikations-Tasks (z. B. `FYI`, `ok`, `bitte prüfen`) werden verworfen.
- Tasks werden behalten, wenn mindestens ein Informationssignal vorliegt, z. B. Link, Due-Date, Entscheidungs-/Freigabesignal, domänenspezifischer Begriff oder sinntragende fachliche Aussage.
- Mentions/Assignees werden separat extrahiert und im Markdown erhalten.

### Metadaten

Für behaltene Tasks werden zusätzliche `promoted_properties` gesetzt:

- `open_task_count`
- `completed_task_count`
- `open_task_mentions`
- `completed_task_mentions`

Signalwortlisten sind in `macro_transformer.py` zentral gehalten und können später konfigurierbar gemacht werden.


## Bewusst ignorierte Makros

Folgende Makros werden ohne Warning und ohne Aktion entfernt:

- `contentbylabel`
- `classifications-hierarchy`
- `classifications-category`
- `anchor`
- `create-from-template`
- `livesearch`
- `profile`
- `tasks-report-macro`
- `children`
- `classifications-status`
- `detailssummary`
- `drawio`
- `draw.io`
- `diagrams.net`
- `inc-drawio`

Das reduziert Rauschen im Output und verbessert die Nutzbarkeit für RAG/Chunking.
