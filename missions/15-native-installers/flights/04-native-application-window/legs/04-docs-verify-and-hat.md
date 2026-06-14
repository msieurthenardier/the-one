# Leg: docs-verify-and-hat

**Status**: completed
**Flight**: [Native Application Window](../flight.md)

## Objective

Document the new windowed launch path (`the-one app`, the `[gui]` extra, the
fallback, single-instance, the Linux WebKitGTK note), run the final
verify-integration pass, and — operator opted in — the **HAT**: the operator
opens the real chromeless window and confirms the native feel + single-instance
+ clean close + the Origin-allowlist behavior.

## Context

- **Test allocation (refined Leg 1):** Legs 1-2 already shipped their launcher
  unit tests (17 passing); this leg is **docs + verify + HAT**, NOT "all
  launcher tests."
- **DD6/DD8:** the rendered window has no CI apparatus — the HAT is the only
  rendered-window check this flight; deeper UI testing is the next mission's
  gated MCP. The HAT is **interactive** (operator-run; not agent-spawned).
- **Origin risk (flagged Leg 1):** the embedded WebView's `Origin` header vs
  `OriginAllowlistMiddleware` (`app.py:316-319`) — GET/WS unaffected, but a
  WebView POST with `Origin: null` could be gated. The HAT validates this.
- **Carried for docs:** the `[gui]` extra + per-platform deps (DD1), the
  system-browser fallback (DD5), the **Linux WebKitGTK system-dependency**
  (apt `gir1.2-webkit2-4.x`, `python3-gi`) — both a user install note and the
  F5 packaging forward-pointer (AppImage-hostile → prefer `.deb`/`.rpm` depends).

## Inputs

- `the_one/interfaces/app.py` (Legs 1-2) — the launcher.
- `README.md`, `CLAUDE.md`, `the_one/agents.md` — docs surfaces.
- `the_one/main.py` — the `the-one app` subcommand (Leg 1).
- `tests/test_app_launcher.py` (17 tests, Legs 1-2).

## Outputs

- `README.md` — a "Desktop window" section: `pip install 'the-one[gui]'` then
  `the-one app`; the system-browser fallback; the Linux WebKitGTK system
  packages; single-instance (one the-one per port).
- `CLAUDE.md` / `agents.md` — a short developer note: the launcher architecture
  (uvicorn.Server on a daemon thread + pywebview on main; the join-and-drain
  shutdown helper, the `server is None` no-op contract; `_select_port`'s
  connect-probe + startup-retry; `_webview_available`'s typelib-only probe; the
  optional `[gui]` extra / lazy import). The browser-CI path-filter + its
  "add new UI surface to the `ui` filter" maintenance rule.
- Flight log — the verify-integration result + the HAT run result/disposition.

## Acceptance Criteria

- [ ] `README.md` documents `the-one app` (the `[gui]` extra install, the
      WebKitGTK Linux packages, the browser fallback, single-instance).
- [ ] `CLAUDE.md` + `agents.md` carry the launcher developer note (architecture,
      the shutdown helper contract, the probes, the `[gui]` extra, the browser-CI
      path-filter maintenance rule).
- [ ] **verify-integration:** the full default suite + bwrap + lint are green;
      `serve`/`chat`/`version` unchanged; `the_one/interfaces/app.py` imports
      clean on Linux without pywebview/gi; the 17 launcher tests pass; the
      browser job correctly **skips** on this (non-UI) PR (Leg 3).
- [ ] **HAT (operator, optional — opted in):** on a machine with a WebView
      backend + `[gui]` installed, `the-one app` opens a chromeless native window
      rendering the UI; a second `the-one app` does NOT double-bind (single-
      instance); the window closes cleanly (no hung process); a basic UI action
      that POSTs works (the Origin check). Result + any disposition recorded;
      if deferred (no display handy), note "HAT operator-run-pending" — the
      flight may still land per DD6.

## Verification Steps

Docs (implementing agent, locally):
- The doc claims match the shipped code (cross-check `the-one app`, the `[gui]`
  extra, the fallback, single-instance behavior).
- `.venv/bin/python -m pytest tests/ --timeout=300 -q` — green (docs don't
  affect tests; regression guard).
- `.venv/bin/python -m pytest tests/test_app_launcher.py -q` — 17 pass.
- `.venv/bin/python -c "import the_one.interfaces.app; import importlib.util as u; print(u.find_spec('webview'))"` → None.

HAT (operator, on a real display):
1. `pip install -e ".[all-llms,dev,gui]"` (or `pip install 'the-one[gui]'`) on a
   machine with a WebView backend (Windows: WebView2; macOS: built-in; Linux:
   `sudo apt install python3-gi gir1.2-webkit2-4.1`).
2. `the-one app` → a chromeless native window opens and renders the agent UI
   (native title bar "GleepGlorp AI", no URL/address bar).
3. Run a `the-one app` again (or while the first is open) → it opens a window
   onto the SAME instance; no second server / no port error (single-instance).
4. Use the UI: send a chat message (WS) and perform one action that POSTs (e.g.
   save a setting) → it succeeds (the Origin-allowlist does not block it).
5. Close the window → the process exits cleanly within a few seconds (the
   lifespan drain completes; no orphaned process — check Task Manager / `ps`).
6. *(fallback, optional)* on a box without a WebView backend, `the-one app`
   opens the system browser instead and keeps serving (Ctrl-C stops it).

## Implementation Guidance

1. **Docs are the implementable part** (spawn a Developer for them). Be accurate
   against the shipped `the_one/interfaces/app.py`. Keep the README section
   user-facing (install + run + the Linux packages + fallback); keep the
   CLAUDE.md/agents.md note developer-facing (the architecture + the contracts).
   CLAUDE.md may hit the self-modification guard (F1/F3 precedent) — if blocked,
   do README + agents.md and flag CLAUDE.md for operator authorization.
2. **Do NOT change launcher/CI code** — docs only. If a doc edit reveals a code
   inaccuracy, flag it to the FD.
3. **The HAT is operator-guided** (NOT agent-spawned): the FD walks the operator
   through the steps above, fixes inline if a step fails (e.g. if the Origin
   check blocks a POST, add the pywebview origin to the allowlist — a small
   `app.py` change), and records the result.

## Notes for the Flight Director

- After the docs Developer lands: Phase 2d reviews ALL of Legs 1-4's uncommitted
  changes (one Reviewer, fix loop), commits, opens the draft PR.
- THEN guide the operator through the HAT (their machine + display). If the HAT
  surfaces the Origin issue, fix it in a follow-up commit. If deferred, land with
  "HAT operator-run-pending" (DD6 allows it; the next mission's MCP is the deeper
  apparatus).
- Then flight → landed, check off in mission.md, `[COMPLETE:flight]`,
  `/flight-debrief`.
