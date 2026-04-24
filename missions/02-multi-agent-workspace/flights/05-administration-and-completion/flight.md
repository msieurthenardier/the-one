# Flight: Administration & Completion

**Status**: in-flight
**Mission**: [Multi-Agent Workspace](../../mission.md)

## Contributing to Criteria
- [ ] The web interface is organized into switchable functional areas (Studio, Chat, Administration) through an app-shell architecture
- [ ] Each functional area has a consistent layout (sidebar + main panel) with area-specific content, and a shared navigation mechanism
- [ ] The Administration area is present with a small number of functional settings and placeholder categories for future expansion

---

## Pre-Flight

### Objective
Build the Administration area with read-only settings display and placeholder categories, completing the final three mission success criteria. Admin is the last missing functional area — Studio and Chat are already implemented.

### Open Questions
- [x] Should settings be editable through the UI? → No, read-only display (D1)
- [x] What categories should the admin sidebar have? → Four categories (D2)
- [x] Should documentation updates be included? → Yes, Flight 04 debrief action item (D4)

### Design Decisions

**D1. Settings are read-only display from live `settings` singleton.** `GET /api/settings` reads from the `settings` object (populated from env vars / `.env` at startup). No write endpoint. Users change settings via environment variables and restart the server. A note in the UI explains this.
- Rationale: `pydantic_settings.BaseSettings` reads env vars at import time. Writing back to `.env` introduces restart-awareness complexity, env var vs .env priority conflicts, and partial-apply bugs. The mission spec says "a small number of functional settings" — read-only display satisfies this. Admin is explicitly "placeholder scaffolding" territory.
- Trade-off: Users must edit env vars and restart to change settings. Acceptable for a single-user system.

**D2. Admin sidebar has category navigation with active/placeholder distinction.** Four categories:
- **General** (active) — LLM config, paths, server info from `GET /api/settings`
- **Agents** (placeholder) — future: default agent, import/export
- **Integrations** (placeholder) — future: MCP connection management, KB pipeline config
- **System** (placeholder) — future: logs, diagnostics, backup/restore
- Rationale: Mission spec requires "placeholder categories for future expansion." Four categories demonstrate extensibility without overbuilding.

**D3. Admin follows the Studio sidebar+content pattern.** Clicking a sidebar category switches the content panel. General panel shows read-only settings in labeled field rows grouped into sections. Placeholder panels show category name + "Coming soon" text.

**D4. Documentation updates included in scope.** Update CLAUDE.md with persistence model, admin area, and settings endpoint documentation. This was a Flight 04 debrief action item explicitly marked for Flight 05.

### Prerequisites
- [x] Flight 01 complete (DB persistence layer)
- [x] Flight 02 complete (app shell)
- [x] Flight 03 complete (Studio agent builder)
- [x] Flight 04 complete (chat evolution)

### Pre-Flight Checklist
- [x] All open questions resolved
- [x] Design decisions documented
- [x] Prerequisites verified
- [x] Validation approach defined
- [x] Legs defined

---

## In-Flight

### Technical Approach
Add a `GET /api/settings` endpoint that returns all config values from the `Settings` class. Replace the admin stub with a full Administration area following the same sidebar+content pattern as Studio. The General category fetches settings and displays them as read-only fields grouped into sections. Three placeholder categories show "Coming soon" text.

### Checkpoints
- [x] Settings API returns correct JSON
- [x] Admin area shows 4 categories with General active
- [ ] All three areas navigate correctly
- [ ] Documentation is accurate

### Adaptation Criteria

**Divert if**:
- Settings model has undiscovered complexity (e.g., nested configs)
- Admin layout conflicts fundamentally with app shell

**Acceptable variations**:
- Minor CSS adjustments for field layout
- Slightly different section grouping for settings

### Legs

- [x] `settings-api` - Add `GET /api/settings` endpoint returning all config values
- [x] `admin-area-ui` - Replace admin stub with functional Administration area
- [ ] `docs-and-uat` - Documentation updates and end-to-end verification

---

## Post-Flight

### Completion Checklist
- [ ] All legs completed
- [ ] Code merged
- [ ] Tests passing
- [ ] Documentation updated

### Verification
1. Navigate to Admin via gear icon — 4 categories, General selected
2. General panel shows correct LLM provider, model, base URL, data dir, etc.
3. Click each placeholder category — "Coming soon" appears
4. Switch between Chat/Studio/Admin — consistent layout, no glitches
5. `curl http://localhost:8484/api/settings` — returns correct JSON
6. Existing tests pass
7. Mission criteria 8, 9, 10 are met
