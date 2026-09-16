import json
import logging
import base64
import html
import re
from io import BytesIO
from pathlib import Path

from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.lib import colors

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

load_dotenv(str(Path(__file__).resolve().parent.parent / ".env"))

from .agent import Agent
from .policy import check_user_request

app = FastAPI(title="Experiment Design Agent")

# Allow the local Dash UI to call this backend during development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8050"],
    allow_credentials=True,
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["*"],
)

agent = Agent()


class ChatRequest(BaseModel):
    message: str


class DownloadArtifact(BaseModel):
    filename: str = "research_report.pdf"
    mime_type: str = "application/pdf"
    content: str | None = None
    url: str | None = None
    encoding: str = "base64"


class ChatResponse(BaseModel):
    answer: str
    summary: str
    audit: str
    data_focus: str
    download: DownloadArtifact | None = None


def _parse_answer_sections(answer: str) -> tuple[str, str, str]:
    heading_pattern = re.compile(
        r"^\s*===\s*(PI SUMMARY|TECHNICAL AUDIT|DATA FOCUS)\s*===\s*$",
        re.IGNORECASE | re.MULTILINE,
    )
    matches = list(heading_pattern.finditer(answer))
    sections = {}
    for index, match in enumerate(matches):
        name = match.group(1).lower().replace(" ", "_")
        end = matches[index + 1].start() if index + 1 < len(matches) else len(answer)
        sections[name] = answer[match.end():end].strip()

    if not matches:
        summary = answer.strip() or "No public evidence found."
        return summary, summary, (
            "No structured raw data was returned. See the technical audit for the evidence review."
        )
    return (
        sections.get("pi_summary", ""),
        sections.get("technical_audit", ""),
        sections.get("data_focus", ""),
    )


def _markdown_flowables(content: str, body_style: ParagraphStyle, heading_style: ParagraphStyle):
    def table_cell_flowable(value: str):
        text = html.escape(value)
        text = re.sub(
            r"\[([^]]+)\]\((https?://[^)]+)\)",
            r'<link href="\2" color="blue">\1</link>',
            text,
        )
        return Paragraph(text, body_style)

    flowables = []
    lines = content.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index].strip()
        if not line:
            index += 1
            continue
        if line.startswith("```"):
            code_lines = []
            index += 1
            while index < len(lines) and not lines[index].strip().startswith("```"):
                code_lines.append(lines[index])
                index += 1
            if index < len(lines):
                index += 1
            code = html.escape("\n".join(code_lines)).replace("\n", "<br/>")
            flowables.append(Paragraph(f"<font name='Courier'>{code}</font>", body_style))
        elif line.startswith("|") and index + 1 < len(lines) and lines[index + 1].strip().startswith("|"):
            table_lines = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                values = [cell.strip() for cell in lines[index].strip().strip("|").split("|")]
                if not all(set(cell) <= set("-: ") for cell in values):
                    table_lines.append([table_cell_flowable(value) for value in values])
                index += 1
            if table_lines:
                table = Table(table_lines, repeatRows=1)
                table.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#d9e6e3")),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                ]))
                flowables.append(table)
        else:
            text = html.escape(line)
            text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
            text = re.sub(r"\[([^]]+)\]\((https?://[^)]+)\)", r'<link href="\2" color="blue">\1</link>', text)
            text = re.sub(r"^#{1,3}\s+", "", text)
            if line.startswith("#"):
                flowables.append(Paragraph(text, heading_style))
            else:
                flowables.append(Paragraph(text.replace("- ", "&#8226; "), body_style))
            index += 1
    return flowables


def _build_pdf_report(summary: str, audit: str, data_focus: str) -> str:
    # Normalize defensively because reports may be generated from older payloads
    # where each field still contained the complete structured answer.
    combined = next(
        (value for value in (summary, audit, data_focus) if "=== PI SUMMARY ===" in value),
        None,
    )
    if combined and all(heading in combined for heading in (
        "=== PI SUMMARY ===",
        "=== TECHNICAL AUDIT ===",
        "=== DATA FOCUS ===",
    )):
        summary, audit, data_focus = _parse_answer_sections(combined)

    buffer = BytesIO()
    styles = getSampleStyleSheet()
    body_style = ParagraphStyle(
        "ReportBody",
        parent=styles["BodyText"],
        alignment=TA_LEFT,
        fontName="Helvetica",
        fontSize=10,
        leading=14,
        spaceAfter=8,
    )
    heading_style = ParagraphStyle(
        "ReportHeading",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=14,
        leading=18,
        spaceBefore=10,
        spaceAfter=8,
    )

    document = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.7 * inch,
        leftMargin=0.7 * inch,
        topMargin=0.7 * inch,
        bottomMargin=0.7 * inch,
        title="Research Report",
    )
    story = [Paragraph("Research Report", styles["Title"])]
    for heading, content in (
        ("Summary", summary),
        ("Technical / Audit", audit),
        ("Data Focus", data_focus),
    ):
        story.append(Paragraph(heading, heading_style))
        story.extend(_markdown_flowables(content, body_style, heading_style))
        story.append(Spacer(1, 4))

    document.build(story)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def _build_three_format_response(answer: str) -> ChatResponse:
    summary, audit, data_focus = _parse_answer_sections(answer)

    pdf_content = _build_pdf_report(summary, audit, data_focus)

    return ChatResponse(
        answer=summary,
        summary=summary,
        audit=audit,
        data_focus=data_focus,
        download=DownloadArtifact(
            filename="research_report.pdf",
            mime_type="application/pdf",
            content=pdf_content,
        ),
    )


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    allowed, reason = check_user_request(request.message)
    logging.getLogger(__name__).info(
        "User request validation: allowed=%s reason=%s", allowed, reason
    )

    if not allowed:
        raise HTTPException(
            status_code=400,
            detail=reason,
        )

    answer = agent.run(request.message)
    return _build_three_format_response(answer)