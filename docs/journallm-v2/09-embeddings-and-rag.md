# Step 9 — Embeddings and RAG compatibility

**Index:** [README.md](./README.md)  
**Plan reference:** [JOURNALLM_V2_IMPLEMENTATION_PLAN.md](../../JOURNALLM_V2_IMPLEMENTATION_PLAN.md)  
**Status:** Complete (spec baseline ready for implementation)  
**Ideation refs:** §4.1 (entity-aware retrieval preamble), architecture diagram (Ingest → Shred → Embed → Retrieve).  
**Locked decisions:** Q4 (re-shred replaces derived rows — vectors must stay consistent with whatever `chunk_text` is derived from).

---

## 1) Scope

### In scope

- **Chunk source policy:** define what text is embedded (journal-only vs journal + per-date structured digest), controlled by config.
- **Staleness and re-embedding:** deterministic rules for when `journal_embeddings` / `vec_journal_chunks` rows are purged and regenerated, without orphan vectors after Q4 re-shreds.
- **`embeddings.py` refactor:** central `build_embed_document(db, entry) -> tuple[str, list[str]]` (canonical source string + chunk list) so chunking, hashing, and embedding share one code path.
- **`journal_entries.embed_input_hash`** (nullable) — SHA-256 hex of the canonical pre-chunk source; drives skip vs rebuild in `embed_journals`.
- **Shredder hook:** after a successful per-entry commit, optionally invalidate embeddings for that `entry_date` when structured digest is enabled (see §6).
- **Retrieval placeholders:** extend `ParsedIntent` and `retrieve()` with optional entity-oriented fields and stub retrievers (no SQL against `people` / `projects` until Step 11).
- **Context metadata:** enrich `journal_chunk` `ContextItem.metadata` with `embedding_model`, `chunk_index`, and optional `chunk_mode` for debugging and future UI (source inspector).
- **Regression matrix** (§17) and manual golden paths.

### Out of scope

- **Full entity-aware SQL retrieval** — Step 11 owns `_retrieve_person_*` / `_retrieve_project_*` implementations.
- **Coach mode prompts** — Step 12.
- **New virtual tables** for entity-specific vectors (e.g. `vec_person_bio`) — backlog unless pulled forward.
- **Frontend changes** — chat UI already displays `retrieved_context`; no Step 9 UI work unless a dev-only “embedding status” panel is added (backlog).
- **Changing the embedding model dimension** without a migration playbook — if `EMBEDDING_MODEL` changes, Step 13 requires a full re-embed; call that out in ops notes, not automated here.

---

## 2) Dependencies

- **Reads normative detail from:**
  - Step 0 — conventions; Q4 transaction semantics.
  - Step 1 — `journal_entries`, `journal_embeddings`, `vec_journal_chunks`, `life_events`, `journal_reflections`.
  - Step 2 — shredder success path; `processed_at` / `shredder_version` writes.
  - Step 6 — `purge_entry_embeddings`, `/api/operations/re-embed`, backfill `purge_embeddings` flag handoff (§6.4–6.5).
- **Feeds:**
  - Step 11 — intent schema + stub hooks become real entity SQL.
  - Step 12 — coach mode assumes retrieval can someday include project rows; Step 9 does not block that.
  - Step 13 — regression checklist references §17.

---

## 3) Problem statement

V1 embeds **raw journal markdown** per `JournalEntry`. Shredding only changes `life_events` / `journal_reflections` / entity links; it does **not** change `raw_content`. Therefore:

- With **journal-only** chunks, a re-shred does **not** require re-embedding for vector correctness — the indexed prose is unchanged.
- With **journal + structured digest** chunks (optional in Step 9), the embedded text **does** change when Q4 replaces events for a date. Vectors **must** be purged for that date after a successful shred, then rebuilt on the next embed pass.

Step 9 makes this distinction explicit, encodes it in config, and gives `embed_journals` a single staleness rule (`embed_input_hash`) so operators and code paths do not guess.

---

## 4) Configuration (`app.core.config.Settings`)

Add:

```python
# Chunk text policy: what gets hashed, chunked, and embedded.
# journal_only — hash = SHA256(normalized raw_content); same as V1 behavior.
# journal_plus_structured — hash includes appended life_events + reflections digest for entry_date.
EMBEDDING_CHUNK_MODE: Literal["journal_only", "journal_plus_structured"] = "journal_only"

# When True and mode is journal_plus_structured, shredder calls
# mark_embeddings_stale_for_date after each successful entry commit (§8).
EMBEDDING_INVALIDATE_ON_SHRED: bool = True

# When True, embed_journals runs automatically at the end of each successful
# single-entry shred (same process). Default False — avoids doubling LLM latency
# on every journal day; operators use POST /api/chat/embed or operations re-embed.
EMBEDDING_SYNC_AFTER_SHRED: bool = False
```

**Migration note:** changing `EMBEDDING_CHUNK_MODE` is a **breaking** change for all existing hashes. On toggle:

1. Run `POST /api/operations/re-embed` with full date range and `purge_first: true`, **or**
2. SQL: `UPDATE journal_entries SET embed_input_hash = NULL` for all rows, then `embed_journals`.

Document in README / Step 13 release notes.

---

## 5) Schema migration (Step 1 or co-shipped with Step 9)

### 5.1 `journal_entries.embed_input_hash`

| Column | Type | Notes |
|--------|------|--------|
| `embed_input_hash` | `String(64)`, nullable | SHA-256 hex of UTF-8 canonical source string (§7). `NULL` means “never embedded” or “invalidated / needs rebuild”. |

Index: optional `(embed_input_hash)` not needed; queries filter by date.

### 5.2 No change to `journal_embeddings` table (Step 9)

Rows remain `(entry_date, chunk_index, chunk_text)`. Optional backlog: `content_kind` enum (`journal` | `synthetic_digest`) if we split chunk types in one table.

---

## 6) Canonical source string and chunking

### 6.1 Normalization

Before hashing and chunking:

```python
def normalize_journal_raw(text: str) -> str:
    """Strip BOM, normalize newlines to \\n, strip trailing whitespace per line."""
    ...
```

Use the **same** normalization for ingestion comparisons elsewhere if we ever unify; Step 9 owns only the embed path.

### 6.2 `journal_only` mode

```python
canonical = normalize_journal_raw(entry.raw_content)
```

### 6.3 `journal_plus_structured` mode

Append a deterministic, date-scoped digest **after** the raw journal:

```
{normalized raw_content}

--- JournalLM structured digest ({entry_date}) ---
Life events:
- [{category}] {description} (sentiment: {sentiment or "n/a"})
  ...

Reflections:
- [{topic}] {content_preview}
  ...

--- End digest ---
```

Rules:

- Load `life_events` for `entry_date` ordered by `id` ascending.
- Load `journal_reflections` for `entry_date` ordered by `id` ascending.
- `content_preview` = first 400 chars of reflection `content`, single-line escaped.
- If no events and no reflections, omit the digest block entirely (canonical equals journal-only) **unless** we want “negative evidence” — **decision:** omit the block when empty to keep hash stable for unshredded days.

Digest is **only** included when `entry.processed_at is not None` (shredded). If `processed_at is None`, canonical = journal-only normalized text (matches “no structured data yet”).

### 6.4 Hashing

```python
embed_input_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
```

Compare to `entry.embed_input_hash`:

- **Equal** → skip embedding for that entry in `embed_journals` (all chunks still valid).
- **Unequal or NULL** → `purge_entry_embeddings(db, entry_date)` then embed fresh chunks, then `UPDATE journal_entries SET embed_input_hash = :hash`.

---

## 7) Module API (`backend/app/services/embeddings.py`)

### 7.1 New public helpers

```python
async def build_canonical_source(
    db: AsyncSession,
    entry: JournalEntry,
) -> str:
    """Return normalized canonical string per EMBEDDING_CHUNK_MODE and shred state."""

def chunk_canonical(canonical: str) -> list[str]:
    """Wrapper around existing chunk_text on the canonical string."""

async def embed_entry_if_stale(
    db: AsyncSession,
    entry: JournalEntry,
    client: genai.Client,
) -> tuple[bool, int]:
    """If hash matches, return (False, 0). Else purge, embed, set hash; return (True, n_chunks)."""
```

Refactor `embed_journals` to:

1. Select all `JournalEntry` where `processed_at IS NOT NULL` (unchanged) **or** optionally all entries with raw content if we want vectors for unshredded days — **decision:** keep V1 rule: only `processed_at IS NOT NULL`. Unshredded entries are skipped (no chunks in RAG for days not shredded — acceptable; chat SQL still has nothing useful).

2. For each entry, `canonical = await build_canonical_source(db, entry)`; `h = sha256(...)`.

3. If `entry.embed_input_hash == h`: `skipped += 1`; continue.

4. Else: `purge_entry_embeddings`, embed chunks, insert vec rows, set `embed_input_hash = h`, commit per entry or batch commit — **decision:** one transaction per entry for embed loop (matches V1 failure isolation). Step 13 may batch.

### 7.2 `EmbedResult` extension

Add fields:

```python
purged_dates: list[datetime.date] = field(default_factory=list)
reembedded_dates: list[datetime.date] = field(default_factory=list)
```

Returned from `embed_journals` for observability.

---

## 8) Shredder integration (`backend/app/services/shredder.py`)

After `await db.commit()` succeeds in `process_single_entry`:

```python
if settings.EMBEDDING_CHUNK_MODE == "journal_plus_structured" and settings.EMBEDDING_INVALIDATE_ON_SHRED:
    # New session or same session? Use a tiny helper that runs UPDATE only:
    await mark_embeddings_stale_for_date(db, entry_date)
    await db.commit()
```

`define mark_embeddings_stale_for_date`:

```python
async def mark_embeddings_stale_for_date(db: AsyncSession, entry_date: date) -> None:
    await db.execute(
        update(JournalEntry)
        .where(JournalEntry.entry_date == entry_date)
        .values(embed_input_hash=None)
    )
    # Optionally: await purge_entry_embeddings(db, entry_date) immediately
```

**Decision — stale marker vs immediate purge:**

- **Preferred:** set `embed_input_hash = NULL` only (fast, no vec delete in hot path). `embed_journals` / `purge_first` paths still purge before insert. This avoids double-deleting if operator runs re-embed with purge.
- **Alternative:** immediate `purge_entry_embeddings` in the same app call after commit — guarantees no stale chunks until next embed. **Spec:** use **NULL hash only** in the shredder hook; `embed_journals` always checks hash and purges before writing when hash mismatches. Immediate purge is optional optimization when `EMBEDDING_SYNC_AFTER_SHRED=True` (below).

If `EMBEDDING_SYNC_AFTER_SHRED`:

1. After stale mark, open embedding subflow: `purge_entry_embeddings`, then embed that single date inside the same request (new `embed_single_entry(db, entry_date)` extracted from loop body).

Latency: unacceptable for interactive shred-all; document “leave False for bulk; True for single-date dev UX.”

---

## 9) Ingestion path (already implemented)

Step 6 specifies `purge_entry_embeddings` on `file_hash` change. Step 9 adds:

- After purge, set `embed_input_hash = NULL` on that `JournalEntry` so the next `embed_journals` pass always rebuilds.

If not already done in code, add the NULL assignment in `ingest_journals` next to purge.

---

## 10) Operations API

No breaking changes to `POST /api/operations/re-embed` contract. Response may include new `purged_dates` / `reembedded_dates` arrays inside `EmbedResult` JSON (additive).

`POST /api/chat/embed` returns extended `EmbedResult` — frontend ignores extra fields.

---

## 11) Retrieval — intent schema extensions (`retrieval.py`)

### 11.1 Extended `ParsedIntent`

Add optional fields (all backward compatible defaults):

```python
class ParsedIntent(BaseModel):
    query_type: str
    date_start: str | None = None
    date_end: str | None = None
    categories: list[str] = []
    keywords: list[str] = []

    # Step 9 placeholders — populated by classifier, consumed in Step 11.
    entity_focus: Literal["none", "person", "project", "ambiguous"] = "none"
    entity_names: list[str] = []  # surface strings from user query (e.g. ["Sam", "Portuguese"])
    prefers_entity_sql: bool = False  # model estimates "when did I last see X?" shapes
```

### 11.2 `INTENT_SYSTEM_PROMPT` additions

Append to the field list in the system prompt:

```
- entity_focus: "person" if the question is primarily about a specific human relationship, \
last time seeing someone, or social interactions with a named person. "project" if primarily \
about a named initiative/workstream side project. "ambiguous" if both. "none" otherwise.
- entity_names: proper names or known project titles the user is asking about (strings).
- prefers_entity_sql: true when the user likely needs structured rows (last_seen_date, mention \
timeline) rather than thematic similarity alone — e.g. "when did I last", "how many times", \
"who did I see".
```

Temperature remains `0.0`.

### 11.3 Stub retrievers

```python
async def _retrieve_person_entities(
    db: AsyncSession,
    intent: ParsedIntent,
) -> list[ContextItem]:
    """Step 11: query people / person_mentions. Step 9 returns []."""
    return []


async def _retrieve_project_entities(
    db: AsyncSession,
    intent: ParsedIntent,
) -> list[ContextItem]:
    """Step 11: query projects / project_events. Step 9 returns []."""
    return []
```

### 11.4 `retrieve()` merge order

1. `classify_intent`
2. `_retrieve_life_events`, `_retrieve_reflections`, `_retrieve_health_metrics` (unchanged)
3. **New:** if `intent.prefers_entity_sql` or `intent.entity_focus in ("person", "project", "ambiguous")`:
   - `extend` from `_retrieve_person_entities` + `_retrieve_project_entities` (empty in Step 9)
4. Semantic branch (unchanged condition): `THEMATIC`, `META`, or `len(context_items) < 3`
5. Deduplication: keep existing `seen_texts` prefix heuristic; consider bumping prefix length to 160 chars when digest chunks overlap event descriptions (config constant).

### 11.5 Reserved `ContextItem.type` values

| type | Step 9 | Step 11 |
|------|--------|---------|
| `life_event` | active | active |
| `reflection` | active | active |
| `health_metric` | active | active |
| `journal_chunk` | active | active |
| `person_mention` | **unused** | SQL rows |
| `project_event` | **unused** | SQL rows |

Document `metadata` keys for future rows:

- `person_id`, `canonical_name`, `relationship_type`, `mention_date`, `context_snippet`, `sentiment`
- `project_id`, `project_name`, `event_type`, `event_date`, `content`

---

## 12) Semantic search metadata

When appending `journal_chunk` items in `retrieve()`:

```python
metadata={
    "similarity": hit.score,
    "embedding_model": EMBEDDING_MODEL,
    "chunk_mode": settings.EMBEDDING_CHUNK_MODE,
}
```

Optional: pass `chunk_index` if `SemanticHit` gains an `chunk_index` field — **decision:** extend `SemanticHit`:

```python
@dataclass
class SemanticHit:
    entry_date: str
    chunk_text: str
    score: float
    chunk_index: int = 0
```

Populate from `JournalEmbedding.chunk_index` when mapping KNN rowids.

---

## 13) Chat engine

No prompt rewrite required. Optional: one line in `DEFAULT_SYSTEM_PROMPT` noting that `journal_chunk` snippets may include a structured digest when enabled — **decision:** add §13 appendix sentence only if `journal_plus_structured` is default; otherwise skip to avoid prompt churn.

---

## 14) Observability

INFO per `embed_journals` run:

```
embed summary processed=12 reembedded=3 skipped=40 purged=3 chunk_mode=journal_only
```

INFO per entry re-embed:

```
embed date=2026-03-12 chunks=4 hash_old=null hash_new=ab12...
```

WARNING when semantic search returns hits but `chunk_text` is empty (should not happen).

DEBUG when intent returns `entity_focus != none` but stub retrievers return 0 rows (expected before Step 11).

---

## 15) Rollback

- Revert `EMBEDDING_CHUNK_MODE` to `journal_only`, set all `embed_input_hash` NULL, run full re-embed with purge.
- Remove stub fields from `ParsedIntent` only if Step 11 is also reverted — prefer leaving fields nullable/stable.

---

## 16) Testing plan

### 16.1 Unit tests — `build_canonical_source`

- `journal_only`: hash stable across extra whitespace normalization.
- `journal_plus_structured`: same raw + different `life_events` rows → different hash.
- Unshredded entry (`processed_at None`): digest block absent.

### 16.2 Unit tests — staleness

- After mock `purge_entry_embeddings`, `embed_entry_if_stale` writes new rows and sets hash.
- Second call with same DB state: skip (no second API call to Gemini — mock client assert call count).

### 16.3 Integration — shredder + hash

- Patch Gemini embed/shred as needed.
- Shred entry in `journal_plus_structured` mode: `embed_input_hash` becomes NULL after shred (or remains NULL).
- Run `embed_journals`: hash set, vec rows exist.

### 16.4 Integration — retrieval

- Parse intent including new fields using mock JSON response.
- `retrieve()` includes zero `person_mention` rows in Step 9.

### 16.5 Manual golden path

1. `journal_only` mode: shred → verify hash unchanged if raw unchanged; chat thematic query still hits semantic.
2. Switch to `journal_plus_structured`, NULL hashes, re-embed full corpus.
3. Shred one date → hash NULL for that date → re-embed → new chunks include digest in `chunk_text` (spot-check DB).
4. Ask chat: “What did I write about Portuguese?” — verify context includes digest lines when relevant.

---

## 17) Regression matrix

| # | Scenario | Config | Expected |
|---|----------|--------|----------|
| R1 | Fresh ingest + shred + embed | any | Vectors exist; hash set; semantic search non-empty on topical query |
| R2 | Edit journal file on disk | any | Ingest purges + NULL hash; next embed rebuilds |
| R3 | Re-shred same date, same raw | `journal_only` | Hash unchanged; embed skip; vec rowids stable |
| R4 | Re-shred same date, life_events change | `journal_plus_structured` | Hash NULL or mismatch after shred; re-embed replaces chunks |
| R5 | Re-shred, life_events change | `journal_only` | Hash unchanged; chunks still describe raw journal only (OK by design) |
| R6 | Thematic chat query | — | Semantic branch runs; `journal_chunk` in context |
| R7 | Factual + tight date + keywords | — | Mostly `life_event` rows; semantic may still augment if `<3` items |
| R8 | Health keywords | — | `health_metric` rows present |
| R9 | Query “When did I last see Sam?” Step 9 | — | `entity_focus=person`, `prefers_entity_sql=true`, **still no person SQL rows**; answer may be incomplete until Step 11 (document known gap) |
| R10 | `EMBEDDING_SYNC_AFTER_SHRED=true`, single date | `journal_plus_structured` | After shred, that date has fresh vectors without manual embed |
| R11 | Switch chunk mode mid-corpus | — | Full re-embed with purge required; no crash |

---

## 18) Backlog

1. **Nightly embedding sweep** — cron / `operations` job to `embed_journals` for any `embed_input_hash IS NULL`.
2. **Separate vector table** for reflection-only or entity-only chunks (multi-vector per date).
3. **Cross-encoder reranking** on top-k semantic hits.
4. **Chat UI:** show embedding model + chunk mode in debug drawer.
5. **Intent routing table** driven by config JSON instead of prompt-only.

---

## 19) Definition of done

Step 9 is complete when:

- `EMBEDDING_CHUNK_MODE`, invalidation, and hash behavior match §4–§9.
- `embed_journals` uses `build_canonical_source` + hash skip logic; `EmbedResult` reports purged/reembedded dates.
- Shredder marks `embed_input_hash` NULL when structured mode + invalidation enabled.
- Ingestion sets `embed_input_hash` NULL when purging embeddings (if not already).
- `ParsedIntent` extended; stub retrievers wired; `SemanticHit` includes `chunk_index`; `journal_chunk` metadata enriched.
- Tests in §16 pass; regression matrix §17 reviewed in PR description.
- README or Step 13 notes document chunk mode switching procedure.

---

## Changelog

- 2026-05-02 — Initial complete Step 9 spec. Defines journal-only vs journal-plus-structured embedding modes, `embed_input_hash` staleness, shredder invalidation hook, refactored embed pipeline, retrieval intent placeholders for Step 11, semantic hit metadata, and an 11-row regression matrix aligned with Q4.
