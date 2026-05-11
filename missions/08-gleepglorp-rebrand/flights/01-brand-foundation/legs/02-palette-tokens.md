# Leg: 02-palette-tokens

**Status**: completed
**Flight**: [Brand Foundation](../flight.md)

## Objective

Retune the `--accent` and related accent-* token values in `tokens.css` from the existing NEXUS-style cyan to a purple/violet GleepGlorp accent in both light and dark themes; shift `--accent-api` to a complementary teal so the chat user-vs-API message differentiation survives; update the Python token mirror; extend the WCAG audit to cover the previously-silent `--accent-api`-as-background slot; iterate hex values until the full contrast audit is green.

## Context

- Leg 2 of 5 in Flight 1 (Brand Foundation). Leg 1 landed the mascot assets, favicon, and topbar icon with the existing cyan palette still in effect. After this leg the running app shows purple-accented buttons, focus rings, links, and chat-user-message bubbles in both themes.
- The palette landed here is a **starter** per Flight 2 (Design Language) — that flight may retune in concert with the robot/control-panel aesthetic exploration. So we are NOT trying to nail the final aesthetic in this leg; we are trying to land a coherent, AA-compliant purple-led starting point.
- The CSS layer routes every primary-color expression through `var(--accent)` (164 references at flight-design time). Changing the token value retires cyan globally without touching consumers. The class names `btn-filled-cyan` / `btn-outlined-cyan` are a separate misnomer that Leg 3 renames.
- `--accent-api` is currently `#7c4dff` (dark) / `#6d28d9` (light) — already a violet — used as the background for API-provider chat messages at `the_one/interfaces/web/static/css/chat.css:94 — ".area-chat .msg.user.api { background: var(--accent-api); ..."`. When `--accent` becomes purple, `--accent-api` will lose its differentiation role and read as a near-duplicate. The flight resolution is to shift `--accent-api` to teal — effectively recycling the retired-cyan into the secondary-accent slot so the user-vs-API differentiation persists.
- The WCAG audit at `tests/test_design_tokens_a11y.py` is the regression net. Its Python mirror at `tests/browser/design_tokens.py` covers `--accent` but does NOT currently carry `--accent-api`, and the audit therefore does not check `--fg-on-accent` on `--accent-api` despite that pair being load-bearing on every API user message. Leg 02 extends the mirror and adds the missing parametrization (per round-2 architect review of the flight).
- Token name strategy from the flight spec: change token VALUES; keep token names. `--accent` stays `--accent` even though its value is now purple. This keeps the diff small and avoids cascading renames across 164 CSS references.
- `tokens.css` carries historical comments referencing "NEXUS-style cyan", "cool-tinted off-white, coordinates with cyan accent", and "cyan-700" at lines ~3, 115, 138-141. Leg 03 cleans those up alongside the CSS class rename — NOT this leg's scope.

### Starter palette working values

These are the working candidates; final values are pinned when the WCAG audit goes green:

| Token | Dark | Light | Rationale |
|---|---|---|---|
| `--accent` | `#a78bfa` (violet-400) | `#6d28d9` (violet-700) | Purple-led identity; dark uses lighter shade for body bg contrast, light uses deeper for `fg-on-accent: #ffffff` body AA |
| `--accent-api` | `#22d3ee` (cyan-400 — the retired primary) | `#0e7490` (cyan-700 — the retired primary) | Complementary teal/cyan; recycles the previous app accent into the secondary slot |
| `--accent-glow` | `rgba(167, 139, 250, 0.25)` | `rgba(109, 40, 217, 0.20)` | Alpha mirrors current cyan-glow values; base color shifts to violet |
| `--accent-glow-strong` | `rgba(167, 139, 250, 0.40)` | `rgba(109, 40, 217, 0.35)` | Same alpha as current |
| `--accent-translucent` | `rgba(167, 139, 250, 0.08)` | `rgba(109, 40, 217, 0.10)` | Same alpha as current |
| `--accent-translucent-hover` | `rgba(167, 139, 250, 0.12)` | `rgba(109, 40, 217, 0.15)` | Same alpha as current |
| `--panel-shadow-glow` (light) | (unchanged structure) | `0 4px 12px rgba(109, 40, 217, 0.18), 0 1px 3px rgba(15, 23, 42, 0.06)` | The light shadow currently composites cyan tint with dark elevation; swap cyan rgba for violet rgba |
| `--nav-fg-active` (light theme nav rail) | (n/a — dark theme uses `var(--accent)`) | `#a78bfa` (or whatever dark `--accent` becomes after WCAG iteration) | The light-theme nav rail uses the dark palette internally (dark navy `--nav-bg: #0f172a`); its active-state color is hardcoded cyan-400 today. Without retuning, the rail stays cyan while everything else goes purple — visible inconsistency exactly where the brand reads loudest. |

Audit expectations against starter values (computed via WCAG 2.1 sRGB formula):
- **`fg_on_accent` on `accent`** (dark `#000` on `#a78bfa`) → contrast ≈ 7.72:1 — passes body AA (4.5:1)
- **`fg_on_accent` on `accent`** (light `#ffffff` on `#6d28d9`) → contrast ≈ 7.10:1 — passes body AA
- **`accent` on `bg`** (dark `#a78bfa` on `#0a0a0a`) → contrast ≈ 9.50:1 — passes large/UI AA (3.0:1)
- **`accent` on `bg`** (light `#6d28d9` on `#fafbfc`) → contrast ≈ 6.86:1 — passes large/UI AA
- **`fg_on_accent` on `accent_api`** (dark `#000` on `#22d3ee`) → contrast ≈ 11.62:1 — passes body AA
- **`fg_on_accent` on `accent_api`** (light `#ffffff` on `#0e7490`) → contrast ≈ 5.36:1 — passes body AA
- **`nav-fg-active` on `nav-bg`** (light nav-rail `#a78bfa` on `#0f172a`) → contrast ≈ 9.5:1 — passes large/UI AA

If any pair undershoots after first run, iterate by darkening/lightening one stop.

## Inputs

Files that must exist (verified at design time):
- `the_one/interfaces/web/static/css/tokens.css` — current accent-* token block; dark at lines 46-52, light at lines 142-147, light `--panel-shadow-glow` at line 189
- `tests/browser/design_tokens.py` — Python mirror; DARK at lines 30-46, LIGHT at lines 53-71. Currently carries `accent` but NOT `accent_api`
- `tests/test_design_tokens_a11y.py` — WCAG audit module
  - `test_body_text_passes_aa` parametrize block — body text pairs (lines ~82-99)
  - `test_large_or_ui_passes_aa` parametrize block — UI / large text pairs incl. `accent on bg` / `accent on surface` (lines ~115-137)
  - `test_text_on_color` parametrize block — text-on-color pairs incl. `fg_on_accent on accent` (lines ~152-176)
- `the_one/interfaces/web/static/css/chat.css:94 — ".area-chat .msg.user.api { background: var(--accent-api); ..."` — the consumer that makes `--accent-api` a load-bearing background

State that must be true:
- Leg 01 landed (status `landed`) and is awaiting Reviewer at flight-commit time. Working tree on `flight/01-brand-foundation` branch.
- Container is running (`make up` if not)

## Outputs

Files modified:
- `the_one/interfaces/web/static/css/tokens.css` — six accent-* values retuned in `[data-theme="dark"]` block; six in `[data-theme="light"]` block; light `--panel-shadow-glow` recomposed with violet rgba; light `--nav-fg-active` retuned from hardcoded `#22d3ee` to the new violet-leaning value
- `tests/browser/design_tokens.py` — `accent` values updated in DARK and LIGHT dicts; new `accent_api` key added to both
- `tests/test_design_tokens_a11y.py` — three new parametrization tuples added to `test_text_on_color`: `("dark", "fg_on_accent", "accent_api", 4.5)`, `("light", "fg_on_accent", "accent_api", 4.5)`, plus `("light", "accent_api", "bg", 3.0)` as a defensive UI/large pair (future-proofs against `--accent-api` being used as a border/icon stroke)

State changes:
- Running app's primary accent reads as purple/violet in both themes — buttons, focus rings, links, `.msg.user`, `.list-item.active`, etc.
- API user messages in chat read as teal/cyan rather than violet, preserving the user-vs-API differentiation
- WCAG audit now covers the previously-silent `accent-api` text-on-color slot

## Acceptance Criteria

- [ ] `tokens.css` `[data-theme="dark"]` accent block has the six new starter values (or a documented iteration if WCAG required tuning): `--accent: #a78bfa` (or iterated), plus the five accent-glow/translucent values keyed off the same base hue
- [ ] `tokens.css` `[data-theme="light"]` accent block has the six new starter values: `--accent: #6d28d9` (or iterated), plus the five accent-glow/translucent values keyed off the same base hue
- [ ] `tokens.css` `[data-theme="dark"]` `--accent-api` is teal/cyan (starter `#22d3ee` or iterated)
- [ ] `tokens.css` `[data-theme="light"]` `--accent-api` is teal/cyan (starter `#0e7490` or iterated)
- [ ] `tokens.css` `[data-theme="light"]` `--panel-shadow-glow` first rgba argument uses the new light `--accent` base color (not the retired cyan-700)
- [ ] `tokens.css` `[data-theme="light"]` `--nav-fg-active` is retuned from the hardcoded `#22d3ee` to a value matching the new dark `--accent` (since the nav rail uses the dark palette internally — see existing comment at the rule)
- [ ] `tests/browser/design_tokens.py` `DARK["accent"]` and `LIGHT["accent"]` match the values in `tokens.css` exactly
- [ ] `tests/browser/design_tokens.py` `DARK["accent_api"]` and `LIGHT["accent_api"]` exist and match the values in `tokens.css` exactly
- [ ] `tests/test_design_tokens_a11y.py::test_text_on_color` parametrize list includes `("dark", "fg_on_accent", "accent_api", 4.5)`, `("light", "fg_on_accent", "accent_api", 4.5)`, AND `("light", "accent_api", "bg", 3.0)`
- [ ] `docker exec the-one pytest tests/test_design_tokens_a11y.py tests/test_token_definitions.py -x -q --timeout 10` exits 0 (full WCAG audit passes including the new accent_api pairs; token-definitions test confirms no `var(--x)` orphans)
- [ ] `make verify-serving` exits 0 (no functional regressions)
- [ ] Final hex values are recorded in the flight log entry for this leg, including any iteration step values that didn't make it (so future readers see why the final choice was made)

## Verification Steps

- **Tokens.css retuned correctly**:
  ```
  grep -A1 "\-\-accent:" the_one/interfaces/web/static/css/tokens.css
  # Expect: dark accent (violet-leaning) + light accent (deeper violet); no #22d3ee or #0e7490 as the primary --accent value
  grep "\-\-accent-api:" the_one/interfaces/web/static/css/tokens.css
  # Expect: teal/cyan values (#22d3ee dark, #0e7490 light or iterated)
  ```
- **Python mirror in sync**:
  ```
  docker exec the-one python -c "from browser.design_tokens import DARK, LIGHT; print('dark accent:', DARK['accent'], '| dark accent_api:', DARK['accent_api']); print('light accent:', LIGHT['accent'], '| light accent_api:', LIGHT['accent_api'])"
  ```
- **WCAG audit green**:
  ```
  docker exec the-one pytest tests/test_design_tokens_a11y.py -v --timeout 10
  # Expect: all parametrizations pass; the two new accent_api pairs appear in the parametrize id output
  ```
- **Token definitions clean**:
  ```
  docker exec the-one pytest tests/test_token_definitions.py -x -q --timeout 10
  # Expect: exit 0 — no orphan var(--x) references
  ```
- **Serving check**: `make verify-serving` exits 0
- **Visual sanity (manual, optional)**: after `make rebuild`, load `http://localhost:8484/`; primary buttons, focus rings, and chat-user-message bubbles should read as purple/violet; API user messages teal/cyan. Side-by-side with `[data-theme="dark"]` and `[data-theme="light"]` via the appearance toggle in Admin → System.

## Implementation Guidance

1. **Update `tokens.css` `[data-theme="dark"]` accent block** (currently lines 46-52)
   - Replace the 6 accent-* values with the starter dark palette (see table in Context)
   - Preserve the surrounding comment block structure; the historical "NEXUS-style cyan" framing in the file docstring (line ~3) and other in-file comments stay UNTOUCHED — Leg 03 cleans those up

2. **Update `tokens.css` `[data-theme="light"]` accent block** (currently lines 142-147)
   - Replace the 6 accent-* values with the starter light palette
   - Update `--panel-shadow-glow` at line ~189: replace `rgba(14, 116, 144, 0.18)` (cyan-700) with `rgba(109, 40, 217, 0.18)` (or whatever the final light --accent base is, after WCAG iteration); the second `rgba(15, 23, 42, 0.06)` slate-900 component stays unchanged
   - Update `--nav-fg-active` at line ~208 (inside the same `[data-theme="light"]` block, under the `/* nav rail palette ... */` comment): replace `#22d3ee` with the dark `--accent` value (e.g., `#a78bfa` starter). Update the inline comment that currently says "we use cyan-400 for the active state" to reflect the new color family (e.g., "we use the dark-theme violet for the active state — visible on the dark navy rail").

3. **Update `tests/browser/design_tokens.py`**
   - Change `DARK["accent"]` value to match new `tokens.css` dark `--accent`
   - Change `LIGHT["accent"]` value to match new `tokens.css` light `--accent`
   - Add `DARK["accent_api"]` and `LIGHT["accent_api"]` keys with matching values
   - Update the inline comments around the changed keys to reflect the new color family (drop "cyan-700" references; replace with "violet-700 (or whatever the final value is)"). The module-level docstring's note about being a mirror of `tokens.css` stays.

4. **Update `tests/test_design_tokens_a11y.py::test_text_on_color` parametrize block** (currently lines 152-176)
   - Add three new tuples to the parametrize list, sitting adjacent to the existing `fg_on_accent on accent` pairs (lines 156-157):
     ```python
     # accent_api is used as a chat message background at chat.css:94 —
     # text-on-color body threshold applies (foreground inherits --fg-on-accent
     # from the parent .msg.user rule). Defensive UI/large pair guards against
     # future use as a border/icon stroke.
     ("dark", "fg_on_accent", "accent_api", 4.5),
     ("light", "fg_on_accent", "accent_api", 4.5),
     ("light", "accent_api", "bg", 3.0),
     ```
   - Also update the existing comment at line 155 — `# Text on accent (cyan) — body threshold ...` is stale post-retune; change "cyan" to "primary accent" or drop the parenthetical entirely.

5. **Run the audit** (`docker exec the-one pytest tests/test_design_tokens_a11y.py -v --timeout 10`)
   - All existing parametrizations must continue to pass
   - The two new `accent_api` pairs must pass
   - If a value fails, iterate by one shade darker or lighter; the working starter values are conservative (well above 4.5:1) so failure is unlikely but possible after retune

6. **Run token-definitions** (`docker exec the-one pytest tests/test_token_definitions.py -x -q --timeout 10`)
   - Catches typos where a CSS rule references `var(--x)` without a definition. Should be unchanged by this leg (we changed values, not names), but verify.

7. **Rebuild and serve check**
   - `make rebuild` to bake the updated CSS into the container's image-baked path
   - `make verify-serving` to confirm all admin sub-modules return 200

8. **Visual spot-check (optional but recommended)**
   - Load `http://localhost:8484/` in a private window
   - Toggle the theme via Admin → System → Appearance
   - Note any obvious visual issue (e.g., the new accent reads too dark/light against `--surface-translucent` overlay) for the alignment HAT in Leg 05

## Edge Cases

- **Audit fails on a value**: iterate. Common direction: light theme values may need to be one stop darker if `accent on bg` undershoots 3:1 large/UI threshold, or `fg_on_accent on accent` undershoots 4.5:1 body. The audit assertion message names the exact pair and ratio — that tells you which direction to move.
- **`--accent-api` text contrast on the chat.css consumer**: the `.area-chat .msg.user.api` rule inherits `color` from `.area-chat .msg.user` which is `var(--fg-on-accent)`. The new test parametrization pins this pair. If a designer ever changes the chat-user-message text color, both the parametrization and the chat.css rule need updating in lockstep.
- **Iteration values that didn't ship**: capture rejected values in the flight log Leg Progress entry so future readers see the iteration path, not just the final answer. Example: "Tried `#7c3aed` for light --accent — `fg_on_accent on accent` came in at 4.32:1 (4.5 required). Stepped to `#6d28d9` (violet-700, 7.2:1)."
- **Theme toggle UI**: the appearance toggle in Admin → System is the easiest way to compare dark/light. If the toggle itself fails for some reason post-retune (very unlikely — no JS changes here), note it.

## Files Affected

- `the_one/interfaces/web/static/css/tokens.css` — accent-* values; light `--panel-shadow-glow`; light `--nav-fg-active` retuned from hardcoded cyan
- `tests/browser/design_tokens.py` — `accent` retuned; `accent_api` newly added
- `tests/test_design_tokens_a11y.py` — three new tuples in `test_text_on_color` parametrize block; stale "Text on accent (cyan)" comment refreshed

**Out of scope (Leg 03)**: prose in `the_one/agents.md` "Design system" section currently pins old hex values (`#0e7490`, `#22d3ee`, "cyan-700", etc.) in lines ~637 and ~684-685. Leg 03's CSS-class-rename + design-system-documentation sweep should also refresh this prose — but it is NOT this leg's job; leg 03 is already chartered for it. Document explicitly in Leg 03's design so it doesn't get missed.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified
- [ ] WCAG audit green; token-definitions green; `make verify-serving` exit 0
- [ ] Final hex values + any iteration history recorded in `flight-log.md` under `## Leg Progress`
- [ ] Set leg status to `landed` in this file's header
- [ ] Signal `[HANDOFF:review-needed]` — orchestrator commits at flight-end; do NOT commit or signal `[COMPLETE:leg]`

---

## Citation Audit

10 citations verified against current code at leg design time:

| Citation | Verified |
|---|---|
| `tokens.css:46-52 — [data-theme="dark"] accent-* block` | OK (line 47 `--accent: #22d3ee` snippet matches) |
| `tokens.css:142-147 — [data-theme="light"] accent-* block` | OK (line 142 `--accent: #0e7490` snippet matches) |
| `tokens.css:189 — light --panel-shadow-glow` | OK (snippet `rgba(14, 116, 144, 0.18)` matches) |
| `tests/browser/design_tokens.py:30-46 — DARK dict` | OK |
| `tests/browser/design_tokens.py:53-71 — LIGHT dict` | OK |
| `tests/test_design_tokens_a11y.py:115-137 — test_large_or_ui_passes_aa parametrize` | OK (`accent on bg/surface` pairs present) |
| `tests/test_design_tokens_a11y.py:152-176 — test_text_on_color parametrize` | OK (`fg_on_accent on accent` pairs at lines 156-157) |
| `the_one/interfaces/web/static/css/chat.css:94 — ".area-chat .msg.user.api { background: var(--accent-api); ..."` | OK |
| `tokens.css` historical comments at ~lines 3, 115, 138-141 (NEXUS-style cyan / cyan-700 framing) | OK — intentionally NOT touched in this leg; Leg 03 owns that sweep |
| `flight.md` design decision: token-value-change-not-rename, accent-api complementary-hue | OK (matches mission/flight spec) |
| `tokens.css:208 — light-theme --nav-fg-active hardcoded cyan #22d3ee` | OK (Developer found this; added to leg scope round 1) |
| `agents.md:~637, ~684-685 — prose pinning old hex values` | OK (deferred to Leg 03 design-system-documentation sweep with explicit note) |

Design-review revisions applied (Developer review, round 1):
- High: added `--nav-fg-active` retune to leg scope (was missed; would have left nav rail cyan post-retune). Acceptance criterion, implementation guidance step 2, and Files Affected all updated.
- Medium: leg now explicitly defers `agents.md` design-system prose cleanup to Leg 03 with an Out-of-Scope note in Files Affected, so it doesn't get missed.
- Low: corrected starter-palette contrast-ratio claims to match Developer's computed values (9.50/7.10/6.86/etc., not the original rounded estimates). Added the defensive `accent_api on bg` 3:1 pair per Developer suggestion. Updated stale "Text on accent (cyan)" inline comment in the test parametrize.
