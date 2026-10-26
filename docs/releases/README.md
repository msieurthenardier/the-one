# Release notes

One file per release, named for its tag: `vX.Y.Z.md`.

## Format

- The first line is `# <release title>`: the title as it should appear on GitHub, for example `# v0.11.5 — MCP servers on the newest protocol`. Start it with the version.
- Everything after the first line (leading blank lines are trimmed) is the release body, in GitHub Markdown.
- Follow the shape of [v0.10.5](https://github.com/msieurthenardier/the-one/releases/tag/v0.10.5): a one-line summary, then only the sections that have content (Added, Changed, Fixed), then Notes with any upgrade advice (schema changes, anything to reconfigure).
- Write for the person using the app: what changed for them, not internal design ids.

## How it is used

The release PR adds `docs/releases/vX.Y.Z.md` alongside the version bump. When the tag is pushed, the "Publish the GitHub release" step of the `publish` job in `.github/workflows/release.yml` splits the file with `scripts/release_notes.py`:

- If the release does not exist, it is created with the file's title and body.
- If the release exists and still has the generic `vX.Y.Z — Windows installer` title, its title and body are replaced from the file.
- A release that already has a different title (for example one written by hand) is left alone.
- If the file is missing, the old behaviour applies: a generic title and auto-generated notes. A missing or malformed file never fails a release; a malformed one (no `# ` first line, empty body) logs a warning and takes the same fallback.

The installer is then uploaded as before.
