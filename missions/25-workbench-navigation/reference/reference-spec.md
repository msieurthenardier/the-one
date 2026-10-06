# Mission 25 reference spec: Workbench and Deep-violet controls

This spec is derived from the approved boards in `boards/` (see `README.md` for provenance).
It is the single reference that Flights 1–4 and 6 build and verify against for SC8: each
redesigned surface must match the approved boards in both themes, checked with screenshots
and computed-style probes.

## 0. Conventions used in this spec

**Citations.** Each value names its source:

| Tag | Meaning |
|---|---|
| `B3:L41` | Line 41 of `boards/B3-workbench-clickable.dc.html` (the markup or the script) |
| `B3:RAIL`, `B3:ROW`, `B3:ROWDPR` | Style-string constants in B3's script (`L314`, `L315`, `L316`) |
| `Btn:L34` | Line 34 of `boards/Buttons.dc.html` (the `.deep` rules are L30–L39; theme variables L58–L59) |
| `bundle:L412` | Line 412 of `boards/ds/gleepglorp/components/bundle.css` (the app's real component classes) |
| `B1:` / `B2:` | Superseded boards, cited only where B3 is silent |

**Token values.** Every token is given for both themes from `ds/gleepglorp/tokens.css` as
`dark / light`, for example `--surface` = `#17181c / #fafafa`. Theme-agnostic tokens get a
single value.

**Source values versus derived values.** The px values in sections 1–11 are as written in
the source. Appendix A lists **derived** rendered boxes, measured by rendering B3's markup in
Chromium at 1440×900 with the app's Geist fonts. Use them as computed-style probe
expectations, with ±1px tolerance unless noted.

**Two rendering facts every crew must know before comparing pixels:**

1. **B3 renders its buttons and toggles in the *current* (pre-mission) treatment.** It links
   the design-system `bundle.css`, which predates the Deep-violet decision: pale `--accent`
   fill, dark ink in dark theme, 12px semibold labels. The approved button treatment comes
   from the Buttons board (§11). Wherever B3 shows a `btn-*` class, take its **placement,
   variant and size** from B3 and its **appearance** from §11.
2. **Box model.** The board has no `box-sizing` reset, so `<div>`, `<section>`, `<nav>`,
   `<aside>` and `<header>` are content-box. The app sets `* { box-sizing: border-box }`
   (`static/css/base.css:3`). Buttons are border-box in both. Fixed sizes that carry padding
   or a border therefore render differently (§1.3).

**Line height.** Nothing on B3 sets `line-height` except bundle classes. The app's `body`
does not set one either, so `normal` applies in both. Geist at `normal` renders roughly
11px→14, 12px→16, 13px→17, 14px→18, 16px→21 and 18px→23 px line boxes.

---

## 1. Global frame

### 1.1 Frame

| Property | Value | Source |
|---|---|---|
| Viewport the board assumes | 1440 × 900, fixed (`$preview` width 1440, height 900) | `B3:L310` |
| Root | `position: relative; width: 1440px; height: 900px; overflow: hidden; display: flex` | `B3:L18` |
| Root ground and ink | `background: var(--bg)` (`#101114 / #ffffff`), `color: var(--fg)` (`#ededf0 / #18181b`) | `B3:L18` |
| Root type | `font-family: var(--font-family-sans)` (Geist, …), `font-size: var(--font-size-body)` (13px) | `B3:L18` |
| Page | `body { margin: 0 }`, `a { color: inherit }`, `a:hover { color: inherit }` | `B3:L14–L15` |

### 1.2 Columns (left to right)

| Column | Element | Width as written | Present on |
|---|---|---|---|
| Rail | `<nav aria-label="Main">` | 72px | always (`B3:L19`) |
| List column | `<section aria-label="Agents\|Chats\|Library">` | 300px | Agents, Chats, Library (`B3:L28`, `L97`, `L184`) |
| Settings nav (takes the list column's place) | `<nav aria-label="Settings">` | 240px | Settings (`B3:L231`) |
| Detail pane | `<main>`, `flex-grow: 1; min-width: 0` | remainder | always (`B3:L55`, `L120`, `L200`, `L235`) |
| Agent drawer | `<aside aria-label="This chat's agent">` | 320px | Chats only, when open (`B3:L166`) |
| Picker and palette overlays | `position: absolute; inset: 0` over the **whole frame**, rail included | — | `B3:L254`, `L289` |

### 1.3 Box-model reconciliation (board render versus app)

| Box | As written | Board renders (outer) | Same CSS in the app (border-box) |
|---|---|---|---|
| Rail | `width: 72px` + 1px border-right | **73px** | 72px |
| List column | `width: 300px` + 1px border-right | **301px** | 300px |
| Settings nav | `width: 240px; padding: 14px 10px` + 1px border-right | **261px** | 240px |
| Drawer | `width: 320px` + 1px border-left | **321px** | 320px |
| Chat header | `height: var(--topbar-h)` (48px) + 1px border-bottom | **49px** | 48px |

The 1px differences fall within tolerance. **The Settings nav differs by 21px and needs a
decision.** The operator approved the 261px render, while `240px` (which equals
`--sidebar-w`) is what the source says. Pick one in Flight 3 and record it. The 261px outer
width matches the approved pixels.

### 1.4 Theme switching on the board

- `data-theme="{{theme}}"` sits on the frame root (`B3:L18`). The component prop `theme` is
  an enum of `dark` and `light`, defaulting to `dark` (`B3:L310`, `L376`).
- The board has **no in-frame theme control**. Reviewers flipped the prop. Every visual
  difference between themes comes from tokens; the markup is identical.
- The board shows neither the mission's minimum widths (designed for 1280, usable at 1024)
  nor any responsive behaviour. At 1280 with the drawer open, the chat pane would be
  1280 − 73 − 301 − 321 = 585px.

---

## 2. Rail

| Property | Value | Source |
|---|---|---|
| Element | `<nav aria-label="Main">` | `B3:L19` |
| Size | `width: 72px`, full height, `flex-shrink: 0` | `B3:L19` |
| Layout | `display: flex; flex-direction: column; align-items: center; gap: 6px; padding: 12px 0` | `B3:L19` |
| Ground | `background: var(--surface)` (`#17181c / #fafafa`); `border-right: 1px solid var(--border)` (`#26272c / #e4e4e7`) | `B3:L19` |
| Brand mark | `<img alt="GleepGlorp AI">`, `width: 28px; height: 28px; image-rendering: pixelated; margin-bottom: 12px`, first item, horizontally centred (renders at x 22, y 12) | `B3:L20` |
| Destination order | Chats, Agents, Library, Settings (top to bottom, directly under the brand mark) | `B3:L21–L24` |
| Destination element | `<button aria-label="{Name}">` containing an 18×18 icon and `<span>{Name}</span>` | `B3:L21–L24` |
| Destination box | `display: flex; flex-direction: column; align-items: center; gap: 4px; width: 60px; padding: 8px 0; border-radius: var(--radius-sm)` (6px); `border: 1px solid transparent`; `font: inherit; font-size: var(--font-size-tiny)` (10px, weight 400); `cursor: pointer` | `B3:RAIL` |
| Destination size | renders **60 × 53**, pitch 59px (53 + 6 gap). Tops at y = 58, 117, 176, 235 | derived |
| Icon | 18×18, `stroke-width 2`, `currentColor` (icons in App. B) | `B3:L21–L24` |
| Label | 10px (`--font-size-tiny`), weight 400, below the icon with a 4px gap | `B3:RAIL` |
| **Active** | `color: var(--fg)` (`#ededf0 / #18181b`); `background: var(--accent-translucent)` (`rgba(167,139,250,0.10) / rgba(109,40,217,0.08)`); `border-color: var(--accent)` (`#a78bfa / #6d28d9`) | `B3:L330` |
| Inactive | `color: var(--fg-secondary)` (`#a1a3ad / #52525b`); `background: transparent` | `B3:L330` |
| Hover | **not defined on the board** | — |
| Focus | **not defined on the board**. Use the app's pinned focus form: `outline: 2px solid var(--accent); outline-offset: 2px` (`bundle:L439` and siblings) | — |
| Current-page semantics | **missing on B3**: the active button has no `aria-current`. B1 and B2 used `<a … aria-current="page">` (`B1:` rail, `B2:` rail). SC10 needs it, so add `aria-current="page"` (or the equivalent) to the active destination | — |
| Badges | none | — |
| Jump-to control | `<button class="btn-ghost" aria-label="Jump to (Ctrl K)">`, `margin-top: auto` (pinned to the bottom of the rail), `width: 44px; height: 44px; padding: 0`, search icon. Renders at x 14, y 844 (12px above the bottom edge). The icon is 18 in its SVG attributes but **renders 16×16** because `.btn-ghost svg { width:16px; height:16px }` overrides them (`bundle:L540–L543`). No visible label and no kbd hint | `B3:L25` |

Superseded variants that do **not** apply: B1/B2 rail items are `<a>` 56px wide with an inset
`box-shadow` active ring, and the jump control is a 40px `btn-ghost` labelled "Search".

---

## 3. List column: shared anatomy

| Part | Value | Source |
|---|---|---|
| Container | `width: 300px; flex-shrink: 0; display: flex; flex-direction: column; border-right: 1px solid var(--border); background: var(--bg); min-height: 0` | `B3:L28`, `L97`, `L184` |
| Title row | `display: flex; align-items: center; gap: 8px; padding: 14px 16px 10px` | `B3:L29`, `L98`, `L185` |
| Title | `<h2>`, `margin: 0; font-size: var(--font-size-h2)` (16px); `font-weight: 600`; colour `--fg` | same |
| Title-row action | `.btn-outlined-primary.btn-sm`, `margin-left: auto`, plus icon, label "New" (Agents) or "Add" (Library). Chats has no title-row action | `B3:L30`, `L186` |
| Title-row height | 48px when it has a `btn-sm` (14 + 24 + 10); 45px without one (Chats) | derived |
| Scroller | `flex-grow: 1; min-height: 0; overflow-y: auto; padding: 0 8px 12px` | `B3:L38`, `L102`, `L188` |
| Group label | `font-size: var(--font-size-caption)` (11px); `font-weight: 500`; `color: var(--fg-muted)` (`#85878f / #6e6e77`); `padding: 12px 10px 4px`. Renders 30px tall | `B3:L103`, `L189`, `L233`, `L268` |
| Row base | `<button>` at `width: 100%`, `border-radius: var(--radius-sm)` (6px), `border: 1px solid transparent`, `background: transparent`, `font: inherit`, `cursor: pointer` | `B3:ROW`, `ROWDPR`, `L190` |
| **Selected row** | `background: var(--accent-translucent)` + `border-color: var(--accent)` (the 1px transparent rest border means selecting causes no layout shift) | `B3:L338`, `L373`, `L190` |
| Hover row | **not defined** | — |
| Scroll | Only the scroller scrolls. The title row (and the filter, on Agents) stay fixed above it. The board does **not** scroll the selected row into view: on load the selected agent, "Research assistant", is 22nd of 28 and sits below the fold | `B3:L38`, derived |

Per-destination differences in row geometry (see §15 for the inconsistency):

| List | Row padding | Inter-row gap | Text lines | Rendered row height |
|---|---|---|---|---|
| Agents | `7px 10px` (`B3:ROW`) | 0 (scroller is not flex) | 2 | 48px |
| Chats | `8px 10px` (`B3:ROWDPR`, `L105–L117`) | 2px (`B3:L102`) | 2 | 51px |
| Library | `8px 10px` (`B3:L190–L197`) | 2px (`B3:L188`) | 2 | 50px |
| Settings nav item | `6px 10px` (`B3:L233`) | 2px (`B3:L231`) | 1 (12px) | 28px |

---

## 4. Detail pane: shared anatomy

| Part | Value | Source |
|---|---|---|
| Container | `<main>`, `flex-grow: 1; min-width: 0; display: flex; flex-direction: column; min-height: 0`. Settings: `overflow: hidden` | `B3:L55`, `L120`, `L200`, `L235` |
| **Item header** (Agents, Library) | `<header class="editor-header">` plus inline `border-bottom: 1px solid var(--border); padding: 12px 24px; align-items: center`. From the bundle: `display: flex; justify-content: space-between; gap: 16px; flex-shrink: 0` (`bundle:L867`) | `B3:L56`, `L201` |
| Breadcrumb | the first child of `.editor-header-text` (flex column, gap 2px, `bundle:L875`): a `<div>` at `font-size: var(--font-size-caption)` (11px), `color: var(--fg-muted)`. Separator: ` / ` | `B3:L58`, `L202` |
| Title | `<h1 class="editor-title">`: 16px (`--font-size-h2`), **weight 700** (`--font-weight-bold`), `--fg`, single line with ellipsis (`bundle:L882`) | `B3:L59`, `L202` |
| Actions | `<div class="form-actions">`: flex, `gap: 8px`, right-aligned (`bundle:L900`) | `B3:L61`, `L203` |
| Header height | renders 62px including the hairline; buttons vertically centred | derived |
| **Page header** (Settings) | `<div class="page-header" style="padding: 16px 32px">`: flex, align centre, gap 12px (`bundle:L735`). Title is `<h1 class="page-title">` at 16px, weight 600, `--fg`. The action is `.btn-outlined-primary`, pushed right by `.page-header > .btn-outlined-primary { margin-left: auto }` (`bundle:L757`). **No border-bottom, no breadcrumb.** Renders 64px | `B3:L236` |
| Chat header | its own anatomy (§5.2) | `B3:L121` |
| **Unsaved-changes indicator** | **Not on B3.** The only board precedent is superseded B1: in `.form-actions`, before the buttons, `<span>` "Unsaved changes" at `font-size: var(--font-size-caption)` (11px), `color: var(--status-warning)` (`#fbbf24 / #8f5606`), followed by `btn-ghost` "Discard" and `btn-filled-primary` "Save" (`B1:` header). Treat it as guidance, not approved design | `B1` |

Content insets per destination:

| Destination | Body padding | Content max-width | Source |
|---|---|---|---|
| Agents (item) | `24px`, `gap: 32px` between content and the outline nav | 640px content column; 180px outline nav (outline is out of scope, §6.2) | `B3:L66–L67`, `L82` |
| Library (item) | `24px`; `display: grid; grid-template-columns: minmax(0, 1fr) 280px; gap: 32px` | left column 680px | `B3:L205–L206` |
| Settings (page) | header `16px 32px`; content `padding: 0 32px` | 880px | `B3:L236–L237` |
| Chats (thread) | `24px` | 720px, centred (`margin: 0 auto`) | `B3:L137–L138` |
| Chats (composer) | wrapper `12px 24px 20px` | 760px, centred | `B3:L153–L154` |
| Chats (new-chat welcome) | `24px`, centred both axes | 480px | `B3:L127–L128` |

On the board the item and page bodies are `overflow: hidden`, because they are static
(`B3:L66`, `L205`, `L235`). In the app the body must scroll under a fixed header; the board
does not say this explicitly.

---

## 5. Chats

### 5.1 List column

| Part | Value | Source |
|---|---|---|
| Title row | h2 "Chats" with no action button | `B3:L98` |
| **New chat** block | wrapper `padding: 0 16px 12px; display: flex; flex-direction: column; gap: 10px` | `B3:L99` |
| New chat button | `<button class="btn-filled-primary btn-lg" style="width: 100%">`: square-pen icon (16px) and label "New chat". Size from `.btn-lg`: `height: 36px; padding: 0 20px; font-size: var(--font-size-body)` (`bundle:L533`). Renders 268 × 36 at x 89, y 45. Appearance per §11 (Deep violet primary; the Buttons board's own New chat sample is `.b.p.wide`: 100% wide, 36px tall, `Btn:L20`) | `B3:L100` |
| Separator | the scroller has `border-top: 1px solid var(--border)`, which renders at y 93 | `B3:L102` |
| Agent filter or dropdown | **none** (mission decision 3) | — |
| Grouping | by recency: **Today**, **Yesterday**, **Last 7 days** (group-label style per §3). Older groups are not drawn | `B3:L103`, `L110`, `L114` |
| Row | `display: flex; flex-direction: column; gap: 2px; width: 100%; padding: 8px 10px; text-align: left` + row base | `B3:ROWDPR`, `L108` |
| Row line 1 | flex, `gap: 8px`: title at 13px (`--font-size-body`), `--fg`, single line with ellipsis; time at `margin-left: auto`, 11px, `--fg-muted`, `flex-shrink: 0` | `B3:L107–L117` |
| Row line 2 | the **agent name**, 11px, `color: var(--fg-secondary)` | same |
| Time format (sample data) | Today: 24-hour `HH:MM` (`10:42`, `09:15`, `08:03`). Yesterday and Last 7 days: short weekday (`Tue`, `Sun`, `Sat`, `Fri`). Pending new chat: `now` | `B3:L105–L117` |
| Selected row | selected style per §3. B3 marks selection with style only (no `aria-current`) | `B3:L373` |
| Pending new-chat row | appears at the **top of Today** when a chat has been started from the picker but not yet sent: title "New chat", time "now", line 2 = agent name, selected | `B3:L104–L106` |
| Cross-agent history | rows from different agents interleave by recency, and connector-driven chats appear too (for example "#help: install on Windows" / Discord concierge) | `B3:L107–L117` |

### 5.2 Detail pane: header

| Part | Value | Source |
|---|---|---|
| Element | `<header>`: `height: var(--topbar-h)` (48px); `flex-shrink: 0; display: flex; align-items: center; gap: 10px; padding: 0 16px 0 24px; border-bottom: 1px solid var(--border)` | `B3:L121` |
| Title | `<h1>`: `margin: 0; font-size: var(--font-size-body)` (13px); `font-weight: 600`. Shows the chat title, or "New chat" for a pending chat | `B3:L122`, `L372` |
| Agent line | `<span>` "with {agent name}": `font-size: var(--font-size-body-sm)` (12px), `--fg-muted` | `B3:L123` |
| Drawer toggle | `<button class="btn-ghost" aria-label="Show this chat's agent" aria-pressed="{open}">`, `margin-left: auto`, panel-right icon (16px), **icon only**. Renders 42 × 32 because the board did not square it (§11.4) | `B3:L124` |

### 5.3 Detail pane: thread state (existing conversation)

| Part | Value | Source |
|---|---|---|
| Thread area | `flex-grow: 1; min-height: 0; padding: 24px` (the board uses `overflow: hidden`; the app scrolls) | `B3:L137` |
| Column | `max-width: 720px; margin: 0 auto` | `B3:L138` |
| Messages | the existing `.messages` / `.msg.user\|tool\|assistant` classes, with gap overridden to **16px** (bundle default 12px, `bundle:L1288`) | `B3:L138–L148` |
| Telemetry | `.telemetry`, `justify-content: flex-end; padding: 0 24px`, sitting directly above the composer. Contents: `ctx:` bar `38%` `in:` `12,480` `out:` `1,106` (existing classes, `bundle:L1298–L1307`) | `B3:L151` |

### 5.4 Detail pane: new-chat state (after picking an agent)

| Part | Value | Source |
|---|---|---|
| Layout | flex centre on both axes, `padding: 24px`; inner `max-width: 480px`, flex column, `gap: 8px`, centred text | `B3:L127–L128` |
| Badge | `.badge.badge--{providerType}` whose **text is the model id** (for example `llama3.1:8b` on the ollama green) | `B3:L129` |
| Agent name | `<h2>`: `margin: 4px 0 0; font-size: var(--font-size-h1)` (18px); `font-weight: 600` | `B3:L130` |
| Description | `<p>`: `margin: 0; font-size: var(--font-size-body-lg)` (14px); `color: var(--fg-secondary)` | `B3:L131` |
| Change agent | `<button class="btn-ghost btn-sm" style="margin-top: 8px">` "Pick a different agent" (reopens the picker) | `B3:L132` |
| Telemetry | absent in this state | `B3:L136` |

### 5.5 Composer (both states)

| Part | Value | Source |
|---|---|---|
| Wrapper | `padding: 12px 24px 20px` | `B3:L153` |
| Box | `max-width: 760px; margin: 0 auto; display: flex; flex-direction: column; gap: 8px; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-md)` (8px); `padding: 10px 12px` | `B3:L154` |
| Label | visually hidden `<label for="cm">` "Message" (positioned off-screen at `left: -9999px`) | `B3:L155` |
| Textarea | `rows="2"`, placeholder "Message {agent name}…", `resize: none; border: 0; background: transparent; color: var(--fg); font-size: var(--font-size-body-lg)` (14px); **`outline: none`** (see §15: the focus indicator has to move to the box) | `B3:L156` |
| Toolbar | flex, align centre, `gap: 8px` | `B3:L157` |
| Attach | `<button class="btn-ghost btn-sm" aria-label="Attach a file">`, paperclip icon, icon only. Renders 34 × 24 with a 16px icon (the SVG says 14) | `B3:L158` |
| Model | `<span>` with the agent's model id: 11px, `--fg-muted`, `--font-family-mono` | `B3:L159` |
| Send | `<button class="btn-filled-primary" style="margin-left: auto">`, send icon and "Send" | `B3:L160` |

### 5.6 Agent picker modal

| Part | Value | Source |
|---|---|---|
| Overlay | `position: absolute; inset: 0; display: flex; justify-content: center; align-items: flex-start; padding-top: 72px` (centred on the whole frame, not the chat pane) | `B3:L254` |
| Scrim | full-cover `<button aria-label="Close">`, `border: 0; background: rgba(0, 0, 0, 0.3); cursor: default`. A literal, the **same in both themes**; there is no token | `B3:L255` |
| Dialog | `role="dialog" aria-modal="true" aria-labelledby="pt"`; `width: 640px; max-height: 720px; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg)` (12px); `box-shadow: var(--shadow-modal)` (`0 8px 30px rgba(0,0,0,0.18)`, both themes); `overflow: hidden; display: flex; flex-direction: column`. Renders 642 × 722 at x 399, y 72 with the default list | `B3:L256` |
| Header | flex, `gap: 8px; padding: 16px 20px 12px` | `B3:L257` |
| Title | `<h2 id="pt">` "Start a chat with…": 16px, weight 600 | `B3:L258` |
| Close | `<button class="btn-ghost btn-sm" style="margin-left: auto">` labelled **"Esc"** (its accessible name is "Esc") | `B3:L259` |
| Search wrapper | `position: relative; padding: 0 20px 12px` | `B3:L261` |
| Search field | `<input id="pk" class="field-input">`, visually hidden label "Find an agent", placeholder **"Find an agent by name, model or provider"**; inline `width: 100%; box-sizing: border-box; padding-left: 34px; height: 40px; font-size: var(--font-size-body-lg)` (14px). The rest comes from `.field-input`: `--surface` fill, 1px `--border`, 6px radius, `8px 12px` padding, focus outline 2px `--accent` offset 2px (`bundle:L174–L190`) | `B3:L262–L263` |
| Search icon | 16px, `--fg-muted`, `position: absolute; left: 32px; top: 12px` (vertically centred in the 40px field) | `B3:L264` |
| Shortcut hint in field | none | — |
| List | `flex-grow: 1; min-height: 0; overflow-y: auto; padding: 0 12px 12px; border-top: 1px solid var(--border)` | `B3:L266` |
| Groups (empty query) | **"Recently used"**: 5 agents in recency order. Then **"All agents"**: every agent, A–Z by name, *including* the five already shown | `B3:L364–L365` |
| Groups (query) | one group labelled **"{n} matching"** | `B3:L363` |
| Group label | §3 group-label style | `B3:L268` |
| Row | `<button>`: `display: flex; align-items: center; gap: 12px; width: 100%; padding: 10px 12px; border-radius: var(--radius-sm); border: 1px solid transparent; background: transparent; text-align: left`. Renders 55px tall | `B3:L270` |
| Row: provider dot | `.badge.badge--{providerType}` sized `8px × 8px; padding: 0; border-radius: 50%`, `aria-hidden` | `B3:L271` |
| Row: name | 13px, **weight 600**, `--fg` | `B3:L273` |
| Row: description | 11px, `--fg-secondary`, single line with ellipsis | `B3:L274` |
| Row: model | right-aligned, 11px, `--fg-muted`, mono, `flex-shrink: 0` | `B3:L276` |
| Row hover, active or keyboard-highlight | **not defined** (see §15) | — |
| Empty result | `.empty-state` (16px padding, `--fg-muted`, 13px, centred; `bundle:L562`): `No agents match "{query}".` | `B3:L281` |
| Footer | flex, `gap: 16px; padding: 10px 20px; border-top: 1px solid var(--border); font-size: 11px; color: var(--fg-muted)`. Left: "Picking an agent starts a new chat with it". Right (`margin-left: auto`): "Enter to start" | `B3:L284` |
| Excluded agents | (mission DD, not on the board) the synthetic default agent and deleted agents never appear in the picker | mission |

### 5.7 Agent drawer

| Part | Value | Source |
|---|---|---|
| Element | `<aside aria-label="This chat's agent">`: `width: 320px; flex-shrink: 0; display: flex; flex-direction: column; border-left: 1px solid var(--border); background: var(--surface)` | `B3:L166` |
| Layout | **pushes** the chat pane (a flex sibling, not an overlay) at 1440. **Open by default** (`inspector: true`, `B3:L321`). Only rendered on Chats | `B3:L165` |
| Header | flex, `gap: 8px; padding: 12px 16px; border-bottom: 1px solid var(--border)`. Renders **42px** tall, which does not line up with the chat header's 48px hairline (§15) | `B3:L167` |
| Header content | agent name (13px, weight 600) and `.badge.badge--{type}` whose text is the **provider type** (for example `anthropic-plan`) | `B3:L168–L169` |
| Body | `padding: 16px; display: flex; flex-direction: column; gap: 16px` | `B3:L171` |
| Description | `<p>`, 12px (`--font-size-body-sm`), `--fg-secondary` | `B3:L172` |
| Facts | `<dl>`: `display: grid; grid-template-columns: auto minmax(0, 1fr); gap: 8px 16px; font-size: 12px`. `<dt>` is `--fg-muted`; `<dd>` has `margin: 0`. Rows: **Model** (dd in mono), **Provider** (provider *display name*, for example "Claude Max"), **Chats** (count) | `B3:L173–L177` |
| "What it can use" | **Not on the board.** Mission decision 3 and SC3 require it. Superseded/rejected precedent: C1's inspector "Used in this chat" list (knowledge, built-in groups, MCP) | gap |
| Settings link | `<button class="btn-outlined-primary" style="align-self: flex-start">`, gear icon, "Open agent settings" | `B3:L178` |
| Close control inside the drawer | none (the header toggle is the only control) | — |
| Synthetic or deleted agent | (mission DD) no settings link | mission |

---

## 6. Agents

### 6.1 List column

| Part | Value | Source |
|---|---|---|
| Title row | h2 "Agents", then a count `<span>` (11px, `--fg-muted`) reading **"{shown} of {total}"** (for example "28 of 28", always in this form, filtered or not), then `.btn-outlined-primary.btn-sm` "New" (plus icon; SVG says 12, renders 16, §15) | `B3:L29–L30`, `L380` |
| Filter wrapper | `padding: 0 16px 8px; display: flex; flex-direction: column; gap: 8px`; inner `position: relative` | `B3:L31–L32` |
| Filter field | `<input id="aq" class="field-input">`, visually hidden label "Filter agents", placeholder **"Filter by name, model or provider"**; inline `width: 100%; box-sizing: border-box; padding-left: 32px`. Renders 268 × 35 | `B3:L33–L34` |
| Filter icon | search, **14px**, `--fg-muted`, `position: absolute; left: 10px; top: 9px` | `B3:L35` |
| Filter shortcut hint | **none on B3** (B1 showed a `/` key-cap; superseded) | — |
| Ordering | flat A–Z by name (`localeCompare`), with no grouping and no pinning (mission decision 2) | `B3:L341` |
| Row | `<button aria-current="true\|false">`: `display: flex; align-items: center; gap: 10px; width: 100%; padding: 7px 10px` + row base | `B3:ROW`, `L41` |
| Row: provider dot | `.badge.badge--{providerType}`, `8px × 8px; padding: 0; border-radius: 50%`, `aria-hidden`, coloured `--badge-{type}` | `B3:L42` |
| Row: text | flex column, `gap: 1px; min-width: 0; text-align: left`. Line 1 is the **name** (13px, `--fg`, ellipsis). Line 2 is the **model id** (11px, `--fg-muted`, mono, ellipsis) | `B3:L43–L45` |
| Selected | §3 selected style, plus `aria-current="true"` | `B3:L337–L338` |
| Empty | `.empty-state` `No agents match "{q}".` (count reads "0 of 28") | `B3:L50–L51` |
| Scale | 28 agents on the board; SC4 requires 30 or more | `B3:L312` |

### 6.2 Detail pane

| Part | Value | Source |
|---|---|---|
| Header | item header (§4). Breadcrumb **"Agents"**; title is the agent name | `B3:L56–L59` |
| Actions | `.btn-outlined-primary` with chat icon, **"Chat"** (starts a new chat with this agent); then `.btn-filled-primary` **"Save"** | `B3:L61–L64` |
| Delete | not in the header; B3 places "Delete agent" as the last outline link in `--status-danger`. Where Delete goes in the hosted tabbed editor is **not on the board** (§15) | `B3:L91` |
| Body | **Out of scope this mission** (decision 7): B3's single-page outline (Identity / Model / Capabilities with toggles / "On this page" nav, `B3:L66–L92`) is next-mission work. Host the **current tabbed editor** inside the 24px-padded body and change only its chrome | mission |

---

## 7. Library

### 7.1 List column

| Part | Value | Source |
|---|---|---|
| Title row | h2 "Library" and `.btn-outlined-primary.btn-sm` **"Add"** (plus icon) | `B3:L185–L186` |
| Intro | `<p>`: `margin: 0; padding: 0 16px 8px; font-size: 11px; color: var(--fg-muted)`: "Things agents can use. Attach them from an agent's Capabilities." It wraps to 2 lines (36px) at 300px | `B3:L187` |
| Add menu | **Not drawn.** The button has no handler and the board has no menu, items or copy. Mission DD: "an Add menu to choose the type" (§15) | gap |
| Scroller | `display: flex; flex-direction: column; gap: 2px` on top of the shared scroller | `B3:L188` |
| Groups (in order) | **Knowledge bases**, **MCP servers**, **Connectors** | `B3:L189`, `L192`, `L196` |
| Row | `<button>`: `display: flex; align-items: center; gap: 10px; width: 100%; padding: 8px 10px; text-align: left; color: var(--fg-secondary)` + row base. The row colour drives the icon colour | `B3:L190–L197` |
| Row: icon | 16px, by type: **database** (knowledge base), **server** (MCP server), **plug** (connector) | same |
| Row: text | flex column, `gap: 1px`. Name: 13px, `--fg`. Meta: 11px, `--fg-muted` | same |
| Meta: knowledge base | `{n} files · {n} agents` (for example "412 files · 6 agents") | `B3:L190–L191` |
| Meta: MCP server | `{n} tools · connected` or `Not connected`. **The connection state is a pre-accepted deviation**; the tool count stays | `B3:L193–L195` |
| Meta: connector | `{n} channels · {n} agents`. **The channel count is a pre-accepted deviation**; "N agents" stays | `B3:L197` |
| Selected | §3 selected style plus `color: var(--fg)`, which turns the icon `--fg` | `B3:L190` |
| Empty or per-group empty | not drawn | — |

### 7.2 Detail pane

| Part | Value | Source |
|---|---|---|
| Header | item header (§4). Breadcrumb **"Library / {Group}"** (for example "Library / Knowledge bases"); title is the item name | `B3:L202` |
| Actions (knowledge base) | `.btn-outlined-primary` with refresh-cw icon, **"Re-index"**; then `.btn-outlined-primary` with plus icon, **"Add folder"**. **No primary** | `B3:L203` |
| MCP server and connector detail | not drawn | — |
| Body | **Out of scope this mission** (knowledge base, MCP server and connector editor internals are next mission). B3's KB body is the 24px-padded grid `1fr \| 280px` (Folders table, "Try a search", "Used by N agents" aside, `B3:L205–L227`). Host the current editors, chrome only | mission |

---

## 8. Settings

### 8.1 Settings nav (in the list column's place)

| Part | Value | Source |
|---|---|---|
| Element | `<nav aria-label="Settings">`: `width: 240px; flex-shrink: 0; display: flex; flex-direction: column; gap: 2px; padding: 14px 10px; border-right: 1px solid var(--border)`. **No background set** (it shows the root `--bg`) | `B3:L231` |
| Heading | `<h2>` "Settings": 16px, weight 600. The inline style is `margin: 0 0 4px 10px; margin: 0;`, so the **second declaration wins (margin 0)**. The heading sits 10px from the column edge while item text sits at 20px (§15). B2 had the indent | `B3:L232` |
| Groups and pages (in order) | **General**: Appearance, Prompts, Encryption · **Models**: Providers · **Defaults for agents**: Built-in tools, Knowledge indexing · **Developer**: Design language | `B3:L233` |
| Group label | §3 group-label style | `B3:L233` |
| Item | `<a>`: `display: block; padding: 6px 10px; border-radius: var(--radius-sm); font-size: var(--font-size-body-sm)` (**12px**); `text-decoration: none; color: var(--fg-secondary)`. Renders 28px tall | `B3:L233` |
| Selected item | `color: var(--fg); background: var(--accent-translucent); box-shadow: inset 0 0 0 1px var(--accent)` (an inset ring, not a border). No `aria-current` | `B3:L233` |
| Superseded B2 values | items `display: flex; min-height: 32px` with an ellipsis span; heading indented 10px | `B2:` nav |

### 8.2 Item page: Providers (the only page drawn)

| Part | Value | Source |
|---|---|---|
| Header | page header (§4): **"Providers"** and `.btn-outlined-primary` with plus icon, **"Add provider"** | `B3:L236` |
| Content | `padding: 0 32px; display: flex; flex-direction: column; max-width: 880px` | `B3:L237` |
| Intro | `<p>`: `margin: 0 0 16px; font-size: 12px; color: var(--fg-muted)`: "A provider is an account or server that runs models. Agents pick one in their Model section." | `B3:L238` |
| Table | `width: 100%; border-collapse: collapse; font-size: 13px` | `B3:L239` |
| Head row | `text-align: left; font-size: 11px; color: var(--fg-muted)`. Each `<th>`: `font-weight: 500; padding: 12px; border-bottom: 1px solid var(--border)`. Columns: **Name · Type · Status · Used by**. (B2 used `8px 12px` head padding; superseded) | `B3:L240` |
| Body cells | `padding: 12px; border-bottom: 1px solid var(--border)`. Name is **weight 600**. Type is `.badge.badge--{type}` showing the type slug. Status is `.test-result.test-result-{ok\|fail}` with `margin: 0` (LED dot plus coloured text). Used by is plain text "{n} agents" (B2 made it an accent link; superseded). Rows render 43px | `B3:L242–L246` |
| Status column and banner | **pre-accepted deviations** (§13) | `B3:L242–L249` |
| Other pages | Appearance, Prompts, Encryption, Built-in tools, Knowledge indexing and Design language are **not drawn**. They host the existing pages under this page-header pattern. How a provider or built-in tool *item* opens while the list stays visible is an open question for Flight 3 | mission |

---

## 9. Jump-to palette

| Part | Value | Source |
|---|---|---|
| Invocation | the rail's bottom control (§2), accessible name "Jump to (Ctrl K)". The footer promises "Ctrl K from anywhere". **The board implements no key handler** | `B3:L25`, `L304` |
| Overlay | `position: absolute; inset: 0; display: flex; justify-content: center; padding-top: 96px` | `B3:L289` |
| Scrim | as for the picker: `<button aria-label="Close">` with `rgba(0,0,0,0.3)` | `B3:L290` |
| Dialog | `role="dialog" aria-modal="true" aria-label="Jump to"`; `width: 600px; height: fit-content; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg); box-shadow: var(--shadow-modal); overflow: hidden`. Renders 602 × 384 at x 419, y 96 with 8 results | `B3:L291` |
| Input bar | flex, align centre, `gap: 10px; padding: 14px 16px; border-bottom: 1px solid var(--border)`: search icon 18px (renders 18), then the input, then a `.btn-ghost.btn-sm` "Esc" close button | `B3:L292–L296` |
| Input | `<input id="pq">` with **no field class**: `flex-grow: 1; border: 0; background: transparent; color: var(--fg); font-size: 14px; outline: none`. Visually hidden label "Jump to"; placeholder **"Jump to an agent, chat, library item or setting"** | `B3:L293–L294` |
| Results | `padding: 8px; display: flex; flex-direction: column; gap: 2px; max-height: 420px; overflow-y: auto` | `B3:L297` |
| Result row | `<button>`: `display: flex; align-items: center; gap: 10px; padding: 8px 12px; border-radius: var(--radius-sm); border: 0; background: transparent; color: var(--fg); font-size: 13px; text-align: left`. Label `<span>`, then a "where" `<span>` (`margin-left: auto`, 11px, `--fg-muted`). Renders 33px | `B3:L299–L300` |
| Result kinds and "where" copy | Agent → `Agent`; conversation → `Chat · {agent name}`; New chat action → label `New chat…`, where `Action`; knowledge base → `Library · Knowledge base`; MCP server → `Library · MCP server`; Settings page → `Settings` (Providers) or `Settings · {group}` (for example `Settings · Defaults for agents`) | `B3:L346–L354` |
| Grouping and ordering | **No group headings.** The candidate order is every agent (data order), then chats, actions, Library and Settings. Results are **capped at 8**, so an empty query shows only the first 8 agents (superseded by Flight 4 leg 9: the empty query is a mix of recent chats, New chat… and recent agents) | `B3:L346–L355` |
| Matching | case-insensitive substring over `label + " " + where`, trimmed | `B3:L355` |
| Empty result | **none defined** (the list simply renders empty) | — |
| Active row or highlight | **not defined** | — |
| Footer | flex, `gap: 16px; padding: 10px 16px; border-top: 1px solid var(--border); font-size: 11px; color: var(--fg-muted)`: "Ctrl K from anywhere" and "Enter to open", both left-aligned (unlike the picker's split footer) | `B3:L304` |

---

## 10. Interaction behaviours (B3 script)

These are behaviour-spec material. State lives in `this.state` (`B3:L321`): `screen`, `sel`,
`q`, `palette`, `pq`, `inspector`, `picker`, `pickQ`, `newChat`. The fields `mode`, `pins`,
`TAGS`, `CHIP`, `pinLabel`, `togglePin`, `tag`, `pinned` and `rank`-as-pin are **vestigial**
from the rejected grouping and pinning prototypes; do not implement them (decision 2).

1. **Initial state.** Screen Agents, selected agent "Research assistant" (`a0`), drawer
   open, no overlays, empty queries, no pending new chat. Theme comes from the prop (dark by
   default). (`B3:L321`, `L376`)
2. **Rail destination click.** Switches to that destination and closes the palette. No other
   state resets, so each destination keeps its selection, filter and pending chat across
   switches. Returning to Agents restores the same agent and filter text. (`B3:L329`)
3. **Rail active marking.** Exactly one destination carries the active style: the current
   screen. (`B3:L330`)
4. **Jump-to rail control.** Opens the palette with an empty query. (`B3:L387`)
5. **Agents filter.** Each input updates the query. The list keeps agents whose
   `name + " " + model + " " + providerType` contains the trimmed, lower-cased query (the
   provider is matched by its **type slug**, not its display name). The result is sorted A–Z
   and the count shows "{matches} of {total}". (`B3:L332–L333`, `L341`, `L379–L380`)
6. **No filter match.** The list shows `No agents match "{q}".`. (`B3:L50–L51`)
7. **Agent row click.** Selects the agent and updates the detail pane. The filter is
   untouched. If later filtering hides the selected agent, the detail pane **keeps showing
   it**. (`B3:L339`, `L342`)
8. **Agent header "Chat".** Goes to Chats and starts a pending new chat with that agent (the
   same effect as picking it in the picker, item 13). (`B3:L384`, `L358`)
9. **"New" (Agents), "Save", "Add" (Library), "Re-index", "Add folder", "Search", "Add
   provider", the composer controls, the Settings nav links and the non-DPR conversation
   rows** are inert on the board.
10. **Chats "New chat".** Opens the agent picker with an empty query. (`B3:L368`)
11. **Picker close.** The scrim click and the "Esc" button both close the picker. The query
    clears on the next open, not on close. (`B3:L368`)
12. **Picker search.** Each input updates the query, which matches
    `name + model + providerType + description`. With an empty query the picker shows
    "Recently used" (top 5 by recency) and "All agents" (A–Z, full list). With a query it
    shows a single "{n} matching" group in **data order (not A–Z)**. Empty groups are
    dropped, and if nothing matches it shows `No agents match "{q}".`.
    (`B3:L359–L366`, `L369`)
13. **Picking an agent** (row click). Closes the picker (and the palette), clears the
    picker query, switches to Chats and creates a **pending new chat** with that agent. The
    list gains a selected "New chat · now · {agent}" row at the top of Today. The header
    reads "New chat" and "with {agent}". The pane shows the welcome (model badge, name,
    description, "Pick a different agent"). The composer placeholder becomes
    "Message {agent}…" and the composer model becomes the agent's model. The drawer shows
    that agent. There is no further step. (`B3:L358`, `L370–L373`)
14. **Picking again** while a new chat is pending **replaces** the pending one: there is
    only ever one pending row. (`B3:L358`)
15. **"Pick a different agent".** Reopens the picker. (`B3:L132`)
16. **Conversation row click** (DPR). Opens that conversation and **discards the pending new
    chat**, removing its row. (`B3:L374`)
17. **Drawer toggle.** Flips the drawer open or closed, and `aria-pressed` mirrors the state.
    The drawer starts open and its state persists across screens. (`B3:L386`)
18. **"Open agent settings".** Goes to Agents, selects the chat's agent, clears the Agents
    filter (so the agent is guaranteed visible) and closes the palette. (`B3:L375`, `L344`)
19. **Library "Settings › Knowledge indexing" link.** Goes to Settings. The board's Settings
    page is static, so in practice it lands on Providers. (`B3:L216`)
20. **Library "Used by" → "Research assistant".** Opens that agent, the same as item 18.
    (`B3:L220`, `L385`)
21. **Palette close.** The scrim and "Esc" both close it. (`B3:L387`)
22. **Palette search.** Each input filters as described in §9, capped at 8 results.
    (`B3:L355`, `L388`)
23. **Palette pick: agent.** Goes to Agents, selects the agent, clears the Agents filter and
    closes the palette. (`B3:L344`, `L346`)
24. **Palette pick: conversation.** Goes to Chats, opens it and discards any pending new
    chat. (`B3:L348`)
25. **Palette pick: "New chat…".** Goes to Chats, closes the palette and **opens the picker**
    with an empty query. (`B3:L349`)
26. **Palette pick: Library item.** Goes to Library; the board selects no specific item.
    **Palette pick: Settings page.** Goes to Settings; the board selects no specific page.
    The app must open the named item or page (SC5). (`B3:L350–L353`)
27. **Keyboard.** The script binds **no keys at all**. Ctrl K, Esc, Enter and arrow keys are
    promised only by copy: "Jump to (Ctrl K)", "Ctrl K from anywhere", the "Esc" buttons,
    "Enter to start" and "Enter to open". The implied contract is: Ctrl K opens the palette
    from anywhere; Esc closes the topmost overlay; Enter starts with or opens the active row,
    which implies an active-row concept and arrow-key movement the board does not show. All
    of this is design work for Flight 1 (the modal rule) and Flight 4. The rejected C2 board
    showed "Up/Down to move" and "Type > for actions"; those are not adopted.

---

## 11. Buttons: Deep violet

### 11.1 Common to all Deep-violet buttons (`.b` plus `.deep .b`)

| Property | Value | Source |
|---|---|---|
| Layout | `display: inline-flex; align-items: center; justify-content: center; gap: 6px; white-space: nowrap` | `Btn:L16` |
| Height | **32px** | `Btn:L16` |
| Padding | **`0 12px`** for every variant. Deep violet does **not** restore the current primary's `0 16px` (`bundle:L449`) | `Btn:L16` |
| Radius | 6px (= `--radius-sm`) | `Btn:L16` |
| Border | `1px solid transparent` unless the variant sets a colour | `Btn:L16` |
| Label | `font-family: var(--font-family-sans)`, **13px, weight 500** in all variants | `Btn:L16`, `L30` |
| Icon | 16 × 16, `flex-shrink: 0` | `Btn:L17` |
| Focus | `outline: 2px solid var(--accent); outline-offset: 2px` on `:focus-visible` | `Btn:L18` |
| Transition | `background-color 150ms, border-color 150ms, opacity 150ms`. For comparison, the app's buttons transition over `--motion-base` (250ms) at rest and `--motion-fast` (150ms) on hover, with `--ease-tactile`; reduced-motion zeroes both | `Btn:L16` |
| Disabled | **not defined on the Buttons board.** The app's existing rule (`opacity: 0.4; cursor: not-allowed`, `bundle:L440` and siblings) is the only precedent | — |

### 11.2 Variants, per theme

| Variant (app class) | Property | Dark | Light | Source |
|---|---|---|---|---|
| **Primary** (`.btn-filled-primary`) | fill | `--x-violet` **`#7c3aed`** | `--x-violet` **`#6d28d9`** | `Btn:L32`, `L58–L59` |
| | label | **`#ffffff`** (a literal; **not** `--fg-on-accent`, which is `#101114` in dark) | **`#ffffff`** | `Btn:L32` |
| | hover | fill `--x-violet-hover` **`#6d28d9`** (no opacity change) | **`#5b21b6`** | `Btn:L33` |
| | border | transparent | transparent | `Btn:L16` |
| **Secondary, raised** (`.btn-outlined-primary`) | fill | `--surface-elevated` `#1c1d22` | `#f4f4f5` | `Btn:L34` |
| | label | `--fg` `#ededf0` | `#18181b` | `Btn:L34` |
| | border | `--border` `#26272c` | `#e4e4e7` | `Btn:L34` |
| | hover | border → `--border-strong` `#4a4b55` (fill unchanged) | `#a1a1aa` | `Btn:L35` |
| **Ghost** (`.btn-ghost`) | fill | transparent | transparent | `Btn:L36` |
| | label | `--fg-secondary` `#a1a3ad` | `#52525b` | `Btn:L36` |
| | hover | fill `--surface-elevated` `#1c1d22`, label `--fg` `#ededf0` | `#f4f4f5` / `#18181b` | `Btn:L37` |
| **Danger** (`.btn-muted-destructive`) | fill | **transparent** (the current treatment uses a soft danger fill at rest) | transparent | `Btn:L38` |
| | label | `--status-danger` `#f87171` | `#b91c1c` | `Btn:L38` |
| | border | `--status-danger-muted` `#d98c8c` | `#b45252` | `Btn:L38` |
| | hover | fill `--status-danger-bg-soft` `rgba(248,113,113,0.08)` | `rgba(185,28,28,0.06)` | `Btn:L39` |

### 11.3 Changes from the app's current classes

| Class | Current (bundle) | Deep violet |
|---|---|---|
| `.btn-filled-primary` | `--accent` fill, `--fg-on-accent` ink, 12px / 600, `0 16px`, hover `opacity: 0.9` (`bundle:L442–L462`) | violet fill, white ink, 13px / 500, `0 12px`, hover darker fill |
| `.btn-outlined-primary` | `--surface` fill, 12px / 400, hover fill `--surface-elevated` and border `--border-hover` (`bundle:L412–L440`) | `--surface-elevated` fill, 13px / 500, hover border `--border-strong` |
| `.btn-ghost` | 12px / 400, hover fill `--surface` (`bundle:L464–L490`) | 13px / 500, hover fill `--surface-elevated` |
| `.btn-muted-destructive` | soft danger fill at rest, 12px / 400, hover border `--status-danger` (`bundle:L492–L519`) | transparent at rest, 13px / 500, hover soft fill |

### 11.4 Sizes and icon-only

| Shape | Deep-violet source | B3 usage | Note |
|---|---|---|---|
| Default | 32px tall (`Btn:L16`) | most buttons | — |
| Wide / large | `.b.wide`: `width: 100%; height: 36px` (`Btn:L20`), used for New chat | `.btn-lg` + `width: 100%` (`bundle:L533`: 36px, `0 20px`, 13px) | The two agree on 36px. They disagree on padding (12 versus 20); with width 100% this is invisible |
| Icon-only | `.b.icon`: `width: 32px; padding: 0`, so **32 × 32** (`Btn:L19`), shown as a ghost "Copy" | B3 never squares its icon-only buttons: drawer toggle `.btn-ghost` renders 42 × 32, composer attach `.btn-ghost.btn-sm` renders 34 × 24, rail jump-to is 44 × 44 by inline style | The app has no icon-only modifier today. The library needs one, sized per the Buttons board (32 × 32), except the rail jump-to, which B3 sizes explicitly at 44 × 44 |
| Small | **not defined on the Buttons board** | `.btn-sm` (`bundle:L532`: 24px, `0 8px`, **10px** label): "New", "Add", both "Esc", "Pick a different agent", attach | Deep violet's "13px medium labels" sits at variant level, so whether `btn-sm` keeps a 10px label is **unresolved** (§15) |

### 11.5 Deep violet on B3's buttons

| Variant | B3 instances |
|---|---|
| Primary | Agents header "Save" (`L63`), Chats "New chat" (large, full width, `L100`), composer "Send" (`L160`) |
| Secondary | Agents "New" (small), agent header "Chat", drawer "Open agent settings", Library "Add" (small), "Re-index", "Add folder", KB "Search", Settings "Add provider" |
| Ghost | rail jump-to (44 × 44), drawer toggle (icon only), composer attach (small, icon only), "Pick a different agent" (small), picker "Esc" and palette "Esc" (small), KB "Used by" agent list (`justify-content: flex-start`) |
| Danger | none as a button on B3 ("Delete agent" is an outline link in `--status-danger`). The Buttons board shows danger as "Delete" with a trash-2 icon |
| Custom (no `btn-*` class) | rail destinations (§2), list rows, picker rows, palette rows, scrims, and the inline link "Settings › Knowledge indexing" (`background: none; border: 0; padding: 0; font: inherit; color: var(--accent)`, `B3:L216`) |

### 11.6 Tokens

The board's `--x-violet` and `--x-violet-hover` are prototype names. Per the mission DD they
become a dedicated fill-token pair under the contrast-gated `--accent*` family, together with
a white on-fill ink token, because `--fg-on-accent` stays `#101114` in dark. The same fill
applies to **checked checkboxes and switched-on toggles** (mission DD). B3's toggles still
render the old `--accent` track (`bundle:L1282`). The existing lighter `--accent` stays for
focus rings, links, selection borders and washes. In light theme the new fill equals the
existing `--accent` (`#6d28d9`). `--x-violet-edge`, `--x-raised-hover` and `--x-highlight`
(`Btn:L58–L59`) belong to the rejected Tactile and Neutral options and are not needed.

---

## 12. Copy deck (every user-visible string on B3)

Conventions taken from the source: sentence case; `…` is U+2026; separators are ` · `
(U+00B7 with spaces); the breadcrumb separator is ` / `; `›` is U+203A
("Settings › Knowledge indexing"); apostrophes are ASCII `'`; queries in empty states sit in
ASCII double quotes. `{…}` marks data.

| Surface | Strings |
|---|---|
| Frame and rail | nav label `Main` · brand alt `GleepGlorp AI` · `Chats` · `Agents` · `Library` · `Settings` (each is both visible label and aria-label) · jump-to aria-label `Jump to (Ctrl K)` |
| Agents list | `Agents` · `{shown} of {total}` · `New` · hidden label `Filter agents` · placeholder `Filter by name, model or provider` · `No agents match "{q}".` |
| Agents detail (chrome) | breadcrumb `Agents` · title `{agent name}` · `Chat` · `Save` |
| Agents detail (body; out of scope, for reference) | `Identity` · `Name` · `Description` · `Model` · `Provider` · `Capabilities` · `Knowledge base · {n} files` · `Built-in · …` · `MCP server · {n} tools` · `On this page` · `Identity` `Model` `Prompt` `Capabilities` `Behavior` `Self-configuration` `Conversations ({n})` `Delete agent` · provider option `{display name} ({type})` |
| Chats list | `Chats` · `New chat` · `Today` · `Yesterday` · `Last 7 days` · pending row `New chat` / `now` / `{agent}` · rows `{title}` / `{time}` / `{agent}` |
| Chat header | `{chat title}` or `New chat` · `with {agent name}` · toggle aria-label `Show this chat's agent` |
| New-chat welcome | `{model}` (badge) · `{agent name}` · `{description}` · `Pick a different agent` |
| Thread telemetry | `ctx:` · `{n}%` · `in:` · `{n}` · `out:` · `{n}` |
| Composer | hidden label `Message` · placeholder `Message {agent name}…` · aria-label `Attach a file` · `{model}` · `Send` |
| Agent drawer | region label `This chat's agent` · `{agent name}` · `{provider type}` (badge) · `{description}` · `Model` · `Provider` · `Chats` · `Open agent settings` |
| Agent picker | `Start a chat with…` · `Esc` · hidden label `Find an agent` · placeholder `Find an agent by name, model or provider` · `Recently used` · `All agents` · `{n} matching` · `No agents match "{q}".` · `Picking an agent starts a new chat with it` · `Enter to start` · scrim aria-label `Close` |
| Library list | `Library` · `Add` · `Things agents can use. Attach them from an agent's Capabilities.` · `Knowledge bases` · `MCP servers` · `Connectors` · `{n} files · {n} agents` · `{n} tools · connected` · `Not connected` · `{n} channels · {n} agents` |
| Library detail (chrome) | breadcrumb `Library / Knowledge bases` · title `{item name}` · `Re-index` · `Add folder` |
| Library KB body (out of scope, for reference) | `Folders` · `Watching · {n} files` · `Indexing · {n} of {m}` · `Try a search` · hidden label `Search this knowledge base` · `Search` · `Chunk size and indexing schedule are app-wide: ` + link `Settings › Knowledge indexing` + `.` · `Used by {n} agents` |
| Settings nav | `Settings` · `General` · `Appearance` · `Prompts` · `Encryption` · `Models` · `Providers` · `Defaults for agents` · `Built-in tools` · `Knowledge indexing` · `Developer` · `Design language` |
| Settings › Providers | `Providers` · `Add provider` · `A provider is an account or server that runs models. Agents pick one in their Model section.` · `Name` · `Type` · `Status` · `Used by` · `{n} agents` · *(deviation)* `Signed in` · `Connected` · `Key rejected` · `OpenAI rejected the saved API key. 6 agents can't reply until you update it.` |
| Jump-to palette | dialog label `Jump to` · hidden label `Jump to` · placeholder `Jump to an agent, chat, library item or setting` · `Esc` · `New chat…` · where-labels `Agent`, `Chat · {agent}`, `Action`, `Library · Knowledge base`, `Library · MCP server`, `Settings`, `Settings · {group}` · `Ctrl K from anywhere` · `Enter to open` · scrim aria-label `Close` |
| **Needed but not on B3** | unsaved indicator (B1 precedent: `Unsaved changes`, `Discard`) · Library **Add menu items** (presumably the singular group names: Knowledge base / MCP server / Connector; not drawn) · palette empty state · empty Chats, Agents and Library lists · drawer "what it can use" section |

---

## 13. Pre-accepted deviations (SC8)

These board elements need data the app cannot yet provide. They may be omitted, or replaced
with a neutral equivalent, without operator sign-off.

| # | Element | Where on the board | Missing data | What stays |
|---|---|---|---|---|
| D1 | Provider **Status** column: `Signed in`, `Connected`, `Key rejected` as `.test-result-ok/-fail` with LED | Settings › Providers table, `B3:L240–L246` | Provider health | Name, Type badge, Used by (derivable). Note: "Signed in" for `anthropic-plan` might be derivable from `oauth_active`, but it is in the same family and either choice is acceptable |
| D2 | **Provider-health banner** `.banner.banner-error`: "OpenAI rejected the saved API key. 6 agents can't reply until you update it." | below the Providers table, `B3:L249` | Provider health | — |
| D3 | **MCP connection state** in Library rows: `· connected`, `Not connected` | Library list, MCP servers group, `B3:L193–L195` | MCP live connection state | `{n} tools` (derivable; mission DD) |
| D4 | **Connector channel count** `3 channels` | Library list, Connectors group, `B3:L197` | Channel counts | `{n} agents` (derivable) |
| D5 | **Providers as a table** (§8.2): Name · Type · Status · Used by rows | Settings › Providers, `B3:L239–L246` | — (an **operator decision**, not missing data: the Mission 25 Flight 3 DD14 checkpoint, 2026-10-05) | The list renders as **tiles matching Built-in tools**: the name link is the item link, with a type badge, the base URL and "Used by". The intro, the page header and "Add provider" stay, and the item opens below the list (Flight 3 DD7, leg 7) |

**Out of scope, not deviations** (hosted unchanged this mission, next mission redesigns them):
the agent-detail body (outline, Capabilities toggles, "On this page"), the knowledge-base
detail body (folders with watch and index status, "Try a search", the "Used by" aside), and
MCP-server and connector detail bodies (not drawn).

---

## 14. Token usage

### 14.1 Tokens B3 references directly (inline styles and script)

| Token | Dark / light | Where used |
|---|---|---|
| `--bg` | `#101114` / `#ffffff` | frame root (`L18`); list sections Agents, Chats, Library (`L28`, `L97`, `L184`) |
| `--surface` | `#17181c` / `#fafafa` | rail (`L19`); composer box (`L154`); drawer (`L166`); picker and palette dialogs (`L256`, `L291`) |
| `--border` | `#26272c` / `#e4e4e7` | all hairlines: rail right; list right; item-header bottom; Chats scroller top; chat header bottom; composer box; drawer left and header bottom; Settings nav right; table cells; picker and palette borders and separators; outline-nav inactive bars; capability rows; KB folder box |
| `--fg` | `#ededf0` / `#18181b` | root ink; active rail item; row names and titles; selected Settings item; drawer and table ink; palette rows; input ink |
| `--fg-secondary` | `#a1a3ad` / `#52525b` | inactive rail items (`RAIL`); chat row agent line; welcome description; drawer description; picker row description; Library row resting colour (icon); "Used by N agents" heading; Settings items |
| `--fg-muted` | `#85878f` / `#6e6e77` | agent count; filter and search icons; agent row model; breadcrumbs; group labels; chat row times; "with {agent}"; composer model; drawer `<dt>`; picker row model; picker and palette footers; palette where-labels; Library intro and meta; table head; Providers intro; "On this page" label; outline inactive links |
| `--accent` | `#a78bfa` / `#6d28d9` | selected border on rail item, agent, chat and Library rows (`L330`, `L338`, `L373`, `L190`); Settings selected inset ring (`L233`); outline active bar (`L84`); inline link (`L216`) |
| `--accent-translucent` | `rgba(167,139,250,0.10)` / `rgba(109,40,217,0.08)` | selected wash on rail item, agent row, chat row, pending new-chat row, Library row and Settings item |
| `--status-danger` | `#f87171` / `#b91c1c` | "Delete agent" outline link (`L91`, out of scope) |
| `--font-family-sans` | Geist, system-ui, … | frame root |
| `--font-family-mono` | Geist Mono, … | agent row model; composer model; drawer Model value; picker row model; KB folder paths |
| `--font-size-tiny` | 10px | rail labels (`RAIL`); `CHIP` (vestigial) |
| `--font-size-caption` | 11px | agent count; agent row model; breadcrumbs; group labels; chat row time and agent; composer model; picker row description and model; footers; palette where-labels; Library intro and meta; table head |
| `--font-size-body-sm` | 12px | "with {agent}"; drawer description and facts; Settings items; Providers intro; outline links; KB paths; Used-by heading |
| `--font-size-body` | 13px | frame root; row names; chat title (h1); drawer name; picker row name; palette rows; table body |
| `--font-size-body-lg` | 14px | composer textarea; welcome description; picker search field; palette input |
| `--font-size-h2` | 16px | list-column titles; Settings heading; picker title |
| `--font-size-h1` | 18px | welcome agent name |
| `--radius-sm` | 6px | rail items; all list rows; Settings items; picker and palette rows |
| `--radius-md` | 8px | composer box; KB folder box |
| `--radius-lg` | 12px | picker and palette dialogs |
| `--shadow-modal` | `0 8px 30px rgba(0,0,0,0.18)` (both themes) | picker and palette dialogs |
| `--topbar-h` | 48px | chat header height |

### 14.2 Tokens reached through classes B3 uses

| Token | Dark / light | Via |
|---|---|---|
| `--surface-elevated` | `#1c1d22` / `#f4f4f5` | `.field-select option`; **Deep-violet secondary fill and ghost hover** |
| `--border-hover` | `#33343b` / `#d4d4d8` | current `.btn-outlined-primary:hover` (replaced) |
| `--border-strong` | `#4a4b55` / `#a1a1aa` | toggle off-track; **Deep-violet secondary hover border** |
| `--fg-on-accent` | `#101114` / `#ffffff` | current primary label (replaced); toggle knob |
| `--fg-faint` | `#6b6d78` / `#898993` | `.telemetry .label` |
| `--status-success` / `--status-warning` | `#4ade80` / `#15803d`; `#fbbf24` / `#8f5606` | `.test-result-ok/-warning` (deviation D1; KB body); B1 "Unsaved changes" |
| `--status-danger-muted`, `--status-danger-bg-soft` | `#d98c8c` / `#b45252`; `rgba(248,113,113,0.08)` / `rgba(185,28,28,0.06)` | `.banner-error`; **Deep-violet danger border and hover** |
| `--accent-translucent-hover` | `rgba(167,139,250,0.16)` / `rgba(109,40,217,0.13)` | `.msg.user` border |
| `--surface-translucent`, `--surface-tool`, `--fg-tool-msg` | — | `.msg.assistant`, `.msg.tool` |
| `--code-block-bg` / `--code-block-fg` | `#0c0d10` / `#f4f4f5`; `#ededf0` / `#18181b` | `.code-block` (KB body) |
| `--badge-{type}` / `--badge-ink-{type}` | ollama `#2ecc71`, openai `#4a9eff`, anthropic `#9b59b6`, anthropic-plan `#cc785c`, openrouter `#7c3aed`, mock `#888888` (same in both themes); web, filesystem and execution differ by theme | `.badge--*`, including the 8px provider dots |
| `--font-weight-medium/-semibold/-bold` | 500 / 600 / 700 | `.field-group > label`, `.badge`, `.editor-title` |
| `--space-1`, `--space-3` | 4px, 12px | `.field-group` |
| `--motion-fast/-base`, `--ease-tactile` | 150ms / 250ms, `cubic-bezier(0.4,0,0.2,1)` | button and field transitions |
| `--line-height-normal/-tight` | 1.5 / 1.2 | `.msg`, `.banner`, `.badge` |

### 14.3 Buttons board only

| Variable | Dark / light | Status |
|---|---|---|
| `--x-violet` | `#7c3aed` / `#6d28d9` | **approved** (primary fill), to be renamed under `--accent*` |
| `--x-violet-hover` | `#6d28d9` / `#5b21b6` | **approved** (primary hover) |
| `--x-violet-edge`, `--x-raised-hover`, `--x-highlight` | — | rejected options only; not needed |

---

## 15. Ambiguities and inconsistencies register

Each item is stated as found. Resolve it in the named flight or raise it at the operator
checkpoint. Do not silently pick a value.

| # | Finding | Source | Owner |
|---|---|---|---|
| A1 | B3 renders buttons and toggles in the **current** treatment; Deep violet comes only from the Buttons board (§0, §11) | `bundle:L412–L543` | F1 |
| A2 | Content-box board versus border-box app: rail 73, list 301 and drawer 321 render 1px wider than written; the **Settings nav renders 261 against 240 as written** | §1.3 | F3 |
| A3 | Settings heading `margin: 0 0 4px 10px; margin: 0;`: the duplicate cancels the indent, so the heading sits 10px inset against the items' 20px. B2 had the indent | `B3:L232` | F3 |
| A4 | SVG `width`/`height` attributes are overridden by `.btn-* svg { 16px }`: "New" and "Add" plus (12→16), rail jump-to (18→16), attach (14→16). The author's intent is unclear | `B3:L25`, `L30`, `L158`, `L186` | F1 |
| A5 | Icon-only buttons on B3 are not square (42 × 32, 34 × 24). The Buttons board's icon variant is 32 × 32. The rail jump-to is 44 × 44 | §11.4 | F1 |
| A6 | `.btn-sm` (24px, 10px label) is used five times on B3 but not defined in Deep violet, which says "13px medium" | §11.4 | F1 |
| A7 | Primary padding: Deep violet `0 12px` against the app's `0 16px`. `.b.wide` against `.btn-lg`: `0 12px` against `0 20px` | `Btn:L16`, `bundle:L449`, `L533` | F1 |
| A8 | List-row geometry differs per list: Agents `7px 10px` with 0 gap (48px); Chats and Library `8px 10px` with 2px gap (51 and 50px); picker `10px 12px` (55px); palette `8px 12px` (33px); Settings items `6px 10px` at 12px type (28px) | §3 | F1 (list pane) |
| A9 | Selected marker: a 1px border on rows and the rail, but an inset `box-shadow` ring on Settings items (visually the same) | `B3:L233` | F1 |
| A10 | **No hover, focus-visible or keyboard-active style** for rail items, list rows, picker rows or palette rows. "Enter to start" and "Enter to open" imply an active row that is never shown | — | F1, F4 |
| A11 | **The script binds no keys.** Ctrl K, Esc and Enter are copy only. The "Esc" buttons' accessible name is "Esc" | §10 item 27 | F1, F4 |
| A12 | `aria-current` is missing on the active rail item, the selected chat row and the selected Settings item; only agent rows have it. B1 and B2 used `aria-current="page"` on the rail | `B3:L21–L24`, `L41`, `L233` | F2, F3 |
| A13 | **The drawer lacks "what it can use"**, which the mission requires (decision 3, SC3); it shows only Model, Provider and Chats | `B3:L171–L178` | F4 |
| A14 | **The Add menu is not drawn**; the Library "Add" button is inert | `B3:L186` | F3 |
| A15 | **No unsaved-changes indicator on B3**; only superseded B1 has one ("Unsaved changes", `--status-warning`, plus Discard and Save) | `B1:` header | F2, F3 |
| A16 | The Agents filter and the picker match the provider **type slug** ("anthropic-plan"), not the provider display name ("Claude Max"). The picker also matches descriptions while the Agents filter does not. Filtered picker results come in **data order, not A–Z**. "All agents" repeats the Recently-used agents | `B3:L333`, `L360`, `L363–L365` | F3, F4 |
| A17 | Palette: no groups, no type ordering, cap 8 (an empty query shows only agents), no empty state, footer not split like the picker's | §9 | F4 |
| A18 | Agent **Delete** lives in the out-of-scope outline; the header has no Delete. Its place in the hosted tabbed editor is not on the board | `B3:L61–L64`, `L91` | F3 |
| A19 | The Library intro says "Attach them from an agent's **Capabilities**", which does not exist this mission (the tabbed editor stays) | `B3:L187` | F3 |
| A20 | Badge text differs: the new-chat welcome badge shows the **model**, while the drawer and Providers badges show the **provider type** | `B3:L129`, `L169` | F4 |
| A21 | Drawer header (42px) and chat header (48px plus 1px) hairlines do not line up | `B3:L121`, `L167` | F4 |
| A22 | Header heights differ across panes: item header 62, page header 64, chat header 48, drawer header 42, Chats list block 93. No cross-column alignment is intended or shown | §4 | info |
| A23 | Static sample data is inconsistent: Providers "Used by" 9/4/9/6/2 (30 agents) against the 28-agent data set (7/4/8/6/2 plus 1 mock, which has no provider row); drawer "Chats 3" against the list. **Counts must come from data, not the board** | `B3:L242–L246`, `L312` | F3, F4 |
| A24 | **Light-theme contrast**: `--fg-muted` caption text on the selected-row wash is **4.43:1** (below 4.5). This affects the model line in a selected agent row, the time in a selected chat row and the meta in a selected Library row. Dark is 4.62:1 | App. C | F1 (SC7) |
| A25 | The composer `<textarea>` has `outline: none` and nothing replaces it, so a focus indicator (for example `:focus-within` on the box) must be added for SC10. The same applies to the palette input | `B3:L156`, `L294` | F4 |
| A26 | The initially selected agent is not scrolled into view (it is 22nd of 28) | §3 | F3 |
| A27 | The board's item and page bodies are `overflow: hidden` because they are static; the app needs scrolling bodies under fixed headers | §4 | F3 |
| A28 | Chats groups: only Today, Yesterday and Last 7 days are drawn; "Yesterday" rows show a weekday rather than a time; older chats are undefined | `B3:L103–L117` | F4 |
| A29 | The pending new chat is **discarded** when another conversation is opened. Is a session created on pick (SC3: "starts a new conversation … with no further step") or on first send? | `B3:L374` | F4 |
| A30 | Scrim `rgba(0,0,0,0.3)` is a literal, the same in both themes, with no token. The scrim is also a focusable full-screen `<button aria-label="Close">` | `B3:L255`, `L290` | F1 |
| A31 | Provider dots on agent and picker rows are colour-only and `aria-hidden`; the provider is not named in the row text | `B3:L42`, `L271` | F1 (a11y) |
| A32 | The board includes a connector agent (Discord concierge) in "Recently used"; mission DD excludes connector-driven sessions from recency (that is data, not a design rule) | `B3:L364` | F4 |

---

## Appendix A: Derived rendered geometry (Chromium, 1440×900, Geist)

These are boxes from `getBoundingClientRect`, so they include borders. Positions are frame
coordinates. Theme-independent.

| Element | x | y | w × h |
|---|---|---|---|
| Rail | 0 | 0 | 73 × 900 |
| Brand mark | 22 | 12 | 28 × 28 |
| Rail item (Chats / Agents / Library / Settings) | 6 | 58 / 117 / 176 / 235 | 60 × 53 |
| Rail item icon / label | — | +9 / +31 | 18 × 18 / ~34 × 13 |
| Rail jump-to | 14 | 844 | 44 × 44 (icon 16) |
| List column | 73 | 0 | 301 × 900 |
| List title h2 | 89 | 15.5 | × 21 |
| Title-row `btn-sm` ("New") | 296 | 14 | 61 × 24 (icon 16) |
| Agents filter field | 89 | 48 | 268 × 35 (icon 14 at 99, 57) |
| First agent row | 81 | 91 | 284 × 48 (dot 8 at x 92) |
| Chats "New chat" | 89 | 45 | 268 × 36 |
| Chats scroller (top hairline) | 73 | 93 | 300 × 807 |
| Group label | 81 | — | 284 × 30 |
| Chat row | 81 | 126 (first) | 284 × 51, pitch 53 |
| Library intro | 73 | 48 | 300 × 36 |
| Library row | 81 | 116 (first) | 284 × 50, pitch 52 |
| Settings nav | 73 | 0 | 261 × 900 |
| Settings heading / first item | 83 / 83 | 14 / 69 | 240 × 21 / 240 × 28 |
| Item header (Agents, Library) | 374 | 0 | 1066 × 62 |
| Breadcrumb / title | 398 | 12 / 28 | × 14 / × 21 |
| Header buttons | — | 14.5 | h 32 ("Chat" 74 wide, "Save" 63 wide in the current treatment) |
| Settings page header | 334 | 0 | 1106 × 64 |
| Providers table head / row | 366 | 96 / 134.5 | h 38.5 / h 43 |
| Chat header | 374 | 0 | 745 × 49 (with drawer) |
| Drawer toggle | 1061 | 8 | 42 × 32 |
| Thread column | 398 | 73 | 697 × … (720 max, limited by the pane) |
| Composer box | 398 | 778 | 697 × 102 |
| Composer Send | 997 | 837 | 85 × 32 (current treatment) |
| Drawer | 1119 | 0 | 321 × 900 |
| Drawer header | 1120 | 0 | 320 × 42 |
| Drawer "Open agent settings" | 1136 | 186 | 161 × 32 (current treatment) |
| Picker dialog | 399 | 72 | 642 × 722 |
| Picker search field | 420 | 125 | 600 × 40 (icon 16 at 432, 137) |
| Picker list (top hairline) | 400 | 177 | 640 × 581 |
| Picker row | 412 | 208 (first) | 616 × 55 |
| Picker footer | 400 | 758 | 640 × 35 |
| Palette dialog | 419 | 96 | 602 × 384 (8 results) |
| Palette input bar | 420 | 97 | 600 × 53 |
| Palette row | 428 | 158 (first) | 584 × 33, pitch 35 |
| Palette footer | 420 | 444 | 600 × 35 |

Deep-violet buttons (Buttons board): default 32px tall; "Save" 56 wide; "New agent" (icon
and label) 114 wide; "Cancel" 68 wide; "Delete" (icon and label) 87 wide; icon-only 32 × 32;
wide 36 tall.

## Appendix B: Icons (Lucide geometry, 24×24 viewBox, `stroke-width: 2`)

| Use | Icon | In app `icons.js` today? |
|---|---|---|
| Rail Chats; "Chat" button | message-circle | yes, as `chat` |
| Rail Agents | bot | yes, as `studio` |
| Rail Settings; "Open agent settings" | settings (gear) | yes, as `admin` |
| Rail Library; knowledge-base rows | database | **no** |
| Jump-to, filter, picker search, palette | search | **no** |
| "New", "Add", "Add folder", "Add provider" | plus | yes |
| "New chat" | square-pen | yes |
| Drawer toggle | panel-right | **no** |
| Attach | paperclip | **no** |
| Send | send | yes |
| Re-index | refresh-cw | yes |
| MCP-server rows | server | **no** |
| Connector rows | plug | **no** |
| Buttons-board samples | copy, trash-2 | `copy` yes; `trash` (trash-2 geometry not verified) |

## Appendix C: Contrast pre-check (informative; the gate is `tests/test_design_tokens_a11y.py`)

| Pair | Dark | Light |
|---|---|---|
| White label on violet fill | 5.70 | 7.10 |
| White label on violet hover | 7.10 | 8.98 |
| Violet fill against `--bg` (non-text) | 3.31 | 7.10 |
| Violet fill against `--surface` (non-text) | 3.11 | 6.81 |
| Secondary: `--fg` on `--surface-elevated` | 14.40 | 16.12 |
| Secondary fill against `--bg` / its `--border` against `--bg` | 1.12 / 1.27 | 1.10 / 1.27 |
| Ghost: `--fg-secondary` on `--bg` | 7.51 | 7.73 |
| Danger: `--status-danger` on `--bg` | 6.83 | 6.47 |
| Danger hairline `--status-danger-muted` against `--bg` (non-text) | 7.26 | 4.92 |
| `--fg` on selected-row wash (over `--bg`) | 14.16 | 15.56 |
| `--fg-muted` on selected-row wash (over `--bg`) | 4.62 | **4.43** |
| `--fg-secondary` on `--surface` (rail labels) | 7.06 | 7.41 |

The raised secondary's boundary is below 3:1 in both themes. Its label identifies the
control, so whether WCAG 1.4.11 applies is a call for the Flight 1 contrast work.
