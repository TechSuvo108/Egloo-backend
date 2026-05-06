# 🐧 Egloo Backend Documentation — Pingo Intelligence

Welcome to the comprehensive guide for the **Egloo** backend. This document explains the architecture, features, and API surface of the system that powers **Pingo**, your intelligent second brain.

---

## 🏗️ System Overview

Egloo is a Retrieval-Augmented Generation (RAG) platform that connects to your personal data sources (Gmail, Slack, Google Drive) and provides an intelligent interface to query, summarize, and organize your digital life.

### The Assistant: Pingo 🐧
Pingo is the personality layer of Egloo. It is designed to be helpful, concise, and context-aware. Pingo doesn't just "search" your data; it understands it.

### Core Tech Stack
*   **Framework**: FastAPI (Python 3.11+)
*   **Database**: PostgreSQL (Structured data), Redis (Caching & Task Queue), ChromaDB (Vector store)
*   **AI Models**: Gemini (Primary), Groq (Fast Fallback), OpenRouter (Broad Fallback)
*   **Async Tasks**: Celery with Redis broker

---

## 🚀 Key Features

### 1. Multi-Source Integration
Connect multiple platforms via OAuth 2.0. Egloo currently supports:
*   **Gmail**: Read emails and threads.
*   **Slack**: Monitor channels and direct messages.
*   **Google Drive**: Index documents and PDFs.

### 2. Intelligent Ingestion Pipeline
When a source is connected, Egloo performs:
1.  **Fetching**: Pulling raw data from APIs.
2.  **Chunking**: Breaking text into semantic pieces.
3.  **Embedding**: Converting text to high-dimensional vectors.
4.  **Vector Storage**: Saving to ChromaDB for semantic retrieval.

### 3. Pingo Query (RAG)
Ask natural language questions about your data. Pingo retrieves relevant context from ChromaDB and generates a grounded response.
*   **Citations**: Every answer includes links back to the original source.
*   **Streaming**: Real-time token-by-token response for a premium UI feel.
*   **Deterministic Caching**: Redis-based cache ensures identical questions don't waste LLM tokens.

### 4. Daily Digests
Automatically generates a summary of your day every morning (or on-demand).
*   **Action Items**: Extracts tasks you need to do.
*   **Topic Clustering**: Groups related conversations together.
*   **Push Notifications**: Can notify the frontend via FCM.

### 5. Smart Topics
Pingo automatically clusters your ingested documents into high-level "Topics" (e.g., "Project Alpha", "Vacation Planning"), making it easier to browse large datasets.

---

## 📑 API Reference

All API endpoints are prefixed with `/api/v1`.

### 🐧 Authentication (`/auth`)
| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/auth/register` | `POST` | Create a new account. |
| `/auth/login` | `POST` | Exchange credentials for JWT tokens. |
| `/auth/refresh` | `POST` | Get a new access token using a refresh token. |
| `/auth/logout` | `POST` | Invalidate current session. |
| `/auth/me` | `GET` | Get current user profile. |

### 🔌 Sources (`/sources`)
| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/sources` | `GET` | List all connected accounts. |
| `/sources/connect/gmail` | `GET` | Start Google OAuth flow. |
| `/sources/connect/slack` | `GET` | Start Slack OAuth flow. |
| `/sources/{type}` | `DELETE` | Disconnect a specific source. |
| `/sources/{type}/status`| `GET` | Get sync status (syncing, success, failed). |

### 📥 Ingestion (`/ingest`)
| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/ingest/trigger/{id}` | `POST` | Queue a background sync for a source. |
| `/ingest/trigger-all` | `POST` | Sync all connected sources. |
| `/ingest/job/{id}` | `GET` | Poll progress of a sync job (0-100%). |
| `/ingest/jobs` | `GET` | List recent sync history. |

### 💬 Query (`/query`)
| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/query/ask` | `POST` | Ask Pingo a question (synchronous). |
| `/query/ask/stream` | `POST` | Ask Pingo (Server-Sent Events stream). |
| `/query/history` | `GET` | View past questions and answers. |
| `/query/suggest` | `GET` | Get recommended questions based on data. |

### 🗞️ Digest (`/digest`)
| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/digest/today` | `GET` | Get or generate today's summary. |
| `/digest/generate` | `POST` | Manually trigger a new digest. |
| `/digest/history` | `GET` | Browse past summaries. |

### 🔖 Saved Items (`/saved`)
| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/saved` | `POST` | Bookmark a digest, query result, or topic. |
| `/saved` | `GET` | List all bookmarks with filters. |
| `/saved/counts` | `GET` | Get breakdown by type (for UI stats). |
| `/saved/{id}` | `DELETE` | Remove a bookmark. |

---

## 🧠 AI Architecture

### LLM Fallback Strategy
Egloo uses a resilient 3-tier routing system to ensure Pingo is always online:
1.  **Primary (Gemini 1.5 Pro)**: Best reasoning, large context window.
2.  **Secondary (Groq / Llama 3)**: Ultra-fast performance if Gemini is rate-limited.
3.  **Tertiary (OpenRouter)**: Wide variety of models as a final safety net.

### RAG Pipeline Flow
1.  **User Question**: User asks "What did Sarah say about the budget?"
2.  **Embedding**: The question is converted to a vector.
3.  **Retrieval**: ChromaDB finds the top 5-10 most relevant document chunks.
4.  **Re-ranking**: Simple scoring to ensure context quality.
5.  **Prompt Construction**: System prompt + Context + User Question → LLM.
6.  **Response**: Pingo answers: "Sarah mentioned in Slack that the budget is approved..."

---

## 🛠️ Developer Setup

### Environment Variables
Ensure the following are set in your `.env` file:
```env
# Core
DATABASE_URL=postgresql+asyncpg://user:pass@localhost/egloo
REDIS_URL=redis://localhost:6379/0

# AI Keys (At least one required)
GEMINI_API_KEYS=key1,key2
GROQ_API_KEYS=key1
OPENROUTER_API_KEYS=key1

# OAuth
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
SLACK_CLIENT_ID=...
SLACK_CLIENT_SECRET=...
```

### Running Locally
1. `docker-compose up -d` (Postgres, Redis, ChromaDB)
2. `pip install -r requirements.txt`
3. `alembic upgrade head`
4. `uvicorn app.main:app --reload`

---

## 🐧 Health & Monitoring
Check `/health` for a real-time status of all backend dependencies.
Check `/api/v1/llm/health` to see the availability of AI providers.

---
*Documentation generated by Antigravity for the Egloo Team.*
