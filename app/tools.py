"""
Tools available to the agent.

The important security property is that the LLM does NOT get arbitrary
HTTP/network access. It can only request tools explicitly exposed here.
"""

import os
from typing import Any

import requests


TAVILY_SEARCH_URL = "https://api.tavily.com/search"


def search_public_web(query: str) -> dict[str, Any]:
    """
    Search public web sources through Tavily.

    This function intentionally does NOT accept an arbitrary URL.
    """

    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        return {
            "query": query,
            "sources": [],
            "error": "TAVILY_API_KEY is not configured.",
        }

    try:
        max_results = int(os.environ.get("TAVILY_MAX_RESULTS", "5"))
    except ValueError:
        max_results = 5

    payload = {
        "api_key": api_key,
        "query": query,
        "search_depth": os.environ.get("TAVILY_SEARCH_DEPTH", "basic"),
        "max_results": max(1, min(max_results, 20)),
        "include_answer": False,
        "include_raw_content": False,
    }

    try:
        response = requests.post(TAVILY_SEARCH_URL, json=payload, timeout=20)
        response.raise_for_status()
        response_data = response.json()
        results = response_data.get("results", [])
        if not isinstance(results, list):
            raise ValueError("Tavily returned an invalid results field.")
    except requests.HTTPError as error:
        try:
            provider_error = response.json().get("detail", {}).get("error")
        except (ValueError, AttributeError):
            provider_error = None

        detail = f": {provider_error}" if provider_error else ""
        return {
            "query": query,
            "sources": [],
            "error": f"Public search failed with HTTP {response.status_code}{detail}",
        }
    except (requests.RequestException, ValueError) as error:
        return {
            "query": query,
            "sources": [],
            "error": f"Public search failed: {error}",
        }

    return {
        "query": query,
        "sources": [
            {
                "title": result.get("title", "Untitled source"),
                "url": result.get("url", ""),
                "snippet": result.get("content", ""),
                "published_at": result.get("published_date"),
            }
            for result in results
            if result.get("url")
        ],
    }


TOOLS = {
    "search_public_web": search_public_web,
}