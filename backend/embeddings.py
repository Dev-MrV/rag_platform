"""
embeddings.py - Ollama-powered text embedding generation and cosine similarity retrieval.
Uses the local nomic-embed-text model via Ollama for document and query embeddings.
No API key required - fully local inference.
"""
from __future__ import annotations

import logging
import numpy as np
import ollama

from config import OLLAMA_BASE_URL, EMBEDDING_MODEL, TOP_K
from database import chunks

logger = logging.getLogger(__name__)

# Ollama client pointed at local server
_client = ollama.Client(host=OLLAMA_BASE_URL)


def embed_texts(texts: list[str]) -> list[list[float]]:
    """
    Generate embeddings for a list of text strings using Ollama.
    Processes texts one by one (Ollama embed supports batches via input list).
    """
    if not texts:
        return []

    response = _client.embed(model=EMBEDDING_MODEL, input=texts)
    return [list(emb) for emb in response.embeddings]


def embed_query(query: str) -> list[float]:
    """Embed a single query string."""
    return embed_texts([query])[0]


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Compute cosine similarity between two embedding vectors."""
    a = np.array(vec_a, dtype=np.float32)
    b = np.array(vec_b, dtype=np.float32)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


def semantic_search(
    query: str,
    doc_ids: list[str] | None = None,
    top_k: int = TOP_K,
) -> list[dict]:
    """
    Retrieve the top_k most semantically similar chunks from MongoDB.

    Args:
        query:   User query string.
        doc_ids: Optional list of doc_ids to scope the search.
        top_k:   Number of results to return.

    Returns:
        List of chunk dicts sorted by descending similarity score,
        each augmented with a 'similarity' field.
    """
    query_vec = embed_query(query)

    mongo_filter: dict = {}
    if doc_ids:
        mongo_filter["doc_id"] = {"$in": doc_ids}

    candidate_chunks = list(
        chunks().find(
            mongo_filter,
            {"_id": 0, "embedding": 1, "text": 1,
             "doc_id": 1, "filename": 1,
             "page": 1, "chunk_index": 1}
        )
    )

    if not candidate_chunks:
        logger.warning("No document chunks found in the database.")
        return []

    scored = []
    for chunk in candidate_chunks:
        if not chunk.get("embedding"):
            continue
        score = cosine_similarity(query_vec, chunk["embedding"])
        scored.append({**chunk, "similarity": round(score, 4)})

    scored.sort(key=lambda x: x["similarity"], reverse=True)
    results = scored[:top_k]

    logger.info(
        "Semantic search: %d chunks retrieved (top score=%.3f)",
        len(results),
        results[0]["similarity"] if results else 0,
    )
    return results
