# Holograph Chat Polish — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the three open issues from the 2026-05-15 walk-through of `localhost:8484/#chat`: fix the regressed topnav layout (L7), wire a real ⌘K command palette (L8), and wire a small user menu behind the avatar (L9).

**Architecture:** All work is on the Holograph UI surface — hand-rolled vanilla JS, no bundler, no framework. New components live under `the_one/interfaces/web/static/js/components/` as IIFEs that expose themselves on `window.App.*` (matches `theme.js`, `dialog.js`, `welcome.js`). New CSS goes into `components.css` under `@layer components`. Tests follow the project's three-tier convention: unit (pytest), browser (Playwright + `pytest.mark.browser`), and visual snapshots (`pytest.mark.pixel`).

**Tech Stack:** Python 3.11, FastAPI, vanilla JS (ES5-ish, no transpile), CSS custom properties (cascade layers), Playwright for browser tests, pytest 9.

**Spec:** `docs/superpowers/specs/2026-05-15-holograph-chat-polish-design.md` (commit `d19d55b`).

**Docker note:** This branch's dev loop runs the app inside a container that serves image-baked code. After editing any file under `the_one/`, run `make rebuild` for the change to be visible at `localhost:8484`. Tests run inside the container via `docker exec the-one pytest …`. The test suite spawns its own uvicorn subprocess on a random port, so tests pass against fresh code even if the served daemon is stale; `make verify-serving` catches that.

---

## File Structure Map

**L7 — Topnav layout + Holograph polish**
- Modify: `the_one/interfaces/web/static/js/topnav.js` (rename `spacer` → `topnav-spacer`; emit `topnav:rerender` event)
- Modify: `the_one/interfaces/web/static/css/components.css` (add `.topnav-spacer`, `.search-wrap`, `.search-input`, `.search-kbd`, `.visually-hidden`, `.tele-strip { flex-shrink: 0 }`; remove orphan `.search`, `.kbd`, `.nav-right`)
- Modify: `the_one/interfaces/web/static/css/chat.css` (composer responsive fix; `.msg-row.system` width constraint)
- Modify: `the_one/interfaces/web/static/js/areas/admin/providers-grid.js` (swap New Provider button to `.btn-primary`)
- Modify: `the_one/interfaces/web/static/js/areas/chat.js` (empty-sessions-list guidance row when no agent has a provider)
- Test: `tests/browser/test_topnav_layout.py` (new — contract test: `.topnav-spacer` resolves `flex-grow: 1`)
- Test: `tests/browser/test_visual_snapshots.py` (regenerate baselines for `topnav-*`, `chat-empty-*`, `admin-providers-empty-*`, plus new `composer-1024-*`)

**L8 — Command palette**
- Create: `the_one/interfaces/web/static/js/components/command-fuzzy.js`
- Create: `the_one/interfaces/web/static/js/components/command-catalog.js`
- Create: `the_one/interfaces/web/static/js/components/command-palette.js`
- Modify: `the_one/interfaces/web/static/css/components.css` (palette overlay + card styling)
- Modify: `the_one/interfaces/web/static/index.html` (script tags for new files, before `app.js`)
- Modify: `the_one/interfaces/web/static/js/app.js` (global `⌘K` keydown listener)
- Modify: `the_one/interfaces/web/static/js/topnav.js` (`<input>` → `<button>` for `.search-input`)
- Test: `tests/test_command_fuzzy.py` (new — pure-JS unit test executed via Playwright `page.evaluate`)
- Test: `tests/browser/test_command_palette.py` (new — open, type, navigate, invoke)
- Test: `tests/browser/test_visual_snapshots.py` (new `palette-open-*` baselines)

**L9 — User menu**
- Create: `the_one/interfaces/web/static/js/components/user-menu.js`
- Modify: `the_one/interfaces/web/static/css/components.css` (menu popover styling)
- Modify: `the_one/interfaces/web/static/index.html` (script tag)
- Modify: `the_one/interfaces/web/static/js/topnav.js` (avatar click → `App.userMenu.toggle`)
- Test: `tests/browser/test_user_menu.py` (new)
- Test: `tests/browser/test_visual_snapshots.py` (new `user-menu-open-*` baselines)

---

# Flight L7 — Topnav Layout + Holograph Polish

## Task 1: Add missing topnav CSS rules

**Files:**
- Modify: `the_one/interfaces/web/static/css/components.css:138-214`

- [ ] **Step 1: Read the current state of the topnav block**

Open `the_one/interfaces/web/static/css/components.css`. Lines 138-214 contain the current `.tele-strip`, `.search`, `.kbd`, `.nav-right`, `.avatar` rules. The new rules will replace the orphans and add the missing ones.

- [ ] **Step 2: Replace the topnav block**

Replace lines 138-214 with this block (preserves `.tele-strip`, `.tele-chip`, `.avatar`; removes orphans `.search`, `.kbd`, `.nav-right`; adds `.topnav-spacer`, `.search-wrap`, `.search-input`, `.search-kbd`, `.visually-hidden`):

```css
  /* M10 — telemetry chip strip in topnav */
  .tele-strip {
    display: flex;
    gap: 14px;
    align-items: center;
    flex-shrink: 0;
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

  /* M10 — flex spacer between nav-segments and right cluster */
  .topnav-spacer { flex: 1; }

  /* ── Search ──────────────────────────────────────────────────────────── */

  .search-wrap {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 10px;
    width: 240px;
    background: var(--surface);
    border: 1px solid var(--hairline);
    border-radius: 8px;
    color: var(--fg-mute);
    font-size: 12.5px;
    transition: border-color var(--t), box-shadow var(--t);
    margin-left: 16px;
  }
  .search-wrap:hover { border-color: var(--hairline-strong); }
  .search-wrap:focus-within {
    border-color: var(--accent);
    box-shadow: 0 0 0 3px var(--accent-soft);
  }

  .search-input {
    flex: 1;
    min-width: 0;
    background: transparent;
    border: 0;
    outline: 0;
    color: var(--fg);
    font: inherit;
    text-align: left;
    cursor: pointer;
    padding: 0;
  }
  .search-input::placeholder { color: var(--fg-mute); }

  .search-kbd {
    flex-shrink: 0;
    font-family: 'JetBrains Mono', monospace;
    font-size: 10.5px;
    background: var(--surface-2);
    color: var(--fg-faint);
    padding: 1px 5px;
    border-radius: 4px;
  }

  /* ── Visually hidden (a11y) ─────────────────────────────────────────── */

  .visually-hidden {
    position: absolute;
    width: 1px;
    height: 1px;
    padding: 0;
    margin: -1px;
    overflow: hidden;
    clip: rect(0, 0, 0, 0);
    white-space: nowrap;
    border: 0;
  }

  /* ── Avatar ──────────────────────────────────────────────────────────── */

  .avatar {
    width: 28px;
    height: 28px;
    border-radius: 50%;
    background: var(--avatar-bg);
    color: var(--avatar-fg);
    display: grid;
    place-items: center;
    font-size: 11.5px;
    font-weight: 600;
    cursor: pointer;
    border: 0;
    margin-left: 12px;
    transition: box-shadow var(--t);
  }

  .avatar:hover { box-shadow: 0 0 0 3px var(--hover-bg); }
  .avatar:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }
```

- [ ] **Step 3: Verify the file parses**

Run: `python -c "from pathlib import Path; t = Path('the_one/interfaces/web/static/css/components.css').read_text(); assert '.topnav-spacer' in t; assert '.search-wrap' in t; assert '.nav-right' not in t; print('ok')"`
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add the_one/interfaces/web/static/css/components.css
git commit -m "L7.1: topnav CSS — .topnav-spacer + .search-wrap/-input/-kbd; retire orphans"
```

---

## Task 2: Rename topnav spacer + add lifecycle event

**Files:**
- Modify: `the_one/interfaces/web/static/js/topnav.js:64, 74-80`

- [ ] **Step 1: Rename the spacer class in `buildTopnavHtml`**

In `the_one/interfaces/web/static/js/topnav.js` find:

```js
'<div class="spacer"></div>' +
```

Replace with:

```js
'<div class="topnav-spacer"></div>' +
```

- [ ] **Step 2: Emit `topnav:rerender` event at the tail of `renderTopnav`**

Find:

```js
  function renderTopnav(activeArea) {
    var topnav = document.getElementById('app-topnav');
    if (!topnav) return;
    // Replace contents: clear, then insertAdjacentHTML to rebuild.
    while (topnav.firstChild) topnav.removeChild(topnav.firstChild);
    topnav.insertAdjacentHTML('beforeend', buildTopnavHtml(activeArea));
  }
```

Replace with:

```js
  function renderTopnav(activeArea) {
    var topnav = document.getElementById('app-topnav');
    if (!topnav) return;
    // Replace contents: clear, then insertAdjacentHTML to rebuild.
    while (topnav.firstChild) topnav.removeChild(topnav.firstChild);
    topnav.insertAdjacentHTML('beforeend', buildTopnavHtml(activeArea));
    // L7.8 lifecycle: notify popovers anchored to topnav elements that
    // their anchors may have been replaced. Listeners: L8 command palette,
    // L9 user menu. No-op cost when no listeners are attached.
    document.dispatchEvent(new CustomEvent('topnav:rerender'));
  }
```

- [ ] **Step 3: Rebuild + verify in the browser**

Run: `make rebuild`
Then open `http://localhost:8484/#chat` and run in DevTools console:

```js
getComputedStyle(document.querySelector('.topnav-spacer')).flexGrow
```

Expected: `"1"`

Then in console:

```js
let fired = false;
document.addEventListener('topnav:rerender', () => fired = true, { once: true });
location.hash = '#studio';
setTimeout(() => console.log('fired?', fired), 200);
```

Expected: `fired? true`

- [ ] **Step 4: Commit**

```bash
git add the_one/interfaces/web/static/js/topnav.js
git commit -m "L7.2: rename spacer → topnav-spacer + emit topnav:rerender on area switch"
```

---

## Task 3: Contract test — `.topnav-spacer` resolves `flex-grow: 1`

**Files:**
- Create: `tests/browser/test_topnav_layout.py`

- [ ] **Step 1: Write the failing test**

Create `tests/browser/test_topnav_layout.py`:

```python
"""L7 — topnav layout regression guards.

These are cheap contract tests that catch the M10 regression where
``.topnav-spacer`` had no rule and the right cluster collapsed against
the search. They run on the dark theme only (the rule is theme-agnostic).
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.browser
def test_topnav_spacer_grows(app_clean: str, page: Page) -> None:
    page.goto(app_clean)
    expect(page.locator(".topnav-spacer")).to_be_visible()
    flex_grow = page.evaluate(
        "() => getComputedStyle(document.querySelector('.topnav-spacer')).flexGrow"
    )
    assert flex_grow == "1", f"topnav-spacer flex-grow regressed: {flex_grow!r}"


@pytest.mark.browser
def test_topnav_search_wrap_has_width(app_clean: str, page: Page) -> None:
    page.goto(app_clean)
    width = page.evaluate(
        "() => document.querySelector('.search-wrap').getBoundingClientRect().width"
    )
    # 240 from the CSS rule; allow 4px tolerance for padding/border.
    assert 236 <= width <= 248, f"search-wrap width regressed: {width}"


@pytest.mark.browser
def test_topnav_event_fires_on_area_switch(app_clean: str, page: Page) -> None:
    page.goto(app_clean)
    page.evaluate(
        """() => {
            window.__rerenderCount = 0;
            document.addEventListener('topnav:rerender', () => window.__rerenderCount++);
        }"""
    )
    page.locator('button[data-area="studio"]').click()
    page.wait_for_function("() => window.__rerenderCount >= 1", timeout=2000)
    count = page.evaluate("() => window.__rerenderCount")
    assert count >= 1, f"topnav:rerender did not fire on area switch (count={count})"
```

- [ ] **Step 2: Run the test (it should pass — Tasks 1 + 2 already shipped the changes)**

Run: `docker exec the-one pytest tests/browser/test_topnav_layout.py -x -m browser -v`
Expected: 3 passed.

If it fails, the most likely cause is `make rebuild` not having been run after Tasks 1+2. Run `make rebuild` and retry.

- [ ] **Step 3: Commit**

```bash
git add tests/browser/test_topnav_layout.py
git commit -m "L7.3: contract tests — .topnav-spacer + .search-wrap width + topnav:rerender"
```

---

## Task 4: Responsive composer fix at 1024px

**Files:**
- Modify: `the_one/interfaces/web/static/css/chat.css` (composer block)

- [ ] **Step 1: Find the current composer rules**

Run: `grep -nE '\.composer|composer-meta|chat-send-btn' the_one/interfaces/web/static/css/chat.css | head -10`

Note the line numbers of the `.composer` rule and the trailing meta/send group. The composer is a flex row with `[textarea]` flexing to fill and a trailing meta + send button cluster.

- [ ] **Step 2: Add the responsive-fix rules**

Append to the `.composer` rule (find the existing block; add `min-width: 0` to the textarea wrapper and `flex-shrink: 0` to the trailing meta cluster). Add at the end of `chat.css` (inside the `@layer areas { … }` block, just before its closing `}`):

```css
  /* L7.4 — composer responsive fix. At <~1100px the textarea was growing
     past the row's width budget and pushing the Send button off-screen.
     Pin trailing meta + send group, let the textarea container shrink. */
  .composer-input-wrap {
    min-width: 0;
    flex: 1;
  }
  .composer-meta,
  .composer-actions {
    flex-shrink: 0;
  }
```

If the existing markup uses different class names (verify with `grep -n "composer-" the_one/interfaces/web/static/js/areas/chat.js`), substitute the matching class names.

- [ ] **Step 3: Verify at 1024×768**

Run: `make rebuild`
Then in agent-browser:

```bash
agent-browser --profile ~/.agent-browser/profiles/claude close
agent-browser --profile ~/.agent-browser/profiles/claude open http://localhost:8484/#chat
agent-browser set viewport 1024 768
agent-browser screenshot /tmp/composer-1024-after.png
```

Open `/tmp/composer-1024-after.png` — the Send button must be visible at the right edge of the composer row.

- [ ] **Step 4: Commit**

```bash
git add the_one/interfaces/web/static/css/chat.css
git commit -m "L7.4: composer — min-width:0 textarea + no-shrink send group (fixes 1024px clip)"
```

---

## Task 5: System-error message bubble — constrain width

**Files:**
- Modify: `the_one/interfaces/web/static/css/chat.css`

- [ ] **Step 1: Find existing system-row styling**

Run: `grep -nE 'msg-row\.system|msg-text|\.system' the_one/interfaces/web/static/css/chat.css | head -10`

Note whether `.msg-row.system` is already styled. The walk-through showed the row spans full width with no max-width.

- [ ] **Step 2: Add or update the system-row rule**

Add to `chat.css` inside the `@layer areas { … }` block:

```css
  /* L7.5 — system messages share the agent-message column geometry so
     error rows like "Cannot start chat: …" don't span the full thread
     width. Mirrors .msg-body { max-width: 720px } at chat.css:206. */
  .msg-row.system {
    display: flex;
    justify-content: flex-start;
  }
  .msg-row.system .msg-text {
    max-width: 720px;
    color: var(--fg-mute);
  }
```

If `.msg-row.system` already has a rule, edit it in place — add the `max-width` and `justify-content` properties.

- [ ] **Step 3: Verify**

`make rebuild`. Open `#chat`, send a message while no provider is configured — the system error should now align to the left rail and wrap within ~720px.

- [ ] **Step 4: Commit**

```bash
git add the_one/interfaces/web/static/css/chat.css
git commit -m "L7.5: msg-row.system — max-width 720px + left-align to agent column"
```

---

## Task 6: Admin "New Provider" button — apply `.btn-primary`

**Files:**
- Modify: `the_one/interfaces/web/static/js/areas/admin/providers-grid.js`

- [ ] **Step 1: Locate the New Provider button markup**

Run: `grep -nE 'New Provider|new-provider-btn' the_one/interfaces/web/static/js/areas/admin/providers-grid.js | head -5`

- [ ] **Step 2: Add the `btn-primary` class**

In the line that renders the New Provider button, ensure the className includes `btn-primary`. Example: if the current line reads

```js
'<button class="new-provider-btn" data-action="new-provider">+ New Provider</button>'
```

change it to

```js
'<button class="btn-primary new-provider-btn" data-action="new-provider">+ New Provider</button>'
```

If the actual class names differ, keep the existing ones and add `btn-primary` as the first class so token rules apply first.

- [ ] **Step 3: Verify `.btn-primary` exists in CSS**

Run: `grep -nE '\.btn-primary' the_one/interfaces/web/static/css/*.css | head`
Expected: at least one rule. If `.btn-primary` is missing, abort this task and reopen the spec — the M10 button-language assumption was wrong.

- [ ] **Step 4: Visual verify**

`make rebuild`. Open `#admin/providers` — the "+ New Provider" button now uses the accent-tinted button styling (matches the "Go to providers →" CTA on the chat empty state).

- [ ] **Step 5: Commit**

```bash
git add the_one/interfaces/web/static/js/areas/admin/providers-grid.js
git commit -m "L7.6: new-provider button — apply .btn-primary instead of UA default"
```

---

## Task 7: New-session empty-state guidance

**Files:**
- Modify: `the_one/interfaces/web/static/js/areas/chat.js`

- [ ] **Step 1: Find the sessions-list render**

Run: `grep -nE 'sessions-list|sessions-pane|renderSessions' the_one/interfaces/web/static/js/areas/chat.js | head -5`

Find the function that renders the sessions list. The empty case (no sessions) currently produces nothing. We add an inline guidance row when `!hasProvider || !hasAgent`.

- [ ] **Step 2: Add the guidance row**

In the sessions-list render function, where it handles the empty case, insert this branch. Find the existing "no sessions" empty render or the line right after the list-container creation, then add:

```js
    // L7.7 — when prerequisites are missing, surface why the + button
    // can't yet create a session. setupState is the same one used by
    // chat/welcome.js (App.config + agents/providers fetches).
    if (sessions.length === 0 && (!setupState.hasProviders || !setupState.hasAgents)) {
      var hint = document.createElement('div');
      hint.className = 'sessions-empty-hint';
      var line = document.createElement('p');
      line.className = 'sessions-empty-hint-text';
      line.textContent = !setupState.hasProviders
        ? 'Add a provider to start a session.'
        : 'Create an agent to start a session.';
      hint.appendChild(line);
      var link = document.createElement('a');
      link.href = !setupState.hasProviders ? '#admin/providers' : '#studio/agents';
      link.className = 'sessions-empty-hint-link';
      link.textContent = !setupState.hasProviders
        ? 'Go to providers →'
        : 'Go to agents →';
      hint.appendChild(link);
      listEl.appendChild(hint);
      return;
    }
```

The exact variable names (`sessions`, `setupState`, `listEl`) need to match what the existing function uses — substitute the local names.

- [ ] **Step 3: Add minimal CSS for the hint**

In `the_one/interfaces/web/static/css/chat.css`, inside `@layer areas`, add:

```css
  .sessions-empty-hint {
    padding: 12px 14px;
    background: var(--surface);
    border: 1px dashed var(--hairline);
    border-radius: 10px;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .sessions-empty-hint-text {
    margin: 0;
    font-size: 12px;
    color: var(--fg-mute);
  }
  .sessions-empty-hint-link {
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    color: var(--accent);
    text-decoration: none;
  }
  .sessions-empty-hint-link:hover { text-decoration: underline; }
```

- [ ] **Step 4: Verify**

`make rebuild`. Open `#chat` with no providers configured. The sessions sidebar should show the hint row with a "Go to providers →" link.

- [ ] **Step 5: Commit**

```bash
git add the_one/interfaces/web/static/js/areas/chat.js the_one/interfaces/web/static/css/chat.css
git commit -m "L7.7: sessions sidebar empty hint when no provider/agent exists"
```

---

## Task 8: Regenerate visual snapshot baselines

**Files:**
- Modify: `tests/browser/__snapshots__/*.png` (regenerated)
- Maybe modify: `tests/browser/test_visual_snapshots.py` (add `composer-1024-*` test)

- [ ] **Step 1: Add a new composer-1024 snapshot test**

Append to `tests/browser/test_visual_snapshots.py`:

```python
@pytest.mark.pixel
@pytest.mark.parametrize("theme", ["dark", "light"])
def test_snapshot_composer_1024(app_clean: str, page: Page, theme: str) -> None:
    """L7.4 — verify composer Send button stays on-screen at 1024×768."""
    page.set_viewport_size({"width": 1024, "height": 768})
    page.goto(app_clean)
    _set_theme(page, theme)
    expect(page.locator('[data-testid="chat-send-btn"]')).to_be_visible(timeout=5000)
    _wait_for_render(page)
    _assert_screenshot(page, f"composer-1024-{theme}")
```

- [ ] **Step 2: Regenerate baselines**

Visual snapshots in this repo are committed PNGs under `tests/browser/__snapshots__/`. The L7 visual changes are intentional and require fresh baselines. Use the same regeneration pattern as L4.6 (commit `22bb380`) and L6.8 (commit `7aba793`).

Run: `docker exec the-one pytest tests/browser/test_visual_snapshots.py -x -m pixel --snapshot-update -v`
Expected: all tests pass (`--snapshot-update` writes the new PNGs).

- [ ] **Step 3: Sanity-check the new images**

Run: `git status tests/browser/__snapshots__/` — expect modified PNGs for `chat-empty-*`, `admin-empty-*` (or `admin-with-provider-*` depending on which page changed visibly), and new files `composer-1024-dark.png` / `composer-1024-light.png`.

Open one with `open tests/browser/__snapshots__/composer-1024-dark.png` and visually confirm the Send button is on-screen and the topnav cluster is no longer collapsed.

- [ ] **Step 4: Run the full pixel suite without `--snapshot-update`**

Run: `docker exec the-one pytest -x -m pixel -v`
Expected: all pass against the new baselines.

- [ ] **Step 5: Commit**

```bash
git add tests/browser/test_visual_snapshots.py tests/browser/__snapshots__/
git commit -m "L7.8: regenerate visual baselines for topnav layout fixes + composer-1024"
```

---

## Task 9: Contrast test for new search-wrap tokens

**Files:**
- Modify: `tests/test_design_tokens_a11y.py`

- [ ] **Step 1: Find the existing token-pair audit**

Run: `grep -nE 'audit_pairs|AUDIT_PAIRS|search' tests/test_design_tokens_a11y.py | head -10`

- [ ] **Step 2: Add a pair entry for `.search-input` text on `.search-wrap` background**

Locate the list of audited foreground/background pairs and add an entry for `--fg` (the search-input text) on `--surface` (the search-wrap background). If the pair `var(--fg)` on `var(--surface)` already exists in the audit (likely — it's the body text combo), no addition is necessary — confirm by grep:

```bash
grep -nE 'fg.*surface|surface.*fg' tests/test_design_tokens_a11y.py | head
```

If the pair is already covered, skip to Step 4. Otherwise add it following the existing entry shape.

- [ ] **Step 3: Run the audit**

Run: `docker exec the-one pytest tests/test_design_tokens_a11y.py -x -v`
Expected: pass.

- [ ] **Step 4: Commit (only if the file was modified)**

```bash
git add tests/test_design_tokens_a11y.py
git commit -m "L7.9: token-a11y audit — ensure search-input fg/bg combo is covered"
```

If no change was needed, skip the commit.

---

## Task 10: L7 end-to-end visual review

- [ ] **Step 1: Run the full browser + pixel suite**

Run: `docker exec the-one pytest tests/browser/ -x -m "browser or pixel" -v`
Expected: all pass.

- [ ] **Step 2: Manual smoke**

```bash
agent-browser --profile ~/.agent-browser/profiles/claude open http://localhost:8484/#chat
agent-browser set viewport 1280 800
agent-browser screenshot /tmp/L7-smoke-1280.png
agent-browser set viewport 1920 1080
agent-browser screenshot /tmp/L7-smoke-1920.png
agent-browser set viewport 1024 768
agent-browser screenshot /tmp/L7-smoke-1024.png
```

Open each PNG. Each one must show: full topnav cluster with breathing room between brand · nav-segments · spacer · tele-strip · search · avatar; no clipping of any chip's first letter; composer Send button visible.

- [ ] **Step 3: Verify the served daemon matches the rebuilt image**

Run: `make verify-serving`
Expected: pass. (Catches the stale-served-code class of bug called out in CLAUDE.md.)

L7 is done. Layout regression closed.

---

# Flight L8 — Command Palette (⌘K)

## Task 11: Fuzzy scorer module + unit test

**Files:**
- Create: `the_one/interfaces/web/static/js/components/command-fuzzy.js`
- Create: `tests/browser/test_command_fuzzy.py`

- [ ] **Step 1: Write the failing test**

Create `tests/browser/test_command_fuzzy.py`:

```python
"""L8 — command-fuzzy.js scorer. Executed via Playwright page.evaluate
because the module is plain JS with no Node entry point — running it in
the browser is the cheapest accurate way to test it.
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Page


@pytest.mark.browser
def test_command_fuzzy_scoring(app_clean: str, page: Page) -> None:
    page.goto(app_clean)

    # Sanity: the module is loaded.
    has_module = page.evaluate("() => !!(window.App && window.App.commandFuzzy)")
    assert has_module, "App.commandFuzzy not loaded — check index.html script order"

    score = page.evaluate(
        """({ q, label }) => window.App.commandFuzzy.score(q, { label })"""
        ,
        {"q": "prov", "label": "Open Providers"},
    )
    assert score >= 100, f"prefix-after-space should beat substring: {score}"

    score_sub = page.evaluate(
        """({ q, label }) => window.App.commandFuzzy.score(q, { label })"""
        ,
        {"q": "agent", "label": "Switch to agent: research"},
    )
    assert score_sub >= 50

    score_miss = page.evaluate(
        """({ q, label }) => window.App.commandFuzzy.score(q, { label })"""
        ,
        {"q": "xyzzy", "label": "Open Providers"},
    )
    assert score_miss == 0

    # Case-insensitivity.
    score_upper = page.evaluate(
        """({ q, label }) => window.App.commandFuzzy.score(q, { label })"""
        ,
        {"q": "PROV", "label": "Open Providers"},
    )
    assert score_upper >= 100

    # Missing fields don't throw.
    score_empty = page.evaluate(
        "() => window.App.commandFuzzy.score('foo', {})"
    )
    assert score_empty == 0
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `docker exec the-one pytest tests/browser/test_command_fuzzy.py -x -m browser -v`
Expected: FAIL — `App.commandFuzzy not loaded` (the module doesn't exist yet).

- [ ] **Step 3: Write the scorer module**

Create `the_one/interfaces/web/static/js/components/command-fuzzy.js`:

```js
// L8 — command palette scorer.
//
// Pure scoring function. Higher score = better match. 0 = no match.
// Scoring (case-insensitive throughout):
//   +100  query is a prefix of label, OR a prefix of any whitespace-
//         separated token in label.
//   +50   query is a substring of label.
//   +20   query is a substring of (section + keywords).
//   0     no match.
//
// Inputs:
//   q     — string user query (trimmed, possibly empty)
//   item  — { label, section?, keywords? }
(function () {
  'use strict';

  window.App = window.App || {};
  window.App.commandFuzzy = {
    score: function (q, item) {
      if (!q || !item || typeof item.label !== 'string') return 0;
      var query = String(q).toLowerCase().trim();
      if (!query) return 0;

      var label = item.label.toLowerCase();
      var section = (item.section || '').toLowerCase();
      var keywords = (item.keywords || '').toLowerCase();

      // Prefix match — label start OR any whitespace-separated token.
      if (label.indexOf(query) === 0) return 100;
      var tokens = label.split(/\s+/);
      for (var i = 0; i < tokens.length; i++) {
        if (tokens[i].indexOf(query) === 0) return 100;
      }

      if (label.indexOf(query) !== -1) return 50;
      if ((section + ' ' + keywords).indexOf(query) !== -1) return 20;
      return 0;
    }
  };
})();
```

- [ ] **Step 4: Wire it into index.html**

In `the_one/interfaces/web/static/index.html`, find the block of `<script>` tags (around line 28-61). Add this line *before* `<script src="/static/js/app.js"></script>`:

```html
<script src="/static/js/components/command-fuzzy.js"></script>
```

- [ ] **Step 5: Rebuild and run the test**

Run: `make rebuild && docker exec the-one pytest tests/browser/test_command_fuzzy.py -x -m browser -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add the_one/interfaces/web/static/js/components/command-fuzzy.js \
        the_one/interfaces/web/static/index.html \
        tests/browser/test_command_fuzzy.py
git commit -m "L8.1: command-fuzzy.js — pure scorer + unit test"
```

---

## Task 12: Catalog module

**Files:**
- Create: `the_one/interfaces/web/static/js/components/command-catalog.js`

- [ ] **Step 1: Write the catalog module**

Create `the_one/interfaces/web/static/js/components/command-catalog.js`:

```js
// L8 — command palette action catalog.
//
// Static actions: navigation + theme + reload + new-session.
// Dynamic actions: agents, providers, sessions — fetched lazily per
// open, cached for 5s. All endpoints are GETs that already exist.
//
// Sessions endpoint: /api/chat/sessions (NOT /api/sessions; the bare
// /api/sessions path does not exist — same gotcha telemetry-refresh.js
// documents at lines 6 + 22).
(function () {
  'use strict';

  var CACHE_TTL_MS = 5000;
  var SESSION_LIMIT = 10;

  var cache = {
    agents: null,
    providers: null,
    sessions: null,
    fetchedAt: 0,
  };

  function fresh() { return Date.now() - cache.fetchedAt < CACHE_TTL_MS; }

  function staticActions() {
    var nav = [
      { id: 'go-chat',     section: 'NAVIGATION', label: 'Go to Chat',                hash: '#chat' },
      { id: 'go-studio',   section: 'NAVIGATION', label: 'Go to Studio',              hash: '#studio' },
      { id: 'go-system',   section: 'NAVIGATION', label: 'Go to System',              hash: '#admin' },
      { id: 'go-providers',section: 'NAVIGATION', label: 'Open Providers',            hash: '#admin/providers' },
      { id: 'go-agents',   section: 'NAVIGATION', label: 'Open Agents',               hash: '#studio/agents' },
      { id: 'go-tools',    section: 'NAVIGATION', label: 'Open Built-in Tools',       hash: '#admin/tools' },
      { id: 'go-mcps',     section: 'NAVIGATION', label: 'Open MCP Servers',          hash: '#studio/mcps' },
    ];

    var current = (window.App && window.App.theme) ? window.App.theme.get() : null;
    var themes = [
      { id: 'theme-light', section: 'ACTIONS', label: 'Theme: Light', themeMode: 'light' },
      { id: 'theme-dark',  section: 'ACTIONS', label: 'Theme: Dark',  themeMode: 'dark'  },
      { id: 'theme-auto',  section: 'ACTIONS', label: 'Theme: Auto',  themeMode: 'auto'  },
    ].filter(function (t) { return t.themeMode !== current; });

    var actions = [
      { id: 'new-session', section: 'ACTIONS', label: 'New session', event: 'chat:new-session' },
      { id: 'reload',      section: 'ACTIONS', label: 'Reload app',  builtin: 'reload' },
    ];

    return nav.concat(themes).concat(actions);
  }

  function fetchJSON(path) {
    return fetch(path, { credentials: 'same-origin' })
      .then(function (r) { return r.ok ? r.json() : Promise.reject(new Error(path + ' ' + r.status)); });
  }

  // Returns a Promise<Array<item>>.  Items have shape:
  //   { id, section, label, keywords?, hash?, themeMode?, event?, builtin?, invoke? }
  function build() {
    var staticItems = staticActions();

    if (fresh() && cache.agents && cache.providers && cache.sessions) {
      return Promise.resolve(staticItems.concat(cache.agents, cache.providers, cache.sessions));
    }

    return Promise.all([
      fetchJSON('/api/agents').catch(function () { return []; }),
      fetchJSON('/api/providers').catch(function () { return []; }),
      fetchJSON('/api/chat/sessions').catch(function () { return []; }),
    ]).then(function (results) {
      var agents = results[0] || [];
      var providers = results[1] || [];
      var sessions = results[2] || [];

      cache.agents = agents.map(function (a) {
        return {
          id: 'agent-' + (a.name || a.id),
          section: 'AGENTS',
          label: 'Switch to agent: ' + (a.name || a.id),
          keywords: (a.persona || '') + ' ' + (a.model || ''),
          event: 'chat:switch-agent',
          eventDetail: { name: a.name || a.id },
        };
      });
      cache.providers = providers.map(function (p) {
        return {
          id: 'provider-' + (p.id || p.name),
          section: 'PROVIDERS',
          label: 'Edit provider: ' + (p.name || p.id),
          keywords: p.provider_type || '',
          hash: '#admin/providers?edit=' + encodeURIComponent(p.id || p.name),
        };
      });
      // Client-side sort + limit — the endpoint does not accept ?limit.
      cache.sessions = sessions
        .slice()
        .sort(function (a, b) { return (b.updated_at || 0) - (a.updated_at || 0); })
        .slice(0, SESSION_LIMIT)
        .map(function (s) {
          return {
            id: 'session-' + s.id,
            section: 'SESSIONS',
            label: 'Open session: ' + (s.title || s.id),
            hash: '#chat?session=' + encodeURIComponent(s.id),
          };
        });
      cache.fetchedAt = Date.now();
      return staticItems.concat(cache.agents, cache.providers, cache.sessions);
    });
  }

  // For tests + the palette's "Some results unavailable" status.
  function lastFetchHadFailures() {
    return !(cache.agents && cache.providers && cache.sessions);
  }

  function invoke(item) {
    if (item.hash) { window.location.hash = item.hash; return; }
    if (item.themeMode && window.App && window.App.theme) {
      window.App.theme.set(item.themeMode); return;
    }
    if (item.event) {
      document.dispatchEvent(new CustomEvent(item.event, { detail: item.eventDetail || {} }));
      return;
    }
    if (item.builtin === 'reload') { window.location.reload(); return; }
  }

  window.App = window.App || {};
  window.App.commandCatalog = {
    build: build,
    invoke: invoke,
    lastFetchHadFailures: lastFetchHadFailures,
    // For tests:
    _resetCache: function () { cache = { agents: null, providers: null, sessions: null, fetchedAt: 0 }; },
  };
})();
```

- [ ] **Step 2: Wire it into index.html**

In `index.html`, add immediately after the `command-fuzzy.js` script tag and before `app.js`:

```html
<script src="/static/js/components/command-catalog.js"></script>
```

- [ ] **Step 3: Rebuild and verify in DevTools**

`make rebuild`. Open `http://localhost:8484/#chat`. In DevTools console:

```js
await window.App.commandCatalog.build().then(items => items.length)
```

Expected: a number > 10 (the static actions alone). With a provider seeded, the count should grow.

- [ ] **Step 4: Commit**

```bash
git add the_one/interfaces/web/static/js/components/command-catalog.js \
        the_one/interfaces/web/static/index.html
git commit -m "L8.2: command-catalog.js — static + dynamic actions with 5s cache"
```

---

## Task 13: Palette component + CSS

**Files:**
- Create: `the_one/interfaces/web/static/js/components/command-palette.js`
- Modify: `the_one/interfaces/web/static/css/components.css`

- [ ] **Step 1: Write the palette component**

Create `the_one/interfaces/web/static/js/components/command-palette.js`:

```js
// L8 — Command Palette (⌘K).
//
// Overlay dialog. Reuses dialog.js patterns: capture-phase keydown,
// focus trap, restore-focus-on-close-only-if-trigger-still-connected.
// Closes on hashchange and on topnav:rerender (L7.8) when the trigger
// anchor was removed.
//
// Safe rendering: every dynamic string (agent names, session titles,
// provider names) is set via textContent. No insertAdjacentHTML on
// user-controlled text.
(function () {
  'use strict';

  var root = null;
  var inputEl = null;
  var resultsEl = null;
  var statusEl = null;
  var trigger = null;
  var items = [];
  var visibleItems = [];
  var activeIndex = 0;

  function build() {
    root = document.createElement('div');
    root.className = 'cp-overlay';
    root.setAttribute('role', 'dialog');
    root.setAttribute('aria-modal', 'true');
    root.setAttribute('aria-labelledby', 'cp-title');
    root.setAttribute('data-testid', 'command-palette');
    root.style.display = 'none';

    var title = document.createElement('h2');
    title.id = 'cp-title';
    title.className = 'visually-hidden';
    title.textContent = 'Command palette';

    var card = document.createElement('div');
    card.className = 'cp-card';

    inputEl = document.createElement('input');
    inputEl.type = 'text';
    inputEl.className = 'cp-input';
    inputEl.setAttribute('placeholder', 'Type a command, agent, provider, or session…');
    inputEl.setAttribute('aria-controls', 'cp-results');
    inputEl.setAttribute('autocomplete', 'off');
    inputEl.setAttribute('spellcheck', 'false');

    statusEl = document.createElement('div');
    statusEl.className = 'cp-status';
    statusEl.setAttribute('aria-live', 'polite');

    resultsEl = document.createElement('ul');
    resultsEl.id = 'cp-results';
    resultsEl.className = 'cp-results';
    resultsEl.setAttribute('role', 'listbox');

    card.appendChild(inputEl);
    card.appendChild(statusEl);
    card.appendChild(resultsEl);
    root.appendChild(title);
    root.appendChild(card);

    root.addEventListener('click', function (e) {
      if (e.target === root) close();
    });
    inputEl.addEventListener('input', render);
    document.body.appendChild(root);
  }

  function rankedItems(query) {
    var fuzzy = window.App.commandFuzzy.score;
    if (!query) {
      // Empty state: show navigation + recent sessions.
      return items.filter(function (it) {
        return it.section === 'NAVIGATION' || it.section === 'SESSIONS';
      }).slice(0, 8);
    }
    var scored = items
      .map(function (it) { return { it: it, s: fuzzy(query, it) }; })
      .filter(function (x) { return x.s > 0; })
      .sort(function (a, b) { return b.s - a.s; });
    return scored.slice(0, 8).map(function (x) { return x.it; });
  }

  function render() {
    var query = inputEl.value;
    visibleItems = rankedItems(query);
    activeIndex = visibleItems.length > 0 ? 0 : -1;

    // Clear results.
    while (resultsEl.firstChild) resultsEl.removeChild(resultsEl.firstChild);

    // Group by section in display order.
    var order = ['NAVIGATION', 'AGENTS', 'PROVIDERS', 'SESSIONS', 'ACTIONS'];
    order.forEach(function (sec) {
      var inSection = visibleItems.filter(function (it) { return it.section === sec; });
      if (inSection.length === 0) return;
      var head = document.createElement('li');
      head.className = 'cp-section';
      head.setAttribute('role', 'presentation');
      head.textContent = sec;
      resultsEl.appendChild(head);
      inSection.forEach(function (it) {
        var li = document.createElement('li');
        li.className = 'cp-item';
        li.setAttribute('role', 'option');
        li.setAttribute('data-id', it.id);
        // Active highlight set below after all rows mounted.
        li.textContent = it.label;
        li.addEventListener('click', function () { invokeIndex(visibleItems.indexOf(it)); });
        resultsEl.appendChild(li);
      });
    });

    updateActiveHighlight();
    statusEl.textContent = window.App.commandCatalog.lastFetchHadFailures()
      ? 'Some results unavailable'
      : '';
  }

  function updateActiveHighlight() {
    var rows = resultsEl.querySelectorAll('.cp-item');
    for (var i = 0; i < rows.length; i++) {
      if (i === activeIndex) {
        rows[i].classList.add('active');
        rows[i].setAttribute('aria-selected', 'true');
      } else {
        rows[i].classList.remove('active');
        rows[i].removeAttribute('aria-selected');
      }
    }
  }

  function invokeIndex(idx) {
    if (idx < 0 || idx >= visibleItems.length) return;
    var item = visibleItems[idx];
    close();
    window.App.commandCatalog.invoke(item);
  }

  function onKeydown(e) {
    if (root.style.display === 'none') return;
    if (e.key === 'Escape') { e.preventDefault(); close(); return; }
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (visibleItems.length === 0) return;
      activeIndex = (activeIndex + 1) % visibleItems.length;
      updateActiveHighlight();
      return;
    }
    if (e.key === 'ArrowUp') {
      e.preventDefault();
      if (visibleItems.length === 0) return;
      activeIndex = (activeIndex - 1 + visibleItems.length) % visibleItems.length;
      updateActiveHighlight();
      return;
    }
    if (e.key === 'Enter') {
      e.preventDefault();
      invokeIndex(activeIndex);
      return;
    }
    if (e.key === 'Tab') {
      // Focus trap — palette only has one focusable (the input), so we
      // just keep focus on it.
      e.preventDefault();
      inputEl.focus();
      return;
    }
  }

  function onHashChange() { if (root && root.style.display !== 'none') close(); }
  function onTopnavRerender() {
    if (root && root.style.display !== 'none' && trigger && !trigger.isConnected) {
      close();
    }
  }

  function open(triggerEl) {
    if (!root) build();
    trigger = triggerEl || null;
    inputEl.value = '';
    items = []; visibleItems = []; activeIndex = -1;
    statusEl.textContent = 'Loading…';
    root.style.display = 'flex';
    inputEl.focus();
    window.App.commandCatalog.build().then(function (built) {
      items = built;
      render();
    });
  }

  function close() {
    if (!root) return;
    root.style.display = 'none';
    if (trigger && trigger.isConnected && typeof trigger.focus === 'function') {
      try { trigger.focus(); } catch (e) { /* ignore */ }
    }
    trigger = null;
  }

  // Capture-phase keydown so palette sees keys before focused-field handlers.
  document.addEventListener('keydown', onKeydown, true);
  window.addEventListener('hashchange', onHashChange);
  document.addEventListener('topnav:rerender', onTopnavRerender);

  window.App = window.App || {};
  window.App.commandPalette = { open: open, close: close };
})();
```

- [ ] **Step 2: Add palette CSS**

Append to `the_one/interfaces/web/static/css/components.css` (inside `@layer components`, at the end before the closing `}` of the layer):

```css
  /* ── L8 Command Palette ──────────────────────────────────────────────── */

  .cp-overlay {
    position: fixed;
    inset: 0;
    z-index: 100;
    display: flex;
    align-items: flex-start;
    justify-content: center;
    background: rgba(0, 0, 0, 0.4);
    padding-top: 88px;
  }
  .cp-card {
    width: 480px;
    max-width: calc(100vw - 32px);
    background: var(--surface);
    border: 1px solid var(--hairline);
    border-radius: 12px;
    box-shadow: var(--shadow-2);
    overflow: hidden;
  }
  .cp-input {
    width: 100%;
    padding: 14px 16px;
    background: transparent;
    border: 0;
    border-bottom: 1px solid var(--hairline);
    color: var(--fg);
    font-size: 14px;
    outline: 0;
  }
  .cp-input::placeholder { color: var(--fg-mute); }
  .cp-status {
    padding: 4px 16px;
    font-size: 11px;
    color: var(--fg-faint);
    min-height: 16px;
  }
  .cp-results {
    list-style: none;
    margin: 0;
    padding: 4px 0 8px;
    max-height: 360px;
    overflow-y: auto;
  }
  .cp-section {
    padding: 8px 16px 4px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    color: var(--fg-faint);
    letter-spacing: 0.08em;
  }
  .cp-item {
    padding: 8px 16px;
    color: var(--fg);
    cursor: pointer;
    font-size: 13px;
  }
  .cp-item.active { background: var(--accent-soft); }
  .cp-item:hover  { background: var(--hover-bg); }
```

- [ ] **Step 3: Wire into index.html**

Add this line in `index.html` after `command-catalog.js` and before `app.js`:

```html
<script src="/static/js/components/command-palette.js"></script>
```

- [ ] **Step 4: Sanity-test in DevTools**

`make rebuild`. Open `http://localhost:8484/#chat`. In DevTools:

```js
window.App.commandPalette.open()
```

Expected: overlay appears, input is focused, results populate after ~100ms.

Type `prov` — only matching results shown. Press Escape — overlay closes.

- [ ] **Step 5: Commit**

```bash
git add the_one/interfaces/web/static/js/components/command-palette.js \
        the_one/interfaces/web/static/css/components.css \
        the_one/interfaces/web/static/index.html
git commit -m "L8.3: command-palette.js — overlay + focus trap + a11y + lifecycle"
```

---

## Task 14: Topnav swap input → button + global ⌘K

**Files:**
- Modify: `the_one/interfaces/web/static/js/topnav.js`
- Modify: `the_one/interfaces/web/static/js/app.js`

- [ ] **Step 1: Swap the search element to a button in `topnav.js`**

In `topnav.js`, replace:

```js
      '<div class="search-wrap">' +
        '<label for="topnav-search" class="visually-hidden">Search</label>' +
        '<input type="search" id="topnav-search" class="search-input" placeholder="Search" aria-label="Open search"/>' +
        '<span class="search-kbd">⌘K</span>' +
      '</div>' +
```

with:

```js
      '<div class="search-wrap">' +
        '<button type="button" id="topnav-search" class="search-input" data-action="open-palette" aria-label="Open command palette">Search</button>' +
        '<span class="search-kbd">⌘K</span>' +
      '</div>' +
```

- [ ] **Step 2: Wire the click handler**

In `topnav.js`, find `bindEvents` and update it to also route `data-action="open-palette"` clicks:

```js
  function bindEvents(onAreaSwitch) {
    var topnav = document.getElementById('app-topnav');
    topnav.addEventListener('click', function (ev) {
      var seg = ev.target.closest('.navseg');
      if (seg && seg.dataset.area) {
        onAreaSwitch(seg.dataset.area);
        return;
      }
      var paletteTrigger = ev.target.closest('[data-action="open-palette"]');
      if (paletteTrigger && window.App && window.App.commandPalette) {
        window.App.commandPalette.open(paletteTrigger);
        return;
      }
    });
  }
```

- [ ] **Step 3: Add the global ⌘K listener in `app.js`**

In `the_one/interfaces/web/static/js/app.js`, find where other global listeners are wired (search for `addEventListener` near the boot block at ~line 196). Add after the existing global listeners:

```js
  // L8 — global ⌘K / Ctrl+K opens the command palette.
  // Skipped when an editable field is focused (so Cmd-K in a textarea
  // doesn't hijack), unless Shift is also held (escape hatch — same
  // convention as VS Code / Linear).
  document.addEventListener('keydown', function (e) {
    if (e.key !== 'k' && e.key !== 'K') return;
    if (!(e.metaKey || e.ctrlKey)) return;
    var t = document.activeElement;
    var inField = t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable);
    if (inField && !e.shiftKey) return;
    e.preventDefault();
    if (window.App && window.App.commandPalette) {
      var trigger = document.getElementById('topnav-search');
      window.App.commandPalette.open(trigger);
    }
  });
```

- [ ] **Step 4: Manual verify**

`make rebuild`. Open `#chat`, press `⌘K`. Palette opens, input focused. Press Escape — palette closes, focus returns to the topnav search button. Click the search button — palette opens.

- [ ] **Step 5: Commit**

```bash
git add the_one/interfaces/web/static/js/topnav.js the_one/interfaces/web/static/js/app.js
git commit -m "L8.4: topnav search → button + global ⌘K opens palette"
```

---

## Task 15: Browser test — palette navigation flow

**Files:**
- Create: `tests/browser/test_command_palette.py`

- [ ] **Step 1: Write the test**

Create `tests/browser/test_command_palette.py`:

```python
"""L8 — Command Palette end-to-end behavior."""
from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.browser
def test_palette_opens_on_cmd_k(app_clean: str, page: Page) -> None:
    page.goto(app_clean)
    page.keyboard.press("Meta+k")
    expect(page.locator('[data-testid="command-palette"]')).to_be_visible()
    expect(page.locator(".cp-input")).to_be_focused()


@pytest.mark.browser
def test_palette_navigates_to_providers(app_clean: str, page: Page) -> None:
    page.goto(app_clean)
    page.keyboard.press("Meta+k")
    expect(page.locator('[data-testid="command-palette"]')).to_be_visible()
    page.locator(".cp-input").fill("prov")
    # Wait for at least one ranked result.
    expect(page.locator(".cp-item.active")).to_be_visible()
    page.keyboard.press("Enter")
    expect(page.locator('[data-testid="command-palette"]')).to_be_hidden()
    page.wait_for_function("() => window.location.hash === '#admin/providers'", timeout=2000)


@pytest.mark.browser
def test_palette_toggles_theme(app_clean: str, page: Page) -> None:
    page.goto(app_clean)
    # Force a known starting state.
    page.evaluate("() => window.App.theme.set('dark')")
    page.keyboard.press("Meta+k")
    page.locator(".cp-input").fill("theme: light")
    page.keyboard.press("Enter")
    page.wait_for_function(
        "() => document.documentElement.getAttribute('data-theme') === 'light'",
        timeout=2000,
    )


@pytest.mark.browser
def test_palette_escape_restores_focus(app_clean: str, page: Page) -> None:
    page.goto(app_clean)
    # Open via the topnav trigger so focus restoration is observable.
    page.locator("#topnav-search").click()
    expect(page.locator('[data-testid="command-palette"]')).to_be_visible()
    page.keyboard.press("Escape")
    expect(page.locator('[data-testid="command-palette"]')).to_be_hidden()
    expect(page.locator("#topnav-search")).to_be_focused()


@pytest.mark.browser
def test_palette_closes_on_hashchange(app_clean: str, page: Page) -> None:
    page.goto(app_clean)
    page.keyboard.press("Meta+k")
    expect(page.locator('[data-testid="command-palette"]')).to_be_visible()
    page.evaluate("() => { window.location.hash = '#studio'; }")
    expect(page.locator('[data-testid="command-palette"]')).to_be_hidden()
```

- [ ] **Step 2: Run the tests**

Run: `docker exec the-one pytest tests/browser/test_command_palette.py -x -m browser -v`
Expected: all 5 pass.

- [ ] **Step 3: Commit**

```bash
git add tests/browser/test_command_palette.py
git commit -m "L8.5: browser tests — palette open/navigate/theme/escape/hashchange"
```

---

## Task 16: Visual snapshot for palette

**Files:**
- Modify: `tests/browser/test_visual_snapshots.py`

- [ ] **Step 1: Add the snapshot test**

Append to `test_visual_snapshots.py`:

```python
@pytest.mark.pixel
@pytest.mark.parametrize("theme", ["dark", "light"])
def test_snapshot_palette_open(app_clean: str, page: Page, theme: str) -> None:
    """L8 — palette overlay rendering."""
    page.set_viewport_size(VIEWPORT)
    page.goto(app_clean)
    _set_theme(page, theme)
    page.keyboard.press("Meta+k")
    expect(page.locator('[data-testid="command-palette"]')).to_be_visible()
    _wait_for_render(page)
    _assert_screenshot(page, f"palette-open-{theme}")
```

- [ ] **Step 2: Generate baselines**

Run: `docker exec the-one pytest tests/browser/test_visual_snapshots.py::test_snapshot_palette_open -x -m pixel --snapshot-update -v`
Expected: pass, two new PNGs created.

- [ ] **Step 3: Re-run without `--snapshot-update`**

Run: `docker exec the-one pytest tests/browser/test_visual_snapshots.py::test_snapshot_palette_open -x -m pixel -v`
Expected: pass.

- [ ] **Step 4: Commit**

```bash
git add tests/browser/test_visual_snapshots.py tests/browser/__snapshots__/palette-open-*.png
git commit -m "L8.6: visual snapshot — palette-open dark + light"
```

L8 is done.

---

# Flight L9 — User (JD) Menu

## Task 17: User menu component + CSS

**Files:**
- Create: `the_one/interfaces/web/static/js/components/user-menu.js`
- Modify: `the_one/interfaces/web/static/css/components.css`
- Modify: `the_one/interfaces/web/static/index.html`

- [ ] **Step 1: Write the component**

Create `the_one/interfaces/web/static/js/components/user-menu.js`:

```js
// L9 — User menu (avatar dropdown).
//
// Items: Theme (Light/Dark/Auto via App.theme.renderToggle) ·
//        System → General · version footer.
//
// No sign-out / profile / multi-user features — this app is single-user
// no-auth per SECURITY-MODEL.md.
(function () {
  'use strict';

  var root = null;
  var anchor = null;

  function build() {
    root = document.createElement('div');
    root.className = 'user-menu';
    root.setAttribute('role', 'menu');
    root.setAttribute('data-testid', 'user-menu');
    root.style.display = 'none';

    // Theme row — renderToggle handles the radiogroup + ARIA.
    var themeHead = document.createElement('div');
    themeHead.className = 'user-menu-heading';
    themeHead.id = 'um-theme-heading';
    themeHead.textContent = 'Theme';

    var themeBox = document.createElement('div');
    themeBox.className = 'user-menu-theme';

    var sysItem = document.createElement('a');
    sysItem.className = 'user-menu-item';
    sysItem.setAttribute('role', 'menuitem');
    sysItem.href = '#admin/general';
    sysItem.textContent = 'System → General';
    sysItem.addEventListener('click', close);

    var divider = document.createElement('div');
    divider.className = 'user-menu-divider';

    var version = document.createElement('div');
    version.className = 'user-menu-version';
    var v = (window.App && window.App.config && window.App.config.version) || 'unknown';
    version.textContent = 'Holograph v' + v;

    root.appendChild(themeHead);
    root.appendChild(themeBox);
    root.appendChild(sysItem);
    root.appendChild(divider);
    root.appendChild(version);

    // Now that themeBox is in the DOM, populate it.
    if (window.App && window.App.theme && typeof window.App.theme.renderToggle === 'function') {
      window.App.theme.renderToggle(themeBox, { labelledBy: 'um-theme-heading' });
    }

    document.body.appendChild(root);
    return root;
  }

  function position() {
    if (!anchor) return;
    var rect = anchor.getBoundingClientRect();
    root.style.position = 'fixed';
    // 220px wide; right-align to anchor's right edge.
    root.style.top  = (rect.bottom + 6) + 'px';
    root.style.left = (rect.right - 220) + 'px';
  }

  function onOutsideClick(e) {
    if (!root || root.style.display === 'none') return;
    if (root.contains(e.target)) return;
    if (anchor && anchor.contains(e.target)) return;
    close();
  }

  function onKeydown(e) {
    if (!root || root.style.display === 'none') return;
    if (e.key === 'Escape') { e.preventDefault(); close(); return; }
  }

  function onHashChange() { if (root && root.style.display !== 'none') close(); }
  function onTopnavRerender() {
    if (root && root.style.display !== 'none' && anchor && !anchor.isConnected) {
      close();
    }
  }

  function toggle(anchorEl) {
    if (root && root.style.display !== 'none') {
      close();
      return;
    }
    if (!root) build();
    anchor = anchorEl || null;
    root.style.display = 'block';
    position();
  }

  function close() {
    if (!root) return;
    root.style.display = 'none';
    if (anchor && anchor.isConnected && typeof anchor.focus === 'function') {
      try { anchor.focus(); } catch (e) { /* ignore */ }
    }
    anchor = null;
  }

  document.addEventListener('click', onOutsideClick);
  document.addEventListener('keydown', onKeydown);
  window.addEventListener('hashchange', onHashChange);
  document.addEventListener('topnav:rerender', onTopnavRerender);

  window.App = window.App || {};
  window.App.userMenu = { toggle: toggle, close: close };
})();
```

- [ ] **Step 2: Add user-menu CSS**

Append to `components.css` inside `@layer components`:

```css
  /* ── L9 User Menu ────────────────────────────────────────────────────── */

  .user-menu {
    width: 220px;
    background: var(--surface);
    border: 1px solid var(--hairline);
    border-radius: 10px;
    box-shadow: var(--shadow-2);
    padding: 10px;
    z-index: 90;
  }
  .user-menu-heading {
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    color: var(--fg-faint);
    letter-spacing: 0.08em;
    padding: 4px 6px;
  }
  .user-menu-theme {
    display: flex;
    gap: 4px;
    padding: 4px 6px 8px;
  }
  .user-menu-item {
    display: block;
    padding: 8px 10px;
    color: var(--fg);
    text-decoration: none;
    font-size: 13px;
    border-radius: 6px;
  }
  .user-menu-item:hover { background: var(--hover-bg); }
  .user-menu-divider {
    height: 1px;
    background: var(--hairline);
    margin: 6px 0;
  }
  .user-menu-version {
    padding: 4px 6px;
    font-size: 11px;
    color: var(--fg-faint);
    font-family: 'JetBrains Mono', monospace;
  }
```

- [ ] **Step 3: Wire into index.html**

Add the script tag after `command-palette.js` and before `app.js`:

```html
<script src="/static/js/components/user-menu.js"></script>
```

- [ ] **Step 4: Sanity-test**

`make rebuild`. Open `#chat`. In DevTools:

```js
window.App.userMenu.toggle(document.querySelector('.avatar'))
```

Expected: dropdown appears anchored to the avatar, theme row + System link + version footer visible.

- [ ] **Step 5: Commit**

```bash
git add the_one/interfaces/web/static/js/components/user-menu.js \
        the_one/interfaces/web/static/css/components.css \
        the_one/interfaces/web/static/index.html
git commit -m "L9.1: user-menu.js — theme toggle + system link + version footer"
```

---

## Task 18: Topnav avatar click → user menu

**Files:**
- Modify: `the_one/interfaces/web/static/js/topnav.js`

- [ ] **Step 1: Extend the click handler**

In `bindEvents` in `topnav.js`, after the palette-trigger branch from Task 14, add:

```js
      var av = ev.target.closest('.avatar');
      if (av && window.App && window.App.userMenu) {
        window.App.userMenu.toggle(av);
        return;
      }
```

The full `bindEvents` should now route three click categories: navseg → area switch, `data-action="open-palette"` → palette, `.avatar` → user menu.

- [ ] **Step 2: Verify**

`make rebuild`. Open `#chat`. Click the JD avatar — menu opens. Click it again — menu closes. Click outside — menu closes. Click "System → General" — menu closes, hash navigates to `#admin/general`.

- [ ] **Step 3: Commit**

```bash
git add the_one/interfaces/web/static/js/topnav.js
git commit -m "L9.2: topnav — avatar click toggles user menu"
```

---

## Task 19: Browser test — user menu

**Files:**
- Create: `tests/browser/test_user_menu.py`

- [ ] **Step 1: Write the test**

Create `tests/browser/test_user_menu.py`:

```python
"""L9 — User menu behavior."""
from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.browser
def test_user_menu_opens_on_avatar_click(app_clean: str, page: Page) -> None:
    page.goto(app_clean)
    page.locator(".avatar").click()
    expect(page.locator('[data-testid="user-menu"]')).to_be_visible()


@pytest.mark.browser
def test_user_menu_theme_switch(app_clean: str, page: Page) -> None:
    page.goto(app_clean)
    page.evaluate("() => window.App.theme.set('dark')")
    page.locator(".avatar").click()
    expect(page.locator('[data-testid="user-menu"]')).to_be_visible()
    # The Light radio comes from App.theme.renderToggle — match by role + name.
    page.get_by_role("radio", name="Light").click()
    page.wait_for_function(
        "() => document.documentElement.getAttribute('data-theme') === 'light'",
        timeout=2000,
    )


@pytest.mark.browser
def test_user_menu_system_link(app_clean: str, page: Page) -> None:
    page.goto(app_clean)
    page.locator(".avatar").click()
    page.get_by_role("menuitem", name="System → General").click()
    page.wait_for_function(
        "() => window.location.hash === '#admin/general'",
        timeout=2000,
    )
    expect(page.locator('[data-testid="user-menu"]')).to_be_hidden()


@pytest.mark.browser
def test_user_menu_version_footer(app_clean: str, page: Page) -> None:
    page.goto(app_clean)
    page.locator(".avatar").click()
    footer = page.locator(".user-menu-version")
    expect(footer).to_be_visible()
    text = footer.text_content() or ""
    assert text.startswith("Holograph v"), f"Unexpected version footer: {text!r}"
    assert "unknown" not in text, "Version not read from App.config.version"


@pytest.mark.browser
def test_user_menu_closes_on_outside_click(app_clean: str, page: Page) -> None:
    page.goto(app_clean)
    page.locator(".avatar").click()
    expect(page.locator('[data-testid="user-menu"]')).to_be_visible()
    page.locator("body").click(position={"x": 5, "y": 200})
    expect(page.locator('[data-testid="user-menu"]')).to_be_hidden()
```

- [ ] **Step 2: Run the tests**

Run: `docker exec the-one pytest tests/browser/test_user_menu.py -x -m browser -v`
Expected: 5 passed.

- [ ] **Step 3: Commit**

```bash
git add tests/browser/test_user_menu.py
git commit -m "L9.3: browser tests — user menu open/theme/system/version/outside-click"
```

---

## Task 20: Visual snapshot for user menu

**Files:**
- Modify: `tests/browser/test_visual_snapshots.py`

- [ ] **Step 1: Add the snapshot test**

Append to `test_visual_snapshots.py`:

```python
@pytest.mark.pixel
@pytest.mark.parametrize("theme", ["dark", "light"])
def test_snapshot_user_menu_open(app_clean: str, page: Page, theme: str) -> None:
    """L9 — user menu dropdown rendering."""
    page.set_viewport_size(VIEWPORT)
    page.goto(app_clean)
    _set_theme(page, theme)
    page.locator(".avatar").click()
    expect(page.locator('[data-testid="user-menu"]')).to_be_visible()
    _wait_for_render(page)
    _assert_screenshot(page, f"user-menu-open-{theme}")
```

- [ ] **Step 2: Generate baselines**

Run: `docker exec the-one pytest tests/browser/test_visual_snapshots.py::test_snapshot_user_menu_open -x -m pixel --snapshot-update -v`
Expected: pass; two new PNGs.

- [ ] **Step 3: Re-run without `--snapshot-update`**

Run: `docker exec the-one pytest tests/browser/test_visual_snapshots.py::test_snapshot_user_menu_open -x -m pixel -v`
Expected: pass.

- [ ] **Step 4: Commit**

```bash
git add tests/browser/test_visual_snapshots.py tests/browser/__snapshots__/user-menu-open-*.png
git commit -m "L9.4: visual snapshot — user-menu-open dark + light"
```

---

## Task 21: Final L7+L8+L9 verification

- [ ] **Step 1: Full suite**

Run: `docker exec the-one pytest -x -v`
Expected: all pass (unit + browser + pixel).

- [ ] **Step 2: Lint**

Run: `ruff check the_one/ tests/`
Expected: no findings.

- [ ] **Step 3: `make verify-serving`**

Run: `make verify-serving`
Expected: pass.

- [ ] **Step 4: Manual smoke walk-through**

```bash
agent-browser --profile ~/.agent-browser/profiles/claude open http://localhost:8484/#chat
```

Verify by hand:
1. Topnav cluster has spacing at 1280 and 1920.
2. `⌘K` opens the palette; type `agents`, Enter navigates to `#studio/agents`.
3. Click JD avatar — menu opens with theme row + System link + version footer.
4. Click "Light" — theme flips.
5. Click "System → General" — menu closes, hash navigates.
6. At 1024×768 the Send button is visible.

L7 + L8 + L9 done.

---

## Self-Review Notes

- **Spec coverage:** Each spec subsection L7.1 through L7.8 → Tasks 1-10; L8.1 → Task 11, L8.2 → Task 12, L8.3 → Task 13, L8.4 (a11y) → Task 13 + 15, L8.5 (topnav swap + global key) → Task 14, L8.6 (theme) → Task 14 + 15, L8.7 (tests) → Tasks 11, 15, 16; L9.1 → Task 17, L9.2 (menu items) → Task 17, L9.3 (UI + lifecycle) → Task 17, L9.4 (topnav integration) → Task 18, L9.5 (tests) → Tasks 19, 20.
- **Type consistency:** `window.App.commandPalette` / `window.App.commandCatalog` / `window.App.commandFuzzy` / `window.App.userMenu` used consistently. `App.theme.set` / `App.theme.get` / `App.theme.renderToggle` match the public API at `theme.js:74-129`.
- **Endpoints:** `/api/chat/sessions` consistently used. No reference to `/api/sessions` other than the documented "not /api/sessions" warning in `command-catalog.js`.
