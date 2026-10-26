# Leg: release-dry-run

**Status**: completed
**Flight**: [Windows on shared metadata, and one release](../flight.md)

## Objective
Prove the composed release once. One manual `release.yml` dispatch builds, checks and lifecycle-tests all four packages and publishes nothing. Then the flight-end gates pass, and one reviewer reviews the whole flight diff.

## Context
- **Flight DDs:** DD8 (the dry run, the fail rule, the budgets) and DD12 (the verification layers).
- **The operator's go (2026-10-26):** the dry run uses `windows_mode=lifecycle`, which is the 4th and last hosted Windows lifecycle run, and `macos_mode=lifecycle`, which is macOS run 2 of 4. A red Windows row then needs the operator's go for any re-run. A red macOS row may use one re-run (run 3), and the release keeps run 4; past that, the operator decides.
- **The release stub** is on `main` (#317, `85d3555`), with its dispatch inputs frozen.
- **The version:** `0.12.0.dev1`. It is the contributors' N (DD10), with a 14-day `.dmg` retention, and the operator's first Windows field step (DD11). It is above v0.11.8, so the Windows L1 row crosses a real version change. That closes leg 3's gap.
- **This is an interactive Flight Director leg** (outward dispatches, evidence reading). Developers are spawned only for fixes. The flight-end Reviewer follows the skill's Phase 2d.

## Steps
1. **Re-check the environment:**
   - `gh auth status`;
   - no standalone platform run in flight (`gh run list`), per the DD7 rule;
   - the host load.
2. **Dispatch:** `gh workflow run release.yml --ref flight/04-windows-and-release -f version=0.12.0.dev1 -f macos_mode=lifecycle -f windows_mode=lifecycle`, with `platforms` at its default.
3. **Read every row:**
   - `audit`;
   - `version`, which should print `0.12.0.dev1` on the dispatch path;
   - Windows `full`, then lifecycle L1-L9, with L1 now 0.11.8 → 0.12.0.dev1;
   - Linux, the gates for both packages;
   - macOS `A/SUMMARY.txt` and `lifecycle/SUMMARY.txt`, including L1's first-paint screenshots (squawk 0261);
   - `publish` skipped;
   - the artifact names `windows-installer`, `linux-packages` and `macos-dmg` all present, with the right file names for `0.12.0.dev1` (`deb_version` `0.12.0~dev1`).

   Record minutes per job.
4. **Fix only what is red.** Classify each failure as a product defect, a harness defect or a runner limit, and fix it through a Developer and a review. Re-run only the failed platform with `-f platforms=<p>`, within the budget above.
5. **Flight-end gates on a quiet host.** Neither gate runs beside another session's test processes.
   - `make test-unit`: 12 skips expected.
   - All browser lanes: `THE_ONE_TEST_NETNS=1 THE_ONE_REQUIRE_WEBKIT=1 PYTHON=.venv/bin/python TEST_TIMEOUT=3600 bash scripts/run-tests.sh --parallel 3 --tb=short`, against the 3-lanes-host-wide policy. If Mission 31 has lanes running, wait.
   - `ruff check` and `ruff format --check`.
6. **The Linux GTK smoke** was run on leg 2's boot-policy commits and does not need re-running unless the shell changed since (it has not).
7. **The flight-end Reviewer** (Phase 2d) reviews the whole branch diff against `origin/main`, every leg's criteria, and the artifacts. Its model is Sonnet, because the diff includes the credential-adjacent smoke probe and the release `contents: write`.

## Acceptance Criteria
- [x] **AC1:** the dry run is green on every job except `publish`, which reads `skipped`. The run id, minutes per job and the full row tables (Windows L1-L9, macOS 13 checks and 13 lifecycle steps, Linux gates) are in the flight log.
- [x] **AC2:** the three artifacts hold exactly the four `0.12.0.dev1` packages under the names `scripts/release_assets.py` expects. Checked by downloading the artifacts and running `release_assets.py` locally against them, into a scratch directory under `$HOME/the-one-m32-evidence/f4/leg5/`. `SHA256SUMS` is generated there; nothing is published.
- [x] **AC3:** the macOS L1 screenshots are classified for squawk 0261 (proven, inconclusive or regressed), and the squawk is updated.
- [x] **AC4:** the gates. `make test-unit` passes (12 skips), every browser lane passes (`PARALLEL_RESULT rc=0 … lanes=13`, with each lane's time against its budget), and ruff is clean. Any flake gets the triage rule (isolated re-run, recorded).
- [x] **AC5:** the flight-end Reviewer signals `[HANDOFF:confirmed]`, after at most 3 fix cycles.
- [x] **AC6:** the budgets are recorded. Hosted Windows lifecycle runs end at 4 of 4. macOS runs end at 2 of 4, or 3 if a re-run was needed.

## Verification Steps
- AC1, AC3: `gh run view <id>`; `gh run download <id>` into `$HOME/the-one-m32-evidence/f4/leg5/`; read the summaries and the PNGs.
- AC2: `python scripts/release_assets.py --version 0.12.0.dev1 --in <dir> --out <dir>` (check its usage first).
- AC4: the gate commands and their result lines.
- AC5: the Reviewer's report.
