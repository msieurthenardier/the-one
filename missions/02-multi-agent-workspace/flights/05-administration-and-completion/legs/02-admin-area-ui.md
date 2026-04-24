# Leg: admin-area-ui

**Status**: completed
**Flight**: [Administration & Completion](../flight.md)

## Objective
Replace the admin stub with a functional Administration area featuring sidebar category navigation and read-only settings display.

## Context
- Design decisions D2 and D3: Admin has 4 sidebar categories (General active, 3 placeholders), follows the Studio sidebar+content pattern
- The current admin.js is a stub that shows "Coming in Flight 05"
- The Studio area (`studio.js`, 613 lines) is the pattern reference: sidebar list + content panel, section titles, field rows, `escapeHtml()`
- The app shell (`app.js`) uses `App.registerArea()` with `init(sidebar, content)`, `activate()`, `deactivate()` lifecycle
- CSS variables are in `styles.css`: `--bg`, `--fg`, `--accent`, `--surface`, `--border`
- `GET /api/settings` endpoint is now available (Leg 01 complete)

## Inputs
- `the_one/interfaces/web/static/js/areas/admin.js` — current stub (18 lines)
- `the_one/interfaces/web/static/styles.css` — existing styles
- `GET /api/settings` — returns JSON with all config fields

## Outputs
- `the_one/interfaces/web/static/js/areas/admin.js` — full rewrite with sidebar categories and settings display
- `the_one/interfaces/web/static/styles.css` — admin area CSS appended

## Acceptance Criteria
- [x] Admin shows sidebar with 4 categories: General, Agents, Integrations, System
- [x] General is selected by default on first load
- [x] Active category has visual highlighting (same pattern as Studio agent list)
- [x] General panel fetches `GET /api/settings` and displays all settings in labeled read-only fields
- [x] Settings are grouped into sections: LLM Configuration, Paths, Server, Concourse CI
- [x] Each field row shows label, value, and the env var name (e.g., `THE_ONE_LLM_PROVIDER`)
- [x] A note at the top explains settings are configured via environment variables
- [x] Placeholder categories (Agents, Integrations, System) show "Coming soon" text
- [x] Placeholder categories have a visual badge ("Soon") distinguishing them from active categories
- [x] Area navigation (Chat/Studio/Admin) works correctly — switching areas works without glitches
- [x] `activate()` refreshes settings (in case server restarted with new env vars)
- [x] Consistent look and feel with Studio and Chat (uses same CSS variables, font, spacing patterns)

## Verification Steps
- Start server, navigate to `#admin` — General panel loads with settings
- Click each placeholder category — "Coming soon" appears
- Switch Chat → Studio → Admin — no layout glitches
- Restart server with a changed env var, switch to Admin — updated value appears

## Implementation Guidance

1. **Rewrite `admin.js`** — Complete replacement of the stub file:
   - Keep `App.registerArea()` with same `id: 'admin'`, `label: 'Admin'`, `icon: '\u2699\uFE0F'`, `order: 30`
   - Define categories array: `[{id: 'general', label: 'General', active: true}, {id: 'agents', label: 'Agents', active: false}, {id: 'integrations', label: 'Integrations', active: false}, {id: 'system', label: 'System', active: false}]`
   - `init(sidebar, content)`:
     - Build sidebar with header ("Administration" title) + category list container
     - Build content with admin content container
     - `renderCategoryList()` — renders category items with active class and placeholder badge
     - `renderContent()` — switches between `renderGeneralPanel()` and `renderPlaceholder()`
     - `renderGeneralPanel()` — shows a "Loading settings..." message, fetches `/api/settings`, replaces with sections of field rows on success (no-op on failure — loading message stays)
     - `renderPlaceholder()` — shows category name + "Coming soon" centered
     - Helper: `settingRow(label, value, envVar)` — returns HTML for one field row. The `envVar` parameter is constructed as `"THE_ONE_" + field_name.toUpperCase()` (matching the `env_prefix` in Settings model config)
     - Helper: `escapeHtml(s)` — same pattern as studio.js
     - Category click handler: updates `currentCategory`, re-renders list and content
   - `activate()`:
     - If currently on General, re-fetch settings and re-render (handles server restart with new env)
   - `deactivate()`: empty

2. **Add admin CSS to `styles.css`** — Insert before `/* === Stub Areas === */`:
   - Scope all rules under `.area-admin`
   - Sidebar: `.admin-sidebar-header` (matches `.studio-sidebar-header` pattern), `.admin-category-list`, `.admin-category-item` (matches `.agent-item` pattern), `.admin-category-badge`
   - Content: `.admin-content`, `.admin-header`, `.admin-title`, `.admin-form`, `.admin-note` (info box), `.admin-section`, `.admin-section-title`, `.admin-field-row` (label + value + env var), `.admin-field-value` (read-only field appearance), `.admin-field-env` (dimmed env var name), `.admin-placeholder` (centered "Coming soon")
   - Use the same values as Studio for padding, font sizes, border radius, and colors to maintain consistency

## Edge Cases
- **Fetch failure**: If `/api/settings` fails, the loading state should remain (no crash). The endpoint is local-only so this is extremely unlikely.
- **Long values**: Path values may be long — use `text-overflow: ellipsis` on `.admin-field-value`
- **Empty values**: If a setting value is null/undefined, show "not set" in dimmed italic

## Files Affected
- `the_one/interfaces/web/static/js/areas/admin.js` — full rewrite
- `the_one/interfaces/web/static/styles.css` — admin CSS added

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified
- [x] Tests passing
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `completed` (in this file's header)
- [x] Check off this leg in flight.md
- [x] Commit all changes together (code + artifacts)
