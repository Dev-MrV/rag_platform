# 🏢 Enterprise Advanced RAG Platform

![Python](https://img.shields.io/badge/Python-3.10%2B-blue?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi)
![Ollama](https://img.shields.io/badge/Ollama-100%25_Local-black?style=for-the-badge&logo=ollama)
![MongoDB](https://img.shields.io/badge/MongoDB-4EA94B?style=for-the-badge&logo=mongodb&logoColor=white)
![LangGraph](https://img.shields.io/badge/LangGraph-AI_Orchestration-orange?style=for-the-badge)
![HTML5](https://img.shields.io/badge/HTML5-E34F26?style=for-the-badge&logo=html5&logoColor=white)
![CSS3](https://img.shields.io/badge/CSS3-1572B6?style=for-the-badge&logo=css3&logoColor=white)
![JavaScript](https://img.shields.io/badge/JavaScript-F7DF1E?style=for-the-badge&logo=javascript&logoColor=black)
![License](https://img.shields.io/badge/License-MIT-green?style=for-the-badge)

A fully local, self-correcting Retrieval-Augmented Generation (CRAG) system designed for parsing complex corporate policy packets and enterprise documents.

This platform eliminates "hallucinations" by cross-referencing vector data chunks, strictly validating retrieval quality using a local cross-encoder model before answering, and providing real-time web-search fallbacks if internal information is missing.

---

## 📸 Screenshots

| Document Workspace & Agent Log | Real-time Search & Citations |
| :---: | :---: |
| <br>![Workspace](https://github.com/Dev-MrV/rag_platform/blob/main/Src/image2.png) | ![Citations](https://github.com/Dev-MrV/rag_platform/blob/main/Src/image3.png) |

---

## ✨ Key Features

- **100% Local & Secure:** Powered entirely by Ollama running locally. No API keys needed, zero rate limits, and zero data leakage to external cloud providers.
- **Self-Correcting Pipeline (CRAG):** Uses LangGraph to orchestrate a multi-agent workflow:
  1. **Retrieve:** Embeds the query and fetches semantic chunks from MongoDB.
  2. **Grade:** A specialized local cross-encoder (`ms-marco-MiniLM-L-6-v2`) evaluates chunk relevance.
  3. **Rewrite & Fallback:** If documents are irrelevant, the AI automatically rewrites the query and falls back to a DuckDuckGo web search.
  4. **Generate:** Synthesizes a strict, fact-checked answer with citations.
- **Strict Citations:** Outputs clear references mapping directly back to the original PDF filename and page number.
- **Premium UI:** A split-pane, glassmorphism web interface featuring a modern drag-and-drop document workspace, multi-select document filtering, and a real-time agent execution terminal.

---

## 🛠️ Architecture & Tech Stack

* **AI Engine:** [Ollama](https://ollama.com/)
  * **LLM:** `qwen2.5:3b` (Optimized for 6GB-8GB RAM machines)
  * **Embeddings:** `nomic-embed-text`
* **Backend:** [FastAPI](https://fastapi.tiangolo.com/) + Uvicorn
* **Database:** [MongoDB](https://www.mongodb.com/) (Local document storage & vector embeddings)
* **Orchestration:** [LangGraph](https://python.langchain.com/docs/langgraph/)
* **Frontend:** Vanilla HTML5, CSS3, JavaScript (No complex build steps)

---

## 🚀 Getting Started

### 1. Prerequisites

Make sure you have the following installed on your machine:
* [Python 3.10+](https://www.python.org/downloads/)
* [Ollama](https://ollama.com/download)
* [MongoDB Community Server (v8.0+)](https://www.mongodb.com/try/download/community)

### 2. Install Required Local Models

Open your terminal and pull the required Ollama models. This only needs to be done once:

```bash
ollama pull qwen2.5:3b
ollama pull nomic-embed-text
```

### 3. Run the Platform

We have provided a unified startup script that automatically starts MongoDB, the Python backend, and opens the frontend UI.

Simply open a PowerShell window in the project root and run:

```powershell
.\run.ps1
```

**The script will automatically:**
1. Verify the `.env` configuration.
2. Start the Ollama engine if it's not already running.
3. Start the local MongoDB instance (storing data in the `mongo_data` folder).
4. Install any missing Python dependencies from `backend/requirements.txt`.
5. Launch the FastAPI backend on `http://localhost:8000`.
6. Open `index.html` in your default web browser.

---

## 📚 How to Use

1. **Upload Documents:** Drag and drop corporate PDFs into the left panel. The platform will automatically parse, chunk, and embed the text into MongoDB.
2. **Filter Scope:** Use the sleek dropdown above the chat to search all documents or restrict the search to specific files.
3. **Ask Questions:** Type your query on the right panel.
4. **Watch the Agent:** View the real-time "Agent Execution Log" on the left to see the CRAG pipeline Retrieve -> Grade -> Rewrite -> Generate in action.

---

## 🛑 Stopping the Server

To cleanly exit the application, simply click into the PowerShell window where you ran `.\run.ps1` and press `Ctrl+C`. This will gracefully shut down the FastAPI backend.

---

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.
