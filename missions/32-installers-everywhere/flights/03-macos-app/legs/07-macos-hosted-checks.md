# Leg: macos-hosted-checks

**Status**: in-flight
**Flight**: [macOS app](../flight.md)

## Objective
Prove the macOS app on the hosted runner: a `lifecycle` dispatch builds N and N+1, passes strict `doctor`, the audit, the signature and the `.dmg` layout, and passes `lifecycle.sh` L1-L10. Fix what the run shows, within the remaining budget (dispatches 3 and 4, with 5 as the spare). Then write the macOS install guide, the contributor checklist, the docs, and the finalized `macos-app-install` behavior test from the evidence.

## Context
- **Flight DDs:** DD10 (the budget is 5 per the operator, with 2 used), DD12 (the CLI by path), DD13 (the hosted layers), DD14 (the contributor check). DD5 plus leg 3b: replacing the app while it runs crashes the old copy (quit first). DD8: `min_os` 14.0.
- **Leg 6's notes for this leg** (flight log, `### macos-recipe`):
  - read L1's `route=subclass` row first;
  - the audit is `--report-only` on the first run, then flipped to enforcing (`M32_AUDIT_ARGS=""`) once `A/audit.txt` is clean;
  - the credential comes from `checks.sh` gate 4, so a skipped checks step makes the lifecycle steps 401;
  - the timeout layering (the review fixes): a 60-minute job and a dynamic lifecycle bound.
- **Known to be unproven until this run:** the System Events close-button click, the quit Apple event to the `/Applications` copy, the JXA screen read, `lsappinfo` after `open -a`, the `hdiutil attach` flags, and leg 4's `_install_delegate`/`_begin_activity` in the real product.
- **Outward steps:** commit and push, then dispatch. They are under the operator's standing go for this flight's runs, and the cap is 5.

## Steps
1. **Dispatch 3:** the Flight Director commits legs 6 and 7's inputs, pushes, re-verifies `gh auth`, and dispatches `gh workflow run macos-packages.yml --ref flight/03-macos-app -f mode=lifecycle`.
2. **Read the evidence** (a Developer): download the run, then build a row-by-row table of `A/SUMMARY.txt` and `lifecycle/SUMMARY.txt`. Read `A/audit.txt`, the first-paint PNGs and the per-quit log segments. Classify each FAIL as one of: a product defect, a harness defect, or a runner limit.
3. **Fix** (a Developer, only if needed): product defects get a fix with unit tests; harness defects a fix with a Linux rehearsal. Flip the audit to enforcing if its report is clean. **Dispatch 4** re-runs `lifecycle`. Dispatch 5 is the spare. **A sixth needs the operator.**
4. **Docs** (a Developer, once a lifecycle run is green or every remaining FAIL has a disposition):
   - **`docs/macos-install.md`** (new), modelled on `docs/linux-install.md`:
     - which download (the `.dmg`, Apple Silicon, macOS 14 or later);
     - install by drag;
     - **Gatekeeper on macOS 15+:** "Not Opened", then System Settings › Privacy & Security › Open Anyway, then confirm. Leg 3 saw "Not Opened" with no Open button on 15.7, and the Settings path is the documented route; say which macOS versions the text covers;
     - first launch;
     - the Dock behaviour (close keeps it running; the Dock icon brings it back; Cmd-Q quits);
     - upgrade: **quit first**, then replace (the old copy crashes if replaced while running);
     - remove: drag to the Trash; the data stays at `~/Library/Application Support/the-one/`, with how to remove it;
     - logs at `~/Library/Logs/GleepGlorp AI/app.log`;
     - the CLI by path (DD12) and `doctor`, with what its `tray: dock`/`path:` lines mean;
     - no Python? (`doctor`'s interpreter line and what to install);
     - troubleshooting;
     - cross-links.
   - **README "Install":** a macOS subsection.
   - **`CLAUDE.md`:** an additive "macOS packaging (M32 F3)" paragraph next to the Linux one: `packaging/macos/` (`build.sh`, `product.json`, `info_plist.py`, `audit.py`, `checks.sh`, `lifecycle.sh`, `lib.sh`, `probe/`), the workflow modes, and pointers.
   - **`the_one/agents.md`:** a "macOS packaging" section (the build flow, the bundle, the audit rules, the log file, the lifecycle driver, the probe), additive.
   - **`docs/macos-contributor-check.md`** (new): the contributor's written checklist, generated from the behavior test's step table, with the commands to paste and the screenshots to take.
   - **`tests/behavior/macos-app-install.md`:** finalized from the evidence (the Gatekeeper wording, the log path, step 9's crash expectation), still status `draft` with "Last Run: never". The run is Flight 4's.

## Acceptance Criteria
- [ ] **AC1:** a `lifecycle` run with every `A/SUMMARY.txt` and `lifecycle/SUMMARY.txt` row PASS, the audit enforcing and clean, the `.dmg` artifact uploaded, and its run id recorded. **Or**, if the budget runs out, every remaining FAIL has a classification and an operator disposition.
- [ ] **AC2:** every product or harness fix carries tests or a rehearsal, and is recorded in the flight log; `make test-unit` passes with 12 skips; ruff is clean.
- [ ] **AC3:** the docs as listed. The guide's commands and paths are the ones the run exercised (cross-checked in the flight log).
- [ ] **AC4:** the hosted minutes are recorded per run, with the flight total.

## Files Affected
- per fixes: `the_one/interfaces/desktop/*`, `packaging/macos/*`, `.github/workflows/macos-packages.yml` (the `on:` block untouched)
- `docs/macos-install.md`, `docs/macos-contributor-check.md` (new), `README.md`, `CLAUDE.md`, `the_one/agents.md`, `tests/behavior/macos-app-install.md`

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.
