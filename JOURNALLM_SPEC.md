
# Project Design Document: JournalLM V1 (General Edition)
**Status:** Ready for Implementation  
**Architecture:** Hybrid (Next.js + FastAPI) / Local-First

## 1. Project Overview & Philosophy
JournalLM V1 is a local-first, standalone intelligence platform designed to bridge the gap between qualitative personal reflections (unstructured journals) and quantitative physiological data (health trackers). 

The system treats a user's journal as a high-resolution data source. By utilizing **Agentic Event Extraction**, it "shreds" raw prose into atomic "Life Events" and "Reflections" to eliminate hallucination in RAG workflows and provide structured longitudinal analysis.

### Core Objectives:
* **Structured Recall:** Turn "I think I went to that cafe last week" into a verifiable data point in a relational database.
* **Nuanced Insight:** Capture the "hard-to-quantify" aspects of life, such as social battery, learning progress, and mood shifts.
* **Physiological Correlation:** Overlay objective metrics (HRV, Sleep, Stress) with subjective journal entries to identify behavioral patterns.
* **Professional UX:** A high-information-density "Command Center" aesthetic.

---

## 2. Technical Stack
* **Frontend:** Next.js (App Router), TypeScript, Tailwind CSS, Shadcn UI.
* **Backend:** FastAPI (Python), SQLAlchemy (ORM).
* **Database:** SQLite + `sqlite-vss` (for semantic vector search).
* **Ingestion:** Git-Ops Pipeline (Polling a private Git repository via REST API).
* **Physiological Sync:** Official Wearable APIs (e.g., Whoop v2 OAuth).

---

## 3. Data Architecture (SQLite Schema)

### 3.1 Source Layer
* **`journal_entries`**: Maintains an audit trail of original text.
    * `id` (PK), `entry_date` (Unique), `raw_content` (Text), `file_hash` (For change detection), `processed_at` (Timestamp).

### 3.2 Atomic Event Layer (The "Shredder" Output)
* **`life_events`**: Stores discrete, categorized occurrences extracted from prose.
    * `category`: Enum (e.g., `SOCIAL`, `LEARNING`, `DIETARY`, `FITNESS`, `WORK`).
    * `description`: Textual summary of the specific event.
    * `metadata_json`: Flexible JSON for specific attributes (e.g., participants, location names, project IDs).
    * `sentiment_score`: Float (-1.0 to 1.0).

### 3.3 Narrative Layer
* **`journal_reflections`**: Stores qualitative takeaways and mental shifts.
    * `topic`: General theme (e.g., "Career Strategy," "Health Philosophy").
    * `content`: The reflection text.
    * `is_actionable`: Boolean (Flags intentions to change behavior).

### 3.4 Physiological Layer
* **`health_metrics`**: Stores daily objective data (HRV, Recovery, Sleep, Activity).

---

## 4. System Modules

### 4.1 The Agentic Extraction Engine ("The Shredder")
A background worker that processes new journal entries through an LLM.
* **Logic:** Instead of summarizing a whole day, it identifies "atomic units" of information and maps them to the `life_events` schema.
* **Configuration:** The extractor is instructed to prioritize categories defined in the user's profile (e.g., "Dining," "Professional Growth," "Family").

### 4.2 Git-Ops Ingestion
* **Polling Strategy:** To maintain a local-first environment without tunnels, the backend polls the user's private repository for new commits.
* **Processing:** It identifies changed files via `file_hash` and triggers the Shredder only for new/modified content.

### 4.3 The "Hybrid" Assistant
* **Query Handling:** Uses an LLM to determine if a user's question is **Factual** (SQL-based) or **Thematic** (Vector-based).
* **RAG Flow:** Combines structured SQL filters (e.g., "events from last October") with semantic vector similarity for high-accuracy recall.

---

## 5. User Experience & Dashboard
The "Home" interface is a grid-based dashboard focused on "Actuals" for the current week.



### Dashboard Widgets:
1.  **Narrative Snapshot:** A 1-2 sentence AI-generated overview of the week's trajectory.
2.  **Activity/Social Heatmap:** Visual representation of events over time.
3.  **Physiological Trends:** Charts showing the relationship between stress/recovery and journaled events.
4.  **Structured Logs:** Lists of specific categorized data (e.g., "Restaurants Visited," "Concepts Learned").

---

## 6. Implementation Phases (For Coding Agent)

* **Phase 1: Foundation.** Setup FastAPI/Next.js and SQLite/Vector schema.
* **Phase 2: Data Ingestion.** Implement Git polling and file parsing logic.
* **Phase 3: The Shredder.** Build the Agentic Extraction prompt and JSON-to-SQL pipeline.
* **Phase 4: API Integration.** Connect physiological data (Wearable API) and OAuth flow.
* **Phase 5: Hybrid RAG.** Build the Chatbot backend with `sqlite-vss`.
* **Phase 6: UI/UX.** Build the "Slate Intelligence" dashboard and widgets.