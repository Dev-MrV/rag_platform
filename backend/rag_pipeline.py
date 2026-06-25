"""
rag_pipeline.py - LangGraph-based Corrective RAG (CRAG) pipeline.

Graph nodes:
  retrieve    - fetch top-k chunks from MongoDB
  grade       - cross-encoder relevance scoring
  rewrite     - Gemini query optimiser (triggered on INCOMPLETE)
  web_search  - DuckDuckGo fallback (triggered on INCOMPLETE)
  generate    - Gemini final answer with citations

Conditional edges:
  grade -> (ACCURATE) -> generate
  grade -> (INCOMPLETE) -> rewrite -> web_search -> generate
"""
from __future__ import annotations

import asyncio
import logging
from typing import TypedDict, AsyncIterator

from langgraph.graph import StateGraph, END

from agents.retriever import retrieve_chunks
from agents.grader import grade_chunks
from agents.rewriter import rewrite_query
from agents.web_search import web_search, format_web_context
import ollama
from config import OLLAMA_BASE_URL, LLM_MODEL

logger = logging.getLogger(__name__)


# ── State Definition ──────────────────────────────────────────

class CRAGState(TypedDict, total=False):
    query: str
    doc_ids: list[str]
    retrieved_chunks: list[dict]
    grade_result: dict
    rewritten_query: str
    web_results: list[dict]
    context: str
    answer: str
    citations: list[dict]
    pipeline_path: list[str]
    events: list[dict]          # streamed to WebSocket


# ── Helpers ───────────────────────────────────────────────────

def _push_event(state: CRAGState, event: dict) -> None:
    """Append an event to the state's event list."""
    state.setdefault("events", [])
    state["events"].append(event)


def _mark_path(state: CRAGState, node: str) -> None:
    state.setdefault("pipeline_path", [])
    state["pipeline_path"].append(node)


# ── Node Functions ────────────────────────────────────────────

def node_retrieve(state: CRAGState) -> CRAGState:
    _mark_path(state, "Retrieve")
    query = state["query"]
    doc_ids = state.get("doc_ids")

    _push_event(state, {
        "step": "retrieve",
        "status": "running",
        "message": f"Searching document store for: \"{query[:80]}\"",
    })

    results = retrieve_chunks(query, doc_ids)

    _push_event(state, {
        "step": "retrieve",
        "status": "done",
        "message": f"Retrieved {len(results)} candidate chunks.",
        "chunks_count": len(results),
    })

    state["retrieved_chunks"] = results
    return state


def node_grade(state: CRAGState) -> CRAGState:
    _mark_path(state, "Grade")
    query = state["query"]
    retrieved = state.get("retrieved_chunks", [])

    _push_event(state, {
        "step": "grade",
        "status": "running",
        "message": "Running cross-encoder relevance scoring…",
    })

    result = grade_chunks(query, retrieved)

    _push_event(state, {
        "step": "grade",
        "status": result["status"],
        "message": result["reason"],
        "avg_score": result["avg_score"],
        "scores": result["scores"],
    })

    state["grade_result"] = result
    # Replace retrieved_chunks with graded+sorted version
    state["retrieved_chunks"] = result["scored_chunks"]
    return state


def node_rewrite(state: CRAGState) -> CRAGState:
    _mark_path(state, "Rewrite")
    original = state["query"]

    _push_event(state, {
        "step": "rewrite",
        "status": "running",
        "message": "Gemini is rewriting the query for web search...",
    })

    rewritten = rewrite_query(original)

    _push_event(state, {
        "step": "rewrite",
        "status": "done",
        "message": f"Query rewritten: \"{rewritten}\"",
        "rewritten_query": rewritten,
    })

    state["rewritten_query"] = rewritten
    return state


def node_web_search(state: CRAGState) -> CRAGState:
    _mark_path(state, "Web Search")
    query = state.get("rewritten_query") or state["query"]

    _push_event(state, {
        "step": "web_search",
        "status": "running",
        "message": f"Searching the web for: \"{query}\"",
    })

    results = web_search(query)

    _push_event(state, {
        "step": "web_search",
        "status": "done",
        "message": f"Found {len(results)} web result(s).",
        "web_results_count": len(results),
        "sources": [{"title": r["title"], "url": r["url"]} for r in results],
    })

    state["web_results"] = results
    return state


def node_generate(state: CRAGState) -> CRAGState:
    _mark_path(state, "Generate")
    query = state["query"]
    retrieved = state.get("retrieved_chunks", [])
    web_results = state.get("web_results", [])

    # Group chunks by unique document filename
    unique_docs = {}
    for chunk in retrieved[:5]:
        fname = chunk["filename"]
        if fname not in unique_docs:
            unique_docs[fname] = []
        unique_docs[fname].append(chunk)

    doc_context_parts = []
    citations: list[dict] = []

    for doc_idx, (filename, chunks) in enumerate(unique_docs.items(), start=1):
        doc_text_parts = []
        for c in chunks:
            doc_text_parts.append(f"--- Page {c['page']} ---\n{c['text']}")
            citations.append({
                "type": "document",
                "label": f"Doc {doc_idx}",
                "filename": filename,
                "page": c["page"],
                "snippet": c["text"][:200],
                "grade_score": c.get("grade_score", c.get("similarity", 0)),
            })
            
        combined_text = "\n".join(doc_text_parts)
        doc_context_parts.append(f"[Doc {doc_idx}] (File: {filename})\n{combined_text}")

    # Augment with web results if present
    web_context = ""
    if web_results:
        web_context = "\n\n--- Web Search Results ---\n" + format_web_context(web_results)
        for r in web_results:
            citations.append({
                "type": "web",
                "label": r["title"],
                "url": r["url"],
                "snippet": r["snippet"][:200],
            })

    doc_context = "\n\n".join(doc_context_parts)
    full_context = doc_context + web_context

    _push_event(state, {
        "step": "generate",
        "status": "running",
        "message": f"Ollama ({LLM_MODEL}) is generating the final validated answer...",
    })

    system_prompt = """You are an enterprise-grade AI document assistant with strict citation requirements.

Rules:
1. Answer using ONLY the provided context (document chunks and/or web results).
2. Every factual claim MUST cite its source using [Doc N] or [Web N] markers inline.
3. If information is insufficient, clearly state what is missing.
4. Be precise, professional, and concise.
5. Do NOT hallucinate or add information not present in the context.
"""

    user_prompt = f"""Context:
{full_context}

Question: {query}

Provide a comprehensive, cited answer:"""

    client = ollama.Client(host=OLLAMA_BASE_URL)
    response = client.chat(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        options={"temperature": 0.1, "num_predict": 1024},
    )

    answer = response.message.content.strip()

    _push_event(state, {
        "step": "generate",
        "status": "done",
        "message": "Answer generated with citations.",
        "answer": answer,
        "citations": citations,
        "pipeline_path": state.get("pipeline_path", []),
    })

    state["answer"] = answer
    state["citations"] = citations
    state["context"] = full_context
    return state


# ── Conditional Edge ──────────────────────────────────────────

def route_after_grade(state: CRAGState) -> str:
    """Route to 'generate' if ACCURATE, else to 'rewrite' for web fallback."""
    grade = state.get("grade_result", {})
    if grade.get("status") == "ACCURATE":
        return "generate"
    return "rewrite"


# ── Graph Construction ────────────────────────────────────────

def build_crag_graph() -> StateGraph:
    graph = StateGraph(CRAGState)

    graph.add_node("retrieve", node_retrieve)
    graph.add_node("grade", node_grade)
    graph.add_node("rewrite", node_rewrite)
    graph.add_node("web_search", node_web_search)
    graph.add_node("generate", node_generate)

    graph.set_entry_point("retrieve")
    graph.add_edge("retrieve", "grade")
    graph.add_conditional_edges("grade", route_after_grade, {
        "generate": "generate",
        "rewrite": "rewrite",
    })
    graph.add_edge("rewrite", "web_search")
    graph.add_edge("web_search", "generate")
    graph.add_edge("generate", END)

    return graph.compile()


# ── Async Runner with Event Streaming ─────────────────────────

async def run_crag_pipeline(
    query: str,
    doc_ids: list[str] | None = None,
    session_id: str = "default",
) -> AsyncIterator[dict]:
    """
    Run the full CRAG pipeline and yield JSON events as they complete.

    Args:
        query:      User's natural language question.
        doc_ids:    Optional list of document IDs to scope retrieval.
        session_id: Session identifier for logging.

    Yields:
        JSON-serializable dicts with step progress and final result.
    """
    compiled = build_crag_graph()

    initial_state: CRAGState = {
        "query": query,
        "doc_ids": doc_ids or [],
        "events": [],
        "pipeline_path": [],
    }

    # Run pipeline in thread pool (LangGraph is sync)
    loop = asyncio.get_event_loop()
    final_state: CRAGState = await loop.run_in_executor(
        None, lambda: compiled.invoke(initial_state)
    )

    # Yield all accumulated events
    for event in final_state.get("events", []):
        yield event
        await asyncio.sleep(0)  # yield control between events

    # Yield completion summary
    yield {
        "step": "complete",
        "status": "done",
        "session_id": session_id,
        "pipeline_path": final_state.get("pipeline_path", []),
        "answer": final_state.get("answer", ""),
        "citations": final_state.get("citations", []),
    }
