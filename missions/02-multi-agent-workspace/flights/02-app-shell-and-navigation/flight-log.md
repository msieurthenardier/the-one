# Flight Log: App Shell & Navigation

**Flight**: [App Shell & Navigation](flight.md)

> **Note:** This flight log was created retroactively. The flight was executed as a continuous implementation session without formal leg tracking.

## Summary

App shell architecture delivered in a single session. The monolithic chat page was decomposed into a pluggable area system with hash routing, consistent layout, and full chat feature parity. Studio and Admin areas stubbed for future flights. Six new/rewritten files, zero regressions in chat functionality.

---

## Leg Progress

### CSS Extraction
**Status**: completed

#### Changes Made
- Created `the_one/interfaces/web/static/styles.css` — ~112 lines
- CSS custom properties design system (--bg, --fg, --accent, --surface, --border, --tool, --sidebar-w, --nav-w)
- Dark theme, flexbox layout, responsive panels

### App Shell
**Status**: completed

#### Changes Made
- Created `the_one/interfaces/web/static/js/app.js` — ~91 lines
- `App` module (IIFE): `registerArea()`, `renderNav()`, `switchTo()`, `getHashArea()`
- Hash-based routing with `hashchange` listener
- Lazy panel initialization with `initialized` map

### Chat Migration
**Status**: completed

#### Changes Made
- Created `the_one/interfaces/web/static/js/areas/chat.js` — ~253 lines
- Full chat UI as area plugin: WebSocket management, session list with source grouping, message rendering by role
- Telemetry display: token counters (in/out/ctx), context bar with warn/critical thresholds
- Session CRUD: new, join, delete, auto-join on startup

### Studio Stub
**Status**: completed

#### Changes Made
- Created `the_one/interfaces/web/static/js/areas/studio.js` — ~19 lines
- Registered as area with order: 2, icon: wrench, label: Studio

### Admin Stub
**Status**: completed

#### Changes Made
- Created `the_one/interfaces/web/static/js/areas/admin.js` — ~19 lines
- Registered as area with order: 3, icon: gear, label: Admin

### Index Rewrite
**Status**: completed

#### Changes Made
- Rewrote `the_one/interfaces/web/templates/index.html` — ~21 lines (down from ~200+)
- Minimal scaffold: three container divs, CSS link, sequential script tags

---

## Decisions

### Hash routing over History API
**Context**: Need client-side routing for area switching without server changes
**Decision**: Use `location.hash` (`#chat`, `#studio`, `#admin`) with `hashchange` listener
**Impact**: Simpler implementation; no server-side route handling needed; default area is `chat`

### WebSocket stays open across area switches
**Context**: Chat area uses WebSocket for real-time messaging; could close on deactivate
**Decision**: Keep WebSocket alive; deactivate callback is a no-op
**Impact**: No reconnection delay when returning to Chat; slight resource usage when inactive

### Session grouping by source
**Context**: Sessions can originate from web UI, API calls, or external integrations
**Decision**: Group session list by `source` field with `web` group first, others alphabetically
**Impact**: Clear visual separation; users can distinguish UI-created sessions from API-created ones

---

## Deviations

### Full CSS rewrite instead of incremental extraction
**Planned**: Extract existing inline styles to external file
**Actual**: Rewrote CSS from scratch with custom properties design system
**Reason**: Existing inline styles were tightly coupled to old single-page layout; cleaner to design the CSS around the new three-panel architecture

### Telemetry display added to chat area
**Planned**: Not in original flight description (which focused on shell architecture)
**Actual**: Added token counters and context bar with visual thresholds
**Reason**: Telemetry data was already available from WebSocket `usage` events; displaying it required minimal additional code and provides immediate value

---

## Anomalies

_(none — implementation proceeded without blocking issues)_
