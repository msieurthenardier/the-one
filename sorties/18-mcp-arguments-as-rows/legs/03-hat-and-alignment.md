# Leg: hat-and-alignment

**Status**: completed
**Flight**: [MCP arguments as rows](../flight.md)

## Objective
The operator walks the new Arguments rows on a scratch instance, one step at a time, and anything they flag is fixed before the sortie lands.

## Context
- Interactive leg: the Flight Director presents one step, the operator performs it and reports, then the next. No Developer runs this leg; a Developer is spawned only for a fix.
- Legs 1 and 2 are implemented, reviewed (two cycles) and committed on the sortie branch before this leg starts. The accessibility review confirmed the change by reading; this walk is the first time a person uses it.
- **Fix or feature.** A look-and-feel fix found here is made inline. A request that adds behaviour gets a scoped design review first. A fix that touches more than the Arguments block (the shared table or field control, another editor) gets a Developer design-review pass before it is built.
- **Contracts the tests rely on** (a change to one is a re-author of tests, done deliberately, not an inline tweak): the testids `mcp-args-field`, `mcp-args-table`, `mcp-args-row`, `mcp-args-input`, `mcp-args-move-up`, `mcp-args-move-down`, `mcp-args-remove`, `mcp-args-add-row-btn`, `mcp-args-hint`; the `data-field="args"` anchor; the button names "Move argument {n} up", "Move argument {n} down", "Remove argument {n}"; the input name "Argument, row {n}"; the hint text; the visible label "+ Add row".
- **Open choices for the operator** (from the flight's HAT list and the reviews):
  1. A server with no arguments shows no rows, only "+ Add row". The alternative is one blank row.
  2. Leading and trailing spaces are trimmed on Save, and an empty-string argument cannot be entered.
  3. The editor has two "+ Add row" buttons. The accessibility reviewer recommends the accessible name "Add row to Arguments" for this one (the visible label stays). It needs one new option on the shared table control, so it is a multi-surface change.
  4. After a Save re-sets the rows, and after a Cancel, where keyboard focus lands (not traced by the accessibility review).

## Inputs
- The sortie branch with legs 1 and 2 committed.
- A scratch dev instance: port 8485, a scratch data directory under the home folder, `THE_ONE_DEV_MODE=true`, started from a scratch working directory (never `make up`, never port 8484, never the default data directory). An API credential minted for that data directory and a one-time handoff link for the operator's browser.
- Two seeded local-command MCP servers: one with arguments (`npx -y` with a package name, a flag, and a path that contains a space), one with none.

## Outputs
- The operator's verdict on each step, recorded in the flight log.
- Any fixes, each tested and reviewed, committed on the sortie branch.

## Acceptance Criteria
- [x] Step 1 [existing server, clean]: opening the seeded server with arguments shows one row per argument in order under the "Arguments" label and its hint; the implicit `-y` is not shown; no column header; rows are full width; "Unsaved changes" is not shown; no error message.
- [x] Step 2 [clean → edited]: typing in a row shows "Unsaved changes"; restoring the text removes it. Adding a blank row does not show it.
- [x] Step 3 [edited → reordered]: Move up and Move down reorder rows; the first row's Move up and the last row's Move down are dimmed and do nothing; after a move, keyboard focus stays on the pressed button (or the row's other move button at an edge).
- [x] Step 4 [reordered → saved]: entering `--flag`, `a`, `--flag`, `a` and `--allow=a,b` as five rows and saving keeps all five in order; blank rows vanish; the form is clean; a reload shows the same rows.
- [x] Step 5 [saved → cancelled]: an edit and a move followed by Cancel return the saved rows in the saved order without the page jumping or reloading.
- [x] Step 6 [empty server]: the server with no arguments, and a new local-command server, show only "+ Add row"; the operator decides open choice 1.
- [x] Step 7 [type switch]: on a new server, rows typed under "Local command" survive a switch to HTTP and back; the block is hidden for HTTP.
- [x] Step 8 [both themes, narrow window]: the block looks right in light and dark and at the minimum supported width (1024px): three buttons on one line, a long argument stays inside its box.
- [x] Step 9 [the other tables]: Environment variables in the same editor, and one other table in the app (a connector's channel map or a secret's values), look and behave as before: no move buttons, their headers visible.
- [x] Step 10 [open choices]: the operator decides open choices 2, 3 and 4.
- [x] Every fix made during the walk has its tests, an independent review, and a green run of the lanes it touches.

## Verification Steps
- Each step is performed by the operator in their browser on the scratch instance and reported back; the Flight Director records the result and any wording the operator objects to.
- Step 4's stored value is also read back by the Flight Director through the scratch instance's `GET /api/mcp-sources/{id}` (`config.args`).
- After any fix: the owning lanes, the static guards and `THE_ONE_TEST_NETNS=1 make test-unit`, then the step is walked again.

## Implementation Guidance

1. **Start the instance** from a scratch working directory with the venv's `the-one serve`, port 8485, a scratch data directory, dev mode on. Record the PID. Mint the credential with `the-one rotate-api-credential` against that data directory. Confirm `/api/live`.
2. **Seed** the two servers through `POST /api/mcp-sources` with the credential. They never need to connect; the walk is about the form.
3. **Hand the operator a link**: mint a one-time handoff URL (`POST /api/session/handoff`) and give it to them; a second browser or a fresh tab needs a second mint.
4. **Walk the steps in order**, one at a time. Static JS and CSS edits are live on the next page load in dev mode; a Python edit needs the instance restarted.
5. **Stop the instance by its recorded PID** when the walk ends, and say so.

## Edge Cases
- **The operator's browser has the page cached from before a fix**: a plain reload is enough in dev mode (asset URLs carry a content hash).
- **The operator asks for one blank row on an empty server**: a behaviour change in the Arguments block only; small, but it changes AC4 of leg 2 and its tests, so it goes through the fix-or-feature call out loud.
- **The operator wants the Add row name changed** (open choice 3): multi-surface (the shared table control gains an option); a Developer design-review pass comes first.

## Files Affected
- `sorties/18-mcp-arguments-as-rows/flight-log.md` - the walk's results
- Source and tests only if a step fails or the operator asks for a change

## Citation Audit
- `CLAUDE.md` "Behavior-test credential convention" - a fresh `serve` data directory has no credential until `the-one rotate-api-credential` is run against it; `POST /api/session/handoff` with the bearer credential returns a one-time URL; `/api/live` needs no credential - verified
- `CLAUDE.md` "UI test apparatus" - port 8485 is the Flight Director's preview instance - verified
- `CLAUDE.md` "Local dev" - in dev mode `index.html` is rebuilt per request and static asset URLs carry a content hash, so a JS or CSS edit needs only a page reload - verified

---

## Post-Completion
Completion steps — status transitions, flight-log update, checking off in the parent flight, and commit — are Flight Control protocol, driven by the execution workflow. Not repeated here.
