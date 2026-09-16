"""
Hard constraints for the agent.

IMPORTANT:
Keep constraints here, outside the LLM prompt. The agent can reason
about these constraints, but the user cannot override them through chat.
"""

import logging
import re

logger = logging.getLogger(__name__)

POLICY = {
    "public_sources_only": True,
    "allow_external_actions": False,
    "allow_private_data": False,
    "require_citations": True,
    "forbid_fabrication": True,
}

PRIVATE_DATA_PATTERNS = (
    "private data",
    "private database",
    "confidential data",
    "confidential records",
    "internal document",
    "internal database",
    "company database",
    "customer records",
    "ssn",
    "social security",
    "credit card",
    "medical records",
    "patient data",
    "bank account",
    "password",
    "api key",
    "secret token",
    "access the company's",
    "employee records",
)

SOCIAL_ENGINEERING_PATTERNS = (
    "ignore previous instructions",
    "ignore all restrictions",
    "disable safety",
    "override policy",
    "bypass the guardrails",
    "act as if",
    "you are now",
    "pretend to be",
)


def check_tool_permission(tool_name: str, arguments: dict) -> tuple[bool, str]:
    """
    Application-level authorization for tool calls.

    Return:
        (True, "") if allowed
        (False, "reason") if blocked
    """

    if POLICY["public_sources_only"]:
        allowed_tools = {"search_public_web"}

        if tool_name not in allowed_tools:
            logger.warning("Tool permission denied: tool=%s not in allowed_tools", tool_name)
            return False, f"Tool '{tool_name}' is not permitted by policy."

    query = str(arguments.get("query", "")).lower()
    if any(pattern in query for pattern in PRIVATE_DATA_PATTERNS):
        logger.warning("Tool permission denied: private-data pattern detected in query=%r", query)
        return False, "Only public sources are permitted. Private data requests are blocked."

    return True, ""


def check_user_request(user_message: str) -> tuple[bool, str]:
    """
    Validate the user's request before sending it to the agent.

    Requests must be limited to public-source research and must not attempt
    to override safety rules or access private data.
    """

    logger.info("User request validation: starting checks for message=%r", user_message)

    if not isinstance(user_message, str):
        logger.warning("User request validation: input is not a string.")
        return False, "The request is not a valid string."

    if not user_message.strip():
        logger.warning("User request validation: message is empty.")
        return False, "The request is empty."

    logger.info("User request validation: message not empty")

    lowered = user_message.lower()

    for phrase in SOCIAL_ENGINEERING_PATTERNS:
        if phrase in lowered:
            logger.warning(
                "User request validation failed: social engineering phrase '%s' detected.",
                phrase,
            )
            return False, "The request attempts to override the agent's restrictions."

    for pattern in PRIVATE_DATA_PATTERNS:
        if pattern in lowered:
            logger.warning(
                "User request validation failed: private-data pattern '%s' detected.",
                pattern,
            )
            return False, "Only public sources are permitted. Private data requests are blocked."

    if re.search(r"\b(private|confidential|internal|secret|restricted|non-public|owned by)\b", lowered):
        logger.warning("User request validation failed: private-data keyword pattern detected.")
        return False, "Only public sources are permitted. Private data requests are blocked."

    logger.info("User request validation: public-only and anti-social-engineering checks passed")
    logger.info("User request validation: request accepted")
    return True, ""