# Leg: macos-probe-run

**Status**: in-flight
**Flight**: [macOS app](../flight.md)

## Objective
Read the evidence of probe run `40203877635` and settle, with citations to that evidence, the decisions legs 4-7 depend on: the apparatus (Accessibility or the test seam), the delegate route and the `NSTerminateLater` behaviour, which path a real Cmd-Q takes, the first-paint cause, the `min_os` value, the inherited environment, and the replace-while-running behaviour.

## Context
- **Flight DDs:** DD3, DD4, DD5, DD7, DD8, DD9, DD11. Leg 2's `packaging/macos/probe/README.md` says how to read each premise's evidence.
- **The run** is dispatch 1 of 4: `macos-packages.yml`, `--ref flight/03-macos-app` at `503ac2e`, `mode=probe`.
- **The product `.app` was built from `main`'s desktop code** (leg 1 is not in it). Its readings describe today's build, not the target (DD9).

## Inputs
- The run's logs (`gh run view 40203877635 --log`) and its uploaded artifact (`gh run download 40203877635 -D $HOME/the-one-m32-evidence/f3/leg3/run-40203877635/`).

## Outputs
- A `### macos-probe-run` section in the flight log with:
  - **A premise table:** for each of P1-P9 and `OTOOL`, what was observed (quoting `SUMMARY.txt` rows and the evidence files) and what it settles.
  - **The decisions** (each one line, with the DD it feeds):
    1. **The apparatus:** Accessibility works or not (P3), so is the DD9 seam needed in leg 4? Does the quit Apple event reach the app (P2)? Is `lsappinfo front` usable (P4)?
    2. **The delegate:** the route that worked (`subclass`, `classAddMethods` or none), and whether `NSTerminateLater` plus the deferred reply terminated the probe app (P2). Divert criterion 1 (DD4) or 2 (DD3) is triggered if neither route works, or if the deferred reply never terminates.
    3. **Cmd-Q's path:** T or S (P3), or unknown if keystrokes were refused.
    4. **The first paint:** the cold and warm timings of the product against the probe-window control, the app log's timeline, and the class of cause among DD11's candidates (our shell, ATS, the first WKWebView start, the runner's rendering). If it's our shell, what leg 4 changes.
    5. **`min_os`:** the maximum `LC_BUILD_VERSION` minos. If it is above 11.0, DD8's `min_os` becomes that value (an operator-visible change to the supported macOS versions; record it, and raise it if it exceeds macOS 13).
    6. **The environment:** the `PATH`/`SHELL` an `open`-launched app inherits (P8), and whether `open --env` passes variables.
    7. **Replace while running (P5):** what happened, and what the guide must say (DD5).
    8. **Gatekeeper (P6):** the `spctl`/`syspolicy_check` verdicts, what an `open` of a quarantined copy did, and the screenshot. These feed the guide's approval steps (leg 7).
    9. **Today's build:** anything notable from the product app (for example a pystray AppKit thread warning, or `focused:false`) that confirms or corrects DD2.
  - **The hosted minutes used** (job minutes, plus the 10× billed estimate).
- Any change these decisions force on legs 4-7 is noted for the Flight Director, who re-designs those legs. This leg edits no other artifact.

## Acceptance Criteria
- [ ] The artifact is downloaded, and its sha256 list is recorded in the evidence dir.
- [ ] The flight-log section has a row for every premise and all nine decisions, each citing an evidence file.
- [ ] Every divert criterion is explicitly evaluated (triggered or not).
- [ ] Nothing in the repo changed except the flight log (and this leg's status).

## Verification Steps
- `ls` of the evidence dir; the flight-log section read against `SUMMARY.txt`.

## Implementation Guidance
- Start from `SUMMARY.txt`, then open each premise's evidence directory. Look at the screenshots (the Read tool shows PNGs) for P1's series, P4's frontmost and P6's dialog.
- Quote; don't paraphrase numbers.
- If the run failed before the probe (a build or selftest failure), the leg's output is the failure's cause and a fix recommendation for the Flight Director. No decision is made on missing evidence.

## Files Affected
- `missions/32-installers-everywhere/flights/03-macos-app/flight-log.md` (its own section)
- this leg file's status

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.
