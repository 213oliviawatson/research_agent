import os
from types import SimpleNamespace
from unittest.mock import patch

from app.agent import Agent


def test_agent_uses_anthropic_client_when_available():
    with patch.dict(
        os.environ,
        {"ANTHROPIC_API_KEY": "test-key", "USE_MOCK_ANTHROPIC": "0"},
        clear=False,
    ):
        with patch("app.agent.Anthropic") as mocked:
            agent = Agent()

    mocked.assert_called_once_with(api_key="test-key")
    assert agent.model == os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")


def test_agent_uses_mock_when_configured():
    with patch.dict(os.environ, {"USE_MOCK_ANTHROPIC": "true"}, clear=False):
        agent = Agent()

    assert agent.client.__class__.__name__ == "_MockAnthropic"


def test_tool_definitions_use_anthropic_schema():
    tool = Agent._tool_definitions()[0]

    assert tool["name"] == "search_public_web"
    assert "type" not in tool
    assert "input_schema" in tool
    assert "parameters" not in tool


def test_multiple_tool_results_share_one_anthropic_user_turn():
    class FakeMessages:
        def __init__(self):
            self.calls = []

        def create(self, **kwargs):
            self.calls.append(kwargs)
            if len(self.calls) == 1:
                return SimpleNamespace(content=[
                    SimpleNamespace(type="tool_use", id="one", name="search_public_web", input={"query": "A"}),
                    SimpleNamespace(type="tool_use", id="two", name="search_public_web", input={"query": "B"}),
                ])
            return SimpleNamespace(content=[SimpleNamespace(
                type="text", text=(
                    "=== PI SUMMARY ===\nSources: [A] and [B].\n"
                    "=== TECHNICAL AUDIT ===\nPublic source review: [A] and [B].\n"
                    "=== DATA FOCUS ===\nNo public evidence found."
                )
            )])

    fake_messages = FakeMessages()
    agent = object.__new__(Agent)
    agent.client = SimpleNamespace(messages=fake_messages)
    agent.model = "claude-sonnet-5"

    with patch("app.agent.TOOLS", {
        "search_public_web": lambda query: {"query": query, "sources": []},
    }):
        agent.run("Compare candidates A and B.")

    follow_up_messages = fake_messages.calls[1]["messages"]
    assert follow_up_messages[-1]["role"] == "user"
    assert len(follow_up_messages[-1]["content"]) == 2
    assert {item["tool_use_id"] for item in follow_up_messages[-1]["content"]} == {"one", "two"}


def test_agent_stops_requesting_search_after_budget():
    class FakeMessages:
        def __init__(self):
            self.calls = []

        def create(self, **kwargs):
            self.calls.append(kwargs)
            if len(self.calls) <= 2:
                return SimpleNamespace(content=[SimpleNamespace(
                    type="tool_use",
                    id=f"call-{len(self.calls)}",
                    name="search_public_web",
                    input={"query": "candidate"},
                )])
            return SimpleNamespace(content=[SimpleNamespace(
                type="text", text=(
                    "=== PI SUMMARY ===\nNo public evidence found for the candidate.\n"
                    "=== TECHNICAL AUDIT ===\nNo public evidence found for the candidate.\n"
                    "=== DATA FOCUS ===\nNo public evidence found for the candidate."
                )
            )])

    fake_messages = FakeMessages()
    agent = object.__new__(Agent)
    agent.client = SimpleNamespace(messages=fake_messages)
    agent.model = "claude-sonnet-5"

    with patch("app.agent.TOOLS", {
        "search_public_web": lambda query: {"query": query, "sources": []},
    }):
        answer = agent.run("Find a candidate.")

    assert "=== PI SUMMARY ===" in answer
    assert "No public evidence found for the candidate." in answer
    assert len(fake_messages.calls) == 3
    assert fake_messages.calls[-1]["tools"] == []


def test_agent_retries_empty_claude_response_without_search():
    class FakeMessages:
        def __init__(self):
            self.calls = []

        def create(self, **kwargs):
            self.calls.append(kwargs)
            if len(self.calls) == 1:
                return SimpleNamespace(content=[])
            return SimpleNamespace(content=[SimpleNamespace(
                type="text", text=(
                    "=== PI SUMMARY ===\nNo public evidence found after review.\n"
                    "=== TECHNICAL AUDIT ===\nNo public evidence found after review.\n"
                    "=== DATA FOCUS ===\nNo public evidence found after review."
                )
            )])

    fake_messages = FakeMessages()
    agent = object.__new__(Agent)
    agent.client = SimpleNamespace(messages=fake_messages)
    agent.model = "claude-sonnet-5"

    answer = agent.run("Find public evidence.")

    assert "=== DATA FOCUS ===" in answer
    assert "No public evidence found after review." in answer
    assert fake_messages.calls[1]["tools"] == []


def test_agent_repairs_missing_citations_without_new_search():
    class FakeMessages:
        def __init__(self):
            self.calls = []

        def create(self, **kwargs):
            self.calls.append(kwargs)
            if len(self.calls) == 1:
                return SimpleNamespace(content=[SimpleNamespace(
                    type="text", text="Candidate A is effective."
                )])
            return SimpleNamespace(content=[SimpleNamespace(
                type="text",
                text=(
                    "=== PI SUMMARY ===\nCandidate A is effective [public source](https://example.org/evidence).\n"
                    "=== TECHNICAL AUDIT ===\nCandidate A is effective [public source](https://example.org/evidence).\n"
                    "=== DATA FOCUS ===\nCandidate A: effectiveness reported in the public source."
                ),
            )])

    fake_messages = FakeMessages()
    agent = object.__new__(Agent)
    agent.client = SimpleNamespace(messages=fake_messages)
    agent.model = "claude-sonnet-5"

    answer = agent.run("Find evidence for candidate A.")

    assert "https://example.org/evidence" in answer
    assert fake_messages.calls[1]["tools"] == []


def test_extract_text_supports_anthropic_model_dump_blocks():
    class ModelDumpBlock:
        type = "text"
        text = None

        def model_dump(self):
            return {"type": "text", "text": "No public evidence found."}

    assert Agent._extract_text([ModelDumpBlock()]) == "No public evidence found."


def test_progress_response_continues_research_with_tools():
    class FakeMessages:
        def __init__(self):
            self.calls = []

        def create(self, **kwargs):
            self.calls.append(kwargs)
            if len(self.calls) == 1:
                return SimpleNamespace(content=[SimpleNamespace(
                    type="text",
                    text="Let me gather more specific data on MgO and Y2O3.",
                )])
            if len(self.calls) == 2:
                return SimpleNamespace(content=[SimpleNamespace(
                    type="tool_use",
                    id="search-1",
                    name="search_public_web",
                    input={"query": "MgO Y2O3 oxide dielectric phase stability"},
                )])
            return SimpleNamespace(content=[SimpleNamespace(
                type="text",
                text=(
                    "=== PI SUMMARY ===\nNo public evidence found for the requested comparison.\n"
                    "=== TECHNICAL AUDIT ===\nNo public evidence found for the requested comparison.\n"
                    "=== DATA FOCUS ===\nNo public evidence found for the requested comparison."
                ),
            )])

    fake_messages = FakeMessages()
    agent = object.__new__(Agent)
    agent.client = SimpleNamespace(messages=fake_messages)
    agent.model = "claude-sonnet-5"

    with patch("app.agent.TOOLS", {
        "search_public_web": lambda query: {"query": query, "sources": []},
    }):
        answer = agent.run("Compare MgO and Y2O3.")

    assert "=== TECHNICAL AUDIT ===" in answer
    assert "No public evidence found for the requested comparison." in answer
    assert fake_messages.calls[1]["tools"]
