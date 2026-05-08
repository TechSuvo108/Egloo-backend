# 🐧 Egloo Backend — Pingo Second Brain

Egloo is an AI-powered **second brain** that connects your **Gmail, Slack, Google Drive, and Documents** into a single intelligent assistant named **Pingo**.

Pingo helps users:

* Search across connected sources using natural language
* **Proactively** identify unanswered requests and pending blockers
* Discover semantic relationships between unrelated documents
* Generate daily digests and summaries automatically
* Get real-time alerts for deadlines and approvals
* Cluster information into smart topics

---

## 🚀 Tech Stack

| Layer                 | Technology                        |
| --------------------- | --------------------------------- |
| **Backend Framework** | FastAPI (Python 3.12)             |
| **Database**          | PostgreSQL 15 + SQLAlchemy Async  |
| **Vector Database**   | ChromaDB                          |
| **Cache / Queue**     | Redis 7                           |
| **Workers**           | Celery + **Celery Beat** (Periodic Tasks) |
| **AI Pipeline**       | Gemini / Groq / OpenRouter        |
| **Resilience**        | 3-Tier LLM Fallback + Health Monitoring |

---

## 📦 Features

* **Proactive Intelligence**: Automated gap analysis (Missing Info), relationship discovery (Connections), and urgent item detection (Alerts).
* **Brain Health Monitoring**: Real-time tracking of Postgres, Redis, ChromaDB, LLM providers, and Scheduler vitality.
* **Resilient LLM Routing**: Deterministic fallback with auth-aware provider skipping and total outage protection.
* **Hardened Ingestion**: Intelligent pipeline that handles OAuth expiration, invalid keys, and multi-source synchronization.
* **Multi-Source Integration**: Gmail, Slack, Google Drive, and manual PDF uploads.
* **Deterministic Caching**: Redis-based query normalization and result caching.
* **Smart Topics**: Automated semantic clustering of large datasets.

---

## ⚡ Quick Start

### 1) Clone repository

```bash
git clone <your-repo-url>
cd egloo/backend
```

### 2) Create environment file

```bash
cp .env.example .env
```

### 3) Start backend

```bash
docker compose build
docker compose up -d
```

### 4) Run migrations

```bash
docker compose exec api alembic upgrade head
```

---

## 🧠 API Modules

| Module  | Endpoint Prefix   | Purpose                          |
| ------- | ----------------- | -------------------------------- |
| Auth    | `/api/v1/auth`    | Register, login, refresh, logout |
| Sources | `/api/v1/sources` | Connect Gmail / Slack / Drive    |
| Ingest  | `/api/v1/ingest`  | Fetch, chunk, embed, store       |
| Brain   | `/api/v1/brain`   | **Proactive Intelligence & Health** |
| Query   | `/api/v1/query`   | Ask Pingo questions (RAG)        |
| Digest  | `/api/v1/digest`  | Daily summaries                  |
| Topics  | `/api/v1/topics`  | Auto-clustered topic groups      |
| Saved   | `/api/v1/saved`   | Bookmarks                        |
| LLM     | `/api/v1/llm`     | Provider health + usage          |

---

## 🏗 Architecture

```text
Android App (Kotlin)
      |
      v
FastAPI Gateway (CORS + JWT)
      |
      v
+----------------------------------+
| Brain Service (Proactive Intel)  |
| Ingestion Service (Hardened)     |
| LLM Router (Fault Tolerant)      |
+----------------------------------+
      |
      v
+------------+-----------+---------+
| PostgreSQL | ChromaDB  | Redis   |
| Metadata   | Vectors   | Cache   |
+------------+-----------+---------+
      |
      v
Celery Worker + Beat (Scheduled Maintenance)
```

---

## ✅ Status

**Backend Complete — Production Ready**

Assistant Name: **Pingo 🐧**
*The most resilient and proactive second brain ever built.*
