from unittest.mock import patch

from dash import dcc, html

from app.ui import BACKEND_TIMEOUT, _linkify_source_urls, _split_response_sections, app, send_message


def _find_component(component_id):
    pending = list(app.layout.children)
    while pending:
        component = pending.pop()
        if getattr(component, "id", None) == component_id:
            return component
        pending.extend(getattr(component, "children", []) or [])
    raise AssertionError(f"Component {component_id!r} was not found")


def test_ui_has_loading_state_controls():
    submit = _find_component("submit")
    status = _find_component("status")
    message = _find_component("message")

    assert isinstance(submit, html.Button)
    assert status is not None
    assert message is not None


def test_ui_allows_time_for_agent_request():
    assert BACKEND_TIMEOUT >= 120


def test_agent_response_is_rendered_as_markdown():
    with patch("app.ui.requests.post") as post:
        post.return_value.status_code = 200
        post.return_value.json.return_value = {
            "summary": "# Ranked candidates\n\n- Candidate A",
            "audit": "## Audit\n\nEvidence",
            "data_focus": "| Candidate | Rank |\n|---|---|\n| A | 1 |",
        }

        _, summary, audit, data_focus, _ = send_message(1, "Rank candidates")

    assert isinstance(summary, dcc.Markdown)
    assert isinstance(audit, dcc.Markdown)
    assert isinstance(data_focus, dcc.Markdown)


def test_source_urls_are_explicit_external_markdown_links():
    rendered = _linkify_source_urls(
        "[Source: ScienceDirect, https://www.sciencedirect.com/article/abs/123]"
    )

    assert rendered == "[Source: ScienceDirect](https://www.sciencedirect.com/article/abs/123)"


def test_ui_uses_current_response_fields_for_separate_tabs():
    summary, audit, data_focus = _split_response_sections({
        "answer": "Executive recommendation.",
        "summary": "Executive recommendation.",
        "audit": "Detailed tradeoffs.",
        "data_focus": "| Option | Value |",
    })

    assert summary == "Executive recommendation."
    assert audit == "Detailed tradeoffs."
    assert data_focus == "| Option | Value |"
