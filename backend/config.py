"""
config.py - Central configuration loader for the RAG platform.
Powered by Ollama - fully local, no API keys required.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from the project root (one level above backend/)
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

# ── Ollama ───────────────────────────────────────────────────
OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
LLM_MODEL: str = os.getenv("LLM_MODEL", "qwen2.5:3b")
EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")

# ── MongoDB ──────────────────────────────────────────────────
MONGO_URI: str = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DB_NAME: str = os.getenv("DB_NAME", "crag_platform")

# Collection names
COL_PROFILES = "client_profiles"
COL_LOGS = "interaction_logs"
COL_CHUNKS = "document_chunks"

# ── Grading & Retrieval ──────────────────────────────────────
CROSS_ENCODER_MODEL: str = os.getenv(
    "CROSS_ENCODER_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2"
)
GRADER_THRESHOLD: float = float(os.getenv("GRADER_THRESHOLD", "0.4"))
TOP_K: int = int(os.getenv("TOP_K", "5"))

# ── Chunking ─────────────────────────────────────────────────
CHUNK_SIZE: int = 500
CHUNK_OVERLAP: int = 80

# ── HuggingFace (for cross-encoder download) ─────────────────
HF_TOKEN: str = os.getenv("HF_TOKEN", "")
