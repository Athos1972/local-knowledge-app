from __future__ import annotations

import csv
from dataclasses import dataclass
import logging
from pathlib import Path
import shutil
import tempfile
import xml.etree.ElementTree as ET
from zipfile import ZIP_DEFLATED, ZipFile

from processing.terminology.candidates import CANDIDATE_COLUMNS
from processing.terminology.loader import TerminologyLoader, write_yaml_files
from processing.terminology.models import SourceMode, TerminologyRelation, TerminologyTerm
from processing.terminology.validator import TerminologyValidator


logger = logging.getLogger(__name__)

XMLNS_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
XMLNS_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
XMLNS_PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
ET.register_namespace("", XMLNS_MAIN)
ET.register_namespace("r", XMLNS_REL)


@dataclass(slots=True)
class ImportResult:
    terms: int
    aliases: int
    relations: int


class TerminologyExcelService:
    def __init__(self, config_root: Path, reports_root: Path) -> None:
        self._config_root = config_root
        self._reports_root = reports_root

    def export_xlsx(self, output: Path, candidates_csv: Path | None = None) -> None:
        loader = TerminologyLoader(self._config_root)
        config = loader.load()

        terms_rows = [["id", "canonical", "label", "description", "term_class", "applies_to", "annotate_policy", "block_policy", "case_sensitive", "priority"]]
        for term in sorted(config.terms_by_id.values(), key=lambda item: (item.priority, item.term_id)):
            terms_rows.append([term.term_id, term.canonical, term.label, term.description, term.term_class, ",".join(term.applies_to), term.annotate_policy, term.block_policy, str(term.case_sensitive).lower(), term.priority])

        aliases_rows = [["term_id", "alias"]]
        for term in sorted(config.terms_by_id.values(), key=lambda item: item.term_id):
            for alias in term.aliases:
                aliases_rows.append([term.term_id, alias])

        relations_rows = [["source_term_id", "relation_type", "target_term_id", "target_label", "note"]]
        for term in sorted(config.terms_by_id.values(), key=lambda item: item.term_id):
            for relation in term.relations:
                relations_rows.append([term.term_id, relation.relation_type, relation.target_id, relation.target_label or "", relation.note or ""])

        sources_rows = [["source_type", "mode", "candidates_enabled", "enabled"]]
        for source_name, source_mode in sorted(config.source_modes.items()):
            enabled = "" if source_mode.enabled is None else str(source_mode.enabled).lower()
            sources_rows.append([source_name, source_mode.mode, str(source_mode.candidates_enabled).lower(), enabled])

        candidates_rows = [CANDIDATE_COLUMNS]
        candidates_path = candidates_csv or (self._reports_root / "terminology_candidates.csv")
        if candidates_path.exists():
            with candidates_path.open("r", encoding="utf-8", newline="") as handle:
                for row in csv.DictReader(handle):
                    candidates_rows.append([row.get(col, "") for col in CANDIDATE_COLUMNS])

        workbook = {
            "terms": terms_rows,
            "aliases": aliases_rows,
            "relations": relations_rows,
            "sources": sources_rows,
            "candidates": candidates_rows,
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        self._write_workbook(output, workbook)
        logger.info("Terminology XLSX exported: path=%s terms=%s", output, len(config.terms_by_id))

    def import_xlsx(self, input_path: Path, dry_run: bool = False, backup: bool = False) -> ImportResult:
        workbook = self._read_workbook(input_path)

        terms_map: dict[str, TerminologyTerm] = {}
        for row in workbook.get("terms", [])[1:]:
            if not row or not row[0]:
                continue
            term_id = str(row[0]).strip()
            terms_map[term_id] = TerminologyTerm(
                term_id=term_id,
                canonical=str(row[1] if len(row) > 1 else "").strip(),
                label=str(row[2] if len(row) > 2 else "").strip(),
                description=str(row[3] if len(row) > 3 else "").strip(),
                term_class=str(row[4] if len(row) > 4 else "business").strip(),
                applies_to=[part.strip() for part in str(row[5] if len(row) > 5 else "").split(",") if part.strip()],
                annotate_policy=str(row[6] if len(row) > 6 else "first_occurrence").strip(),
                block_policy=str(row[7] if len(row) > 7 else "include").strip(),
                case_sensitive=str(row[8] if len(row) > 8 else "false").strip().lower() == "true",
                priority=int(str(row[9] if len(row) > 9 else "100") or "100"),
            )

        alias_count = 0
        for row in workbook.get("aliases", [])[1:]:
            if len(row) < 2:
                continue
            term = terms_map.get(str(row[0]).strip())
            alias = str(row[1]).strip()
            if term and alias:
                term.aliases.append(alias)
                alias_count += 1

        relation_count = 0
        for row in workbook.get("relations", [])[1:]:
            if len(row) < 3:
                continue
            term = terms_map.get(str(row[0]).strip())
            if term and str(row[1]).strip() and str(row[2]).strip():
                term.relations.append(TerminologyRelation(relation_type=str(row[1]).strip(), target_id=str(row[2]).strip(), target_label=str(row[3]).strip() if len(row) > 3 and str(row[3]).strip() else None, note=str(row[4]).strip() if len(row) > 4 and str(row[4]).strip() else None))
                relation_count += 1

        source_modes: dict[str, SourceMode] = {}
        for row in workbook.get("sources", [])[1:]:
            if len(row) < 1 or not str(row[0]).strip():
                continue
            source_modes[str(row[0]).strip()] = SourceMode(
                mode=str(row[1] if len(row) > 1 else "off").strip(),
                candidates_enabled=str(row[2] if len(row) > 2 else "false").strip().lower() == "true",
                enabled=(str(row[3]).strip().lower() == "true") if len(row) > 3 and str(row[3]).strip() else None,
            )

        settings = TerminologyLoader(self._config_root).load().settings
        if dry_run:
            logger.info("Terminology XLSX import dry-run: terms=%s aliases=%s relations=%s", len(terms_map), alias_count, relation_count)
            return ImportResult(terms=len(terms_map), aliases=alias_count, relations=relation_count)

        if backup:
            backup_dir = self._config_root.parent / f"{self._config_root.name}.backup"
            if backup_dir.exists():
                shutil.rmtree(backup_dir)
            shutil.copytree(self._config_root, backup_dir)

        with tempfile.TemporaryDirectory(prefix="terminology-import-") as tmp_dir:
            temp_root = Path(tmp_dir) / "terminology"
            write_yaml_files(temp_root, settings=settings, sources=source_modes, terms=list(terms_map.values()))
            temp_validation = TerminologyValidator(temp_root).validate()
            if temp_validation.errors:
                raise ValueError(f"Import validation failed with {len(temp_validation.errors)} errors")
            for filename in ["settings.yml", "sources.yml", "terms.yml"]:
                shutil.move(str(temp_root / filename), str(self._config_root / filename))

        final_result = TerminologyValidator(self._config_root).validate()
        if final_result.errors:
            raise ValueError(f"Post-import validation failed with {len(final_result.errors)} errors")

        logger.info("Terminology XLSX imported: terms=%s aliases=%s relations=%s", len(terms_map), alias_count, relation_count)
        return ImportResult(terms=len(terms_map), aliases=alias_count, relations=relation_count)

    def _write_workbook(self, path: Path, workbook: dict[str, list[list[object]]]) -> None:
        sheet_names = list(workbook.keys())
        with ZipFile(path, "w", compression=ZIP_DEFLATED) as zf:
            zf.writestr("[Content_Types].xml", self._content_types(len(sheet_names)))
            zf.writestr("_rels/.rels", self._root_rels())
            zf.writestr("xl/workbook.xml", self._workbook_xml(sheet_names))
            zf.writestr("xl/_rels/workbook.xml.rels", self._workbook_rels(len(sheet_names)))
            zf.writestr("xl/styles.xml", self._styles_xml())

            for idx, sheet_name in enumerate(sheet_names, start=1):
                rows = workbook[sheet_name]
                zf.writestr(f"xl/worksheets/sheet{idx}.xml", self._sheet_xml(rows))

    def _read_workbook(self, path: Path) -> dict[str, list[list[str]]]:
        data: dict[str, list[list[str]]] = {}
        with ZipFile(path, "r") as zf:
            wb_root = ET.fromstring(zf.read("xl/workbook.xml"))
            rels_root = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
            rel_map = {
                rel.attrib["Id"]: rel.attrib["Target"]
                for rel in rels_root.findall(f"{{{XMLNS_PKG_REL}}}Relationship")
            }
            for sheet in wb_root.findall(f"{{{XMLNS_MAIN}}}sheets/{{{XMLNS_MAIN}}}sheet"):
                name = sheet.attrib.get("name", "sheet")
                rel_id = sheet.attrib.get(f"{{{XMLNS_REL}}}id", "")
                target = rel_map.get(rel_id, "")
                sheet_xml = zf.read(f"xl/{target}")
                data[name] = self._read_sheet(sheet_xml)
        return data

    def _read_sheet(self, sheet_xml: bytes) -> list[list[str]]:
        root = ET.fromstring(sheet_xml)
        rows: list[list[str]] = []
        for row in root.findall(f"{{{XMLNS_MAIN}}}sheetData/{{{XMLNS_MAIN}}}row"):
            values: list[str] = []
            for cell in row.findall(f"{{{XMLNS_MAIN}}}c"):
                cell_type = cell.attrib.get("t", "")
                value = ""
                if cell_type == "inlineStr":
                    node = cell.find(f"{{{XMLNS_MAIN}}}is/{{{XMLNS_MAIN}}}t")
                    value = node.text if node is not None and node.text is not None else ""
                else:
                    node = cell.find(f"{{{XMLNS_MAIN}}}v")
                    value = node.text if node is not None and node.text is not None else ""
                values.append(value)
            rows.append(values)
        return rows

    def _sheet_xml(self, rows: list[list[object]]) -> str:
        root = ET.Element(f"{{{XMLNS_MAIN}}}worksheet")
        ET.SubElement(root, f"{{{XMLNS_MAIN}}}sheetViews")
        ET.SubElement(root, f"{{{XMLNS_MAIN}}}sheetFormatPr")
        cols = ET.SubElement(root, f"{{{XMLNS_MAIN}}}cols")
        max_cols = max((len(row) for row in rows), default=1)
        for idx in range(1, max_cols + 1):
            ET.SubElement(cols, f"{{{XMLNS_MAIN}}}col", attrib={"min": str(idx), "max": str(idx), "width": "20", "customWidth": "1"})

        sheet_data = ET.SubElement(root, f"{{{XMLNS_MAIN}}}sheetData")
        for row_idx, row_values in enumerate(rows, start=1):
            row = ET.SubElement(sheet_data, f"{{{XMLNS_MAIN}}}row", attrib={"r": str(row_idx)})
            for col_idx, raw in enumerate(row_values, start=1):
                cell_ref = self._cell_ref(col_idx, row_idx)
                c = ET.SubElement(row, f"{{{XMLNS_MAIN}}}c", attrib={"r": cell_ref, "t": "inlineStr"})
                if row_idx == 1:
                    c.attrib["s"] = "1"
                is_node = ET.SubElement(c, f"{{{XMLNS_MAIN}}}is")
                t = ET.SubElement(is_node, f"{{{XMLNS_MAIN}}}t")
                t.text = str(raw) if raw is not None else ""

        ET.SubElement(root, f"{{{XMLNS_MAIN}}}autoFilter", attrib={"ref": f"A1:{self._cell_ref(max_cols, 1)}"})
        ET.SubElement(root, f"{{{XMLNS_MAIN}}}pane", attrib={"ySplit": "1", "topLeftCell": "A2", "activePane": "bottomLeft", "state": "frozen"})
        return ET.tostring(root, encoding="utf-8", xml_declaration=True).decode("utf-8")

    @staticmethod
    def _cell_ref(col: int, row: int) -> str:
        letters = ""
        value = col
        while value:
            value, rem = divmod(value - 1, 26)
            letters = chr(65 + rem) + letters
        return f"{letters}{row}"

    @staticmethod
    def _content_types(sheet_count: int) -> str:
        parts = "".join(
            f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            for i in range(1, sheet_count + 1)
        )
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
            f"{parts}"
            '</Types>'
        )

    @staticmethod
    def _root_rels() -> str:
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            f'<Relationships xmlns="{XMLNS_PKG_REL}">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            '</Relationships>'
        )

    @staticmethod
    def _workbook_xml(sheet_names: list[str]) -> str:
        sheets = "".join(
            f'<sheet name="{name}" sheetId="{idx}" r:id="rId{idx}"/>'
            for idx, name in enumerate(sheet_names, start=1)
        )
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            f'<workbook xmlns="{XMLNS_MAIN}" xmlns:r="{XMLNS_REL}"><sheets>{sheets}</sheets></workbook>'
        )

    @staticmethod
    def _workbook_rels(sheet_count: int) -> str:
        sheet_rels = "".join(
            f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>'
            for i in range(1, sheet_count + 1)
        )
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            f'<Relationships xmlns="{XMLNS_PKG_REL}">'
            f'{sheet_rels}<Relationship Id="rId{sheet_count + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
            '</Relationships>'
        )

    @staticmethod
    def _styles_xml() -> str:
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            f'<styleSheet xmlns="{XMLNS_MAIN}">'
            '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font></fonts>'
            '<fills count="1"><fill><patternFill patternType="none"/></fill></fills>'
            '<borders count="1"><border/></borders>'
            '<cellStyleXfs count="1"><xf/></cellStyleXfs>'
            '<cellXfs count="2"><xf xfId="0"/><xf xfId="0" fontId="1" applyFont="1"/></cellXfs>'
            '</styleSheet>'
        )
