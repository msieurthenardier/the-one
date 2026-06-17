# Leg: docs

**Status**: completed
**Flight**: [Windows Native App Hardening — Visual Polish](../flight.md)

## Objective

Update the project docs to reflect what F7 actually shipped — the `DesktopSession` structure, the
launch splash, the **native OS frame** (NOT frameless — the DD3 divert), and the brand icon — and
record the pywebview/WebView2 frameless-chrome footgun so the mac/Linux port doesn't re-attempt it.

## Context

- Deferred to last (F6-debrief lesson: docs as a separate, final leg) so it documents the
  settled shape rather than churning across the splash spike + the DD3 divert.
- **Critical:** the frameless custom chrome was ABANDONED (DD3 divert → DD2-alt). Docs must NOT
  describe a frameless window / custom HTML titlebar / `js_api` window controls as shipped —
  those were removed in Leg 8. The shipped window is a **native OS frame** + splash + brand icon.

## Acceptance Criteria

- [x] `agents.md` (and/or `CLAUDE.md`) updated where it describes the desktop interface: the
      `the_one/interfaces/desktop/` module + `DesktopSession` lifecycle (window/tray/quit/splash),
      the launch **splash** (frameless brand window during the boot wait, dismissed on the main
      window `loaded`), the **native-framed** main window (`frameless=False`; close→tray via the
      native X), and the brand `.ico` baked into `exe_gui`.
- [x] A **footgun note** recorded (agents.md, near the desktop/pywebview notes): pywebview
      frameless custom chrome does NOT work on Windows WebView2 (edgechromium) — `easy_drag` /
      `.pywebview-drag-region` only activate on `platform=='chromium'`; CSS `-webkit-app-region`
      is Electron-only; `pywebviewready` can fire before a 2nd window's page listener attaches.
      The mac/Linux port should use the **native frame** (DD2-alt), not frameless.
- [x] `README.md` reflects the desktop app accurately if it describes launch/features (splash +
      native window); no stale "frameless/custom titlebar" claims anywhere.
- [x] `packaging/windows/regenerate_icon.py` is referenced where icon regeneration would be
      looked for (packaging README or a comment) so the `.ico` regen is discoverable.
- [x] No doc claims the custom frameless chrome shipped. Grep the docs for `frameless`,
      `titlebar`, `js_api`, `win-controls` and correct/remove stale references.

## Verification Steps

- `grep -rin "frameless\|custom titlebar\|js_api\|win-control" *.md agents.md docs/ 2>/dev/null`
  → no stale "shipped" claims; only accurate native-frame + the footgun note.
- Docs read coherently against the actual `the_one/interfaces/desktop/shell.py` (DesktopSession,
  splash, `frameless=False`).
- No source/test changes in this leg (docs only).

## Implementation Guidance

1. Find where the desktop interface is documented (`grep -rn "desktop\|pywebview\|run_desktop\|the-one app" agents.md CLAUDE.md README.md docs/`).
2. Update those sections to the shipped F7 shape: DesktopSession, splash, native frame, brand icon.
3. Add the WebView2-frameless footgun note (concise, near existing desktop/pywebview guidance).
4. Keep it accurate and minimal — no new frameless/custom-chrome claims.

## Files Affected

- `agents.md` and/or `CLAUDE.md` — desktop section + footgun note.
- `README.md` — desktop app description (if present).
- Possibly `packaging/windows/README.md` — reference `regenerate_icon.py`.

---

## Post-Completion Checklist

**Per the batched model — set status to `landed`; do NOT commit. The flight-completion commit
covers this leg.**

- [x] Docs updated to the native-frame + splash + icon reality; footgun note added
- [x] No stale frameless/custom-chrome "shipped" claims
- [x] Update flight-log.md; set this leg `landed`; check off `docs` in flight.md
