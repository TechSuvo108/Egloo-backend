# 🐧 Egloo Backend Documentation — Pingo Intelligence

Welcome to the comprehensive guide for the **Egloo** backend. This document explains the architecture, features, and API surface of the system that powers **Pingo**, your intelligent second brain.

---

## 🏗️ System Overview 

Egloo is a Retrieval-Augmented Generation (RAG) platform that connects to your personal data sources (Gmail, Slack, Google Drive, and manual PDF uploads) and provides an intelligent interface to query, summarize, and organize your digital life.

### The Assistant: Pingo 🐧
Pingo is the personality layer of Egloo. It is designed to be helpful, concise, and context-aware. Pingo doesn't just "search" your data; it understands it.

### Core Tech Stack
*   **Framework**: FastAPI (Python 3.12+)
*   **Database**: PostgreSQL (Structured data), Redis (Caching & Task Queue), ChromaDB (Vector store)
*   **AI Models**: Gemini 1.5 Pro (Primary), Groq (Fast Fallback), OpenRouter (Broad Fallback)
*   **Async Tasks**: Celery with Redis broker + Celery Beat for scheduling

---

## 🚀 Key Features

### 1. Multi-Source Integration
Connect multiple platforms via OAuth 2.0 or direct upload. Egloo currently supports:
*   **Gmail**: Read emails and threads.
*   **Slack**: Monitor channels and direct messages.
*   **Google Drive**: Index documents and PDFs.
*   **PDF Uploads**: Manually upload documents for indexing.

### 2. Intelligent Ingestion Pipeline
When a source is connected, Egloo performs:
1.  **Fetching**: Pulling raw data from APIs (Gmail/Slack/Drive).
2.  **Chunking**: Breaking text into semantic pieces (~800 chars).
3.  **Embedding**: Converting text to high-dimensional vectors.
4.  **Vector Storage**: Saving to ChromaDB for semantic retrieval.
5.  **Hardened Processing**: Gracefully skips static sources (PDFs) in background workers and handles authentication failures (401/Invalid Key) by marking sources as `auth_expired` to stop retry storms.

### 3. Pingo Query (RAG)
Ask natural language questions about your data. Pingo retrieves relevant context from ChromaDB and generates a grounded response.
*   **Citations**: Every answer includes links back to the original source.
*   **Streaming**: Real-time token-by-token response for a premium UI feel.
*   **Deterministic Caching**: Redis-based cache ensures identical questions don't waste LLM tokens.

### 4. Proactive Intelligence (Brain Module)
Pingo doesn't just wait for questions; it proactively analyzes your data:
*   **Daily Today Summary**: Aggregates the most important items from the last 24 hours.
*   **Missing Info Engine**: Identifies unanswered requests, pending approvals, and unresolved blockers.
*   **Connection Engine**: Discovers semantic relationships between unrelated sources (e.g., a Slack message about a budget and a PDF contract).
*   **Proactive Alerts**: Matches incoming data against "critical" keywords (deadline, approval, blocker) and stores them for immediate notification.

### 5. Automated Maintenance
*   **Daily Brain Refresh**: A Celery Beat task runs every morning to pre-cache intelligence for all active users.
*   **Scheduler Heartbeat**: Constant vitality monitoring ensures the background scheduler is always online.

---

## 📑 API Reference

All API endpoints are prefixed with `/api/v1`.

### 🐧 Authentication (`/auth`)
| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/auth/register` | `POST` | Create a new account. |
| `/auth/login` | `POST` | Exchange credentials for JWT tokens. |
| `/auth/me` | `GET` | Get current user profile. |

### 🔌 Sources (`/sources`)
| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/sources` | `GET` | List user's connected sources. |
| `/sources/connect/gmail` | `GET` | Start Google OAuth flow. |
| `/sources/connect/slack` | `GET` | Start Slack OAuth flow. |
| `/sources/{type}/status`| `GET` | Get sync status (idle, syncing, success, auth_expired, failed). |

### 🧠 Brain & Proactive Intelligence (`/brain`)
| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/brain/health` | `GET` | **New:** Detailed health check of all dependencies + scheduler. |
| `/brain/today` | `GET` | Get today's proactive summary. |
| `/brain/missing` | `GET` | **New:** Find unanswered requests and pending blockers. |
| `/brain/connections` | `GET` | **New:** View cross-source semantic correlations. |
| `/brain/alerts` | `GET` | List matched proactive alerts (deadlines, approvals). |

### 💬 Query (`/query`)
| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/query/ask` | `POST` | Ask Pingo a question (synchronous). |
| `/query/ask/stream` | `POST` | Ask Pingo (Server-Sent Events stream). |

---

## 🧠 AI Architecture

### Resilient LLM Routing
Egloo uses a 3-tier fault-tolerant routing system with graceful fallbacks:
1.  **Primary (Gemini 1.5 Pro)**: Best reasoning, large context window.
2.  **Secondary (Groq)**: Ultra-fast performance if Gemini is rate-limited.
3.  **Tertiary (OpenRouter)**: Final safety net for maximum reliability.

**Hardening Features:**
*   **Auth-Aware Failover**: If a provider returns a `401 Unauthorized` (invalid API key), Egloo automatically skips it and marks it as unhealthy in Redis to prevent further failed attempts.
*   **No-Crash Guarantee**: If all providers fail, the system returns a safe fallback message ("LLM temporarily unavailable") instead of crashing the request.

---

## 🛠️ Developer Setup

### Environment Variables
Ensure the following are set in your `.env` file:
```env
# Core
DATABASE_URL=postgresql+asyncpg://user:pass@localhost/egloo
REDIS_URL=redis://localhost:6379/0
ENCRYPTION_KEY=...

# AI Keys (Comma-separated for multi-key support)
GEMINI_API_KEYS=key1,key2
GROQ_API_KEYS=key1
OPENROUTER_API_KEYS=key1
```

### Running Locally
1. `docker compose up -d` (Postgres, Redis, ChromaDB, Worker, Beat)
2. `pip install -r requirements.txt`
3. `alembic upgrade head`
4. `uvicorn app.main:app --reload`

---

## 🐧 Health & Monitoring
*   **System Health**: Check `/health` for basic connectivity.
*   **Brain Health**: Check `/api/v1/brain/health` for a deep dive into Postgres, Redis, ChromaDB, LLM provider availability, and Scheduler vitality.

---
*Documentation generated by Antigravity for the Egloo Team.*
