"""
agents/retriever.py — PDF parsing, chunking, embedding indexing, and chunk retrieval.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from pypdf import PdfReader
from database import chunks
from embeddings import embed_texts, semantic_search
from config import CHUNK_SIZE, CHUNK_OVERLAP, TOP_K

logger = logging.getLogger(__name__)


# ── PDF Parsing ───────────────────────────────────────────────

def parse_pdf(file_bytes: bytes) -> list[dict]:
    """
    Extract text from all pages of a PDF.

    Returns:
        List of dicts: { page: int, text: str }
    """
    import io
    reader = PdfReader(io.BytesIO(file_bytes))
    pages = []
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        text = text.strip()
        if text:
            pages.append({"page": i + 1, "text": text})
    return pages


# ── Text Chunking ─────────────────────────────────────────────

def chunk_text(page_text: str, page: int, doc_id: str, filename: str) -> list[dict]:
    """
    Split a page's text into overlapping character chunks.

    Returns:
        List of chunk dicts ready for MongoDB insertion.
    """
    text = page_text
    chunk_list = []
    start = 0
    chunk_index = 0

    while start < len(text):
        end = min(start + CHUNK_SIZE, len(text))
        chunk = text[start:end].strip()
        if chunk:
            chunk_list.append({
                "doc_id": doc_id,
                "filename": filename,
                "page": page,
                "chunk_index": chunk_index,
                "text": chunk,
                "char_start": start,
                "char_end": end,
                "embedding": [],    # filled after batch embed
                "indexed_at": datetime.now(timezone.utc),
            })
            chunk_index += 1
        start += CHUNK_SIZE - CHUNK_OVERLAP

    return chunk_list


# ── Indexing Pipeline ─────────────────────────────────────────

async def index_pdf(file_bytes: bytes, filename: str) -> dict:
    """
    Full pipeline: parse PDF → chunk pages → embed chunks → store in MongoDB.

    Returns:
        { doc_id, filename, total_pages, total_chunks }
    """
    doc_id = str(uuid.uuid4())
    logger.info("Indexing '%s' (doc_id=%s)", filename, doc_id)

    # 1. Parse
    pages = parse_pdf(file_bytes)
    if not pages:
        raise ValueError(f"No extractable text found in '{filename}'.")

    # 2. Chunk all pages
    all_chunks: list[dict] = []
    for page_data in pages:
        page_chunks = chunk_text(
            page_text=page_data["text"],
            page=page_data["page"],
            doc_id=doc_id,
            filename=filename,
        )
        all_chunks.extend(page_chunks)

    logger.info("'%s': %d pages → %d chunks", filename, len(pages), len(all_chunks))

    # 3. Batch embed
    texts = [c["text"] for c in all_chunks]
    embeddings = embed_texts(texts)

    for chunk, emb in zip(all_chunks, embeddings):
        chunk["embedding"] = emb

    # 4. Store in MongoDB
    if all_chunks:
        chunks().insert_many(all_chunks)

    return {
        "doc_id": doc_id,
        "filename": filename,
        "total_pages": len(pages),
        "total_chunks": len(all_chunks),
    }


# ── Retrieval ─────────────────────────────────────────────────

def retrieve_chunks(query: str, doc_ids: list[str] | None = None) -> list[dict]:
    """
    Retrieve top-k semantically relevant chunks for a query.

    Returns a list of chunk dicts with a 'similarity' score.
    """
    results = semantic_search(query=query, doc_ids=doc_ids, top_k=TOP_K)
    logger.info("Retrieved %d chunks for query: '%s'", len(results), query[:60])
    return results


def delete_document(doc_id: str) -> int:
    """Remove all chunks for a given doc_id. Returns deleted count."""
    result = chunks().delete_many({"doc_id": doc_id})
    logger.info("Deleted %d chunks for doc_id=%s", result.deleted_count, doc_id)
    return result.deleted_count


def list_documents() -> list[dict]:
    """Return a summary of all distinct indexed documents."""
    pipeline = [
        {
            "$group": {
                "_id": "$doc_id",
                "filename": {"$first": "$filename"},
                "total_chunks": {"$sum": 1},
                "total_pages": {"$max": "$page"},
                "indexed_at": {"$min": "$indexed_at"},
            }
        },
        {"$sort": {"indexed_at": -1}},
    ]
    results = list(chunks().aggregate(pipeline))
    return [
        {
            "doc_id": r["_id"],
            "filename": r["filename"],
            "total_chunks": r["total_chunks"],
            "total_pages": r["total_pages"],
            "indexed_at": r["indexed_at"].isoformat() if r["indexed_at"] else None,
        }
        for r in results
    ]
