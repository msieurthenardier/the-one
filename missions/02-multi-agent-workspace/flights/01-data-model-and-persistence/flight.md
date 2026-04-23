# Flight: Data Model & Persistence

**Status**: landed
**Mission**: [Multi-Agent Workspace](../../mission.md)

> **Note:** This flight spec was created retroactively after implementation. It captures what was done, not what was planned upfront. No formal leg specs were created prior to execution.

## Contributing to Criteria

- [x] Chat conversations persist across application restarts, with each session's full message history recoverable
- [x] MCP tool sources can be registered and attached to agents (data model and persistence — actual MCP connection stubbed)
- [x] Knowledge bases can be created with name/description, items added, hierarchical sub-items supported (data model — actual file upload, crawling, RAG stubbed)
- [x] Knowledge bases can be attached to and detached from agents (association persisted)

---

## Pre-Flight

### Objective

Implement the complete data model and async SQLite persistence layer for the multi-agent workspace: agent configs, knowledge bases, KB items, MCP sources, and chat sessions. Provide REST API endpoints for all CRUD operations. Migrate existing JSON agent configs to SQLite.

### Design Decisions

**SQLite + aiosqlite**: Single-file database with async wrapper
- Rationale: One small pure-Python dependency (~300 lines), handles relational queries, tree structures (KB items via parent_id), and large chat histories
- Trade-off: No concurrent write scaling, but acceptable for single-user workstation

**Raw SQL, no ORM**: Hand-written queries with manual schema versioning
- Rationale: Full control, no migration framework complexity, small-model friendly
- Trade-off: More boilerplate for CRUD; schema changes require manual migration code

**Protocol-based store abstraction**: `AgentConfigStore` protocol decouples factory from storage
- Rationale: Enables swapping SQLite for other backends without touching consumer code
- Trade-off: Extra indirection layer

**Manual message codec**: Custom JSON encoder/decoder for Message dataclasses
- Rationale: Keeps LLM core model-agnostic (no Pydantic dependency on Message); isolated serialization
- Trade-off: Must be updated when Message types change

**UUID hex IDs (12 chars)**: Shorter than full UUIDs
- Rationale: Readable URLs, easy to reference in UI
- Trade-off: Slightly higher collision probability (negligible at expected scale)

**Cascade deletes on foreign keys**: Agent deletion cascades to chat sessions
- Rationale: Automatic cleanup, no orphaned records
- Trade-off: Irreversible — deleting an agent destroys all its chat history

### Prerequisites

- [x] Mission 01 complete (AgentConfig, AgentFactory, ToolProvider protocol)
- [x] aiosqlite dependency approved

---

## In-Flight

### Technical Approach

Six-layer architecture: schema definition, Pydantic data models, message codec, async CRUD repositories, REST API router, and one-time JSON-to-SQLite migration.

### Legs

Work was executed as a continuous implementation session without formal leg boundaries. Logical groupings:

- [x] `schema-and-connection` — SQLite schema (6 tables), connection singleton, WAL mode, FK enforcement
- [x] `data-models` — Pydantic v2 models for KnowledgeBase, KBItem, MCPSource, ChatSession
- [x] `message-codec` — Round-trip JSON serialization for Message dataclasses (ToolCall, ToolResult, TokenUsage, Role enum)
- [x] `repositories` — Five async CRUD repository classes (SQLiteAgentStore, KnowledgeBaseRepository, KBItemRepository, MCPSourceRepository, ChatSessionRepository)
- [x] `rest-api` — FastAPI router with complete CRUD endpoints for all entities
- [x] `migration` — One-time idempotent migration from FilesystemConfigStore JSON to SQLite
- [x] `integration` — CLI and web app startup wiring (init_db, migrate, factory injection)
- [x] `tests` — 50+ tests across 5 test modules

---

## Post-Flight

### Completion Checklist

- [x] All logical legs completed
- [x] Tests passing (50+ tests)
- [x] REST API functional for all entities
- [x] Migration preserves existing agent configs
- [ ] Code not yet committed (part of larger working tree)

### Verification

- All CRUD operations exercised through test suite
- Message codec round-trips complex conversation histories
- Migration idempotent (safe to run repeatedly)
- CLI and web app both initialize DB and create factory from SQLite store
