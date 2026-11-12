# Leg: three-platform-font-check

**Status**: ready
**Flight**: [Visuals on Chat Platforms](../flight.md)

## Objective
The `chart images` doctor gate passes with the same reference width (20463 design units) and the same reference chart size (1280×520) in the packaged Linux, Windows and macOS builds, before any send path is built on the renderer.

## Context
- DD12: the gate means "the same text rendering on every platform". DD4: the width is a property of the SHA-pinned font file, so it must not vary between builds. Flight Adaptation Criteria: if it does vary, divert and investigate the font bundling first.
- Leg 1 landed with:
  - the gate (`_probe_chart_images`);
  - the fonts collected by all three freeze specs (`font_datas`);
  - `chart images: OK` in the Windows `build.ps1` needle lists and in the macOS `checks.sh` notes.
  
  Locally, `the-one doctor` printed `chart images: OK — width 20463 du, layout basic, pillow 13.0.0, freetype 2.13.2`.
- **Apparatus: the three hosted dispatch-only package workflows**, which build from a pushed ref and upload the doctor output as artifacts:
  - `linux-packages.yml`: the container gate suite, with doctor pinned and unpinned per distro and format; evidence artifacts `evidence-{format}-{distro}` with `doctor-pinned.txt` and `doctor-unpinned.txt`.
  - `windows-packages.yml` (`mode=full`): `build.ps1` matches each `"{gate}: OK"` needle; doctor output is in the logs artifact, `doctor-*.txt`.
  - `macos-packages.yml` (`mode=full`): `checks.sh` runs a strict doctor and notes the gate lines.
  
  The flight's original plan listed local Linux container gates and a Windows freeze through `windows_test_copy.py` as alternatives. The hosted workflows cover all three platforms the same way, need no operator at the Windows desktop, and are the recipes the release uses.
- **Prerequisite (deviation from the flight's "commit once" default, recorded in the flight log):** the workflows build a pushed ref. So Leg 1 is reviewed and committed as a checkpoint, and the branch is pushed, before this leg runs. Each push and each dispatch is an outward step confirmed by the operator at the time (`leg-execution.md` "Outward steps": run separately, check `git rev-parse HEAD origin/<branch>`, record run id and head SHA).
- **No code is planned.** If a build fails because the frozen app cannot load the fonts or `PIL._imagingft`, the fix (a `hiddenimports` or datas entry) is a Developer pass inside this leg. It is followed by a re-dispatch of the failing platform only.

## Inputs
- Leg 1 committed on `flight/03-visuals-on-chat-platforms` and pushed to `origin`.
- `gh` authenticated (verified 2026-11-12: `msieurthenardier`, active).
- No other `linux-packages`, `windows-packages` or `macos-packages` run in progress, and no release running (CLAUDE.md: never dispatch a platform workflow during a release).

## Outputs
- Three workflow runs on the pushed head, with their run ids and head SHA recorded in the flight log.
- A table in the flight log with, per platform and package cell, the `chart images:` line: width, layout, Pillow and FreeType versions.

## Acceptance Criteria
- [ ] AC1: `linux-packages.yml` on the pushed head concludes `success`. Every cell's `doctor-pinned.txt` and `doctor-unpinned.txt` has `chart images: OK — width 20463 du, layout basic, …`.
- [ ] AC2: `windows-packages.yml` (`mode=full`) on the pushed head concludes `success`. Its `build.ps1` doctor check passed with the `chart images: OK` needle, and the captured doctor output shows width 20463.
- [ ] AC3: `macos-packages.yml` (`mode=full`) on the pushed head concludes `success`, and the strict doctor output shows `chart images: OK` with width 20463.
- [ ] AC4: the reference chart size is 1280×520 on all three platforms. The probe fails on any other size, so `OK` on all three proves it.
- [ ] AC5: the flight log records each run's id, the head SHA, the `chart images:` line per platform, and any difference in FreeType versions, which is informational.

## Verification Steps
- `gh run list --workflow <file> --branch flight/03-visuals-on-chat-platforms -L 1` for each workflow. Check `gh run view <id> --json conclusion,headSha`.
- `gh run download <id> -D $HOME/m35f3-leg2/<platform>` (outside the repo). Then `grep -r "chart images" $HOME/m35f3-leg2/<platform>`.

## Implementation Guidance
1. Confirm with the operator, then push the checkpoint commit: `git push -u origin flight/03-visuals-on-chat-platforms`. Then check `git rev-parse HEAD origin/flight/03-visuals-on-chat-platforms`.
2. Confirm with the operator, then dispatch each workflow as its own command:
   - `gh workflow run linux-packages.yml --ref flight/03-visuals-on-chat-platforms`
   - `gh workflow run windows-packages.yml --ref flight/03-visuals-on-chat-platforms -f mode=full`
   - `gh workflow run macos-packages.yml --ref flight/03-visuals-on-chat-platforms -f mode=full`
   
   Record each run id and head SHA straight after its dispatch.
3. Wait for completion with a background `gh run watch <id> --exit-status`, not a polling loop. Then download each run's artifacts outside the repo and read the `chart images:` lines.
4. On a failure, read the failing step's log (`gh run view <id> --log-failed`).
   - A font or PIL bundling cause gets a Developer fix in this leg, then a re-dispatch of that platform only.
   - Any other cause is triaged. A pre-existing, unrelated failure is recorded and raised to the operator, never folded in.

## Edge Cases
- **A width other than 20463 on a platform:** divert (flight Adaptation Criteria). Check that the bundled TTF hashes match first: a wrong or missing file in the bundle is the likely cause.
- **FreeType versions differ between platforms:** expected and informational. Only the width and size gate.
- **A hosted runner is unavailable or queued for a long time:** report it to the operator. Do not substitute a different apparatus without their agreement.

## Files Affected
- None planned. A bundling fix, if needed, touches `packaging/{windows,linux,macos}/the-one.spec`.
- The flight log.

## Citation Audit
Checked 2026-11-12 against the Leg 1 working tree.
- `.github/workflows/linux-packages.yml` — `workflow_dispatch` with an optional `version` only; evidence artifacts `evidence-${{ matrix.format }}-${{ matrix.distro }}` (`:219`) — verified
- `.github/workflows/windows-packages.yml` / `macos-packages.yml` — `workflow_dispatch` inputs `version` and `mode` (`full|lifecycle|probe`, default `full`) — verified
- `.github/workflows/windows-packages.yml:243` — copies `doctor-*.txt` into the uploaded logs — verified
- `packaging/linux/checks/gates-inner.sh:143-146` — doctor pinned and unpinned into `$EV/doctor-*.txt` — verified
- `packaging/windows/build.ps1` — `chart images: OK` in both needle lists (Leg 1) — verified by the Leg 1 Developer; to be re-checked by the checkpoint reviewer
- `gh auth status` — logged in, active — verified

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.
