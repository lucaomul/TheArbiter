import io
import zipfile

from arbiter.app.export_artifacts import (
    build_export_bundle,
    export_solution_csv,
    export_solution_xlsx,
)


def test_export_csv_prefers_markdown_tables():
    solution = """
## Weekly Plan

| Owner | Status | Next Step |
| --- | --- | --- |
| Growth | In progress | Launch ads |
| Ops | Done | Share SOP |
"""
    csv_text = export_solution_csv(solution)

    assert "Owner,Status,Next Step" in csv_text
    assert "Growth,In progress,Launch ads" in csv_text
    assert "Section,Content" not in csv_text


def test_export_bundle_falls_back_to_narrative_rows():
    solution = """
### Priorities
- Fix onboarding handoff
- Review customer churn notes

### Risks
- Team is over capacity
"""
    bundle = build_export_bundle(solution)

    assert bundle.table is None
    assert bundle.narrative_headers == ["Section", "Content"]
    assert ["Priorities", "Fix onboarding handoff"] in bundle.narrative_rows
    assert ["Risks", "Team is over capacity"] in bundle.narrative_rows


def test_export_xlsx_contains_expected_sheets_and_content():
    solution = """
## Launch Checklist
- Finalize copy
- QA payment flow
"""
    xlsx_bytes = export_solution_xlsx(
        solution,
        metadata={"Task Mode": "Marketing & Growth", "Iterations": 2},
    )

    with zipfile.ZipFile(io.BytesIO(xlsx_bytes)) as archive:
        names = set(archive.namelist())
        workbook_xml = archive.read("xl/workbook.xml").decode("utf-8")
        sheet_xml = archive.read("xl/worksheets/sheet2.xml").decode("utf-8")

    assert "[Content_Types].xml" in names
    assert "xl/worksheets/sheet1.xml" in names
    assert "Overview" in workbook_xml
    assert "Narrative" in workbook_xml
    assert "Finalize copy" in sheet_xml


def test_export_artifacts_guard_against_formula_injection():
    solution = """
| Formula | Value |
| --- | --- |
| =SUM(1,1) | @danger |
"""
    csv_text = export_solution_csv(solution)
    xlsx_bytes = export_solution_xlsx(solution)

    assert "'=SUM(1,1)" in csv_text
    assert "'@danger" in csv_text

    with zipfile.ZipFile(io.BytesIO(xlsx_bytes)) as archive:
        sheet_xml = archive.read("xl/worksheets/sheet2.xml").decode("utf-8")

    assert "'=SUM(1,1)" in sheet_xml
    assert "'@danger" in sheet_xml
