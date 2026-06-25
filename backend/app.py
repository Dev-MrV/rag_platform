"""
app.py — FastAPI entrypoint for the Enterprise RAG Platform.

Endpoints:
  POST   /upload                — Upload and index a PDF document
  GET    /documents             — List all indexed documents
  DELETE /documents/{doc_id}   — Delete a document and its chunks
  WS     /chat                  — Real-time CRAG pipeline WebSocket
  GET    /health                — Health check
"""
from __future__ import annotations

import json
import logging
import sys
import uuid
from contextlib import asynccontextmanager

import uvicorn
from fastapi import (
    FastAPI, File, Form, UploadFile,
    WebSocket, WebSocketDisconnect, HTTPException
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# ── Logging ───────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# ── App Lifespan ──────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: init DB indexes and pre-load cross-encoder model."""
    logger.info("Starting Enterprise RAG Platform…")
    try:
        from database import init_indexes
        init_indexes()
    except Exception as e:
        logger.error("MongoDB init failed: %s", e)

    try:
        from agents.grader import get_cross_encoder
        get_cross_encoder()  # warm up model
    except Exception as e:
        logger.warning("Cross-encoder pre-load failed: %s", e)

    logger.info("Platform ready.")
    yield
    logger.info("Shutting down.")


# ── FastAPI App ───────────────────────────────────────────────
app = FastAPI(
    title="Enterprise RAG Platform",
    description="Self-correcting Retrieval-Augmented Generation with CRAG pipeline",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── REST Endpoints ────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "platform": "Enterprise RAG Platform v1.0"}


@app.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    session_id: str = Form(default="anonymous"),
):
    """Upload and index a PDF document."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    file_bytes = await file.read()
    if len(file_bytes) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    from agents.retriever import index_pdf
    from database import upsert_client_profile

    try:
        upsert_client_profile(session_id)
        result = await index_pdf(file_bytes, file.filename)
        logger.info("Indexed document: %s", result)
        return JSONResponse(content={"success": True, **result})
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error("Upload error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Indexing failed: {e}")


@app.get("/documents")
async def list_documents():
    """Return a list of all indexed documents."""
    from agents.retriever import list_documents as _list
    docs = _list()
    return {"documents": docs, "count": len(docs)}


@app.delete("/documents/{doc_id}")
async def delete_document(doc_id: str):
    """Delete a document and all its indexed chunks."""
    from agents.retriever import delete_document as _delete
    deleted = _delete(doc_id)
    return {"success": True, "deleted_chunks": deleted, "doc_id": doc_id}


# ── WebSocket Chat ────────────────────────────────────────────

@app.websocket("/chat")
async def websocket_chat(websocket: WebSocket):
    """
    Real-time CRAG pipeline via WebSocket.

    Client sends:
      { "query": str, "doc_ids": [str], "session_id": str }

    Server streams:
      Multiple JSON event objects during pipeline execution,
      ending with a "complete" event containing the final answer.
    """
    await websocket.accept()
    logger.info("WebSocket connection accepted.")

    try:
        while True:
            raw = await websocket.receive_text()

            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"error": "Invalid JSON payload."})
                continue

            query = payload.get("query", "").strip()
            if not query:
                await websocket.send_json({"error": "Query cannot be empty."})
                continue

            doc_ids: list[str] = payload.get("doc_ids", [])
            session_id: str = payload.get("session_id", str(uuid.uuid4()))

            logger.info("WS query: '%s' | session=%s | docs=%s",
                        query[:60], session_id, doc_ids)

            from rag_pipeline import run_crag_pipeline
            from database import save_interaction_log

            steps: list[dict] = []
            final_answer = ""
            citations: list[dict] = []
            pipeline_path: list[str] = []

            # Stream pipeline events to client
            async for event in run_crag_pipeline(query, doc_ids, session_id):
                await websocket.send_json(event)

                steps.append(event)
                if event.get("step") == "complete":
                    final_answer = event.get("answer", "")
                    citations = event.get("citations", [])
                    pipeline_path = event.get("pipeline_path", [])

            # Persist the full interaction to MongoDB
            try:
                save_interaction_log(
                    session_id=session_id,
                    query=query,
                    steps=steps,
                    final_answer=final_answer,
                    citations=citations,
                    pipeline_path=pipeline_path,
                )
            except Exception as e:
                logger.warning("Failed to save interaction log: %s", e)

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected.")
    except Exception as e:
        logger.error("WebSocket error: %s", e, exc_info=True)
        try:
            await websocket.send_json({"error": str(e), "step": "error"})
        except Exception:
            pass


# ── Entrypoint ────────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
