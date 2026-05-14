# Mission 10 — Scientific Instrument Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Apply the Scientific Instrument visual lens across the entire web UI — empty states, topnav, area headers, working states, motion layer, and light theme adaptation — closing the "no committed aesthetic direction" finding from the L8 rating pass.

**Architecture:** Six independently-shippable legs (L1 foundation → L6 motion + WS telemetry). Each leg ships a coherent visual state; partial completion looks less complete, never broken. New CSS primitives land first; topnav + telemetry-store next; area headers and empty states build on that foundation; working-state polish and motion close it out. Backend additions: a single WS ping/pong handler + a `_presets.py` agent factory.

**Tech Stack:** Vanilla JS (no framework), CSS custom properties keyed by `[data-theme]`, Python/FastAPI backend, Playwright for visual snapshots, pytest for everything else. All new modules follow project conventions in `the_one/agents.md` (canonical-import + convenience-re-export, structural-Protocol-satisfaction).

**Reference:** Spec at `docs/superpowers/specs/2026-05-14-mission-10-instrument-design.md`.

---

## Phase L1 — Foundation

Goal: token additions + new primitive CSS components + grid canvas + corner ticks land. No JS routing changes, no markup changes (other than the one-time `.canvas-frame` mount). Visual diff: faint grid + corner ticks become visible. Self-contained, ships green.

### Task 1.1: Add motion + spacing + status tokens

**Files:**
- Modify: `the_one/interfaces/web/static/css/tokens.css`

- [ ] **Step 1: Read current tokens.css**

Run: `cat the_one/interfaces/web/static/css/tokens.css | head -120`

Confirm where the `:root` block ends and where `[data-theme="dark"]` / `[data-theme="light"]` overrides live. The additions below slot into `:root` (theme-agnostic) and per-theme blocks.

- [ ] **Step 2: Append theme-agnostic tokens to `:root`**

Add these lines to the `:root { … }` block (just before the closing brace):

```css
  /* M10 — spacing scale (formalized; previously inlined as px literals) */
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 20px;
  --space-6: 24px;
  --space-7: 32px;
  --space-8: 48px;

  /* M10 — motion */
  --motion-fast: 120ms;
  --motion-base: 180ms;
  --motion-slow: 240ms;
  --motion-pulse-cycle: 1400ms;

  /* M10 — instrument primitives */
  --font-mono-eyebrow-size: 10px;
  --font-mono-eyebrow-tracking: 0.15em;
  --corner-tick-size: 8px;
  --corner-tick-inset: 12px;
  --canvas-grid-step: 20px;
```

- [ ] **Step 3: Add per-theme status + grid + accent-soft tokens**

In the `[data-theme="dark"] { … }` block, add:

```css
  --surface-grid: rgba(255, 255, 255, 0.025);
  --accent-soft: rgba(167, 139, 250, 0.10);
  --good: #6ee7b7;
  --bad: #f87171;
  --warn: #fbbf24;
  --brand-mark-bg: linear-gradient(135deg, var(--accent), #7c5cff);
```

In the `[data-theme="light"] { … }` block, add:

```css
  --surface-grid: rgba(0, 0, 0, 0.025);
  --accent-soft: rgba(51, 88, 192, 0.10);
  --good: #0d9166;
  --bad: #c83232;
  --warn: #b87900;
  --brand-mark-bg: var(--accent);
```

- [ ] **Step 4: Verify tokens load in both themes**

Run: `make rebuild && curl -s http://localhost:8484/static/css/tokens.css | grep -E "surface-grid|accent-soft|space-7|motion-base" | head -8`

Expected: at least 4 matching lines visible. No CSS lint errors.

- [ ] **Step 5: Commit**

```bash
git add the_one/interfaces/web/static/css/tokens.css
git commit -m "L1.1: add M10 instrument tokens (spacing, motion, status, surface-grid)"
```

---

### Task 1.2: Audit a11y contrast for new color pairs

**Files:**
- Modify: `tests/test_design_tokens_a11y.py`

- [ ] **Step 1: Read the existing test file structure**

Run: `cat tests/test_design_tokens_a11y.py | head -80`

Confirm the helper `contrast_ratio(fg_hex, bg_hex)` exists and how existing pairs are asserted.

- [ ] **Step 2: Add three new test functions**

Append to `tests/test_design_tokens_a11y.py`:

```python
def test_m10_accent_on_bg_passes_aa_both_themes():
    """M10 — accent color must read on the canvas in both themes."""
    # Dark
    assert contrast_ratio("#a78bfa", "#0a0c10") >= 4.5
    # Light
    assert contrast_ratio("#3358c0", "#f8f8f6") >= 4.5


def test_m10_good_on_bg_passes_aa_both_themes():
    """M10 — status `good` must be readable as text/label color."""
    assert contrast_ratio("#6ee7b7", "#0a0c10") >= 4.5
    assert contrast_ratio("#0d9166", "#f8f8f6") >= 4.5


def test_m10_bad_on_bg_passes_aa_both_themes():
    """M10 — status `bad` must be readable as text/label color."""
    assert contrast_ratio("#f87171", "#0a0c10") >= 4.5
    assert contrast_ratio("#c83232", "#f8f8f6") >= 4.5
```

- [ ] **Step 3: Run the three new tests — must pass**

Run: `docker exec the-one pytest tests/test_design_tokens_a11y.py -v -k "m10" --tb=short`

Expected: 3 passed. If `good` light or `bad` dark fails, adjust the hex in `tokens.css` until it passes, then re-run. (Both values above were chosen to pass; verify here.)

- [ ] **Step 4: Commit**

```bash
git add tests/test_design_tokens_a11y.py
git commit -m "L1.2: audit M10 status color pairs for WCAG AA contrast"
```

---

### Task 1.3: Add primitive component CSS

**Files:**
- Modify: `the_one/interfaces/web/static/css/components.css`

- [ ] **Step 1: Locate the `@layer components` block**

Run: `grep -n "^@layer components" the_one/interfaces/web/static/css/components.css`

Confirm the layer scope so the new primitives slot into the correct cascade band.

- [ ] **Step 2: Append the M10 primitives section**

Add to `components.css` inside `@layer components { … }` (before the closing brace):

```css
  /* ============================================================
     M10 instrument primitives — see specs/2026-05-14-mission-10-instrument-design.md §1
     ============================================================ */

  /* Body-level grid canvas. Mounted once at app init via app.js. */
  #main-content {
    background-image:
      linear-gradient(var(--surface-grid) 1px, transparent 1px),
      linear-gradient(90deg, var(--surface-grid) 1px, transparent 1px);
    background-size: var(--canvas-grid-step) var(--canvas-grid-step);
  }

  /* Corner ticks — applied to #main-content via ::before/::after on a once-injected frame. */
  .canvas-frame {
    position: fixed;
    inset: 56px 0 0 0; /* below topnav */
    pointer-events: none;
    z-index: 0;
  }
  .canvas-frame::before,
  .canvas-frame::after {
    content: "";
    position: absolute;
    width: var(--corner-tick-size);
    height: var(--corner-tick-size);
  }
  .canvas-frame::before {
    top: var(--corner-tick-inset);
    left: var(--corner-tick-inset);
    border-top: 1px solid var(--accent);
    border-left: 1px solid var(--accent);
  }
  .canvas-frame::after {
    bottom: var(--corner-tick-inset);
    right: var(--corner-tick-inset);
    border-bottom: 1px solid var(--accent);
    border-right: 1px solid var(--accent);
  }
  .canvas-frame .tr,
  .canvas-frame .bl {
    position: absolute;
    width: var(--corner-tick-size);
    height: var(--corner-tick-size);
  }
  .canvas-frame .tr {
    top: var(--corner-tick-inset);
    right: var(--corner-tick-inset);
    border-top: 1px solid var(--accent);
    border-right: 1px solid var(--accent);
  }
  .canvas-frame .bl {
    bottom: var(--corner-tick-inset);
    left: var(--corner-tick-inset);
    border-bottom: 1px solid var(--accent);
    border-left: 1px solid var(--accent);
  }

  /* Section eyebrow — small mono label above titles with a leading rule */
  .eyebrow {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    font-family: 'JetBrains Mono', monospace;
    font-size: var(--font-mono-eyebrow-size);
    letter-spacing: var(--font-mono-eyebrow-tracking);
    color: var(--accent);
    text-transform: uppercase;
    margin-bottom: var(--space-2);
  }
  .eyebrow::before {
    content: "";
    width: 18px;
    height: 1px;
    background: var(--accent);
  }

  /* Coord pill — route readout */
  .pill-coord {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    padding: 5px 10px;
    background: var(--surface-2);
    border: 1px solid var(--hairline-strong);
    border-radius: 4px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    letter-spacing: 0.08em;
    color: var(--fg-mute);
  }
  .pill-coord .dot {
    width: 4px;
    height: 4px;
    border-radius: 50%;
    background: var(--accent);
  }
  .pill-coord .sep {
    color: var(--fg-faint);
  }

  /* Status dot — 4 states */
  .stat-dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    display: inline-block;
    flex-shrink: 0;
  }
  .stat-dot.idle { background: var(--fg-faint); box-shadow: 0 0 0 2px rgba(154, 160, 170, 0.12); }
  .stat-dot.work { background: var(--accent); box-shadow: 0 0 0 2px var(--accent-soft); animation: m10-pulse var(--motion-pulse-cycle) ease-in-out infinite; }
  .stat-dot.ok   { background: var(--good); box-shadow: 0 0 0 2px rgba(110, 231, 183, 0.18); }
  .stat-dot.err  { background: var(--bad); box-shadow: 0 0 0 2px rgba(248, 113, 113, 0.22); }
  @keyframes m10-pulse { 50% { opacity: 0.55; } }

  /* Bracket framing — focal element ornament */
  .brack {
    position: relative;
    padding: var(--space-6) var(--space-7);
  }
  .brack::before,
  .brack::after {
    content: "";
    position: absolute;
    width: 14px;
    height: 14px;
    border: 1px solid var(--accent);
  }
  .brack::before { top: 0; left: 0; border-right: 0; border-bottom: 0; }
  .brack::after  { bottom: 0; right: 0; border-left: 0; border-top: 0; }

  /* Accent rule — gradient separator */
  .accent-rule {
    position: relative;
    height: 1px;
    background: linear-gradient(90deg, var(--accent), transparent);
    margin: var(--space-5) 0;
  }
  .accent-rule[data-meta]::after {
    content: attr(data-meta);
    position: absolute;
    right: 0;
    top: -7px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 9px;
    letter-spacing: 0.12em;
    color: var(--fg-faint);
    text-transform: uppercase;
    background: var(--bg);
    padding-left: var(--space-2);
  }

  /* Mono CTA */
  .btn-mono {
    padding: 9px 16px;
    background: var(--accent-soft);
    color: var(--accent);
    border: 1px solid var(--accent);
    border-radius: 6px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    letter-spacing: 0.04em;
    cursor: pointer;
    appearance: none;
    -webkit-appearance: none;
    transition: background var(--motion-fast) ease;
  }
  .btn-mono:hover { background: color-mix(in srgb, var(--accent-soft), var(--accent) 8%); }
```

- [ ] **Step 3: Add a token-definition test for the new vars**

Run: `docker exec the-one pytest tests/test_token_definitions.py -v --tb=short`

The existing test scans all `var(--x)` references in component CSS and asserts each is defined. The new primitives reference `--space-*`, `--motion-*`, `--accent-soft`, `--surface-grid`, `--brand-mark-bg`, `--corner-tick-size`, `--corner-tick-inset`, `--canvas-grid-step`, `--font-mono-eyebrow-size`, `--font-mono-eyebrow-tracking`, `--good`, `--bad`. All were added in Task 1.1.

Expected: PASS. If any var is reported undefined, return to Task 1.1 and add it.

- [ ] **Step 4: Verify CSS lints clean**

Run: `make rebuild 2>&1 | grep -iE "error|fail" | head -5 || echo "clean"`

Expected: `clean` (no error lines in the docker build output).

- [ ] **Step 5: Commit**

```bash
git add the_one/interfaces/web/static/css/components.css
git commit -m "L1.3: add M10 instrument primitives (eyebrow, coord, stat, brack, rule, btn-mono, canvas-frame)"
```

---

### Task 1.4: Mount `.canvas-frame` at app init

**Files:**
- Modify: `the_one/interfaces/web/static/js/app.js`

- [ ] **Step 1: Locate the app-init function**

Run: `grep -n "function init\|App.init\|topnav.innerHTML" the_one/interfaces/web/static/js/app.js | head -10`

Find the function that runs once at boot (where `topnav.innerHTML = …` lives, around line 25-50 per the L8.7 patch).

- [ ] **Step 2: Inject the canvas-frame element once**

Add right after the topnav is set, BEFORE any area mounts. Find this block in `app.js`:

```javascript
    topnav.innerHTML =
      '<div class="brand">' +
        '<div class="brand-mark">H</div>' +
        '<div class="brand-name">Holograph</div>' +
      …
```

Add this immediately after the topnav block (and after any nav-event-binding lines):

```javascript
    // M10 — body-level instrument frame (corner ticks); the grid canvas
    // itself lives on #main-content via components.css.
    if (!document.querySelector('.canvas-frame')) {
      var frame = document.createElement('div');
      frame.className = 'canvas-frame';
      frame.setAttribute('aria-hidden', 'true');
      // Two extra spans for top-right + bottom-left ticks (the ::before/::after
      // pseudos cover top-left + bottom-right).
      frame.innerHTML = '<span class="tr"></span><span class="bl"></span>';
      document.body.appendChild(frame);
    }
```

- [ ] **Step 3: Verify the frame renders**

Run: `make rebuild` (waits for the up + verify-serving block to print).

Then in the browser at `http://localhost:8484/`, open devtools and run:

```javascript
document.querySelectorAll('.canvas-frame').length
document.querySelectorAll('.canvas-frame .tr').length
```

Both should print `1`.

- [ ] **Step 4: Visual smoke check**

Open `http://localhost:8484/` in both light and dark themes. Confirm faint grid lines are visible across all three areas (Chat, Studio, Admin) and that four corner ticks anchor each viewport corner. The grid must be subtle — not attention-grabbing.

- [ ] **Step 5: Commit**

```bash
git add the_one/interfaces/web/static/js/app.js
git commit -m "L1.4: mount .canvas-frame at app boot — grid + corner ticks visible"
```

---

### Task 1.5: Regenerate visual snapshot baselines

**Files:**
- Modify: `tests/browser/__snapshots__/*.png` (auto-regenerated)

- [ ] **Step 1: Identify snapshot tests affected by L1**

Run: `grep -l "snapshot" tests/browser/test_visual_snapshots.py 2>&1 | head -3`

The grid + corner ticks change every visible screen; every snapshot baseline needs regeneration. There are 12 baselines per `the_one/agents.md` (3 areas × 2 states × 2 themes).

- [ ] **Step 2: Regenerate baselines**

Run: `docker exec the-one pytest -m browser tests/browser/test_visual_snapshots.py --snapshot-update`

Expected: 12 snapshots updated, all green. If the dev container lacks Playwright binaries (per the L8.7 verification path), regenerate from a host context where Playwright is installed, OR defer to a CI run that has the binaries — note this in the commit message.

- [ ] **Step 3: Commit baselines**

```bash
git add tests/browser/__snapshots__/
git commit -m "L1.5: regenerate visual snapshot baselines for M10 foundation"
```

---

## Phase L2 — Topnav

Goal: replace topnav with V2 design (mono coord segments + per-area telemetry chips). Extract render to a new `topnav.js` module. Add `telemetry-store.js` to back live counts. WS RTT chip lands as `—` until L6 wires it.

### Task 2.1: Create telemetry-store.js (no consumers yet)

**Files:**
- Create: `the_one/interfaces/web/static/js/utils/telemetry-store.js`
- Test: `tests/browser/test_telemetry_store.py`

- [ ] **Step 1: Write the failing test**

Create `tests/browser/test_telemetry_store.py`:

```python
"""Unit tests for the in-memory telemetry store.

The store is a plain ES-module-on-window observable; we exercise it
inside a Playwright page context to avoid Node.js setup.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page


@pytest.mark.browser
def test_telemetry_store_initial_state_is_em_dash(app_clean: str, page: Page) -> None:
    page.goto(app_clean)
    state = page.evaluate("window.TelemetryStore.get()")
    assert state["sessions"] == "—"
    assert state["agents"] == "—"
    assert state["providers"] == "—"
    assert state["tools"] == "—"
    assert state["ctx"] == "—"
    assert state["ws_rtt_ms"] == "—"
    assert state["ws_state"] == "down"


@pytest.mark.browser
def test_telemetry_store_set_emits_change(app_clean: str, page: Page) -> None:
    page.goto(app_clean)
    result = page.evaluate(
        """async () => {
          const calls = [];
          window.TelemetryStore.subscribe((s) => calls.push({ ...s }));
          window.TelemetryStore.set({ sessions: 3, agents: 1 });
          return calls;
        }"""
    )
    assert len(result) >= 1
    last = result[-1]
    assert last["sessions"] == 3
    assert last["agents"] == 1


@pytest.mark.browser
def test_telemetry_store_unsubscribe_stops_emissions(app_clean: str, page: Page) -> None:
    page.goto(app_clean)
    result = page.evaluate(
        """async () => {
          const calls = [];
          const off = window.TelemetryStore.subscribe((s) => calls.push({ ...s }));
          window.TelemetryStore.set({ sessions: 1 });
          off();
          window.TelemetryStore.set({ sessions: 99 });
          return calls.length;
        }"""
    )
    assert result == 1
```

- [ ] **Step 2: Run the failing test**

Run: `docker exec the-one pytest -m browser tests/browser/test_telemetry_store.py -v --tb=short`

Expected: 3 FAIL (`window.TelemetryStore` is undefined).

- [ ] **Step 3: Create the store module**

Create `the_one/interfaces/web/static/js/utils/telemetry-store.js`:

```javascript
// M10 — telemetry store. Single source of live counts for the topnav
// chip strip, area headers, and empty-state stat rows. Plain
// observable — no framework. Initial values are em-dash placeholders
// (NOT zero — see spec §16 risk).
(function () {
  'use strict';

  var state = {
    sessions: '—',
    agents: '—',
    providers: '—',
    tools: '—',
    ctx: '—',
    ws_rtt_ms: '—',
    ws_state: 'down'  // 'down' | 'stale' | 'ok'
  };
  var subs = [];

  function get() {
    // Defensive copy to prevent mutation by consumers.
    return Object.assign({}, state);
  }

  function set(patch) {
    Object.assign(state, patch);
    for (var i = 0; i < subs.length; i++) {
      try {
        subs[i](get());
      } catch (e) {
        console.error('[TelemetryStore] subscriber threw:', e);
      }
    }
  }

  function subscribe(fn) {
    subs.push(fn);
    // Emit current state immediately so subscribers don't see undefined.
    fn(get());
    return function unsubscribe() {
      var idx = subs.indexOf(fn);
      if (idx >= 0) subs.splice(idx, 1);
    };
  }

  window.TelemetryStore = { get: get, set: set, subscribe: subscribe };
})();
```

- [ ] **Step 4: Wire the module into index.html load order**

Modify `the_one/interfaces/web/static/index.html` — add this `<script>` line BEFORE the other JS modules (it must load before `app.js`):

```html
<script src="/static/js/utils/telemetry-store.js"></script>
```

Place it right after `<script src="/static/js/icons.js"></script>` for grouping with utilities.

- [ ] **Step 5: Run tests to verify pass**

Run: `make rebuild && docker exec the-one pytest -m browser tests/browser/test_telemetry_store.py -v --tb=short`

Expected: 3 PASS.

- [ ] **Step 6: Commit**

```bash
git add the_one/interfaces/web/static/js/utils/telemetry-store.js \
        the_one/interfaces/web/static/index.html \
        tests/browser/test_telemetry_store.py
git commit -m "L2.1: add telemetry-store.js observable for live UI counts"
```

---

### Task 2.2: Extract topnav render to topnav.js (no behavior change)

**Files:**
- Create: `the_one/interfaces/web/static/js/topnav.js`
- Modify: `the_one/interfaces/web/static/js/app.js`
- Modify: `the_one/interfaces/web/static/index.html`

- [ ] **Step 1: Read the existing topnav render in app.js**

Run: `grep -n "topnav.innerHTML\|navlink" the_one/interfaces/web/static/js/app.js | head -15`

Identify the block that builds `<div class="brand">…</div><div class="navlinks">…</div>…` (around line 25-60 per L8.7).

- [ ] **Step 2: Create topnav.js with the lift-and-shift render**

Create `the_one/interfaces/web/static/js/topnav.js`:

```javascript
// M10 — topnav render. Extracted from app.js. Owns brand + nav + search
// + avatar markup AND the per-area telemetry chip strip (chip selection
// per spec §2). Subscribes to TelemetryStore for live counts.
(function () {
  'use strict';

  // Chip configurations per area. Keys are the chip render slots; values
  // are arrays of telemetry-store keys to render. Order matters.
  var AREA_CHIPS = {
    chat:   ['sessions', 'ctx', 'ws'],
    studio: ['agents', 'providers', 'ws'],
    admin:  ['providers', 'tools', 'ws']
  };

  var CHIP_LABELS = {
    sessions: 'SESSIONS',
    agents: 'AGENTS',
    providers: 'PROVIDERS',
    tools: 'TOOLS',
    ctx: 'CTX',
    ws: 'WS'
  };

  function renderChip(key, store) {
    if (key === 'ws') {
      var dotClass = store.ws_state === 'ok' ? 'ok' : (store.ws_state === 'stale' ? 'err' : 'err');
      var rtt = store.ws_rtt_ms === '—' ? '—' : (store.ws_rtt_ms + 'ms');
      return (
        '<span class="tele-chip"><span class="stat-dot ' + dotClass + '"></span>' +
        'WS<strong>' + rtt + '</strong></span>'
      );
    }
    return '<span class="tele-chip">' + CHIP_LABELS[key] + '<strong>' + store[key] + '</strong></span>';
  }

  function renderTopnav(activeArea) {
    var topnav = document.getElementById('app-topnav');
    if (!topnav) return;

    var store = window.TelemetryStore.get();
    var chipKeys = AREA_CHIPS[activeArea] || AREA_CHIPS.chat;
    var chipsHtml = chipKeys.map(function (k) { return renderChip(k, store); }).join('');

    var areas = [
      { id: 'chat',   idx: '01', label: 'CHAT' },
      { id: 'studio', idx: '02', label: 'STUDIO' },
      { id: 'admin',  idx: '03', label: 'SYSTEM' }
    ];
    var navHtml = areas.map(function (a) {
      var cls = 'navseg' + (a.id === activeArea ? ' active' : '');
      var ariaCur = a.id === activeArea ? ' aria-current="page"' : '';
      return (
        '<button class="' + cls + '" data-area="' + a.id + '" aria-label="Go to ' + a.label + '"' + ariaCur + '>' +
          '<span class="idx">' + a.idx + '</span>' + a.label +
        '</button>'
      );
    }).join('');

    topnav.innerHTML =
      '<div class="brand">' +
        '<div class="brand-mark">H</div>' +
        '<div class="brand-name">Holograph</div>' +
      '</div>' +
      '<div class="nav-segments">' + navHtml + '</div>' +
      '<div class="spacer"></div>' +
      '<div class="tele-strip">' + chipsHtml + '</div>' +
      '<div class="search-wrap"><label for="topnav-search" class="visually-hidden">Search</label>' +
        '<input type="search" id="topnav-search" class="search-input" placeholder="Search" aria-label="Open search"/>' +
        '<span class="search-kbd">⌘K</span>' +
      '</div>' +
      '<button class="avatar" aria-label="User">JD</button>';
  }

  function bindEvents(onAreaSwitch) {
    var topnav = document.getElementById('app-topnav');
    topnav.addEventListener('click', function (ev) {
      var seg = ev.target.closest('.navseg');
      if (seg && seg.dataset.area) {
        onAreaSwitch(seg.dataset.area);
      }
    });
  }

  function subscribeForRerender() {
    window.TelemetryStore.subscribe(function () {
      // Re-render only the chip strip, not the whole topnav.
      var topnav = document.getElementById('app-topnav');
      if (!topnav) return;
      var strip = topnav.querySelector('.tele-strip');
      if (!strip) return;
      var active = topnav.querySelector('.navseg.active');
      var areaId = active ? active.dataset.area : 'chat';
      var chipKeys = AREA_CHIPS[areaId] || AREA_CHIPS.chat;
      var store = window.TelemetryStore.get();
      strip.innerHTML = chipKeys.map(function (k) { return renderChip(k, store); }).join('');
    });
  }

  window.Topnav = {
    render: renderTopnav,
    bindEvents: bindEvents,
    subscribeForRerender: subscribeForRerender
  };
})();
```

- [ ] **Step 3: Replace the topnav block in app.js**

In `app.js`, REPLACE the existing `topnav.innerHTML = '<div class="brand">…'` block (the lift-and-shift target identified in Step 1) with:

```javascript
    // M10 — topnav rendered by topnav.js (extracted in L2.2).
    window.Topnav.render('chat');
    window.Topnav.bindEvents(function (areaId) {
      window.location.hash = '#' + areaId;
    });
    window.Topnav.subscribeForRerender();
```

Find the existing `performCrossAreaSwitch` function and after it sets the active panel, add a call to re-render the topnav so the active `.navseg` updates:

```javascript
      // Re-render topnav so the active nav segment + per-area chips update.
      if (window.Topnav) window.Topnav.render(areaId);
```

- [ ] **Step 4: Wire topnav.js into index.html**

Modify `the_one/interfaces/web/static/index.html` — add `<script src="/static/js/topnav.js"></script>` right after the `telemetry-store.js` line from Task 2.1.

- [ ] **Step 5: Smoke verify**

Run: `make rebuild`

In the browser at `http://localhost:8484/`:
- Topnav renders with the V2 nav segments (`01 CHAT`, `02 STUDIO`, `03 SYSTEM`)
- Clicking nav segments switches areas (existing behavior preserved)
- Topnav active state updates when switching areas
- Chip strip shows three em-dash placeholders (no real data wired yet — that's Task 2.3)

- [ ] **Step 6: Commit**

```bash
git add the_one/interfaces/web/static/js/topnav.js \
        the_one/interfaces/web/static/js/app.js \
        the_one/interfaces/web/static/index.html
git commit -m "L2.2: extract topnav render to topnav.js (lift-and-shift, no behavior change)"
```

---

### Task 2.3: Add V2 topnav CSS

**Files:**
- Modify: `the_one/interfaces/web/static/css/components.css`

- [ ] **Step 1: Locate the existing `.topnav` and `.navlink` styles**

Run: `grep -n "^\\.topnav\\|^\\.navlink\\|^  \\.navlink" the_one/interfaces/web/static/css/components.css | head -10`

The L8.7 `.navlink` block lives around line 90 (with `appearance: none` already applied). M10 keeps the topnav frame but replaces `.navlink` semantics with `.navseg`.

- [ ] **Step 2: Replace the navlink block with navseg styles**

REMOVE the existing `.navlink { … }` block and any `.navlink.active` / `.navlink:hover` rules from `components.css`.

ADD this in their place (inside `@layer components`):

```css
  /* M10 — nav segments (replaces .navlink). See spec §2. */
  .nav-segments {
    display: flex;
    align-items: center;
    padding: 4px;
    background: var(--surface-2);
    border: 1px solid var(--hairline);
    border-radius: 6px;
  }
  .navseg {
    position: relative;
    padding: 5px 12px 5px 28px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    letter-spacing: 0.08em;
    color: var(--fg-mute);
    background: transparent;
    border: 0;
    border-radius: 4px;
    cursor: pointer;
    appearance: none;
    -webkit-appearance: none;
    transition: background var(--motion-fast) ease, color var(--motion-fast) ease;
  }
  .navseg .idx {
    position: absolute;
    left: 9px;
    top: 5px;
    color: var(--fg-faint);
    transition: color var(--motion-fast) ease;
  }
  .navseg:hover { color: var(--fg); }
  .navseg.active {
    background: var(--accent-soft);
    color: var(--fg);
  }
  .navseg.active .idx { color: var(--accent); }
  .navseg.active::after {
    content: "";
    position: absolute;
    left: 50%;
    bottom: -1px;
    transform: translateX(-50%);
    width: 22px;
    height: 2px;
    background: var(--accent);
    border-radius: 1px;
  }
  .navseg:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }

  /* M10 — telemetry chip strip in topnav */
  .tele-strip {
    display: flex;
    gap: 14px;
    align-items: center;
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    color: var(--fg-faint);
    letter-spacing: 0.04em;
  }
  .tele-chip {
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }
  .tele-chip strong {
    color: var(--fg);
    font-weight: 500;
    font-variant-numeric: tabular-nums;
  }
```

- [ ] **Step 3: Verify the V2 nav renders correctly**

Run: `make rebuild` then `http://localhost:8484/` in the browser.

- Three nav segments visible with mono labels (`01 CHAT`, `02 STUDIO`, `03 SYSTEM`)
- Active segment has accent-soft background + 22px underline
- Hover state lightens text from `--fg-mute` to `--fg`
- Focus ring appears on keyboard `Tab` navigation

- [ ] **Step 4: Run any existing topnav tests**

Run: `docker exec the-one pytest tests/browser/test_flow_hash_routing.py -v --tb=short`

Expected: existing route-switching tests pass (the L8.7 test still asserts `.navseg` exists for selector compatibility — check the test source for selector strings before running and update if it references `.navlink`):

```python
# In tests/browser/test_flow_hash_routing.py — search for any '.navlink' selector
# and change to '.navseg'. Same for data-area attribute.
```

If a test uses `.navlink[data-area="…"]`, change it to `.navseg[data-area="…"]`. Run again.

- [ ] **Step 5: Commit**

```bash
git add the_one/interfaces/web/static/css/components.css \
        tests/browser/test_flow_hash_routing.py
git commit -m "L2.3: replace .navlink with .navseg (mono coord segments per M10 spec §2)"
```

---

### Task 2.4: Wire telemetry-store to API counts

**Files:**
- Modify: `the_one/interfaces/web/static/js/app.js`
- Create: `the_one/interfaces/web/static/js/utils/telemetry-refresh.js`
- Test: `tests/browser/test_topnav_chips.py`

- [ ] **Step 1: Write the failing test**

Create `tests/browser/test_topnav_chips.py`:

```python
"""Tests that the topnav chip strip reflects live API counts."""

from __future__ import annotations

import httpx
import pytest
from playwright.sync_api import Page, expect


@pytest.mark.browser
def test_topnav_chips_load_real_counts_after_boot(app_clean: str, page: Page) -> None:
    """After page load + a refresh tick, chips show numeric values from
    the API — not the em-dash placeholders."""
    page.goto(app_clean)
    # Add a provider via API so PROVIDERS chip will read 1.
    httpx.post(
        f"{app_clean}/api/providers",
        json={"name": "test", "type": "anthropic", "api_key": "sk-test", "config": {}},
        timeout=2.0,
    )
    # Switch to System area where PROVIDERS chip is shown.
    page.goto(f"{app_clean}#admin")
    # The telemetry-refresh utility should fire on area mount.
    page.wait_for_timeout(800)
    chip = page.locator('.tele-chip:has-text("PROVIDERS")')
    expect(chip.locator("strong")).to_have_text("1", timeout=5000)
```

- [ ] **Step 2: Run failing test**

Run: `docker exec the-one pytest -m browser tests/browser/test_topnav_chips.py -v --tb=short`

Expected: FAIL — chip stays at em-dash.

- [ ] **Step 3: Create the refresh utility**

Create `the_one/interfaces/web/static/js/utils/telemetry-refresh.js`:

```javascript
// M10 — telemetry refresh. Fetches API counts and pushes them into
// TelemetryStore. Called on area mount and after operator actions
// that change counts (provider create/delete, agent create/delete).
(function () {
  'use strict';

  function fetchJSON(url) {
    return fetch(url, { credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .catch(function () { return null; });
  }

  function refresh() {
    Promise.all([
      fetchJSON('/api/providers'),
      fetchJSON('/api/agents'),
      fetchJSON('/api/sessions'),
      fetchJSON('/api/tools/configs')
    ]).then(function (results) {
      var providers = results[0];
      var agents = results[1];
      var sessions = results[2];
      var tools = results[3];

      var patch = {};
      if (Array.isArray(providers)) patch.providers = providers.length;
      if (Array.isArray(agents)) patch.agents = agents.length;
      if (Array.isArray(sessions)) patch.sessions = sessions.length;
      if (Array.isArray(tools)) patch.tools = tools.length;

      if (Object.keys(patch).length > 0) {
        window.TelemetryStore.set(patch);
      }
    });
  }

  window.TelemetryRefresh = { refresh: refresh };
})();
```

- [ ] **Step 4: Wire the refresh into app.js**

In `app.js`, in `performCrossAreaSwitch` (or whatever the area-mount function is called), add at the end:

```javascript
      // M10 — refresh telemetry counts on every area switch so chips stay live.
      if (window.TelemetryRefresh) window.TelemetryRefresh.refresh();
```

ALSO add an initial refresh after the topnav renders for the first time:

```javascript
    // M10 — initial telemetry hydration.
    if (window.TelemetryRefresh) window.TelemetryRefresh.refresh();
```

Place it right after the `window.Topnav.subscribeForRerender();` line from Task 2.2.

- [ ] **Step 5: Wire telemetry-refresh.js into index.html**

Modify `index.html` — add `<script src="/static/js/utils/telemetry-refresh.js"></script>` AFTER `telemetry-store.js` and BEFORE `topnav.js`.

- [ ] **Step 6: Run test — verify pass**

Run: `make rebuild && docker exec the-one pytest -m browser tests/browser/test_topnav_chips.py -v --tb=short`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add the_one/interfaces/web/static/js/utils/telemetry-refresh.js \
        the_one/interfaces/web/static/js/app.js \
        the_one/interfaces/web/static/index.html \
        tests/browser/test_topnav_chips.py
git commit -m "L2.4: wire telemetry-store to /api counts (providers, agents, sessions, tools)"
```

---

## Phase L3 — Area Headers

Goal: apply the eyebrow + bumped `.area-title` + dynamic subtitle pattern to Studio and Admin. Chat keeps its custom shell (eyebrow lands later in L5 inside the stream).

### Task 3.1: Bump `.area-title` size + add eyebrow CSS hook

**Files:**
- Modify: `the_one/interfaces/web/static/css/components.css`

- [ ] **Step 1: Edit the `.area-title` block**

Find the existing `.area-title { font-size: 22px; … }` block (added in L8.7) and update:

```css
  .area-title {
    display: block;
    font-size: 26px;  /* M10 — was 22px */
    font-weight: 500;
    letter-spacing: -0.015em;  /* M10 — was -0.02em */
    line-height: 1.1;  /* M10 — was 1.2 */
    color: var(--fg);
  }
```

- [ ] **Step 2: Verify visually**

`make rebuild` then load `http://localhost:8484/#studio` and `http://localhost:8484/#admin`. Title font size jumps from 22px to 26px. The L8.7 two-line stack of title + subtitle remains.

- [ ] **Step 3: Commit**

```bash
git add the_one/interfaces/web/static/css/components.css
git commit -m "L3.1: bump .area-title to 26px (M10 instrument scale)"
```

---

### Task 3.2: Add eyebrow + dynamic subtitle to Studio header

**Files:**
- Modify: `the_one/interfaces/web/static/js/areas/studio.js`

- [ ] **Step 1: Locate the area-header markup in studio.js**

Run: `grep -n "area-header\|area-title\|area-sub" the_one/interfaces/web/static/js/areas/studio.js | head -10`

Find where the studio area-header HTML is generated.

- [ ] **Step 2: Modify the header markup**

Replace the existing area-header template with:

```javascript
function renderStudioHeader(state) {
  // state = { agentCount, providerCount, lastEditMinutesAgo }
  var subtitle;
  if (state.agentCount === 0) {
    var pCount = state.providerCount || 0;
    subtitle = pCount === 0
      ? 'No providers configured. Wire one up in System first.'
      : 'A configured provider unlocks agent creation. You have <strong>' + pCount + ' provider' + (pCount === 1 ? '' : 's') + '</strong> wired up.';
  } else {
    var edit = state.lastEditMinutesAgo != null
      ? ' · last edit ' + state.lastEditMinutesAgo + 'm ago'
      : '';
    subtitle = state.agentCount + ' agent' + (state.agentCount === 1 ? '' : 's') + ' configured' + edit;
  }

  return (
    '<header class="area-header">' +
      '<div class="area-header-titleblock">' +
        '<div class="eyebrow">STUDIO · AGENTS</div>' +
        '<h1 class="area-title">' + (state.activeAgentName || 'Configure and edit your agents') + '</h1>' +
        '<p class="area-sub">' + subtitle + '</p>' +
      '</div>' +
      '<div class="area-header-actions">' +
        '<button class="btn-mono" data-action="new-agent">+ NEW AGENT</button>' +
      '</div>' +
    '</header>'
  );
}
```

Wire the function in to the studio init: it must run on initial mount AND after any agent CRUD operation.

- [ ] **Step 3: Compute the state**

Add this helper near the top of `studio.js`:

```javascript
function deriveStudioHeaderState() {
  var agents = window._studioAgents || [];  // populated by the existing list fetch
  var providers = window._adminProviders || [];  // populated by topnav refresh
  var activeAgentId = window._studioActiveAgentId || null;
  var active = activeAgentId ? agents.find(function (a) { return a.id === activeAgentId; }) : null;

  var lastEdit = null;
  if (active && active.updated_at) {
    var ms = Date.now() - new Date(active.updated_at).getTime();
    lastEdit = Math.max(1, Math.round(ms / 60000));
  }
  return {
    agentCount: agents.length,
    providerCount: providers.length,
    lastEditMinutesAgo: lastEdit,
    activeAgentName: active ? active.name : null
  };
}
```

(If `_studioAgents` / `_adminProviders` aren't already on `window`, adjust the read path to match the existing studio module's state model — find via grep and adapt.)

- [ ] **Step 4: Smoke verify**

`make rebuild` then load `http://localhost:8484/#studio`. Confirm:
- Eyebrow row `STUDIO · AGENTS` with leading violet rule above the title
- Title is 26px
- Subtitle reads `N agent(s) configured…` or the empty-state copy
- `+ NEW AGENT` is mono-typeset (uses `.btn-mono`)

- [ ] **Step 5: Commit**

```bash
git add the_one/interfaces/web/static/js/areas/studio.js
git commit -m "L3.2: Studio area header — eyebrow + dynamic subtitle + .btn-mono CTA"
```

---

### Task 3.3: Add eyebrow + dynamic subtitle to Admin header

**Files:**
- Modify: `the_one/interfaces/web/static/js/areas/admin.js`

- [ ] **Step 1: Locate the admin area-header markup**

Run: `grep -n "area-header\|area-title\|area-sub" the_one/interfaces/web/static/js/areas/admin.js | head -10`

- [ ] **Step 2: Replace the admin header template**

```javascript
function renderAdminHeader(state) {
  // state = { subtab: 'general' | 'providers' | 'tools', providerCount, toolsEnabled }
  var titles = {
    general:   { title: 'General',       sub: 'Appearance, encryption, base prompt — single-user local settings.' },
    providers: { title: 'LLM Providers', sub: state.providerCount === 0
      ? 'Wire up a provider to unlock the rest of the app. API keys are encrypted at rest.'
      : state.providerCount + ' provider' + (state.providerCount === 1 ? '' : 's') + ' configured · API keys encrypted at rest.' },
    tools:     { title: 'Built-in Tools', sub: state.toolsEnabled + ' / 19 tools enabled at operator level.' }
  };
  var eyebrows = {
    general:   'SYSTEM · GENERAL',
    providers: 'SYSTEM · LLM PROVIDERS',
    tools:     'SYSTEM · BUILT-IN TOOLS'
  };
  var t = titles[state.subtab] || titles.general;
  var e = eyebrows[state.subtab] || eyebrows.general;

  return (
    '<header class="area-header">' +
      '<div class="area-header-titleblock">' +
        '<div class="eyebrow">' + e + '</div>' +
        '<h1 class="area-title">' + t.title + '</h1>' +
        '<p class="area-sub">' + t.sub + '</p>' +
      '</div>' +
    '</header>'
  );
}
```

- [ ] **Step 3: Wire it into the admin mount + sub-tab switch handlers**

Find the existing admin init function and the sub-tab click handler. Call `renderAdminHeader({...})` on both initial mount and on every sub-tab switch.

- [ ] **Step 4: Smoke verify**

`make rebuild` then click through `#admin/general`, `#admin/providers`, `#admin/tools`. Eyebrow + title + subtitle update per sub-tab. Verify the URL hash routing still works (the L8.7 routing test should still pass).

- [ ] **Step 5: Commit**

```bash
git add the_one/interfaces/web/static/js/areas/admin.js
git commit -m "L3.3: Admin area header — per-subtab eyebrow + dynamic subtitle"
```

---

## Phase L4 — Empty States

Goal: implement every empty state in the spec. Each state ships with a snapshot test.

### Task 4.1: Chat empty state — first-run (no provider)

**Files:**
- Modify: `the_one/interfaces/web/static/js/areas/chat.js`
- Modify: `the_one/interfaces/web/static/css/chat.css`
- Test: `tests/browser/test_chat_empty_states.py`

- [ ] **Step 1: Write the failing test**

Create `tests/browser/test_chat_empty_states.py`:

```python
"""Empty-state coverage for the Chat area."""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.browser
def test_chat_empty_first_run_shows_two_step_cards(app_clean: str, page: Page) -> None:
    page.goto(app_clean)
    # Eyebrow + bracket headline visible
    expect(page.locator(".eyebrow:has-text('HOLOGRAPH · CHAT · IDLE')")).to_be_visible(timeout=4000)
    expect(page.locator(".brack:has-text('Two steps to your first message')")).to_be_visible()
    # Two step cards
    step1 = page.locator(".step:has-text('STEP 01')")
    step2 = page.locator(".step:has-text('STEP 02')")
    expect(step1).to_be_visible()
    expect(step2).to_be_visible()
    # Step 1 is .next (highlighted)
    expect(step1).to_have_class("step next", timeout=1000)
```

- [ ] **Step 2: Run failing test**

Run: `docker exec the-one pytest -m browser tests/browser/test_chat_empty_states.py -v --tb=short`

Expected: FAIL.

- [ ] **Step 3: Update the chat empty-state render**

In `chat.js`, find the function that renders the "Hello." empty state. Replace its body with:

```javascript
function renderChatEmptyState(state) {
  // state = { hasProvider, hasAgent }
  var step1State = state.hasProvider ? 'done' : 'next';
  var step2State = state.hasAgent ? 'done' : (state.hasProvider ? 'next' : '');
  var step1Prefix = state.hasProvider ? '✓ STEP 01' : 'STEP 01';
  var step2Prefix = state.hasAgent ? '✓ STEP 02' : 'STEP 02';

  var headline;
  if (!state.hasProvider) {
    headline = 'Two steps to your first message.';
  } else if (!state.hasAgent) {
    headline = 'One step left.';
  } else {
    headline = 'Ready when you are.';
  }

  var subtitle;
  if (!state.hasProvider) {
    subtitle = 'Configure a provider, build an agent, then come back here. The shortest path to a working setup takes about a minute.';
  } else if (!state.hasAgent) {
    subtitle = 'You have a provider. Build an agent and we\'re live.';
  } else {
    subtitle = 'Press ⌘N or use the composer to start a conversation.';
  }

  var stepsHtml = '';
  if (!state.hasProvider || !state.hasAgent) {
    stepsHtml =
      '<div class="steps">' +
        '<div class="step ' + step1State + '">' +
          '<div class="stepnum">' + step1Prefix + '</div>' +
          '<div class="steplabel">Add a provider</div>' +
          '<div class="stepdesc">Wire up an LLM — Anthropic, OpenAI, or local Ollama.</div>' +
          '<button class="step-cta" data-href="#admin/providers">Go to providers →</button>' +
        '</div>' +
        '<div class="step ' + step2State + '">' +
          '<div class="stepnum">' + step2Prefix + '</div>' +
          '<div class="steplabel">Create an agent</div>' +
          '<div class="stepdesc">Pick a model, set a persona, choose tools.</div>' +
          '<button class="step-cta" data-href="#studio/agents" ' + (step2State === '' ? 'disabled' : '') + '>Go to Studio →</button>' +
        '</div>' +
      '</div>';
  }

  return (
    '<div class="chat-empty">' +
      '<div class="eyebrow">HOLOGRAPH · CHAT · ' + (state.hasAgent ? 'READY' : 'IDLE') + '</div>' +
      '<div class="brack">' +
        '<h2 class="brack-title">' + headline + '</h2>' +
        '<p class="brack-sub">' + subtitle + '</p>' +
      '</div>' +
      stepsHtml +
    '</div>'
  );
}

// Click delegation for the step CTAs.
document.addEventListener('click', function (ev) {
  var btn = ev.target.closest('.step-cta');
  if (btn && btn.dataset.href && !btn.disabled) {
    window.location.hash = btn.dataset.href;
  }
});
```

Wire `renderChatEmptyState` into the existing empty-state branch of `chat.js`. The state object comes from `{hasProvider: window._adminProviders && window._adminProviders.length > 0, hasAgent: window._studioAgents && window._studioAgents.length > 0}` or whatever the existing module reads.

- [ ] **Step 4: Add empty-state CSS**

Append to `chat.css`:

```css
@layer areas {
  .chat-empty {
    max-width: 560px;
    margin: 0 auto;
    padding: var(--space-8) var(--space-7);
  }
  .chat-empty .brack {
    margin-bottom: var(--space-6);
  }
  .chat-empty .brack-title {
    font-size: 22px;
    font-weight: 500;
    color: var(--fg);
    line-height: 1.2;
    margin: 0;
  }
  .chat-empty .brack-sub {
    color: var(--fg-mute);
    font-size: 13px;
    margin-top: var(--space-2);
    max-width: 380px;
    line-height: 1.5;
  }
  .steps {
    display: flex;
    gap: var(--space-3);
  }
  .step {
    flex: 1;
    background: var(--surface-2);
    border: 1px solid var(--hairline);
    border-radius: 8px;
    padding: var(--space-4) var(--space-4);
    transition: border-color var(--motion-base) ease, background var(--motion-base) ease;
  }
  .step.next {
    border-color: var(--accent);
    background: var(--accent-soft);
  }
  .step.done .stepnum {
    color: var(--good);
  }
  .stepnum {
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    letter-spacing: 0.12em;
    color: var(--accent);
    text-transform: uppercase;
    margin-bottom: var(--space-2);
  }
  .steplabel {
    font-size: 13px;
    color: var(--fg);
    font-weight: 500;
    margin-bottom: 3px;
  }
  .stepdesc {
    font-size: 11px;
    color: var(--fg-mute);
    line-height: 1.5;
    margin-bottom: var(--space-3);
  }
  .step-cta {
    background: transparent;
    border: 0;
    padding: 0;
    color: var(--accent);
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    letter-spacing: 0.04em;
    cursor: pointer;
  }
  .step-cta:disabled {
    color: var(--fg-faint);
    cursor: not-allowed;
  }
}
```

- [ ] **Step 5: Run tests — verify pass**

Run: `make rebuild && docker exec the-one pytest -m browser tests/browser/test_chat_empty_states.py -v --tb=short`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add the_one/interfaces/web/static/js/areas/chat.js \
        the_one/interfaces/web/static/css/chat.css \
        tests/browser/test_chat_empty_states.py
git commit -m "L4.1: Chat empty state — eyebrow + bracket headline + two-step card flow"
```

---

### Task 4.2: Studio · Agents empty state

**Files:**
- Modify: `the_one/interfaces/web/static/js/areas/studio.js`
- Modify: `the_one/interfaces/web/static/css/studio.css`
- Test: `tests/browser/test_studio_empty_states.py`

- [ ] **Step 1: Write failing test**

Create `tests/browser/test_studio_empty_states.py`:

```python
from __future__ import annotations
import pytest
from playwright.sync_api import Page, expect


@pytest.mark.browser
def test_studio_agents_empty_shows_bracket_and_two_ctas(app_clean: str, page: Page) -> None:
    page.goto(f"{app_clean}#studio/agents")
    expect(page.locator(".eyebrow:has-text('STUDIO · AGENTS')").first).to_be_visible(timeout=4000)
    expect(page.locator(".brack:has-text('Build your first agent')")).to_be_visible()
    expect(page.locator(".btn-mono:has-text('+ NEW AGENT')")).to_be_visible()
    expect(page.locator("button:has-text('start from preset')")).to_be_visible()
```

- [ ] **Step 2: Run failing test**

Run: `docker exec the-one pytest -m browser tests/browser/test_studio_empty_states.py -v --tb=short`

Expected: FAIL.

- [ ] **Step 3: Update the studio empty-state render**

In `studio.js`, find where the "No agents yet" empty state is rendered. Replace with:

```javascript
function renderStudioAgentsEmpty() {
  return (
    '<div class="studio-empty">' +
      '<div class="studio-cols">' +
        '<aside class="agents-list">' +
          '<div class="agents-list-l">AGENT LIST<span>0</span></div>' +
          '<div class="agents-list-empty">no agents · click + to create</div>' +
        '</aside>' +
        '<div class="studio-empty-focal">' +
          '<div class="brack">' +
            '<h2 class="brack-title">Build your first agent.</h2>' +
            '<p class="brack-sub">An agent is a model + persona + tool selection. The default tool kit covers shell, filesystem, web, and Python — narrow it from there.</p>' +
          '</div>' +
          '<div class="studio-empty-ctas">' +
            '<button class="btn-mono" data-action="new-agent">+ NEW AGENT</button>' +
            '<button class="btn-link-mono" data-action="open-presets">→ start from preset</button>' +
          '</div>' +
        '</div>' +
      '</div>' +
    '</div>'
  );
}
```

- [ ] **Step 4: Add the CSS**

Append to `studio.css` inside `@layer areas`:

```css
  .studio-empty .studio-cols {
    display: grid;
    grid-template-columns: 260px 1fr;
    gap: var(--space-6);
    margin-top: var(--space-5);
  }
  .agents-list-l {
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    letter-spacing: 0.12em;
    color: var(--fg-faint);
    text-transform: uppercase;
    margin-bottom: var(--space-3);
    display: flex;
    justify-content: space-between;
  }
  .agents-list-l span { color: var(--fg-mute); font-weight: 500; }
  .agents-list-empty {
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    color: var(--fg-faint);
    padding-left: var(--space-3);
    border-left: 2px solid var(--hairline);
  }
  .studio-empty-ctas {
    margin-top: var(--space-5);
    display: flex;
    gap: var(--space-3);
    align-items: center;
  }
  .btn-link-mono {
    background: transparent;
    border: 0;
    padding: 9px 16px;
    color: var(--fg-mute);
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    cursor: pointer;
  }
  .btn-link-mono:hover { color: var(--fg); }
```

- [ ] **Step 5: Wire `data-action="new-agent"` to existing new-agent flow**

In `studio.js`, ensure the existing click handler that opens the new-agent form responds to `[data-action="new-agent"]` (not just the previous `#new-agent-btn` id). Add or extend the handler accordingly.

- [ ] **Step 6: Run tests — verify pass**

Run: `make rebuild && docker exec the-one pytest -m browser tests/browser/test_studio_empty_states.py -v --tb=short`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add the_one/interfaces/web/static/js/areas/studio.js \
        the_one/interfaces/web/static/css/studio.css \
        tests/browser/test_studio_empty_states.py
git commit -m "L4.2: Studio agents empty state — bracket + agent-list rail + two CTAs"
```

---

### Task 4.3: Studio · Knowledge / MCP Sources empty states

**Files:**
- Modify: `the_one/interfaces/web/static/js/areas/studio/knowledge-tab.js`
- Modify: `the_one/interfaces/web/static/js/areas/studio/mcps-tab.js`
- Test: extend `tests/browser/test_studio_empty_states.py`

- [ ] **Step 1: Extend the test file**

Add to `tests/browser/test_studio_empty_states.py`:

```python
@pytest.mark.browser
def test_studio_knowledge_empty(app_clean: str, page: Page) -> None:
    page.goto(f"{app_clean}#studio/knowledge")
    expect(page.locator(".brack:has-text('No knowledge bases yet')")).to_be_visible(timeout=4000)


@pytest.mark.browser
def test_studio_mcp_empty(app_clean: str, page: Page) -> None:
    page.goto(f"{app_clean}#studio/mcp-sources")
    expect(page.locator(".brack:has-text('No MCP sources connected')")).to_be_visible(timeout=4000)
```

- [ ] **Step 2: Run failing tests**

Run: `docker exec the-one pytest -m browser tests/browser/test_studio_empty_states.py::test_studio_knowledge_empty tests/browser/test_studio_empty_states.py::test_studio_mcp_empty -v --tb=short`

Expected: 2 FAIL.

- [ ] **Step 3: Implement knowledge-tab empty state**

In `knowledge-tab.js`, find where "No knowledge bases" or similar copy renders. Replace with:

```javascript
function renderKnowledgeEmpty() {
  return (
    '<div class="studio-empty">' +
      '<div class="brack">' +
        '<h2 class="brack-title">No knowledge bases yet.</h2>' +
        '<p class="brack-sub">Knowledge is searchable content an agent can cite. Add markdown, web pages, or PDF excerpts; the agent calls a search tool to retrieve relevant chunks.</p>' +
      '</div>' +
      '<div class="studio-empty-ctas">' +
        '<button class="btn-mono" data-action="new-knowledge">+ NEW KNOWLEDGE BASE</button>' +
      '</div>' +
    '</div>'
  );
}
```

- [ ] **Step 4: Implement mcps-tab empty state**

In `mcps-tab.js`, replace the empty state with:

```javascript
function renderMcpsEmpty() {
  return (
    '<div class="studio-empty">' +
      '<div class="brack">' +
        '<h2 class="brack-title">No MCP sources connected.</h2>' +
        '<p class="brack-sub">Connect a Model Context Protocol server to extend an agent\'s tool surface. Supports stdio and streamable-HTTP transports; OAuth is handled spec-compliantly.</p>' +
      '</div>' +
      '<div class="studio-empty-ctas">' +
        '<button class="btn-mono" data-action="new-mcp-source">+ NEW MCP SOURCE</button>' +
      '</div>' +
    '</div>'
  );
}
```

- [ ] **Step 5: Run tests — verify pass**

Run: `make rebuild && docker exec the-one pytest -m browser tests/browser/test_studio_empty_states.py -v --tb=short`

Expected: 3 PASS (Task 4.2's test plus the 2 new ones).

- [ ] **Step 6: Commit**

```bash
git add the_one/interfaces/web/static/js/areas/studio/knowledge-tab.js \
        the_one/interfaces/web/static/js/areas/studio/mcps-tab.js \
        tests/browser/test_studio_empty_states.py
git commit -m "L4.3: Studio Knowledge + MCP Sources empty states"
```

---

### Task 4.4: Admin · LLM Providers empty state (4-card grid)

**Files:**
- Modify: `the_one/interfaces/web/static/js/areas/admin/providers-grid.js`
- Test: `tests/browser/test_admin_empty_states.py`

- [ ] **Step 1: Write failing test**

Create `tests/browser/test_admin_empty_states.py`:

```python
from __future__ import annotations
import pytest
from playwright.sync_api import Page, expect


@pytest.mark.browser
def test_admin_providers_empty_shows_four_provider_cards(app_clean: str, page: Page) -> None:
    page.goto(f"{app_clean}#admin/providers")
    # Eyebrow + title
    expect(page.locator(".eyebrow:has-text('SYSTEM · LLM PROVIDERS')")).to_be_visible(timeout=4000)
    expect(page.locator(".area-title:has-text('LLM Providers')")).to_be_visible()
    # Four type cards
    expect(page.locator(".provider-type-card:has-text('Anthropic')")).to_be_visible()
    expect(page.locator(".provider-type-card:has-text('OpenAI')").first).to_be_visible()
    expect(page.locator(".provider-type-card:has-text('Ollama')")).to_be_visible()
    # Anthropic is flagged RECOMMENDED
    rec = page.locator(".provider-type-card:has-text('Anthropic')")
    expect(rec.locator(".provider-type-cat")).to_have_text("RECOMMENDED")
```

- [ ] **Step 2: Run failing test**

Run: `docker exec the-one pytest -m browser tests/browser/test_admin_empty_states.py -v --tb=short`

Expected: FAIL.

- [ ] **Step 3: Modify providers-grid.js**

In `providers-grid.js`, find the empty-state branch. Replace with:

```javascript
function renderProvidersEmpty(onPickType) {
  var types = [
    { id: 'anthropic',           name: 'Anthropic',         cat: 'RECOMMENDED', desc: 'Claude family · API key',  recommended: true },
    { id: 'openai',              name: 'OpenAI',            cat: 'CLOUD',       desc: 'GPT family · API key',     recommended: false },
    { id: 'openai-compatible',   name: 'OpenAI-compatible', cat: 'CLOUD',       desc: 'Together, Groq, etc.',     recommended: false },
    { id: 'ollama',              name: 'Ollama',            cat: 'LOCAL',       desc: 'Self-hosted · no key',     recommended: false }
  ];
  var cardsHtml = types.map(function (t) {
    var cls = 'provider-type-card' + (t.recommended ? ' recommended' : '');
    return (
      '<button class="' + cls + '" data-provider-type="' + t.id + '">' +
        '<div class="provider-type-cat">' + t.cat + '</div>' +
        '<div class="provider-type-name">' + t.name + '</div>' +
        '<div class="provider-type-desc">' + t.desc + '</div>' +
      '</button>'
    );
  }).join('');

  var container = document.querySelector('#admin-providers-content');
  container.innerHTML = '<div class="provider-type-grid">' + cardsHtml + '</div>';
  container.querySelectorAll('.provider-type-card').forEach(function (card) {
    card.addEventListener('click', function () { onPickType(card.dataset.providerType); });
  });
}
```

- [ ] **Step 4: Add CSS to admin.css**

```css
  .provider-type-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: var(--space-3);
    margin-top: var(--space-6);
  }
  .provider-type-card {
    padding: var(--space-4);
    background: var(--surface-2);
    border: 1px solid var(--hairline);
    border-radius: 8px;
    text-align: left;
    cursor: pointer;
    appearance: none;
    -webkit-appearance: none;
    transition: border-color var(--motion-fast) ease, transform var(--motion-fast) ease;
  }
  .provider-type-card.recommended { border-color: var(--accent); }
  .provider-type-card:hover { transform: translateY(-1px); border-color: var(--accent); }
  .provider-type-cat {
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    letter-spacing: 0.1em;
    color: var(--fg-faint);
    margin-bottom: var(--space-2);
  }
  .provider-type-card.recommended .provider-type-cat { color: var(--accent); }
  .provider-type-name {
    font-size: 13px;
    color: var(--fg);
    font-weight: 500;
    margin-bottom: 2px;
  }
  .provider-type-desc {
    font-size: 11px;
    color: var(--fg-mute);
  }
```

- [ ] **Step 5: Wire `onPickType` to open the existing provider-editor modal**

The existing modal flow probably routes to `#admin/providers/new?type=anthropic` or similar. Trace the existing path:

Run: `grep -rn "provider-editor\|new-provider\|provider-type" the_one/interfaces/web/static/js/areas/admin/ | head -10`

Pass the picked type into the existing modal opener with a sensible argument shape — verify by reading the existing editor module.

- [ ] **Step 6: Run tests — verify pass**

Run: `make rebuild && docker exec the-one pytest -m browser tests/browser/test_admin_empty_states.py -v --tb=short`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add the_one/interfaces/web/static/js/areas/admin/providers-grid.js \
        the_one/interfaces/web/static/css/admin.css \
        tests/browser/test_admin_empty_states.py
git commit -m "L4.4: Admin providers empty — 4-card type grid with Anthropic recommended"
```

---

### Task 4.5: Agent presets ("start from preset")

**Files:**
- Create: `the_one/agent/_presets.py`
- Modify: `the_one/interfaces/web/api.py` (add `/api/agent-presets` endpoint)
- Modify: `the_one/interfaces/web/static/js/areas/studio.js` (preset picker dialog)
- Test: `tests/test_agent_presets.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_agent_presets.py`:

```python
"""Tests the agent preset registry."""

from __future__ import annotations


def test_presets_module_exports_three_presets():
    from the_one.agent._presets import PRESETS
    assert len(PRESETS) == 3
    names = {p["name"] for p in PRESETS}
    assert names == {"research", "shell-buddy", "web-crawler"}


def test_presets_each_have_required_keys():
    from the_one.agent._presets import PRESETS
    for p in PRESETS:
        assert "name" in p
        assert "description" in p
        assert "tools_enabled" in p
        assert isinstance(p["tools_enabled"], list)
        assert "system_prompt" in p
        assert "default_model_family" in p  # 'opus' | 'sonnet' | 'haiku'


def test_research_preset_is_read_only():
    from the_one.agent._presets import PRESETS
    research = next(p for p in PRESETS if p["name"] == "research")
    forbidden = {"write_file", "delete_file", "edit_file", "move_file"}
    assert not (set(research["tools_enabled"]) & forbidden), (
        "research preset must not include write tools"
    )


def test_shell_buddy_preset_is_minimal():
    from the_one.agent._presets import PRESETS
    sb = next(p for p in PRESETS if p["name"] == "shell-buddy")
    assert "shell" in sb["tools_enabled"]
    assert "web_search" not in sb["tools_enabled"]
    assert sb["default_model_family"] == "haiku"
```

- [ ] **Step 2: Run failing test**

Run: `docker exec the-one pytest tests/test_agent_presets.py -v --tb=short`

Expected: 4 FAIL (`ImportError`).

- [ ] **Step 3: Create the presets module**

Create `the_one/agent/_presets.py`:

```python
"""Agent preset registry — surfaced via the Studio "start from preset" picker.

Each preset is a recipe: a model family hint, a system prompt, and a starter
tool set. The user can edit any field after creation; presets are just a
warm-start convenience.
"""

from __future__ import annotations

from typing import Any

PRESETS: list[dict[str, Any]] = [
    {
        "name": "research",
        "description": "Read-only research assistant. Greps, reads, cites — never writes.",
        "default_model_family": "opus",
        "system_prompt": (
            "You are a research assistant. Use grep, find, read_file, and "
            "web_search to investigate the worktree and the open web. Cite "
            "specific paths and line numbers when surfacing findings. Do not "
            "modify any files."
        ),
        "tools_enabled": [
            "shell",
            "grep",
            "read_file",
            "glob",
            "list_dir",
            "web_search",
            "fetch_url",
            "http_request",
            "search_tools",
            "continue",
        ],
    },
    {
        "name": "shell-buddy",
        "description": "Fast shell + filesystem helper. Tight scope.",
        "default_model_family": "haiku",
        "system_prompt": (
            "You are a focused shell assistant. Help with one-liners, "
            "filesystem operations, and quick scripting. Ask for the working "
            "directory if unclear."
        ),
        "tools_enabled": [
            "shell",
            "read_file",
            "write_file",
            "edit_file",
            "glob",
            "list_dir",
            "search_tools",
            "continue",
        ],
    },
    {
        "name": "web-crawler",
        "description": "Web research only — no filesystem or shell.",
        "default_model_family": "sonnet",
        "system_prompt": (
            "You are a web research assistant. Use web_search, fetch_url, and "
            "http_request to gather information. Cite source URLs. You have no "
            "filesystem access."
        ),
        "tools_enabled": [
            "web_search",
            "fetch_url",
            "http_request",
            "download_file",
            "search_tools",
            "continue",
        ],
    },
]
```

- [ ] **Step 4: Run tests — verify pass**

Run: `docker exec the-one pytest tests/test_agent_presets.py -v --tb=short`

Expected: 4 PASS.

- [ ] **Step 5: Add API endpoint**

In `the_one/interfaces/web/api.py`, add:

```python
@router.get("/agent-presets")
async def list_agent_presets() -> list[dict]:
    """Return the agent preset registry for the Studio picker."""
    from the_one.agent._presets import PRESETS
    return PRESETS
```

Place it alongside the other `/api/...` route handlers. Confirm the router is the one mounted under `/api`.

- [ ] **Step 6: Add the preset picker dialog**

In `studio.js`, add a function that opens a dialog (use the existing `dialog.js` helper at `the_one/interfaces/web/static/js/dialog.js`):

```javascript
function openPresetPicker(onPick) {
  fetch('/api/agent-presets', { credentials: 'same-origin' })
    .then(function (r) { return r.json(); })
    .then(function (presets) {
      var optsHtml = presets.map(function (p) {
        return (
          '<button class="preset-option" data-name="' + p.name + '">' +
            '<div class="preset-name">' + p.name + '</div>' +
            '<div class="preset-desc">' + p.description + '</div>' +
            '<div class="preset-meta">' + p.default_model_family + ' · ' + p.tools_enabled.length + ' tools</div>' +
          '</button>'
        );
      }).join('');
      window.App.dialog.open({
        title: 'Start from preset',
        content: '<div class="preset-list">' + optsHtml + '</div>',
        onMount: function (root) {
          root.querySelectorAll('.preset-option').forEach(function (b) {
            b.addEventListener('click', function () {
              var preset = presets.find(function (p) { return p.name === b.dataset.name; });
              onPick(preset);
              window.App.dialog.close();
            });
          });
        }
      });
    });
}

// Wire the "→ start from preset" CTA from Task 4.2 to this opener.
document.addEventListener('click', function (ev) {
  var btn = ev.target.closest('[data-action="open-presets"]');
  if (!btn) return;
  openPresetPicker(function (preset) {
    // Open the new-agent editor pre-filled with the preset's fields.
    if (window.Studio && window.Studio.newAgentFromPreset) {
      window.Studio.newAgentFromPreset(preset);
    }
  });
});
```

`window.Studio.newAgentFromPreset(preset)` is a small helper — add it on the studio module to pipe preset values into the existing new-agent form:

```javascript
window.Studio = window.Studio || {};
window.Studio.newAgentFromPreset = function (preset) {
  window.Studio.openNewAgentEditor({
    initialName: preset.name + '-copy',
    initialPrompt: preset.system_prompt,
    initialTools: preset.tools_enabled,
    modelHint: preset.default_model_family
  });
};
```

Wire `openNewAgentEditor` to whatever the existing studio module uses for opening the new-agent form (find via grep and adapt the call shape).

- [ ] **Step 7: Add minimal preset-picker CSS**

Append to `studio.css`:

```css
  .preset-list { display: flex; flex-direction: column; gap: var(--space-2); }
  .preset-option {
    padding: var(--space-4);
    background: var(--surface-2);
    border: 1px solid var(--hairline);
    border-radius: 8px;
    text-align: left;
    cursor: pointer;
    appearance: none;
    -webkit-appearance: none;
    transition: border-color var(--motion-fast) ease;
  }
  .preset-option:hover { border-color: var(--accent); }
  .preset-name { color: var(--fg); font-size: 14px; font-weight: 500; margin-bottom: 2px; }
  .preset-desc { color: var(--fg-mute); font-size: 12px; margin-bottom: var(--space-2); }
  .preset-meta {
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    color: var(--fg-faint);
    letter-spacing: 0.04em;
  }
```

- [ ] **Step 8: Smoke verify**

`make rebuild` → `http://localhost:8484/#studio/agents` (with no agents). Click "→ start from preset". Dialog opens with three preset options. Picking one opens the new-agent editor with prefilled fields. Saving creates an agent.

- [ ] **Step 9: Commit**

```bash
git add the_one/agent/_presets.py \
        the_one/interfaces/web/api.py \
        the_one/interfaces/web/static/js/areas/studio.js \
        the_one/interfaces/web/static/css/studio.css \
        tests/test_agent_presets.py
git commit -m "L4.5: agent presets — research / shell-buddy / web-crawler via Studio picker"
```

---

### Task 4.6: Visual snapshot baselines for L4

**Files:**
- Modify: `tests/browser/test_visual_snapshots.py`
- Modify: `tests/browser/__snapshots__/*.png`

- [ ] **Step 1: Add snapshot cases for new empty states**

In `test_visual_snapshots.py`, add cases for:
- Chat empty first-run, dark + light
- Studio agents empty, dark + light
- Studio knowledge empty, dark + light
- Studio MCP empty, dark + light
- Admin providers empty (4-card), dark + light

(8 new baseline images.)

- [ ] **Step 2: Generate baselines**

Run: `docker exec the-one pytest -m browser tests/browser/test_visual_snapshots.py --snapshot-update`

Expected: 8 new snapshots created, all existing ones regenerated (they now sit on the L1 grid canvas).

- [ ] **Step 3: Commit**

```bash
git add tests/browser/__snapshots__/ tests/browser/test_visual_snapshots.py
git commit -m "L4.6: visual snapshot baselines for L4 empty states"
```

---

## Phase L5 — Working States

Goal: polish the in-conversation Chat experience, the populated Studio editor, and the populated Admin views with the same lens primitives.

### Task 5.1: Chat stream — session eyebrow + mono `who` lines

**Files:**
- Modify: `the_one/interfaces/web/static/js/areas/chat.js`
- Modify: `the_one/interfaces/web/static/js/areas/chat/message-bubble.js`
- Modify: `the_one/interfaces/web/static/css/chat.css`

- [ ] **Step 1: Add the stream-leading session eyebrow**

In `chat.js`, find where the conversation stream is rendered. Above the first message, add:

```javascript
function renderSessionEyebrow(session) {
  if (!session) return '';
  return '<div class="eyebrow stream-eyebrow">SESSION ' +
    String(session.index || 1).padStart(2, '0') +
    ' · ' + (session.title || 'untitled').toUpperCase() + '</div>';
}
```

Prepend this once at the top of the rendered stream when a session is active.

- [ ] **Step 2: Restyle `who` lines in message-bubble.js**

Find the message bubble template. Replace the existing speaker label with:

```javascript
function renderWhoLine(msg) {
  if (msg.role === 'user') {
    return '<div class="msg-who msg-who-user">YOU <span class="who-tag">→' + (msg.agent_name || '').toLowerCase() + '</span></div>';
  } else {
    return '<div class="msg-who msg-who-agent"><span class="who-tag">' + (msg.agent_name || 'agent').toLowerCase() + '</span> ← ' + (msg.model || '').toLowerCase() + '</div>';
  }
}
```

- [ ] **Step 3: Add CSS**

In `chat.css`:

```css
  .stream-eyebrow {
    margin-bottom: var(--space-5);
    margin-top: var(--space-3);
  }
  .msg-who {
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    letter-spacing: 0.1em;
    color: var(--fg-faint);
    text-transform: uppercase;
    margin-bottom: var(--space-2);
    display: flex;
    align-items: center;
    gap: var(--space-2);
  }
  .msg-who .who-tag { color: var(--accent); }
```

- [ ] **Step 4: Smoke verify with a real conversation**

Run: `make rebuild`. Add a provider + agent (use the empty-state CTAs). Start a chat, send a message, get a response. Verify:
- Stream starts with `SESSION 01 · {TITLE}` eyebrow
- User message shows `YOU →research`
- Agent message shows `research ← claude-opus-4-7`

- [ ] **Step 5: Commit**

```bash
git add the_one/interfaces/web/static/js/areas/chat.js \
        the_one/interfaces/web/static/js/areas/chat/message-bubble.js \
        the_one/interfaces/web/static/css/chat.css
git commit -m "L5.1: Chat stream — session eyebrow + mono who-lines"
```

---

### Task 5.2: Tool-call header restyle

**Files:**
- Modify: `the_one/interfaces/web/static/css/chat.css`

- [ ] **Step 1: Find the existing `.toolcall` styles**

Run: `grep -n "\\.toolcall" the_one/interfaces/web/static/css/chat.css | head -5`

- [ ] **Step 2: Restyle**

Replace the existing `.toolcall` rules with:

```css
  .toolcall {
    margin: var(--space-3) 0;
    padding: var(--space-3) var(--space-4);
    background: var(--surface-2);
    border: 0;
    border-left: 2px solid var(--accent);
    border-radius: 4px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    color: var(--fg-mute);
  }
  .toolcall-head {
    display: flex;
    justify-content: space-between;
    margin-bottom: var(--space-1);
  }
  .toolcall-head .tc-name { color: var(--accent); }
  .toolcall-head .tc-meta { color: var(--fg-faint); }
  .toolcall-body {
    color: var(--fg);
    white-space: pre;
    overflow-x: auto;
  }
```

If the existing template's class names differ (e.g., `.toolcall .head` vs `.toolcall-head`), grep the rendering JS for the exact selectors and adapt accordingly — the goal is the visual treatment, not the class taxonomy.

- [ ] **Step 3: Smoke verify**

Trigger a tool call in chat. Confirm the new left-border + mono header format renders.

- [ ] **Step 4: Commit**

```bash
git add the_one/interfaces/web/static/css/chat.css
git commit -m "L5.2: tool-call block — accent left-border + mono header"
```

---

### Task 5.3: Working-row indicator

**Files:**
- Modify: `the_one/interfaces/web/static/js/areas/chat/thinking-indicator.js`
- Modify: `the_one/interfaces/web/static/css/chat.css`

- [ ] **Step 1: Replace the thinking indicator markup**

In `thinking-indicator.js`, find the existing "thinking" indicator. Replace its template with:

```javascript
function renderWorkingRow(state) {
  // state = { tokens_so_far, tokens_target }
  var tokensPart = '';
  if (state && state.tokens_so_far != null && state.tokens_target != null) {
    tokensPart = ' · token ' + state.tokens_so_far + ' / ' + state.tokens_target;
  }
  return '<div class="working-row">' +
    '<span class="stat-dot work"></span>' +
    '<span class="working-label">WORKING</span>' +
    '<span class="working-detail">— agent is responding' + tokensPart + '</span>' +
  '</div>';
}
```

- [ ] **Step 2: Add CSS**

In `chat.css`:

```css
  .working-row {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    color: var(--fg-faint);
    letter-spacing: 0.06em;
    padding: var(--space-2) 0;
  }
  .working-label { color: var(--accent); }
  .working-detail { color: var(--fg-mute); }
```

- [ ] **Step 3: Smoke verify**

Send a message that triggers a long-running agent response. Confirm the working-row shows with a pulsing accent dot and a `token N / M` counter.

- [ ] **Step 4: Commit**

```bash
git add the_one/interfaces/web/static/js/areas/chat/thinking-indicator.js \
        the_one/interfaces/web/static/css/chat.css
git commit -m "L5.3: working-row indicator — pulsing dot + token counter"
```

---

### Task 5.4: Studio editor — coord-header + mono fields + tool chips

**Files:**
- Modify: `the_one/interfaces/web/static/js/areas/studio/agent-editor.js`
- Modify: `the_one/interfaces/web/static/css/studio.css`

- [ ] **Step 1: Replace the editor header**

In `agent-editor.js`, find where the editor header (with agent name + actions) renders. Replace with:

```javascript
function renderEditorHeader(agent, state) {
  // state = { isDirty, agentIndex }
  var idx = String((state.agentIndex || 0) + 1).padStart(2, '0');
  return (
    '<div class="editor-head">' +
      '<div>' +
        '<div class="editor-coord"><span class="dot">●</span> EDITING · AGENT ' + idx + '</div>' +
        '<div class="editor-name">' + (agent.name || 'new agent') + '</div>' +
      '</div>' +
      '<div class="editor-actions">' +
        '<button class="btn-action" data-action="revert" ' + (state.isDirty ? '' : 'disabled') + '>↻ REVERT</button>' +
        '<button class="btn-action accent" data-action="save" ' + (state.isDirty ? '' : 'disabled') + '>✓ SAVE</button>' +
      '</div>' +
    '</div>'
  );
}
```

- [ ] **Step 2: Convert field labels to mono**

For each form field block in the editor, ensure the label uses the `.field-label` class with optional `.field-hint` smalls:

```javascript
function renderField(label, hint, inputHtml) {
  var hintHtml = hint ? '<span class="field-hint">' + hint + '</span>' : '';
  return (
    '<div class="field">' +
      '<div class="field-label">' + label + hintHtml + '</div>' +
      inputHtml +
    '</div>'
  );
}

// Example call sites:
// renderField('PROVIDER · MODEL', 'claude family · 1m context', '<select>…</select>')
// renderField('SYSTEM PROMPT', '~120 words · appended to base', '<textarea>…</textarea>')
// renderField('TOOLS · ' + agent.tools_enabled.length + ' / 19 enabled', 'narrowed from defaults', toolChipsHtml)
```

- [ ] **Step 3: Render tool chips**

Replace any existing tool-toggle block with:

```javascript
function renderToolChips(allTools, enabled) {
  // allTools is the registry; enabled is the agent's filter.
  var enabledSet = new Set(enabled);
  return allTools.map(function (t) {
    var on = enabledSet.has(t.name);
    var cls = 'tool-chip' + (on ? ' on' : ' off');
    return '<button class="' + cls + '" data-tool="' + t.name + '">' + t.name + '</button>';
  }).join('');
}
```

- [ ] **Step 4: Add CSS**

Append to `studio.css`:

```css
  .editor-head {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: var(--space-5);
    padding-bottom: var(--space-4);
    border-bottom: 1px solid var(--hairline);
  }
  .editor-coord {
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    letter-spacing: 0.1em;
    color: var(--fg-faint);
    text-transform: uppercase;
  }
  .editor-coord .dot { color: var(--accent); }
  .editor-name { font-size: 18px; color: var(--fg); font-weight: 500; }
  .editor-actions { display: flex; gap: var(--space-2); }
  .btn-action {
    background: transparent;
    border: 0;
    padding: 6px 12px;
    color: var(--fg-mute);
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    cursor: pointer;
  }
  .btn-action.accent { color: var(--accent); }
  .btn-action:disabled { color: var(--fg-faint); cursor: not-allowed; }

  .field { margin-bottom: var(--space-5); }
  .field-label {
    display: flex;
    gap: var(--space-2);
    align-items: baseline;
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    letter-spacing: 0.1em;
    color: var(--fg-faint);
    text-transform: uppercase;
    margin-bottom: var(--space-2);
  }
  .field-hint {
    color: var(--fg-faint);
    font-size: 9px;
    text-transform: none;
    letter-spacing: 0;
  }

  .tool-chip {
    padding: 3px 8px;
    background: var(--bg);
    border: 1px solid var(--hairline);
    border-radius: 4px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    cursor: pointer;
    margin: 2px;
  }
  .tool-chip.on { color: var(--fg-mute); }
  .tool-chip.off {
    color: var(--fg-faint);
    text-decoration: line-through;
    border-style: dashed;
  }
```

- [ ] **Step 5: Smoke verify**

Open Studio → select an agent → verify:
- Editor header shows `● EDITING · AGENT 01` coord above the agent name
- Save/Revert buttons disabled until a field is edited
- Fields show mono labels + hints
- Tool chips render with on/off styling

- [ ] **Step 6: Commit**

```bash
git add the_one/interfaces/web/static/js/areas/studio/agent-editor.js \
        the_one/interfaces/web/static/css/studio.css
git commit -m "L5.4: Studio editor — coord-header + mono fields + tool chips"
```

---

### Task 5.5: Admin provider cards — status dots + last-used

**Files:**
- Modify: `the_one/interfaces/web/static/js/areas/admin/providers-grid.js`
- Modify: `the_one/interfaces/web/static/css/admin.css`

- [ ] **Step 1: Restyle the populated provider card**

In `providers-grid.js`, find the rendering function for populated provider cards (when at least one provider exists). Replace the card template with:

```javascript
function renderProviderCard(p) {
  var statusClass = p.last_test_ok ? 'ok' : (p.last_test_ok === false ? 'err' : 'idle');
  var statusLabel = p.last_test_ok ? 'READY' : (p.last_test_ok === false ? 'ERROR' : 'UNTESTED');
  var lastUsed = p.last_used_at ? formatRelative(p.last_used_at) : 'never';
  return (
    '<button class="provider-card" data-provider-id="' + p.id + '">' +
      '<div class="provider-card-head">' +
        '<div class="provider-type-cat">' + p.type.toUpperCase() + '</div>' +
        '<div class="provider-card-status"><span class="stat-dot ' + statusClass + '"></span>' + statusLabel + '</div>' +
      '</div>' +
      '<div class="provider-card-name">' + p.name + '</div>' +
      '<div class="provider-card-meta">LAST USED · ' + lastUsed.toUpperCase() + '</div>' +
    '</button>'
  );
}

function formatRelative(iso) {
  var ms = Date.now() - new Date(iso).getTime();
  var min = Math.floor(ms / 60000);
  if (min < 1) return 'just now';
  if (min < 60) return min + 'm ago';
  var hr = Math.floor(min / 60);
  if (hr < 24) return hr + 'h ago';
  return Math.floor(hr / 24) + 'd ago';
}
```

If `last_test_ok` / `last_used_at` aren't on the existing provider payload, defer them — render `UNTESTED` and `never` for now. (Wiring those fields server-side is a separate small task; the M10 spec assumes they exist or fall back gracefully.)

- [ ] **Step 2: Add CSS**

In `admin.css`:

```css
  .provider-card {
    padding: var(--space-4);
    background: var(--surface-2);
    border: 1px solid var(--hairline);
    border-radius: 8px;
    text-align: left;
    cursor: pointer;
    appearance: none;
    -webkit-appearance: none;
    transition: border-color var(--motion-fast) ease;
  }
  .provider-card:hover { border-color: var(--accent); }
  .provider-card-head {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: var(--space-2);
  }
  .provider-card-status {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    font-family: 'JetBrains Mono', monospace;
    font-size: 9px;
    letter-spacing: 0.1em;
    color: var(--fg-mute);
  }
  .provider-card-name {
    font-size: 14px;
    color: var(--fg);
    font-weight: 500;
    margin-bottom: var(--space-3);
  }
  .provider-card-meta {
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    color: var(--fg-faint);
    letter-spacing: 0.06em;
  }
```

- [ ] **Step 3: Smoke verify**

Add 2-3 providers via Admin. Confirm each card shows: TYPE label, status dot+label, name, LAST USED meta.

- [ ] **Step 4: Commit**

```bash
git add the_one/interfaces/web/static/js/areas/admin/providers-grid.js \
        the_one/interfaces/web/static/css/admin.css
git commit -m "L5.5: Admin populated provider cards — status dot + last-used meta"
```

---

## Phase L6 — Motion + WS Telemetry

Goal: subtle motion across the app + measured WS round-trip time backing the WS chip.

### Task 6.1: Area transition fade

**Files:**
- Modify: `the_one/interfaces/web/static/css/components.css`

- [ ] **Step 1: Add the transition**

Append to `components.css` inside `@layer components`:

```css
  .content-panel {
    transition: opacity var(--motion-base) ease;
  }
  /* When the L8.7 router toggles display: none, opacity won't transition
     (no element). When it sets display: '', opacity defaults to 1.
     To make the fade actually transition, the router must opacity-flip
     in two ticks. See Task 6.2 for the JS side. */
```

- [ ] **Step 2: Verify CSS lints**

Run: `make rebuild 2>&1 | grep -iE "error|fail" | head -5 || echo "clean"`

- [ ] **Step 3: Commit**

```bash
git add the_one/interfaces/web/static/css/components.css
git commit -m "L6.1: add .content-panel opacity transition (180ms)"
```

---

### Task 6.2: Two-tick opacity flip in router

**Files:**
- Modify: `the_one/interfaces/web/static/js/app.js`

- [ ] **Step 1: Modify the L8.7 display toggle**

Find the L8.7 router code block (around line 120-148 per the L8.7 commit). Replace the simple `display = ''` / `display = 'none'` with a two-tick opacity flip:

```javascript
      // M10 — fade outgoing panels.
      var contentPanels = document.querySelectorAll('#main-content .content-panel');
      for (var i = 0; i < contentPanels.length; i++) {
        var p = contentPanels[i];
        p.classList.remove('active');
        p.style.opacity = '0';
        // Wait for transition end, then hide.
        (function (panel) {
          setTimeout(function () {
            if (!panel.classList.contains('active')) {
              panel.style.display = 'none';
            }
          }, 180);  // matches --motion-base
        })(p);
      }

      // ...mounting logic unchanged...

      var targetContent = document.querySelector('#main-content .area-' + areaId);
      if (targetContent) {
        targetContent.classList.add('active');
        targetContent.style.display = '';
        targetContent.style.opacity = '0';
        // Force reflow so the opacity 0 takes effect before flipping to 1.
        targetContent.offsetHeight; // eslint-disable-line no-unused-expressions
        targetContent.style.opacity = '1';
      }
```

- [ ] **Step 2: Smoke verify**

Switch between Chat / Studio / Admin via the topnav. Confirm a 180ms fade between areas. Reduce-motion preference should bypass (add a `prefers-reduced-motion` JS check before the transition path — see Task 6.7).

- [ ] **Step 3: Update the L8.7 regression test**

The test `test_cross_area_switch_unmounts_previous_area` asserts that after a switch, the outgoing panel is `not_to_be_visible()`. With the fade, there's a 180ms window where it's still in the DOM. The test should wait for the fade to complete:

```python
# In tests/browser/test_flow_hash_routing.py — modify the test added in L8.7
page.wait_for_timeout(220)  # wait past --motion-base 180ms + buffer
expect(studio_panel).not_to_be_visible()
```

- [ ] **Step 4: Verify the test still passes**

Run: `docker exec the-one pytest -m browser tests/browser/test_flow_hash_routing.py::test_cross_area_switch_unmounts_previous_area -v --tb=short`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add the_one/interfaces/web/static/js/app.js \
        tests/browser/test_flow_hash_routing.py
git commit -m "L6.2: two-tick opacity flip — 180ms area fade transitions"
```

---

### Task 6.3: lerp-counter.js + wire to telemetry-store

**Files:**
- Create: `the_one/interfaces/web/static/js/utils/lerp-counter.js`
- Modify: `the_one/interfaces/web/static/js/topnav.js`
- Modify: `the_one/interfaces/web/static/index.html`
- Test: `tests/browser/test_lerp_counter.py`

- [ ] **Step 1: Write failing test**

Create `tests/browser/test_lerp_counter.py`:

```python
from __future__ import annotations

import pytest
from playwright.sync_api import Page


@pytest.mark.browser
def test_lerp_counter_animates_value_change(app_clean: str, page: Page) -> None:
    """Counter element receives intermediate values during the lerp window."""
    page.goto(app_clean)
    result = page.evaluate(
        """async () => {
          const node = document.createElement('div');
          node.textContent = '0';
          document.body.appendChild(node);
          const observed = [];
          const obs = new MutationObserver(() => observed.push(node.textContent));
          obs.observe(node, { characterData: true, childList: true, subtree: true });
          window.LerpCounter.animate(node, 100, 240);
          await new Promise(r => setTimeout(r, 280));
          obs.disconnect();
          return { final: node.textContent, intermediates: observed.length };
        }"""
    )
    assert result["final"] == "100"
    assert result["intermediates"] > 1  # at least a couple of intermediate frames


@pytest.mark.browser
def test_lerp_counter_respects_reduced_motion(app_clean: str, page: Page) -> None:
    """With prefers-reduced-motion, the counter jumps instantly."""
    page.emulate_media(reduced_motion="reduce")
    page.goto(app_clean)
    result = page.evaluate(
        """async () => {
          const node = document.createElement('div');
          node.textContent = '0';
          document.body.appendChild(node);
          window.LerpCounter.animate(node, 100, 240);
          await new Promise(r => setTimeout(r, 20));
          return node.textContent;
        }"""
    )
    assert result == "100"
```

- [ ] **Step 2: Run failing test**

Run: `docker exec the-one pytest -m browser tests/browser/test_lerp_counter.py -v --tb=short`

Expected: 2 FAIL.

- [ ] **Step 3: Create the utility**

Create `the_one/interfaces/web/static/js/utils/lerp-counter.js`:

```javascript
// M10 — smooth integer counter animation. Honors prefers-reduced-motion.
// Cap update frequency at 4Hz so rapid telemetry changes don't stutter.
(function () {
  'use strict';

  var MIN_INTERVAL_MS = 250;
  var inflight = new WeakMap();  // node → { stop, lastUpdate }

  function reducedMotion() {
    return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  }

  function animate(node, target, durationMs) {
    if (!node) return;
    var startVal = parseInt(node.textContent, 10);
    if (isNaN(startVal)) startVal = 0;
    var endVal = parseInt(target, 10);
    if (isNaN(endVal)) {
      // Non-numeric target (e.g., '—'); jump.
      node.textContent = String(target);
      return;
    }
    if (reducedMotion()) {
      node.textContent = String(endVal);
      return;
    }
    if (startVal === endVal) return;

    // Cancel any in-flight animation on this node.
    var existing = inflight.get(node);
    if (existing) existing.stop = true;

    var startMs = performance.now();
    var d = durationMs || 240;
    var token = { stop: false, lastUpdate: 0 };
    inflight.set(node, token);

    function tick(now) {
      if (token.stop) return;
      var t = Math.min(1, (now - startMs) / d);
      var eased = 1 - Math.pow(1 - t, 3);  // easeOutCubic
      var v = Math.round(startVal + (endVal - startVal) * eased);
      var sinceLast = now - token.lastUpdate;
      if (sinceLast >= MIN_INTERVAL_MS || t === 1) {
        node.textContent = String(v);
        token.lastUpdate = now;
      }
      if (t < 1) {
        requestAnimationFrame(tick);
      } else {
        // Ensure final value lands.
        node.textContent = String(endVal);
        inflight.delete(node);
      }
    }
    requestAnimationFrame(tick);
  }

  window.LerpCounter = { animate: animate };
})();
```

- [ ] **Step 4: Wire telemetry-store changes through the lerp**

In `topnav.js::subscribeForRerender`, when a chip's strong-tag updates and the new value is numeric, run the lerp instead of replacing innerHTML:

```javascript
function subscribeForRerender() {
  var lastStore = window.TelemetryStore.get();
  window.TelemetryStore.subscribe(function (store) {
    var topnav = document.getElementById('app-topnav');
    if (!topnav) return;
    var strip = topnav.querySelector('.tele-strip');
    if (!strip) return;
    var active = topnav.querySelector('.navseg.active');
    var areaId = active ? active.dataset.area : 'chat';
    var chipKeys = AREA_CHIPS[areaId] || AREA_CHIPS.chat;

    // For each chip, find its existing <strong> node and lerp the value
    // if both old and new are numeric. Otherwise re-render the chip.
    chipKeys.forEach(function (k) {
      var label = CHIP_LABELS[k];
      var chipEl = strip.querySelector('.tele-chip:has(strong)');
      // … select by chip key — see Step 5 for selector hardening.
      var nextVal = (k === 'ws') ? (store.ws_rtt_ms === '—' ? '—' : store.ws_rtt_ms + 'ms') : store[k];
      var prevVal = (k === 'ws') ? (lastStore.ws_rtt_ms === '—' ? '—' : lastStore.ws_rtt_ms + 'ms') : lastStore[k];
      if (chipEl && typeof nextVal === 'number' && typeof prevVal === 'number') {
        var strong = chipEl.querySelector('strong');
        if (strong) window.LerpCounter.animate(strong, nextVal, 240);
      } else {
        // fall back to full re-render for this chip
        // (selector hardening required — see Step 5)
      }
    });

    lastStore = store;
  });
}
```

- [ ] **Step 5: Harden chip selectors**

For Step 4 to work, chips need addressable selectors. In `topnav.js::renderChip`, add `data-chip` attribute:

```javascript
function renderChip(key, store) {
  // ...
  if (key === 'ws') {
    // ...
    return (
      '<span class="tele-chip" data-chip="ws"><span class="stat-dot ' + dotClass + '"></span>' +
      'WS<strong>' + rtt + '</strong></span>'
    );
  }
  return '<span class="tele-chip" data-chip="' + key + '">' + CHIP_LABELS[key] + '<strong>' + store[key] + '</strong></span>';
}
```

And in `subscribeForRerender`, select via `strip.querySelector('.tele-chip[data-chip="' + k + '"]')`.

- [ ] **Step 6: Wire lerp-counter.js into index.html**

Add `<script src="/static/js/utils/lerp-counter.js"></script>` AFTER `telemetry-store.js` and BEFORE `topnav.js`.

- [ ] **Step 7: Run tests — verify pass**

Run: `make rebuild && docker exec the-one pytest -m browser tests/browser/test_lerp_counter.py -v --tb=short`

Expected: 2 PASS.

- [ ] **Step 8: Commit**

```bash
git add the_one/interfaces/web/static/js/utils/lerp-counter.js \
        the_one/interfaces/web/static/js/topnav.js \
        the_one/interfaces/web/static/index.html \
        tests/browser/test_lerp_counter.py
git commit -m "L6.3: lerp-counter — smooth telemetry chip value transitions"
```

---

### Task 6.4: WebSocket ping/pong — server side

**Files:**
- Modify: `the_one/interfaces/web/websocket.py`
- Test: `tests/test_websocket_ping.py`

- [ ] **Step 1: Find the WS message handler**

Run: `grep -n "async def\|websocket\|message_type\|ws.receive" the_one/interfaces/web/websocket.py | head -15`

Locate the function that dispatches incoming WS messages by type.

- [ ] **Step 2: Write failing test**

Create `tests/test_websocket_ping.py`:

```python
"""Test the WS ping/pong RTT primitive."""

from __future__ import annotations

import pytest
import websockets
import json
import asyncio


@pytest.mark.asyncio
async def test_ws_ping_returns_pong(app_running_url):
    """`{"type":"ping"}` triggers an immediate `{"type":"pong"}`."""
    ws_url = app_running_url.replace("http", "ws") + "/ws"
    async with websockets.connect(ws_url) as ws:
        await ws.send(json.dumps({"type": "ping"}))
        msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
        data = json.loads(msg)
        assert data["type"] == "pong"
```

`app_running_url` is an existing fixture or analogous fixture in the test suite — if not present, use the `app_clean` URL via httpx-style setup.

- [ ] **Step 3: Run failing test**

Run: `docker exec the-one pytest tests/test_websocket_ping.py -v --tb=short`

Expected: FAIL — pong not returned.

- [ ] **Step 4: Add the ping handler**

In `websocket.py`, in the message-dispatch function, add a branch:

```python
if data.get("type") == "ping":
    await websocket.send_json({"type": "pong"})
    continue  # or return — match the function's flow
```

Place it near the top of the dispatch so it short-circuits without further parsing.

- [ ] **Step 5: Run test — verify pass**

Run: `docker exec the-one pytest tests/test_websocket_ping.py -v --tb=short`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add the_one/interfaces/web/websocket.py tests/test_websocket_ping.py
git commit -m "L6.4: WS ping/pong handler — server side"
```

---

### Task 6.5: WebSocket ping client + RTT measurement

**Files:**
- Modify: `the_one/interfaces/web/static/js/websocket.js` (or whichever module owns the WS client)

- [ ] **Step 1: Find the WS client module**

Run: `grep -rn "new WebSocket\|WebSocket(" the_one/interfaces/web/static/js/ | head -5`

Locate the WS client class/module.

- [ ] **Step 2: Add ping interval + RTT measurement**

In the WS module, add at the connection-open lifecycle:

```javascript
function startPinging(ws) {
  var pendingPing = null;
  var pingInterval = setInterval(function () {
    if (ws.readyState !== WebSocket.OPEN) return;
    pendingPing = performance.now();
    ws.send(JSON.stringify({ type: 'ping' }));
    // If no pong within 5s, mark stale.
    setTimeout(function () {
      if (pendingPing != null && performance.now() - pendingPing > 5000) {
        if (window.TelemetryStore) {
          window.TelemetryStore.set({ ws_state: 'stale' });
        }
      }
    }, 5100);
  }, 10000);
  ws.addEventListener('close', function () { clearInterval(pingInterval); });

  return function onMessage(data) {
    if (data && data.type === 'pong' && pendingPing != null) {
      var rtt = Math.round(performance.now() - pendingPing);
      pendingPing = null;
      if (window.TelemetryStore) {
        // Exponential moving average (alpha 0.3).
        var prev = window.TelemetryStore.get().ws_rtt_ms;
        var smoothed = (typeof prev === 'number') ? Math.round(0.3 * rtt + 0.7 * prev) : rtt;
        window.TelemetryStore.set({ ws_rtt_ms: smoothed, ws_state: 'ok' });
      }
      return true;  // signal: pong consumed, don't dispatch further
    }
    return false;
  };
}
```

Wire `startPinging(ws)` into the existing `onopen` handler. Plug the returned `onMessage` callback into the existing WS message-dispatch logic so pongs short-circuit before reaching downstream handlers:

```javascript
// existing onmessage handler — adapt:
ws.addEventListener('message', function (ev) {
  var data;
  try { data = JSON.parse(ev.data); } catch (e) { return; }
  if (pongHandler && pongHandler(data)) return;  // pong consumed
  // ...existing dispatch...
});
```

- [ ] **Step 3: On WS disconnect, mark store**

In the existing `onclose` handler, add:

```javascript
if (window.TelemetryStore) {
  window.TelemetryStore.set({ ws_rtt_ms: '—', ws_state: 'down' });
}
```

- [ ] **Step 4: Smoke verify**

`make rebuild` → load the app. After ~10s, the WS chip should display a numeric RTT (e.g., `WS 14ms`) with an `.ok` (green) status dot. Disable network in devtools; the chip flips to `WS · OFFLINE` or `—` with `.err` (red).

- [ ] **Step 5: Commit**

```bash
git add the_one/interfaces/web/static/js/websocket.js
git commit -m "L6.5: client-side WS ping + RTT measurement (EMA smoothed)"
```

---

### Task 6.6: prefers-reduced-motion audit

**Files:**
- Modify: `the_one/interfaces/web/static/css/base.css` (or `tokens.css`)
- Test: `tests/test_prefers_reduced_motion.py`

- [ ] **Step 1: Verify the existing media query**

Run: `grep -n "prefers-reduced-motion" the_one/interfaces/web/static/css/base.css the_one/interfaces/web/static/css/tokens.css the_one/interfaces/web/static/css/components.css 2>&1`

If a query already exists, confirm it covers all `*` selectors. If not, add to `base.css`:

```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
  }
}
```

- [ ] **Step 2: Write a contract test**

Create `tests/test_prefers_reduced_motion.py`:

```python
"""Asserts the prefers-reduced-motion safeguard is present in base CSS."""

from __future__ import annotations

from pathlib import Path
import re


def test_prefers_reduced_motion_query_exists():
    css_dir = Path("the_one/interfaces/web/static/css")
    found = False
    for path in css_dir.glob("*.css"):
        content = path.read_text()
        if "prefers-reduced-motion" in content and re.search(
            r"\*, \*::before, \*::after",
            content,
        ):
            found = True
            break
    assert found, "No prefers-reduced-motion universal-selector guard found in CSS"
```

- [ ] **Step 3: Run test — verify pass**

Run: `docker exec the-one pytest tests/test_prefers_reduced_motion.py -v --tb=short`

Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add the_one/interfaces/web/static/css/base.css \
        tests/test_prefers_reduced_motion.py
git commit -m "L6.6: prefers-reduced-motion universal guard + contract test"
```

---

### Task 6.7: Reduced-motion-aware router fade

**Files:**
- Modify: `the_one/interfaces/web/static/js/app.js`

- [ ] **Step 1: Gate the L6.2 fade behind a runtime check**

Modify the area-switch block from Task 6.2:

```javascript
      var reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

      var contentPanels = document.querySelectorAll('#main-content .content-panel');
      for (var i = 0; i < contentPanels.length; i++) {
        var p = contentPanels[i];
        p.classList.remove('active');
        if (reducedMotion) {
          p.style.display = 'none';
          p.style.opacity = '';
        } else {
          p.style.opacity = '0';
          (function (panel) {
            setTimeout(function () {
              if (!panel.classList.contains('active')) {
                panel.style.display = 'none';
              }
            }, 180);
          })(p);
        }
      }

      // ...mounting...

      if (targetContent) {
        targetContent.classList.add('active');
        targetContent.style.display = '';
        if (reducedMotion) {
          targetContent.style.opacity = '';
        } else {
          targetContent.style.opacity = '0';
          targetContent.offsetHeight;
          targetContent.style.opacity = '1';
        }
      }
```

- [ ] **Step 2: Smoke verify with the chrome devtools media-emulation**

DevTools → Rendering panel → "Emulate CSS media feature prefers-reduced-motion" → "reduce". Switch areas. No fade — instant snap. Without the override, fade should still be visible.

- [ ] **Step 3: Commit**

```bash
git add the_one/interfaces/web/static/js/app.js
git commit -m "L6.7: gate area-fade transition on prefers-reduced-motion"
```

---

### Task 6.8: Final visual snapshot regeneration

**Files:**
- Modify: `tests/browser/__snapshots__/*.png`

- [ ] **Step 1: Update all baselines**

Run: `docker exec the-one pytest -m browser tests/browser/test_visual_snapshots.py --snapshot-update`

The L5 working-state changes affect Chat and Studio populated snapshots. Regenerate everything to reflect the final M10 state.

- [ ] **Step 2: Commit**

```bash
git add tests/browser/__snapshots__/
git commit -m "L6.8: final visual snapshot baselines for M10 complete state"
```

---

## Self-Review Checklist

After all six phases land, re-run:

- [ ] All unit tests: `docker exec the-one pytest tests/ --ignore=tests/browser -q --tb=short` → 1500+ passed, only the bwrap-on-Mac integration tests deselected.
- [ ] All browser tests (in CI env with Playwright binaries): `pytest -m browser tests/browser/ -q --tb=short` → all pass.
- [ ] Linting: `make lint` → clean.
- [ ] WCAG audit: `docker exec the-one pytest tests/test_design_tokens_a11y.py -v --tb=short` → all pairs pass.
- [ ] Cross-area routing regression: `pytest -m browser tests/browser/test_flow_hash_routing.py -v --tb=short`.
- [ ] Visual snapshots: `pytest -m browser tests/browser/test_visual_snapshots.py -v --tb=short` → no unexpected diffs.

If any test fails, fix in-place and amend the relevant leg commit OR add a small follow-up commit before merging.

---

## Plan Done. Saved to `docs/superpowers/plans/2026-05-14-mission-10-instrument.md`.

Two execution options:

1. **Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** — Execute tasks in this session using `executing-plans`, batch execution with checkpoints.

Which approach?
