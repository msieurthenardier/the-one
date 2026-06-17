# Flight Debrief: Windows install docs & mission closeout

**Date**: 2026-06-17
**Flight**: [Windows install docs & mission closeout](flight.md)
**Status**: landed
**Duration**: 2026-06-17 (single session)
**Legs Completed**: 2 of 2

## Outcome Assessment

### Objectives Achieved

The flight achieved its (re-scoped) objective: a documentation-only closeout of Mission 15.
`docs/windows-install.md` now walks a non-technical Windows user from download through a running
app (SmartScreen passthrough, UAC, the two-exe model, close-to-tray, `%LOCALAPPDATA%` data +
`~/.the-one` migration, `the-one.exe doctor`, uninstall), linked from the README. The last stale
Docker-era operator messages were reworded host-native (both `stdio.py` `SandboxError` messages,
`cache_cleanup.py` comments, `api.py` `host.docker.internal`), the `config.py` `%APPDATA%`→
`%LOCALAPPDATA%` docstring bug was fixed, the README demotes the retired Docker path, and the stale
`packaging/windows/README.md` Output section was corrected. No app behavior changed; the suite
stayed green.

**This is the last flight of Mission 15** — with Flights 1, 3–9 landed and Flight 2 (macOS Seatbelt)
migrated out, the Windows-only mission is functionally complete pending merge + `/mission-debrief`.

### Mission Criteria Advanced

- "Installation + first-run steps, including the unsigned-app workaround, documented (Windows)" — **met** (primary deliverable).
- "Non-Docker guidance when a runtime is absent" — **met** (the last Docker-flavored operator messages removed).
- "Working CLI alongside the windowed app" — **documented** (`the-one.exe` two-exe model).
- "Data per-user, preserved across restarts, `~/.the-one` migrated" — **documented** (`%LOCALAPPDATA%` + migration; behavior shipped F1).

### Checkpoints

All flight checkpoints met during execution; the flight.md completion checklist is fully checked
except "Code merged" (the PR merge — a process step). PR #124 is open/ready.

## What Went Well

- **Re-scope discipline.** Narrowing the roadmap's bundled "first-run UX + acceptance + comprehensive
  HAT" down to a docs-only closeout was the right, principled call — the installer was already
  operator-validated (F8), and neither carry-forward Known Issue had ever been witnessed in normal
  use. Avoided regression risk in core paths for unwitnessed edges.
- **Design review earned its keep on a docs flight** — it caught *factual* errors that would have
  shipped wrong docs: the two-exe reality (`the-one-app.exe` shortcut vs `the-one.exe` CLID), the
  stale `packaging/windows/README.md` Output section, the `config.py` `%APPDATA%` docstring bug, the
  tray Show item, the UAC prompt. For documentation, the review *is* a fact-check.
- **Pre-grepping the test assertions before the messaging leg** converted a likely mid-leg surprise
  (broken assertions) into a known constraint: preserve the asserted prefixes (`bubblewrap exited
  non-zero`, `namespace creation refused`), reword only the Docker-prescriptive tail. Zero test
  updates needed; suite stayed green.
- **DD2b triage (not zero-hit grep)** was the right model — every Docker reference was classified
  with a disposition rather than destructively scrubbed; accurate dev/historical context retained.

## What Could Be Improved

### Process
- A cross-leg carry-item (fix the stale `packaging/windows/README.md` Output section) surfaced at
  Leg-1 *design review* and was injected into Leg 2 via the flight log rather than being in the
  original scope. Low-stakes here (both legs doc-only), but cross-leg dependencies materializing at
  design time are a mild coordination risk worth noting.

### Technical
- **WebView2 edge case** (Developer): the guide says "no extra download needed," true for Windows
  10+ in the vast majority of cases, but a stripped Enterprise LTSB image without Edge WebView2 would
  silently fail to render. Defensible for the target audience; worth a one-line guide note in a
  future revision (or when signing lands).
- The two **deferred Known Issues** remain open by design (see Deviations) — non-blocking edge cases.

### Documentation
- macOS/Linux install docs are intentionally absent (Windows-only re-scope, DD4) — the README now
  has a Windows-first install path with no macOS/Linux equivalent. This is scoped to the follow-up
  mission, not an oversight; the mission debrief should say so explicitly.
- `tests/HAT.md` (`docker compose logs` steps) and `tests/behavior/pty-session-containment.md`
  ("under Docker: cap_add SYS_ADMIN" precondition) carry stale Docker-era test-doc references. They
  pass the DD2b bar (test-historical, not operator-facing) but are genuine debt — flagged as a
  maintenance candidate.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|-----------|--------|--------------|
| Roadmap F9 ("UX + acceptance + HAT") re-scoped to docs-only closeout | Installer already operator-validated (F8); the 2 carry-forward issues never witnessed in normal use; closeout shouldn't risk core-path regressions | **Yes** (the pattern) — re-scope a roadmap flight to its *real remaining value* at planning rather than executing the stale bundle |
| 2 carry-forward Known Issues deferred, not fixed (DD1) | Test/HAT-discovered edge cases, non-blocking; informed operator decision | n/a — recorded as accepted maintenance-bound; carried to mission debrief |
| Leg 2 skipped a dedicated design-review spawn (FD grounded the test-assertion risk by direct grep) | Flight-level Architect already validated DD2/DD2b/DD5; only addition was the prefix-preservation note | Situational — sound economy when the flight-level review already covers the leg's design surface |

## Key Learnings

- **A design review on a docs flight is a fact-check** — its value is verifying every claim against
  the code, which is exactly where doc bugs hide. It caught four real inaccuracies here.
- **Reword messages by preserving test-asserted prefixes and replacing only the stale tail** — grep
  the tests first; it lets a "message accuracy" change stay a pure no-logic string edit.
- **Test metrics held flat** — 3219 passed / 18 skipped / ~341s, identical pass/skip to F8 (no
  logic changed); the message rewordings preserved the asserted prefixes (`test_mcp_sandbox_integration.py:505/545` pass). No regression, no flakes.

## Recommendations

1. **Proceed to `/mission-debrief`** after merge — Mission 15 (Windows-only) is functionally
   complete; this debrief feeds it. The mission debrief should classify the cross-platform criteria
   as **"deferred to the follow-up macOS/Linux mission"** (operator re-scope), not "unmet."
2. **Carry the two deferred Known Issues into the mission debrief** as scoped maintenance legs:
   (a) single-instance no-window-`serve` coexistence behavior (`shell.py:488-496`); (b) `run_shell`
   Windows tree-kill (`taskkill /F /T`/Job Object on the non-PTY path + un-gate the regression test).
3. **Bundle a low-risk test-doc cleanup pass** (HAT.md + `pty-session-containment.md` Docker-era
   references) as the first maintenance item after the mission closes.
4. **Carry the F8 CI items** into the mission debrief's known-constraints: the manual pre-push
   `fly execute` gate (discipline-dependent), the single shared Windows worker (queuing risk if the
   project grows), and the MinIO bare-IP endpoint fragility (recommend a stable alias).
5. **Minor**: add a WebView2 one-liner to the Windows guide in a future revision (stripped Enterprise
   images).

## Action Items
- [ ] Merge PR #124 (then the unified Concourse `ci` + installer refresh runs on `main`, per DD5).
- [ ] Run `/mission-debrief` for Mission 15 — carry forward items per Recommendations 1–4.
- [ ] (Maintenance, post-mission) The two deferred Known Issues + the HAT.md/behavior-spec test-doc cleanup.
