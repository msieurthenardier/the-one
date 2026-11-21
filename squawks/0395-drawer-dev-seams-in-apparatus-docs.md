# Squawk 0395: Name the drawer and fill dev seams in the UI test apparatus docs

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-11-21
**Completed**: 2026-11-21

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
Added a "GleepGlorp drawer and fill dev seams (M36 F3 L9)" subsection to `the_one/agents.md`, at the end
of "UI test apparatus" (before "Errors and late responses"), naming each of the five seams with a path
and purpose. `CLAUDE.md` untouched. Note: the `__ggFillSettleTimeoutMs` read is in
`areas/studio/agent-editor-fill.js` (`timeoutMs_`), not `gleepglorp-drawer/fill.js` as the report said;
the doc cites the real file.

## Verification
The agents.md "UI test apparatus" section names each seam with a one-line purpose. Every path it cites
exists.

Checked: `ls scripts/gleepglorp_drawer_seed.py scripts/probe/gg-drawer` shows the seed script and
`esc.js fill.js open.js`; `grep` found `__ggFillSettleTimeoutMs` in `agent-editor-fill.js:94`,
`_selected_response` in `the_one/llm/mock.py:31`, `data-gg-probe` / `open-done` in
`scripts/probe/gg-drawer/open.js`, and `L9b` in `packaging/macos/lifecycle.sh` (lines 32, 643, 658,
742, 777). Seed refusals and flags read from the script's own docstring and `add_argument` calls.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet; the security tier, since the batch changed the shell-write hook and CLAUDE.md's safety rules), batch review of squawks 0368, 0379, 0384, 0385, 0391-0397
**Verdict**: confirmed
**Commit**: `squawk: turnaround 2026-11-21` on squawk/turnaround-2026-11-21
