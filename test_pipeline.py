# -*- coding: utf-8 -*-
"""
test_pipeline.py - Validation script for the Enterprise RAG Platform.
Run from the project root: python test_pipeline.py
Tests: Ollama connection, MongoDB, cross-encoder load, and a full pipeline run.
"""
import sys
import os

# Force UTF-8 output on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

SEP = "=" * 54
print(f"\n{SEP}")
print("  Enterprise RAG Platform -- Validation Tests")
print(f"{SEP}\n")

PASS = "[PASS]"
FAIL = "[FAIL]"
results = []

# -- Test 1: Config loads ----------------------------------------
try:
    from config import OLLAMA_BASE_URL, LLM_MODEL, EMBEDDING_MODEL, MONGO_URI
    print(f"{PASS}  Config loaded   LLM={LLM_MODEL}  Embed={EMBEDDING_MODEL}")
    results.append(("Config", True))
except Exception as e:
    print(f"{FAIL}  Config: {e}")
    results.append(("Config", False))

# -- Test 2: Ollama connection & LLM check -----------------------
try:
    import ollama
    client = ollama.Client(host=OLLAMA_BASE_URL)
    models = [m.model for m in client.list().models]
    assert any(LLM_MODEL in m for m in models), \
        f"Model '{LLM_MODEL}' not found. Run: ollama pull {LLM_MODEL}"
    print(f"{PASS}  Ollama running   available models: {', '.join(models)}")
    results.append(("Ollama LLM", True))
except AssertionError as e:
    print(f"{FAIL}  Ollama LLM: {e}")
    results.append(("Ollama LLM", False))
except Exception as e:
    print(f"{FAIL}  Ollama LLM: {e}")
    print("       --> Make sure Ollama is running (ollama serve)")
    results.append(("Ollama LLM", False))

# -- Test 3: MongoDB connection ----------------------------------
try:
    from database import get_client, init_indexes
    get_client()
    init_indexes()
    print(f"{PASS}  MongoDB connected at {MONGO_URI}")
    results.append(("MongoDB", True))
except Exception as e:
    print(f"{FAIL}  MongoDB: {e}")
    print("       --> Make sure MongoDB is running (run .\\run.ps1)")
    results.append(("MongoDB", False))

# -- Test 4: Ollama Embedding ------------------------------------
try:
    from embeddings import embed_texts
    vecs = embed_texts(["Hello, test embedding."])
    assert len(vecs) == 1 and len(vecs[0]) > 50
    print(f"{PASS}  Ollama embedding   model={EMBEDDING_MODEL}  dim={len(vecs[0])}")
    results.append(("Ollama Embed", True))
except Exception as e:
    print(f"{FAIL}  Ollama Embed: {e}")
    print(f"       --> Run: ollama pull {EMBEDDING_MODEL}")
    results.append(("Ollama Embed", False))

# -- Test 5: Cross-Encoder loads --------------------------------
try:
    from agents.grader import get_cross_encoder
    model = get_cross_encoder()
    scores = model.predict([("test query", "test passage about the query topic")])
    print(f"{PASS}  Cross-encoder loaded   sample score: {scores[0]:.4f}")
    results.append(("Cross-Encoder", True))
except Exception as e:
    print(f"{FAIL}  Cross-Encoder: {e}")
    results.append(("Cross-Encoder", False))

# -- Test 6: Full pipeline (synthetic) --------------------------
try:
    import asyncio
    from rag_pipeline import run_crag_pipeline
    from database import chunks
    from embeddings import embed_texts as _embed
    from datetime import datetime, timezone

    test_text = (
        "The corporate leave policy allows 20 paid leave days "
        "per year for all full-time employees."
    )
    emb = _embed([test_text])[0]
    fake_doc_id = "test-pipeline-doc"
    chunks().delete_many({"doc_id": fake_doc_id})
    chunks().insert_one({
        "doc_id": fake_doc_id, "filename": "test.pdf", "page": 1,
        "chunk_index": 0, "text": test_text,
        "char_start": 0, "char_end": len(test_text),
        "embedding": emb, "indexed_at": datetime.now(timezone.utc),
    })

    events = []

    async def collect():
        async for ev in run_crag_pipeline(
            "How many paid leave days do employees get?",
            doc_ids=[fake_doc_id], session_id="test",
        ):
            events.append(ev)

    asyncio.run(collect())
    complete = [e for e in events if e.get("step") == "complete"]
    assert complete, "No completion event received"
    answer = complete[0].get("answer", "")
    assert answer, "Empty answer returned"

    path = " -> ".join(complete[0].get("pipeline_path", []))
    print(f"{PASS}  Full pipeline run   path: {path}")
    print(f"       Answer: \"{answer[:120]}...\"")
    results.append(("Full Pipeline", True))

    chunks().delete_many({"doc_id": fake_doc_id})

except Exception as e:
    print(f"{FAIL}  Full Pipeline: {e}")
    results.append(("Full Pipeline", False))

# -- Summary ----------------------------------------------------
print(f"\n{SEP}")
passed = sum(1 for _, ok in results if ok)
total = len(results)
print(f"  Results: {passed}/{total} tests passed")
print(SEP)
for name, ok in results:
    print(f"  {'[OK]' if ok else '[XX]'}  {name}")
print(f"{SEP}\n")

if passed < total:
    print("Some tests failed. Checklist:")
    print("  1. Make sure Ollama is running:   ollama serve")
    print("  2. Pull required models:")
    print("     ollama pull gemma4")
    print("     ollama pull nomic-embed-text")
    print("  3. Start MongoDB (run .\\run.ps1 or start mongod manually)")
    sys.exit(1)
else:
    print("All tests passed! Run .\\run.ps1 to launch the platform.\n")
