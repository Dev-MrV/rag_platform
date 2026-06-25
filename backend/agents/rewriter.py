"""
agents/rewriter.py - Ollama-powered query rewriter.

When the grader marks retrieval as INCOMPLETE, the rewriter transforms
the original user query into an optimised web-search query using a
locally running Ollama model. No API key required.
"""
from __future__ import annotations

import logging
import ollama

from config import OLLAMA_BASE_URL, LLM_MODEL

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are an expert search query optimizer for an enterprise RAG system.\n\n"
    "Your task: Given a user's question that could NOT be answered from an internal "
    "document, rewrite it into the BEST possible web search query.\n\n"
    "Rules:\n"
    "- Be concise (max 15 words)\n"
    "- Use specific keywords and relevant domain terms\n"
    "- Remove conversational filler (e.g., 'What is', 'Can you tell me')\n"
    "- Focus on extractable facts\n"
    "- Output ONLY the rewritten query - no explanation, no quotes, no preamble."
)


def rewrite_query(original_query: str) -> str:
    """
    Use the local Ollama LLM to rewrite the user query for better web search.

    Args:
        original_query: The user's original natural language question.

    Returns:
        A concise, search-optimised query string.
    """
    client = ollama.Client(host=OLLAMA_BASE_URL)

    logger.info("Rewriting query: '%s'", original_query[:80])

    response = client.chat(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": f"Original question: {original_query}"},
        ],
        options={"temperature": 0.2, "num_predict": 64},
    )

    rewritten = response.message.content.strip()
    # Strip any accidental leading/trailing quotes or newlines
    rewritten = rewritten.strip('"\'').split("\n")[0].strip()
    logger.info("Rewritten query: '%s'", rewritten)
    return rewritten
