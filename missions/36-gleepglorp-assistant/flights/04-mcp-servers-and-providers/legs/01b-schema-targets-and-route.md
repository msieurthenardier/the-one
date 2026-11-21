# Leg: 01b-schema-targets-and-route

**Status**: completed
**Flight**: [MCP servers and model providers](../flight.md)

## Objective

This leg prepares the lower layers for the new kinds. The registered kinds stay agent, rule and
routine. It makes proposals and fills able to:
- store any kind;
- carry a `target_id`.

It also:
- gives GleepGlorp MCP server and provider ids in its reads;
- adds the open page's route to the page line (hidden from the operator's chip);
- gives the GleepGlorp browser tests their own lane.

## Context

- **Flight decisions covered:**
  - DD4 (schema v56);
  - DD5 (ids; the internal `resolve_target`);
  - DD6 (the route in the page line);
  - DD11, server half, cut down to what is truly common;
  - DD14 (the `gleepglorp` lane);
  - the `db/schema.py` part of squawk 0398.
- **Depends on Leg 1a** (landed, uncommitted): the `kinds/` registry, `Kind` (a frozen
  dataclass in `kinds/base.py`), `kinds.get`, `kinds.FILLABLE` and `FieldSpec.path`. The flight
  log's Leg 1a entry records what moved where.
- **Decisions made at this leg's design review (FD, 2026-11-21):**
  - **The `target` tool parameter moves to Leg 4,** where the first id-targeted kind uses it.
    - Adding it now would change both tools' parameter schemas (platform prompt text) with no
      consumer, and with no description telling the model what it does.
    - This leg adds only the internal `Kind.resolve_target` and `kinds.target_key` for
      id-targeted kinds.
  - **The operator's chip hides the route.** The stored `page.line` carries the route for the
    model. The transcript chip (`addPageChip` / `App.ui.message.context`) strips a trailing
    ` (#…)` suffix for display.
    - So the existing chip assertions (`tests/browser/test_flow_gleepglorp_drawer_chat.py`
      ~:636, :673, :715 and :776) pass unedited, which pins the strip.
    - The drawer's "Looking at" line is built client-side from the descriptor and is
      unaffected.
  - **AUTOINCREMENT high-water marks are kept.** Proposal ids appear in chat text
    ("Proposal N"), so the rebuild copies `sqlite_sequence.seq` for both tables.
  - **The shared store base is cut down** to the pieces that really are common (AC6). Status
    transitions stay per store.
  - **The `gleepglorp` lane's provisional budget is 360 s.**
  - **The `chat` alias keeps its pattern** (`chats_pat`, `test_flow_chat*`), so it still
    expands the two moved chat files. Its pin becomes chats ∪ chats-transcript ∪ chats-widgets
    ∪ those two files.

## Inputs

- Leg 1a landed (uncommitted on the branch).
- `db/schema.py` `CURRENT_VERSION = 55`; the v54 (`gleepglorp_proposals`) and v55
  (`gleepglorp_fills`) blocks; the `agent_revisions` `PRAGMA table_info` guard (~:2500) as a
  shape-detection precedent.
- `gleepglorp/proposals/store.py`, `fill/store.py`, the two `events.py` modules, `page.py`,
  `view_core.py`, `view_mcp.py`, `view_library.py`, `scripts/run-tests.sh`, the chat chip JS.

## Outputs

- **Schema v56.**
  - `gleepglorp_proposals` is rebuilt with no kind CHECK.
  - `gleepglorp_fills` is rebuilt with `agent_name` nullable and `target_id TEXT` after
    `agent_name`.
  - Both keep every row, their indexes, their other CHECKs and defaults, and their
    AUTOINCREMENT high-water mark.
  - `CURRENT_VERSION = 56`.
- **Stores.**
  - The proposal store refuses a kind `kinds.get` does not know.
  - The fill store refuses kinds not in `kinds.FILLABLE`, and stores and returns `target_id`.
  - Both use a small shared module for their common pieces.
- **Types.** `Normalized.agent_name`, `NewFill.agent_name` and `Fill.agent_name` are
  `str | None`.
- **`Kind.resolve_target`** is an optional member (`None` by default), set for agent. There is
  also `kinds.target_key(kind, action, target_id, name)` for id-targeted kinds.
- **Reads.** MCP server and provider reads include `id`, and `read_app_config(name=...)` matches
  an id before a name.
- **The page line** carries the route; the chip strips it for display. The eval scenario page
  lines match.
- **The `gleepglorp` lane.**
- **Docs.**

## Acceptance Criteria

- [ ] **AC1. v56 on a fresh database.**
  - The fresh path runs v54 and v55, then v56, which rebuilds the two empty tables.
  - `gleepglorp_proposals` has no CHECK on `kind`. It keeps `CHECK (action IN ('create',
    'change'))`, the status CHECK and `status DEFAULT 'pending'`.
  - `gleepglorp_fills` has `agent_name` nullable and `target_id` after `agent_name`. It keeps
    the action CHECK, the status CHECK and `status DEFAULT 'sent'`.
  - All four indexes exist: `idx_gleepglorp_proposals_session`, `_proposals_agent`,
    `_fills_session` and `_fills_agent`.
  - `CURRENT_VERSION == 56`.
- [ ] **AC2. v55 → v56 keeps rows and ids.**
  - Build the v55 shape by hand, recreating the old-shape tables and rewinding the version as
    `TestSchemaV55` does; the session template is v56 and has no v55 path.
  - Fill it with proposals of every status and kind, and fills of every status, then delete the
    top row of each table so `sqlite_sequence` is above `MAX(id)`.
  - After migrating to v56: every column of every row is kept, fills have `target_id NULL`, and
    the next insert into each table gets an id above the old high-water mark.
- [ ] **AC3. Replay-safe, per table.**
  - Each table's rebuild runs only if that table is not already v56-shaped. Two small named
    helpers decide:
    - `_proposals_has_kind_check`: `sqlite_master.sql` contains `CHECK (kind IN`;
    - `_fills_has_target_id`: `PRAGMA table_info`.
  - Rewinding the versions ≥ 56 (and ≥ 54, as `TestSchemaV54` does) on a v56 database and
    re-running `ensure_schema` keeps every row and keeps a `target_id` value set after v56.
  - A test covers each.
- [ ] **AC4. The ceremony.** It follows the v33/v44 provider-type ceremony (`the_one/agents.md`
  "Provider type extension checklist", item 5):
  - `executescript` with `PRAGMA foreign_keys=OFF` … `PRAGMA foreign_keys=ON`;
  - a `DROP TABLE IF EXISTS <t>_new` prelude;
  - every column copied by name;
  - the indexes recreated;
  - the `sqlite_sequence` row carried over;
  - `INSERT OR IGNORE INTO schema_version` last.

  The two tables are checked and rebuilt independently, so a half-done table never blocks the
  other.
- [ ] **AC5. Pins updated, none weakened.**
  - **Every** `== 55` version pin in `tests/test_db_migration.py` (grep it; there are about 16)
    and `tests/test_gleepglorp_fill_store.py:58` becomes 56.
  - The fills column-list pin gains `target_id`.
  - `TestSchemaV54.test_check_constraints_refuse_bad_values` (~:6912) is inverted for `kind`.
    It is renamed to state that the table accepts any kind (the registry is now the gate), and
    keeps its action and status CHECK assertions.
- [ ] **AC6. Shared store pieces, only what is common.** A new module (for example
  `gleepglorp/status_rows.py`) holds:
  - `_loads`/`_dumps`, with the two stores' serializers unified only if their output is
    byte-identical for stored rows. Otherwise keep both and report it.
  - a generic `get` and `list_for_session` taking the table, the column list and the row
    decoder;
  - a frame helper `push_session_frame(session_id, frame_type, payload_key, view, log_label)`.
    - It keeps its `broadcast_to_session` import local, because tests patch
      `the_one.sessions._broadcast.broadcast_to_session`.
    - `push_proposal_changed`, `push_fill_requested` and `push_fill_changed` stay as thin
      wrappers with the same names and modules, so every patch site is still valid:
      - `test_gleepglorp_proposals_apply.py:63`;
      - `test_gleepglorp_apply_error.py:70`;
      - `fill/tool.py`'s imports.

  Status transitions (`mark_op`, the fills' `claim` and `record_outcome`) and each `insert` stay
  in their stores. All existing proposal and fill tests pass with their assertions unedited.
- [ ] **AC7. Store kind checks and `target_id`.**
  - `GleepGlorpProposalRepository.insert` refuses an unknown kind with the error type the fill
    store uses for its own refusal (`fill/store.py:135`).
  - The fill store checks `kinds.FILLABLE` (drop `fill/store.KINDS`; nothing imports it).
  - `NewFill`, `Fill`, the fill SQL and `fill_view` carry `target_id`. The `fill_view` key-set
    pins (grep `fill_view` and the frame payload tests) gain it.
  - `fill_view`'s agent lookups (`_agent_names`, `agent_base`) are guarded for
    `agent_name is None`.
  - New tests cover each refusal and the `target_id` round trip.
- [ ] **AC8. `resolve_target` and `target_key`.**
  - `Kind.resolve_target` is an optional member, default `None`.
    - For agent it resolves an existing name to `(name, name)`, with the same refusal sentence
      as today for an unknown name.
    - Rule and routine leave it `None`.
    - The agent's `Normalized.target_id` stays `None`, as today.
  - `kinds.target_key(kind, action, target_id, name)` returns `{kind}:{target_id}` (change) or
    `{kind}:new:{name}` (create). It is documented as **for id-targeted kinds only**.
  - Agent, rule and routine keep their inline formulas byte-identical: `agent:{name}`,
    `rule:{agent}:new`, `rule:{agent}:{id}`, `routine:{agent}:new:{name}` and
    `routine:{agent}:{id}`.
  - A stub-kind test pins the id-first resolution order, the duplicate-name refusal listing
    "name (id)" for each match, and the unknown-ref refusal. It is written as a reusable helper
    that Leg 4's real resolver will call.
- [ ] **AC9. Ids in the reads.**
  - `read_app_config(kind="mcp_servers")` and `kind="providers"` include `id` in each list entry
    and in the detail. This goes through an explicit `_list_or_detail(..., id_of=...)`
    parameter, so no other kind's shape changes.
    - The synthetic self-configuration MCP entry (key `None`) and the "…" overflow entry get no
      `id`.
  - `OPERATOR_PATHS` declares `mcp_servers.list.id`, `mcp_servers.detail.id`,
    `providers.list.id` and `providers.detail.id`. `tests/test_gleepglorp_views_provenance.py`
    covers them, and those reads keep the operator-typed mark where they had it.
  - `_list_or_detail(name=...)` matches `str(key) == name` first, then the name. For two
    same-named MCP servers, the second is reachable by id, and a test pins it.
- [ ] **AC10. The page line route.** `build_line(descriptor, resolved_name=None,
  resolved_id=None)` appends ` (#<route>)` only from server-resolved values:
  - **agents:**
    - `#agents` with no item;
    - `#agents/~new` for create;
    - `#agents/{id}` or `#agents/{id}/{tab}` **only when the item resolved**; otherwise no
      route;
  - **library:**
    - `#library/{section}/~new` for create;
    - `#library/{section}/{id}` when the item resolved;
    - no route for a section only, an unresolved item, or no section (`tests/_app_routes.py`:
      bare `library/{group}` redirects);
  - **settings:** `#settings/{section}`, never the item. No route without a section, because
    bare `settings` redirects.

  Also:
  - `build_line(descriptor)` with no `resolved_*` gives the old line plus a route only for the
    item-free cases above. Existing `build_line` tests are updated accordingly.
  - Segments are encoded like `router.js` `enc` (`:128-131`). A test reads the `enc` body by
    regex, as `tests/_app_routes.py` reads the client, and pins the Python encoder against it.
  - `LINE_CAP` truncates only the label part, and a route longer than the cap on its own is
    omitted.
  - `_stored_name` becomes `_resolve_item(conn, descriptor) -> (name, id)`:
    - agents: `(name, name)`;
    - library: `(found.name, found.id)`;
    - settings: `(item, None)`.
- [ ] **AC11. The chip hides the route.**
  - The client's page-chip path strips one trailing ` (#…)` suffix before display. This covers
    the `page_line` frame, the `user` event's `page.line` and history replay, all through one
    function.
  - The existing chip assertions in `tests/browser/test_flow_gleepglorp_drawer_chat.py` pass
    unedited.
  - `tests/test_ws_page_context.py` is updated wherever it pins a server-built line (its
    `LINE` literal is a create page, so it gains ` (#library/mcp/~new)` where the server
    builds it). Read each use.
  - One new browser assertion shows that a chip for a page with a resolved item has no `(#` in
    its text.
  - The static JS guards pass.
- [ ] **AC12. Eval page lines.**
  - Every `[page]` line in `evals/gleepglorp/scenarios/*.toml` equals what production would
    build:
    - `Agents › New Agent (#agents/~new)`;
    - `Library › MCP servers › New MCP server (#library/mcp/~new)`;
    - `Library › Model providers › New model provider (#library/providers/~new)`;
    - `Settings › Built-in tools (#settings/tools)`;
    - the agents item lines with the encoded agent name.
  - Per-fact fields carry the encoded segment where a template needs it, for example
    `agent_seg = "Trip%20Planner"` beside `agent` in `fill-change-prompt.toml`'s facts.
  - `tests/test_evals_gleepglorp_fills.py`'s page-line pin (`:91`) builds lines with
    `resolved_name=item_name or item, resolved_id=item`, which matches production for agent
    items, the only item kind in the scenarios. The test says so in a comment. Its other
    literal pins (`:166`, and `:513` if compared to a built line) are updated.
  - `tests/test_evals_freeze.py` does not cover `evals/gleepglorp/scenarios/`; confirm that it
    passes.
- [ ] **AC13. The `gleepglorp` lane.**
  - `scripts/run-tests.sh --lane gleepglorp --list` prints exactly five files:
    - `test_flow_gleepglorp_drawer_chat.py`, `test_flow_gleepglorp_drawer_shell.py` and
      `test_flow_gleepglorp_fill.py`;
    - `test_flow_chat_gleepglorp.py` and `test_flow_chat_proposals.py`.
  - They are out of `chats-transcript`, `chats` and `shared`.
  - The lane is in `LANE_LIST`, `CANON_LANES`, the `case` table and `BUDGET`, at 360 s with
    the comment "M36 F4 L1b provisional; re-measured at the Flight 4 closing gate". The header
    comment at `run-tests.sh:23` lists it.
  - `tests/test_run_tests_lanes.py` is updated:
    - its `LANES` tuple;
    - the exact `LANE_LIST` string (~:224);
    - the `chat` alias pin (~:190), per Context;
    - and any partition assertion.
  - `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane gleepglorp`
    is green.
- [ ] **AC14. Docs.**
  - `CLAUDE.md` "Per-area browser test lanes" lists `gleepglorp`.
  - `the_one/agents.md` covers:
    - v56 (with the sequence carry);
    - `resolve_target` and `target_key`;
    - the shared store module;
    - the route and the chip strip (update the old `build_line` signature at ~:3376);
    - the lane, in "Browser test lanes, budgets and run policy".
  - The comment at `db/schema.py:797` (squawk 0398) cites `the_one/agents.md`.
- [ ] **AC15. Gates.**
  - `THE_ONE_TEST_NETNS=1 make test-unit` passes with 15 skips.
  - The `gleepglorp` lane passes, and so does `chats-transcript`, since files left it.
  - The static JS guards (`tests/test_ui_guards.py`, `tests/test_token_definitions.py`,
    `tests/test_design_tokens_a11y.py`) pass.
  - `ruff check` and `ruff format --check` are clean.

## Verification Steps

- AC1-AC5: `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_db_migration.py tests/test_schema_template.py tests/test_gleepglorp_fill_store.py -x --timeout 60`.
- AC6-AC9: `tests/test_gleepglorp_*.py` (store, tool, apply, views, provenance).
- AC10-AC12: the page tests, `tests/test_ws_page_context.py`, `tests/test_evals_gleepglorp*.py`,
  `tests/test_evals_freeze.py`, then the `gleepglorp` lane for AC11.
- AC13: `--lane gleepglorp --list`, `--lane chats-transcript --list`, `--lane shared --list`,
  `tests/test_run_tests_lanes.py`, then the lane run in the background.
- AC15: `THE_ONE_TEST_NETNS=1 make test-unit` in the background, after the lanes (never
  concurrent with them).

## Implementation Guidance

1. **Re-read Leg 1a's landed code** and its flight-log entry.

2. **Schema v56.**
   - Add the two shape helpers.
   - For each table, if it is not v56-shaped, run one `executescript`:
     - `PRAGMA foreign_keys=OFF;`
     - `DROP TABLE IF EXISTS <t>_new;`
     - `CREATE TABLE <t>_new (...)`, the v56 DDL;
     - `INSERT INTO <t>_new (cols) SELECT cols FROM <t>`, with fills taking `NULL` for
       `target_id`;
     - carry the sequence: read the old `seq` from `sqlite_sequence` before the drop, and after
       the rename write it back with `INSERT OR REPLACE`. The simplest correct sequence is
       read old seq → rebuild → `UPDATE sqlite_sequence SET seq = max(seq, old) WHERE name =
       '<t>'`, or an insert when no row exists;
     - `DROP TABLE <t>;`, `ALTER TABLE <t>_new RENAME TO <t>;`
     - recreate its indexes;
     - `PRAGMA foreign_keys=ON;`
   - Then the version stamp.
   - Fix the squawk 0398 comment at `:797`.

3. **Stores (AC6, AC7).**
   - Build the small shared module.
   - Switch both stores to it without changing their public API.
   - Add the kind checks and `target_id`, and make `agent_name` optional in the types.
   - Grep the tests for the frame wrapper names and keep them all valid.

4. **`resolve_target` and `target_key` (AC8).**
   - Add `resolve_target` as an optional `Kind` field and set it on `agent.KIND`. Reuse the
     existing name check; do not change the normalize path's sentences.
   - Write the shared resolution helper, for example `kinds.resolve_by_id_or_name(entries,
     ref, label)`, that Leg 4 will use with real tables. Test it with stub entries.

5. **Reads (AC9).** Add `id_of=` to `_list_or_detail`, pass it from `view_mcp.py` and
   `view_library.py` `providers_view`, declare the paths, and match the id first.

6. **The page line (AC10).** The resolver, `_route`, `_enc`, the truncation restructure, and the
   `resolve_page` call. Grep `tests/` and `evals/` for `build_line(` and `[Page:` pins.

7. **The chip (AC11).**
   - Find the one function that renders a page chip from a line (`addPageChip` /
     `App.ui.message.context`). Add the strip there: a regex anchored at the end,
     `/ \(#[^()\s]*\)$/`.
   - If the chip is rendered by the `App.ui` control, follow its catalogue and contract-test
     rules (`docs/ui-control-inventory.md` row note, if behaviour is described there).

8. **Eval scenarios (AC12).** Edit through the edit tool, then run the eval tests.

9. **The lane (AC13).**
   - Add `gleepglorp_pat`, remove the two files from `chats_transcript_pat`, subtract
     `gleepglorp_pat` in `chats_files`, add it to the `shared` assigned list, and add it to
     `LANE_LIST`, `CANON_LANES`, `BUDGET`, the `case` table and the header comment.
   - Update `tests/test_run_tests_lanes.py`.

10. **Docs (AC14).** Then run the AC15 gates.

## Edge Cases

- **A fresh database** builds the old shapes in v54 and v55, and v56 rebuilds them while they
  are empty. This is fine, and the sequence carry handles a missing `sqlite_sequence` row.
- **The CHECK detection** must not match the action or status CHECKs: match `CHECK (kind IN`
  exactly as the v54 DDL spells it.
- **The agents route with an encoded name.** `#agents/Trip%20Planner/tools`. The label shows
  the plain name.
- **Lines stored before this leg** keep their old form, so the strip is a no-op on them.
- **The seam-import guard** (`test_the_seam_modules_do_not_import_interfaces`) covers any new
  `gleepglorp/` module that `apply`/`continuation` import. Add the new store module to its
  parameters if the guard lists files explicitly.

## Files Affected

- `the_one/db/schema.py`.
- `the_one/gleepglorp/status_rows.py` (new), `proposals/store.py`, `fill/store.py`,
  `proposals/events.py`, `fill/events.py`.
- `the_one/gleepglorp/proposals/shape.py` (`Normalized.agent_name` type).
- `the_one/gleepglorp/kinds/base.py`, `kinds/__init__.py`, `kinds/agent.py`.
- `the_one/gleepglorp/view_core.py`, `view_mcp.py`, `view_library.py`.
- `the_one/gleepglorp/page.py`.
- The chat chip JS (`addPageChip` / `App.ui.message.context`; locate it).
- `evals/gleepglorp/scenarios/*.toml`.
- `scripts/run-tests.sh`.
- **Tests:**
  - `tests/test_db_migration.py`, `tests/test_gleepglorp_fill_store.py`;
  - the proposal and fill store, view and provenance tests;
  - the page tests, `tests/test_ws_page_context.py`, `tests/test_evals_gleepglorp_fills.py`;
  - `tests/test_run_tests_lanes.py`;
  - `tests/browser/test_flow_gleepglorp_drawer_chat.py` (one new assertion only);
  - new test files.
- `CLAUDE.md`, `the_one/agents.md`.

## Design Review

Cycle 1 (Developer, Sonnet): **approve with changes.** Folded in as follows:
- **High:**
  - **The route showing in the chip:** stripped client-side (AC11), so the existing chip
    assertions pin it.
  - **`TestSchemaV54`'s bogus-kind assertion:** inverted (AC5).
- **Medium:**
  - every `== 55` pin;
  - the `foreign_keys=ON` bracket;
  - the AUTOINCREMENT sequence, carried;
  - per-table rebuild checks;
  - how the v55 test database is built;
  - target-key formulas, confined to id-targeted kinds;
  - `resolve_target` optional, and the agent's `target_id` stays `None`;
  - `agent_name` types;
  - `fill_view` `target_id`;
  - AC6 cut down, with no shared `mark`;
  - the lane pins and the `chat` alias;
  - one 360 s budget.
- **Deferred to Leg 4:** the `target` tool parameter. It would have changed platform prompt
  text with no consumer.
- **Removed:** the freeze-digest branch, since `evals/gleepglorp/scenarios` is not covered.
- **Specified:** the eval page lines, with the per-fact encoded segment.
- **Low:**
  - route cases;
  - `id_of=` confined to MCP and providers;
  - self-configuration and overflow entries without ids;
  - id-first `str(key)` match;
  - the `agents.md` `build_line` signature.

There is no second cycle: these are resolutions and scope cuts, and the chip strip is a single
display function covered by unedited assertions.

## Citation Audit

Re-checked against the working tree with Leg 1a landed:
- `db/schema.py:18` `CURRENT_VERSION = 55`; the v54 DDL `kind TEXT NOT NULL CHECK (kind IN ('agent', 'rule', 'routine'))`, plus action and status CHECKs and `status DEFAULT 'pending'`; the v55 fills DDL (no kind CHECK, `agent_name NOT NULL`, `status DEFAULT 'sent'`); four indexes; `:797` the CLAUDE.md citation; the `agent_revisions` `PRAGMA table_info` guard (~:2500) — verified (design review).
- `tests/test_db_migration.py`: about 16 `== 55` pins (lines listed in the review); `TestSchemaV54.test_check_constraints_refuse_bad_values` (~:6912) inserts `kind='bogus'` — verified (design review).
- `fill/store.py:29` `KINDS` (no importers), `:135` the insert refusal; `proposals/store.py:142` `insert`, `:159` the replacement rule; `mark_op` is a module function in proposals; fills use `claim` and `record_outcome` — verified (design review).
- `shape.py` `Normalized.agent_name: str` (~:77) — verified (design review).
- `page.py` `_stored_name` and `resolve_page`; `router.js:128-131` `enc` — verified.
- `tests/browser/test_flow_gleepglorp_drawer_chat.py` ~:636/:673/:715/:776 chip assertions; `tests/test_ws_page_context.py` `LINE` — verified (design review).
- `tests/test_evals_gleepglorp_fills.py:91`, `:166`, `:513`; `fill-change-prompt.toml:31` (the only scenario with a page item) — verified (design review).
- `tests/test_evals_freeze.py` covers `SCORING_DIGESTS`, `MEASURE_DIGESTS` and the platform `evals/scenarios` fingerprint, but not `evals/gleepglorp/scenarios` — verified (design review).
- `scripts/run-tests.sh:23` header, `chats_transcript_pat`, `chats_files`, the `shared` complement; `tests/test_run_tests_lanes.py` `LANES`, `LANE_LIST` string ~:224 and the `chat` alias pin ~:190 — verified (design review).
- `view_core.py:242`/`:261` the `mcp_servers` and `providers` `OPERATOR_PATHS` blocks; `_list_or_detail` first-name match — verified.
