# Leg: release-and-field-check

**Status**: ready
**Flight**: [Windows on shared metadata, and one release](../flight.md)

## Objective
Ship `v0.12.0` from `main` through `release.yml`. Then close the field checks: the operator upgrades their own Windows install, and contributors run the macOS check on real Macs. Cut patch releases if the field finds anything. The flight lands when the operator confirms.

## Context
- **Flight DDs:** DD10 (the contributor check), DD11 (the order, the two-step Windows field upgrade, the outward steps).
- **The dry run proved the composed release.** Run `40263206440` covered the audit, the version gate, three platforms, four packages, `release_assets.py` and `SHA256SUMS`. Its Windows findings were fixed and proven on run `40265814405`.
- **What the tag first exercises:** `publish` (draft, upload, publish), and the version gate's tag path. Both are unit-tested.
- **The notes:** `docs/releases/v0.12.0.md` was approved by the operator (2026-10-26).
- **Interactive leg:** the operator merges and gives each go; the Flight Director guides one step at a time.

## Steps
1. **The version bump**, the PR's last code commit. `the_one/__init__.py`: `__version__ = "0.12.0"`. It goes through a Developer and a tiny review. Check that `scripts/release_check.py --event push --ref refs/tags/v0.12.0` passes locally, and that the unit slice and ruff pass.
2. **The flight PR,** from `flight/04-windows-and-release` to `main`. The stub files on `main` (`release.yml`, `windows-packages.yml`) conflict add/add; resolve by keeping the branch's versions, as Flight 3 did. The PR body follows the skill's format. CI (lint, pip-audit) must be green. **The operator reviews and merges.**
3. **The tag** (with the operator's go):
   - re-check `gh auth status`;
   - `git fetch`, then confirm `origin/main` holds the merge and `the_one/__init__.py` says `0.12.0`;
   - `git tag -a v0.12.0 origin/main -m "v0.12.0"`, then `git push origin v0.12.0`.
4. **The release run:** watch `release.yml` on the tag (audit → version → three platforms in `full` mode → publish). Check that the release page lists the five files and that `SHA256SUMS` verifies after download. Record the run id and minutes. This is macOS run 3 of 4.
5. **The Windows field upgrade** (the operator, DD11, two steps):
   1. Back up `%LOCALAPPDATA%\the-one`.
   2. With v0.11.8 running, install the dry run's `the-one-setup-0.12.0.dev1.exe` (artifact `windows-installer` from run `40263206440`; this uses the force path).
   3. Start it, then install the release's `the-one-setup-0.12.0.exe` over it (the graceful path, under a real UAC prompt).
   4. Check the tray, the Windows 11 tint, single instance, the startup screen's logo, and that the data survived.
6. **The contributors' macOS check** (DD10). Send them `docs/macos-contributor-check.md`, with N = the dry run's `.dmg` (artifact `macos-dmg` of run `40263206440`, 14 days) and N+1 = the release `.dmg`. Their returned checklist and screenshots become the run log of `tests/behavior/macos-app-install.md` (the evidence-HAT shape). Squawk 0261 is decided by their step 3 observation.
7. **Patches:** any field issue becomes a fix on a branch, a PR, a merge, then a tag `v0.12.1`, each with the operator's go.
8. **Landing:** when the operator confirms, the flight is marked `landed` and the mission's Flight 4 is checked off. This leg's artifacts go in a follow-up PR.

## Acceptance Criteria
- [ ] **AC1:** `v0.12.0`, or its last patch, is published by `release.yml` from `main`, with the four packages plus `SHA256SUMS`. The run id is in the flight log.
- [ ] **AC2:** the operator reports the two-step Windows upgrade done, with data intact, and the field checks as they found them.
- [ ] **AC3:** a contributor's real-Mac report is recorded as the `macos-app-install` run log, or the operator accepts its absence or failures as known issues.
- [ ] **AC4:** the operator confirms the flight.
