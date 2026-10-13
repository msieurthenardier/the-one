# Squawk 0200: Releases publish with a generic title and bare auto-generated notes

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-12
**Completed**: 2026-10-13

## Report
Every release since v0.11.0 (v0.11.0 through v0.11.4) is titled "vX.Y.Z — Windows installer". Each body is only GitHub's auto-generated list of merged PRs. An operator can't tell what changed in a release, or why to upgrade.

v0.10.5 shows the intended standard: the title "Windows shell sessions", a one-line summary, Fixed, and Notes (known issues, upgrade). That release was written by hand before the installer workflow ran, and the workflow only creates a release when none exists.

## Evidence
- `.github/workflows/windows-installer.yml`, step "Publish GitHub Release with installer": `gh release create "$TAG" --title "$TAG — Windows installer" --generate-notes`. It runs only when `gh release view "$TAG"` fails, then uploads the `.exe` with `--clobber`.
- `gh release list`: v0.11.0 through v0.11.4 all have the generic title. v0.10.5's title is "Windows shell sessions" and it has hand-written notes.
- Release commits carry no notes. For example, `chore: release 0.11.4 (#272)` says only "Patch release 0.11.4: sortie 03 — Claude Plan (Token) provider (#271)."

## Proposed Corrective Action
- **Notes in the release PR.** The release PR adds the release notes as a committed file, with a short title line and v0.10.5's shape: summary, Added / Changed / Fixed, and Notes. The default is per-version files at `docs/releases/vX.Y.Z.md`. The operator may choose one `CHANGELOG.md` instead, deciding at completion time.
- **Workflow change.** The publish step uses the file's first line as `--title` and the rest as `--notes-file`. It also `gh release edit`s an existing release that still carries the generic title. With no notes file, it falls back to today's behaviour, so a missing file never fails a release.
- **Backfill.** Edit v0.11.0 through v0.11.4 with `gh release edit`, using notes drafted from what each release shipped. These are public pages, so the operator approves the drafted text before any edit.

## Corrective Action
Operator decision (2026-10-13): notes live in one file per version, `docs/releases/vX.Y.Z.md`, not `CHANGELOG.md`.
- `docs/releases/README.md` defines the format: first line `# <release title>`, the rest is the GitHub Markdown body in v0.10.5's shape. The release PR adds the file with the version bump.
- `scripts/release_notes.py` (stdlib only) splits a file into title and body (`--title` prints the title, `--title-out PATH` and `--body-out PATH` write them as UTF-8); a missing `# ` line or empty body exits 1.
- `.github/workflows/windows-installer.yml`, step "Publish GitHub Release with installer": with `docs/releases/$TAG.md` present, a missing release is created with `--title` and `--notes-file`; a release still titled `"$TAG — Windows installer"` is `gh release edit`ed to match; any other existing title is left alone. With no file it keeps the old create-with-`--generate-notes` behaviour, so a missing file never fails a release. Review fixes: the title travels through a UTF-8 file (`--title-out`, read with `tr -d '\r'`), never stdout, because the Windows runner encodes piped stdout as cp1252 and would corrupt the em dash (`PYTHONUTF8=1` also set). A malformed file (script exits non-zero) logs `::warning::` and takes the no-file path (generic title, `--generate-notes`; an existing release is left alone); the upload still runs. v0.11.1's intro now says "Patch release". `gh release upload --clobber` is unchanged. Comment block updated.
- `docs/releases/v0.11.5.md` matches the hand-published v0.11.5 release (compared against `gh release view`).
- Backfill drafts `docs/releases/v0.11.0.md` to `v0.11.4.md` are written from the merged PRs and mission artifacts. The `gh release edit` of the five published releases is pending operator approval of the drafts and will be applied by the Flight Director.

## Verification
- `.venv/bin/python -m pytest tests/test_release_notes.py -x -q --timeout 30`: 18 passed. It parses every `docs/releases/v*.md` (title starts with its own version, body non-empty), covers the splitter (blank-line trimming, `# ` stripping, CRLF, missing marker and empty body errors, CLI), and pins the workflow step (`docs/releases/`, `scripts/release_notes.py`, `--title-out` with no stdout title capture, the `::warning::` fallback, `PYTHONUTF8`, `--notes-file`, `gh release edit`, the `--generate-notes` fallback, the `--clobber` upload).
- `--title-out` writes the exact UTF-8 bytes of an em-dash title (tested). Workflow YAML parses; the extracted step passes `bash -n`. Ruff check and format clean after the fixes.
- `make test-unit`: 6245 passed, 12 skipped (the expected count).
- `ruff check the_one/ tests/ scripts/`: clean. `ruff format --check`: 586 files already formatted.
- Not exercised live: the `gh release create/edit` branches run only on a tag push on the Windows runner.

**Backfill applied (Flight Director, 2026-10-13, operator-approved drafts):** `gh release edit` set the title and notes of v0.11.0 to v0.11.4 from `docs/releases/`, after a guard confirmed each still had the generic title. The new titles are:
- "v0.11.0 — Agent rules and notes"
- "v0.11.1 — Agents know the date and time"
- "v0.11.2 — Time zone and housekeeping fixes"
- "v0.11.3 — Model providers move to Library"
- "v0.11.4 — Claude Plan (Token) provider"

Installer assets are unchanged. v0.11.5 was published by hand with these notes before this squawk, and its file matches.

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet), two cycles.
- **Cycle 1** found one blocking issue: the title was taken from Python's stdout on the Windows runner, where cp1252 would corrupt the em dash. It also raised one non-blocking point about a malformed notes file. Both were fixed.
- **Cycle 2** gave `[HANDOFF:confirmed]`.
- **Accepted minor:** in the edit-if-generic branch, `gh release view` is unguarded. A transient `gh` failure there would stop the step before the upload. This is low risk, because the release was just confirmed to exist.

**Verdict**: confirmed
**Commit**: the `squawk/0200` commit, PR #279
