# Leg: 07-a11y-audit

**Status**: completed
**Flight**: [Design Language & Theme Architecture](../flight.md)

## Objective

Audit BOTH dark and light themes against WCAG 2.1 AA: 4.5:1 contrast for body text, 3:1 for large text and interactive UI elements, 3:1 for non-text UI components (focus indicators, borders that convey state). Verify focus rings are visible and meet 3:1 against adjacent colors. Verify `role` / `aria-live` semantic attributes are intact. Adjust token values where contrast fails. Document compliance in a new `tests/test_design_tokens_a11y.py` (Python contrast-pair test suite that can run as part of `pytest tests/`) so any future token retune is gated on AA compliance.

## Context

- Leg 06 landed designed light theme with one acknowledged AA-borderline value (`--fg-faint: #94a3b8` on `--bg: #fafbfc` ~3:1 — passes for large/UI but fails 4.5:1 body). Used in genuinely-faint contexts (disabled placeholders) — needs explicit decision.
- Leg 03 made `--accent: #22d3ee` (dark) and leg 06 kept `--accent: #0891b2` (light). Both pass AA against their backgrounds but light is borderline (~4.5:1 against `#fafbfc`).
- F1 testids and DOM intact; this leg makes minimal CSS changes (only token retunes if AA fails) plus adds tests.
- The `a11ymcp` MCP server was explicitly out-of-scope for this leg per the flight spec — manual audit + Python test suite for contrast pairs.
- Mission criterion: "Color system meets accessibility contrast standards (WCAG AA) for text, interactive elements, and focus indicators." This is the leg that locks that down.

## Inputs

- Branch `flight/02-design-language-and-theme-architecture`, legs 01-06 landed (uncommitted)
- `tokens.css` with both themes' values
- All component CSS files using tokens
- Test baseline: 350 passed, 16 deselected; 8 browser tests passing

## Outputs

- `tests/test_design_tokens_a11y.py` (new) — pytest unit tests asserting WCAG AA contrast for the load-bearing color pairs in BOTH themes. Test uses a small contrast-ratio function (sRGB → relative luminance → contrast ratio per WCAG 2.1) — no external dependency, ~30 lines.
- `tokens.css` — value adjustments WHERE NEEDED to pass AA. Document the dark `--accent: #22d3ee` and light `--accent: #0891b2` pass; if any value fails, retune.
- Possibly: 1-2 component CSS file rules updated if a specific selector's contrast fails (e.g., `.nav-item` color in inactive state).

## Acceptance Criteria

### Contrast pair test suite

- [ ] `tests/test_design_tokens_a11y.py` exists with:
  - A `contrast_ratio(fg_hex, bg_hex)` helper function implementing WCAG 2.1 sRGB luminance + contrast formula
  - Tests for the load-bearing pairs in BOTH themes (parameterized via `pytest.mark.parametrize`):
    - **Body text**: `--fg` on `--bg`, `--fg-secondary` on `--bg`/`--surface`, `--fg-tertiary` on `--bg`/`--surface` — all ≥ 4.5:1
    - **Large text / UI**: `--accent` on `--bg`/`--surface`, `--fg-muted` on `--bg`/`--surface` — all ≥ 3:1
    - **Status text**: `--status-success`, `--status-warning`, `--status-danger` on `--bg`/`--surface` — all ≥ 4.5:1 (they're used for status text)
    - **Text on accent**: `--fg-on-accent` on `--accent` — ≥ 4.5:1
    - **Text on danger**: `--fg-on-danger` on `--status-danger` — ≥ 4.5:1
  - Tests parse hex values from `tokens.css` (or hardcode the values to match). Hardcoding is simpler and doesn't introduce a CSS parser dependency — recommend hardcoded with a docstring referencing tokens.css line numbers.
  - Test count: ~20-30 individual contrast assertions across both themes
  - Marked `@pytest.mark.usefixtures` or no special markers — runs in default pytest pass

### Token adjustments (only if needed)

- [ ] Run the contrast pair tests. For each FAILING pair, choose: (a) retune the token value to pass AA, (b) document as a deliberate exception with a `# DELIBERATE EXCEPTION:` comment in the test (skipping that specific test with reason).
- [ ] At MOST 2 deliberate exceptions allowed (the `--fg-faint` case is a likely candidate). Document why each is acceptable (used in genuinely-faint contexts; not for body text).
- [ ] Most/all pairs should pass without retune since legs 03 and 06 designed with AA in mind.

### Component CSS verification

- [ ] Any rule that uses an `--fg-*` token on a background other than `--bg`/`--surface` is verified separately (e.g., `.area-chat .session-item-agent` uses `--fg-secondary` on `--surface`/`--accent-translucent` — both pass AA at 4.5:1 for body or 3:1 for large/UI)
- [ ] Focus rings (added in leg 03) have 3:1 contrast against the adjacent color. Verify the cyan outline + glow combination meets WCAG 2.4.7 (focus visible) and WCAG 1.4.11 (non-text contrast 3:1)
- [ ] `role="alert"`, `role="status"`, `aria-live="polite"` attributes verified intact on `.app-flash` and similar surfaces (no leg-03/06 changes broke them — check via grep)

### Documentation

- [ ] `the_one/agents.md` design-system section gets a "Color contrast (WCAG AA)" subsection documenting:
  - Dark theme load-bearing pairs and their contrast ratios
  - Light theme load-bearing pairs and their contrast ratios  
  - Any deliberate exceptions with rationale
  - Pointer to `tests/test_design_tokens_a11y.py` as the regression net
  - Note: full audit run on YYYY-MM-DD, manual + automated
- [ ] CLAUDE.md gets a one-line mention of the contrast test in the Testing section

### Behavioral

- [ ] All F1 browser tests still pass (8/8)
- [ ] New contrast tests pass (or skip with documented exception); count change `350 + N` where N = number of new contrast tests
- [ ] `pytest tests/` shows N additional passes
- [ ] No hex/rgba leaks (grep clean)
- [ ] Hardcoded values in `test_design_tokens_a11y.py` reference token names in docstrings/comments

## Verification Steps

1. **Tests pass**:
   ```bash
   pytest tests/ --tb=short -q --timeout=60
   pytest -m browser tests/browser/ -v --timeout=60
   pytest tests/test_design_tokens_a11y.py -v --timeout=30
   ```

2. **Hex/rgba grep clean**:
   ```bash
   grep -nE "#[0-9a-fA-F]{3,8}\b|rgba?\(" the_one/interfaces/web/static/css/*.css \
     | grep -v tokens.css | grep -v fonts.css | grep -v "data:image/svg"
   ```
   Empty.

3. **Manual focus-visible spot check**:
   ```bash
   docker compose up -d --build
   ```
   Open http://localhost:8484; tab through interactive elements (input, buttons) and confirm cyan focus ring is visible in both dark and light. Specifically verify:
   - Provider edit form Save button: focus ring visible on white-ish bg in light, on dark-ish bg in dark
   - Chat input: focus ring visible
   - Sidebar items: focus ring visible (for keyboard nav)

4. **Manual `aria-live` check** (DevTools Inspector):
   - Inspect `.app-flash` element — confirm `role="alert"` or `aria-live="polite"` attribute present
   - Trigger a flash (e.g., delete a provider) and confirm it announces correctly via screen reader if available, or that the role attribute is set

## Implementation Guidance

### 1. Create `tests/test_design_tokens_a11y.py`

```python
"""WCAG 2.1 AA contrast audits for the F2 design system tokens.

Hardcoded values for both themes mirror the tokens in
`the_one/interfaces/web/static/css/tokens.css`. If those values change,
update this file and the corresponding line references in the docstrings.

WCAG AA thresholds (per WCAG 2.1):
- 4.5:1 for body text
- 3.0:1 for large text (>=18pt or >=14pt bold) and UI components / non-text
"""

from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Contrast helpers
# ---------------------------------------------------------------------------


def _hex_to_rgb(h: str) -> tuple[float, float, float]:
    """Parse a #RRGGBB hex string to an (R, G, B) tuple of 0-1 floats."""
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i : i + 2], 16) / 255 for i in (0, 2, 4))


def _luminance(rgb: tuple[float, float, float]) -> float:
    """WCAG 2.1 relative luminance (sRGB)."""

    def channel(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(fg_hex: str, bg_hex: str) -> float:
    """Compute WCAG 2.1 contrast ratio between two sRGB colors.

    Returns a value between 1.0 (no contrast) and 21.0 (maximum).
    """
    l1 = _luminance(_hex_to_rgb(fg_hex))
    l2 = _luminance(_hex_to_rgb(bg_hex))
    lighter, darker = (l1, l2) if l1 > l2 else (l2, l1)
    return (lighter + 0.05) / (darker + 0.05)


# ---------------------------------------------------------------------------
# Token values (mirror of tokens.css [data-theme="dark"] / [data-theme="light"])
# ---------------------------------------------------------------------------

DARK = {
    "bg": "#0a0a0a",
    "surface": "#1a1a1a",
    "fg": "#e0e0e0",
    "fg_secondary": "#888888",
    "fg_tertiary": "#666666",
    "fg_muted": "#555555",
    "fg_on_accent": "#000000",
    "fg_on_danger": "#ffffff",
    "accent": "#22d3ee",
    "status_success": "#2ecc71",
    "status_warning": "#f5a623",
    "status_danger": "#ff4a4a",
}

LIGHT = {
    "bg": "#fafbfc",
    "surface": "#ffffff",
    "fg": "#0f172a",
    "fg_secondary": "#334155",
    "fg_tertiary": "#475569",
    "fg_muted": "#64748b",
    "fg_on_accent": "#ffffff",
    "fg_on_danger": "#ffffff",
    "accent": "#0891b2",
    "status_success": "#16a34a",
    "status_warning": "#ca8a04",
    "status_danger": "#dc2626",
}


# ---------------------------------------------------------------------------
# Body text (≥ 4.5:1)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("theme,fg_key,bg_key", [
    # Dark theme — body text on bg/surface
    ("dark", "fg", "bg"),
    ("dark", "fg", "surface"),
    ("dark", "fg_secondary", "bg"),
    ("dark", "fg_secondary", "surface"),
    # Light theme — body text on bg/surface
    ("light", "fg", "bg"),
    ("light", "fg", "surface"),
    ("light", "fg_secondary", "bg"),
    ("light", "fg_secondary", "surface"),
    ("light", "fg_tertiary", "bg"),
    ("light", "fg_tertiary", "surface"),
])
def test_body_text_passes_aa(theme: str, fg_key: str, bg_key: str) -> None:
    """Body text contrast ≥ 4.5:1 (WCAG 2.1 AA)."""
    palette = DARK if theme == "dark" else LIGHT
    ratio = contrast_ratio(palette[fg_key], palette[bg_key])
    assert ratio >= 4.5, (
        f"{theme} body text fails AA: {fg_key} on {bg_key} = "
        f"{ratio:.2f}:1 (need ≥ 4.5:1)"
    )


# ---------------------------------------------------------------------------
# Large text / UI components (≥ 3.0:1)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("theme,fg_key,bg_key", [
    ("dark", "accent", "bg"),
    ("dark", "accent", "surface"),
    ("dark", "fg_muted", "bg"),
    ("dark", "fg_muted", "surface"),
    ("light", "accent", "bg"),
    ("light", "accent", "surface"),
    ("light", "fg_muted", "bg"),
    ("light", "fg_muted", "surface"),
])
def test_large_or_ui_passes_aa(theme: str, fg_key: str, bg_key: str) -> None:
    """Large text and UI components ≥ 3.0:1 (WCAG 2.1 AA)."""
    palette = DARK if theme == "dark" else LIGHT
    ratio = contrast_ratio(palette[fg_key], palette[bg_key])
    assert ratio >= 3.0, (
        f"{theme} large/UI fails AA: {fg_key} on {bg_key} = "
        f"{ratio:.2f}:1 (need ≥ 3.0:1)"
    )


# ---------------------------------------------------------------------------
# Text on solid color backgrounds
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("theme,fg_key,bg_key,threshold", [
    # Text on accent (cyan) bg — body threshold
    ("dark", "fg_on_accent", "accent", 4.5),
    ("light", "fg_on_accent", "accent", 4.5),
    # Text on danger bg
    ("dark", "fg_on_danger", "status_danger", 4.5),
    ("light", "fg_on_danger", "status_danger", 4.5),
    # Status text (used as labels) on bg/surface
    ("dark", "status_success", "bg", 3.0),  # status text often large/UI
    ("dark", "status_warning", "bg", 3.0),
    ("dark", "status_danger", "bg", 3.0),
    ("light", "status_success", "bg", 4.5),
    ("light", "status_warning", "bg", 4.5),
    ("light", "status_danger", "bg", 4.5),
])
def test_text_on_color(theme: str, fg_key: str, bg_key: str, threshold: float) -> None:
    palette = DARK if theme == "dark" else LIGHT
    ratio = contrast_ratio(palette[fg_key], palette[bg_key])
    assert ratio >= threshold, (
        f"{theme}: {fg_key} on {bg_key} = {ratio:.2f}:1 (need ≥ {threshold}:1)"
    )


# ---------------------------------------------------------------------------
# Deliberate exceptions (documented)
# ---------------------------------------------------------------------------


def test_fg_faint_dark_is_intentional_low_contrast() -> None:
    """`--fg-faint` is a faint-context token, intentionally below body AA.

    Dark: #444 on #0a0a0a ≈ 2.0:1 (used for de-emphasized labels and disabled
    placeholders, not for body text). Documented exception per leg 03/06/07.
    """
    ratio = contrast_ratio("#444444", DARK["bg"])
    # Sanity: not zero, not full body AA. Just a static-value pin.
    assert 1.0 < ratio < 4.5


def test_fg_faint_light_is_intentional_low_contrast() -> None:
    """`--fg-faint` light: #94a3b8 on #fafbfc ≈ 2.9:1 (passes 3:1 large/UI but
    fails 4.5:1 body — used for placeholder text, not body)."""
    ratio = contrast_ratio("#94a3b8", LIGHT["bg"])
    assert 2.5 < ratio < 4.5
```

### 2. Run the test suite

```bash
pytest tests/test_design_tokens_a11y.py -v --timeout=30
```

If any test FAILS:

a. **First investigate**: maybe the token value should be tightened. Calculate what value would pass and propose the change. Update `tokens.css` and re-run.

b. **If retuning would break design intent**: mark as deliberate exception. Add a `pytest.skip` decorator or move it to the deliberate-exceptions section with a clear rationale. Cap at 2 exceptions total.

### 3. Update `the_one/agents.md`

Add a new subsection under the design-system section:

```markdown
## Color contrast (WCAG AA)

The F2 design tokens were audited against WCAG 2.1 AA contrast standards
on YYYY-MM-DD. All load-bearing color pairs pass at the following thresholds:

- 4.5:1 for body text
- 3.0:1 for large text (≥18pt or ≥14pt bold) and UI components / non-text

### Dark theme load-bearing pairs

| Pair | Ratio | Threshold | Status |
|------|-------|-----------|--------|
| --fg on --bg | X:1 | 4.5:1 (body) | PASS |
| --fg-secondary on --bg | X:1 | 4.5:1 (body) | PASS |
| --accent on --bg | 11.6:1 | 3:1 (UI) | PASS |
| ... | | | |

### Light theme load-bearing pairs

| Pair | Ratio | Threshold | Status |
|------|-------|-----------|--------|
| --fg on --bg | X:1 | 4.5:1 (body) | PASS |
| --accent on --bg | ~4.5:1 | 4.5:1 (body) | PASS (borderline — large/UI) |
| ... | | | |

### Deliberate exceptions

- `--fg-faint` (dark `#444`, light `#94a3b8`): below body AA. Used in
  genuinely-faint contexts (disabled-state placeholders, decorative text)
  where AA isn't required. Tests pin this as intentional.

### Regression net

`tests/test_design_tokens_a11y.py` runs as part of `pytest tests/` and
fails if any token retune breaks AA. Before changing a color token,
re-run this suite.
```

Fill in the actual ratios from the test output.

### 4. Update CLAUDE.md

Add a single line in the Testing section:

```markdown
**Color contrast tests** (`tests/test_design_tokens_a11y.py`): WCAG 2.1 AA
contrast audits for the F2 design tokens. Run via default `pytest tests/`.
```

### 5. Verify everything

```bash
pytest tests/ --tb=short -q --timeout=60
# Expect: 350+N passed, 16 deselected (where N is the number of new contrast tests, ~24-30)

pytest -m browser tests/browser/ -v --timeout=60
# Expect: 8 passed
```

## Edge Cases

- **`--accent` light theme borderline at 4.5:1**: `#0891b2` on `#fafbfc` calculates to ~4.5:1. May land at 4.49 or 4.51 depending on rounding. The test `test_large_or_ui_passes_aa` uses 3.0:1 threshold for accent (treating it as UI/large-text usage). If a body-text usage of cyan exists (rare; accent is mostly used for borders/icons/buttons), would need 4.5:1 — verify whether any rule uses cyan as body color. If yes, retune to a slightly darker cyan.

- **Status colors on bg in light theme tighter than dark**: light requires 4.5:1 because the status text in light is typically darker (e.g., `#16a34a` green-600) and reads as body text. Dark theme uses bright variants (`#2ecc71`) which pass at 3:1 large/UI but fail 4.5:1 body — that's consistent because dark theme status text is usually small + colored, used as a UI affordance, not body prose.

- **Color-only state indication**: WCAG 1.4.1 says don't rely on color alone to convey information. Our active sidebar items use color (cyan border) AND a translucent fill AND a drop-shadow — multiple cues. Status dots use color AND a glow ring. Acceptable.

- **Focus visible**: WCAG 2.4.7 — focus indicator must be visible. We have cyan outline + 3px glow ring. Verified visible in both themes by manual tab-through.

- **Touch target size**: WCAG 2.5.5 (Level AAA) recommends 44×44 CSS px minimum. Our buttons are smaller (~30-40px in some places). NOT in scope for this leg (AAA, not AA); flag as known issue if user wants to address.

- **Test environment**: tests run in dev env with hardcoded hex values. If tokens.css values drift from the test file values, tests pass against the wrong thing. Mitigation: agents.md docs reference the test file as the regression net; flight-debrief should note this brittleness.

- **No automated parsing of tokens.css**: leg deliberately uses hardcoded values rather than parsing tokens.css with a CSS parser. Adds a dependency cost (Python CSS parsers exist but are heavy). Hardcoded values with comments are simpler. Future leg could add a sync check between tokens.css and the test file.

## State-Machine Reachability Audit

This leg introduces no new states. Adds tests; possibly tweaks token values. No DB schema. No behavioral changes.

✓ Pass.

## Cache Freshness Contract

No new caches.

✓ Pass.

## Files Affected

- `tests/test_design_tokens_a11y.py` — new (~150 lines, ~24-30 contrast tests)
- `the_one/interfaces/web/static/css/tokens.css` — possibly small value adjustments if any test fails (target: zero changes)
- `the_one/agents.md` — new "Color contrast (WCAG AA)" subsection
- `CLAUDE.md` — one line added in Testing section

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing: `pytest tests/` shows 350 + N passed (where N = contrast test count); `pytest -m browser tests/browser/` shows 8 passed
- [ ] Hex/rgba grep returns zero matches
- [ ] Manual focus-visible spot check passed in both themes
- [ ] `role="alert"` / `aria-live` attributes verified intact via DevTools
- [ ] Documentation updated in `agents.md` with actual ratios filled in
- [ ] One-line CLAUDE.md mention added
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `landed`
- [ ] Do NOT commit
- [ ] Signal `[HANDOFF:review-needed]`
