# Leg: 06-light-realization

**Status**: landed
**Flight**: [Design Language & Theme Architecture](../flight.md)

## Objective

Bring the light theme to design parity with dark by retuning the `[data-theme="light"]` token values in tokens.css. Apply per-surface design judgment so light is a coherent variant of the design language (not a pragmatic flip): off-white backgrounds with subtle cool tint, deep navy text, visibly darker borders, drop shadows in place of cyan glow (glow doesn't read on white), keep cyan accent palette + Geist + Lucide icons + `// SECTION` headers + geometric language. Reference quality: Linear light, Stripe docs light. F1 browser tests pass; dark theme unchanged.

## Context

- This is the user-requested designed light theme (per F2 mission planning: "lets add the extra leg to figure out the light mode it probably means using much light backgrounds and dark border and font variants").
- **Leg 03 outcome**: dark theme realized with cyan accent `#22d3ee`, glowing borders, translucent panels, gradient backdrop. Light theme has placeholder values (white surfaces + deeper cyan + naive gradient) that fail WCAG AA in places.
- **Leg 06 strategy**: retune `[data-theme="light"]` token values in tokens.css. Token names stay; values change. Component CSS rules don't change (they reference tokens). For elements where the visual interpretation differs (e.g., box-shadow GLOW in dark vs box-shadow DROP-SHADOW in light), the token VALUE handles the difference — same `var(--panel-shadow-glow)` resolves to a glow in dark and a drop-shadow in light.
- **Reference points**: Linear light, Stripe docs light — both use cool grays, subtle drop shadows for elevation, accent colors as borders/highlights (not glows), and feel "designed" not "white-mode'd".
- **WCAG AA targets**: 4.5:1 for body text, 3:1 for large text/interactive elements, 3:1 for UI element borders against background.
- **Out of scope for this leg**: WCAG AA audit and refinements (that's leg 07). This leg lands the design intent; leg 07 enforces compliance.
- **Dark theme MUST NOT change**: implementer should confirm dark-theme rendering is identical to pre-leg.

## Inputs

- Branch `flight/02-design-language-and-theme-architecture`, legs 01-05 landed (uncommitted)
- `the_one/interfaces/web/static/css/tokens.css` — has both theme blocks; light theme has placeholder values
- All component CSS files reference tokens; no hardcoded literals (verified by grep)
- Test baseline: 350 passed, 16 deselected; 8 browser tests passing

## Outputs

- `tokens.css` `[data-theme="light"]` block retuned with designed values per the spec below. Token names unchanged from legs 02/03 (no new tokens introduced — pure value retune).
- Possibly: 1-3 component CSS adjustments where the dark/light visual interpretation diverges enough that a `[data-theme="light"]` selector override is cleaner than retuning the token. Examples to evaluate during implementation:
  - `.msg.user` cyan glow on chat user bubble — drop-shadow translation
  - `.session-item.active` etc. — glow → border + subtle drop-shadow
  - The cyan-accent translucent fills — alpha bumps for visibility on white

## Acceptance Criteria

### Light-theme token values (designed retune)

- [ ] `tokens.css` `[data-theme="light"]` block contains the following retuned values (replacing leg 02/03 placeholder values):

  **Surfaces** (cool tint to coordinate with cyan):
  - `--bg: #fafbfc`
  - `--surface: #ffffff`
  - `--surface-elevated: #f1f5f9`
  - `--surface-tool: #f3f4f6`
  - `--surface-translucent: rgba(15, 23, 42, 0.02)` (CHANGED from rgba on white — subtle darkening of underlying bg)

  **Borders** (visibly darker than dark theme — borders need to read on light surfaces):
  - `--border: #e5e7eb`
  - `--border-hover: #cbd5e1`
  - `--border-strong: #94a3b8`

  **Text** (deep navy-black for primary; AA-compliant secondaries):
  - `--fg: #0f172a` (deep navy — slightly cooler than #1a1a1a)
  - `--fg-secondary: #334155` (was #4b5563 — darken for contrast)
  - `--fg-tertiary: #475569` (was #6b7280)
  - `--fg-muted: #64748b` (was #9ca3af; ~5.5:1 against #fafbfc — passes AA body)
  - `--fg-faint: #94a3b8` (intentional secondary-tier; AA-borderline; mark as exception)
  - `--fg-on-accent: #ffffff` (white text on cyan accent)
  - `--fg-on-accent-muted: #cbd5e1` (light gray for muted text on accent-hover bg)
  - `--fg-on-danger: #ffffff`
  - `--fg-tool-msg: #475569` (deeper for legibility)

  **Accent** (deeper cyan for contrast on light):
  - `--accent: #0891b2` (Tailwind cyan-600 — keep from leg 03 placeholder; ~4.5:1 against #fafbfc, passes AA)
  - `--accent-api: #6d28d9` (deeper purple for AA on white; was #7c3aed)
  - `--accent-glow: rgba(8, 145, 178, 0.20)` (slightly less alpha — drop shadows are subtler than glows)
  - `--accent-glow-strong: rgba(8, 145, 178, 0.35)`
  - `--accent-translucent: rgba(8, 145, 178, 0.10)` (CHANGED from 0.08 — needs to be visible on white)
  - `--accent-translucent-hover: rgba(8, 145, 178, 0.15)`

  **Status** (deeper variants for AA):
  - `--status-success: #16a34a` (Tailwind green-600)
  - `--status-warning: #ca8a04` (Tailwind yellow-600 — was #d97706, retuned for better AA)
  - `--status-warning-bg-soft: rgba(202, 138, 4, 0.08)`
  - `--status-warning-bg-soft-2: rgba(202, 138, 4, 0.12)`
  - `--status-warning-border: rgba(202, 138, 4, 0.3)`
  - `--status-danger: #dc2626` (Tailwind red-600)
  - `--status-success-glow: rgba(22, 163, 74, 0.3)`
  - `--status-warning-glow: rgba(202, 138, 4, 0.3)`
  - `--status-danger-glow: rgba(220, 38, 38, 0.3)`

  **Provider badges** (brand-stable across themes — same as dark):
  - `--badge-ollama: #2ecc71`
  - `--badge-openai-compatible: #d4a800`
  - `--badge-openai: #4a9eff` (UNCHANGED — brand stability)
  - `--badge-anthropic: #9b59b6`
  - `--badge-mock: #888888`
  - `--badge-unknown: #888888`

  **Shadows** (drop-shadow style for light, instead of glow):
  - `--panel-shadow: 0 1px 3px rgba(15, 23, 42, 0.06), 0 1px 2px rgba(15, 23, 42, 0.04)` (subtle elevation, not glow)
  - `--panel-shadow-glow: 0 4px 12px rgba(8, 145, 178, 0.18), 0 1px 3px rgba(15, 23, 42, 0.06)` (cyan-tinted drop shadow for active/hovered panels — composite of cyan tint + dark drop shadow for visible elevation on white)

  **Body backdrop** (visible cool gradient):
  - `--bg-gradient: linear-gradient(180deg, #fafbfc 0%, #f1f5f9 100%)` (subtle but visible cool fade)

  **Density-and-geometry** (same as dark — geometry doesn't change between themes):
  - `--sidebar-w: 240px`
  - `--nav-w: 48px`

  **Panel design tokens** (same as dark):
  - `--panel-radius: 10px`
  - `--panel-radius-sm: 6px`

### Component CSS adjustments

- [ ] Inspect 3-5 specific rules that may need `[data-theme="light"]` selector overrides if the token retune alone produces an awkward visual:
  - `.area-chat .msg.user` (cyan bg + cyan glow shadow): in light, the cyan bg is fine, but the cyan glow needs to land as a subtle drop shadow. If `--accent-glow` value adjustment doesn't produce a good result, add `[data-theme="light"] .area-chat .msg.user { box-shadow: 0 1px 2px rgba(0,0,0,0.08); }` override.
  - `.session-item.active` and similar active sidebar items: same consideration — glow → drop-shadow translation.
  - `.app-flash`: cyan glow on flash.
  
  Decision criterion: if the token retune produces a result that "looks like the design language in light mode" — keep it. If it looks broken or makes the element disappear — add a theme override. Document each override in a CSS comment.

### Behavioral
- [ ] Dark theme renders IDENTICALLY to pre-leg (verify with `App.theme.set('dark')` and visual comparison)
- [ ] Light theme renders as a coherent designed variant: off-white bg with cool gradient, deep navy text, visible borders, cyan accents, subtle drop shadows for elevation
- [ ] All F1 browser tests still pass (8/8) — they run in the test env's `color_scheme="no-preference"` which resolves to dark (no change for tests)
- [ ] Default `pytest tests/` shows 350 passed, 16 deselected
- [ ] No new hex/rgba leaks — grep check still clean

### Visual judgment
- [ ] Light theme looks INTENTIONAL — like Linear or Stripe light, not like dark theme with surfaces inverted
- [ ] Cyan accent reads on white surfaces (deeper variant `#0891b2` is visible)
- [ ] Active sidebar items show a clear active state (translucent cyan + cyan border + subtle drop-shadow)
- [ ] Section headers' `// ` prefix renders in cyan (recessive but visible)
- [ ] No element is illegible due to insufficient contrast (full WCAG AA enforcement is leg 07; gross failures get fixed here)
- [ ] Body gradient is subtle but visible from top to bottom
- [ ] Glow effects from leg 03 translate cleanly to drop shadows in light mode

## Verification Steps

1. **Tests pass**:
   ```bash
   pytest tests/ --tb=short -q --timeout=60
   pytest -m browser tests/browser/ -v --timeout=60
   ```
   Expected: 350/16 deselected; 8 browser tests pass.

2. **Hex/rgba grep still clean**:
   ```bash
   grep -nE "#[0-9a-fA-F]{3,8}\b|rgba?\(" the_one/interfaces/web/static/css/*.css \
     | grep -v tokens.css | grep -v fonts.css | grep -v "data:image/svg"
   ```
   Expected: empty (any new theme overrides should reference tokens, not literals).

3. **Manual visual check** (CRITICAL for this leg):
   ```bash
   docker compose up -d --build
   ```
   Open http://localhost:8484:
   - **Dark first**: `App.theme.set('dark')` — confirm IDENTICAL to pre-leg dark rendering. No regression.
   - **Light**: `App.theme.set('light')` — page should render with off-white bg, cool gradient, deep navy text, cyan accent visible (deeper than dark theme's cyan), section headers show `//` prefix in cyan, active sidebar items have cyan border + light cyan fill + subtle drop-shadow, no element illegible.
   - **Auto** (`App.theme.set('auto')`): if OS preference is dark or no preference, returns to dark. If OS preference is light, lands on light theme.

4. **Cross-area visual check** in light mode:
   - Chat: messages, telemetry, send button look right
   - Studio: section titles `// IDENTITY`, agent list active state, `+` button
   - Admin: provider cards, type badges (brand colors visible), eye-toggle on password field

## Implementation Guidance

### 1. Update `tokens.css` `[data-theme="light"]` block

Replace the existing light block contents with the retuned values per the Acceptance Criteria token list. The structure stays the same (token name organization unchanged); only values change.

Example structure:

```css
[data-theme="light"] {
  /* surfaces */
  --bg: #fafbfc;
  --surface: #ffffff;
  --surface-elevated: #f1f5f9;
  --surface-tool: #f3f4f6;
  --surface-translucent: rgba(15, 23, 42, 0.02);

  /* borders */
  --border: #e5e7eb;
  --border-hover: #cbd5e1;
  --border-strong: #94a3b8;

  /* text */
  --fg: #0f172a;
  --fg-secondary: #334155;
  --fg-tertiary: #475569;
  --fg-muted: #64748b;
  --fg-faint: #94a3b8;
  --fg-on-accent: #ffffff;
  --fg-on-accent-muted: #cbd5e1;
  --fg-on-danger: #ffffff;
  --fg-tool-msg: #475569;

  /* accent */
  --accent: #0891b2;
  --accent-api: #6d28d9;
  --accent-glow: rgba(8, 145, 178, 0.20);
  --accent-glow-strong: rgba(8, 145, 178, 0.35);
  --accent-translucent: rgba(8, 145, 178, 0.10);
  --accent-translucent-hover: rgba(8, 145, 178, 0.15);

  /* status */
  --status-success: #16a34a;
  --status-warning: #ca8a04;
  --status-warning-bg-soft: rgba(202, 138, 4, 0.08);
  --status-warning-bg-soft-2: rgba(202, 138, 4, 0.12);
  --status-warning-border: rgba(202, 138, 4, 0.3);
  --status-danger: #dc2626;
  --status-success-glow: rgba(22, 163, 74, 0.3);
  --status-warning-glow: rgba(202, 138, 4, 0.3);
  --status-danger-glow: rgba(220, 38, 38, 0.3);

  /* provider badges — brand-stable */
  --badge-ollama: #2ecc71;
  --badge-openai-compatible: #d4a800;
  --badge-openai: #4a9eff;
  --badge-anthropic: #9b59b6;
  --badge-mock: #888888;
  --badge-unknown: #888888;

  /* shadows — drop-shadow style for light (replaces dark's glow shadows) */
  --panel-shadow: 0 1px 3px rgba(15, 23, 42, 0.06), 0 1px 2px rgba(15, 23, 42, 0.04);
  --panel-shadow-glow: 0 4px 12px rgba(8, 145, 178, 0.18), 0 1px 3px rgba(15, 23, 42, 0.06);

  /* body backdrop */
  --bg-gradient: linear-gradient(180deg, #fafbfc 0%, #f1f5f9 100%);

  /* density-and-geometry */
  --sidebar-w: 240px;
  --nav-w: 48px;
  --panel-radius: 10px;
  --panel-radius-sm: 6px;
}
```

### 2. Toggle to light and inspect

```bash
docker compose up -d --build
```

In browser DevTools console: `App.theme.set('light')`. Walk through Chat / Studio / Admin and observe:
- Backgrounds, surfaces, borders, text — all look intentional?
- Cyan accent visible on buttons, borders, active states?
- Section header `//` prefix readable?
- Glow effects translated to drop shadows correctly?
- Any element illegible or visually broken?

### 3. Apply theme overrides where needed

For elements where token retune alone doesn't produce a good result, add `[data-theme="light"]` selector overrides in the appropriate component CSS file. Examples (only add if needed; if `var(--panel-shadow-glow)` token retune produces good results, no override required):

```css
@layer areas {
  /* In chat.css — only if needed */
  [data-theme="light"] .area-chat .msg.user {
    box-shadow: 0 1px 3px rgba(15, 23, 42, 0.08);
  }
}
```

Document each override with a CSS comment explaining why the token alone wasn't sufficient. Aim for ZERO overrides if possible — that's the sign tokens are doing their job.

### 4. Verify dark unchanged

`App.theme.set('dark')` and confirm pixel-identical rendering to pre-leg. The dark token block should not have changed at all in this leg.

### 5. Run tests

```bash
pytest tests/ --tb=short -q --timeout=60
pytest -m browser tests/browser/ -v --timeout=60
```

### 6. Hex/rgba grep

```bash
grep -nE "#[0-9a-fA-F]{3,8}\b|rgba?\(" the_one/interfaces/web/static/css/*.css \
  | grep -v tokens.css | grep -v fonts.css | grep -v "data:image/svg"
```

Expected: empty (any new theme overrides reference tokens, not literals).

## Edge Cases

- **Light theme passes WCAG AA "mostly" but not strictly**: `--fg-faint: #94a3b8` on `--bg: #fafbfc` is ~3.0:1 — passes for large text and UI elements (3:1) but fails for body text (4.5:1). It's used in genuinely-faint contexts (e.g., disabled-state placeholders) where this is acceptable. Leg 07 may further refine; current leg accepts.

- **`--accent-api` purple in light**: `#6d28d9` (Tailwind violet-700) on white is ~7.4:1, passes AA. The `.msg.user.api` purple bubble's white text is readable.

- **Cyan accent on light**: `#0891b2` (cyan-600) on white = ~4.5:1 contrast. Borderline AA for body text; passes for large text and UI elements. The cyan is mostly used as borders/accents/icons, not body text — those use cases are fine.

- **Drop shadows are tinted cyan in `--panel-shadow-glow`**: `rgba(8, 145, 178, 0.18)` provides the design-language tint while the second `rgba(15, 23, 42, 0.06)` provides the elevation. Composite reads as "this panel has cyan affordance with subtle elevation" — close to the dark-mode glow's purpose.

- **Test environment is `color_scheme="no-preference"` resolving to dark**: F1 tests don't render in light theme, so light values can't break them. Manual verification is the only check for light.

- **Status warning yellow tradeoff**: `#ca8a04` (Tailwind yellow-600) is darker/more amber than `#d97706` (orange-600); passes AA on white better. May read slightly less "warning" than orange — visual judgment call. If it looks weak, consider a slightly more saturated variant.

- **Body gradient subtlety**: `#fafbfc → #f1f5f9` is a small delta (~3-4 perceptual units). Visible in a tall viewport, may be imperceptible in a short one. Acceptable.

- **Existing mock providers in light theme**: leg 02 noted that mock providers created in dark mode keep rendering when light is enabled. Verified that `--badge-mock: #888888` works in both themes.

## State-Machine Reachability Audit

This leg introduces no new states. Pure value retune of existing light-theme tokens. No new tokens introduced (or at most 0-3 if theme overrides are added). Component CSS unchanged unless overrides needed.

✓ Pass.

## Cache Freshness Contract

No caches. Pure CSS value changes.

✓ Pass.

## Files Affected

- `the_one/interfaces/web/static/css/tokens.css` — `[data-theme="light"]` block retuned (~30 lines changed; values only, no name changes)
- Possibly: 1-3 component CSS files if theme overrides needed (target: zero overrides)

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing: `pytest tests/` shows 350/16 deselected; `pytest -m browser tests/browser/` shows 8 passed
- [ ] Hex/rgba grep returns zero matches
- [ ] Manual visual check: dark theme IDENTICAL to pre-leg; light theme is a coherent designed variant (Linear/Stripe-light quality), no element illegible, cyan visible, section headers readable, drop shadows visible
- [ ] If theme overrides were added: each documented with CSS comment explaining why
- [ ] Update flight-log.md with leg progress entry (status, what was done, anomalies, list of any theme overrides added)
- [ ] Set this leg's status to `landed`
- [ ] Do NOT commit
- [ ] Signal `[HANDOFF:review-needed]`
