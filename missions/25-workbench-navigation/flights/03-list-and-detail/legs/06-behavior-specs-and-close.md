# Leg: behavior-specs-and-close (6)

**Status**: completed
**Flight**: [List and Detail](../flight.md)

## Objective

Close Flight 3: prove that the retired surfaces are gone for good, bring every behavior
spec in line with the list-and-detail shell, run the flight-close gates, and leave the
tree ready for the flight-end review and the single flight commit (DD12; the flight's
Post-Flight checklist).

The work is split by **who may write it**, for the Witnessed pattern's independence:

- **The Developer** (this leg's implementation) does the code-side close:
  - the guard ending its allow-list;
  - mechanical text updates in the behavior specs that are **not** run at flight close;
  - a docs consistency pass;
  - the full gates.
- **The Flight Director** authors the new `list-and-detail` spec and updates the six
  specs that **are** run at flight close. The behavior runs then happen after the flight
  commit, as in Flight 2.

The agent that built the surfaces does not write the acceptance tests run against them.

## Context

- **Flight decisions:**
  - DD12: specs and apparatus. It lists the specs to update and run, and the CDP-driven
    Chromium fallback.
  - DD14: the checkpoint package, which the Flight Director builds after the flight
    commit.
  - The DD2 refinement: the breadcrumb's last segment links to its root.
- **Legs 1–5b** are implemented in the working tree, uncommitted. Read every leg entry
  in the flight log, especially the "Deviations" lists and the items flagged for the
  flight-end review.
- **The retired-selector guard** is `tests/test_nav_helper.py`, which holds
  `RETIRED_SELECTORS` and `RETIRED_SELECTOR_ALLOWLIST`. Leg 5b left the allow-list
  empty (`frozenset()`).
- **Ground truth after leg 5b** (Flight Director, 2026-10-02):
  - **A new settings-lane glob.** `scripts/run-tests.sh` has a `test_flow_settings_*`
    pattern (`test_flow_settings_items.py`). The lane-union check must cover it.
  - **Squawks logged during the flight:** 0110 (pre-existing), 0113, 0114 and 0115. Leave
    them open, and don't fix them here.
  - **The README** screenshot alt text still describes the old grid. Fix the text only,
    not the image (the docs pass).
  - **Left for the flight-end Accessibility Reviewer, not this leg:**
    - two `h1`s on a Settings item page;
    - the "Settings" `nav` inside the aside also labelled "Settings";
    - the `nameSuffix` comma spacing;
    - leg 4b's focus after Continue.
- **Behavior specs naming retired surfaces.** The Flight Director's grep on 2026-10-02
  counted hits per spec. Many hits are generic words ("back", "grid"), so re-grep and
  judge each one.
  - **Run at close, so the Flight Director updates them:** `system-provider-config` 20,
    `studio-agent-crud` 15, `workbench-navigation` 13, `shell-navigation-smoke` 7,
    `kb-studio-round-trip` 4. (Leg 5a already updated the text of `workbench-navigation`
    and `shell-navigation-smoke` for Settings.)
  - **Not run at close, so the Developer updates them:**
    - `save-preserves-config` 5, `kb-agent-query-round-trip` 4;
    - `agent-governance-and-search`, `stub-connector-round-trip`,
      `extended-thinking-tool-turn`, `anthropic-plan-signin`, `discord-live-round-trip`,
      `pty-session-containment`, `tool-sandbox-containment`, `windows-pty-parity`, 2 each;
    - `studio-smoke`, `chat-roundtrip`, `anthropic-plan-chat-parity`, `vision-round-trip`,
      `tool-sandbox-box-isolation`, `kb-folder-index-round-trip`,
      `gemma-tool-use-recovery`, `directory-lookup-send`,
      `agent-self-revision-propagation`, 1 each.

## Outputs

**1. The guard ends its allow-list.**
- `RETIRED_SELECTOR_ALLOWLIST` is empty.
- **Remove the mechanism or pin it.** If nothing else uses it, delete the allow-list
  mechanism and make the guard unconditional. Otherwise keep it with a test asserting it
  stays empty.
- `RETIRED_SELECTORS` keeps every retired id: `entity-tile`, `section-nav-item`, every
  `back-*-btn` and the three `new-*-btn`. A retired id cannot come back.

**2. Mechanical spec updates** (the specs not run at close).
- For each hit, change a reference to a retired surface into the current one:
  - "the tile" → "the row in the Agents list";
  - "New Agent" → "New";
  - `#admin/…` and `#studio/…` → the destination routes;
  - "Back" → the breadcrumb link or the rail;
  - "LLM Providers" → "Providers";
  - "General" (Settings) → "Appearance", "Prompts" or "Encryption";
  - "Settings sections" → the Settings nav.
- **Generic "back" and "grid" words** that are not a retired surface stay.
- **Don't change a step's intent.** If a spec's steps no longer make sense against the
  new shell, leave a `> **M25 F3:** …` note under the step and list the spec in the
  flight log for the Flight Director. Don't rewrite its assertions.
- **Don't touch `Last Run`.** These specs are not run in this flight. Add one line under
  each spec's header: `**Updated**: 2026-10-02 (M25 F3 surface rename; not re-run)`.

**3. Docs consistency pass.** Reconcile, and report each mismatch you fix:
- `CLAUDE.md`: the destination router line (routes for all four destinations, `~new`),
  App shell, `App.store`, the `_lists.py` paragraph, and the lane lists (the explicit
  `library_pat` file list);
- `the_one/agents.md`: the list and detail sections for each destination, the invalidation
  map, create routes, retired surfaces, and the guard;
- `docs/ui-testid-registry.md`: every testid added in legs 1–5b is registered, and every
  retired one is in the "Retired testids" table;
- `docs/ui-control-inventory.md`: `listPane` (options and methods), `navGroups`, `menu`
  usage, and the section-nav row removed;
- the flight's Post-Flight checklist items that docs satisfy.

**4. Squawk 0101.** Confirm its Corrective Action and Verification are written. Set it
to `completed`, with Completed `2026-10-02` and a one-line sign-off naming leg 4a. The
flight commit carries it.

**5. Flight-close gates** (the flight's Verification section), on the final tree:
- `make lint`, `ruff format --check`, `make test-unit`;
- the static guards (`test_ui_guards`, `test_token_definitions`,
  `test_design_tokens_a11y`, `test_store_static`, `test_ui_control_inventory`,
  `test_nav_helper`, `test_index_asset_cache_busting`);
- every `test_ui_*` in both engines with `THE_ONE_REQUIRE_WEBKIT=1`;
- all five lanes, **one at a time**, with `THE_ONE_TEST_NETNS=1` (`TEST_TIMEOUT=3600` for
  shared);
- a **lane-union check**: the five lanes' collected test count equals
  `-m browser tests/browser/`'s, with no file in two lanes (`--collect-only -q`);
- the **WebKitGTK probe** at `#agents`, `#library/knowledge` and `#settings/appearance`,
  in both themes.
  - Use root selectors that wait for content (legs 3–4b found that a bare `#main-content`
    scans before the editor mounts).
  - Also probe one open item per destination with an editor-scoped selector.

## Acceptance Criteria

- [ ] **AC1 — Guard.** The allow-list is empty, or its mechanism is removed, and a test
  pins it. `RETIRED_SELECTORS` is complete. `make test-unit` is green.
- [ ] **AC2 — Specs.**
  - Every non-close spec hit is updated or noted, with the `**Updated**` line.
  - No spec run at close was edited by this leg; leg 5a's text edits are allowed.
  - The flight log lists each spec touched and each one left with a note.
- [ ] **AC3 — Docs.** The consistency pass is done, and its fixes are listed in the
  flight log.
- [ ] **AC4 — Squawk 0101** is `completed`, with sign-off.
- [ ] **AC5 — Gates.** Every gate in Outputs §5 is green, recorded with pass and skip
  counts and durations, including the lane-union check and the probe table.

## Edge Cases

- **A test in the lanes fails because of an interaction between legs** (for example a
  leg 5b change to a test that leg 4a touched). Fix it in this leg. Classify it in the
  flight log as a real defect or a test precondition, as earlier legs did.
- **A spec hit needs a design decision**, such as a step that relies on Back to close an
  item where no single equivalent exists. Leave the note, and don't decide it.
- **Pixel baselines.** They are local and gitignored. Regenerate them with
  `--snapshot-update` only if you run `-m pixel`; that run is optional and not a gate.

## Files Affected

- `tests/test_nav_helper.py`
- `tests/behavior/*.md`: the non-close specs only
- `CLAUDE.md`, `the_one/agents.md`, `docs/ui-testid-registry.md`,
  `docs/ui-control-inventory.md`
- `squawks/0101-kb-create-lands-on-grid-not-detail.md`
- any test or source file a gate failure requires, recorded in the flight log
- `missions/25-workbench-navigation/flights/03-list-and-detail/flight-log.md`

## After this leg (Flight Director, not the Developer)

1. **Flight-end review.** A Reviewer and an Accessibility Reviewer, with fixes looped
   until both confirm.
2. **Spec authoring.** `list-and-detail` (new), plus the six run-at-close specs updated
   against the final tree.
3. **The flight commit** (squawk 0101 closed in it), then a rebase onto `main` with
   `git rebase --onto origin/main e6a3a90`. PR #218 was squash-merged as `560aa9b`, whose
   tree equals `e6a3a90`.
4. **Behavior runs** (DD12) on the CDP Chromium fallback: `list-and-detail` in both
   themes, `workbench-navigation`, `shell-navigation-smoke`, `studio-agent-crud`,
   `system-provider-config` and `kb-studio-round-trip`. The run logs go in a follow-up
   commit.
5. **The PR.**
6. **The DD14 operator checkpoint package**, then a **STOP** for the operator's go.

## Citation Audit

The Flight Director wrote this on 2026-10-02 after legs 1–4b landed, with 5a in
implementation. The per-spec hit counts come from a grep the same day. The Developer
re-greps at leg start, after 5b lands.

---

## Post-Completion

Status transitions, the flight-log update, checking off in the parent flight, and the
commit are Flight Control protocol, driven by the execution workflow. They are not
repeated here.
