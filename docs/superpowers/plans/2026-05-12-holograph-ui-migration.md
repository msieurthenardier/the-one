# Holograph UI Migration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate GleepGlorp AI's web UI to the Holograph design language — replacing the current `topbar + sidebar + content` shell with `topnav + content`, retiring all Mission 08 visual vocabulary, and adopting the mockup's CSS class vocabulary verbatim in both light and dark themes.

**Architecture:** Big-bang rewrite across 8 sequenced legs (L1–L8) inside one feature branch. Each leg is a separate commit (sometimes multiple) with passing CI. L1 establishes tokens + base + components; L2 rewrites the shell; L3–L5 migrate Chat, Studio, Admin; L6 reskins modals; L7 rebaselines snapshots + cross-area tests; L8 is housekeeping. Visual ground truth is `playground/mockups/holograph.html` (light) and `playground/mockups/holograph-dark.html` (dark). Authoritative design decisions live in `docs/superpowers/specs/2026-05-12-holograph-ui-migration-design.md`.

**Tech Stack:** vanilla JS + CSS (no frameworks), Python+FastAPI backend untouched, Playwright for browser tests, pytest, Docker for dev (`make rebuild` to pick up frontend changes).

---

## Pre-flight

**Files:**
- (no edits — environment setup only)

- [ ] **Step 0.1: Verify clean working tree on `main`**

```bash
git status
git log --oneline -3
```

Expected output: working tree clean, HEAD at `0446cbc holograph: UI/UX exploration mockups + migration design spec` (or later).

- [ ] **Step 0.2: Create feature branch**

```bash
git checkout -b feat/holograph-migration
```

Expected: branch created.

- [ ] **Step 0.3: Baseline test pass**

```bash
docker exec the-one pytest tests/ -x -q
```

Expected: all 213+ default tests pass. Note pre-migration baseline count.

- [ ] **Step 0.4: Visual baseline snapshot count**

```bash
ls tests/browser/__snapshots__/ | wc -l
```

Expected: ~24 .png files (12 baselines × ~2 per snapshot — light/dark). Note count for end-of-migration comparison.

- [ ] **Step 0.5: Confirm running dev container can serve current UI**

```bash
make up && make verify-serving
```

Expected: container up; admin sub-modules return 200. Browse `http://localhost:8484` to confirm the current Mission-08 UI renders.

---

## L1 — Tokens + base + section-nav primitive

**Files:**
- Replace: `the_one/interfaces/web/static/css/tokens.css`
- Replace: `the_one/interfaces/web/static/css/base.css`
- Replace: `the_one/interfaces/web/static/css/components.css`
- Replace: `the_one/interfaces/web/static/css/fonts.css`
- Add: `the_one/interfaces/web/static/fonts/Inter-{400,500,600,700}.woff2`
- Add: `the_one/interfaces/web/static/fonts/JetBrainsMono-{400,500}.woff2`
- Delete: `the_one/interfaces/web/static/fonts/Geist-*.woff2`, `GeistMono-*.woff2`
- Modify: `the_one/interfaces/web/static/js/areas/layout/section-nav.js`
- Modify: `tests/test_design_tokens_a11y.py`
- Modify: `tests/test_token_definitions.py`
- Modify: `tests/browser/design_tokens.py`

### Task 1.1: Download Inter + JetBrains Mono font files

- [ ] **Step 1.1.1: Download Inter latin-subset WOFF2 (weights 400/500/600/700)**

```bash
mkdir -p the_one/interfaces/web/static/fonts/holograph-staging
cd the_one/interfaces/web/static/fonts/holograph-staging
for w in 400 500 600 700; do
  curl -fL "https://fonts.gstatic.com/s/inter/v18/UcCO3FwrK3iLTeHuS_nVMrMxCp50ojIQA.woff2" -o "Inter-${w}.woff2"
done
```

Or — preferred — fetch from the Inter GitHub release (https://github.com/rsms/inter/releases) and pick the variable WOFF2 for stability.

If unsure: use a single `Inter-Variable.woff2` file with `font-weight: 100 900` in the `@font-face` declaration. Verify file size: 80–150KB.

- [ ] **Step 1.1.2: Download JetBrains Mono latin-subset WOFF2 (weights 400/500)**

```bash
# JetBrains Mono variable font from the official release
curl -fL "https://github.com/JetBrains/JetBrainsMono/raw/master/fonts/webfonts/JetBrainsMono-Regular.woff2" -o JetBrainsMono-400.woff2
curl -fL "https://github.com/JetBrains/JetBrainsMono/raw/master/fonts/webfonts/JetBrainsMono-Medium.woff2" -o JetBrainsMono-500.woff2
```

Verify file size: 30–70KB each.

- [ ] **Step 1.1.3: Move font files into place + delete Geist**

```bash
cd the_one/interfaces/web/static/fonts/
mv holograph-staging/*.woff2 .
rmdir holograph-staging
rm Geist-*.woff2 GeistMono-*.woff2 2>/dev/null || true
ls *.woff2
```

Expected: Inter + JetBrainsMono files present; Geist files gone.

- [ ] **Step 1.1.4: Commit fonts**

```bash
git add the_one/interfaces/web/static/fonts/
git commit -m "L1.1: replace Geist with self-hosted Inter + JetBrains Mono"
```

### Task 1.2: Rewrite `fonts.css`

- [ ] **Step 1.2.1: Replace `fonts.css` content**

Write the file at `the_one/interfaces/web/static/css/fonts.css`:

```css
/* Holograph font stack — self-hosted Inter (body) + JetBrains Mono (code/IDs).
 * Replaces the prior self-hosted Geist Sans + Geist Mono. Latin subset only;
 * tools/IDs/code never need extended Unicode.
 */

@font-face {
  font-family: 'Inter';
  src: url('/static/fonts/Inter-400.woff2') format('woff2');
  font-weight: 400;
  font-display: swap;
  font-style: normal;
}
@font-face {
  font-family: 'Inter';
  src: url('/static/fonts/Inter-500.woff2') format('woff2');
  font-weight: 500;
  font-display: swap;
  font-style: normal;
}
@font-face {
  font-family: 'Inter';
  src: url('/static/fonts/Inter-600.woff2') format('woff2');
  font-weight: 600;
  font-display: swap;
  font-style: normal;
}
@font-face {
  font-family: 'Inter';
  src: url('/static/fonts/Inter-700.woff2') format('woff2');
  font-weight: 700;
  font-display: swap;
  font-style: normal;
}

@font-face {
  font-family: 'JetBrains Mono';
  src: url('/static/fonts/JetBrainsMono-400.woff2') format('woff2');
  font-weight: 400;
  font-display: swap;
  font-style: normal;
}
@font-face {
  font-family: 'JetBrains Mono';
  src: url('/static/fonts/JetBrainsMono-500.woff2') format('woff2');
  font-weight: 500;
  font-display: swap;
  font-style: normal;
}
```

(If you used a variable font in 1.1.1/1.1.2, collapse to a single `@font-face` per family with `font-weight: 100 900;`.)

- [ ] **Step 1.2.2: Commit fonts.css**

```bash
git add the_one/interfaces/web/static/css/fonts.css
git commit -m "L1.2: fonts.css — Inter + JetBrains Mono @font-face"
```

### Task 1.3: Rewrite `tokens.css`

- [ ] **Step 1.3.1: Replace `tokens.css` with Holograph tokens**

Write the file at `the_one/interfaces/web/static/css/tokens.css`:

```css
/* Theme tokens — Holograph migration (Mission 09).
 *
 * Light theme: warm-neutral palette + restrained blue accent (#3358c0,
 * calibrated from mockup #4070e0 to pass WCAG AA at the body threshold).
 * Dark theme: deep calm + GleepGlorp violet (#a78bfa, preserved from
 * Mission 08 dark accent).
 *
 * Token group order (preserved across themes for diffability):
 *   1. surfaces        (bg, surface, surface-2)
 *   2. borders         (hairline, hairline-strong)
 *   3. text            (fg, fg-mute, fg-faint, fg-on-danger)
 *   4. accent          (accent, accent-tint, accent-tint-strong)
 *   5. status          (success, warn, danger)
 *   6. shadows         (shadow-1, shadow-2, shadow-3)
 *   7. badges          (provider + tool category)
 *
 * Theme-stable tokens (geometry, motion) sit OUTSIDE the per-theme blocks.
 *
 * Spec: docs/superpowers/specs/2026-05-12-holograph-ui-migration-design.md
 */

@layer tokens {
  :root {
    color-scheme: dark light;

    /* geometry — identical across themes */
    --radius-card: 12px;
    --radius-control: 8px;
    --radius-chip: 6px;

    /* motion — single transition curve */
    --t: 160ms cubic-bezier(0.2, 0, 0, 1);
  }

  [data-theme="light"] {
    /* surfaces */
    --bg: #f8f8f6;
    --surface: #ffffff;
    --surface-2: #fbfbf9;

    /* borders */
    --hairline: rgba(15, 17, 21, 0.07);
    --hairline-strong: rgba(15, 17, 21, 0.12);

    /* text */
    --fg: #16181d;
    --fg-mute: #6a6e76;
    --fg-faint: #878d96;      /* calibrated from mockup #9da3ad to pass AA-large */
    --fg-on-danger: #ffffff;

    /* accent */
    --accent: #3358c0;        /* calibrated from mockup #4070e0 to pass AA body */
    --accent-tint: rgba(51, 88, 192, 0.10);
    --accent-tint-strong: rgba(51, 88, 192, 0.18);

    /* status */
    --success: #2f9c6a;
    --warn: #c98a2b;
    --danger: #c5443d;

    /* shadows */
    --shadow-1: 0 1px 2px rgba(15, 17, 21, 0.045), 0 1px 1px rgba(15, 17, 21, 0.025);
    --shadow-2: 0 4px 10px rgba(15, 17, 21, 0.05), 0 1px 2px rgba(15, 17, 21, 0.04);
    --shadow-3: 0 12px 28px rgba(15, 17, 21, 0.08), 0 2px 4px rgba(15, 17, 21, 0.04);

    /* provider badges — theme-stable brand colors */
    --badge-ollama: #2ecc71;
    --badge-openai-compatible: #d4a800;
    --badge-openai: #4a9eff;
    --badge-anthropic: #9b59b6;
    --badge-openrouter: #7c3aed;
    --badge-mock: #888888;
    --badge-unknown: #888888;

    /* tool category badges — slightly lighter for light-mode contrast */
    --badge-filesystem: #0e8e8e;
    --badge-execution: #c5912a;
    --badge-web: #d63a93;
  }

  [data-theme="dark"] {
    /* surfaces */
    --bg: #0a0c10;
    --surface: #14171c;
    --surface-2: #181c22;

    /* borders */
    --hairline: rgba(255, 255, 255, 0.08);
    --hairline-strong: rgba(255, 255, 255, 0.14);

    /* text */
    --fg: #e6e7ea;
    --fg-mute: #9aa1ac;
    --fg-faint: #6a7280;
    --fg-on-danger: #0a0c10;

    /* accent */
    --accent: #a78bfa;
    --accent-tint: rgba(167, 139, 250, 0.10);
    --accent-tint-strong: rgba(167, 139, 250, 0.18);

    /* status */
    --success: #4ade80;
    --warn: #f5c97a;
    --danger: #f87171;

    /* shadows */
    --shadow-1: 0 1px 2px rgba(0, 0, 0, 0.25), 0 1px 1px rgba(0, 0, 0, 0.18);
    --shadow-2: 0 4px 12px rgba(0, 0, 0, 0.32), 0 2px 4px rgba(0, 0, 0, 0.22);
    --shadow-3: 0 12px 30px rgba(0, 0, 0, 0.40), 0 3px 6px rgba(0, 0, 0, 0.25);

    /* provider badges */
    --badge-ollama: #2ecc71;
    --badge-openai-compatible: #d4a800;
    --badge-openai: #4a9eff;
    --badge-anthropic: #9b59b6;
    --badge-openrouter: #7c3aed;
    --badge-mock: #888888;
    --badge-unknown: #888888;

    /* tool category badges */
    --badge-filesystem: #008b8b;
    --badge-execution: #b8860b;
    --badge-web: #c71585;
  }

  /* a11y — reduced motion */
  @media (prefers-reduced-motion: reduce) {
    :root { --t: 0ms; }
  }
}
```

- [ ] **Step 1.3.2: Verify tokens.css is parseable**

```bash
make rebuild
curl -sI http://localhost:8484/static/css/tokens.css | head -1
```

Expected: `HTTP/1.1 200 OK`. (CSS parsing happens at browser-side; this just confirms the file is served.)

- [ ] **Step 1.3.3: Update `tests/browser/design_tokens.py` mirror**

Replace the file with the new per-theme token mirror:

```python
"""Per-theme design-token mirror for browser-side assertions.

Mirrors the values in the_one/interfaces/web/static/css/tokens.css.
When tokens.css changes, this file must be updated in lockstep.
"""

LIGHT_TOKENS = {
    "--bg": "#f8f8f6",
    "--surface": "#ffffff",
    "--surface-2": "#fbfbf9",
    "--hairline": "rgba(15, 17, 21, 0.07)",
    "--hairline-strong": "rgba(15, 17, 21, 0.12)",
    "--fg": "#16181d",
    "--fg-mute": "#6a6e76",
    "--fg-faint": "#878d96",
    "--fg-on-danger": "#ffffff",
    "--accent": "#3358c0",
    "--accent-tint": "rgba(51, 88, 192, 0.10)",
    "--accent-tint-strong": "rgba(51, 88, 192, 0.18)",
    "--success": "#2f9c6a",
    "--warn": "#c98a2b",
    "--danger": "#c5443d",
}

DARK_TOKENS = {
    "--bg": "#0a0c10",
    "--surface": "#14171c",
    "--surface-2": "#181c22",
    "--hairline": "rgba(255, 255, 255, 0.08)",
    "--hairline-strong": "rgba(255, 255, 255, 0.14)",
    "--fg": "#e6e7ea",
    "--fg-mute": "#9aa1ac",
    "--fg-faint": "#6a7280",
    "--fg-on-danger": "#0a0c10",
    "--accent": "#a78bfa",
    "--accent-tint": "rgba(167, 139, 250, 0.10)",
    "--accent-tint-strong": "rgba(167, 139, 250, 0.18)",
    "--success": "#4ade80",
    "--warn": "#f5c97a",
    "--danger": "#f87171",
}
```

- [ ] **Step 1.3.4: Commit tokens**

```bash
git add the_one/interfaces/web/static/css/tokens.css tests/browser/design_tokens.py
git commit -m "L1.3: tokens.css — Holograph palette (light + dark)"
```

### Task 1.4: Update `test_design_tokens_a11y.py` with new audit pairs

- [ ] **Step 1.4.1: Write failing test against new pairs**

Replace the audited-pair list in `tests/test_design_tokens_a11y.py` with the spec's table. Key change: drop Mission-08 pair names; add the Holograph pair names with expected ratios.

Pseudocode for the audit assertion shape (concrete code lives in the existing file — preserve test class structure, change only the data table):

```python
HOLOGRAPH_LIGHT_PAIRS = [
    ("--accent", "#3358c0", "--bg", "#f8f8f6", 4.5, "body AA"),
    ("--fg", "#16181d", "--bg", "#f8f8f6", 7.0, "AAA"),
    ("--fg-mute", "#6a6e76", "--bg", "#f8f8f6", 4.5, "body AA"),
    ("--fg-faint", "#878d96", "--bg", "#f8f8f6", 3.0, "AA-large/UI"),
    ("--fg-on-danger", "#ffffff", "--danger", "#c5443d", 4.5, "body AA"),
    # button text pairs
    ("button-text", "#ffffff", "--accent", "#3358c0", 4.5, "body AA on primary button"),
]
HOLOGRAPH_DARK_PAIRS = [
    ("--accent", "#a78bfa", "--bg", "#0a0c10", 4.5, "body AA"),
    ("--fg", "#e6e7ea", "--bg", "#0a0c10", 7.0, "AAA"),
    ("--fg-mute", "#9aa1ac", "--bg", "#0a0c10", 4.5, "body AA"),
    ("--fg-faint", "#6a7280", "--bg", "#0a0c10", 3.0, "AA-large/UI"),
    ("--fg-on-danger", "#0a0c10", "--danger", "#f87171", 4.5, "body AA"),
    ("button-text", "#15101f", "--accent", "#a78bfa", 4.5, "body AA on primary button"),
]
```

- [ ] **Step 1.4.2: Run a11y test**

```bash
docker exec the-one pytest tests/test_design_tokens_a11y.py -v
```

Expected: PASS — all pairs meet their threshold (per spec §"A11y audit"). If a pair fails, the token value in tokens.css needs adjustment.

- [ ] **Step 1.4.3: Commit**

```bash
git add tests/test_design_tokens_a11y.py
git commit -m "L1.4: a11y test — Holograph contrast pairs"
```

### Task 1.5: Rewrite `base.css`

- [ ] **Step 1.5.1: Replace `base.css`**

Write the file at `the_one/interfaces/web/static/css/base.css`:

```css
/* Holograph base layer — typography reset, focus rings, scrollbar, skip-link,
 * body bg. Per-theme values come from tokens.css.
 */

@layer base {
  * { box-sizing: border-box; }
  html, body { margin: 0; padding: 0; }
  body {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    font-size: 13.5px;
    line-height: 1.5;
    color: var(--fg);
    background: var(--bg);
    -webkit-font-smoothing: antialiased;
    min-width: 1280px;
    letter-spacing: -0.005em;
  }

  h1, h2, h3, h4, h5, h6 { margin: 0; }

  a { color: inherit; text-decoration: none; }

  button { font-family: inherit; cursor: pointer; }

  .skip-link {
    position: absolute;
    left: -9999px;
    top: 0;
    padding: 8px 12px;
    background: var(--surface);
    color: var(--fg);
    border: 1px solid var(--hairline-strong);
    border-radius: var(--radius-control);
    z-index: 100;
  }
  .skip-link:focus {
    left: 12px;
    top: 12px;
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }

  :focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
    border-radius: 6px;
  }
  button:focus-visible, .tab:focus-visible, .navlink:focus-visible, .subnav-item:focus-visible {
    outline-offset: 3px;
  }

  ::-webkit-scrollbar { width: 8px; height: 8px; }
  ::-webkit-scrollbar-thumb { background: var(--hairline-strong); border-radius: 4px; }
  ::-webkit-scrollbar-thumb:hover { background: var(--fg-faint); }
  ::-webkit-scrollbar-track { background: transparent; }
}
```

- [ ] **Step 1.5.2: Commit**

```bash
git add the_one/interfaces/web/static/css/base.css
git commit -m "L1.5: base.css — Holograph typography reset + focus + scrollbar"
```

### Task 1.6: Rewrite `components.css`

- [ ] **Step 1.6.1: Replace `components.css` with Holograph shared chrome**

Write the file at `the_one/interfaces/web/static/css/components.css`. The CSS source is the mockup's `<style>` block sections covering: `.topnav`, `.brand*`, `.navlinks/navlink`, `.search`, `.kbd`, `.avatar`, `.area*`, `.btn` family, `.card`, `.chip` family, `.dot` family, `.toggle`, `.seg/seg-btn`, `.tabs/tab`, `.form-row/form-label/form-help/form-control`, `.section-label`, `.icn` family, `.modal-*`, `.confirm-dialog`, `.holograph-section-nav`, `.holograph-section-item`.

Copy the styles verbatim from `playground/mockups/holograph.html` lines 50–250 and 188–1029 (the shared-chrome ranges). Wrap in `@layer components { ... }`.

Add the modal vocabulary (NOT in the mockup):

```css
@layer components {
  /* (existing mockup-derived rules above) */

  .modal-backdrop {
    position: fixed;
    inset: 0;
    background: rgba(15, 17, 21, 0.5);
    z-index: 100;
    display: flex;
    align-items: center;
    justify-content: center;
    backdrop-filter: blur(4px);
    -webkit-backdrop-filter: blur(4px);
  }
  .modal-shell {
    background: var(--surface);
    border: 1px solid var(--hairline);
    border-radius: var(--radius-card);
    box-shadow: var(--shadow-3);
    max-width: 560px;
    width: 90vw;
    max-height: 80vh;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }
  .modal-header {
    display: flex;
    align-items: center;
    padding: 16px 20px;
    border-bottom: 1px solid var(--hairline);
  }
  .modal-title { font-size: 15px; font-weight: 600; letter-spacing: -0.01em; }
  .modal-close {
    margin-left: auto;
    appearance: none;
    background: transparent;
    border: 0;
    color: var(--fg-mute);
    padding: 4px;
    border-radius: 6px;
    cursor: pointer;
  }
  .modal-close:hover { background: rgba(15,17,21,0.05); color: var(--fg); }
  .modal-body { padding: 20px; overflow-y: auto; flex: 1; }
  .modal-footer {
    padding: 12px 20px;
    border-top: 1px solid var(--hairline);
    display: flex;
    justify-content: flex-end;
    gap: 8px;
  }

  .confirm-dialog { max-width: 380px; }
  .confirm-dialog .btn-primary.danger {
    background: var(--danger);
    color: var(--fg-on-danger);
    border-color: var(--danger);
  }
  .confirm-dialog .btn-primary.danger:hover { background: #b03830; border-color: #b03830; }

  /* Holograph section nav — shared by Admin and Studio subnavs */
  .holograph-section-nav {
    display: flex;
    gap: 4px;
    border-bottom: 1px solid var(--hairline);
  }
  .holograph-section-item {
    padding: 10px 14px;
    font-size: 13px;
    font-weight: 500;
    color: var(--fg-mute);
    cursor: pointer;
    border-bottom: 2px solid transparent;
    margin-bottom: -1px;
    transition: color var(--t), border-color var(--t);
    background: transparent;
    border-left: 0; border-right: 0; border-top: 0;
  }
  .holograph-section-item:hover { color: var(--fg); }
  .holograph-section-item.active { color: var(--fg); border-bottom-color: var(--accent); }

  /* Reduced-transparency fallback for the only translucent surface (topnav). */
  @media (prefers-reduced-transparency: reduce) {
    .topnav { background: var(--bg); backdrop-filter: none; -webkit-backdrop-filter: none; }
    .modal-backdrop { backdrop-filter: none; -webkit-backdrop-filter: none; }
  }
}
```

The mockup-verbatim rules from earlier ranges go above this block. Use the mockup's exact selectors and values. Wrap the whole file in `@layer components { ... }`.

- [ ] **Step 1.6.2: Run smoke test**

```bash
docker exec the-one pytest tests/browser/test_smoke.py -x -q
```

Expected: smoke test still passes (it asserts the app boots; component class changes don't break boot). If the test inspects specific old classes, it'll fail — that's L7's job. For L1, smoke must still pass.

- [ ] **Step 1.6.3: Commit**

```bash
git add the_one/interfaces/web/static/css/components.css
git commit -m "L1.6: components.css — Holograph shared chrome + modals + section-nav"
```

### Task 1.7: Restyle `section-nav.js` markup

- [ ] **Step 1.7.1: Modify `section-nav.js` to emit Holograph classes**

Open `the_one/interfaces/web/static/js/areas/layout/section-nav.js`. The public API `App.layout.renderSectionNav(container, items, active, options)` and `App.layout.updateActiveSection(container, active)` is preserved (per spec Decision 17). Only the emitted markup changes.

Find the rendered HTML inside `renderSectionNav` and change:
- Container class from whatever it currently is (likely `section-nav` or `app-section-nav`) → add `holograph-section-nav` (keep old class as a no-op until L7 strips it).
- Item class from `section-nav-item` → add `holograph-section-item`.
- Preserve `data-section-id`, `role="tablist"` / `role="tab"`, and any keydown handlers.

Concrete diff shape (find the existing render function and adapt):

```js
// BEFORE
container.innerHTML = items.map(item =>
  `<button class="section-nav-item" data-section-id="${item.id}" role="tab" ...>${item.label}</button>`
).join('');

// AFTER
container.classList.add('holograph-section-nav');
container.setAttribute('role', 'tablist');
if (options && options.ariaLabel) container.setAttribute('aria-label', options.ariaLabel);
container.innerHTML = items.map(item =>
  `<button class="holograph-section-item${item.id === active ? ' active' : ''}" data-section-id="${item.id}" role="tab" aria-selected="${item.id === active}">${item.label}</button>`
).join('');
```

Adjust `updateActiveSection` to toggle `.active` on `.holograph-section-item` elements.

- [ ] **Step 1.7.2: Verify section-nav still renders in current app**

```bash
make rebuild
```

Manually browse to `http://localhost:8484/#admin/providers` and confirm the admin subnav still renders + clicks still navigate. (The OLD styling is gone — buttons may look unstyled until L5 adds `.admin-subnav` styling alias. That's OK for L1.)

- [ ] **Step 1.7.3: Commit**

```bash
git add the_one/interfaces/web/static/js/areas/layout/section-nav.js
git commit -m "L1.7: section-nav.js — emit Holograph markup; preserve public API"
```

### Task 1.8: Token-definitions test passes

- [ ] **Step 1.8.1: Run token-definitions test**

```bash
docker exec the-one pytest tests/test_token_definitions.py -v
```

Expected: PASS — every `var(--x)` in CSS resolves to a definition in `tokens.css` or `base.css`. If FAIL, investigate:
- If a retired token (e.g. `--glass-bg`) is still referenced in a CSS file other than `tokens.css`, fix that reference — for L1 we only need the CSS layers in tokens/base/components to be clean. chat.css/studio.css/admin.css can still reference retired tokens (they're rewritten in L3/L4/L5).

If the test only audits `tokens.css` + `base.css` + `components.css`, it should pass. If it audits all `.css` files, mark this step as expected-fail until L5 and re-run in L7.

### Task 1.9: L1 acceptance + commit milestone

- [ ] **Step 1.9.1: Run full test suite**

```bash
docker exec the-one pytest tests/ -x -q
```

Expected: all unit tests + token a11y + token defs pass. Browser tests will partially fail — that's expected for in-flight migration. Note any unexpected failures.

- [ ] **Step 1.9.2: Manual browser sanity check**

Open `http://localhost:8484` and confirm:
- App boots without console errors
- Fonts load (Inter visible in body, JetBrains Mono visible in any monospace UI element)
- Theme toggle still works at `#admin/general`
- Topbar still renders (old shell — L2's job to replace)

Note: many surfaces will look broken/unstyled at this point. That's expected. Don't fix piecemeal — L2-L5 handle the area rewrites.

- [ ] **Step 1.9.3: Optional: amend an L1 summary commit**

(All L1 commits already happened. If desired, add an empty marker commit for clarity in `git log`.)

```bash
git commit --allow-empty -m "L1 complete — tokens + base + section-nav + fonts"
```

---

## L2 — Shell rewrite

**Files:**
- Replace: `the_one/interfaces/web/static/index.html`
- Modify: `the_one/interfaces/web/static/js/app.js` (renderTopBar → renderTopNav; `registerArea({init: fn(content)})` API; preserve hash routing)
- Modify: any area registering with `registerArea({init: fn(sidebar, content)})` — update signatures to receive only `content` (BUT areas remain functional with the old code until L3-L5 rewrites — we use a transitional shim)

### Task 2.1: Rewrite `index.html`

- [ ] **Step 2.1.1: Replace `index.html`**

Write the file at `the_one/interfaces/web/static/index.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<link rel="icon" type="image/png" sizes="16x16" href="/static/brand/favicon-16.png">
<link rel="icon" type="image/png" sizes="32x32" href="/static/brand/favicon-32.png">
<link rel="icon" type="image/png" sizes="48x48" href="/static/brand/favicon-48.png">
<link rel="icon" href="/static/brand/favicon.ico">
<link rel="apple-touch-icon" sizes="180x180" href="/static/brand/apple-touch-icon.png">
<title>GleepGlorp AI</title>
<style>@layer tokens, base, components, areas, utilities;</style>
<script src="/static/js/theme.js"></script>
<link rel="stylesheet" href="/static/css/fonts.css">
<link rel="stylesheet" href="/static/css/tokens.css">
<link rel="stylesheet" href="/static/css/base.css">
<link rel="stylesheet" href="/static/css/components.css">
<link rel="stylesheet" href="/static/css/chat.css">
<link rel="stylesheet" href="/static/css/studio.css">
<link rel="stylesheet" href="/static/css/admin.css">
</head>
<body>
<a class="skip-link" href="#main-content">Skip to main content</a>

<nav class="topnav" id="app-topnav"></nav>
<main id="main-content" tabindex="-1"></main>

<script src="/static/js/app.js"></script>
<script src="/static/js/icons.js"></script>
<script src="/static/js/markdown.js"></script>
<script src="/static/js/confirm.js"></script>
<script src="/static/js/dialog.js"></script>
<script src="/static/js/tabs.js"></script>
<script src="/static/js/areas/layout/section-nav.js"></script>
<script src="/static/js/areas/chat/welcome.js"></script>
<script src="/static/js/areas/chat/history-buckets.js"></script>
<script src="/static/js/areas/chat/message-bubble.js"></script>
<script src="/static/js/areas/chat/thinking-indicator.js"></script>
<script src="/static/js/areas/chat/telemetry-overlay.js"></script>
<script src="/static/js/areas/chat.js"></script>
<script src="/static/js/areas/studio/stub-knowledge.js"></script>
<script src="/static/js/areas/studio/knowledge-tab.js"></script>
<script src="/static/js/areas/studio/general-tab.js"></script>
<script src="/static/js/areas/studio/tools-tab.js"></script>
<script src="/static/js/areas/studio/mcps-tab.js"></script>
<script src="/static/js/areas/studio/agent-editor.js"></script>
<script src="/static/js/areas/studio/mcp-servers-grid.js"></script>
<script src="/static/js/areas/studio/mcp-server-editor.js"></script>
<script src="/static/js/areas/studio.js"></script>
<script src="/static/js/areas/admin/providers-grid.js"></script>
<script src="/static/js/areas/admin/provider-editor.js"></script>
<script src="/static/js/areas/admin/provider-models.js"></script>
<script src="/static/js/areas/admin/tools-grid.js"></script>
<script src="/static/js/areas/admin/tools-form-helpers.js"></script>
<script src="/static/js/areas/admin/tools-editor.js"></script>
<script src="/static/js/areas/admin/system-page.js"></script>
<script src="/static/js/areas/admin.js"></script>
</body>
</html>
```

Notable removals from the prior shell:
- `<header id="app-topbar">` → replaced by `<nav class="topnav" id="app-topnav">`
- `<div class="app-shell-row"> <aside id="app-sidebar"> <main>` → flat `<main id="main-content">`
- `gleepglorp_banner.png` reference is gone
- `design-language-page.js` and `design-language/*.js` script tags are gone (will be re-added by mistake if you copy the old index — verify before commit)

- [ ] **Step 2.1.2: Verify HTML serves**

```bash
make rebuild
curl -sI http://localhost:8484/static/index.html | head -1
curl -s http://localhost:8484/static/index.html | grep -E "(app-topnav|app-sidebar|app-topbar)"
```

Expected: `200 OK`. The grep should find `app-topnav` exactly once and NOT find `app-sidebar` or `app-topbar` (other than incidentally inside any retained classnames in script content — pure index.html grep should be clean).

- [ ] **Step 2.1.3: Commit**

```bash
git add the_one/interfaces/web/static/index.html
git commit -m "L2.1: index.html — topnav + content shell"
```

### Task 2.2: Rewrite `app.js` shell logic

- [ ] **Step 2.2.1: Read the existing `app.js`**

```bash
cat the_one/interfaces/web/static/js/app.js | head -200
```

Note the existing functions: `registerArea`, `renderTopBar`, `parseHash`, `switchTo`. The structure is preserved; we modify `renderTopBar` → `renderTopNav` and the `switchTo` panel-mounting logic.

- [ ] **Step 2.2.2: Modify `app.js`**

Replace `renderTopBar` with `renderTopNav` that emits the Holograph topnav markup. Modify `switchTo` to mount panels under `#main-content` only (no sidebar). Modify `registerArea` to accept descriptors whose `init` takes ONLY `content`.

Key sections to change:

```js
// renderTopBar → renderTopNav (replaces the existing function)
function renderTopNav() {
  var topnav = document.getElementById('app-topnav');

  var navlinksHtml = '';
  for (var i = 0; i < order.length; i++) {
    var a = order[i];
    navlinksHtml +=
      '<button class="navlink" data-area="' + a.id + '" aria-label="Go to ' + a.label + '">' +
      a.label +
      '</button>';
  }

  topnav.innerHTML =
    '<div class="brand">' +
      '<div class="brand-mark">G</div>' +
      '<div class="brand-name">GleepGlorp <span class="sub">AI</span></div>' +
    '</div>' +
    '<div class="navlinks">' + navlinksHtml + '</div>' +
    '<div class="nav-right">' +
      '<button class="search" aria-label="Open search" aria-keyshortcuts="Control+K Meta+K">' +
        '<svg class="icn" viewBox="0 0 16 16"><circle cx="7" cy="7" r="5"/><path d="M14 14l-3-3"/></svg>' +
        '<span>Search</span>' +
        '<span class="kbd">⌘K</span>' +
      '</button>' +
      '<div class="avatar" id="app-user-avatar" aria-label="User">JD</div>' +
    '</div>';

  // Wire navlink clicks to hash navigation.
  var buttons = topnav.querySelectorAll('.navlink');
  for (var j = 0; j < buttons.length; j++) {
    (function (btn) {
      var areaId = btn.dataset.area;
      btn.addEventListener('click', function (e) {
        e.stopPropagation();
        location.hash = areaId;
      });
    })(buttons[j]);
  }

  // Wire search affordance to stub toast.
  var searchBtn = topnav.querySelector('.search');
  searchBtn.addEventListener('click', function () {
    if (window.App && window.App.toast) {
      window.App.toast('Search coming soon.');
    } else {
      console.info('[Holograph] Search coming soon.');
    }
  });

  // ⌘K / Ctrl-K opens the same stub.
  document.addEventListener('keydown', function (e) {
    if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
      e.preventDefault();
      searchBtn.click();
    }
  });
}
```

Also modify `switchTo` to mount panels in `#main-content` only:

```js
function switchTo(areaId, sub) {
  if (!areas[areaId]) areaId = 'chat';
  sub = (sub === undefined ? null : sub);

  if (areaId === currentId && sub === currentSub) return;
  if (areaId === currentId && sub !== currentSub) {
    currentSub = sub;
    if (typeof areas[areaId].hydrateState === 'function') areas[areaId].hydrateState(sub);
    syncUrlFromState(areaId, sub);
    return;
  }

  function performCrossAreaSwitch() {
    if (currentId && areas[currentId]) areas[currentId].deactivate();

    // Hide all content panels.
    var contentPanels = document.querySelectorAll('#main-content .content-panel');
    for (var i = 0; i < contentPanels.length; i++) contentPanels[i].classList.remove('active');

    if (!initialized[areaId]) {
      var contentPanel = document.createElement('div');
      contentPanel.className = 'content-panel area-' + areaId;
      document.getElementById('main-content').appendChild(contentPanel);
      areas[areaId].init(contentPanel);   // single arg (Decision 3)
      initialized[areaId] = true;
    }

    var targetContent = document.querySelector('#main-content .area-' + areaId);
    if (targetContent) targetContent.classList.add('active');

    // Update active navlink.
    var allNavlinks = document.querySelectorAll('.topnav .navlink');
    for (var k = 0; k < allNavlinks.length; k++) {
      allNavlinks[k].classList.toggle('active', allNavlinks[k].dataset.area === areaId);
    }

    currentId = areaId;
    currentSub = sub;
    if (typeof areas[areaId].hydrateState === 'function') areas[areaId].hydrateState(sub);
    if (typeof areas[areaId].activate === 'function') areas[areaId].activate();
    syncUrlFromState(areaId, sub);
  }

  if (currentId && areas[currentId] && typeof areas[currentId].confirmLeave === 'function') {
    areas[currentId].confirmLeave(performCrossAreaSwitch);
  } else {
    performCrossAreaSwitch();
  }
}
```

Also update `init()` (the bootstrap function that calls `renderTopBar`):

```js
function init() {
  renderTopNav();  // was: renderTopBar()

  // Initial hash routing.
  var parsed = parseHash(location.hash);
  if (!parsed.area) location.hash = order.length > 0 ? order[0].id : 'chat';
  else switchTo(parsed.area, parsed.sub);

  window.addEventListener('hashchange', function () {
    var parsed = parseHash(location.hash);
    switchTo(parsed.area, parsed.sub);
  });
}
```

- [ ] **Step 2.2.3: Add `App.toast` helper (simple inline impl)**

Either add to `app.js` directly OR a new file. Inline is simpler:

```js
// Append near the end of app.js, before `init()` is called.
window.App = window.App || {};
window.App.toast = function (msg, opts) {
  opts = opts || {};
  var existing = document.querySelector('.app-toast');
  if (existing) existing.remove();
  var el = document.createElement('div');
  el.className = 'app-toast';
  el.textContent = msg;
  el.setAttribute('role', 'status');
  document.body.appendChild(el);
  setTimeout(function () { el.classList.add('app-toast-out'); }, opts.duration || 2400);
  setTimeout(function () { el.remove(); }, (opts.duration || 2400) + 320);
};
```

Add corresponding CSS to `components.css`:

```css
.app-toast {
  position: fixed;
  bottom: 24px;
  left: 50%;
  transform: translateX(-50%);
  background: var(--surface);
  border: 1px solid var(--hairline-strong);
  border-radius: var(--radius-control);
  box-shadow: var(--shadow-2);
  padding: 10px 16px;
  font-size: 13px;
  color: var(--fg);
  z-index: 200;
  transition: opacity 320ms ease-out, transform 320ms ease-out;
}
.app-toast-out { opacity: 0; transform: translateX(-50%) translateY(8px); }
```

- [ ] **Step 2.2.4: Add transitional shim for areas that still expect `init(sidebar, content)`**

The cleanest path: each area is rewritten in L3-L5 to accept `init(content)`. To survive L2's commit with the current area code, wrap `areas[areaId].init(contentPanel)` in a guard that detects the old signature and passes a stub sidebar div:

```js
// In switchTo's performCrossAreaSwitch, BEFORE areas[areaId].init(contentPanel):
if (areas[areaId].init.length >= 2) {
  // OLD signature — pass a detached stub sidebar div so the area mounts safely
  // (the stub never enters the DOM; L3-L5 rewrite each area to use the new sig)
  var stubSidebar = document.createElement('div');
  stubSidebar.className = 'sidebar-panel area-' + areaId + ' legacy-stub';
  areas[areaId].init(stubSidebar, contentPanel);
} else {
  areas[areaId].init(contentPanel);
}
```

This shim is **temporary** — L8 removes it once all areas use the new signature.

- [ ] **Step 2.2.5: Verify app boots**

```bash
make rebuild
```

Open `http://localhost:8484` and confirm:
- Topnav renders with brand + Chat / Studio / Admin / search affordance / avatar
- Clicking navlinks navigates correctly (URL hash updates; active styling moves)
- ⌘K (or Ctrl-K) triggers the stub toast
- The CURRENT area JS still mounts (likely looking ugly because old CSS classes don't match new components.css — that's expected)
- No JS errors in console

- [ ] **Step 2.2.6: Run smoke + hash-routing test**

```bash
docker exec the-one pytest tests/browser/test_smoke.py tests/browser/test_flow_hash_routing.py -x -q
```

Smoke should PASS. Hash routing may fail on selectors that target the old topbar — flag these for L7. The shell mechanics (hashchange → area switch) should still work.

- [ ] **Step 2.2.7: Commit**

```bash
git add the_one/interfaces/web/static/js/app.js the_one/interfaces/web/static/css/components.css
git commit -m "L2.2: app.js — renderTopNav + init(content) shell"
```

### Task 2.3: L2 acceptance

- [ ] **Step 2.3.1: Run all unit tests**

```bash
docker exec the-one pytest tests/ --ignore=tests/browser -x -q
```

Expected: unit tests pass; no regressions.

- [ ] **Step 2.3.2: Document expected browser-test failures**

```bash
docker exec the-one pytest tests/browser/ -q --tb=no 2>&1 | tail -20
```

Expected: failures concentrated in tests that select the old shell (`#app-sidebar`, `.app-picker-button`, etc.). These get fixed per-area in L3-L5. Note the FAILED count for end-of-mission comparison.

---

## L3 — Chat area

**Files:**
- Replace: `the_one/interfaces/web/static/css/chat.css`
- Modify: `the_one/interfaces/web/static/js/areas/chat.js` (render `<div class="chat-layout">` inside content; new DOM)
- Modify: `the_one/interfaces/web/static/js/areas/chat/welcome.js`
- Modify: `the_one/interfaces/web/static/js/areas/chat/history-buckets.js`
- Modify: `the_one/interfaces/web/static/js/areas/chat/message-bubble.js`
- Modify: `the_one/interfaces/web/static/js/areas/chat/thinking-indicator.js`
- Modify: `the_one/interfaces/web/static/js/areas/chat/telemetry-overlay.js`
- Modify (selectors only): `tests/browser/test_flow_chat.py`, `test_flow_streaming.py`, `test_flow_new_chat.py`, `test_flow_markdown_chat.py`, `test_flow_picker.py`, `test_markdown.py`

### Task 3.1: Rewrite `chat.css`

- [ ] **Step 3.1.1: Replace `chat.css` with mockup-verbatim chat styles**

Copy the chat-specific section from the mockup's `<style>` block (lines 267–582 of `playground/mockups/holograph.html`) into `the_one/interfaces/web/static/css/chat.css`. Wrap in `@layer areas { ... }`.

The covered selectors are: `.chat-layout`, `.sessions-pane`, `.sessions-header`, `.new-session-btn`, `.sessions-list`, `.session-card` (+ `.active`), `.session-title`, `.session-meta`, `.session-snippet`, `.session-time`, `.session-agent-dot`, `.convo-pane`, `.convo-header`, `.convo-title`, `.convo-agent`, `.convo-actions`, `.convo-stream`, `.msg-row` (+ `.user`), `.agent-avatar`, `.msg-body`, `.msg-meta`, `.msg-author`, `.msg-time`, `.msg-text`, `.toolcall` (+ `.open`), `.toolcall-header`, `.toolcall-icon`, `.toolcall-name`, `.toolcall-summary`, `.toolcall-status`, `.toolcall-chevron`, `.toolcall-body`, `.toolcall-section`, `.toolcall-section-label`, `.toolcall-content`, `.composer`, `.composer-box`, `.composer-input`, `.composer-controls`.

- [ ] **Step 3.1.2: Commit**

```bash
git add the_one/interfaces/web/static/css/chat.css
git commit -m "L3.1: chat.css — Holograph chat styles"
```

### Task 3.2: Rewrite `chat.js` top-level render

- [ ] **Step 3.2.1: Read existing `chat.js`**

```bash
sed -n '1,80p' the_one/interfaces/web/static/js/areas/chat.js
```

Identify the `init`, `activate`, `deactivate`, `hydrateState`, `serializeState` functions and the top-level HTML render.

- [ ] **Step 3.2.2: Modify `init` to use new signature + render new DOM**

Change the signature from `init: function (sidebar, content)` to `init: function (content)`. In the render, output the chat layout inside `content`:

```js
init: function (content) {
  content.innerHTML =
    '<div class="chat-layout">' +
      '<aside class="sessions-pane">' +
        '<div class="sessions-header">' +
          '<h3>Sessions</h3>' +
          '<button class="new-session-btn" aria-label="New session">' +
            '<svg class="icn icn-sm" viewBox="0 0 12 12"><path d="M6 2v8M2 6h8" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>' +
          '</button>' +
        '</div>' +
        '<div class="sessions-list" id="chat-sessions-list"></div>' +
      '</aside>' +
      '<div class="convo-pane">' +
        '<div class="convo-header" id="chat-convo-header"></div>' +
        '<div class="convo-stream" id="chat-convo-stream"></div>' +
        '<div class="composer" id="chat-composer"></div>' +
      '</div>' +
    '</div>';

  // Wire new-session button + load sessions
  content.querySelector('.new-session-btn').addEventListener('click', this._onNewSession.bind(this));
  this._loadSessions();
  // ... other init logic from existing chat.js (websocket, event listeners, etc.)
},
```

Preserve all existing behavior: session loading, WebSocket setup, agent picker logic, dirty-confirm, hash sync.

- [ ] **Step 3.2.3: Update session-card render**

Find the function that renders the session list (likely calls `history-buckets.js`). Change each session item from the old `.sidebar-item` (or whatever) class to `.session-card`. Use the markup shape from the mockup:

```js
function renderSessionCard(session, isActive) {
  return (
    '<div class="session-card' + (isActive ? ' active' : '') + '" data-session-id="' + escapeHtml(session.id) + '">' +
      '<div class="session-title">' + escapeHtml(session.title || 'Untitled') + '</div>' +
      '<div class="session-meta">' +
        '<span class="session-agent-dot"></span>' +
        '<span>' + escapeHtml(session.agent_name || '') + ' · ' + escapeHtml(session.model || '') + '</span>' +
      '</div>' +
      '<div class="session-snippet">' + escapeHtml(session.snippet || '') + '</div>' +
      '<div class="session-time">' + formatRelativeTime(session.updated_at) + '</div>' +
    '</div>'
  );
}
```

- [ ] **Step 3.2.4: Update convo-header render**

The convo header shows session title + agent name + agent model chip + actions. Build it from the mockup shape:

```js
function renderConvoHeader(session) {
  return (
    '<div><div class="convo-title">' + escapeHtml(session.title) + '</div></div>' +
    '<div class="convo-agent">' +
      '<div class="agent-avatar">' + (session.agent_initial || 'A') + '</div>' +
      '<span>' + escapeHtml(session.agent_name || 'Agent') + '</span>' +
      '<span class="chip mono">' + escapeHtml(session.model || '') + '</span>' +
    '</div>' +
    '<div class="convo-actions">' +
      '<button class="btn btn-ghost" aria-label="Session settings">' +
        '<svg class="icn" viewBox="0 0 16 16"><circle cx="8" cy="8" r="2" stroke="currentColor" stroke-width="1.6" fill="none"/></svg>' +
      '</button>' +
    '</div>'
  );
}
```

- [ ] **Step 3.2.5: Update message-bubble render**

Open `message-bubble.js`. Replace the old message-rendering shape with `.msg-row`/`.msg-body`/etc per mockup. User messages get `.msg-row.user`; agent messages have an `.agent-avatar` + `.msg-meta` + `.msg-text`. Tool calls render as `.toolcall` blocks (collapsed by default; click toggles `.open`).

Concrete bubble shape:

```js
function renderAgentMessage(msg) {
  return (
    '<div class="msg-row">' +
      '<div class="agent-avatar">' + (msg.agent_initial || 'A') + '</div>' +
      '<div class="msg-body">' +
        '<div class="msg-meta">' +
          '<span class="msg-author">' + escapeHtml(msg.agent_name) + '</span>' +
          '<span class="msg-time">' + formatTime(msg.created_at) + '</span>' +
        '</div>' +
        '<div class="msg-text">' + renderMarkdown(msg.content) + '</div>' +
        renderToolCalls(msg.tool_calls || []) +
      '</div>' +
    '</div>'
  );
}

function renderUserMessage(msg) {
  return (
    '<div class="msg-row user">' +
      '<div class="msg-body">' +
        '<div class="msg-text">' + escapeHtml(msg.content) + '</div>' +
        '<div class="msg-meta" style="justify-content:flex-end;">' +
          '<span class="msg-time">' + formatTime(msg.created_at) + '</span>' +
        '</div>' +
      '</div>' +
    '</div>'
  );
}

function renderToolCalls(calls) {
  if (!calls.length) return '';
  return calls.map(function (tc) {
    return (
      '<div class="toolcall" data-tool-call-id="' + escapeHtml(tc.id) + '">' +
        '<div class="toolcall-header">' +
          '<svg class="icn toolcall-chevron" viewBox="0 0 16 16"><path d="M6 4l4 4-4 4" stroke="currentColor" stroke-width="1.6" fill="none" stroke-linecap="round"/></svg>' +
          '<div class="toolcall-icon">' + toolIconSvg(tc.tool_name) + '</div>' +
          '<span class="toolcall-name">' + escapeHtml(tc.tool_name) + '</span>' +
          '<span class="toolcall-summary">' + escapeHtml(tc.summary || '') + '</span>' +
          '<span class="toolcall-status"><span class="dot live"></span><span>' + escapeHtml(tc.status || 'done') + '</span></span>' +
        '</div>' +
        '<div class="toolcall-body">' +
          (tc.args ? '<div class="toolcall-section"><div class="toolcall-section-label">Args</div><div class="toolcall-content">' + escapeHtml(JSON.stringify(tc.args, null, 2)) + '</div></div>' : '') +
          (tc.result ? '<div class="toolcall-section"><div class="toolcall-section-label">Result</div><div class="toolcall-content">' + escapeHtml(tc.result) + '</div></div>' : '') +
        '</div>' +
      '</div>'
    );
  }).join('');
}
```

Wire the toolcall-header click toggling `.open` class.

- [ ] **Step 3.2.6: Update composer render**

```js
function renderComposer(agentName) {
  return (
    '<div class="composer-box">' +
      '<textarea class="composer-input" rows="1" placeholder="Ask ' + escapeHtml(agentName || 'agent') + ' anything…"></textarea>' +
      '<div class="composer-controls">' +
        '<button class="btn btn-ghost" data-action="attach"><svg class="icn" viewBox="0 0 16 16"><path d="M10 4L5 9a2 2 0 002.8 2.8L13 6.6a3.5 3.5 0 00-4.9-4.9L3 6.6" stroke="currentColor" stroke-width="1.6" fill="none" stroke-linecap="round"/></svg> Attach</button>' +
        '<div class="right">' +
          '<span class="chip mono" id="chat-ctx-chip">0k ctx</span>' +
          '<button class="btn btn-primary" data-action="send">Send <svg class="icn icn-sm" viewBox="0 0 12 12"><path d="M2 6h8M6 2l4 4-4 4" stroke="currentColor" stroke-width="1.6" fill="none" stroke-linecap="round"/></svg></button>' +
        '</div>' +
      '</div>' +
    '</div>'
  );
}
```

Wire send-button click + Enter-key submission (preserve existing WebSocket sender logic).

- [ ] **Step 3.2.7: Update telemetry-overlay**

`telemetry-overlay.js` currently renders a floating telemetry panel. Repurpose it: render the context-usage chip into `#chat-ctx-chip` (text-only — no separate overlay). Remove the floating panel; the convo header shows the chip instead.

- [ ] **Step 3.2.8: Update thinking-indicator**

`thinking-indicator.js` renders a "thinking" state. Repurpose to inject a `.toolcall.open` with `.dot.live` and the text "Thinking…" into the convo stream while the agent is between user-message and first tool-call.

```js
function renderThinkingIndicator() {
  return (
    '<div class="toolcall open" data-thinking-indicator>' +
      '<div class="toolcall-header">' +
        '<svg class="icn toolcall-chevron" viewBox="0 0 16 16"><path d="M6 4l4 4-4 4" stroke="currentColor" stroke-width="1.6" fill="none" stroke-linecap="round"/></svg>' +
        '<span class="toolcall-name">Thinking…</span>' +
        '<span class="toolcall-status"><span class="dot live"></span></span>' +
      '</div>' +
    '</div>'
  );
}
```

- [ ] **Step 3.2.9: Update welcome / empty state**

`welcome.js` renders the empty state. Update its HTML to match the mockup's empty-pane patterns (centered headline + sub + primary button linking to Studio/Admin as appropriate).

- [ ] **Step 3.2.10: Verify chat in browser**

```bash
make rebuild
```

Open `http://localhost:8484/#chat`. Confirm:
- Sessions list shows on the left at 280px width
- Clicking a session loads the convo
- Tool calls render as collapsible blocks; click to expand
- Composer renders with rounded box; focus shows accent halo
- Send a test message (with the mock provider configured) — verify the WebSocket flow works
- New-session button creates a new session

- [ ] **Step 3.2.11: Commit chat JS**

```bash
git add the_one/interfaces/web/static/js/areas/chat.js the_one/interfaces/web/static/js/areas/chat/
git commit -m "L3.2: chat.js — emit Holograph DOM; preserve WebSocket + tool-call behavior"
```

### Task 3.3: Update chat flow tests

- [ ] **Step 3.3.1: Update selectors in `test_flow_chat.py`**

Run the test once to see what's failing:

```bash
docker exec the-one pytest tests/browser/test_flow_chat.py -x -q --tb=short 2>&1 | head -40
```

Look at failures. They'll mention selectors like `.app-picker-button`, `.sidebar-panel`, `.chat-input-textarea`, etc. Map each to the new selector:

| Old selector | New selector |
|---|---|
| `.app-picker-button[data-area="chat"]` | `.navlink[data-area="chat"]` |
| `#app-sidebar .sidebar-panel.area-chat` | `#main-content .area-chat .sessions-pane` |
| `.sidebar-item.session-item` | `.session-card` |
| `.sidebar-item.session-item.active` | `.session-card.active` |
| `.chat-input-textarea` | `.composer-input` |
| `.chat-send-button` | `.composer .btn-primary[data-action="send"]` |
| `.message-bubble.user` | `.msg-row.user` |
| `.message-bubble.agent` | `.msg-row:not(.user)` |
| `.tool-call-block` | `.toolcall` |

Edit `test_flow_chat.py` to use the new selectors. Same pattern for `test_flow_streaming.py`, `test_flow_new_chat.py`, `test_flow_markdown_chat.py`, `test_flow_picker.py` (chat-side selectors), `test_markdown.py`.

- [ ] **Step 3.3.2: Run chat tests**

```bash
docker exec the-one pytest tests/browser/test_flow_chat.py tests/browser/test_flow_streaming.py tests/browser/test_flow_new_chat.py tests/browser/test_flow_markdown_chat.py tests/browser/test_flow_picker.py tests/browser/test_markdown.py -x -q
```

Expected: all pass. If any fail with selector errors not in the table above, add the new selector to the table and update the test.

- [ ] **Step 3.3.3: Commit test updates**

```bash
git add tests/browser/test_flow_chat.py tests/browser/test_flow_streaming.py tests/browser/test_flow_new_chat.py tests/browser/test_flow_markdown_chat.py tests/browser/test_flow_picker.py tests/browser/test_markdown.py
git commit -m "L3.3: chat flow tests — Holograph selectors"
```

### Task 3.4: L3 acceptance

- [ ] **Step 3.4.1: All chat tests pass**

```bash
docker exec the-one pytest tests/browser/test_flow_chat.py tests/browser/test_flow_streaming.py tests/browser/test_flow_new_chat.py tests/browser/test_flow_markdown_chat.py tests/browser/test_flow_picker.py tests/browser/test_markdown.py tests/test_markdown.py -q
```

Expected: all pass.

- [ ] **Step 3.4.2: Manual Chat smoke**

Open `http://localhost:8484/#chat` and:
- Create new session
- Send a message via mock provider
- See agent response render in the convo stream
- Expand a tool-call block (if any) and see args/result
- Verify telemetry chip updates with context usage

---

## L4 — Studio area + sub-nav

**Files:**
- Replace: `the_one/interfaces/web/static/css/studio.css`
- Modify: `the_one/interfaces/web/static/js/areas/studio.js` (render `.studio-subnav` + 3 `.studio-sub` blocks)
- Modify: `the_one/interfaces/web/static/js/areas/studio/agent-editor.js`
- Modify: `the_one/interfaces/web/static/js/areas/studio/general-tab.js`
- Modify: `the_one/interfaces/web/static/js/areas/studio/tools-tab.js`
- Modify: `the_one/interfaces/web/static/js/areas/studio/mcps-tab.js`
- Modify: `the_one/interfaces/web/static/js/areas/studio/mcp-servers-grid.js`
- Modify: `the_one/interfaces/web/static/js/areas/studio/mcp-server-editor.js` (the 1,654-line file — style updates only; OAuth Reset preserved; `__MASKED__` contract preserved)
- Modify: `the_one/interfaces/web/static/js/areas/studio/knowledge-tab.js`
- Modify: `the_one/interfaces/web/static/js/areas/studio/stub-knowledge.js`
- Modify (selectors): all `tests/browser/test_flow_agent_*.py`, `test_flow_studio_*.py`, `test_studio_mcps_tab.py`, `test_mcp_test_connection_button.py`

### Task 4.1: Rewrite `studio.css`

- [ ] **Step 4.1.1: Replace `studio.css` with mockup-verbatim styles**

Copy the studio-specific section from `playground/mockups/holograph.html` lines 584–796 into `the_one/interfaces/web/static/css/studio.css`. Wrap in `@layer areas { ... }`.

Covered selectors: `.studio-layout`, `.agents-pane`, `.agents-list`, `.agent-card` (+ `.selected`), `.agent-card-avatar`, `.agent-card-body`, `.agent-card-title`, `.agent-card-model`, `.agent-card-meta`, `.editor-pane`, `.editor-header`, `.editor-title-row`, `.editor-title`, `.editor-actions`, `.editor-sub`, `.editor-body`, `.editor-section`.

Add NEW selectors (not in mockup) for `.studio-subnav` (styling alias of `.holograph-section-nav`), `.studio-sub`, `.knowledge-stub-pane`, `.mcp-sources-grid`, `.mcp-source-card`, `.mcp-source-head`, `.mcp-source-body`, `.mcp-source-editor-pane`:

```css
@layer areas {
  /* ... mockup-verbatim rules above ... */

  /* Studio sub-nav — styling alias of .holograph-section-nav */
  .studio-subnav { /* relies on shared .holograph-section-nav rules from components.css */ }
  .studio-sub { display: none; }
  .studio-sub.active { display: block; }

  /* Knowledge stub */
  .knowledge-stub-pane {
    background: var(--surface);
    border: 1px solid var(--hairline);
    border-radius: var(--radius-card);
    box-shadow: var(--shadow-1);
    padding: 80px 32px;
    text-align: center;
    max-width: 560px;
    margin: 32px auto;
  }
  .knowledge-stub-pane h2 {
    font-size: 18px;
    font-weight: 600;
    letter-spacing: -0.01em;
    margin-bottom: 6px;
  }
  .knowledge-stub-pane p {
    color: var(--fg-mute);
    font-size: 13px;
    margin-bottom: 20px;
  }

  /* MCP Sources grid */
  .mcp-sources-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 16px;
  }
  .mcp-source-card {
    background: var(--surface);
    border: 1px solid var(--hairline);
    border-radius: var(--radius-card);
    box-shadow: var(--shadow-1);
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 12px;
    cursor: pointer;
    transition: box-shadow var(--t), border-color var(--t);
  }
  .mcp-source-card:hover { box-shadow: var(--shadow-2); border-color: var(--hairline-strong); }
  .mcp-source-card.selected { border-color: var(--accent); box-shadow: var(--shadow-2); }
  .mcp-source-head { display: flex; align-items: center; gap: 10px; }
  .mcp-source-body { color: var(--fg-mute); font-size: 12.5px; }
  .mcp-source-editor-pane {
    background: var(--surface);
    border: 1px solid var(--hairline);
    border-radius: var(--radius-card);
    box-shadow: var(--shadow-1);
  }
}
```

- [ ] **Step 4.1.2: Commit**

```bash
git add the_one/interfaces/web/static/css/studio.css
git commit -m "L4.1: studio.css — Holograph studio styles + sub-nav + MCP cards"
```

### Task 4.2: Rewrite `studio.js` top-level render with sub-nav

- [ ] **Step 4.2.1: Read existing `studio.js` init + render**

```bash
sed -n '1,120p' the_one/interfaces/web/static/js/areas/studio.js
sed -n '250,320p' the_one/interfaces/web/static/js/areas/studio.js
```

Identify where the sub-nav currently renders (line 285 — `App.layout.renderSectionNav(sectionNavEl, ...)`) and where each section's content renders.

- [ ] **Step 4.2.2: Update `init` to new signature + render sub-nav shell**

```js
init: function (content) {
  this._content = content;
  content.innerHTML =
    '<div class="area-header">' +
      '<div>' +
        '<span class="area-title">Studio</span>' +
        '<span class="area-sub">Configure and edit your agents</span>' +
      '</div>' +
      '<button class="btn btn-primary" id="studio-new-agent-btn">' +
        '<svg class="icn icn-sm" viewBox="0 0 12 12"><path d="M6 2v8M2 6h8" stroke="currentColor" stroke-width="1.6"/></svg>' +
        'New agent' +
      '</button>' +
    '</div>' +
    '<div class="studio-subnav" id="studio-subnav"></div>' +
    '<div class="studio-sub" id="sub-agents"></div>' +
    '<div class="studio-sub" id="sub-knowledge"></div>' +
    '<div class="studio-sub" id="sub-mcp-sources"></div>';

  // Wire sub-nav via existing App.layout.renderSectionNav (preserved API).
  var self = this;
  App.layout.renderSectionNav(
    document.getElementById('studio-subnav'),
    [
      { id: 'agents', label: 'Agents' },
      { id: 'knowledge', label: 'Knowledge' },
      { id: 'mcp-sources', label: 'MCP Sources' }
    ],
    this._activeSection || 'agents',
    {
      ariaLabel: 'Studio sections',
      onChange: function (sectionId) { self._setActiveSection(sectionId); }
    }
  );

  // Initial sub-render (preserves existing _renderAgents / _renderKnowledgeStub / _renderMcpSources logic)
  this._renderAgentsSub();
  this._renderKnowledgeSub();
  this._renderMcpSourcesSub();
  this._setActiveSection(this._activeSection || 'agents');
},

_setActiveSection: function (sectionId) {
  this._activeSection = sectionId;
  ['agents', 'knowledge', 'mcp-sources'].forEach(function (sid) {
    var el = document.getElementById('sub-' + sid);
    if (el) el.classList.toggle('active', sid === sectionId);
  });
  App.layout.updateActiveSection(document.getElementById('studio-subnav'), sectionId);
  // Update URL via existing _writeUrl logic
  if (typeof this._writeUrl === 'function') this._writeUrl();
},
```

Preserve all existing `hydrateState`, `serializeState`, `confirmLeave` logic — only the rendered DOM changes.

- [ ] **Step 4.2.3: Update `_renderAgentsSub` to render Agents-section content**

```js
_renderAgentsSub: function () {
  var el = document.getElementById('sub-agents');
  el.innerHTML =
    '<div class="studio-layout">' +
      '<aside class="agents-pane">' +
        '<div class="sessions-header"><h3>Agents</h3></div>' +
        '<div class="agents-list" id="studio-agents-list"></div>' +
      '</aside>' +
      '<div class="editor-pane" id="studio-editor-pane">' +
        // editor renders here on agent select; empty state otherwise
      '</div>' +
    '</div>';
  this._loadAgents();
},
```

- [ ] **Step 4.2.4: Update `_renderKnowledgeSub`**

```js
_renderKnowledgeSub: function () {
  var el = document.getElementById('sub-knowledge');
  el.innerHTML =
    '<div class="knowledge-stub-pane" data-testid="studio-knowledge-stub">' +
      '<h2>Knowledge base coming soon</h2>' +
      '<p>This area will let you attach documents, snippets, and references that agents can search.</p>' +
      '<button class="btn" disabled>Coming soon</button>' +
    '</div>';
},
```

(Preserve the `data-testid="studio-knowledge-stub"` attribute — flow tests assert on it.)

- [ ] **Step 4.2.5: Update `_renderMcpSourcesSub`**

```js
_renderMcpSourcesSub: function () {
  var el = document.getElementById('sub-mcp-sources');
  el.innerHTML =
    '<div class="mcp-sources-grid" id="studio-mcp-sources-grid"></div>';
  this._loadMcpSources();   // existing logic
},
```

The existing `mcp-servers-grid.js` provides the grid render. Update its emitted markup to use `.mcp-source-card` / `.mcp-source-head` / `.mcp-source-body` per Task 4.4 below.

- [ ] **Step 4.2.6: Update agent-card render**

In `studio.js` (or wherever the agents list is rendered — likely a method on the studio area object or a helper):

```js
function renderAgentCard(agent, isSelected) {
  return (
    '<div class="agent-card' + (isSelected ? ' selected' : '') + '" data-agent-name="' + escapeHtml(agent.name) + '">' +
      '<div class="agent-card-avatar">' + escapeHtml(agent.avatar_initial || agent.name.charAt(0).toUpperCase()) + '</div>' +
      '<div class="agent-card-body">' +
        '<div class="agent-card-title">' + escapeHtml(agent.name) + '</div>' +
        '<div class="agent-card-model">' + escapeHtml(agent.provider_type || '') + ' · ' + escapeHtml(agent.llm_model || '') + '</div>' +
        '<div class="agent-card-meta">' +
          '<span>' + (agent.enabled_tools_count || 0) + ' tools</span><span>·</span>' +
          '<span>used ' + formatRelativeTime(agent.last_used_at) + '</span>' +
        '</div>' +
      '</div>' +
    '</div>'
  );
}
```

- [ ] **Step 4.2.7: Update agent-editor render**

Open `agent-editor.js`. The header → tab strip → body shape needs to match the mockup. The tabs are `General | Tools | MCPs | Tool Overrides`.

```js
function renderEditor(agent) {
  return (
    '<div class="editor-header">' +
      '<div class="editor-title-row">' +
        '<span class="editor-title">' + escapeHtml(agent.name) + '</span>' +
        '<span class="chip">' + (agent.enabled_tools_count || 0) + ' tools</span>' +
        '<span class="chip mono">' + escapeHtml(agent.llm_model || '') + '</span>' +
        '<div class="editor-actions">' +
          '<button class="btn btn-ghost" data-action="duplicate">Duplicate</button>' +
          '<button class="btn" data-action="save">Save</button>' +
        '</div>' +
      '</div>' +
      '<div class="editor-sub">Edited ' + formatRelativeTime(agent.updated_at) + '</div>' +
    '</div>' +
    '<div class="tabs" data-agent-tabs>' +
      '<div class="tab' + (activeTab === 'general' ? ' active' : '') + '" data-tab="general">General</div>' +
      '<div class="tab' + (activeTab === 'tools' ? ' active' : '') + '" data-tab="tools">Tools</div>' +
      '<div class="tab' + (activeTab === 'mcps' ? ' active' : '') + '" data-tab="mcps">MCPs</div>' +
      '<div class="tab' + (activeTab === 'overrides' ? ' active' : '') + '" data-tab="overrides">Tool Overrides</div>' +
    '</div>' +
    '<div class="editor-body" id="agent-editor-body"></div>'
  );
}
```

- [ ] **Step 4.2.8: Update general-tab, tools-tab, mcps-tab render outputs**

For each per-tab file, replace the existing form rendering with `.form-row` / `.form-label` / `.form-help` / `.form-control` / `.section-label` markup per the mockup.

Example for `general-tab.js`:

```js
function renderGeneralTab(agent) {
  return (
    '<div class="editor-section">' +
      '<div class="section-label">Identity</div>' +
      '<div class="form-row">' +
        '<div>' +
          '<div class="form-label">Name</div>' +
          '<div class="form-help">Shown in agent picker and chat headers.</div>' +
        '</div>' +
        '<input class="form-control" data-field="name" value="' + escapeAttr(agent.name) + '">' +
      '</div>' +
      // ... avatar, provider, model, system prompt, behavior toggles
    '</div>'
  );
}
```

For `tools-tab.js`: render `.tools-grid` of `.tool-card` instances per agent.

For `mcps-tab.js`: render the list of attached MCP sources as `.mcp-source-card` instances. Click → navigate to `#studio/agents/{name}/mcps/{source-id}` (preserves F8 L3 deep-link). Add a sub-render for the per-agent attachment editor (per spec §"Per-agent MCP attachment editor").

For `overrides` tab (no dedicated file — likely inline in `agent-editor.js`): render the marker-dispatched override widgets via `tools-form-helpers.js`. Only styling changes.

- [ ] **Step 4.2.9: Commit studio.js + per-tab updates**

```bash
git add the_one/interfaces/web/static/js/areas/studio.js the_one/interfaces/web/static/js/areas/studio/agent-editor.js the_one/interfaces/web/static/js/areas/studio/general-tab.js the_one/interfaces/web/static/js/areas/studio/tools-tab.js the_one/interfaces/web/static/js/areas/studio/mcps-tab.js the_one/interfaces/web/static/js/areas/studio/knowledge-tab.js the_one/interfaces/web/static/js/areas/studio/stub-knowledge.js
git commit -m "L4.2: studio.js — sub-nav + agent editor + tabs Holograph markup"
```

### Task 4.3: Restyle MCP server editor

- [ ] **Step 4.3.1: Read the existing `mcp-server-editor.js` Reset-button code**

```bash
sed -n '300,360p' the_one/interfaces/web/static/js/areas/studio/mcp-server-editor.js
```

Confirm the single "Reset connection" button at line 343-345 with data-testid `reset-mcp-connection-btn`. Preserve verbatim.

- [ ] **Step 4.3.2: Restyle button classes (markup only)**

Find the existing `.btn-outlined-primary` class on the Reset button. Replace with `.btn` (Holograph's outlined-primary equivalent). Keep all other attributes (data-testid, aria-label, title, data-confirm-title).

```js
// BEFORE
html += '<button type="button" class="btn-outlined-primary mcp-reset-connection-btn" ...';

// AFTER
html += '<button type="button" class="btn mcp-reset-connection-btn" ...';
```

Apply the same `.btn-outlined-primary` → `.btn` rename throughout the file. Keep `.btn-filled-primary` → `.btn-primary`, `.btn-muted-destructive` → `.btn-ghost` (or `.btn-primary.danger` for the actual delete-source button).

- [ ] **Step 4.3.3: Restyle form rows**

Find every form row / input render in the file. Convert to `.form-row` + `.form-label` + `.form-help` + `.form-control` shape per mockup. This is mostly a class-rename refactor — the field count and validation logic are preserved.

- [ ] **Step 4.3.4: Verify `__MASKED__` contract still works**

Don't touch the submit handler or the GET-mask handler — just the form CSS. After rebuild:

```bash
make rebuild
docker exec the-one pytest tests/browser/test_flow_studio_mcp_editor.py -x -q
```

Expected: PASS (with selectors updated in Task 4.5).

- [ ] **Step 4.3.5: Commit**

```bash
git add the_one/interfaces/web/static/js/areas/studio/mcp-server-editor.js the_one/interfaces/web/static/js/areas/studio/mcp-servers-grid.js
git commit -m "L4.3: MCP server editor + grid — Holograph form vocabulary; Reset preserved"
```

### Task 4.4: Add per-agent MCP attachment editor

Per spec §"Per-agent MCP attachment editor" — opens via deep-link `#studio/agents/{name}/mcps/{source-id}` inside the MCPs tab.

- [ ] **Step 4.4.1: Read existing mcps-tab.js + studio.js hydrate path**

```bash
grep -n "mcps/" the_one/interfaces/web/static/js/areas/studio.js | head
grep -n "_selectedMcpAgentSourceId" the_one/interfaces/web/static/js/areas/studio.js | head
```

Identify where the deep-link is parsed (already in `hydrateState`) and where the per-attachment editor would mount.

- [ ] **Step 4.4.2: Render attachment editor when `_selectedMcpAgentSourceId` is set**

Add to `mcps-tab.js`:

```js
function renderAttachmentEditor(sourceId, attachment, parentSource) {
  return (
    '<div class="editor-section" data-testid="agent-mcp-attachment-editor">' +
      '<div style="display:flex;align-items:center;gap:10px;margin-bottom:14px;">' +
        '<button class="btn btn-ghost" data-action="back" aria-label="Back to attachments">' +
          '<svg class="icn" viewBox="0 0 16 16"><path d="M10 4l-4 4 4 4" stroke="currentColor" stroke-width="1.6"/></svg>' +
        '</button>' +
        '<span class="editor-title" style="font-size:15px;">' + escapeHtml(parentSource.name) + '</span>' +
        '<span class="chip">' + escapeHtml(parentSource.transport) + '</span>' +
      '</div>' +

      (parentSource.auth_required ?
        '<div class="callout warn" style="margin-bottom:14px;">' +
          'This source requires authorization. ' +
          '<a href="#studio/mcp-sources/' + encodeURIComponent(sourceId) + '">Connect on the MCP Sources page</a>.' +
        '</div>' : '') +

      '<div class="section-label">Tools mode</div>' +
      '<div class="seg" style="margin-bottom:18px;" data-attachment-mode>' +
        '<button class="seg-btn' + (attachment.mode === 'allowlist' ? ' active' : '') + '" data-mode="allowlist">Allowlist</button>' +
        '<button class="seg-btn' + (attachment.mode === 'denylist' ? ' active' : '') + '" data-mode="denylist">Denylist</button>' +
      '</div>' +

      '<div class="section-label">Cached tools (' + (parentSource.cached_tools || []).length + ')</div>' +
      '<div class="tools-grid">' +
        (parentSource.cached_tools || []).map(function (t) {
          var enabled = attachment.mode === 'allowlist'
            ? (attachment.tools || []).indexOf(t.name) !== -1
            : (attachment.tools || []).indexOf(t.name) === -1;
          return (
            '<div class="tool-card">' +
              '<div class="tool-head">' +
                '<span class="tool-name">' + escapeHtml(t.name) + '</span>' +
                '<div class="tool-toggle-wrap"><div class="toggle' + (enabled ? ' on' : '') + '" data-tool-toggle="' + escapeAttr(t.name) + '"></div></div>' +
              '</div>' +
              '<div class="tool-desc">' + escapeHtml(t.description || '') + '</div>' +
            '</div>'
          );
        }).join('') +
      '</div>'
    '</div>'
  );
}
```

Wire the back-button to navigate to `#studio/agents/{name}/mcps` (clear the source-id from URL); wire the mode segments + tool toggles to update the agent's attachment record via `PUT /api/agents/{name}/mcp-sources/{source-id}`.

- [ ] **Step 4.4.3: Verify deep-link works**

```bash
make rebuild
```

Navigate to `http://localhost:8484/#studio/agents/Researcher/mcps/some-source-id` (use a real agent + source from your local DB). Confirm:
- The editor renders inline in the MCPs tab
- Back-button navigates back to `#studio/agents/Researcher/mcps`
- Tool toggles persist on refresh

- [ ] **Step 4.4.4: Commit**

```bash
git add the_one/interfaces/web/static/js/areas/studio/mcps-tab.js
git commit -m "L4.4: per-agent MCP attachment editor — deep-link rendering"
```

### Task 4.5: Update Studio flow tests

- [ ] **Step 4.5.1: Run all Studio flow tests and collect selector failures**

```bash
docker exec the-one pytest tests/browser/test_flow_agent_crud.py tests/browser/test_flow_agent_tabs.py tests/browser/test_flow_agent_tile.py tests/browser/test_flow_studio_navigation.py tests/browser/test_flow_studio_mcp_editor.py tests/browser/test_flow_studio_mcp_navigation.py tests/browser/test_flow_studio_openrouter_picker.py tests/browser/test_flow_studio_tools_overrides.py tests/browser/test_studio_mcps_tab.py tests/browser/test_mcp_test_connection_button.py -x -q --tb=short 2>&1 | head -60
```

- [ ] **Step 4.5.2: Map old selectors to new (per file)**

Standard selector map for Studio:

| Old selector | New selector |
|---|---|
| `#app-sidebar .sidebar-panel.area-studio` | `#main-content .area-studio .agents-pane` |
| `.studio-sidebar-section-nav` | `#studio-subnav.studio-subnav` (or `.holograph-section-nav`) |
| `.studio-sidebar-section-item[data-section-id="agents"]` | `.holograph-section-item[data-section-id="agents"]` |
| `.studio-agent-tile` | `.agent-card` |
| `.studio-agent-tile.selected` | `.agent-card.selected` |
| `.studio-editor-tab[data-tab="general"]` | `.tab[data-tab="general"]` |
| `.studio-editor-field[data-field-name="X"]` | `.form-control[data-field="X"]` (or similar — verify) |
| `.studio-knowledge-stub` | `[data-testid="studio-knowledge-stub"]` |
| `.mcp-source-tile` | `.mcp-source-card` |
| `.btn-outlined-primary[data-testid="reset-mcp-connection-btn"]` | `.btn[data-testid="reset-mcp-connection-btn"]` |

Update each test file accordingly.

- [ ] **Step 4.5.3: Run tests; iterate until green**

```bash
docker exec the-one pytest tests/browser/test_flow_agent_crud.py tests/browser/test_flow_agent_tabs.py tests/browser/test_flow_agent_tile.py tests/browser/test_flow_studio_navigation.py tests/browser/test_flow_studio_mcp_editor.py tests/browser/test_flow_studio_mcp_navigation.py tests/browser/test_flow_studio_openrouter_picker.py tests/browser/test_flow_studio_tools_overrides.py tests/browser/test_studio_mcps_tab.py tests/browser/test_mcp_test_connection_button.py -x -q
```

Expected: all pass after selector updates.

- [ ] **Step 4.5.4: Commit**

```bash
git add tests/browser/test_flow_agent_*.py tests/browser/test_flow_studio_*.py tests/browser/test_studio_mcps_tab.py tests/browser/test_mcp_test_connection_button.py
git commit -m "L4.5: Studio flow tests — Holograph selectors"
```

### Task 4.6: L4 acceptance

- [ ] **Step 4.6.1: Manual Studio smoke**

Browse to `#studio` and:
- Verify three-section sub-nav renders: Agents / Knowledge / MCP Sources
- Click each — content swaps
- Knowledge stub renders the centered card
- MCP Sources grid renders
- Click an agent → editor opens with 4 tabs (General / Tools / MCPs / Tool Overrides)
- Test `__MASKED__` round-trip: edit an MCP source with a secret → save without changing it → reload editor → secret should still show masked tail (backend round-trip preserved)
- Test the per-agent attachment editor: navigate to `#studio/agents/{name}/mcps/{id}` deep-link → editor renders → back-button works

---

## L5 — Admin area

**Files:**
- Replace: `the_one/interfaces/web/static/css/admin.css`
- Modify: `the_one/interfaces/web/static/js/areas/admin.js` (render area-header + admin-subnav + 3 admin-sub blocks; preserve `system → general` redirect)
- Modify: `the_one/interfaces/web/static/js/areas/admin/providers-grid.js`
- Modify: `the_one/interfaces/web/static/js/areas/admin/provider-editor.js`
- Modify: `the_one/interfaces/web/static/js/areas/admin/provider-models.js`
- Modify: `the_one/interfaces/web/static/js/areas/admin/tools-grid.js`
- Modify: `the_one/interfaces/web/static/js/areas/admin/tools-form-helpers.js`
- Modify: `the_one/interfaces/web/static/js/areas/admin/tools-editor.js`
- Modify: `the_one/interfaces/web/static/js/areas/admin/system-page.js`
- Delete: `the_one/interfaces/web/static/js/areas/admin/design-language-page.js` and all of `the_one/interfaces/web/static/js/areas/admin/design-language/`
- Modify (selectors): `test_flow_admin_*.py`, `test_flow_provider_*.py`

### Task 5.1: Rewrite `admin.css`

- [ ] **Step 5.1.1: Replace `admin.css` with mockup-verbatim styles**

Copy the admin-specific section from `playground/mockups/holograph.html` lines 791–1011 into `the_one/interfaces/web/static/css/admin.css`. Wrap in `@layer areas { ... }`.

Covered selectors: `.admin-subnav` (styling alias of `.holograph-section-nav`), `.subnav-item`, `.providers-grid`, `.provider-card` (+ `.selected`, `.expanded`), `.provider-head`, `.provider-logo`, `.provider-name`, `.provider-type`, `.provider-body`, `.provider-expanded-body`, `.provider-status`, `.stat-label`, `.stat-value` (+ `.mono`), `.tools-section`, `.tools-section-head`, `.tools-section-title`, `.tools-section-meta`, `.tools-grid`, `.tool-card` (+ `.disabled`), `.tool-head`, `.tool-name`, `.tool-toggle-wrap`, `.tool-desc`, `.general-grid`, `.general-card`, `.general-card-title`, `.general-card-sub`.

Add `.admin-sub` for tab-content sectioning + the expanded-state grid behavior:

```css
@layer areas {
  /* ... mockup-verbatim rules above ... */

  .admin-sub { display: none; }
  .admin-sub.active { display: block; }

  /* Provider expanded state — span 2 columns inside the 3-col grid */
  .provider-card.expanded { grid-column: span 2; cursor: default; }
  .provider-card.expanded:hover { box-shadow: var(--shadow-2); }
}
```

- [ ] **Step 5.1.2: Commit**

```bash
git add the_one/interfaces/web/static/css/admin.css
git commit -m "L5.1: admin.css — Holograph admin styles + provider grid + tools grid"
```

### Task 5.2: Rewrite `admin.js` top-level render

- [ ] **Step 5.2.1: Update init + render area-header + sub-nav + sub blocks**

Open `admin.js`. Change `init(sidebar, content)` to `init(content)`. Render:

```js
init: function (content) {
  this._content = content;
  content.innerHTML =
    '<div class="area-header">' +
      '<div>' +
        '<span class="area-title">Administration</span>' +
        '<span class="area-sub">Providers, built-in tools, and general settings</span>' +
      '</div>' +
    '</div>' +
    '<div class="admin-subnav" id="admin-subnav"></div>' +
    '<div class="admin-sub" id="sub-providers"></div>' +
    '<div class="admin-sub" id="sub-tools"></div>' +
    '<div class="admin-sub" id="sub-general"></div>';

  var self = this;
  App.layout.renderSectionNav(
    document.getElementById('admin-subnav'),
    [
      { id: 'providers', label: 'Providers' },
      { id: 'tools', label: 'Built-in Tools' },
      { id: 'general', label: 'General' }
    ],
    this._activeSub || 'providers',
    {
      ariaLabel: 'Admin sections',
      onChange: function (subId) { self._setActiveSub(subId); }
    }
  );

  this._renderProvidersSub();
  this._renderToolsSub();
  this._renderGeneralSub();
  this._setActiveSub(this._activeSub || 'providers');
},

_setActiveSub: function (subId) {
  this._activeSub = subId;
  ['providers', 'tools', 'general'].forEach(function (sid) {
    var el = document.getElementById('sub-' + sid);
    if (el) el.classList.toggle('active', sid === subId);
  });
  App.layout.updateActiveSection(document.getElementById('admin-subnav'), subId);
  if (typeof this._writeUrl === 'function') this._writeUrl();
},
```

**Preserve `hydrateState` with the existing `system → general` redirect** (admin.js:48-54). Do NOT remove the redirect:

```js
hydrateState: function (sub) {
  // ... existing redirect (preserved verbatim) ...
  if (sub === 'system') sub = 'general';
  // ... rest of existing hydrate logic ...
  this._setActiveSub(sub || 'general');
},
```

- [ ] **Step 5.2.2: Update `_renderProvidersSub` to use `.providers-grid`**

```js
_renderProvidersSub: function () {
  var el = document.getElementById('sub-providers');
  el.innerHTML = '<div class="providers-grid" id="admin-providers-grid"></div>';
  this._loadProviders();
},
```

The grid render (in `providers-grid.js`) emits `.provider-card` instances + a trailing dashed "Add provider" card per mockup.

- [ ] **Step 5.2.3: Update `_renderToolsSub` to use `.tools-section` groupings**

```js
_renderToolsSub: function () {
  var el = document.getElementById('sub-tools');
  el.innerHTML =
    '<div class="tools-section" data-category="filesystem">' +
      '<div class="tools-section-head">' +
        '<div class="tools-section-title">Filesystem</div>' +
        '<div class="tools-section-meta" id="tools-meta-filesystem"></div>' +
      '</div>' +
      '<div class="tools-grid" id="tools-grid-filesystem"></div>' +
    '</div>' +
    '<div class="tools-section" data-category="execution">' +
      '<div class="tools-section-head">' +
        '<div class="tools-section-title">Execution</div>' +
        '<div class="tools-section-meta" id="tools-meta-execution"></div>' +
      '</div>' +
      '<div class="tools-grid" id="tools-grid-execution"></div>' +
    '</div>' +
    '<div class="tools-section" data-category="web">' +
      '<div class="tools-section-head">' +
        '<div class="tools-section-title">Web</div>' +
        '<div class="tools-section-meta" id="tools-meta-web"></div>' +
      '</div>' +
      '<div class="tools-grid" id="tools-grid-web"></div>' +
    '</div>';
  this._loadTools();
},
```

- [ ] **Step 5.2.4: Update `_renderGeneralSub` to use `.general-grid` + `.general-card`**

```js
_renderGeneralSub: function () {
  var el = document.getElementById('sub-general');
  el.innerHTML = '<div class="general-grid" id="admin-general-grid"></div>';
  this._loadSystemPage();   // existing system-page.js fills the grid
},
```

`system-page.js` populates the grid with 4 cards: Appearance (theme `.seg`), Encryption (fingerprint + Rotate button), Base prompt (read-only textarea), System info (mono key/value list).

- [ ] **Step 5.2.5: Delete design-language page + directory**

```bash
rm -rf the_one/interfaces/web/static/js/areas/admin/design-language/
rm the_one/interfaces/web/static/js/areas/admin/design-language-page.js
```

Also remove their script tags from `index.html` (should already be absent from the L2 rewrite — verify).

Also remove any `design-language` entry from the section-nav items list in `admin.js`.

- [ ] **Step 5.2.6: Commit admin.js + delete design-language**

```bash
git add the_one/interfaces/web/static/js/areas/admin.js
git rm -r the_one/interfaces/web/static/js/areas/admin/design-language/
git rm the_one/interfaces/web/static/js/areas/admin/design-language-page.js
git commit -m "L5.2: admin.js — Holograph subnav + 3 sub blocks; design-language page removed"
```

### Task 5.3: Update per-component admin renderers

- [ ] **Step 5.3.1: Update providers-grid.js**

Change the emitted markup to `.provider-card` shape per mockup (provider-head + provider-body 2x2 stat grid + status footer). Clicking a card sets `.selected` and opens the editor in-place via `.expanded` (col-span-2):

```js
function renderProviderCard(provider, isSelected, isExpanded) {
  var classes = ['provider-card'];
  if (isSelected) classes.push('selected');
  if (isExpanded) classes.push('expanded');
  return (
    '<div class="' + classes.join(' ') + '" data-provider-id="' + escapeAttr(provider.id) + '">' +
      '<div class="provider-head">' +
        '<div class="provider-logo">' + escapeHtml(provider.short_label || provider.type.slice(0, 2).toUpperCase()) + '</div>' +
        '<div>' +
          '<div class="provider-name">' + escapeHtml(provider.name) + '</div>' +
          '<div class="provider-type">' + escapeHtml(provider.type) + '</div>' +
        '</div>' +
        (isSelected ? '<span class="chip accent" style="margin-left:auto;">Editing</span>' : '') +
      '</div>' +
      '<div class="provider-body">' +
        '<div><div class="stat-label">Models</div><div class="stat-value">' + (provider.model_count || 0) + ' discovered</div></div>' +
        '<div><div class="stat-label">Last tested</div><div class="stat-value mono">' + formatRelativeTime(provider.last_tested_at) + '</div></div>' +
        '<div><div class="stat-label">Used by</div><div class="stat-value">' + (provider.used_by_count || 0) + ' agents</div></div>' +
        '<div><div class="stat-label">Status</div><div class="stat-value"><span class="provider-status"><span class="dot ' + (provider.connected ? 'live' : 'warn') + '"></span> ' + (provider.connected ? 'Connected' : 'Stale') + '</span></div></div>' +
      '</div>' +
      (isExpanded ? renderProviderExpandedBody(provider) : '') +
    '</div>'
  );
}
```

- [ ] **Step 5.3.2: Update provider-editor.js**

Inside `.provider-expanded-body`, render the editor form using `.form-row` + `.form-control` shape per mockup. **Preserve the `__MASKED__` sentinel for `api_key` field**:

```js
// In the form construction:
'<div class="form-row">' +
  '<div><div class="form-label">API Key</div><div class="form-help">Leave as ' + maskedTail(provider.api_key) + ' to keep current.</div></div>' +
  '<input class="form-control" data-field="api_key" value="__MASKED__" type="password">' +
'</div>'
```

The submit handler must continue sending `__MASKED__` when the operator hasn't modified the field (backend preserves the existing key per the API contract).

- [ ] **Step 5.3.3: Update tools-grid.js**

Group tool cards by category. Per category section, render `.tools-grid` with `.tool-card` per tool:

```js
function renderToolCard(tool, isEnabled) {
  return (
    '<div class="tool-card' + (isEnabled ? '' : ' disabled') + '" data-tool-name="' + escapeAttr(tool.name) + '">' +
      '<div class="tool-head">' +
        '<span class="tool-name">' + escapeHtml(tool.name) + '</span>' +
        '<div class="tool-toggle-wrap"><div class="toggle' + (isEnabled ? ' on' : '') + '" data-tool-toggle></div></div>' +
      '</div>' +
      '<div class="tool-desc">' + escapeHtml(tool.description) + '</div>' +
    '</div>'
  );
}
```

Click on the card body opens the tool config modal (via `tools-editor.js`).

- [ ] **Step 5.3.4: Update tools-editor.js to open as a modal**

Convert the tool-editor from inline rendering to a modal opening flow. Use the `.modal-shell` from `components.css`.

Reuse the existing form-render logic (marker-dispatched widgets via `tools-form-helpers.js`); only the modal wrapper is new.

- [ ] **Step 5.3.5: Update tools-form-helpers.js — markup only**

The widget renderer is shared between Admin (operator-mode) and Studio (agent-mode). Only the class names change. Preserve all marker dispatch logic.

- [ ] **Step 5.3.6: Update system-page.js**

Render 4 cards inside `.general-grid`:

```js
function renderSystemPage() {
  return (
    '<div class="general-card">' +
      '<div class="general-card-title">Appearance</div>' +
      '<div class="general-card-sub">Theme preference applies across the app.</div>' +
      '<div id="admin-theme-toggle"></div>' +
    '</div>' +
    '<div class="general-card">' +
      '<div class="general-card-title">Encryption</div>' +
      '<div class="general-card-sub">Symmetric key used for stored credentials.</div>' +
      // existing fingerprint + rotate button
    '</div>' +
    '<div class="general-card">' +
      '<div class="general-card-title">Base prompt</div>' +
      '<div class="general-card-sub">Layered beneath every agent\'s system prompt.</div>' +
      // existing readonly textarea
    '</div>' +
    '<div class="general-card">' +
      '<div class="general-card-title">System info</div>' +
      '<div class="general-card-sub">Schema, storage, uptime.</div>' +
      // existing mono key/value list
    '</div>'
  );
}
```

Wire `App.theme.renderToggle(document.getElementById('admin-theme-toggle'))` into the Appearance card.

- [ ] **Step 5.3.7: Commit admin per-component renderers**

```bash
git add the_one/interfaces/web/static/js/areas/admin/
git commit -m "L5.3: admin renderers — provider/tools/system Holograph markup"
```

### Task 5.4: Update Admin flow tests

- [ ] **Step 5.4.1: Map old selectors to new**

| Old selector | New selector |
|---|---|
| `.app-picker-button[data-area="admin"]` | `.navlink[data-area="admin"]` |
| `.admin-section-nav` | `#admin-subnav.admin-subnav` |
| `.admin-section-item[data-section-id="providers"]` | `.holograph-section-item[data-section-id="providers"]` |
| `.providers-list .provider-tile` | `.providers-grid .provider-card` |
| `.tools-grid .tool-row` | `.tools-grid .tool-card` |
| `.tool-config-modal` | `.modal-backdrop .modal-shell` |
| `.system-page-section` | `.general-card` |

- [ ] **Step 5.4.2: Update tests**

Edit each `test_flow_admin_*.py` and `test_flow_provider_*.py` per the selector map.

- [ ] **Step 5.4.3: Run admin tests**

```bash
docker exec the-one pytest tests/browser/test_flow_admin_navigation.py tests/browser/test_flow_admin_openrouter.py tests/browser/test_flow_admin_tools_editor.py tests/browser/test_flow_admin_tools_grid.py tests/browser/test_flow_provider_dirty_confirm.py tests/browser/test_flow_provider_editor.py tests/browser/test_flow_provider_grid.py tests/browser/test_flow_provider_setup.py -x -q
```

Expected: all pass.

- [ ] **Step 5.4.4: Commit test updates**

```bash
git add tests/browser/test_flow_admin_*.py tests/browser/test_flow_provider_*.py
git commit -m "L5.4: admin flow tests — Holograph selectors"
```

### Task 5.5: Verify `system → general` redirect

- [ ] **Step 5.5.1: Manual check**

Browse to `http://localhost:8484/#admin/system`. Confirm:
- URL redirects to `#admin/general`
- General page renders

- [ ] **Step 5.5.2: Add an explicit redirect-preservation test (if not already present)**

Check `tests/browser/test_flow_admin_navigation.py` for a redirect assertion. If missing:

```python
def test_admin_system_legacy_redirect(page, app_url):
    """#admin/system must redirect to #admin/general for bookmark stability."""
    page.goto(f"{app_url}/#admin/system")
    page.wait_for_function("() => window.location.hash === '#admin/general'", timeout=2000)
    assert page.locator(".admin-sub#sub-general.active").is_visible()
```

Commit if added:

```bash
git add tests/browser/test_flow_admin_navigation.py
git commit -m "L5.5: assert #admin/system → #admin/general redirect preserved"
```

### Task 5.6: L5 acceptance

- [ ] **Step 5.6.1: Manual Admin smoke**

Browse to `#admin`. Confirm:
- Three-section sub-nav: Providers / Built-in Tools / General
- Providers grid renders with provider cards (3-col)
- Click a provider card → expands inline (col-span-2 visible)
- Built-in Tools renders 3 category sections, each with `.tools-grid` of `.tool-card`
- Click a tool → modal opens with tool config form
- General renders 4 cards; theme toggle works; encryption rotate button works; base prompt visible

---

## L6 — Modals + dialogs

**Files:**
- Modify: `the_one/interfaces/web/static/js/confirm.js` (restyle markup to `.confirm-dialog`)
- Modify: `the_one/interfaces/web/static/js/dialog.js` (restyle to `.modal-shell`)
- Modify: any OAuth-status modal logic in `mcp-server-editor.js` or `mcps-tab.js` to use `.modal-shell` shape
- Modify (selectors): `tests/browser/test_oauth_modal_flow.py`, plus any other modal-touching tests

### Task 6.1: Restyle `confirm.js`

- [ ] **Step 6.1.1: Update confirm-dialog markup**

```js
function showConfirm(opts) {
  // opts: { title, message, confirmLabel, cancelLabel, danger, onConfirm, onCancel }
  var backdrop = document.createElement('div');
  backdrop.className = 'modal-backdrop';
  backdrop.innerHTML =
    '<div class="modal-shell confirm-dialog' + (opts.danger ? ' danger' : '') + '">' +
      '<div class="modal-header">' +
        '<div class="modal-title">' + escapeHtml(opts.title) + '</div>' +
        '<button class="modal-close" aria-label="Close"><svg class="icn" viewBox="0 0 16 16"><path d="M4 4l8 8M4 12l8-8" stroke="currentColor" stroke-width="1.6"/></svg></button>' +
      '</div>' +
      '<div class="modal-body">' + escapeHtml(opts.message) + '</div>' +
      '<div class="modal-footer">' +
        '<button class="btn btn-ghost" data-action="cancel">' + escapeHtml(opts.cancelLabel || 'Cancel') + '</button>' +
        '<button class="btn btn-primary' + (opts.danger ? ' danger' : '') + '" data-action="confirm">' + escapeHtml(opts.confirmLabel || 'Confirm') + '</button>' +
      '</div>' +
    '</div>';
  document.body.appendChild(backdrop);

  // Wire interactions (close, escape, click outside, confirm, cancel)
  // ... preserve existing behavior
}
```

Preserve the existing API (`App.confirm(...)` or equivalent) — only the markup changes.

- [ ] **Step 6.1.2: Commit**

```bash
git add the_one/interfaces/web/static/js/confirm.js
git commit -m "L6.1: confirm.js — Holograph .confirm-dialog markup"
```

### Task 6.2: Restyle `dialog.js`

- [ ] **Step 6.2.1: Update dialog markup**

Same pattern as confirm.js — use `.modal-backdrop` + `.modal-shell` shape. Preserve the existing public API.

- [ ] **Step 6.2.2: Commit**

```bash
git add the_one/interfaces/web/static/js/dialog.js
git commit -m "L6.2: dialog.js — Holograph .modal-shell markup"
```

### Task 6.3: Restyle OAuth-status modal

- [ ] **Step 6.3.1: Find the OAuth-status modal render in `mcp-server-editor.js`**

```bash
grep -n "auth_required\|oauth\|waiting" the_one/interfaces/web/static/js/areas/studio/mcp-server-editor.js | head -10
```

- [ ] **Step 6.3.2: Update its markup to `.modal-shell`**

The OAuth-status modal shows during the popup flow. Use `.modal-shell` with width 480px, inline-spinner SVG, "Waiting for authorization at {idp_host}…" message, Cancel button. Preserve the synthetic-csid no-op suppression for non-chat sources.

- [ ] **Step 6.3.3: Run OAuth modal flow test**

```bash
docker exec the-one pytest tests/browser/test_oauth_modal_flow.py -x -q
```

Expected: PASS after selector updates in the test.

- [ ] **Step 6.3.4: Commit**

```bash
git add the_one/interfaces/web/static/js/areas/studio/mcp-server-editor.js tests/browser/test_oauth_modal_flow.py
git commit -m "L6.3: OAuth-status modal — Holograph .modal-shell; csid suppression preserved"
```

### Task 6.4: L6 acceptance

- [ ] **Step 6.4.1: Run all modal-related tests**

```bash
docker exec the-one pytest tests/browser/test_oauth_modal_flow.py tests/browser/test_flow_dirty_confirm.py tests/browser/test_flow_provider_dirty_confirm.py -x -q
```

Expected: all pass.

- [ ] **Step 6.4.2: Manual modal smoke**

- Trigger a confirm dialog (e.g., delete an agent in Studio) → shows Holograph-styled confirm
- Trigger an OAuth flow on an MCP source → shows Holograph-styled status modal
- Click backdrop → modal closes
- Press Escape → modal closes

---

## L7 — Cross-area tests + final snapshot rebase

**Files:**
- Modify: `tests/browser/test_flow_hash_routing.py`, `test_flow_dirty_confirm.py`, `test_flow_keyboard.py`, `test_smoke.py`, `test_app_fixture.py`, `test_seeders.py`
- Modify: `tests/browser/test_visual_snapshots.py`
- Regenerate: `tests/browser/__snapshots__/` (all baselines)

### Task 7.1: Update cross-area flow tests

- [ ] **Step 7.1.1: Run cross-area tests**

```bash
docker exec the-one pytest tests/browser/test_flow_hash_routing.py tests/browser/test_flow_dirty_confirm.py tests/browser/test_flow_keyboard.py tests/browser/test_smoke.py tests/browser/test_app_fixture.py tests/browser/test_seeders.py -x -q --tb=short 2>&1 | head -30
```

- [ ] **Step 7.1.2: Update remaining selectors**

Apply the same selector-map approach from L3/L4/L5 to any cross-area tests that still reference old shell selectors.

- [ ] **Step 7.1.3: Commit**

```bash
git add tests/browser/test_flow_hash_routing.py tests/browser/test_flow_dirty_confirm.py tests/browser/test_flow_keyboard.py tests/browser/test_smoke.py tests/browser/test_app_fixture.py tests/browser/test_seeders.py
git commit -m "L7.1: cross-area flow tests — Holograph selectors"
```

### Task 7.2: Expand visual snapshot matrix

> **⚠ DEFERRED**: This expansion was deferred during execution. Commit `7fc6bfa` migrated selectors on the existing 12 baselines but did NOT expand to the 40-baseline matrix described below. The matrix specification is preserved here for a future polish leg. Track as carry-forward.

- [ ] **Step 7.2.1: Edit `test_visual_snapshots.py` to add new snapshots**

Per spec §"Visual snapshot matrix (≥28)", expand the matrix to 40 baselines:

```python
SNAPSHOT_MATRIX = [
    # (route, state_setup_fn, theme, snapshot_name)
    ("#chat", _seed_active_session, "light", "chat-active-light"),
    ("#chat", _seed_active_session, "dark", "chat-active-dark"),
    ("#chat", _seed_empty, "light", "chat-empty-light"),
    ("#chat", _seed_empty, "dark", "chat-empty-dark"),

    ("#studio/agents/Researcher/general", _seed_agents, "light", "studio-agents-selected-light"),
    ("#studio/agents/Researcher/general", _seed_agents, "dark", "studio-agents-selected-dark"),
    ("#studio/agents", _seed_empty, "light", "studio-agents-empty-light"),
    ("#studio/agents", _seed_empty, "dark", "studio-agents-empty-dark"),
    ("#studio/agents/Researcher/mcps", _seed_agent_mcps, "light", "studio-mcps-tab-light"),
    ("#studio/agents/Researcher/mcps", _seed_agent_mcps, "dark", "studio-mcps-tab-dark"),
    ("#studio/agents/Researcher/mcps/source-1", _seed_agent_mcps, "light", "studio-mcps-attachment-light"),
    ("#studio/agents/Researcher/mcps/source-1", _seed_agent_mcps, "dark", "studio-mcps-attachment-dark"),
    ("#studio/agents/Researcher/tools", _seed_agent_tools, "light", "studio-tools-tab-light"),
    ("#studio/agents/Researcher/tools", _seed_agent_tools, "dark", "studio-tools-tab-dark"),
    ("#studio/agents/Researcher/overrides", _seed_agent_tools, "light", "studio-overrides-tab-light"),
    ("#studio/agents/Researcher/overrides", _seed_agent_tools, "dark", "studio-overrides-tab-dark"),

    ("#studio/knowledge", _seed_empty, "light", "studio-knowledge-light"),
    ("#studio/knowledge", _seed_empty, "dark", "studio-knowledge-dark"),

    ("#studio/mcp-sources", _seed_mcp_sources, "light", "studio-mcp-sources-grid-light"),
    ("#studio/mcp-sources", _seed_mcp_sources, "dark", "studio-mcp-sources-grid-dark"),
    ("#studio/mcp-sources/source-1", _seed_mcp_sources, "light", "studio-mcp-source-editor-light"),
    ("#studio/mcp-sources/source-1", _seed_mcp_sources, "dark", "studio-mcp-source-editor-dark"),

    ("#admin/providers", _seed_providers, "light", "admin-providers-grid-light"),
    ("#admin/providers", _seed_providers, "dark", "admin-providers-grid-dark"),
    # 3 column-position expanded snapshots
    ("#admin/providers", _expand_provider_col1, "light", "admin-providers-expanded-col1-light"),
    ("#admin/providers", _expand_provider_col1, "dark", "admin-providers-expanded-col1-dark"),
    ("#admin/providers", _expand_provider_col2, "light", "admin-providers-expanded-col2-light"),
    ("#admin/providers", _expand_provider_col2, "dark", "admin-providers-expanded-col2-dark"),
    ("#admin/providers", _expand_provider_col3, "light", "admin-providers-expanded-col3-light"),
    ("#admin/providers", _expand_provider_col3, "dark", "admin-providers-expanded-col3-dark"),

    ("#admin/tools", _seed_tools, "light", "admin-tools-grid-light"),
    ("#admin/tools", _seed_tools, "dark", "admin-tools-grid-dark"),
    ("#admin/tools", _open_tool_config_modal, "light", "admin-tool-config-modal-light"),
    ("#admin/tools", _open_tool_config_modal, "dark", "admin-tool-config-modal-dark"),

    ("#admin/general", _seed_empty, "light", "admin-general-light"),
    ("#admin/general", _seed_empty, "dark", "admin-general-dark"),

    # Modal states (rendered over Chat to provide background)
    ("#chat", _open_confirm_dialog, "light", "modal-confirm-light"),
    ("#chat", _open_confirm_dialog, "dark", "modal-confirm-dark"),
    ("#studio/mcp-sources/source-with-oauth", _trigger_oauth_modal, "light", "modal-oauth-status-light"),
    ("#studio/mcp-sources/source-with-oauth", _trigger_oauth_modal, "dark", "modal-oauth-status-dark"),
]
```

Implement the helper setup functions (`_seed_active_session`, `_expand_provider_col1`, etc.) as needed in `tests/browser/seeders.py`.

- [ ] **Step 7.2.2: Generate fresh baselines**

```bash
docker exec the-one pytest tests/browser/test_visual_snapshots.py --snapshot-update -q
```

Expected: 40 PNGs land in `tests/browser/__snapshots__/`. Manually review each (open the folder, eyeball 5–10 random snapshots) to confirm they match the mockups in shape and feel.

- [ ] **Step 7.2.3: Run snapshot test against baselines (no update)**

```bash
docker exec the-one pytest tests/browser/test_visual_snapshots.py -x -q
```

Expected: all 40 snapshots pass.

- [ ] **Step 7.2.4: Commit baselines + matrix**

```bash
git add tests/browser/test_visual_snapshots.py tests/browser/__snapshots__/ tests/browser/seeders.py
git commit -m "L7.2: visual snapshots — 40-baseline Holograph matrix"
```

### Task 7.3: Token-definitions test passes against all CSS

- [ ] **Step 7.3.1: Run token-definitions test**

```bash
docker exec the-one pytest tests/test_token_definitions.py -v
```

Expected: PASS. If any retired token is still referenced, find and fix it.

```bash
grep -rn "var(--glass-\|var(--bezel-\|var(--accent-glow\|var(--bg-gradient\|var(--panel-shadow\|var(--panel-radius\|var(--btn-v3" the_one/interfaces/web/static/css/ the_one/interfaces/web/static/js/ 2>/dev/null
```

Expected: no matches. If any, remove them.

- [ ] **Step 7.3.2: Commit if any cleanups needed**

```bash
git add -p
git commit -m "L7.3: token-definitions test — remove residual retired-token references"
```

### Task 7.4: L7 acceptance — full test suite green

- [ ] **Step 7.4.1: Run everything**

```bash
docker exec the-one pytest tests/ -q
```

Expected: every test passes. Note the count vs baseline.

- [ ] **Step 7.4.2: Run a11y audit**

```bash
docker exec the-one pytest tests/test_design_tokens_a11y.py -v
```

Expected: all contrast pairs pass per spec table.

---

## L8 — Cleanup

**Files:**
- Modify: `the_one/interfaces/web/static/js/app.js` (remove legacy-stub shim)
- Modify: `CLAUDE.md`
- Modify: `the_one/agents.md`
- Modify: `playground/index.html`

### Task 8.1: Remove legacy `init(sidebar, content)` shim

- [ ] **Step 8.1.1: Confirm all areas use new signature**

```bash
grep -rn "init: function (sidebar, content)" the_one/interfaces/web/static/js/areas/
```

Expected: no matches (only `init: function (content)`).

- [ ] **Step 8.1.2: Remove the shim block in `app.js`**

Delete the `if (areas[areaId].init.length >= 2) { ... } else { ... }` shim. Just call `areas[areaId].init(contentPanel)`.

- [ ] **Step 8.1.3: Verify**

```bash
make rebuild
docker exec the-one pytest tests/browser/test_smoke.py -x -q
```

- [ ] **Step 8.1.4: Commit**

```bash
git add the_one/interfaces/web/static/js/app.js
git commit -m "L8.1: remove legacy init(sidebar,content) shim"
```

### Task 8.2: Update `CLAUDE.md` Design System section

- [ ] **Step 8.2.1: Edit the "Design system" subsection**

Replace the Mission-08 design-system narrative with a Holograph reference:

```markdown
The web UI ships a token-based design system (Holograph — light theme uses a
warm-neutral palette with a #3358c0 accent; dark theme uses GleepGlorp violet
#a78bfa). Both themes share token names; values differ in `[data-theme="light"]`
and `[data-theme="dark"]` blocks in `tokens.css`. Geometry, radii, and motion
tokens are theme-stable.

Body font is self-hosted Inter; mono is self-hosted JetBrains Mono. Mockups at
`playground/mockups/holograph.html` (light) and `playground/mockups/holograph-dark.html`
(dark) are the visual ground truth. Migration spec:
`docs/superpowers/specs/2026-05-12-holograph-ui-migration-design.md`.

A tri-state theme switcher (`App.theme.{get,resolved,set}` with `'light'/'dark'/'auto'`
semantics) lives in Admin → General → Appearance. Token a11y audited via
`tests/test_design_tokens_a11y.py`; per-theme values mirrored in
`tests/browser/design_tokens.py`.

For architecture internals, see `the_one/agents.md`.
```

- [ ] **Step 8.2.2: Edit `the_one/agents.md` Design system section** (mirror)

- [ ] **Step 8.2.3: Update `playground/index.html`**

Add a banner at the top noting Holograph has shipped:

```html
<div class="callout" style="background: #2f9c6a; color: white; padding: 10px 14px; border-radius: 6px; margin-bottom: 32px;">
  Holograph has shipped. The live app at <code>http://localhost:8484</code> now uses this design.
  These mockups remain as historical reference.
</div>
```

- [ ] **Step 8.2.4: Commit**

```bash
git add CLAUDE.md the_one/agents.md playground/index.html
git commit -m "L8.2: docs — Holograph design-system references"
```

### Task 8.3: Final verification

- [ ] **Step 8.3.1: Full test suite**

```bash
docker exec the-one pytest tests/ -q
```

Expected: all green.

- [ ] **Step 8.3.2: Lint + format**

```bash
docker exec the-one ruff check the_one/ tests/
docker exec the-one ruff format --check the_one/ tests/
```

Expected: clean.

- [ ] **Step 8.3.3: Verify served assets**

```bash
make verify-serving
```

Expected: all admin sub-modules return 200.

- [ ] **Step 8.3.4: Final commit (if any pending changes)**

```bash
git status
# if clean: skip; else
git add -p
git commit -m "L8.3: housekeeping — lint/format cleanups"
```

### Task 8.4: Open PR

- [ ] **Step 8.4.1: Push branch**

```bash
git push -u origin feat/holograph-migration
```

- [ ] **Step 8.4.2: Open PR via gh**

```bash
gh pr create --title "mission/09: Holograph UI migration" --body "$(cat <<'EOF'
## Summary
- Big-bang migration to the Holograph design language across Chat, Studio (Agents / Knowledge / MCP Sources), and Administration (Providers / Built-in Tools / General)
- Replaced topbar+sidebar+content shell with topnav+content; each area owns its internal layout
- Retired Mission 08 visual vocabulary (glass, bezel, gleam); adopted mockup CSS class vocabulary verbatim
- Self-hosted Inter + JetBrains Mono replacing self-hosted Geist
- Light theme: warm neutrals + #3358c0 accent (AA-calibrated); dark theme: GleepGlorp violet #a78bfa
- Visual snapshot baselines expanded from 12 to 40 (every area × state × theme)

Spec: `docs/superpowers/specs/2026-05-12-holograph-ui-migration-design.md` (v3)
Mockups: `playground/mockups/holograph.html` (light) + `holograph-dark.html` (dark)

## Test plan
- [ ] All unit tests pass (`make test`)
- [ ] All browser flow tests pass (`make test-browser`)
- [ ] Visual snapshots stable (`pytest -m browser tests/browser/test_visual_snapshots.py`)
- [ ] Manual smoke: Chat (send message, expand tool call, switch theme)
- [ ] Manual smoke: Studio (create agent, edit, attach MCP source via deep-link)
- [ ] Manual smoke: Admin (add provider, configure tool, rotate encryption key)
- [ ] Manual smoke: #admin/system redirects to #admin/general
- [ ] Manual smoke: dirty-confirm modal on area switch with unsaved changes
- [ ] Manual smoke: OAuth flow on a streamable-http MCP source

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Expected: PR URL printed.

---

## Self-review

Plan covers:
- Spec §"Goals" — each goal traces to a leg (L1: tokens+fonts+a11y; L2: shell; L3: Chat; L4: Studio; L5: Admin; L6: modals; L7: snapshots + cross-area; L8: cleanup + docs)
- Spec §"Non-goals" — observed (no command palette, no mobile, no drag-and-drop, no per-agent colors)
- Spec §"Design decisions" 1-22 — each is enforced by an explicit step (Decision 13's `system → general` redirect verified in Task 5.5; Decision 17's section-nav API preserved in Task 1.7 + 4.2.2 + 5.2.1; Decision 21's single OAuth Reset preserved in Task 4.3.2; Decision 22's `--fg-on-danger` defined in Task 1.3.1)
- Spec §"Token system" — exact light + dark token values in Task 1.3.1
- Spec §"Component vocabulary" — exact selector list adopted in CSS rewrites (L1.6, L3.1, L4.1, L5.1) + new modal/section-nav classes in L1.6
- Spec §"App shell architecture" — Task 2.1 (index.html) + 2.2 (app.js with new `init(content)` signature)
- Spec §"Area-by-area IA" — Studio sub-nav in 4.2; Knowledge stub in 4.2.4; MCP Sources grid + editor in 4.2.5 + 4.3; per-agent attachment editor in 4.4; Admin `system → general` redirect in 5.5
- Spec §"Non-mockup surface coverage" — confirm dialog in 6.1; modal-shell + dialog in 6.2; OAuth modal in 6.3
- Spec §"Test strategy" — 40-baseline matrix in 7.2; per-leg test ownership matches spec
- Spec §"Risks + mitigations" — addressed by the transitional shim (2.2.4 → 8.1) and the layered leg structure

Placeholder scan: no "TBD", "TODO", or hedged "handle edge cases" instructions remain. Every step has either concrete code, an explicit grep/sed pattern, or a verification command with expected output.

Type / API consistency: `init(content)` signature used throughout (L2 introduces shim, L3-L5 migrate, L8 removes shim). `App.layout.renderSectionNav` + `App.layout.updateActiveSection` API preserved (L1.7, used by L4.2.2 and L5.2.1). `App.theme.renderToggle` referenced in L5.3.6 — preserved from existing code.

Gaps fixed inline during review: added the L1.7 shim's removal target (L8.1); added explicit `_setActiveSection` / `_setActiveSub` helper functions inside studio.js and admin.js rewrites so the cross-references aren't dangling.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-05-12-holograph-ui-migration.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

**Which approach?**
