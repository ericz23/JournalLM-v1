# JournalLM

A local-first intelligence platform that bridges qualitative journal entries with quantitative health data. JournalLM "shreds" raw journal prose into structured Life Events and Reflections, then provides a RAG-powered chat interface grounded in your actual data.

## Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js (App Router), TypeScript, Tailwind CSS, Shadcn UI |
| Backend | FastAPI, SQLAlchemy (async), Python |
| Database | SQLite + sqlite-vec (vector similarity search) |
| AI | Google Gemini (structured extraction, embeddings, chat) |
| Health Data | Whoop API v2 (OAuth 2.0) |

## Features

- **Agentic Event Extraction** — Gemini shreds journal markdown into atomic Life Events and Reflections with categories, sentiment scores, and metadata
- **RAG Chat** — Two-stage retrieval (intent classification + structured SQL + semantic search) grounded in journal data
- **Chat Modes** — Extensible mode system with Default (journal Q&A) and Therapist (CBT-informed reflective support) modes
- **Temporary Chats** — Ephemeral sessions that aren't persisted, with save-to-permanent option
- **Dashboard** — Weekly narrative, dining log, reflections panel, and learning progress widgets
- **Whoop Integration** — OAuth sync for recovery, strain, sleep, and HRV metrics
- **Vector Search** — sqlite-vec powered semantic search over journal embeddings

## Setup

### Prerequisites

- Python 3.11+
- Node.js 18+
- A [Google Gemini API key](https://aistudio.google.com/apikey)

### Environment

Create a `.env` file in the project root:

```
GEMINI_API_KEY=your-key-here
GEMINI_MODEL=gemini-2.5-flash

# Optional: Whoop integration
WHOOP_CLIENT_ID=
WHOOP_CLIENT_SECRET=
```

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The frontend runs at `http://localhost:3000` and connects to the backend at `http://localhost:8000`.

## Usage

1. **Ingest journals** — `POST /api/journals/ingest` scans the journal source directory
2. **Shred entries** — `POST /api/shredder/run` extracts structured events and reflections
3. **Triage entity inbox** — `/inbox` confirms or merges proposed people/projects
4. **Build embeddings** — `POST /api/chat/embed` generates vector embeddings for semantic search
5. **Chat** — Open the chat page to query your journal data with RAG-grounded responses

### Operational scripts

For batch operations (V2 cutover, prompt-bump re-shreds, re-embed runs), see
the runbook in [`docs/journallm-v2/06-backfill-and-operations.md`](docs/journallm-v2/06-backfill-and-operations.md).
The two main entry points are:

- `python -m scripts.backfill --max-version v2.2 --force --note "V2 cutover"` — batch shred + resolve.
- `python -m scripts.re_embed` — purge + regenerate journal embeddings.

Both scripts must be run from the `backend/` directory and require the
FastAPI server to be stopped to avoid LLM rate-limit conflicts.

## Project Structure

```
backend/
  app/
    core/         # Config, database setup
    models/       # SQLAlchemy ORM models
    routes/       # FastAPI route handlers
    services/     # Business logic (shredder, retrieval, chat engine, etc.)
frontend/
  src/
    app/          # Next.js pages (dashboard, chat)
    components/   # UI components (chat, dashboard, layout)
    lib/          # API client, utilities, chat mode config
synthetic_journals/   # Sample Obsidian-style markdown journals
```
