from __future__ import annotations

import csv
import html
import io
import re
import zipfile
from dataclasses import dataclass
from typing import Iterable
from xml.sax.saxutils import escape as xml_escape


HTML_TAG_RE = re.compile(r"<[^>]+>")
HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.*)$")
STAR_HEADING_RE = re.compile(r"^\s*([*_]{2,})\s*(.*?)\s*\1\s*$")
ORDERED_ITEM_RE = re.compile(r"^\s*\d+\.\s+(.*)$")
UNORDERED_ITEM_RE = re.compile(r"^\s*[-*+]\s+(.*)$")
TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?(?:\s*:?-{3,}:?\s*\|)+\s*:?-{3,}:?\s*\|?\s*$")
ILLEGAL_XML_RE = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F]")
FORMULA_PREFIXES = ("=", "+", "-", "@")


@dataclass(frozen=True)
class ExportTable:
    headers: list[str]
    rows: list[list[str]]


@dataclass(frozen=True)
class ExportBundle:
    title: str
    table: ExportTable | None
    narrative_headers: list[str]
    narrative_rows: list[list[str]]
    overview_rows: list[list[str]]


def build_export_bundle(
    solution_text: str,
    *,
    title: str = "The Arbiter Report",
    metadata: dict[str, object] | None = None,
) -> ExportBundle:
    clean_text = _strip_html(solution_text)
    table = _extract_primary_table(clean_text)
    narrative_headers, narrative_rows = _build_narrative_rows(clean_text)
    overview_rows = _build_overview_rows(title=title, metadata=metadata or {})
    return ExportBundle(
        title=title,
        table=table,
        narrative_headers=narrative_headers,
        narrative_rows=narrative_rows,
        overview_rows=overview_rows,
    )


def export_solution_csv(
    solution_text: str,
    *,
    title: str = "The Arbiter Report",
    metadata: dict[str, object] | None = None,
) -> str:
    bundle = build_export_bundle(solution_text, title=title, metadata=metadata)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    if bundle.table is not None:
        writer.writerow([_safe_cell_text(cell) for cell in bundle.table.headers])
        writer.writerows([[_safe_cell_text(cell) for cell in row] for row in bundle.table.rows])
    else:
        writer.writerow([_safe_cell_text(cell) for cell in bundle.narrative_headers])
        writer.writerows([[_safe_cell_text(cell) for cell in row] for row in bundle.narrative_rows])
    return buffer.getvalue()


def export_solution_xlsx(
    solution_text: str,
    *,
    title: str = "The Arbiter Report",
    metadata: dict[str, object] | None = None,
) -> bytes:
    bundle = build_export_bundle(solution_text, title=title, metadata=metadata)
    sheets: list[tuple[str, list[list[str]]]] = [
        ("Overview", bundle.overview_rows),
        ("Narrative", [bundle.narrative_headers, *bundle.narrative_rows]),
    ]
    if bundle.table is not None:
        sheets.insert(1, ("Structured Data", [bundle.table.headers, *bundle.table.rows]))
    return _build_xlsx_workbook(sheets)


def _build_overview_rows(*, title: str, metadata: dict[str, object]) -> list[list[str]]:
    rows = [["Field", "Value"], ["Title", title]]
    for key, value in metadata.items():
        rows.append([str(key), _stringify(value)])
    return rows


def _build_narrative_rows(text: str) -> tuple[list[str], list[list[str]]]:
    rows: list[list[str]] = []
    current_section = "General"
    for raw_line in text.splitlines():
        line = _normalize_line(raw_line)
        if not line or TABLE_SEPARATOR_RE.match(line):
            continue
        heading = _extract_heading(line)
        if heading:
            current_section = heading
            continue
        if _looks_like_table_row(line):
            continue
        item = _strip_list_marker(line)
        if item:
            rows.append([current_section, item])
            continue
        rows.append([current_section, line])
    if not rows:
        rows.append(["General", "No exportable narrative content was found."])
    return ["Section", "Content"], rows


def _extract_primary_table(text: str) -> ExportTable | None:
    lines = text.splitlines()
    index = 0
    best_table: ExportTable | None = None
    while index < len(lines):
        line = lines[index]
        if "|" not in line:
            index += 1
            continue
        block: list[str] = []
        while index < len(lines) and "|" in lines[index]:
            block.append(lines[index])
            index += 1
        table = _parse_table_block(block)
        if table is None:
            continue
        if best_table is None or len(table.rows) > len(best_table.rows):
            best_table = table
    return best_table


def _parse_table_block(lines: list[str]) -> ExportTable | None:
    if len(lines) < 2 or not TABLE_SEPARATOR_RE.match(lines[1]):
        return None
    headers = _split_table_row(lines[0])
    if not headers:
        return None
    rows: list[list[str]] = []
    for raw_line in lines[2:]:
        cells = _split_table_row(raw_line)
        if not any(cells):
            continue
        padded = (cells + [""] * len(headers))[: len(headers)]
        rows.append(padded)
    return ExportTable(headers=headers, rows=rows)


def _split_table_row(line: str) -> list[str]:
    trimmed = line.strip()
    if trimmed.startswith("|"):
        trimmed = trimmed[1:]
    if trimmed.endswith("|"):
        trimmed = trimmed[:-1]
    return [_normalize_line(cell) for cell in trimmed.split("|")]


def _strip_html(text: str) -> str:
    return html.unescape(HTML_TAG_RE.sub("", str(text or "")))


def _normalize_line(line: str) -> str:
    value = _strip_html(line).strip()
    if not value:
        return ""
    match = STAR_HEADING_RE.match(value)
    if match:
        value = match.group(2).strip()
    value = value.replace("\u00a0", " ")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _extract_heading(line: str) -> str | None:
    match = HEADING_RE.match(line)
    if match:
        return match.group(1).strip(" -*_")
    if line.endswith(":") and len(line) <= 80:
        return line.rstrip(":").strip()
    return None


def _strip_list_marker(line: str) -> str | None:
    ordered = ORDERED_ITEM_RE.match(line)
    if ordered:
        return ordered.group(1).strip()
    unordered = UNORDERED_ITEM_RE.match(line)
    if unordered:
        return unordered.group(1).strip()
    return None


def _looks_like_table_row(line: str) -> bool:
    return "|" in line and line.count("|") >= 2


def _build_xlsx_workbook(sheets: Iterable[tuple[str, list[list[str]]]]) -> bytes:
    normalized_sheets = [
        (_sanitize_sheet_name(name, index), rows)
        for index, (name, rows) in enumerate(sheets, start=1)
    ]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _content_types_xml(len(normalized_sheets)))
        archive.writestr("_rels/.rels", _root_relationships_xml())
        archive.writestr("xl/workbook.xml", _workbook_xml([name for name, _ in normalized_sheets]))
        archive.writestr("xl/_rels/workbook.xml.rels", _workbook_relationships_xml(len(normalized_sheets)))
        archive.writestr("docProps/core.xml", _core_properties_xml())
        archive.writestr("docProps/app.xml", _app_properties_xml([name for name, _ in normalized_sheets]))
        for index, (_, rows) in enumerate(normalized_sheets, start=1):
            archive.writestr(f"xl/worksheets/sheet{index}.xml", _worksheet_xml(rows))
    return buffer.getvalue()


def _worksheet_xml(rows: list[list[str]]) -> str:
    xml_rows: list[str] = []
    for row_index, row in enumerate(rows, start=1):
        cells = []
        for column_index, value in enumerate(row, start=1):
            reference = f"{_column_name(column_index)}{row_index}"
            cell_text = _safe_cell_text(value)
            if cell_text == "":
                cells.append(f'<c r="{reference}"/>')
                continue
            escaped = xml_escape(_strip_illegal_xml(cell_text))
            cells.append(
                f'<c r="{reference}" t="inlineStr"><is><t xml:space="preserve">{escaped}</t></is></c>'
            )
        xml_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"<sheetData>{''.join(xml_rows)}</sheetData>"
        "</worksheet>"
    )


def _content_types_xml(sheet_count: int) -> str:
    overrides = [
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>',
        '<Override PartName="/docProps/core.xml" '
        'ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>',
        '<Override PartName="/docProps/app.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>',
    ]
    for index in range(1, sheet_count + 1):
        overrides.append(
            f'<Override PartName="/xl/worksheets/sheet{index}.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        f"{''.join(overrides)}"
        "</Types>"
    )


def _root_relationships_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/>'
        '<Relationship Id="rId2" '
        'Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" '
        'Target="docProps/core.xml"/>'
        '<Relationship Id="rId3" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" '
        'Target="docProps/app.xml"/>'
        "</Relationships>"
    )


def _workbook_xml(sheet_names: list[str]) -> str:
    sheets_xml = []
    for index, name in enumerate(sheet_names, start=1):
        sheets_xml.append(
            f'<sheet name="{xml_escape(name)}" sheetId="{index}" r:id="rId{index}"/>'
        )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f"<sheets>{''.join(sheets_xml)}</sheets>"
        "</workbook>"
    )


def _workbook_relationships_xml(sheet_count: int) -> str:
    relationships = []
    for index in range(1, sheet_count + 1):
        relationships.append(
            f'<Relationship Id="rId{index}" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
            f'Target="worksheets/sheet{index}.xml"/>'
        )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f"{''.join(relationships)}"
        "</Relationships>"
    )


def _core_properties_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:dcterms="http://purl.org/dc/terms/" '
        'xmlns:dcmitype="http://purl.org/dc/dcmitype/" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        "<dc:title>The Arbiter Export</dc:title>"
        "<dc:creator>The Arbiter</dc:creator>"
        "</cp:coreProperties>"
    )


def _app_properties_xml(sheet_names: list[str]) -> str:
    parts = "".join(f"<vt:lpstr>{xml_escape(name)}</vt:lpstr>" for name in sheet_names)
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" '
        'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
        "<Application>The Arbiter</Application>"
        f"<TitlesOfParts><vt:vector size=\"{len(sheet_names)}\" baseType=\"lpstr\">{parts}</vt:vector></TitlesOfParts>"
        "</Properties>"
    )


def _sanitize_sheet_name(name: str, index: int) -> str:
    value = re.sub(r"[\[\]:*?/\\]", " ", str(name or "")).strip() or f"Sheet {index}"
    return value[:31]


def _column_name(column_index: int) -> str:
    result = []
    current = column_index
    while current > 0:
        current, remainder = divmod(current - 1, 26)
        result.append(chr(65 + remainder))
    return "".join(reversed(result))


def _safe_cell_text(value: object) -> str:
    text = _stringify(value)
    if text.startswith(FORMULA_PREFIXES):
        return f"'{text}"
    return text


def _stringify(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:.4f}".rstrip("0").rstrip(".")
    if isinstance(value, (list, tuple, set)):
        return ", ".join(_stringify(item) for item in value)
    return str(value)


def _strip_illegal_xml(text: str) -> str:
    return ILLEGAL_XML_RE.sub("", text)
