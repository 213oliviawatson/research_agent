from app.validation import (
    validate_final_response,
    validate_tool_arguments,
)


def test_search_requires_query():
    valid, _ = validate_tool_arguments(
        "search_public_web",
        {},
    )

    assert not valid


def test_valid_search():
    valid, _ = validate_tool_arguments(
        "search_public_web",
        {"query": "candidate A"},
    )

    assert valid


def test_response_cannot_be_empty():
    valid, _ = validate_final_response("")

    assert not valid


def test_progress_narration_is_not_a_final_response():
    valid, reason = validate_final_response(
        "Let me gather more specific data on MgO, Y2O3, and phase stability/toxicity considerations."
    )

    assert not valid
    assert "progress narration" in reason


def test_claim_without_source_is_rejected():
    valid, reason = validate_final_response(
        "The evidence shows candidate A is effective."
    )

    assert not valid
    assert "cite" in reason.lower()


def test_unable_to_find_evidence_is_allowed():
    valid, reason = validate_final_response(
        "I was unable to find public evidence for candidate A."
    )

    assert valid
    assert reason == ""