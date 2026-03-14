# Confluence Transformer

Dieses Modul transformiert Confluence-Storage-Exportseiten in ingestierbares Markdown.

## Bausteine

- `transformer.py`: Orchestriert Makros, Tabellen, Links, Struktur und Cleanup.
- `macro_transformer.py`: Makro-spezifische Pattern-Transformationen.
- `table_transformer.py`: Tabellen-Erkennung, Key/Value-Extraktion und Markdown-Rendern.
- `page_property_rules.py`: TOML-basiertes Regelwerk für Frontmatter-Property-Mapping.
- `markdown_renderer.py`: Rendert Frontmatter + Body.

## Erweiterungspatterns

### Neue Makros ergänzen

1. In `SUPPORTED_SIMPLE` aufnehmen.
2. Eine dedizierte `_replace_*` oder `_unwrap_*` Methode erstellen.
3. Methode in `transform()` aufrufen.
4. Mit Unit-Tests absichern (`tests/test_confluence_macro_transformer.py`).

### Neue Frontmatter-Keys ergänzen

1. `config/confluence_page_property_rules.toml` erweitern.
2. Optional Aliases unter `[frontmatter.aliases]` ergänzen.
3. Optional Listen-Trenner unter `[frontmatter.value_lists]` definieren.
4. Tests in `tests/test_confluence_table_transformer.py` ergänzen.

## Verhalten: Page-Properties

- Key/Value-Tabellen werden erkannt.
- Nur Rows mit Value werden als Properties übernommen.
- Konfigurierte Keys landen direkt im Frontmatter und erscheinen nicht im Markdown-Text.
- Nicht konfigurierte Keys bleiben als Bullet-Liste im Text sichtbar.

## Konfiguration

- Property-Regeln: `config/confluence_page_property_rules.toml`
- Mindestlänge für Rohseiten: `confluence_transform.mininum_number_of_raw_characters_in_page` in `config/app.toml`
