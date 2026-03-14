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

## Konfiguration

Aus `config/app.toml`:

- `minimum_number_of_raw_characters_in_page`: Seiten unterhalb dieser Rohzeichenanzahl werden übersprungen.
- `page_properties_frontmatter_keys`: alphabetisch sortierte Whitelist der zu promotenden Seiteneigenschaften.

## Designprinzipien

- Kleine, fokussierte Methoden mit klaren Verantwortlichkeiten.
- Pattern-basierte Erweiterung statt monolithischer Sonderlogik.
- Konservative Extraktion: lieber stabiler Fallback als aggressive Vermutung.
