"""
Validation of agent outputs.

These checks should be deterministic wherever possible.
"""

import logging
import re

logger = logging.getLogger(__name__)


def validate_tool_arguments(tool_name: str, arguments: dict) -> tuple[bool, str]:
    """Validate arguments before executing a tool."""

    if tool_name == "search_public_web":
        query = arguments.get("query", "")

        if not query:
            return False, "Search query cannot be empty."

        if len(query) > 500:
            return False, "Search query is too long."

        lowered = query.lower()
        if any(pattern in lowered for pattern in (
            "private data",
            "private database",
            "confidential",
            "internal",
            "customer records",
            "medical records",
            "ssn",
        )):
            return False, "Only public-source queries are permitted."

    return True, ""


def validate_final_response(response: str) -> tuple[bool, str]:
    """
    Validate the final response before returning it to the user.

    The agent must either:
      - provide only factual statements that cite the public sources used, or
      - state that it was unable to find public evidence.
    """

    if not response.strip():
        return False, "The agent returned an empty response."

    cleaned = response.strip()
    lowered = cleaned.lower()

    progress_only_patterns = (
        "let me gather",
        "let me search",
        "i'll gather",
        "i will gather",
        "i'm gathering",
        "i am gathering",
        "i'll look for",
        "i will look for",
        "i'm looking for",
        "i am looking for",
    )
    if any(lowered.startswith(pattern) for pattern in progress_only_patterns):
        return False, "The response is progress narration, not a final answer."

    unable_to_find_patterns = (
        "unable to find public evidence",
        "unable to find evidence",
        "could not find public evidence",
        "could not find evidence",
        "i was unable to find",
        "no public evidence found",
        "no evidence found",
    )

    if any(pattern in lowered for pattern in unable_to_find_patterns):
        logger.info("Final response validation: evidence-not-found statement accepted.")
        return True, ""

    factual_claim_pattern = re.compile(
        r"\b(is|are|was|were|has|have|had|shows|show|demonstrates|demonstrate|indicates|indicate|supports|support|suggests|suggest|proves|prove|found|evidence)\b",
        re.IGNORECASE,
    )

    has_factual_claim = bool(factual_claim_pattern.search(cleaned))
    has_source_citation = bool(
        re.search(r"\[(?:\d+|[a-z]+)\]|https?://|according to|source[s]?\s*[:\-]|cited in|public source", cleaned, re.IGNORECASE)
    )

    if has_factual_claim and not has_source_citation:
        logger.warning("Final response validation failed: factual claim without source citation.")
        return False, "Any factual claim must cite the public source(s) used. Do not fabricate evidence."

    if has_factual_claim and not re.search(r"\b(?:public|source|sources|citation|cite|cited)\b", lowered):
        logger.warning("Final response validation failed: factual claim lacks explicit citation language.")
        return False, "Any factual claim must cite the public source(s) used."

    logger.info("Final response validation: response passed content and citation checks.")
    return True, ""