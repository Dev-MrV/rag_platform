"""
agents/web_search.py — DuckDuckGo web search fallback agent.

Executes a search for the rewritten query, retrieves top web results,
and returns cleaned text snippets as supplementary context with URLs.
"""
from __future__ import annotations

import logging
from duckduckgo_search import DDGS

logger = logging.getLogger(__name__)

_MAX_RESULTS = 5
_SNIPPET_MAX_LEN = 600  # characters per snippet


def web_search(query: str, max_results: int = _MAX_RESULTS) -> list[dict]:
    """
    Search the web via DuckDuckGo and return cleaned text snippets.

    Args:
        query:       The (rewritten) search query.
        max_results: Number of top results to fetch.

    Returns:
        List of dicts:
          { title, url, snippet }
    """
    logger.info("Web search: '%s'", query)

    results = []
    try:
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=max_results):
                snippet = (r.get("body") or "").strip()
                # Truncate overly long snippets
                if len(snippet) > _SNIPPET_MAX_LEN:
                    snippet = snippet[:_SNIPPET_MAX_LEN] + "…"
                results.append({
                    "title": r.get("title", "").strip(),
                    "url": r.get("href", ""),
                    "snippet": snippet,
                })
    except Exception as e:
        logger.error("Web search failed: %s", e)

    logger.info("Web search returned %d results.", len(results))
    return results


def format_web_context(results: list[dict]) -> str:
    """
    Format web search results into a plain text context block for the LLM.
    """
    if not results:
        return "No web results found."

    lines = []
    for i, r in enumerate(results, 1):
        lines.append(f"[Web {i}] {r['title']}\nSource: {r['url']}\n{r['snippet']}")
    return "\n\n".join(lines)
