# Squawk 0086: CLAUDE.md says a restart is required for JS/CSS changes; it is not

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-09-19
**Completed**: —

## Report

`CLAUDE.md:61` states:

> **When `make restart` is required**: any change under `the_one/` you want
> reflected in the running `make up` server — JS, CSS, HTML, Python. There is no
> live-reload, so a restart re-imports the source.

The Python half is correct. **The JS/CSS/HTML half is not.** Static assets are
served by `StaticFiles` (`the_one/interfaces/web/app.py:559`), which reads from
disk on each request — they are not snapshotted at import. A JS or CSS edit is
live to the next request with no restart.

The stated reason ("a restart re-imports the source") is what makes the claim
plausible and wrong: re-importing is exactly what static assets never needed.

**The cost is wasted work and misplaced confidence, and it has already been paid
twice.** During Mission 24 Flight 6's HAT the Flight Director restarted the dev
instance and minted fresh handoff links after two separate JS/CSS passes, neither
of which needed it, and planned a third restart before checking. Separately, a
Developer agent with no other source of truth reported at hand-back that the
running instance "still serves the pre-change `knowledge-section.js` and needs a
restart before the next HAT walk" — the served file was already byte-identical to
the working tree. The documentation is now demonstrably propagating the error into
fresh agents that have no way to know better.

There is a second-order effect worth noting for whoever fixes this. Squawk 0085
(asset cache-busting keyed to app version rather than file content) is the *real*
reason a changed asset can fail to appear. While CLAUDE.md attributes staleness to
a missing restart, 0085's browser-cache cause stays masked — the operator's
"I'm not seeing the changes" during this flight was 0085, diagnosed as a restart
problem.

## Evidence

- `CLAUDE.md:61` — the claim, naming JS, CSS, HTML, Python together
- `the_one/interfaces/web/app.py:559` — `app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")`
- Measured on the live 8485 dev instance: after committing `20f9c93`, the process
  had not been restarted (same pid, same start time), yet
  `GET /static/js/areas/studio/knowledge-section.js` returned a body
  byte-identical to the working-tree file (`cmp -s` → identical), including the
  newly added `_relativeItemPath`.

## Corrective Action

*(pending)* Split the claim: a restart is required for **Python** changes under
`the_one/` (including the Pydantic class-definition note already below it), and is
**not** required for static assets under `the_one/interfaces/web/static/`, which
`StaticFiles` reads per request. Point the asset-staleness case at squawk 0085
(browser cache) rather than at the restart, so the real cause is named where
someone hitting it will look.

## Verification

*(pending)* With a `make up` instance running and unrestarted, edit a file under
`the_one/interfaces/web/static/`, then `curl` that asset with the local-API
credential and confirm the response matches the file on disk.

## Sign-Off

*(pending)*
