# Flight: Studio — Agent Builder

**Status**: landed
**Mission**: [Multi-Agent Workspace](../../mission.md)

## Contributing to Criteria

- [x] Users can create, edit, and delete agent definitions through a Studio interface, configuring name, description, LLM provider/model, and system prompt for each
- [x] Built-in tools can be selectively enabled or disabled per agent through the Studio interface
- [x] MCP tool sources (local stdio and remote SSE) can be registered and attached to agents through the Studio interface, with the data model and persistence in place
- [x] Knowledge bases can be attached to and detached from agents through the Studio interface, with the association persisted

---

## Pre-Flight

### Objective

Build the Studio area: agent list sidebar with create/delete, full agent editor panel (identity, LLM config, system prompt, tool toggles, MCP/KB attachment chips), dirty tracking, and save. Add a tools listing API endpoint. Wire everything to the existing REST CRUD endpoints from Flight 01.

### Design Decisions

**D1. Single scrollable form, not tabs.** The editor has ~5 sections (identity, LLM config, system prompt, tools, connections). Total content fits comfortably in one scroll. Tabs hide information and add complexity for no benefit.

**D2. Agent name is editable on create, displayed as header on edit.** Name is the PK and immutable after creation. On edit, it renders as the panel header (not a disabled input). The API already enforces this (`PUT` overwrites `data["name"]` from the URL path).

**D3. Tool toggles with descriptions, grouped by category.** 14 tools grouped into 4 categories (Filesystem, Execution, Web, System). Each tool row: toggle switch + name (monospace) + description (dimmed). Select All / Deselect All at the top.

**D4. Chip/tag pattern for MCP and KB attachment.** Current attachments shown as removable chips. "Add" button opens dropdown of available (unattached) items. Minimal UI since these are stubs.

**D5. Explicit Save with dirty tracking.** Save button grayed when clean, accent-colored when dirty. Switching agents with unsaved changes triggers `confirm()` dialog. No auto-save.

**D6. Inline delete confirmation.** Click "Delete" -> button changes to "Confirm Delete?" (red) for 3 seconds -> second click deletes. No modal.

**D7. Tool toggle state mapping.** UI tracks a simple set of enabled tool names. On save: all on -> `enabled_tools: null, disabled_tools: []`; some off -> uses blacklist or whitelist based on which list is shorter.

### Prerequisites

- [x] Flight 01 complete (REST API for agents, MCP sources, knowledge bases)
- [x] Flight 02 complete (app shell, area registration, sidebar/content pattern)

### Pre-Flight Checklist

- [x] All open questions resolved
- [x] Design decisions documented
- [x] Prerequisites verified
- [x] Validation approach defined
- [x] Legs defined

---

## In-Flight

### Technical Approach

Three-leg implementation: (1) tools API endpoint, (2) Studio sidebar with agent list and CRUD, (3) full editor panel with all fields, toggles, chips, and save logic. All vanilla JS following the closure-based area pattern from chat.js.

### Legs

- [x] `tools-api` - Add GET /api/tools endpoint exposing built-in tool names and descriptions
- [x] `sidebar-and-crud` - Studio sidebar with agent list, create/delete, selection
- [x] `editor-panel` - Full editor form with all AgentConfig fields, tool toggles, MCP/KB chips, dirty tracking, save
- [x] `uat-and-alignment` - Interactive UAT session with verification of all acceptance criteria

---

## Post-Flight

### Completion Checklist

- [x] Tools API endpoint implemented and verified (14 tools returned)
- [x] Studio sidebar with agent list, create, delete with inline confirmation
- [x] Full editor form with all fields
- [x] All legs completed
- [x] Code committed

### Verification

1. Navigate to Studio (`#studio`) — area loads, nav rail highlights
2. Create agent — fill form, click Create, agent appears in sidebar and persists via API
3. Edit agent — select, modify fields, save, reload confirms persistence
4. Tool toggles — disable some, save, reload, toggles reflect saved state
5. MCP/KB attachment — attach/detach sources, save, verify association persists
6. Delete agent — inline confirmation, agent removed from list and database
7. Dirty state — modify field, switch agents, confirmation dialog appears
8. Empty state — delete all agents, "No agents" message shown
