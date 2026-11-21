# Squawk 0395: Name the drawer and fill dev seams in the UI test apparatus docs

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-21
**Completed**: —

## Report
Mission 36 Flight 3 added dev-only seams that the desktop and HAT checks rely on, and the docs never
name them together:
- `window.__ggFillSettleTimeoutMs`, the fill settle timeout, read only in dev mode;
- `scripts/gleepglorp_drawer_seed.py`, which seeds a dev instance so GleepGlorp runs on a scripted
  mock, with `--check-fill`;
- the mock provider's `config["responses"]` sequence;
- `scripts/probe/gg-drawer/*.js`;
- the macOS lifecycle step `L9b`.

Add them to `the_one/agents.md` "UI test apparatus", not to `CLAUDE.md`. The operator said on
2026-11-21 that `CLAUDE.md` is too large and should point to other docs; see squawk 0397. At most,
`CLAUDE.md` gets a pointer.

## Evidence
- `the_one/interfaces/web/static/js/gleepglorp-drawer/fill.js`: `__ggFillSettleTimeoutMs`.
- `scripts/gleepglorp_drawer_seed.py`, `the_one/llm/mock.py::_selected_response`,
  `scripts/probe/gg-drawer/`, `packaging/macos/lifecycle.sh` (`L9b`).
- Flight 3 debrief, "Documentation".

## Corrective Action
*(written at completion)*

## Verification
The agents.md "UI test apparatus" section names each seam with a one-line purpose. Every path it cites
exists.
