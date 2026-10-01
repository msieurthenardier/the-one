# Mission 25 reference: approved prototype boards

This directory holds the design source for Mission 25 (Workbench Navigation and Control
Library). It contains the prototype boards the operator reviewed, copied verbatim, and a
derived spec (`reference-spec.md`) that crews build and verify against for SC8 ("matches
the approved samples").

**This is design source, not a test baseline.** Nothing here is compared byte-for-byte or
pixel-for-pixel by a test. Screenshots taken to compare a running build against these boards
are **flight-log evidence**. They are never committed, whether here, under `tests/`, or
anywhere else in the repo. Verification uses computed-style probes and DOM assertions against
`reference-spec.md`, with screenshots as supporting evidence only.

## Source artifacts

| Artifact | URL | Version | Copied |
|---|---|---|---|
| Prototype canvas ("GleepGlorp Navigation Prototypes") | https://claude.ai/artifact/787XyAuiyoA969YSF5ZnFc | `1790814146-6469` | 2026-09-30 |
| Design system ("GleepGlorp AI") | https://claude.ai/artifact/51jpj1RcXp18MehEQAteWs | `1790808967-8eb7` | 2026-09-30 (`canvas.json` records `copiedAt` 2026-09-30T18:30:00Z) |

Both URLs point to mutable artifacts. **The copies in this directory are the reference of
record for this mission.** If a URL later shows something different, these files win.

## Board status

| File | Canvas title | Status | Notes |
|---|---|---|---|
| `boards/B3-workbench-clickable.dc.html` | B · Workbench — clickable (28 agents) | **Approved** | The interactive board. Its layout, copy and state machine are the primary source for the spec. |
| `boards/Buttons.dc.html` | Button treatments | **Approved: "Deep violet" section only** | The `.deep` rules plus the `--x-violet` / `--x-violet-hover` per-theme variables. The Current, Neutral primary, Tactile and Pill options were not chosen. |
| `boards/B1-agents.dc.html` | B1 · Workbench — agents | Superseded | Earlier static version of direction B. Useful for interpreting B3 (for example, its "Unsaved changes" header). **B3 wins wherever they differ.** Its single-page outline editor and merged Capabilities list are next-mission scope (mission decision 7). |
| `boards/B2-settings.dc.html` | B2 · Workbench — one Settings | Superseded | Earlier static Settings for direction B. B3 wins wherever they differ. |
| `boards/Main.dc.html` | A1 · Agents first — chat | Rejected | Direction A. |
| `boards/A2-agent-page.dc.html` | A2 · Agents first — agent page | Rejected | Direction A. |
| `boards/C1-chat-inspector.dc.html` | C1 · Chat-first — inspector | Rejected | Direction C. |
| `boards/C2-jump-to.dc.html` | C2 · Chat-first — jump to anything | Rejected | Direction C. B3 carries its own jump-to palette. |
| `boards/canvas.json` | — | Index | Board positions and titles, the design-system pin, and the operator's sticky notes (`notes.sb3` is the B3 walkthrough). |
| `boards/ds/gleepglorp/tokens.css`, `tokens.json` | — | Design-system copy | The tokens the boards render with. At copy time their color, spacing, radius, shadow and typography values match the app's `static/css/tokens.css` and `static/css/fonts.css`, checked 2026-09-30. |
| `boards/ds/gleepglorp/components/bundle.css` | — | Design-system copy | The app's `components.css` verbatim, plus unscoped extractions of area rules. Class names (`btn-filled-primary`, `field-input`, `badge--ollama`, …) are the app's real classes. |

## Checksums (sha256)

Computed 2026-09-30, when the boards were copied in. The board files must stay byte-identical to the canvas copy.

```
2ebf0b1dd530a0b0e94026d60f8d15f10097c5446c3c9ea0731c9a0696573cc4  boards/B3-workbench-clickable.dc.html
53034330ab33362d11b7c26a2d254bd99bf01e28717d44fd0aaa1513a9265139  boards/Buttons.dc.html
a4d16e7b03334a32144424fd6a5a9b76fb8462a2b45b6be16fb2a4028f189efc  boards/B1-agents.dc.html
bb78882d983b431e16296549de5a6f035af3c5bac503cd39eecf3e0b6a675224  boards/B2-settings.dc.html
641382094c616ed26b9efeb376a3319102029a7b3480f681a0bfaa1634ef351a  boards/Main.dc.html
646a19877a765bfa353f5f805e5a25d03da2290721e0bdaab9c5fdac45b6eae4  boards/A2-agent-page.dc.html
f4ab6f3caaefd2ccb4ce92cf2a229bf12f2346c2a015203e7efe3bb84ed35683  boards/C1-chat-inspector.dc.html
da0cd6b632b9fca7ad87c31333890e3f1589c835bcd1843e4b957c893809e21b  boards/C2-jump-to.dc.html
2719f7fe2597cbaa5210538197d43283c3687e89db6addebab701c234a51a770  boards/canvas.json
cb39b983081219608b4ecd0298d4fc502141e2fe96d92d4438f93365e59beffe  boards/ds/gleepglorp/tokens.css
3b2861da5dee9f7a509c8beda3f34b215bdaef61696ab6fc551dbd15189cf50d  boards/ds/gleepglorp/tokens.json
0404c45c5e16276e6fc30a2be58f48600c4fdc24b19cf12c4d81bb9ff43d4767  boards/ds/gleepglorp/components/bundle.css
```

To re-check, run `cd missions/25-workbench-navigation/reference && sha256sum -c` with the
block above saved to a file.

## External references inside the boards (not copied)

- **`./support.js`** is the canvas's Design-Component runtime. It expands the `<x-dc>`
  template (`{{holes}}`, `<sc-for>`, `<sc-if>`), runs the `class Component extends DCLogic`
  script, and re-renders on `setState`. It is not copied and is never shipped, so the
  boards do **not** render standalone in a browser. To see one locally, a crew can write a
  throwaway shim for those four semantics and keep it out of the repo. The derived geometry
  in `reference-spec.md` was measured that way, in Chromium at 1440×900 with the app's Geist
  fonts.
- **`/_blob/84cc497525576d6498f3b4c9e77f9514`** is the canvas's blob-store copy of the app's
  brand mark (rendered 28×28, `image-rendering: pixelated`, `alt="GleepGlorp AI"`). The repo
  already ships the brand under `the_one/interfaces/web/static/brand/`. Today the top bar
  uses `topbar-icon-24.png` as `.app-brand-mark`, and larger sources such as
  `gleepglorp_icon.png` (600 px) and `gleepglorp_small.png` (512 px) are also present. The
  blob is not copied.
- **`fonts/Geist-VF.woff2`, `fonts/Geist-Mono-VF.woff2`** are referenced by
  `ds/gleepglorp/tokens.css` and not copied. The app ships the same pinned fonts in
  `the_one/interfaces/web/static/fonts/`.

## Using this reference

- Build and verify against **`reference-spec.md`**. It cites every value back to a line in
  B3, the Buttons board's `.deep` rules or `bundle.css`. Where the boards are ambiguous or
  inconsistent, the spec says so instead of guessing.
- Visual comparison happens in **both themes**. The boards switch theme through the
  component prop `theme` (`dark` by default, or `light`), which sets `data-theme` on the
  frame root.
- Elements that need data the app cannot yet provide (provider health and its banner, MCP
  connection state, connector channel counts) are **pre-accepted deviations** (SC8). The
  spec lists each one. Every other deviation is fixed, or accepted by the operator and
  recorded in the flight log.
