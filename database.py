"""
database.py — MongoDB connection manager and collection accessors.
Collections:
  - client_profiles      : Client display names and upload history
  - interaction_logs     : Full per-query CRAG trace logs
  - document_chunks      : PDF text chunks with embeddings
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from pymongo import MongoClient, ASCENDING
from pymongo.collection import Collection
from pymongo.errors import ConnectionFailure

from config import (
    MONGO_URI, DB_NAME,
    COL_PROFILES, COL_LOGS, COL_CHUNKS,
)

logger = logging.getLogger(__name__)

# ── Singleton Connection ──────────────────────────────────────
_client: MongoClient | None = None


def get_client() -> MongoClient:
    global _client
    if _client is None:
        _client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        try:
            _client.admin.command("ping")
            logger.info("Connected to MongoDB at %s", MONGO_URI)
        except ConnectionFailure as e:
            logger.error("Cannot connect to MongoDB: %s", e)
            raise
    return _client


def get_db():
    return get_client()[DB_NAME]


# ── Collection Accessors ──────────────────────────────────────

def profiles() -> Collection:
    return get_db()[COL_PROFILES]


def logs() -> Collection:
    return get_db()[COL_LOGS]


def chunks() -> Collection:
    return get_db()[COL_CHUNKS]


# ── Initialization ────────────────────────────────────────────

def init_indexes() -> None:
    """Create indexes for efficient querying."""
    # Document chunks: index on doc_id and chunk_index
    chunks().create_index([("doc_id", ASCENDING), ("chunk_index", ASCENDING)])
    chunks().create_index([("filename", ASCENDING)])

    # Interaction logs: index on session_id and timestamp
    logs().create_index([("session_id", ASCENDING)])
    logs().create_index([("timestamp", ASCENDING)])

    logger.info("MongoDB indexes initialized.")


# ── Helper Functions ──────────────────────────────────────────

def save_interaction_log(
    session_id: str,
    query: str,
    steps: list[dict],
    final_answer: str,
    citations: list[dict],
    pipeline_path: list[str],
) -> str:
    """Persist a completed CRAG interaction to MongoDB."""
    doc = {
        "session_id": session_id,
        "query": query,
        "steps": steps,
        "final_answer": final_answer,
        "citations": citations,
        "pipeline_path": pipeline_path,
        "timestamp": datetime.now(timezone.utc),
    }
    result = logs().insert_one(doc)
    return str(result.inserted_id)


def upsert_client_profile(session_id: str, display_name: str = "Anonymous") -> None:
    profiles().update_one(
        {"session_id": session_id},
        {
            "$set": {"display_name": display_name, "last_active": datetime.now(timezone.utc)},
            "$setOnInsert": {"created_at": datetime.now(timezone.utc)},
        },
        upsert=True,
    )
