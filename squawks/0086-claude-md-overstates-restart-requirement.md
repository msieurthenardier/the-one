# Squawk 0086: CLAUDE.md says a restart is required for JS/CSS changes; it is not

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-09-19
**Completed**: 2026-09-19

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

Corrected CLAUDE.md's "Local dev (host-native)" section: rewrote the
"is required" / "is NOT required" pair, added one new paragraph, and qualified
one clause in the section's opening paragraph. The Pydantic class-definition
note that follows the pair is correct and was left untouched.

1. **"When `make restart` is required"** now says **Python** changes under
   `the_one/` — not "JS, CSS, HTML, Python".

2. **HTML is NOT in the hot set** — the original report and its proposed
   corrective action both lumped HTML in with JS/CSS, and that is wrong.
   `the_one/interfaces/web/static/index.html` is the only HTML file under
   `static/`, and the `/` route does not serve it through the `StaticFiles`
   mount: it serves `_cache_busted_index_html()`
   (`the_one/interfaces/web/app.py`), which is decorated
   `@functools.lru_cache(maxsize=1)`. The file is therefore read from disk
   exactly once per process, and an edit to it **does** need a restart. The
   corrected paragraph names it explicitly as the one static file that behaves
   like Python.

3. **"When `make restart` is NOT required"** now leads with JS and CSS under
   `the_one/interfaces/web/static/` (served by the `StaticFiles` mount, which
   reads from disk per request), and keeps the pre-existing `tests/` clause as
   its second item rather than dropping it.

4. **The section's own intro (CLAUDE.md's "Local dev (host-native)" opening
   paragraph) restated the same overstatement** — "source edits take effect on
   `make restart`". Left as-is it would have contradicted the corrected
   paragraphs three lines below it, so it is now "**Python** source edits take
   effect on `make restart`", with a pointer to the JS/CSS case below. Minimal
   qualification only; nothing else in that paragraph changed.

5. **New paragraph pointing asset staleness at the browser cache.** It states
   that `index.html`'s `/static` refs are busted with `?v={__version__}` — the
   package version, which an edit does not change — so a browser serves its
   cached copy regardless of restarts, names squawk 0085, and gives the two
   real remedies (hard reload; `curl` the asset with the local-API credential).
   It stops short of anything 0085 does not claim: it describes the current
   version-keyed mechanism and its dev-time consequence, and does not describe
   or presume 0085's proposed mtime/content-hash fix.

**Out of scope, noted for follow-up**: `the_one/agents.md` carries the same
overstatement in its own words — "source edits under `./the_one/` take effect on
`make restart`". It is a different file from the one this squawk reports, so it
was left untouched rather than widening the fix. (`agents.md`'s separate
hard-reload-after-restart note is already consistent with the new browser-cache
paragraph.)

## Verification

Measured directly, not inferred from the mount alone. A dedicated dev instance
was started on **port 8487 with a scratch data directory** (never 8484, never
the platformdirs default data directory — the default was printed from
`the_one.config.settings` and confirmed untouched; the scratch directory got its
own freshly minted `api-credential`). All probes were reverted and the instance
stopped; `git status` shows no residue.

1. **Baseline** — `GET /static/js/areas/studio/knowledge-section.js` with the
   local-API credential returned HTTP 200 and a body `cmp`-identical to the
   working-tree file.
2. **JS edit is live with no restart** — appended a marker comment to that file
   and re-fetched it. Same pid, no restart issued: the response contained the
   marker and was again `cmp`-identical to disk. Confirms the report's central
   claim.
3. **`index.html` is NOT live** — appended an HTML comment marker to
   `static/index.html` and re-fetched `GET /`. The marker was present on disk
   and **absent** from the served body, proving the `lru_cache` memoization and
   refuting the "HTML" half of the proposed corrective action.
4. **Cache-bust key confirmed** — the served index carried
   `knowledge-section.js?v=0.8.1`, i.e. the package version, as squawk 0085
   describes.

## Sign-Off

*Verified against `the_one/interfaces/web/app.py` directly — the StaticFiles-per-request vs. lru_cache-memoized-index distinction is accurate, and the restart-required/not-required split in CLAUDE.md now matches actual server behavior. The decision to leave `agents.md`'s parallel overstatement untouched is correctly scoped and logged rather than folded in. Approved.*

**Reviewer**: independent Reviewer agent, turnaround batch 2026-09-19.

> Prior pending note, kept for the record:
>
> *(pending)*
> 
> ## Reporter's Error, Recorded
> 
> This squawk's Corrective Action asked for the docs to say a restart is "**not**
> required for static assets under `the_one/interfaces/web/static/`". That is wrong
> for one file in that directory. `index.html` is not served through the
> `StaticFiles` mount at all — `/` returns `_cache_busted_index_html()`
> (`the_one/interfaces/web/app.py:121-122`), which is decorated
> `@functools.lru_cache(maxsize=1)`, so the file is read from disk exactly **once per
> process** and an edit to it does need a restart. The implementing Developer caught
> it, proved it empirically (marker comment present on disk, absent from the served
> body, same pid), and wrote the narrower true claim: JS and CSS are hot,
> `static/index.html` is not. It is the only `.html` file under `static/`, so JS/CSS
> is exactly the hot set.
> 
> Following this squawk verbatim would have replaced one wrong claim in CLAUDE.md
> with another — which is the same failure this squawk exists to fix, committed by
> the squawk itself. Second instance in this turnaround batch (see 0090's equivalent
> note), and the same lesson both times: **a reporter's proposed corrective action is
> a hypothesis, not an instruction.** The Developer's job includes falsifying it.
