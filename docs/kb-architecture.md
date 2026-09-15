# Knowledge Base Architecture for Personal Agentic System

> **Superseded.** This is a pre-mission research survey, not a decision
> record. `missions/24-knowledge-bases/mission.md` supersedes it as the
> source of truth. Its scale target ("10s of GB per KB", below) was revised
> down by the operator to the mission's Constraints ceiling — low
> single-digit GB of raw text per KB. The mission adopted this survey's
> general shape (a bundled local static-embedding model; a vectors-only,
> disk-first store) but not its specific vendor picks — it chose
> `potion-retrieval-32M` over Nomic/BGE, and `sqlite-vec`/`usearch` over
> LanceDB (ruled out on weight at the corrected, lower ceiling).
> `sqlite-vec` was removed in Flight 2 Leg 6 after the benchmark; `usearch`
> is the shipped store.

## Context

Personal agentic system where users create multiple curated knowledge bases (KBs) — each indexing files and/or crawled websites — and attach them to agents. Agents decide at runtime whether to query a given KB.

**Constraints:**
- Single user, but corpora reach low single-digit GB per KB (originally surveyed at 10s of GB; revised down — see Mission 24)
- Not memory-resident — disk-first storage required
- One user may maintain dozens of KBs (notebook-style)
- Audience: regular WFH users / small businesses — runs on laptops, expects offline & private
- KBs are **targeted and curated**, not "index everything" — separate filesystem/document tools handle ad-hoc access

---

## Open-Source RAG Landscape (Late 2025 / Early 2026)

### 1. Vector Databases / Stores

| Tool | Hosting | Strengths | Typical use |
|---|---|---|---|
| **Qdrant** | Embedded or server (Rust) | Fast, rich payload filtering, native hybrid (sparse+dense) | Default when you outgrow pgvector |
| **Chroma** | Embedded or server | Simplest API, great DX, built around LLM apps | Prototypes; weakest at scale |
| **Weaviate** | Server | Built-in vectorizer modules, hybrid search, GraphQL | Batteries-included; powers Verba |
| **Milvus** | Server (distributed) | Billion-scale, GPU acceleration | Massive corpora; heavy ops |
| **LanceDB** | Embedded (columnar Lance format) | Disk-based, larger-than-memory, multimodal, no server | Local agents, edge, big-on-disk datasets |
| **pgvector** | Postgres extension | One DB for everything; HNSW matches dedicated DBs to ~1–5M vectors | Default if you already run Postgres |
| **Vespa** | Server (JVM) | Search engine + vector + ranking framework | Search/recommendation hybrids at scale |
| **FAISS** | Library (C++/Python) | Fastest pure ANN, GPU support, quantization | Component, not a DB |

**Mature vs hyped:** Qdrant, Milvus, pgvector, FAISS, Weaviate are solidly mature. Chroma is mature for prototyping but has scaling gaps. LanceDB is rising fast in the embedded/multimodal niche.

### 2. RAG Frameworks / Orchestration

- **LlamaIndex** — Strongest data-ingestion and indexing layer (LlamaHub connectors, structured indices). Best when shaping heterogeneous data is the hard part.
- **LangChain (RAG bits)** — Broadest integrations, fast prototyping, heavier abstraction. **LangGraph** (sibling) is the most mature production agent loop.
- **Haystack (deepset)** — Pipeline-as-graph, low overhead, strong production stability and observability.
- **txtai** — All-in-one embeddings DB + workflows in a small package; runs on edge.
- **RAGFlow** — Self-hosted, deep document understanding (tables, scanned PDFs), low-code UI.
- **Verba** — Reference RAG app on Weaviate; useful as a starting template.
- **R2R** — Opinionated "RAG-as-a-service" with built-in agentic Deep Research.
- **Cognita (TrueFoundry)** — Productionization-focused wrapper around LlamaIndex/LangChain.

### 3. Embedding Models

- **BGE family (BAAI)** — `bge-large-en-v1.5` and `bge-m3` are workhorses. **BGE-M3** does dense + sparse + multi-vector in one model and 100+ languages.
- **E5 (Microsoft)** — `e5-large-v2` / `multilingual-e5-large`; quality near BGE.
- **Nomic Embed v2** — 137M-param MoE, runs on CPU, Matryoshka dims (64–768), 8K context. Best quality-per-byte.
- **Jina v3** — 8K context with "late chunking"; strong for long documents.
- **GTE (Alibaba)** — `gte-multilingual-base` competitive with BGE.
- **Sentence-Transformers (`all-MiniLM-L6-v2`)** — Tiny, fast, sensible CPU baseline.

**Tradeoffs:** Larger models (~1B params) gain ~2–5 MTEB points over MiniLM at 10–50× the hosting cost. BGE-base or Nomic v2 hits the sweet spot.

### 4. Agent-Specific KB Patterns

- **Hybrid search (BM25 + vector)** — Table-stakes. Reciprocal Rank Fusion (RRF) merges results.
- **Reranking** — `bge-reranker-v2-m3` is the dominant open cross-encoder. Adds ~10 MRR points; highest-ROI single addition.
- **GraphRAG (Microsoft)** — Entities/relationships into a KG, summarizes graph "communities" for global queries. **LazyGraphRAG** (2025) cut indexing cost ~1000×.
- **Agentic RAG** — Multi-step retrieval, routing, reflection. **LangGraph** is the production leader.
- **Memory systems** (separate from doc RAG):
  - **Mem0** — Most mature SaaS; vector-similarity over extracted memories.
  - **Letta (formerly MemGPT)** — Tiered memory with LLM-managed eviction; full agent runtime.
  - **Zep / Graphiti** — Temporal knowledge graph with validity windows.
  - **Cognee, LangMem, Supermemory** — Smaller OSS-local entrants.

### 5. Typical Architecture

```
[Sources] → INGEST → CHUNK → EMBED → STORE → RETRIEVE → RERANK → GENERATE
              │        │       │        │        │          │         │
   LlamaHub /          │   BGE/E5/    Qdrant/  Hybrid:    bge-      LLM +
   RAGFlow /           │   Nomic/     pgvector BM25 +     reranker  citations
   Haystack            │   Jina       Milvus/  vector     -v2-m3
   loaders             │   (TEI)      Lance    (RRF)
                       │                       + filters
                semantic /
                heading-aware
                chunking

         Agent loop wraps RETRIEVE→GENERATE (LangGraph / LlamaIndex Agents)
                                  │
                  ┌───────────────┴───────────────┐
                  │                               │
            Doc KB (above)              Memory (Mem0/Letta/Zep)
                                                  │
                              Optional: GraphRAG layer for global
                              / cross-document relational queries
```

---

## Recommended Stack for This Use Case

Given the constraints (single-user, multiple isolated curated KBs, agent-as-tool-router, at the originally-assumed 10s-of-GB scale — superseded, see notice above), the landscape narrows hard.

### Storage: LanceDB

Unambiguous fit:
- **Embedded** — no server to run on a laptop or SBC
- **Disk-first** — handles the originally-assumed 10s-of-GB scale (superseded, see notice above); rules out Chroma and most in-memory options
- **One table per KB** — perfect isolation, trivial add/drop
- **Built-in BM25 full-text search** — get hybrid (vector + keyword) without bolting on a second system

pgvector forces every user to run Postgres. Qdrant embedded works but is server-flavored. Milvus is wildly overkill.

### Embeddings: Nomic Embed v2 (or `bge-small-en-v1.5`)

- Run on CPU at acceptable speed via `sentence-transformers` or HuggingFace's `text-embeddings-inference`
- Nomic's Matryoshka dims (truncate to 256/384/512) trade recall for disk space — useful at the originally-assumed 10s-of-GB scale (superseded, see notice above)
- **Avoid API-based embeddings** for this audience: privacy expectation + offline use + per-token cost on a 10GB corpus

### Ingestion

- **Files:** LlamaIndex's readers (`SimpleDirectoryReader` + format-specific extractors) cover PDF/docx/markdown/code. Use semantic or heading-aware chunking, not fixed-size.
- **Web crawling:** **Crawl4AI** — purpose-built for LLM ingestion (clean markdown, JS rendering, sitemap-driven). Firecrawl OSS is the alternative. Don't roll your own — boilerplate stripping is where naive crawlers fail.

### Reranking

Skip initially. Add `bge-reranker-v2-m3` later only if retrieval quality demands it. Cross-encoders cost real CPU time and the gain is marginal once hybrid search + good chunking are in place.

### Agent Integration

Don't reach for LangGraph/LlamaIndex Agents for this. The routing problem is **one tool per KB**, with the user-authored description as the routing signal:

```
search_tax_docs(query)      — "2023–2025 tax filings, 1099s, receipts"
search_client_emails(query) — "archived client correspondence, project X"
```

The agent picks based on tool descriptions. Cheapest, most legible architecture, composes naturally with existing filesystem tools.

---

## Non-Obvious Things to Plan For

1. **Embedding throughput is the bottleneck, not retrieval.** Embedding 10 GB of text on CPU is hours-to-days. Make ingestion **resumable** (checkpoint per file/URL), show progress, run it as a background job — not blocking the UI.

2. **Disk budget ≈ 2–3× raw text.** Vectors + BM25 index + Lance overhead. A 10 GB corpus → ~25–30 GB on disk. Tell users.

3. **Web KBs go stale.** Per-KB refresh policy (manual, weekly, on-demand) and per-source last-crawled timestamps. Without this, web KBs rot silently.

4. **Per-KB tool descriptions are the routing brain.** Make the UI for writing them prominent — bad descriptions → wrong KB picked → bad answers, and the user blames the model. Consider auto-generating a draft from indexed content and letting the user edit.

5. **Chunk metadata matters more than the chunker.** Always store `{source_path, url, page, last_modified, kb_id}`. Enables citations, freshness filtering, source-level dedup later — cheap now, painful to retrofit.

6. **Don't pre-build GraphRAG/memory layers.** Curated, targeted KBs + a competent agent loop solve 90% of the problem. Add complexity only when retrieval failures motivate it.

---

## The 80% Architecture

**LanceDB (one table per KB) + Nomic/BGE embeddings + Crawl4AI + LlamaIndex readers + KB-as-tool.**

Differentiate above that line only when measured retrieval quality demands it.
