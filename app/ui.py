import base64
import json
import os
import re
import requests

import dash
from dash import html, dcc, Output, Input, State

# Simple Dash UI that posts to the FastAPI backend `/chat` endpoint.
# Run this with: `python -m app.ui` (it starts a Dash dev server on 8050).

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")
BACKEND_TIMEOUT = float(os.environ.get("BACKEND_TIMEOUT", "120"))


def _linkify_source_urls(markdown: str) -> str:
    """Make model-emitted source URLs explicit external Markdown links."""
    source_citation = re.compile(
        r"\[([^\]]*?)(?:,\s*|\s+)(https?://[^\s\]]+)\]"
    )
    markdown = source_citation.sub(r"[\1](\2)", markdown)

    url_pattern = re.compile(r"https?://[^\s)\]>]+")

    def replace_url(match: re.Match[str]) -> str:
        start = match.start()
        if start and markdown[start - 1] == "(":
            return match.group(0)
        url = match.group(0)
        return f"[{url}]({url})"

    return url_pattern.sub(replace_url, markdown)


def _split_response_sections(data: dict) -> tuple[str, str, str]:
    """Read the three current backend fields independently for their tabs."""
    summary = str(data.get("summary", data.get("answer", "(no answer)")))
    audit = str(data.get("audit", ""))
    data_focus = str(data.get("data_focus", ""))
    return summary, audit, data_focus

app = dash.Dash(__name__)
app.title = "Research Agent UI"
app.index_string = """
<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>{%title%}</title>
        {%favicon%}
        {%css%}
        <style>
            :root {
                color-scheme: dark;
                --canvas: #111315;
                --panel: #191c1f;
                --panel-raised: #202428;
                --line: #30363b;
                --text: #edf2f2;
                --muted: #9da7aa;
                --accent: #67d2be;
                --accent-dark: #173b38;
                --danger: #ff9b8f;
            }

            * { box-sizing: border-box; }
            body {
                margin: 0;
                background: var(--canvas);
                color: var(--text);
                font-family: "Trebuchet MS", "Segoe UI", sans-serif;
            }
            button, textarea { font: inherit; }
            button:focus-visible, textarea:focus-visible, [role="tab"]:focus-visible {
                outline: 2px solid var(--accent);
                outline-offset: 3px;
            }
            .app-shell {
                min-height: 100vh;
                padding: 48px 24px 72px;
                background: var(--canvas);
            }
            .workspace { max-width: 1040px; margin: 0 auto; }
            .eyebrow {
                margin: 0 0 12px;
                color: var(--accent);
                font-size: 12px;
                font-weight: 700;
                letter-spacing: 0.14em;
                text-transform: uppercase;
            }
            .page-title {
                margin: 0;
                font-family: Georgia, "Times New Roman", serif;
                font-size: clamp(34px, 5vw, 56px);
                font-weight: 400;
                letter-spacing: 0;
                line-height: 1.05;
            }
            .page-intro {
                max-width: 650px;
                margin: 16px 0 34px;
                color: var(--muted);
                font-size: 16px;
                line-height: 1.6;
            }
            .query-panel {
                padding: 24px;
                border: 1px solid var(--line);
                border-radius: 8px;
                background: rgba(25, 28, 31, 0.94);
                box-shadow: 0 18px 50px rgba(0, 0, 0, 0.2);
            }
            .field-label {
                display: block;
                margin-bottom: 10px;
                color: var(--text);
                font-size: 14px;
                font-weight: 700;
            }
            .query-input {
                width: 100%;
                min-height: 132px;
                resize: vertical;
                padding: 16px;
                border: 1px solid #3a4347;
                border-radius: 6px;
                background: #121517;
                color: var(--text);
                font-size: 16px;
                line-height: 1.5;
            }
            .query-input::placeholder { color: #758084; }
            .query-actions {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 16px;
                margin-top: 18px;
            }
            .query-hint { color: var(--muted); font-size: 13px; line-height: 1.4; }
            .submit-button {
                min-width: 124px;
                padding: 11px 20px;
                border: 1px solid var(--accent);
                border-radius: 5px;
                background: var(--accent);
                color: #10211f;
                cursor: pointer;
                font-weight: 700;
                transition: background 160ms ease, transform 160ms ease;
            }
            .submit-button:hover:not(:disabled) { background: #8be2d0; transform: translateY(-1px); }
            .submit-button:disabled { cursor: wait; opacity: 0.55; }
            .status-line {
                min-height: 24px;
                margin-top: 14px;
                color: var(--accent);
                font-size: 14px;
            }
            .results-heading {
                display: flex;
                align-items: baseline;
                justify-content: space-between;
                gap: 16px;
                margin: 42px 0 14px;
            }
            .results-heading h2 { margin: 0; font-size: 20px; font-weight: 700; }
            .results-heading span { color: var(--muted); font-size: 13px; }
            .result-tabs { border-bottom: 1px solid var(--line); }
            .result-tab {
                padding: 13px 16px !important;
                border: 0 !important;
                background: transparent !important;
                color: var(--muted) !important;
                font-size: 14px !important;
                font-weight: 700 !important;
            }
            .result-tab--selected {
                border-bottom: 2px solid var(--accent) !important;
                color: var(--text) !important;
            }
            .result-output {
                min-height: 180px;
                margin-top: 14px;
                padding: 22px;
                border: 1px solid var(--line);
                border-radius: 8px;
                background: var(--panel);
                color: #dce4e4;
                font-size: 15px;
                line-height: 1.65;
            }
            .download-area { margin-top: 14px; }
            .download-button {
                display: inline-block;
                padding: 10px 15px;
                border: 1px solid #49645f;
                border-radius: 5px;
                background: var(--accent-dark);
                color: var(--accent);
                text-decoration: none;
                font-size: 14px;
                font-weight: 700;
            }
            @media (max-width: 640px) {
                .app-shell { padding: 30px 16px 48px; }
                .query-panel { padding: 18px; }
                .query-actions, .results-heading { align-items: flex-start; flex-direction: column; }
                .submit-button { width: 100%; }
                .result-tab { padding: 12px 9px !important; font-size: 12px !important; }
            }
        </style>
    </head>
    <body>
        {%app_entry%}
        <footer>{%config%}{%scripts%}{%renderer%}</footer>
    </body>
</html>
"""

app.layout = html.Div(
    [
        html.Div(
            [
                html.Div("PUBLIC EVIDENCE WORKSPACE", className="eyebrow"),
                html.H1("Research Agent", className="page-title"),
                html.P(
                    "Turn a research question into a cited, ranked view of the available public evidence.",
                    className="page-intro",
                ),
                html.Div(
                    [
                        html.Label("What would you like to investigate?", htmlFor="message", className="field-label"),
                        dcc.Textarea(
                            id="message",
                            placeholder="Example: Compare candidates A, B, and C using public evidence and rank them by effectiveness.",
                            className="query-input",
                        ),
                        html.Div(
                            [
                                html.Div("Public sources only. Ask for ranking criteria when it matters.", className="query-hint"),
                                html.Button("Run research", id="submit", n_clicks=0, className="submit-button"),
                            ],
                            className="query-actions",
                        ),
                        html.Div(id="status", className="status-line", role="status", **{"aria-live": "polite"}),
                    ],
                    className="query-panel",
                ),
                html.Div(
                    [
                        html.H2("Research output"),
                        html.Span("Citations, caveats, and ranking detail", className="results-caption"),
                    ],
                    className="results-heading",
                ),
                dcc.Tabs(
                    id="result-tabs",
                    value="summary-tab",
                    className="result-tabs",
                    children=[
                        dcc.Tab(label="Summary", value="summary-tab", className="result-tab", selected_className="result-tab--selected"),
                        dcc.Tab(label="Technical / Audit", value="audit-tab", className="result-tab", selected_className="result-tab--selected"),
                        dcc.Tab(label="Data Focus", value="data-tab", className="result-tab", selected_className="result-tab--selected"),
                    ],
                ),
                html.Div(id="summary-output", className="result-output", style={"display": "block"}),
                html.Div(id="audit-output", className="result-output", style={"display": "none"}),
                html.Div(id="data-output", className="result-output", style={"display": "none"}),
                html.Div(id="download-area", className="download-area"),
            ],
            className="workspace",
        )
    ],
    className="app-shell",
)


@app.callback(
    Output("status", "children"),
    Output("summary-output", "children"),
    Output("audit-output", "children"),
    Output("data-output", "children"),
    Output("download-area", "children"),
    Input("submit", "n_clicks"),
    State("message", "value"),
    prevent_initial_call=True,
    running=[
        (Output("submit", "disabled"), True, False),
        (Output("message", "disabled"), True, False),
        (Output("result-tabs", "disabled"), True, False),
        (Output("status", "children"), "Working on your request... This can take a moment.", ""),
    ],
)
def send_message(n_clicks, message):
    if not n_clicks:
        return "", "", "", "", ""

    if not message or not message.strip():
        return "Please enter a message.", "Please enter a message.", "", "", ""

    try:
        resp = requests.post(
            f"{BACKEND_URL}/chat",
            json={"message": message},
            timeout=BACKEND_TIMEOUT,
        )
    except requests.exceptions.Timeout:
        return (
            f"The request took longer than {BACKEND_TIMEOUT:g} seconds. "
            "Claude may still be processing the research; please try again.",
            "",
            "",
            "",
            "",
        )
    except Exception as e:
        return f"Error contacting backend: {e}", "", "", "", ""

    if resp.status_code != 200:
        try:
            detail = resp.json()
        except Exception:
            detail = resp.text

        return f"Backend returned {resp.status_code}", str(detail), "", "", ""

    data = resp.json()
    summary, audit, data_focus = _split_response_sections(data)

    summary_markdown = dcc.Markdown(_linkify_source_urls(summary), link_target="_blank")
    audit_markdown = dcc.Markdown(_linkify_source_urls(audit), link_target="_blank")
    data_focus_markdown = dcc.Markdown(_linkify_source_urls(data_focus), link_target="_blank")

    download = data.get("download")
    if download and download.get("content"):
        content = download["content"]
        filename = download.get("filename", "research_report.pdf")
        mime_type = download.get("mime_type", "application/pdf")
        if download.get("encoding") == "base64":
            encoded_content = content
        else:
            encoded_content = base64.b64encode(content.encode("utf-8")).decode("ascii")
        data_uri = "data:{};base64,{}".format(mime_type, encoded_content)
        download_button = html.A(
            "Download PDF report",
            href=data_uri,
            download=filename,
            className="download-button",
        )
    else:
        download_button = ""

    return "Done.", summary_markdown, audit_markdown, data_focus_markdown, download_button


@app.callback(
    Output("summary-output", "style"),
    Output("audit-output", "style"),
    Output("data-output", "style"),
    Input("result-tabs", "value"),
)
def update_tabs(tab_value):
    summary_style = {"display": "block" if tab_value == "summary-tab" else "none"}
    audit_style = {"display": "block" if tab_value == "audit-tab" else "none"}
    data_style = {"display": "block" if tab_value == "data-tab" else "none"}
    return summary_style, audit_style, data_style


if __name__ == "__main__":
    # Allow overriding the port for convenience.
    host = os.environ.get("DASH_HOST", "0.0.0.0")
    port = int(os.environ.get("DASH_PORT", 8050))
    app.run(debug=True, host=host, port=port)
