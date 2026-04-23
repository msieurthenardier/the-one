# Flight: App Shell & Navigation

**Status**: landed
**Mission**: [Multi-Agent Workspace](../../mission.md)

> **Note:** This flight spec was created retroactively after implementation. It captures what was done, not what was planned upfront. No formal leg specs were created prior to execution.

## Contributing to Criteria

- [x] The web interface is organized into switchable functional areas (Studio, Chat, Administration) through an app-shell architecture that can accommodate additional areas without structural changes
- [x] Each functional area has a consistent layout (sidebar + main panel) with area-specific content, and a shared navigation mechanism for switching between areas
- [x] Users can select which agent to converse with (session management in Chat area — agent picker deferred to Flight 4)

---

## Pre-Flight

### Objective

Build the extensible app-shell architecture: area registry, hash-based routing, sidebar/panel layout, navigation rail. Migrate the existing chat UI into the Chat area with full feature parity (WebSocket, sessions, telemetry). Stub Studio and Admin areas. Establish the vanilla JS frontend patterns all future areas will use.

### Design Decisions

**Hash-based routing**: `#chat`, `#studio`, `#admin` drive navigation
- Rationale: No server-side route handling needed; simpler than History API
- Trade-off: URLs include `#` prefix; no server-side rendering possible

**Area registration pattern**: Each area registers a descriptor with init/activate/deactivate callbacks
- Rationale: Pure plugin model — new areas added by creating a JS file and registering, no framework changes
- Trade-off: No dependency management between areas; order determined by numeric `order` property

**Lazy panel initialization**: Sidebar and content panels created on first activation, not on page load
- Rationale: Memory efficient for multi-area apps; fast initial load
- Trade-off: First navigation to an area has slight delay for DOM creation

**CSS-only visibility toggle**: Areas shown/hidden via `.active` class, not DOM insertion/removal
- Rationale: Preserves area state (scroll position, form inputs) across navigation
- Trade-off: All activated area DOMs remain in memory

**WebSocket persistence across areas**: Chat WebSocket stays open when navigating away
- Rationale: Avoids reconnection delay and potential message loss on navigation
- Trade-off: Resource usage when Chat area is inactive

**Closure-based state isolation**: Each area manages its own state within its init function closure
- Rationale: No global state collisions; clean encapsulation without class syntax
- Trade-off: State not accessible from other areas (by design)

### Prerequisites

- [x] Flight 01 complete (REST API, session persistence)
- [x] Existing chat UI functional (WebSocket endpoint, agent interaction)

---

## In-Flight

### Technical Approach

Extract CSS from inline styles, build app shell framework (app.js), migrate chat functionality into area plugin (chat.js), create stub areas (studio.js, admin.js), rewrite index.html as minimal scaffold.

### Legs

Work was executed as a continuous implementation session. Logical groupings:

- [x] `css-extraction` — Extract all styling from inline `<style>` to `styles.css` with CSS custom properties design system
- [x] `app-shell` — Area registry, hash routing, panel management, navigation rail rendering
- [x] `chat-migration` — Full chat UI migrated to area plugin: WebSocket, session list with source grouping, message rendering, telemetry display with context bar
- [x] `studio-stub` — Placeholder area with "Coming in Flight 03" message
- [x] `admin-stub` — Placeholder area with "Coming in Flight 05" message
- [x] `index-rewrite` — Minimal HTML scaffold: nav, sidebar, content containers + script tags

---

## Post-Flight

### Completion Checklist

- [x] All logical legs completed
- [x] Chat functionality preserved (WebSocket, sessions, telemetry)
- [x] Three areas navigable via hash routing
- [x] Consistent layout across all areas
- [ ] Code not yet committed (part of larger working tree)

### Verification

- Navigation between all three areas via nav rail and URL hash
- Chat WebSocket connects, sessions list and switch, messages send/receive
- Telemetry display with token counters and context bar
- Session grouping by source (web, API, external)
- Studio and Admin stubs render with placeholder content
