# Semantic Memory System for Claude Local

**Status:** Planned
**Priority:** High - Foundation for persistent Claude memory
**Dependencies:** `fpf_engine.py`, SQLite, local embeddings
**Target Location:** `local-utilities/`

---

## Overview

A hybrid storage system combining human-readable JSONL files (source of truth) with a SQLite vector index (derived, rebuildable). This gives us the best of both worlds: debuggable flat files AND semantic search.

---

## Design Principles

| Principle | Implementation |
|-----------|----------------|
| **Human-readable source of truth** | JSONL files you can open, read, git diff |
| **Vectors are derived** | Rebuildable index, not precious data |
| **Append-only logs** | JSONL is naturally append-friendly |
| **Content-hash linkage** | Detect changes, know when to re-embed |
| **Portable** | Share decisions without needing the embedding model |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                      CLAUDE CODE SESSION                             │
│                                                                      │
│  "What did we decide about caching?"                                │
│  "Why did we choose SQLite over Postgres?"                          │
└─────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      SEMANTIC MEMORY API                             │
│                                                                      │
│  memory.search("caching strategy")     → top-k similar records      │
│  memory.store(decision)                → append JSONL + embed       │
│  memory.recall(session_context)        → relevant past decisions    │
│  memory.rebuild_index()                → re-embed from JSONL        │
└─────────────────────────────────────────────────────────────────────┘
                    │                               │
                    ▼                               ▼
┌───────────────────────────────┐   ┌─────────────────────────────────┐
│     SOURCE OF TRUTH           │   │     DERIVED INDEX               │
│     (Human-Readable)          │   │     (Rebuildable)               │
│                               │   │                                 │
│  .quint/                      │   │  .quint/vectors.db              │
│  ├── decisions.jsonl          │──▶│  ├── embeddings                 │
│  ├── hypotheses.jsonl         │   │  │   (id, hash, vector)         │
│  ├── evidence.jsonl           │   │  └── fts_index                  │
│  └── learnings.jsonl          │   │      (full-text search)         │
│                               │   │                                 │
│  • Git-friendly diffs         │   │  • Fast semantic search         │
│  • Human-debuggable           │   │  • Hybrid vector + keyword      │
│  • Portable                   │   │  • Auto-rebuild on mismatch     │
└───────────────────────────────┘   └─────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      LOCAL EMBEDDING MODEL                           │
│                                                                      │
│  Recommended: all-MiniLM-L6-v2 (80MB, 384 dim, ~5ms/embed)          │
│  Alternative: Ollama nomic-embed-text (if already installed)        │
└─────────────────────────────────────────────────────────────────────┘
```

---

## File Structure

```
.quint/
├── decisions.jsonl      # Append-only decision log (SOURCE OF TRUTH)
├── hypotheses.jsonl     # Hypotheses from reasoning cycles
├── evidence.jsonl       # Evidence records
├── learnings.jsonl      # Ad-hoc insights/learnings
├── vectors.db           # SQLite with embeddings (DERIVED, rebuildable)
├── state.json           # Current session state
└── knowledge/           # Active reasoning cycle workspace
    ├── L0/
    ├── L1/
    ├── L2/
    └── invalid/

local-utilities/
├── fpf_engine.py        # FPF reasoning engine
├── semantic_memory.py   # Embedding + search (NEW)
├── requirements.txt     # Dependencies
└── tests/
```

---

## JSONL Format

### decisions.jsonl

```jsonl
{"id":"abc123","type":"decision","question":"Caching strategy for candle data?","chosen_id":"hyp_001","chosen_title":"DO SQLite","alternatives":["hyp_002","hyp_003"],"rationale":"DO SQLite wins: 15ms latency acceptable, zero ops overhead, already in stack.","assumptions":["Single region acceptable","Cloudflare limits won't be hit"],"valid_until":"2025-06-21","created_at":"2025-12-21T10:30:00Z"}
{"id":"def456","type":"decision","question":"Authentication approach?","chosen_id":"hyp_010","chosen_title":"JWT with refresh tokens","alternatives":["hyp_011"],"rationale":"Stateless auth scales better for our use case.","assumptions":["Token rotation is acceptable UX"],"valid_until":"2025-12-21","created_at":"2025-12-21T14:00:00Z"}
```

### hypotheses.jsonl

```jsonl
{"id":"hyp_001","decision_id":"abc123","title":"DO SQLite cache","content":"Cache candle data in Durable Object SQLite, already in our stack.","assumptions":["Single region acceptable","Sub-50ms latency OK"],"layer":"L2","score":0.85,"created_at":"2025-12-21T10:00:00Z"}
{"id":"hyp_002","decision_id":"abc123","title":"Redis distributed cache","content":"Use Redis for sub-ms distributed caching across workers.","assumptions":["Need <10ms latency","Multi-region required"],"layer":"L1","score":0.60,"created_at":"2025-12-21T10:05:00Z"}
```

### evidence.jsonl

```jsonl
{"id":"evi_001","hypothesis_id":"hyp_001","source":"benchmark","content":"DO SQLite p99 latency: 15ms under load","verdict":"pass","congruence":3,"valid_until":"2025-03-21","created_at":"2025-12-21T10:15:00Z"}
{"id":"evi_002","hypothesis_id":"hyp_001","source":"cost_analysis","content":"Zero additional infrastructure cost","verdict":"pass","congruence":3,"valid_until":"2025-06-21","created_at":"2025-12-21T10:20:00Z"}
```

### learnings.jsonl (ad-hoc insights)

```jsonl
{"id":"lrn_001","context":"Debugging pattern backtest failures","insight":"Patterns with >20 conditions tend to overfit. Keep condition count under 15.","source":"manual observation","tags":["patterns","overfitting"],"created_at":"2025-12-21T16:00:00Z"}
{"id":"lrn_002","context":"Cloudflare DO limits","insight":"DO SQLite has 10GB limit per object. Shard by asset for large datasets.","source":"documentation","tags":["cloudflare","limits","sqlite"],"created_at":"2025-12-20T09:00:00Z"}
```

---

## Vector Index Schema (vectors.db)

```sql
-- Lightweight index pointing back to JSONL records
CREATE TABLE embeddings (
    id TEXT PRIMARY KEY,           -- Same as record ID in JSONL
    source_file TEXT NOT NULL,     -- 'decisions', 'hypotheses', etc.
    content_hash TEXT NOT NULL,    -- SHA256 of embedded content
    vector BLOB NOT NULL,          -- float32 array, serialized
    model TEXT,                    -- 'all-MiniLM-L6-v2'
    created_at TEXT
);

CREATE TABLE index_meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
-- Stores: last_rebuild, model_version, record_counts

-- Full-text search for hybrid retrieval
CREATE VIRTUAL TABLE fts_index USING fts5(
    id,
    source_file,
    content,
    tokenize='porter'
);

-- Indexes
CREATE INDEX idx_embeddings_source ON embeddings(source_file);
CREATE INDEX idx_embeddings_hash ON embeddings(content_hash);
```

---

## Content Hash Linkage

The key mechanism for keeping vectors in sync with JSONL:

```python
import hashlib
import json

def compute_content_hash(record: dict) -> str:
    """
    Hash the embeddable content of a record.
    Used to detect when records change and need re-embedding.
    """
    if record.get("type") == "decision":
        content = f"{record['question']}\n{record['rationale']}"
    elif "hypothesis" in record.get("id", ""):
        content = f"{record['title']}\n{record['content']}\n{' '.join(record.get('assumptions', []))}"
    elif "evidence" in record.get("id", ""):
        content = f"{record['source']}: {record['content']}"
    else:
        content = json.dumps(record, sort_keys=True)

    return hashlib.sha256(content.encode()).hexdigest()[:16]


def needs_reembedding(record: dict, stored_hash: str) -> bool:
    """Check if a record's embedding is stale."""
    return compute_content_hash(record) != stored_hash
```

---

## Sync Strategy

### On Store (Append)

```python
def store_decision(self, decision: DecisionRecord):
    # 1. Append to JSONL (source of truth)
    with open(self.decisions_jsonl, 'a') as f:
        f.write(json.dumps(asdict(decision), default=str) + '\n')

    # 2. Compute embedding
    content = f"{decision.question}\n{decision.rationale}"
    content_hash = compute_content_hash(decision)
    vector = self.embedder.embed(content)

    # 3. Store in vector index
    self.db.execute(
        "INSERT OR REPLACE INTO embeddings (id, source_file, content_hash, vector, model, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (decision.id, "decisions", content_hash, vector, self.model_name, datetime.now().isoformat())
    )

    # 4. Update FTS
    self.db.execute(
        "INSERT OR REPLACE INTO fts_index (id, source_file, content) VALUES (?, ?, ?)",
        (decision.id, "decisions", content)
    )
```

### On Search

```python
def search(self, query: str, top_k: int = 5) -> list[MemoryResult]:
    # 1. Embed query
    query_vec = self.embedder.embed(query)

    # 2. Vector similarity search
    vector_results = self._vector_search(query_vec, top_k * 2)

    # 3. FTS keyword search
    fts_results = self._fts_search(query, top_k * 2)

    # 4. Combine with reciprocal rank fusion
    combined = self._reciprocal_rank_fusion(vector_results, fts_results)

    # 5. Fetch full records from JSONL
    results = []
    for record_id, source_file, score in combined[:top_k]:
        record = self._fetch_from_jsonl(source_file, record_id)
        results.append(MemoryResult(record=record, score=score, source=source_file))

    return results
```

### Rebuild Index (from JSONL)

```python
def rebuild_index(self):
    """
    Rebuild entire vector index from JSONL files.
    Called when: model changes, index corrupted, or periodic maintenance.
    """
    print("[Memory] Rebuilding vector index from JSONL...")

    # Clear existing
    self.db.execute("DELETE FROM embeddings")
    self.db.execute("DELETE FROM fts_index")

    # Re-embed all records
    for source_file in ["decisions", "hypotheses", "evidence", "learnings"]:
        jsonl_path = self.quint_dir / f"{source_file}.jsonl"
        if not jsonl_path.exists():
            continue

        with open(jsonl_path) as f:
            for line in f:
                record = json.loads(line)
                content = self._get_embeddable_content(record)
                content_hash = compute_content_hash(record)
                vector = self.embedder.embed(content)

                self.db.execute(
                    "INSERT INTO embeddings (id, source_file, content_hash, vector, model, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (record["id"], source_file, content_hash, vector, self.model_name, datetime.now().isoformat())
                )
                self.db.execute(
                    "INSERT INTO fts_index (id, source_file, content) VALUES (?, ?, ?)",
                    (record["id"], source_file, content)
                )

    self.db.commit()
    print(f"[Memory] Rebuilt index with {self._count_embeddings()} embeddings")
```

### Integrity Check

```python
def check_integrity(self) -> list[str]:
    """
    Verify vector index matches JSONL source of truth.
    Returns list of issues found.
    """
    issues = []

    for source_file in ["decisions", "hypotheses", "evidence", "learnings"]:
        jsonl_path = self.quint_dir / f"{source_file}.jsonl"
        if not jsonl_path.exists():
            continue

        # Load all records from JSONL
        jsonl_records = {}
        with open(jsonl_path) as f:
            for line in f:
                record = json.loads(line)
                jsonl_records[record["id"]] = record

        # Check each has matching embedding with correct hash
        for record_id, record in jsonl_records.items():
            row = self.db.execute(
                "SELECT content_hash FROM embeddings WHERE id = ? AND source_file = ?",
                (record_id, source_file)
            ).fetchone()

            if not row:
                issues.append(f"Missing embedding: {source_file}/{record_id}")
            elif row[0] != compute_content_hash(record):
                issues.append(f"Stale embedding: {source_file}/{record_id}")

    return issues
```

---

## Embedding Strategy

### Model Selection

**Recommended: `all-MiniLM-L6-v2`** via sentence-transformers

| Model | Size | Dim | Speed | Quality |
|-------|------|-----|-------|---------|
| all-MiniLM-L6-v2 | 80MB | 384 | ~5ms/embed | Good |
| all-mpnet-base-v2 | 420MB | 768 | ~20ms/embed | Better |
| nomic-embed-text (Ollama) | 274MB | 768 | ~50ms/embed | Good |

### Embedding Pipeline

```python
class EmbeddingPipeline:
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        from sentence_transformers import SentenceTransformer
        self.model = SentenceTransformer(model_name)
        self.model_name = model_name
        self.dimension = self.model.get_sentence_embedding_dimension()

    def embed(self, text: str) -> bytes:
        """Generate embedding and serialize to bytes."""
        vector = self.model.encode(text, normalize_embeddings=True)
        return vector.astype(np.float32).tobytes()

    def embed_batch(self, texts: list[str]) -> list[bytes]:
        """Batch embedding for efficiency."""
        vectors = self.model.encode(texts, normalize_embeddings=True, batch_size=32)
        return [v.astype(np.float32).tobytes() for v in vectors]
```

---

## Search Implementation

### Hybrid Search (Vector + FTS)

```python
def _vector_search(self, query_vec: bytes, top_k: int) -> list[tuple]:
    """Cosine similarity search over embeddings."""
    query_np = np.frombuffer(query_vec, dtype=np.float32)

    rows = self.db.execute(
        "SELECT id, source_file, vector FROM embeddings"
    ).fetchall()

    scores = []
    for id, source, vec_bytes in rows:
        vec = np.frombuffer(vec_bytes, dtype=np.float32)
        similarity = np.dot(query_np, vec)  # Normalized = cosine
        scores.append((id, source, similarity))

    scores.sort(key=lambda x: -x[2])
    return scores[:top_k]


def _fts_search(self, query: str, top_k: int) -> list[tuple]:
    """Full-text search with BM25 ranking."""
    rows = self.db.execute("""
        SELECT id, source_file, rank
        FROM fts_index
        WHERE fts_index MATCH ?
        ORDER BY rank
        LIMIT ?
    """, (query, top_k)).fetchall()
    return [(r[0], r[1], -r[2]) for r in rows]  # Negate rank (lower = better)


def _reciprocal_rank_fusion(
    self,
    vector_results: list[tuple],
    fts_results: list[tuple],
    k: int = 60,
    vector_weight: float = 0.7
) -> list[tuple]:
    """
    Combine rankings using Reciprocal Rank Fusion.
    Higher k = less emphasis on top results.
    """
    scores = {}

    for rank, (id, source, _) in enumerate(vector_results):
        key = (id, source)
        scores[key] = scores.get(key, 0) + vector_weight / (k + rank + 1)

    for rank, (id, source, _) in enumerate(fts_results):
        key = (id, source)
        scores[key] = scores.get(key, 0) + (1 - vector_weight) / (k + rank + 1)

    sorted_results = sorted(scores.items(), key=lambda x: -x[1])
    return [(k[0], k[1], v) for k, v in sorted_results]
```

---

## JSONL Utilities

```python
def _fetch_from_jsonl(self, source_file: str, record_id: str) -> Optional[dict]:
    """Fetch a specific record from JSONL file."""
    jsonl_path = self.quint_dir / f"{source_file}.jsonl"
    if not jsonl_path.exists():
        return None

    with open(jsonl_path) as f:
        for line in f:
            record = json.loads(line)
            if record.get("id") == record_id:
                return record
    return None


def _iter_jsonl(self, source_file: str):
    """Iterate over all records in a JSONL file."""
    jsonl_path = self.quint_dir / f"{source_file}.jsonl"
    if not jsonl_path.exists():
        return

    with open(jsonl_path) as f:
        for line in f:
            yield json.loads(line)


def export_readable(self, output_path: Path, format: str = "markdown"):
    """Export all decisions to human-readable format."""
    with open(output_path, 'w') as out:
        for decision in self._iter_jsonl("decisions"):
            if format == "markdown":
                out.write(f"# {decision['question']}\n\n")
                out.write(f"**Chosen:** {decision['chosen_title']}\n\n")
                out.write(f"**Rationale:** {decision['rationale']}\n\n")
                out.write(f"**Date:** {decision['created_at']}\n\n")
                out.write("---\n\n")
```

---

## CLI Commands

```bash
# Initialize with semantic memory
python semantic_memory.py init --path /project

# Search past decisions (semantic)
python semantic_memory.py search "caching strategy"
python semantic_memory.py search "what did we decide about authentication"

# Check index integrity
python semantic_memory.py check

# Rebuild index from JSONL
python semantic_memory.py rebuild

# Check for stale decisions
python semantic_memory.py decay

# Export to markdown (human-readable)
python semantic_memory.py export --format markdown --output decisions.md

# Show stats
python semantic_memory.py stats
```

---

## Migration Plan

### Phase 1: JSONL Foundation

1. Modify `fpf_engine.py` to write decisions to JSONL instead of individual markdown files
2. Keep markdown generation as optional export
3. Test append-only behavior, git diffs

### Phase 2: Vector Index

1. Add `sentence-transformers` to requirements.txt
2. Implement `semantic_memory.py` with embedding pipeline
3. Auto-embed on store, create `vectors.db`
4. Implement content-hash linkage

### Phase 3: Search Implementation

1. Implement vector similarity search
2. Implement FTS indexing
3. Implement hybrid search with RRF
4. Add `search()` method to FPF engine

### Phase 4: Integrity & Maintenance

1. Implement `check_integrity()`
2. Implement `rebuild_index()`
3. Add decay checking with JSONL source
4. Add stats/diagnostics

### Phase 5: Claude Integration

1. Add MCP tool for Claude to query memory
2. Auto-inject relevant context at session start
3. Proactive recall during conversations

---

## Why JSONL + Vectors?

| Concern | JSONL Handles | Vectors Handle |
|---------|--------------|----------------|
| Human debugging | ✓ Open file, read it | |
| Git diffs | ✓ Meaningful changes visible | |
| Portability | ✓ Share without model deps | |
| Backup/restore | ✓ Just copy files | |
| Corruption recovery | ✓ Source of truth intact | ✓ Rebuild from JSONL |
| Semantic search | | ✓ Find by meaning |
| Fast retrieval | | ✓ Vector similarity |
| Hybrid search | | ✓ Vector + keyword |

**Key insight:** Vectors are an *index*, not *storage*. Treat them like a database index - derived, rebuildable, not precious.

---

## Dependencies

```txt
# requirements.txt additions
sentence-transformers>=2.2.0
numpy>=1.24.0
```

**Lighter weight option:** Use ONNX runtime backend to avoid full PyTorch:
```python
from sentence_transformers import SentenceTransformer
model = SentenceTransformer("all-MiniLM-L6-v2", device="cpu", backend="onnx")
```

---

## Performance Targets

| Operation | Target | Notes |
|-----------|--------|-------|
| Embed single text | <10ms | all-MiniLM-L6-v2 |
| Search 1000 records | <50ms | Brute force cosine |
| Search 10000 records | <200ms | May need sqlite-vec |
| Store decision | <20ms | Append JSONL + embed |
| Rebuild index (1000) | <30s | Batch embedding |
| Cold start (load model) | <2s | One-time per session |

---

## Open Questions

1. **JSONL compaction**: Over time, may have duplicates (updates). Periodic compaction?
   - *Proposal:* Treat as append-only log, latest wins on duplicate ID

2. **Cross-project memory**: Project-scoped or global?
   - *Proposal:* Project-scoped by default, with optional `--global` flag

3. **Large files**: JSONL at 100k+ records?
   - *Proposal:* Split by year or shard by type if needed

4. **Model updates**: When embedding model changes?
   - *Proposal:* Store model name in `index_meta`, rebuild on mismatch

---

## Success Criteria

- [x] JSONL files are human-readable (can open in any editor)
- [x] Git diffs show meaningful changes
- [ ] `memory.search("caching")` returns relevant decisions by meaning
- [ ] Sub-100ms search latency for typical corpus (<1000 records)
- [ ] `rebuild_index()` regenerates vectors from JSONL
- [ ] `check_integrity()` detects stale embeddings
- [ ] Decisions persist across Claude sessions
- [ ] Decay warnings surface stale decisions

---

*Plan updated: JSONL as source of truth, vectors as derived index.*
