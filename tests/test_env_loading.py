import base64
import sys
from pathlib import Path
from unittest.mock import patch


def test_main_loads_dotenv_from_project_root(monkeypatch):
    root = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(root)
    monkeypatch.setenv("USE_MOCK_ANTHROPIC", "true")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    sys.modules.pop("app.main", None)

    with patch("dotenv.load_dotenv") as mocked:
        import app.main  # noqa: F401

    mocked.assert_called_once()
    assert mocked.call_args.args[0] == str(root / ".env")


def test_report_artifact_is_a_pdf(monkeypatch):
    monkeypatch.setenv("USE_MOCK_ANTHROPIC", "true")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    from app.main import _build_pdf_report

    encoded = _build_pdf_report("Summary", "Audit", "Data")

    assert base64.b64decode(encoded).startswith(b"%PDF")


def test_structured_answer_populates_distinct_report_sections():
    from app.main import _build_three_format_response

    response = _build_three_format_response(
        "=== PI SUMMARY ===\nShort ranking.\n"
        "=== TECHNICAL AUDIT ===\nMethod and [source](https://example.org).\n"
        "=== DATA FOCUS ===\n| Candidate | k |\n|---|---|\n| MgO | 9 |"
    )

    assert response.summary == "Short ranking."
    assert response.audit.startswith("Method and")
    assert "MgO" in response.data_focus
    assert response.summary != response.audit != response.data_focus


def test_parser_removes_section_headings_from_each_pdf_section():
    from app.main import _parse_answer_sections

    summary, audit, data_focus = _parse_answer_sections(
        "Here are the ranked candidates and their associated data\n\n"
        "=== PI SUMMARY ===\nSummary only.\n\n"
        "=== TECHNICAL AUDIT ===\nAudit only.\n\n"
        "=== DATA FOCUS ===\nData only."
    )

    assert summary == "Summary only."
    assert audit == "Audit only."
    assert data_focus == "Data only."
    assert "=== TECHNICAL AUDIT ===" not in summary
    assert "=== PI SUMMARY ===" not in audit


def test_parser_keeps_missing_structured_sections_empty():
    from app.main import _parse_answer_sections

    summary, audit, data_focus = _parse_answer_sections(
        "=== PI SUMMARY ===\nSummary only.\n"
        "=== DATA FOCUS ===\nData only."
    )

    assert summary == "Summary only."
    assert audit == ""
    assert data_focus == "Data only."


def test_pdf_builder_accepts_markdown_tables_and_links(monkeypatch):
    monkeypatch.setenv("USE_MOCK_ANTHROPIC", "true")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    from app.main import _build_pdf_report

    encoded = _build_pdf_report(
        "**Summary**",
        "[Source](https://example.org)",
        "| Candidate | Value |\n|---|---|\n| MgO | 9 |",
    )

    assert base64.b64decode(encoded).startswith(b"%PDF")


def test_pdf_table_links_render_as_reportlab_links():
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, Table

    from app.main import _markdown_flowables

    styles = getSampleStyleSheet()
    flowables = _markdown_flowables(
        "| Source | Finding |\n|---|---|\n"
        "| [Paper](https://example.org/paper) | Supported |",
        styles["BodyText"],
        styles["Heading2"],
    )

    table = next(flowable for flowable in flowables if isinstance(flowable, Table))
    cell = table._cellvalues[1][0]
    assert isinstance(cell, Paragraph)
    assert 'href="https://example.org/paper"' in cell.text


def test_pdf_builder_normalizes_legacy_full_response_fields(monkeypatch):
    monkeypatch.setenv("USE_MOCK_ANTHROPIC", "true")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    from app.main import _build_pdf_report

    full_answer = (
        "=== PI SUMMARY ===\nSummary only.\n"
        "=== TECHNICAL AUDIT ===\nAudit only.\n"
        "=== DATA FOCUS ===\nData only."
    )
    encoded = _build_pdf_report(full_answer, "legacy full response", "legacy full response")

    assert base64.b64decode(encoded).startswith(b"%PDF")
