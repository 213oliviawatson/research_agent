from unittest.mock import Mock, patch

import requests

from app.tools import TAVILY_SEARCH_URL, search_public_web


def test_search_public_web_normalizes_tavily_results():
    tavily_response = Mock()
    tavily_response.json.return_value = {
        "results": [
            {
                "title": "Candidate A study",
                "url": "https://example.org/study",
                "content": "Relevant public evidence.",
                "published_date": "2026-01-15",
            }
        ]
    }
    tavily_response.raise_for_status.return_value = None

    with patch.dict("os.environ", {"TAVILY_API_KEY": "test-key"}, clear=False):
        with patch("app.tools.requests.post", return_value=tavily_response) as post:
            result = search_public_web("candidate A effectiveness")

    assert result["sources"] == [
        {
            "title": "Candidate A study",
            "url": "https://example.org/study",
            "snippet": "Relevant public evidence.",
            "published_at": "2026-01-15",
        }
    ]
    assert post.call_args.args[0] == TAVILY_SEARCH_URL
    assert post.call_args.kwargs["json"]["api_key"] == "test-key"
    assert post.call_args.kwargs["json"]["include_answer"] is False
    assert post.call_args.kwargs["json"]["max_results"] == 5


def test_search_public_web_reports_missing_key():
    with patch.dict("os.environ", {}, clear=True):
        result = search_public_web("candidate A")

    assert result["sources"] == []
    assert result["error"] == "TAVILY_API_KEY is not configured."


def test_search_public_web_reports_provider_failure():
    with patch.dict("os.environ", {"TAVILY_API_KEY": "test-key"}, clear=False):
        with patch(
            "app.tools.requests.post",
            side_effect=requests.exceptions.Timeout("network unavailable"),
        ):
            result = search_public_web("candidate A")

    assert result["sources"] == []
    assert "Public search failed" in result["error"]


def test_search_public_web_includes_provider_http_error_detail():
    tavily_response = Mock()
    tavily_response.status_code = 432
    tavily_response.json.return_value = {
        "detail": {"error": "This request exceeds this API key's set usage limit."}
    }
    tavily_response.raise_for_status.side_effect = requests.HTTPError("432 Client Error")

    with patch.dict("os.environ", {"TAVILY_API_KEY": "test-key"}, clear=False):
        with patch("app.tools.requests.post", return_value=tavily_response):
            result = search_public_web("candidate A")

    assert result["sources"] == []
    assert "usage limit" in result["error"]


def test_search_public_web_handles_invalid_result_payload():
    tavily_response = Mock()
    tavily_response.raise_for_status.return_value = None
    tavily_response.json.return_value = {"results": {"unexpected": "object"}}

    with patch.dict("os.environ", {"TAVILY_API_KEY": "test-key"}, clear=False):
        with patch("app.tools.requests.post", return_value=tavily_response):
            result = search_public_web("candidate A")

    assert result["sources"] == []
    assert "invalid results field" in result["error"]


def test_search_public_web_clamps_invalid_result_count():
    tavily_response = Mock()
    tavily_response.raise_for_status.return_value = None
    tavily_response.json.return_value = {"results": []}

    with patch.dict(
        "os.environ",
        {"TAVILY_API_KEY": "test-key", "TAVILY_MAX_RESULTS": "not-a-number"},
        clear=False,
    ):
        with patch("app.tools.requests.post", return_value=tavily_response) as post:
            search_public_web("candidate A")

    assert post.call_args.kwargs["json"]["max_results"] == 5
