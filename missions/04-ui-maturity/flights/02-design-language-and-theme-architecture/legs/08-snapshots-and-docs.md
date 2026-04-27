# Leg: 08-snapshots-and-docs

**Status**: landed
**Flight**: [Design Language & Theme Architecture](../flight.md)

## Objective

Establish the visual regression net for F2's design language: ~12 Playwright `to_have_screenshot()` baselines covering 3 areas × 2 states × 2 themes (chat-empty, chat-with-messages, studio-empty, studio-with-agent, admin-empty, admin-with-provider — each in dark + light). Add `tests/browser/design_tokens.py` exporting token names as constants for future test imports. Add a CI-style pytest that fails if any `var(--x)` reference in CSS isn't defined in `tokens.css`. Verify the design-system documentation in `agents.md` is complete (typography scale, icon list, theme switching contract — most added by earlier legs; this leg fills any gaps).

## Context

- This is the LAST autonomous leg of F2. After it lands, HAT (leg 09) runs interactively, then the flight-level review and commit.
- **Earlier-leg outcomes already in place**:
  - Leg 04: Geist font integration + typography scale tokens
  - Leg 05: 20 Lucide icons in `App.icons` (icons.js)
  - Leg 06: light theme designed
  - Leg 07: WCAG AA contrast tests + agents.md "Design system" section with "Color contrast (WCAG AA)" subsection + CLAUDE.md Testing line
- **What this leg adds**:
  1. Playwright visual snapshots — the FIRST visual regression net for the design language. Subsequent flights (F3-F6) baseline against these.
  2. `tests/browser/design_tokens.py` — Python module re-exporting token names + values (mirrors `tokens.css`); single source of truth for tests that need to reference design tokens.
  3. `tests/test_token_definitions.py` — pytest that fails if a CSS file references a `var(--x)` undefined in `tokens.css`. Catches typos that wouldn't fail at runtime (CSS treats undefined custom properties as `unset`).
  4. agents.md additions: typography scale reference, icon catalog, theme switching contract — fill gaps if any (most added by legs 04-07).
- **Snapshot tooling**: Playwright Python supports `expect(page).to_have_screenshot("name.png")`. Baselines stored under `tests/browser/__snapshots__/` (or `<test_file>-snapshots/`). First run generates baselines; subsequent runs compare. Tolerance via `maxDiffPixels` or `maxDiffPixelRatio`.
- **Test environment is `color_scheme="no-preference"`** which resolves to dark by default. To capture light theme snapshots, the test calls `page.evaluate("App.theme.set('light')")` and waits for re-render.

## Inputs

- Branch `flight/02-design-language-and-theme-architecture`, legs 01-07 landed (uncommitted)
- Test baseline: 386 passed, 16 deselected; 8 browser tests passing (smoke + 2 fixture sanity + 2 seeder + 3 flow)
- F1 fixtures: `app_clean`, `app_with_provider`, `app_with_agent` (the seeded variants make state setup easy)
- `tests/browser/conftest.py` has Playwright fixtures (module-scoped browser, function-scoped page)

## Outputs

- `tests/browser/test_visual_snapshots.py` (new) — Playwright snapshot tests covering 12 baselines (3 areas × 2 states × 2 themes)
- `tests/browser/__snapshots__/` (new directory) — generated baseline PNGs (one per test+theme combination, browser-tagged per Playwright convention)
- `tests/browser/design_tokens.py` (new) — Python module exporting `DARK` and `LIGHT` dicts (re-using leg-07's tests/test_design_tokens_a11y.py token tables, refactored to a single source)
- `tests/test_token_definitions.py` (new) — pytest that fails if any `var(--x)` referenced in `static/css/*.css` isn't defined in `tokens.css`'s theme blocks
- `the_one/interfaces/web/static/css/tokens.css` — UNCHANGED (verify; just used as source for the definition check)
- `the_one/agents.md` — gap-fill additions:
  - Typography scale reference (8 sizes + 4 weights + 2 line-heights — mirrors fonts.css)
  - Icon catalog (list of 20 Lucide icons available via `App.icons`)
  - Theme switching contract (App.theme.set/get/resolved API + tri-state semantics + localStorage `theme-preference` key)
- `tests/test_design_tokens_a11y.py` — small refactor: import DARK/LIGHT dicts from `tests/browser/design_tokens.py` (single source of truth) instead of hardcoding

## Acceptance Criteria

### Visual snapshot tests

- [ ] `tests/browser/test_visual_snapshots.py` exists with 12 snapshot tests (or fewer parametrized tests producing 12 baselines):
  1. `chat-empty-dark` — `app_clean` fixture, default theme (dark), navigate to `#chat`, screenshot
  2. `chat-empty-light` — same but `App.theme.set('light')` first
  3. `chat-with-messages-dark` — `app_with_agent` fixture, `#chat`, send a "hello" message via mock provider, screenshot after assistant response
  4. `chat-with-messages-light` — same with light theme
  5. `studio-empty-dark` — `app_with_provider` fixture, `#studio`, no agents yet
  6. `studio-empty-light` — same with light theme
  7. `studio-with-agent-dark` — `app_with_agent` fixture, `#studio`, agent visible in sidebar
  8. `studio-with-agent-light` — same with light theme
  9. `admin-empty-dark` — `app_clean` fixture, `#admin`, click "LLM Providers" category, empty state
  10. `admin-empty-light` — same with light theme
  11. `admin-with-provider-dark` — `app_with_provider` fixture, `#admin` → LLM Providers, card visible
  12. `admin-with-provider-light` — same with light theme
- [ ] All 12 baselines exist in `tests/browser/__snapshots__/` (or wherever Playwright places them based on test_visual_snapshots.py location). Generated by running `pytest --update-snapshots` (or Playwright's equivalent) on first run.
- [ ] Tests use `expect(page).to_have_screenshot("<name>.png", maxDiffPixelRatio=0.02)` (2% tolerance — accommodates anti-aliasing without being so loose it misses regressions)
- [ ] Helper: each test waits for fonts to load (`page.evaluate("document.fonts.ready")`) before screenshotting to avoid FOUC variance
- [ ] Helper: tests set viewport explicitly (e.g., 1280×800) so snapshots are dimensionally consistent
- [ ] Each snapshot test marked `@pytest.mark.browser`

### `design_tokens.py` module

- [ ] `tests/browser/design_tokens.py` exists with `DARK` and `LIGHT` dicts containing all token name → value mappings (mirrors `tokens.css` blocks)
- [ ] `tests/test_design_tokens_a11y.py` (from leg 07) refactored to import DARK/LIGHT from `tests/browser/design_tokens.py` instead of hardcoding (DRY)
- [ ] All 36 a11y tests still pass after refactor

### Token-definition consistency check

- [ ] `tests/test_token_definitions.py` exists with a test that:
  - Reads all `static/css/*.css` files
  - Extracts every `var(--xxx)` reference
  - Reads `tokens.css` and extracts every `--xxx: ...;` definition (in either `[data-theme="dark"]` or `[data-theme="light"]` block)
  - Asserts: every referenced token has a definition in BOTH theme blocks
  - Fails with a clear message naming the missing token + offending file
- [ ] Test passes (i.e., no undefined token references in current state)

### Documentation gap-fill

- [ ] `the_one/agents.md` "Design system" section (created in leg 07) has the following subsections — verify each is present, add any missing:
  - "Color contrast (WCAG AA)" — added in leg 07 ✓
  - "Typography scale" — table listing the 8 size tokens, 4 weight tokens, 2 line-height tokens, and the Geist Sans + Geist Mono families. Add if missing.
  - "Icon catalog" — list of 20 Lucide icons available via `App.icons` / `App.icon(name)`. Add if missing.
  - "Theme switching contract" — describe `App.theme.set/get/resolved` API, the tri-state semantics (`'dark'` | `'light'` | `'auto'`), the `theme-preference` localStorage key, and the `[data-theme]` HTML attribute. Add if missing.
- [ ] `CLAUDE.md` (already updated in leg 07 with a11y test mention) gets one more line in Testing section: visual snapshot tests reference

### Behavioral

- [ ] All existing F1 + F2 tests pass: `pytest tests/` shows 386 + 12 = 398 passed, 16 + 12 = 28 deselected (the 12 snapshot tests are `@pytest.mark.browser` so they're deselected by default)
- [ ] Browser test suite: `pytest -m browser tests/browser/` shows 8 + 12 = 20 passed
- [ ] Token-definition test passes
- [ ] No hex/rgba leaks (grep clean — no regression)

## Verification Steps

1. **Generate baselines** (FIRST RUN):
   ```bash
   docker compose up -d --build
   pytest -m browser tests/browser/test_visual_snapshots.py -v --timeout=120 \
     --snapshot-update
   ```
   First run generates baseline images. Inspect them visually; they should look like the expected design.

2. **Verify baselines stable**:
   ```bash
   pytest -m browser tests/browser/test_visual_snapshots.py -v --timeout=120
   ```
   Should pass against the just-generated baselines.

3. **Repeat-run stability** (3 consecutive runs):
   ```bash
   for i in 1 2 3; do pytest -m browser tests/browser/test_visual_snapshots.py -q --timeout=120 \
     || { echo "FAIL $i"; exit 1; }; done
   ```

4. **Token-definition check**:
   ```bash
   pytest tests/test_token_definitions.py -v --timeout=10
   ```
   Should pass (no undefined token references).

5. **All tests**:
   ```bash
   pytest tests/ --tb=short -q --timeout=60
   pytest -m browser tests/browser/ -v --timeout=120
   ```

6. **Hex/rgba grep clean**:
   ```bash
   grep -nE "#[0-9a-fA-F]{3,8}\b|rgba?\(" the_one/interfaces/web/static/css/*.css \
     | grep -v tokens.css | grep -v fonts.css | grep -v "data:image/svg"
   ```
   Empty.

## Implementation Guidance

### 1. Create `tests/browser/design_tokens.py`

Move the DARK/LIGHT dicts from `tests/test_design_tokens_a11y.py` into this new module so all tests share one source. Both dicts mirror `tokens.css` blocks.

```python
"""Design tokens — Python mirror of static/css/tokens.css blocks.

Single source of truth for tests that need to reference token values.
Used by:
- tests/test_design_tokens_a11y.py (WCAG AA contrast pairs)
- tests/test_token_definitions.py (var(--x) reference check; reads names only)
- tests/browser/test_visual_snapshots.py (theme-toggle helpers)

If tokens.css values change, update this file in lockstep.
"""

from __future__ import annotations

DARK = {
    "bg": "#0a0a0a",
    "surface": "#1a1a1a",
    # ... (full set, copied from tests/test_design_tokens_a11y.py leg 07)
    "fg-on-danger": "#000000",  # leg-07 retune from #ffffff
    # ...
}

LIGHT = {
    "bg": "#fafbfc",
    "surface": "#ffffff",
    # ... (full set, copied from tests/test_design_tokens_a11y.py leg 07)
    "accent": "#0e7490",         # leg-07 retune from #0891b2
    "status-success": "#15803d",  # leg-07 retune
    "status-warning": "#a16207",  # leg-07 retune
    # ...
}
```

Refactor `tests/test_design_tokens_a11y.py` to import:

```python
from browser.design_tokens import DARK, LIGHT
```

(The `browser` import path uses pytest's `pythonpath = ["tests"]` config from F1 leg 01.)

### 2. Create `tests/test_token_definitions.py`

```python
"""Verify every var(--x) reference in CSS files has a corresponding token
definition in tokens.css. Catches typos that wouldn't fail at runtime
(CSS treats undefined custom properties as `unset`)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest


CSS_DIR = Path(__file__).parent.parent / "the_one/interfaces/web/static/css"

VAR_REF_PATTERN = re.compile(r"var\(\s*(--[a-zA-Z0-9_-]+)")
VAR_DEF_PATTERN = re.compile(r"^\s*(--[a-zA-Z0-9_-]+)\s*:")


def _extract_var_references(css_path: Path) -> set[str]:
    text = css_path.read_text()
    return set(VAR_REF_PATTERN.findall(text))


def _extract_var_definitions(tokens_css: Path) -> set[str]:
    text = tokens_css.read_text()
    return set(VAR_DEF_PATTERN.findall(text))


def test_every_var_reference_is_defined() -> None:
    tokens_path = CSS_DIR / "tokens.css"
    defined = _extract_var_definitions(tokens_path)

    fonts_path = CSS_DIR / "fonts.css"
    if fonts_path.exists():
        defined |= _extract_var_definitions(fonts_path)

    referenced = set()
    for css_file in CSS_DIR.glob("*.css"):
        if css_file.name in {"tokens.css", "fonts.css"}:
            continue
        referenced |= _extract_var_references(css_file)

    undefined = referenced - defined
    assert not undefined, (
        f"Undefined CSS custom properties referenced: {sorted(undefined)}\n"
        f"Defined tokens: {sorted(defined)}"
    )
```

### 3. Create `tests/browser/test_visual_snapshots.py`

```python
"""Visual regression snapshots for F2 design language.

Captures 12 baselines (3 areas × 2 states × 2 themes) so subsequent
flights (F3-F6) can detect unintended visual regressions.

Snapshot tolerance: 2% pixel diff to absorb anti-aliasing variance
without missing real regressions.
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

from browser.seeders import SeededApp


VIEWPORT = {"width": 1280, "height": 800}


def _wait_for_render(page: Page) -> None:
    """Wait for fonts loaded + 1 animation frame to stabilize render."""
    page.evaluate("document.fonts.ready")
    page.evaluate("new Promise(r => requestAnimationFrame(() => r()))")


def _set_theme(page: Page, theme: str) -> None:
    page.evaluate(f"App.theme.set('{theme}')")
    _wait_for_render(page)


# ----- Chat -----

@pytest.mark.browser
@pytest.mark.parametrize("theme", ["dark", "light"])
def test_snapshot_chat_empty(app_clean: str, page: Page, theme: str) -> None:
    page.set_viewport_size(VIEWPORT)
    page.goto(app_clean)
    _set_theme(page, theme)
    expect(page.locator("body")).to_be_visible()
    expect(page).to_have_screenshot(f"chat-empty-{theme}.png", max_diff_pixel_ratio=0.02)


@pytest.mark.browser
@pytest.mark.parametrize("theme", ["dark", "light"])
def test_snapshot_chat_with_messages(
    app_with_agent: SeededApp, page: Page, theme: str
) -> None:
    page.set_viewport_size(VIEWPORT)
    page.goto(app_with_agent.base_url)
    _set_theme(page, theme)
    # Wait for session auto-create + agent badge
    expect(page.locator(".session-agent-badge")).to_have_text(
        app_with_agent.agent_name, timeout=5000
    )
    # Send a message and wait for assistant response
    page.locator('[data-testid="chat-input"]').fill("hello")
    page.locator('[data-testid="chat-send-btn"]').click()
    expect(page.locator('[data-testid="message"].assistant')).to_have_text(
        "Mock response from the mock provider.", timeout=10000
    )
    _wait_for_render(page)
    expect(page).to_have_screenshot(
        f"chat-with-messages-{theme}.png", max_diff_pixel_ratio=0.02
    )


# ----- Studio -----

@pytest.mark.browser
@pytest.mark.parametrize("theme", ["dark", "light"])
def test_snapshot_studio_empty(
    app_with_provider: SeededApp, page: Page, theme: str
) -> None:
    page.set_viewport_size(VIEWPORT)
    page.goto(f"{app_with_provider.base_url}#studio")
    _set_theme(page, theme)
    expect(page.locator('[data-testid="agent-empty"]')).to_be_visible()
    expect(page).to_have_screenshot(f"studio-empty-{theme}.png", max_diff_pixel_ratio=0.02)


@pytest.mark.browser
@pytest.mark.parametrize("theme", ["dark", "light"])
def test_snapshot_studio_with_agent(
    app_with_agent: SeededApp, page: Page, theme: str
) -> None:
    page.set_viewport_size(VIEWPORT)
    page.goto(f"{app_with_agent.base_url}#studio")
    _set_theme(page, theme)
    expect(page.locator('[data-testid="agent-item"]')).to_have_count(1)
    expect(page).to_have_screenshot(
        f"studio-with-agent-{theme}.png", max_diff_pixel_ratio=0.02
    )


# ----- Admin -----

@pytest.mark.browser
@pytest.mark.parametrize("theme", ["dark", "light"])
def test_snapshot_admin_empty(app_clean: str, page: Page, theme: str) -> None:
    page.set_viewport_size(VIEWPORT)
    page.goto(f"{app_clean}#admin")
    _set_theme(page, theme)
    page.locator(".admin-category-item", has_text="LLM Providers").click()
    expect(page.locator(".admin-provider-empty")).to_be_visible()
    expect(page).to_have_screenshot(f"admin-empty-{theme}.png", max_diff_pixel_ratio=0.02)


@pytest.mark.browser
@pytest.mark.parametrize("theme", ["dark", "light"])
def test_snapshot_admin_with_provider(
    app_with_provider: SeededApp, page: Page, theme: str
) -> None:
    page.set_viewport_size(VIEWPORT)
    page.goto(f"{app_with_provider.base_url}#admin")
    _set_theme(page, theme)
    page.locator(".admin-category-item", has_text="LLM Providers").click()
    expect(page.locator('[data-testid="provider-card"]')).to_be_visible()
    expect(page).to_have_screenshot(
        f"admin-with-provider-{theme}.png", max_diff_pixel_ratio=0.02
    )
```

### 4. Generate baselines (FIRST RUN)

```bash
docker compose up -d --build
pytest -m browser tests/browser/test_visual_snapshots.py --timeout=120 --snapshot-update
```

This generates 12 PNG baselines under `tests/browser/__snapshots__/` (or per Playwright Python's convention).

**Inspect them visually** — open each PNG and confirm it matches the expected design (cyan accents, gradient bg, Geist typography, etc.). If any baseline looks wrong (e.g., showed a mid-render state), fix the test (add waits) and re-run with `--snapshot-update`.

### 5. Verify stability

```bash
# Run again WITHOUT --snapshot-update — should pass against the just-generated baselines
pytest -m browser tests/browser/test_visual_snapshots.py -v --timeout=120
```

Repeat 2-3 times to confirm no flakiness.

### 6. Doc gap-fill

Open `the_one/agents.md`. Find the "Design system" section (added in leg 07). Verify or add:

**"Typography scale" subsection**:

```markdown
### Typography scale

Defined in `static/css/fonts.css` as CSS custom properties (theme-agnostic).

**Families** (Geist + Geist Mono, self-hosted, OFL/SIL pinned to `vercel/geist-font@1.8.0`):
- `--font-family-sans`: Geist + system-ui chain (UI/prose)
- `--font-family-mono`: Geist Mono + JetBrains Mono + ui-monospace chain (data/code/section-headers)

**Sizes**:
| Token | Value |
|-------|-------|
| --font-size-display | 24px |
| --font-size-h1 | 18px |
| --font-size-h2 | 16px |
| --font-size-body-lg | 14px |
| --font-size-body | 13px |
| --font-size-body-sm | 12px |
| --font-size-caption | 11px |
| --font-size-tiny | 10px |

**Weights**: --font-weight-regular (400), -medium (500), -semibold (600), -bold (700)

**Line-heights**: --line-height-tight (1.2), -normal (1.5)
```

**"Icon catalog" subsection**:

```markdown
### Icon catalog

Lucide icons available via `App.icons.{name}` (returns SVG string) or `App.icon(name)` (with miss-warn). Pinned to `lucide@v0.265.0`.

| Name | Lucide source | Used in |
|------|---------------|---------|
| chat | message-circle | nav rail (Chat area) |
| studio | bot | nav rail (Studio area) |
| admin | settings | nav rail (Admin area) |
| plus | plus | Add buttons |
| x | x | Delete/close buttons |
| edit | edit | (future use) |
| trash | trash-2 | (future use) |
| check | check | (future use) |
| alert-triangle | alert-triangle | (future use) |
| alert-circle | alert-circle | (future use) |
| info | info | (future use) |
| eye | eye | Password reveal toggle |
| eye-off | eye-off | Password hide toggle |
| refresh | refresh-cw | (future use) |
| send | send | (future use) |
| download | download | (future use) |
| chevron-down | chevron-down | (future use — currently inline data URL) |
| chevron-right | chevron-right | (future use) |
| zap | zap | (future use) |
| sparkles | sparkles | (future use) |

Add new icons by editing `static/js/icons.js`. SVGs use `stroke="currentColor"` for theme-aware color inheritance. License: Lucide is MIT.
```

**"Theme switching contract" subsection**:

```markdown
### Theme switching contract

Tri-state preference (Light / Dark / Auto) persisted in localStorage. The `<html>` element carries `data-theme="dark"` or `"light"` attribute, applied synchronously by `static/js/theme.js` before render to avoid FOUC.

**API** (exposed on `App.theme`):
- `App.theme.get()` — returns `'dark'` | `'light'` | `'auto'` (the user's preference)
- `App.theme.resolved()` — returns `'dark'` | `'light'` (the currently-applied theme)
- `App.theme.set(pref)` — sets the preference (`'dark'` | `'light'` | `'auto'`); auto removes the localStorage key

**Auto mode**: follows OS preference via `matchMedia('(prefers-color-scheme: dark)')` and `matchMedia('(prefers-color-scheme: light)')`. If neither matches (no OS preference), defaults to dark (the canonical default for the design language). Live OS-preference changes propagate via `change` event listeners on both media queries.

**localStorage key**: `theme-preference`. Wrapped in try/catch so private-browsing degrades gracefully to in-memory non-persistent.

**Test environment**: Playwright's `browser.new_context(color_scheme="no-preference")` triggers the canonical-default branch, resolving auto to dark. To capture light theme in tests, call `App.theme.set('light')` after navigation.
```

### 7. Update CLAUDE.md

Add to the existing Testing section:

```markdown
**Visual snapshot tests** (`tests/browser/test_visual_snapshots.py`): 12 Playwright baseline screenshots covering 3 UI areas × 2 states × 2 themes. Run via `pytest -m browser tests/browser/test_visual_snapshots.py`. Baselines in `tests/browser/__snapshots__/`. Tolerance: 2% pixel diff.
```

## Edge Cases

- **Snapshot anti-aliasing variance**: `max_diff_pixel_ratio=0.02` (2%) is generous enough to absorb sub-pixel font rendering differences across runs. If still flaky, increase to 0.03; if you see false positives, decrease.

- **Font loading race**: `document.fonts.ready` returns a Promise; awaiting it ensures Geist + Geist Mono are loaded before screenshot. Without this, the first run might capture fallback fonts and subsequent runs would show diff.

- **Light theme doesn't persist across page reload**: theme.js writes localStorage only on explicit `App.theme.set('light')`. If the test calls `set('light')` then navigates to a new URL, the theme should persist (localStorage). Verify by setting light, navigating, screenshotting.

- **Test environment color_scheme**: `no-preference` resolves to dark by default. Snapshots that expect dark just navigate without setting theme; snapshots that expect light call `App.theme.set('light')` first.

- **Browser version stability**: Playwright pins Chromium (currently chromium-1208 per F1 leg 01). Snapshots are bound to that browser version. If Chromium upgrades and rendering changes, baselines need re-generation. Document in agents.md.

- **CI snapshot generation**: in F1's CI integration (Concourse), the `--snapshot-update` flag should NEVER be used. Baselines are committed to git; CI runs against them. If a legit visual change happens, regenerate locally and commit.

- **Snapshot diffs visualization**: Playwright generates `<test>-actual.png`, `<test>-expected.png`, `<test>-diff.png` on failure for visual inspection. Useful for the inevitable "is this a regression or anti-aliasing?" call.

- **Test count math**: 12 new snapshot tests, all `@pytest.mark.browser`. Default `pytest tests/` shows them as deselected (not added to passed count). Browser-suite: 8 + 12 = 20 passed.

- **Token-definition test caveat**: the regex `r"var\(\s*(--[a-zA-Z0-9_-]+)"` matches the simple form `var(--x)` and `var(  --x  )`. Doesn't match `var(--x, fallback)` if the fallback is present — but our codebase doesn't use the fallback form (verified by grep). If a future leg introduces fallbacks, update the regex.

## State-Machine Reachability Audit

This leg adds tests + docs. No new states. No DB schema. Token-definition test exercises existing CSS files; doesn't change behavior.

✓ Pass.

## Cache Freshness Contract

No new caches.

✓ Pass.

## Files Affected

- `tests/browser/test_visual_snapshots.py` — new (~120 LOC, 6 parametrized tests producing 12 baselines)
- `tests/browser/__snapshots__/*.png` — new (12 baseline images)
- `tests/browser/design_tokens.py` — new (~80 LOC, DARK/LIGHT dicts mirroring tokens.css)
- `tests/test_token_definitions.py` — new (~50 LOC, 1 test)
- `tests/test_design_tokens_a11y.py` — small refactor to import from `browser.design_tokens` (~5 lines changed)
- `the_one/agents.md` — Design system section additions (typography scale + icon catalog + theme switching contract)
- `CLAUDE.md` — one line added in Testing section

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing: `pytest tests/` shows 386 + 1 = 387 passed (token-def + a11y refactor); `pytest -m browser tests/browser/` shows 20 passed (8 + 12)
- [ ] All 12 visual snapshots generated and committed to `tests/browser/__snapshots__/`
- [ ] Token-definition test passes
- [ ] 3 consecutive runs of snapshot tests pass (no flakiness)
- [ ] Hex/rgba grep returns zero matches
- [ ] agents.md "Design system" section is complete (color contrast + typography scale + icon catalog + theme switching contract)
- [ ] CLAUDE.md mentions both a11y test (from leg 07) AND visual snapshot test
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `landed`
- [ ] Do NOT commit
- [ ] Signal `[HANDOFF:review-needed]`
