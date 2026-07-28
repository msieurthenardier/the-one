# Leg: 05-icon-system

**Status**: completed
**Flight**: [Design Language & Theme Architecture](../flight.md)

## Objective

Replace emoji and character-based icons (`💬`, `🤖`, `⚙️`, `×`, `+`, `●●●`) with curated Lucide SVG icons inlined as a single JS module (`static/js/icons.js`). Add `App.icon(name)` helper. Icons inherit color via `currentColor` (works in both themes). Update the nav rail rendering in `app.js` to support SVG icon strings.

## Context

- This leg replaces visible emoji icons across the three areas (Chat / Studio / Admin) and any inline character icons used as affordances (`+`, `×`, `●●●`) with Lucide SVG icons.
- **Lucide** is an open-source SVG icon library (MIT, ~1500 icons, geometric line style by Vercel/community). Pairs aesthetically with Geist (both Vercel ecosystem). We bundle a curated subset of ~20 icons inline in a JS module — single HTTP request, no per-icon fetch latency.
- **`currentColor` integration**: SVG `stroke="currentColor"` (or `fill="currentColor"`) inherits the rule's text color. So an icon inside a cyan `<a>` tag shows cyan; inside a danger-red button it shows red. No per-icon color tokens needed.
- **`app.js:21` is `el.textContent = a.icon`**: this renders the icon string as TEXT. For SVG we need `innerHTML`. Change to `innerHTML` (one-line edit) — safe because area registrations are controlled by project code, no user input.
- **Out of scope for this leg**: the dropdown arrow `data:image/svg+xml,...` background-image at studio.css. That stays as exception (replaceable in F3 with a `::after` pseudo-element + Lucide chevron-down).
- **Leg 04 outcome**: Geist Sans + Mono active; typography scale tokens; minimal FOUC.
- **Tests**: F1 testids stable; flow tests assert on text content of buttons (e.g., "+ Add Provider", "Delete Agent") — verify which assertions might match icons + text vs text alone.

## Inputs

- Branch `flight/02-design-language-and-theme-architecture`, legs 01-04 landed (uncommitted)
- `the_one/interfaces/web/static/js/app.js` — has `el.textContent = a.icon` at line 21 (renders area icons in nav rail)
- `the_one/interfaces/web/static/js/areas/{chat,studio,admin}.js` — register areas with emoji icons:
  - chat.js line 4: `icon: '💬'` (💬)
  - studio.js line 4: `icon: '🤖'` (🤖)
  - admin.js line 4: `icon: '⚙️'` (⚙️)
- Character icons in JS code: `×` (close/delete buttons in chat/studio sidebars; chip-remove), `+` (new chat / new agent / add provider buttons), `●●●` (eye-toggle button text on password fields)
- Test baseline: 350 passed, 16 deselected; 8 browser tests passing

## Outputs

- `the_one/interfaces/web/static/js/icons.js` (new) — JS module exporting an `Icons` object with ~20 curated Lucide SVG strings; attaches as `window.App.icons` (mutate-in-place pattern from leg 01)
- `the_one/interfaces/web/static/js/app.js` — modified: (1) `el.textContent = a.icon` → `el.innerHTML = a.icon` (line 21); (2) add `App.icon(name)` helper to the App namespace via Object.assign
- `the_one/interfaces/web/static/index.html` — `<script src="/static/js/icons.js"></script>` added BEFORE the area scripts (icons.js needs to load before chat/studio/admin reference `App.icons`)
- `the_one/interfaces/web/static/js/areas/chat.js` — area icon changes from emoji to `App.icons.chat` (or equivalent SVG string lookup); `✕` (×) chip-remove / session-delete replaced with `App.icon('x')`; `+` in `+ new` button → kept text label; the standalone `+` standalone in studio replaced with icon
- `the_one/interfaces/web/static/js/areas/studio.js` — area icon → `App.icons.studio`; `+` button text → SVG icon; `✕` (×) → `App.icon('x')`
- `the_one/interfaces/web/static/js/areas/admin.js` — area icon → `App.icons.admin`; `+ Add Provider` → `<icon> Add Provider`; `●●●` (admin-pf-eye) → eye/eye-off toggle
- `the_one/interfaces/web/static/css/{chat,studio,admin,base}.css` — minor: `.nav-item` font-size may need adjustment if SVG icons render differently than emoji; ensure SVG sizing via `.nav-item svg { width: 18px; height: 18px }` or similar

## Acceptance Criteria

### Icons module
- [ ] `the_one/interfaces/web/static/js/icons.js` exists and attaches `App.icons` (mutate `window.App` via Object.assign — same pattern as leg 01's app.js refactor)
- [ ] `App.icons` is an object mapping icon name → SVG string. Curated set (~20 icons): `chat`, `studio`, `admin`, `plus`, `x`, `edit`, `trash`, `check`, `alert-triangle`, `alert-circle`, `info`, `eye`, `eye-off`, `refresh`, `send`, `download`, `chevron-down`, `chevron-right`, `zap`, `sparkles` (or substitutes from Lucide's catalog)
- [ ] All SVG strings use `stroke="currentColor"` (line icons) or `fill="currentColor"` so icons inherit text color via CSS
- [ ] All SVGs include `width` and `height` attributes set to a default size (e.g., `width="18" height="18"`) and have `viewBox="0 0 24 24"` (Lucide standard)
- [ ] `App.icon(name)` helper function exists on `App` namespace; returns the SVG string for the named icon, or empty string if missing (with `console.warn` for missing names)

### app.js update
- [ ] `app.js:21` changes from `el.textContent = a.icon` to `el.innerHTML = a.icon` to support SVG icon strings
- [ ] `App.icon` helper added to the App namespace via the Object.assign pattern (matches leg 01's mutation style)

### HTML wiring
- [ ] `index.html` has `<script src="/static/js/icons.js"></script>` placed AFTER `<script src="/static/js/app.js">` and BEFORE the three area scripts (so icons.js can mutate window.App after app.js initializes it, before areas reference it)

### Area icons
- [ ] `chat.js` line 4: `icon: '💬'` → `icon: App.icons.chat` (or computed lazily via getter — actual mechanism may need adapting; see Implementation Guidance)
- [ ] `studio.js` line 4: emoji → `App.icons.studio` (Lucide `bot` or `sparkles`)
- [ ] `admin.js` line 4: emoji → `App.icons.admin` (Lucide `settings`)

### Character icon replacements
- [ ] All `✕` (×) close/delete characters in JS replaced with `App.icon('x')`. Specific sites: `chat.js` session-list `.delete` and `chip-remove` (if any); `studio.js` `.agent-item-delete`; `admin.js` (none currently — uses the visible emoji rendered through CSS, no inline)
- [ ] `+` in standalone-button context replaced with `App.icon('plus')` where appropriate. Specifically: `studio.js` `.new-agent-btn` (currently just `+` text). NOT replaced where it's part of a label like `+ Add Provider` (keep `+` as visible part of the label OR use icon + text — pick consistent approach across all three)
- [ ] `●●●` (`●●●` — bullets used by `.admin-pf-eye` to denote password) replaced with `App.icon('eye')` and `App.icon('eye-off')` for the toggle states

### CSS sizing
- [ ] `.nav-item svg` rule added (in base.css `@layer base`) sizing icons appropriately — e.g., `width: 20px; height: 20px;` to match the prior emoji size visually
- [ ] Icons inside small-button contexts (`.delete`, `.agent-item-delete`, `.chip-remove`, `.new-agent-btn`, `.admin-pf-eye`) sized appropriately — e.g., `width: 14px; height: 14px;` for inline action icons

### Behavioral
- [ ] All F1 browser tests still pass (8/8). Specifically verify: `test_studio_agent_crud_flow` may assert on button text containing "+" or specific labels — re-verify those assertions still match. Most flow tests use `data-testid` selectors so icon-only changes don't break them.
- [ ] Default `pytest tests/` shows 350 passed, 16 deselected
- [ ] Hex/rgba grep still clean (no regression)
- [ ] No `console.error` / `console.warn` unless intentional (`App.icon('missing')` would warn — but no real call should hit this)

### Visual
- [ ] Manual visual check: nav rail shows 3 SVG icons (chat speech bubble, studio bot, admin gear) instead of emoji. Icons inherit color via currentColor (cyan in active state, fg-secondary in inactive). All replaced character icons (`×`, `+`, eye toggle) render as Lucide SVGs.

## Verification Steps

1. **Tests pass**:
   ```bash
   pytest tests/ --tb=short -q --timeout=60
   pytest -m browser tests/browser/ -v --timeout=60
   ```
2. **Hex/rgba grep clean**:
   ```bash
   grep -nE "#[0-9a-fA-F]{3,8}\b|rgba?\(" the_one/interfaces/web/static/css/*.css \
     | grep -v tokens.css | grep -v fonts.css | grep -v "data:image/svg"
   ```
   Expected: empty.
3. **Manual visual check**:
   ```bash
   docker compose up -d --build
   ```
   Open http://localhost:8484:
   - Nav rail (left): SVG icons for Chat, Studio, Admin
   - Active state: icon inherits cyan accent color
   - Studio sidebar: `+` button now shows plus icon instead of "+" text
   - Provider edit form: password field has eye icon (toggles to eye-off when revealing)
   - Session/agent delete `×` is now an x SVG icon
   - DevTools console: no errors

## Implementation Guidance

### 1. Curate Lucide SVG icons

Visit `https://lucide.dev/icons` for the catalog. For each icon needed, click and copy the SVG markup. Or use `gh api repos/lucide-icons/lucide/contents/icons` to find raw SVG paths.

Lucide SVGs follow a consistent format:

```xml
<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <!-- paths -->
</svg>
```

`stroke="currentColor"` is the key — icons inherit color from CSS. Keep `width="24" height="24"` in the source SVG; size adjustments via CSS (`.nav-item svg { width: 20px; height: 20px }`).

For each icon, you can either (a) copy the SVG from lucide.dev, or (b) use the `gh` CLI to fetch from the repo:

```bash
gh api repos/lucide-icons/lucide/contents/icons/message-circle.svg --jq '.content' | base64 -d
```

### 2. Create `the_one/interfaces/web/static/js/icons.js`

```javascript
/* Lucide icons — curated subset bundled inline.
 *
 * Source: https://lucide.dev (MIT). Icons inherit color via stroke="currentColor".
 * Sizing via CSS: .nav-item svg { width: 20px; height: 20px }, etc.
 *
 * Pinned to lucide@<RELEASE_TAG> at time of leg.
 */

(function () {
  'use strict';

  var Icons = {
    // Area nav icons
    chat: '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>',
    studio: '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 8V4H8"/><rect width="16" height="12" x="4" y="8" rx="2"/><path d="M2 14h2"/><path d="M20 14h2"/><path d="M15 13v2"/><path d="M9 13v2"/></svg>',
    admin: '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/><circle cx="12" cy="12" r="3"/></svg>',

    // Action affordances
    plus: '<svg ...>...</svg>',
    x: '<svg ...>...</svg>',
    edit: '<svg ...>...</svg>',
    trash: '<svg ...>...</svg>',
    check: '<svg ...>...</svg>',
    'alert-triangle': '<svg ...>...</svg>',
    'alert-circle': '<svg ...>...</svg>',
    info: '<svg ...>...</svg>',
    eye: '<svg ...>...</svg>',
    'eye-off': '<svg ...>...</svg>',
    refresh: '<svg ...>...</svg>',  // Lucide refresh-cw or rotate-cw
    send: '<svg ...>...</svg>',     // Lucide send (paper airplane)
    download: '<svg ...>...</svg>',
    'chevron-down': '<svg ...>...</svg>',
    'chevron-right': '<svg ...>...</svg>',
    zap: '<svg ...>...</svg>',
    sparkles: '<svg ...>...</svg>',
  };

  window.App = window.App || {};
  Object.assign(window.App, {
    icons: Icons,
    icon: function (name) {
      var svg = Icons[name];
      if (!svg) {
        console.warn('App.icon: unknown icon name "' + name + '"');
        return '';
      }
      return svg;
    },
  });
})();
```

Replace each `<svg ...>...</svg>` placeholder with the actual SVG markup copied from lucide.dev or fetched via `gh api`. Keep the inline single-line format for brevity OR break each across multiple lines for readability — both work.

### 3. Update `the_one/interfaces/web/static/js/app.js`

Change line 21 from:

```javascript
el.textContent = a.icon;
```

to:

```javascript
el.innerHTML = a.icon;
```

This allows SVG strings to render as actual SVG elements. Existing emoji icons would also still work (innerHTML interprets HTML entities; emoji are unicode-safe).

### 4. Update `the_one/interfaces/web/static/index.html`

Add the icons.js script tag AFTER app.js but BEFORE the area scripts. Example:

```html
<script src="/static/js/app.js"></script>
<script src="/static/js/icons.js"></script>     <!-- NEW -->
<script src="/static/js/areas/chat.js"></script>
<script src="/static/js/areas/studio.js"></script>
<script src="/static/js/areas/admin.js"></script>
```

(Reasoning: app.js exposes `window.App`; icons.js mutates it via `Object.assign`; areas reference `App.icons` and `App.icon` after both load.)

### 5. Update area icons

In `chat.js` (line 4):
```javascript
App.registerArea({
  id: 'chat',
  label: 'Chat',
  icon: App.icons.chat,  // was '💬'
  order: 10,
  // ...
});
```

Same pattern for studio.js (`App.icons.studio`) and admin.js (`App.icons.admin`).

### 6. Replace character icons in JS

Find each `✕` (×) and `+` and `●●●` in the area JS files. Replace with appropriate `App.icon(name)` string concatenation. Examples:

**chat.js** session-list delete `×`:
```javascript
delBtn.textContent = '✕';
// becomes:
delBtn.innerHTML = App.icon('x');
```

**studio.js** new-agent-btn `+`:
```javascript
sidebar.innerHTML = '... <button class="new-agent-btn">+</button> ...';
// becomes:
sidebar.innerHTML = '... <button class="new-agent-btn">' + App.icon('plus') + '</button> ...';
```

**admin.js** password eye toggle `●●●`:
```javascript
'<button class="admin-pf-eye" type="button" ...>●●●</button>'
// becomes:
'<button class="admin-pf-eye" type="button" ...>' + App.icon('eye') + '</button>'
// And the JS toggle handler swaps between 'eye' and 'eye-off':
eyeBtn.innerHTML = passwordInput.type === 'password' ? App.icon('eye') : App.icon('eye-off');
```

### 7. CSS sizing

Add to `base.css` (in `@layer base`):

```css
.nav-item svg {
  width: 20px;
  height: 20px;
  display: block;
}
```

Add to other component files as needed:

```css
/* chat.css */
.area-chat .session-item .delete svg { width: 12px; height: 12px; }

/* studio.css */
.area-studio .new-agent-btn svg { width: 14px; height: 14px; display: block; }
.area-studio .agent-item-delete svg { width: 10px; height: 10px; display: block; }

/* admin.css */
.area-admin .admin-provider-add-btn svg { width: 12px; height: 12px; vertical-align: middle; margin-right: 4px; }
.area-admin .admin-pf-eye svg { width: 14px; height: 14px; display: block; }
```

### 8. Run verification

```bash
pytest tests/ --tb=short -q --timeout=60
pytest -m browser tests/browser/ -v --timeout=60
docker compose up -d --build
# Manual check at http://localhost:8484
```

## Edge Cases

- **F1 browser tests use `data-testid` selectors, not text content of buttons**, so icon-only renders don't break them. Specifically: leg 06 `test_studio_agent_crud_flow` uses `[data-testid="new-agent-btn"]`, not `text="+"`. Same for delete buttons. Verified during F1 review.

- **Some flow tests assert text content of LABELS that include `+` (e.g., "+ Add Provider")**. If we move `+` to an icon, the assertion `to_contain_text("+ Add Provider")` would fail; `to_contain_text("Add Provider")` would still pass. Recommend keeping the visual `+` as text in labels (let the icon replace ONLY the standalone `+` button in studio sidebar).

- **`innerHTML` vs `textContent`**: changing app.js line 21 from `textContent` to `innerHTML` is XSS-relevant if untrusted strings are ever passed as `a.icon`. In our codebase, `a.icon` comes from area registrations (`chat.js`, `studio.js`, `admin.js`) — controlled project code. No user input. Safe.

- **Icon size visual parity with emoji**: emoji at 18px font-size renders ~16-18px tall depending on font. SVG at 20px×20px is slightly larger but reads consistently. Pick the size that looks balanced in the nav rail; 20px is a starting point — the implementer can tune to 18px if it looks too big.

- **Color inheritance via `currentColor`**: SVG `stroke="currentColor"` inherits CSS `color`. In `.nav-item.active` the color is `var(--accent)` — icon shows cyan. In inactive state the color comes from inherited body/parent — icon shows the default fg color. Verified pattern used by Lucide intentionally.

- **Lucide license**: MIT. Bundle inline; no attribution required (MIT recommends but doesn't require). Optionally add a comment in icons.js: `// Icons from Lucide (https://lucide.dev) — MIT License`.

- **Studio.css dropdown arrow data URL**: `studio.css:154` (or wherever after the leg-02 split) has the `data:image/svg+xml,...%23888...` background. NOT replaced in this leg. Stays as documented exception. F3 form-primitive extraction can revisit.

- **`+ Add Provider` button**: keep `+` in the visible label text. The icon system provides the `plus` icon for places where the `+` is standalone (i.e., `studio.js .new-agent-btn`). Don't double up.

## State-Machine Reachability Audit

This leg introduces no new states. Pure additive: new JS module, app.js mutation, area icon string changes. No DB schema. F1 testids unaffected.

✓ Pass.

## Cache Freshness Contract

- **Icon SVG strings**: in-memory at `App.icons`. Computed once at module load, never mutated.
- **No new caches.**

✓ Pass.

## Files Affected

- `the_one/interfaces/web/static/js/icons.js` — new (~80 lines, ~20 inline SVGs)
- `the_one/interfaces/web/static/js/app.js` — modified (1 line: `textContent` → `innerHTML`; helper added via Object.assign)
- `the_one/interfaces/web/static/index.html` — 1 line added (`<script src="/static/js/icons.js">`)
- `the_one/interfaces/web/static/js/areas/chat.js` — area icon + character-icon replacements (~3-5 lines changed)
- `the_one/interfaces/web/static/js/areas/studio.js` — area icon + character-icon replacements (~5 lines changed)
- `the_one/interfaces/web/static/js/areas/admin.js` — area icon + eye toggle (~5 lines changed)
- `the_one/interfaces/web/static/css/base.css` — `.nav-item svg` sizing rule
- `the_one/interfaces/web/static/css/{chat,studio,admin}.css` — small SVG sizing rules per file

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing: `pytest tests/` shows 350/16 deselected; `pytest -m browser tests/browser/` shows 8 passed
- [ ] Hex/rgba grep returns zero matches
- [ ] Manual visual check: nav rail shows SVG icons; active state icon inherits cyan; standalone `+` and `×` and `●●●` characters all replaced with SVGs; no console errors
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `landed`
- [ ] Do NOT commit
- [ ] Signal `[HANDOFF:review-needed]`
