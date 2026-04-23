# Mission: Multi-Agent Workspace

**Status**: active

## Outcome

The-one becomes a multi-agent workspace where users can design, manage, and interact with specialized agents through a unified web interface. Each agent has its own identity, LLM configuration, system prompt, attached tools, and knowledge base references. Conversations persist across restarts. The interface is organized into distinct functional areas — Studio for agent construction, Chat for agent interaction, and Administration for system settings — all sharing a consistent look and feel through an extensible app-shell architecture that supports adding new areas in the future.

## Context

Mission 01 (Structural Foundation) established the architectural foundation: clean module boundaries, `AgentConfig` with Pydantic persistence, `AgentFactory`, `ToolProvider` protocol, and a working web UI. However, the current system only supports a single default agent with in-memory sessions. There is no way to create or manage agents through the UI, no concept of knowledge bases, no chat history persistence, and no tool attachment beyond name-based filtering. The web UI is a single-purpose chat page — it needs to evolve into a multi-area workspace.

This mission builds on the Mission 01 foundation to deliver the data model, persistence layer, and UI framework that make the-one a usable multi-agent platform. Three capabilities are deliberately stubbed with data models and UI shells but no functional implementation — these are scoped as their own future missions:

- **MCP integration** — data model for MCP sources (stdio and SSE) with attachment to agents, but no actual protocol connection or tool discovery
- **Knowledge base pipeline** — data model for KBs and items (files, URLs, hierarchical sub-items) with agent attachment, but no file upload, crawling, embedding, or RAG retrieval
- **Administration** — a few functional settings are included, but most categories are placeholder scaffolding

## Success Criteria

- [ ] Users can create, edit, and delete agent definitions through a Studio interface, configuring name, description, LLM provider/model, and system prompt for each
- [ ] Built-in tools can be selectively enabled or disabled per agent through the Studio interface
- [ ] MCP tool sources (local stdio and remote SSE) can be registered and attached to agents through the Studio interface, with the data model and persistence in place — actual MCP connection and tool discovery is stubbed for a future mission
- [ ] Knowledge bases can be created with a name and description, and items (files or URLs) can be added to them, with the data model supporting hierarchical sub-items (directory trees, crawled page trees) — actual file upload, crawling, and RAG retrieval are stubbed for future missions
- [ ] Knowledge bases can be attached to and detached from agents through the Studio interface, with the association persisted
- [x] Chat conversations persist across application restarts, with each session's full message history (including tool calls and results) recoverable when the user returns
- [x] Users can select which agent to converse with, and the selected agent's configuration (LLM, prompt, tools) is reflected in the conversation
- [ ] The web interface is organized into switchable functional areas (Studio, Chat, Administration) through an app-shell architecture that can accommodate additional areas without structural changes
- [ ] Each functional area has a consistent layout (sidebar + main panel) with area-specific content, and a shared navigation mechanism for switching between areas
- [ ] The Administration area is present with a small number of functional settings (e.g., default LLM provider/model, data directory) and placeholder categories for future expansion

## Stakeholders

- **Primary user**: Solo developer/operator who wants to create specialized agents for different tasks (coding, research, ops) without editing JSON config files
- **Future self-modification**: The agent itself, which will eventually manage its own agent definitions and knowledge bases programmatically

## Constraints

- **No frontend frameworks**: No React, Vue, Svelte, or similar. Vanilla JS with custom architecture. AI generates frontend code well; framework dependencies add supply-chain risk and impose constraints.
- **No heavy backend frameworks beyond FastAPI**: The existing FastAPI + WebSocket stack is the foundation. No Django, Flask migration, etc.
- **Minimal new dependencies**: Any new library must justify itself against writing the code by hand. `aiosqlite` is approved (async wrapper for stdlib sqlite3, ~300 lines). RAG/embedding libraries are expected for the knowledge base pipeline in a future mission, but this mission stubs that boundary. No ORMs (SQLAlchemy, etc.) — raw SQL only.
- **Preserve existing functionality**: The CLI interface, self-deployment, and Concourse pipeline must continue working. The web UI evolution must not break programmatic API consumers (`/api/chat`, `/api/selftest`).
- **Python 3.11+, async throughout**: Maintain current runtime requirements.
- **Small-model friendly**: Data models, API contracts, and UI component patterns should be simple enough for 7B-class models to work with.

## Environment Requirements

- Local Python 3.11+ with editable install (`pip install -e ".[all-llms,dev]"`)
- Docker and docker-compose for container testing
- Concourse CI instance (concourse-local) for pipeline validation
- Ollama with qwen2.5:7b (or equivalent) for local LLM testing
- ruff for linting and formatting
- A browser for UI development and testing

## Open Questions

_(none currently open)_

## Resolved Questions

- **Persistence format**: SQLite + aiosqlite. Single file (`~/.the-one/the-one.db`), one small pure-Python dependency, handles relational queries (sessions by agent), tree structures (KB items via recursive CTEs), and large chat histories. No ORM — raw SQL. Hand-rolled schema versioning, no migration framework. Existing JSON agent configs migrated to SQLite on first run.
- **App-shell routing**: Hash-based (`#chat`, `#studio`, `#admin`). Simpler than History API — no server-side route handling needed. Default area is `chat`. Resolved during Flight 02 implementation.
- **Message serialization**: Custom codec (`the_one/db/codec.py`) with `encode_messages()` / `decode_messages()`. Keeps Message as plain dataclasses in the LLM core; codec handles JSON serialization for persistence. Avoids adding Pydantic dependency to hot-path agent loop. Resolved during Flight 01 implementation.

## Known Issues

_(none yet — this is a new mission)_

## Flights

> **Note:** These are tentative suggestions, not commitments. Flights are planned and created one at a time as work progresses. This list will evolve based on discoveries during implementation.

- [x] Flight 1: **Data Model & Persistence** — Extend AgentConfig with tool attachment and KB references. Design KnowledgeBase, KBItem, MCPSource, and ChatSession data models. Implement persistence for all models (with protocol abstractions for future swapability). Resolve open questions on chat history storage format and message serialization. Design the REST API surface for all CRUD operations.
- [x] Flight 2: **App Shell & Navigation** — Build the extensible app-shell architecture (vanilla JS component system, area registry, sidebar/panel layout, app switcher icon). Migrate the existing chat UI into the Chat area. Establish the frontend patterns all areas will use.
- [x] Flight 3: **Studio — Agent Builder** — Build the Studio area: agent list sidebar, agent editor panel (name, description, LLM config, system prompt, built-in tool toggles, MCP source attachment stubs, KB attachment stubs). Full agent CRUD through the UI backed by the persistence APIs.
- [x] Flight 4: **Chat Evolution** — Add agent picker to Chat area, wire agent selection to AgentFactory, implement persistent chat history (full message list save/load/purge), restore sessions on startup.
- [ ] Flight 5: **Administration & Completion** — Build Administration area with functional settings (default LLM provider/model, data directory) and placeholder categories. Resolve any remaining Mission 01 debrief action items that intersect with this mission's scope. End-to-end verification.
- [ ] Flight 6 *(optional)*: **Alignment** — Interactive vibe-coding session for UI polish, UX refinement, and hands-on adjustments across all areas.
