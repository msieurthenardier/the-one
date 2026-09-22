# Squawk 0093: two same-named knowledge bases are indistinguishable in the inventory, before an irreversible delete

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-09-21
**Completed**: —

## Report

Studio's Knowledge inventory renders each knowledge base as a listbox option
showing **only its name**. Two knowledge bases with the same name produce two
pixel-identical rows — no id, no creation date, no folder-path preview, nothing
that tells them apart.

Names are not unique and are not required to be: the create form accepts a
duplicate name without complaint (verified — DD-16's length hint is advisory and
there is no uniqueness constraint at all).

**The hazard is what the operator does next.** Deleting a knowledge base is an
immediate, irreversible, cascading delete — the knowledge base, its registered
folders, every file item, and every chunk. An operator facing two identical rows
has no way to tell which is which from the list, and the only safe path is to
open each candidate and inspect its folders before trusting the delete.

Found during Mission 24 Flight 7's `kb-studio-round-trip` run (2026-09-21),
steps 16-17, which deliberately create a same-named pair to test DD-17. The
Executor had to open **both** options and read the id out of the **URL**
(`#studio/knowledge/<id>`) to identify which one to delete. It got the right one
only because it knew which it had just created — an operator with two
independently-created knowledge bases has no such foreknowledge.

**The backend is already collision-safe; the UI is not.** Flight 6's DD-17 made
the derived tool name carry an unconditional `sha256(kb_id)` discriminator
precisely so same-named knowledge bases stay distinguishable — the run confirmed
two identical names yielding `kb__kb-studio-renamed_5352333b__search` and
`kb__kb-studio-renamed_8f7dd3e0__search`. That treatment never reached the
inventory list.

## Evidence

- `tests/behavior/kb-studio-round-trip/runs/2026-09-21-02-10-21.md` — "Incidental
  findings", item 1; Executor closing summary item 2
- Run observation: inventory rendered two options both reading
  `kb-studio-renamed —`, distinct only by ids `37ddc71d3938` and `dcf61722261b`,
  neither of which appears on the row
- The detail view already displays the registered folder path, so the
  disambiguating data exists one click away and is simply not surfaced in the list

## Disposition

Qualified against the squawk gate: **one coherent item** ✅ (one list row needs a
disambiguator); **no design decisions** ⚠️ *borderline* — which disambiguator to
show (folder path, creation date, id prefix) is a small presentation choice, but
the data is already fetched and the detail view already renders the folder path,
so the minimal fix is discoverable in one read pass; **bounded blast radius** ✅
(one rendering site in `knowledge-section.js`); **verifiable** ✅ (a browser test
creating two same-named knowledge bases and asserting the rows differ).

Logged as a squawk on the strength of the last three. If the implementer finds
the presentation choice needs a real design conversation, that is the escalation
trigger — stop and raise it rather than picking one silently.

## Corrective Action

*(pending)* Surface a disambiguator on the inventory row. The registered folder
path is the strongest candidate — it is what an operator actually reasons about,
it is already displayed in the detail view, and it degrades gracefully (a
knowledge base with no folder registered shows nothing extra). Keep the existing
name as the primary label.

## Verification

*(pending)* A browser test in the `studio` lane: create two knowledge bases with
an identical name, register a different folder on each, assert the two rendered
rows are distinguishable without opening either.

## Sign-Off

*(written at completion)*
