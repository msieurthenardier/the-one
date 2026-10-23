# Leg: flight-hat

**Status**: ready
**Flight**: [Knowledge and connectors on the library](../flight.md)

## Objective
The operator walks the Library's knowledge-base and connector editors on a dedicated dev instance, in both themes. The walk confirms that:
- both editors on the library look as they did, apart from the DD7 changes and the HAT items below;
- the DD8 defects are fixed;
- the operator answers the agent editor's Knowledge tab label question;
- the before and after capture set is approved (the mission's capture criterion for this flight).

## Context
- **Flight decisions:** DD5 (mount once, patch in place, the token's masked round-trip), DD6 (canonical forms), DD7 (the approved visible changes 1-10 and the ledger), DD8 (the defects).
- **Captures:**
  - before: `$HOME/.cache/the-one-ui-capture/m31-f3-before/` (leg 01);
  - after: `$HOME/.cache/the-one-ui-capture/m31-f3-after/` (leg 09). Every visible difference there maps to a ledger row.
- **The HAT list, from the flight log's completed ledger (leg 09).** The operator approves or changes each:
  1. The knowledge-base header's Cancel and Create/Save buttons sit about 8px further in from the right edge (05a, found at leg 09's capture compare).
  2. The "Loading knowledge base…" and failure lines lost the old 20px vertical padding and body-size text (05a).
  3. The re-index scope hint now sits under the "Status" title, above the counts (05b).
  4. Folder panel paths: a long path ellipsises instead of breaking, has no medium weight, and the summary gains the library focus ring. Check in both themes (06a).
  5. The item-menu trigger is a ghost `more` icon button where it was a bordered "⋯" text button. Compare the row height and the trigger in both themes (06b).
  6. A menu opened on the last "Other items" row may extend the scroll area. There is no flipping (06b).
  7. **Question:** the agent editor's Knowledge tab label stays "Knowledge", or becomes "Knowledge bases" to match the Library group and the router (08, DD7-3, squawk 0192).
- **The approved changes the walk confirms (DD7):**
  - 1: the connector's Enabled library switch;
  - 2: the search × button;
  - 3: the "Knowledge bases" announcement;
  - 4: the masked token with the reveal eye, re-masked after Save;
  - 5: the danger zones;
  - 6: the doctor and pairing status lines;
  - 7: the pairing code copy field;
  - 8: the channel-map table;
  - 9: the locked and invalid chips on the agent Tools tab;
  - 10: the connector header status line.
- **The defect fixes the walk confirms (DD8):**
  - 1: the channel map keeps typed values;
  - 2: one connector per Create;
  - 3: the doctor on a non-OK response;
  - 4: the poll no longer steals focus;
  - 5: the panel and search races, and focus on the panel heading;
  - 7: Ctrl K with a menu open (it did not reproduce; the test is kept as a pin).
- **Fix-vs-feature gate:** a look-and-feel fix rides inline. New behaviour goes through a scoped design review first. A change that spans more than one surface gets a quick Developer design pass before the fix. A change to item 7's label touches the agent editor and its tests, so it gets a Developer design pass.

## Inputs
- The flight is committed on `flight/03-knowledge-and-connectors-on-the-library`, and the draft PR is open.
- A dev instance:
  - port 8486 or higher (never 8484, 8485 or 8491);
  - a scratch data dir under `$HOME`;
  - started from a scratch cwd;
  - `THE_ONE_DEV_MODE=true` and `THE_ONE_STUB_TEST_ENDPOINT=1`, so the stub connector type is available.
- Seeded with:
  - a mock provider;
  - agent A, attached to the knowledge base;
  - a knowledge base "HAT notes" with two registered folders: a short one, and one with a long nested path (over 80 characters) holding enough text files that the "Other items" panel has several rows;
  - a stub connector, with its default agent A and two channel-map rows.

## HAT steps (state transitions)
1. **[fresh] Open the dev instance** through its handoff URL and go to Library.
   - The list shows the groups Model providers, Knowledge bases, MCP servers and Connectors, each once (squawk 0191).
   - Open "HAT notes". The breadcrumb reads "Library / Knowledge bases". The page title and the announcement name "Knowledge bases" (DD7-3).
   - No error messages.
2. **[kb-create] Add › Knowledge base.**
   - The form header shows Cancel and Create (item 1, the inset).
   - Create with an empty name: the field error appears.
   - Fill a name and Create. The new knowledge base opens, and focus is on its folder-path input.
   - Keep this one for step 9.
3. **[kb-detail] Open "HAT notes".**
   - The loading line flashes briefly (item 2).
   - Expand a folder panel, run a search, then edit the description: the unsaved caption appears.
   - Revert the edit by hand: the caption clears and Save disables (value-model dirty, DD5).
   - Edit again and Save. Patched in place, so:
     - the expanded panel, the search results and the scroll position survive;
     - focus returns to the title.
4. **[kb-status] The Status section.**
   - The scope hint sits under the title, above the counts (item 3).
   - Re-index (changed): the counts move, and the chips and lines update without flicker.
5. **[kb-folders] The folder panels.**
   - A long path ellipsises, and the summary's focus ring shows on Tab (item 4).
   - The `status:` and `watch:` meta chips sit beside the path. A standalone item shows the warning chip (soft fill and border).
   - Add a folder path that does not exist: the field error appears, tied to the input.
   - Delete the short folder: it arms on the summary, then commits. Focus moves to the Add-folder input.
6. **[kb-items] The item menu and the inspect panels.**
   - Each file row has the ghost `more` trigger; compare the row height (item 5).
   - Open the menu on the last "Other items" row (item 6).
   - Arrow keys move between items, and Escape returns focus to the trigger.
   - Choose "View chunks": the chunks panel opens, and focus is on its heading (DD8-5). "View source" does the same.
   - With a menu open, Ctrl K opens Jump to, and the arrows and Escape act on the palette (DD8-7).
7. **[kb-poll] Re-index (all), then Tab to a row's menu trigger and wait through a few poll ticks.**
   - Focus stays on the trigger, and an open menu stays open (DD8-4).
8. **[kb-search] Search.**
   - Type a query, then Search: results show.
   - × clears the query and the results, and focus stays in the field (DD7-2).
   - Type again and press Escape: it clears.
   - A query with no hits shows "No results."
9. **[kb-danger] On the knowledge base made in step 2, Delete Knowledge Base.**
   - The trash icon arms to its confirm state, then commits, and the list drops the row (DD7-5).
10. **[connector] Open the stub connector.**
    - The Enabled row is the library switch with its label beside it (DD7-1). Tab reaches it, and Space toggles it.
    - The token is masked, with the reveal eye (DD7-4). Type a new value and reveal it. Save: the field shows the mask again, with the reveal off.
    - Type a change and revert it: clean (DD5).
    - The header status line reads the connection state (DD7-10).
    - Run doctor: the button is disabled while it runs, then a status line shows the result (DD7-6, from the flight-review fix pass).
    - Generate pairing code: the code is in a read-only field, and "Copy pairing code" shows "Copied" (DD7-7).
11. **[channel-map] The channel-map table** (DD7-8, DD8-1).
    - It has column labels and a trash remove button on each row.
    - Edit row 1's agent, add a row, then remove row 2: row 1 keeps the typed value. Save.
    - Edit row 1 again, add a row, then Save a second time: the newest value is stored. Reload to check.
12. **[connector-create] Add › Connector (stub).**
    - Fill it and double-click Create: exactly one connector appears in the list (DD8-2).
    - Then delete it from its danger zone: one arm, then the commit (DD7-5).
13. **[agent-tools] Open agent A's Tools tab** (DD7-9).
    - Locked chips have the library fill.
    - Make a chip list invalid, if the editor allows it: the red border appears.
14. **[agent-knowledge] Open agent A's Knowledge tab: item 7.** The operator chooses the label.
15. **[theme] Switch to the other theme** (Settings › Appearance) and take a quick look at steps 5, 6, 10 and 11. Nothing reads wrong.
16. **[captures] Review the before and after set** side by side. On request, the Flight Director can publish a private comparison page. Approve the set, or name each difference to change.

## Acceptance Criteria
- [ ] Every step passes, or each failure is fixed and re-verified, with the fixes recorded in the flight log.
- [ ] HAT items 1-7 are approved or changed by the operator.
- [ ] The before and after capture set is approved (the mission's capture criterion for this flight).

## Edge Cases
- **Step 7 needs indexing in progress.** A re-index (all) of the larger folder gives a few seconds of ticks. If it finishes too fast, the Flight Director adds files to the folder on disk, and the watcher picks them up.
- **Step 10's doctor and probe on a stub connector** report the stub's own result. A non-OK doctor (DD8-3) is pinned by tests, and the live walk does not force one.
- **A fix that touches other surfaces:** route it through a Developer design pass first.

## Citation Audit
- The steps come from:
  - the flight log's "Visible-differences ledger" rows 01-08 and its "Completed visible-differences ledger (leg 09)";
  - flight DD7 items 1-10 and DD8 items 1-8.
- Checked on 2026-10-23 against the landed code:
  - `connector-editor.js` shows pairing in edit mode only (`if (!isCreate)`), so step 10 uses the saved stub connector;
  - the stub plugin (`the_one/connectors/stub.py`) implements `doctor`.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off in the parent flight, and the commit) are Flight Control protocol, driven by the execution workflow. They are not repeated here.
