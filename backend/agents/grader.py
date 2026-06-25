"""
agents/grader.py — Local cross-encoder relevance grader.

Scores each retrieved chunk against the user query using a HuggingFace
cross-encoder model. If the average score is below GRADER_THRESHOLD,
the retrieval is marked INCOMPLETE → triggers web fallback.
"""
from __future__ import annotations

import logging
import os
from functools import lru_cache

from sentence_transformers import CrossEncoder

from config import CROSS_ENCODER_MODEL, GRADER_THRESHOLD, HF_TOKEN

logger = logging.getLogger(__name__)

# ── Model Loading ─────────────────────────────────────────────


@lru_cache(maxsize=1)
def get_cross_encoder() -> CrossEncoder:
    """Load (and cache) the cross-encoder model."""
    logger.info("Loading cross-encoder model: %s", CROSS_ENCODER_MODEL)
    if HF_TOKEN:
        os.environ.setdefault("HUGGING_FACE_HUB_TOKEN", HF_TOKEN)
    model = CrossEncoder(CROSS_ENCODER_MODEL, max_length=512)
    logger.info("Cross-encoder loaded successfully.")
    return model


# ── Grading Logic ─────────────────────────────────────────────

GradeResult = dict  # { status, scores, scored_chunks, reason }


def grade_chunks(query: str, retrieved_chunks: list[dict]) -> GradeResult:
    """
    Score each retrieved chunk against the query and decide retrieval quality.

    Args:
        query:             User's query string.
        retrieved_chunks:  List of chunk dicts from the retriever.

    Returns:
        {
          "status":        "ACCURATE" | "INCOMPLETE",
          "scores":        list of float scores per chunk,
          "scored_chunks": chunks sorted by score descending,
          "avg_score":     float,
          "reason":        str (human-readable explanation),
        }
    """
    if not retrieved_chunks:
        return {
            "status": "INCOMPLETE",
            "scores": [],
            "scored_chunks": [],
            "avg_score": 0.0,
            "reason": "No chunks were retrieved — web fallback required.",
        }

    model = get_cross_encoder()

    # Build (query, chunk_text) pairs for the cross-encoder
    pairs = [(query, chunk["text"]) for chunk in retrieved_chunks]
    raw_scores: list[float] = model.predict(pairs).tolist()

    # Attach scores to chunks
    scored = []
    for chunk, score in zip(retrieved_chunks, raw_scores):
        scored.append({**chunk, "grade_score": round(float(score), 4)})

    # Sort by score descending
    scored.sort(key=lambda x: x["grade_score"], reverse=True)

    avg_score = sum(raw_scores) / len(raw_scores)
    max_score = max(raw_scores)

    # Determine status
    if max_score >= GRADER_THRESHOLD:
        status = "ACCURATE"
        reason = (
            f"Best chunk score {max_score:.3f} ≥ threshold {GRADER_THRESHOLD}. "
            "Document context is sufficient."
        )
    else:
        status = "INCOMPLETE"
        reason = (
            f"All chunk scores below threshold {GRADER_THRESHOLD} "
            f"(best={max_score:.3f}, avg={avg_score:.3f}). "
            "Triggering query rewrite and web search fallback."
        )

    logger.info("Grader: status=%s, avg=%.3f, max=%.3f", status, avg_score, max_score)

    return {
        "status": status,
        "scores": [round(float(s), 4) for s in raw_scores],
        "scored_chunks": scored,
        "avg_score": round(avg_score, 4),
        "reason": reason,
    }
