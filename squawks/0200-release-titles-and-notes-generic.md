# Squawk 0200: Releases publish with a generic title and bare auto-generated notes

**Status**: open
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-12
**Completed**: —

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

## Verification
*(written at completion)*

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
