"""Web search tool using DuckDuckGo (no API key required)."""
from __future__ import annotations


def web_search(query: str) -> str:
    """Search the web using DuckDuckGo.

    Args:
        query: The search query string.
    """
    try:
        import requests
    except ImportError:
        return "Error: 'requests' package is required. Install with: pip install requests"

    try:
        url = "https://api.duckduckgo.com/"
        params = {
            "q": query,
            "format": "json",
            "no_html": 1,
            "skip_disambig": 1,
        }
        resp = requests.get(url, params=params, timeout=15, headers={
            "User-Agent": "AgentEngine/0.1.0",
        })
        resp.raise_for_status()
        data = resp.json()

        results = []
        abstract = data.get("AbstractText", "")
        if abstract:
            results.append(f"Abstract: {abstract}")

        related = data.get("RelatedTopics", [])
        for topic in related[:5]:
            if isinstance(topic, dict) and "Text" in topic:
                results.append(f"- {topic['Text']}")

        if not results:
            return f"No results found for '{query}'."

        return "\n".join(results)
    except Exception as e:
        return f"Search error: {e}"
