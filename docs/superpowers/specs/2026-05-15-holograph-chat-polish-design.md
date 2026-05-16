# Holograph Chat Polish — L7 · L8 · L9

**Status:** Draft · 2026-05-15
**Branch:** `worktree-feat+holograph-migration`
**Extends:** Mission 10 — Scientific Instrument (`2026-05-14-mission-10-instrument-design.md`)
**Scope:** Three follow-on flights that close out the chat surface review: topnav layout fix, command palette, user menu.

## Background

A walk-through of `localhost:8484/#chat` on 2026-05-15 surfaced nine defects across the chat, studio, and admin surfaces. Three are real product gaps (search is a dead control, the user-avatar button has no menu, onboarding cards persist after the first message); the rest are mechanical regressions in the M10 chrome rewrite — specifically, `topnav.js` shipped new class names (`.search-wrap`, `.search-input`, `.search-kbd`, `.spacer`) that the matching CSS was never updated to style, so the topnav cluster collapses against the search affordance and the right edge of the viewport.

The fixes are decomposed into three independently reviewable flights so the layout regression can ship immediately while the larger interactive surfaces (palette, menu) are designed and built without blocking the obvious wins.

## What This Is Not

- Not a redesign — Mission 10 visual vocabulary holds.
- Not an auth or multi-user story. The app is single-user, no-auth (see `SECURITY-MODEL.md`); the user menu carries only theme + a System link.
- Not a rewrite of the chat thread. Empty-state behavior is adjusted, not replaced.

---

## Flight L7 — Topnav Layout + Holograph Polish

Pure layout + theming fixes. No new features, no new behavior. Same hand-rolled module style as the rest of `static/js/`.

### L7.1 Topnav cluster layout

**Root cause.** `topnav.js` renders markup using class names introduced for M10 (`.search-wrap`, `.search-input`, `.search-kbd`, and a structural `<div class="spacer">`). `components.css` still carries the pre-M10 names (`.search`, `.kbd`, `.nav-right`) and never grew rules for the new ones. The spacer has no `flex: 1`, so the right cluster never gets pushed right; the search-wrap has no width, border, or padding, so the label, input, and `⌘K` hint collapse against each other and against the `tele-strip`. The first letter of the leading telemetry chip (`SESSIONS` / `AGENTS` / `PROVIDERS`) is clipped because `.tele-strip` has no `flex-shrink: 0` and the unstyled spacer's zero width lets the cluster overflow its container.

**Fix.**
- Add `.topnav-spacer { flex: 1; }` in `components.css`. Rename `<div class="spacer">` → `<div class="topnav-spacer">` in `topnav.js` so the rule is class-targeted, not name-collision with a generic utility.
- Add `.search-wrap`, `.search-input`, `.search-kbd`, `.visually-hidden` rules. These replace the orphan `.search`, `.kbd`, `.nav-right` rules, which are removed.
- Set `.tele-strip { flex-shrink: 0; }`.

Acceptance: at 1024 / 1280 / 1440 / 1920 viewport widths, the topnav renders as `[brand] [nav-segments] ────── [tele-strip] [search] [avatar]` with no element clipped and no overlap.

### L7.2 Sessions sidebar — `SESSIONS` heading clipped

Resolves with L7.1 (root cause is the same overflow that bleeds into the chat layout's left edge). Verify after L7.1 lands; if residual clipping remains, bump `.area`'s left padding in `chat.css` to clear the grid background's `1px` repeating frame.

### L7.3 Responsive composer at 1024px

`.composer` row shrinks the Send button + `0k ctx` meta off the page below ~1100px. Add `min-width: 0` to the textarea container and `flex-shrink: 0` to the trailing meta + Send group. Verify at 1024×768.

### L7.4 System-error message bubble

The `[ System ] Cannot start chat: Agent 'default' has no provider configured…` row currently spans the full message-column width with no max-width and no horizontal alignment to the agent-message column. Constrain to the same `max-width: 720px` the agent messages use; left-align to the agent rail. Style in `chat.css` under `.msg-row.system`.

### L7.5 Admin "+ New Provider" button — un-themed

The button on `#admin/providers` renders as a UA-default `<button>` (light gray on dark surface). Apply the existing `.btn-primary` token set so it matches the Mission 09/10 button language. Pure class swap in `providers-grid.js`; no new CSS.

### L7.6 New-session empty-state feedback

Clicking the `+` button in the sessions sidebar when no agent has a provider currently produces no visible feedback. Render an inline guidance row in the empty sessions list — "Add a provider and create an agent to start a session →" with a link to `#admin/providers`. No toast, no modal; matches the empty-state language already in `chat/welcome.js`.

### L7.7 Onboarding cards — keep prerequisite-driven, fix visual stacking

The chosen semantics are: cards stay visible until both a provider exists *and* an agent exists. `welcome.js` already implements this (`if (!hasProvider || !hasAgent) { render steps }`). The visual defect was the system-error bubble overflow (L7.4), not the welcome itself. Once L7.4 lands, the welcome + thread + error stack reads correctly. No changes to `welcome.js`.

### L7 testing

- Regenerate visual snapshot baselines for: `topnav-{chat,studio,admin}`, `chat-empty-{0p,1p}` , `admin-providers-empty`, `composer-1024`. Pattern matches commits `4176a6b`, `22bb380`, `7aba793`.
- Contrast test (existing harness) for the new `.search-wrap` / `.search-input` against dark and light theme tokens.
- Contract test: assert computed `flex-grow` of `.topnav-spacer` is `1` (cheap regression guard).

### L7 risk

Low. Pure visual; isolated to chrome and chat empty-state.

---

## Flight L8 — Command Palette (⌘K)

The topnav search affordance promises a command palette (`⌘K` hint, `aria-label="Open search"`) that doesn't exist. L8 wires it.

### L8.1 Module layout

Three new files under `static/js/components/`:

- `command-palette.js` (~200 lines) — DOM, focus trap, keyboard handling, render loop. Exposes `window.CommandPalette = { open(), close(), register(provider) }`.
- `command-catalog.js` (~100 lines) — Pure module. Builds the action catalog from data fetched via existing API helpers (no DOM). Caches dynamic data for 5s per open.
- `command-fuzzy.js` (~60 lines) — Pure scoring function (substring + prefix boost). Unit-testable in isolation.

Pattern matches `dialog.js`, `topnav.js`, and the rest of `static/js/` — hand-rolled IIFE, `window.Foo` export, no bundler.

### L8.2 Action catalog

**Static actions** (always present):
- Navigation: "Go to Chat", "Go to Studio", "Go to System", "Open Providers", "Open Agents", "Open Built-in Tools", "Open MCP Servers"
- Actions: "New session", "Toggle theme", "Reload app"

**Dynamic entries** (fetched lazily per open, cached 5s):
- `GET /api/agents` → "Switch to agent: <name>" (only if `hasProviders && hasAgents`)
- `GET /api/providers` → "Edit provider: <name>"
- `GET /api/sessions?limit=10` → "Open session: <title>"

API endpoints already exist; no backend work in L8.

### L8.3 Scoring

`command-fuzzy.js` exports `score(query, item)`:
- Exact prefix match on `label.toLowerCase()` → score += 100
- Substring match on `label` → score += 50
- Substring match on `section + keywords` → score += 20
- Tie-break by recency (sessions, agents) then alphabetical.

No external dependency. Top 8 results shown.

### L8.4 UI

- Overlay with `role="dialog" aria-modal="true"`. Centered card, 480px wide, anchored ~88px from viewport top.
- Sections rendered in order: `NAVIGATION`, `AGENTS`, `PROVIDERS`, `SESSIONS`, `ACTIONS`. Empty sections hidden.
- Input at top with `aria-controls="cp-results"`. Live result list below.
- Keyboard: Arrow up/down navigate, Enter invokes, Esc closes, Tab cycles within the dialog (focus trap).
- Empty-query state shows recent sessions + static navigation.
- Uses existing tokens (`--surface`, `--hairline`, `--accent`, `--shadow-2`). No new design surface.

### L8.5 Topnav integration

The current `<input type="search" class="search-input">` is replaced by a `<button type="button" class="search-input">` carrying the same class so L7.1's `.search-input` rule applies unchanged. Clicking it (or pressing `⌘K` anywhere in the app) calls `CommandPalette.open()`. This removes the dead input that currently focuses but does nothing.

Global keydown listener registered in `app.js`: `(e.metaKey || e.ctrlKey) && e.key === 'k'` → `CommandPalette.open()`; ignored when an editable element is focused unless `e.shiftKey` (escape hatch — same convention as VS Code, Linear).

### L8.6 Theme integration

The "Toggle theme" action calls `window.Theme.toggle()` (existing). Palette closes before the toggle so the snapshot transition is visible.

### L8.7 Testing

- Playwright browser test: press `⌘K`, type `prov`, press `Enter`, assert `window.location.hash === '#admin/providers'`.
- Playwright browser test: press `⌘K`, type `theme`, `Enter`, assert `<html data-theme>` flipped.
- Unit-style test for `command-fuzzy.score()` covering: prefix beats substring, case-insensitive, missing fields don't throw.
- Visual snapshot of the open palette in both themes.

### L8 risk

Medium. New component with focus management. Mitigated by following `dialog.js`'s focus-trap pattern, which is already shipping in this codebase.

---

## Flight L9 — User (JD) Menu

The avatar button in the topnav has no menu. L9 wires the two settings that exist on this single-user, no-auth app.

### L9.1 Module

`static/js/components/user-menu.js` (~120 lines). Same hand-rolled pattern. Exposes `window.UserMenu = { toggle(anchorEl), close() }`.

### L9.2 Menu items

- **Theme** — inline three-button row (Light · Dark · System). Calls `window.Theme.set(mode)`. The active mode shows the left-side accent bar from `.navseg.active`.
- **System → General** — `<a href="#admin/general">` (existing route).
- Divider.
- **Holograph v0.2.0** — read-only version footer. `the_one/__init__.py` already exports `__version__`. Surface it to the UI via a `<meta name="app-version" content="…">` tag rendered into `index.html` (the FastAPI app already serves `index.html` through `interfaces/web/app.py` — add a small template variable or post-process step there).

No sign-out. No account management. No profile.

### L9.3 UI

- Popover, ~220px wide, anchored to the bottom-right of `.avatar`.
- `role="menu"`, items are `role="menuitem"`. Keyboard nav: Arrow up/down, Home/End, Enter invokes, Esc closes.
- Click-outside closes (same outside-click pattern as `dialog.js`).
- Tokens only — `--surface`, `--hairline`, `--shadow-2`, `--accent`. No new visual primitives.

### L9.4 Topnav integration

`topnav.js` extends the existing click handler:

```js
var av = ev.target.closest('.avatar');
if (av) { window.UserMenu.toggle(av); return; }
```

No structural changes to the topnav render path.

### L9.5 Testing

- Playwright browser test: click `.avatar`, assert menu opens, click "Theme · Light", assert `<html data-theme="light">` and reload-persists.
- Snapshot in both themes.
- Contract test that the menu carries exactly the three documented items (regression guard against scope creep).

### L9 risk

Low. Smaller than L8; reuses palette-style scaffolding L8 introduces (focus trap, outside-click handler can be shared as `static/js/utils/popover.js` if L8 extracts it — optional, decide during L8 execution).

---

## Sequencing

L7 → L8 → L9. L7 is fully independent. L8 depends on L7 (replaces the search input with a button — the new `.search-input-trigger` styling rides on the L7 search-wrap rules). L9 depends on L8 only if popover scaffolding is shared; otherwise independent.

## Out of scope

- Recent-query history / palette analytics.
- Multi-user, auth, profile management — explicitly disallowed by the security model.
- Mobile / narrow viewport (<1024px) — Holograph is desktop-only per Mission 10.
- Reworking the chat empty state semantics beyond L7.4. The cards stay prerequisite-driven as designed.
