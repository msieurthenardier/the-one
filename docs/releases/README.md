# Release notes

One file per release, named for its tag: `vX.Y.Z.md`.

## Format

- The first line is `# <release title>`: the title as it should appear on GitHub, for example `# v0.11.5 — MCP servers on the newest protocol`. Start it with the version.
- Everything after the first line (leading blank lines are trimmed) is the release body, in GitHub Markdown.
- Follow the shape of [v0.10.5](https://github.com/msieurthenardier/the-one/releases/tag/v0.10.5): a one-line summary, then only the sections that have content (Added, Changed, Fixed), then Notes with any upgrade advice (schema changes, anything to reconfigure).
- Write for the person using the app: what changed for them, not internal design ids.

## How it is used

The release PR adds `docs/releases/vX.Y.Z.md` alongside the version bump (`the_one/__init__.py` is the only place the version lives). Pushing the tag `vX.Y.Z` starts `.github/workflows/release.yml`, which runs in this order:

1. **audit**: the release-closure `pip-audit`; a finding stops the release before any build time is spent.
2. **version**: `scripts/release_check.py` requires the tag to equal `__version__`, a final release (no `.devN`), and the tagged commit to be on `main`.
3. **windows, linux, macos**: the three reusable package workflows build at that version.
4. **publish**: `scripts/release_assets.py` selects exactly the four packages (`the-one-setup-<V>.exe`, `GleepGlorp_AI-<V>-x86_64.AppImage`, `gleepglorp-ai_<V>_amd64.deb`, `GleepGlorp_AI-<V>-arm64.dmg`) and writes `SHA256SUMS`; a missing or extra file fails the job. The release is created as a **draft**, all five files are uploaded, and only then is it published, so a partial upload is never visible. The "Publish the GitHub release" step splits `docs/releases/vX.Y.Z.md` with `scripts/release_notes.py`:

- If the release does not exist, a draft is created with the file's title and body.
- If a draft already exists (a re-run after a partial publish), its title and body are replaced from the file, the files are re-uploaded with `--clobber`, and it is published.
- If the release is already published, its title and notes are never changed; the files are only re-uploaded with `--clobber`.
- If the file is missing, the title is the tag and the notes are auto-generated. A missing or malformed file never fails a release; a malformed one (no `# ` first line, empty body) logs a warning and takes the same fallback.

A `workflow_dispatch` of `release.yml` is a dry run: it builds the chosen platforms at the given `.devN` version, uploads the packages as Actions artifacts and publishes nothing.
