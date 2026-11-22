# Leg: 04b-mcp-editor-fill

**Status**: completed
**Flight**: [MCP servers and model providers](../flight.md)

## Objective

GleepGlorp can fill the MCP server editor as unsaved edits:
- **new servers:** every field;
- **existing servers:** every field except the type.

Each filled control gets a quiet note, and the env or headers table gets one note. An empty
Sensitive row hands a key to the operator. An MCP editor open when an MCP proposal is approved
follows the approval without a reload, and never overwrites the operator's unsaved edits. MCP
proposal cards show their header and env rows and warnings.

## Context

- **Flight decisions:** DD8 (fills for every kind), DD9 (MCP), DD11 (the client registry and the
  operator-approved layouts: one note under a key-value table; header and env rows as their own
  card rows; warnings in the card footer).
- **Depends on Leg 4a (landed, uncommitted).** What 4a actually built:
  - `kinds/mcp_server.py` with `fillable = ()`;
  - `normalize` refuses an empty row value for every action, and refuses a `type` change on a
    change;
  - `proposal_view` adds `warnings` and the applied create's `target_id`;
  - `display_values` flattens rows, but `proposal_view` keeps nested `changes` and `base`;
  - `config_changed` for `mcp_server` carries `agent: null` and `target_id`.
- **Server work in this leg,** found by the design review: `fill/tool.py` still refuses non-agent
  kinds, and `fill_view` is agent-shaped.
- **FD decisions at this leg's design (2026-11-21), recorded in the flight log:**
  1. **No `type` change on an existing server, by fill or by proposal.** GleepGlorp tells the
     operator to switch the type in the editor. This narrows DD9 (it was fill-only) to
     create-only. Reason: the editor decides which old-type keys and Sensitive rows a switch
     drops, and a fill would have to replay that exactly. One dropdown change is a small
     handoff. A fill may still set `type` on a **create**.
  2. **The handoff row is a bare `""`, in fills only, for a secret-looking key only.** A fill row
    `{"X-Api-Key": ""}` is accepted when `looks_secret_key(key)` is true (`mcp/service.py`), and
    the client adds it as an empty **Sensitive** row. An empty value for a non-secret key
    (`Accept`) is still refused. Proposals still refuse every empty row. The OAuth-managed-name
    and stored-Sensitive collision refusals still apply.
  3. **`fill_form` keeps `agent` for agents.** `target` carries an MCP server's id or name.

## Inputs

- Leg 4a landed: `kinds/mcp_server.py`, `mcp/service.py` (`looks_secret_key`, `_stale_fields`,
  `_current_value`), `proposals/store.py`, `kinds/base.py`.
- `fill/tool.py`, `fill/store.py` (`fill_view`), `outside.py`, `proposals/guard.py`.
- **Client:**
  - `areas/studio/`: `mcp-server-editor.js`, `mcp-glue.js` (test seam
    `self._currentMcpEditor()`, `state.mcpSourceFormMode`, `state.editingMcpSource`,
    `mcpTypesReady`), `mcp-connection-fields.js`, `mcp-env-headers.js`,
    `mcp-editor-shared.js`;
  - `ui/key-value-table.js`;
  - `areas/studio/agent-editor-fill.js`, `agent-editor-follow.js` and `agent-kinds.js` (the
    patterns);
  - `gleepglorp-kinds.js`, `gleepglorp-drawer/fill.js`, `areas/chat/proposal-cards.js`,
    `approvals.js`;
  - `router.js` (the MCP spec is `{destination: 'library', section: 'mcp', id}` or
    `{..., create: true}`).
- **Tests:** `tests/browser/seeders.py` (`seed_gleepglorp_fill`, `seed_gleepglorp_proposal`),
  `tests/browser/_mcp_editor.py`, `tests/browser/test_flow_gleepglorp_fill.py` (`_bworld`,
  `_deliver`, `_wait_status`), `tests/browser/test_flow_gleepglorp_kinds.py`.

## Outputs

**Server**
- **`Kind.normalize` gains a `mode` argument** (`"propose"` | `"fill"`, default `"propose"`),
  passed by `fill/tool.py`.
  - The `mcp_server` kind uses it only for decision 2's empty secret-looking row.
  - The other kinds ignore it, and their outputs are byte-identical.
  - `outside.check` and `guard.check` pass on `""` values (`outside` skips empty strings like
    `None`).
- **`kinds/mcp_server.py` `fillable = ("create", "change")`.**
- **`fill/tool.py` is generalized:**
  - the agent-only refusal goes, and a kind must be in `kinds.FILLABLE`;
  - `notes_enabled` stays agent-only;
  - the return text names the editor by kind ("the MCP server editor");
  - the description names the fillable kinds. It is provisional platform text, measured in Legs
    6 and 7, within the 90-token and character pins.
- **`fill_view`** takes `title` and `target_gone` from `kind.card_extras` when the kind has it.
  `stale` is computed for `mcp_server` change fills by comparing `fill.base` with the current
  stored values, using the service's `_current_value` (or a public alias). The agent path is
  unchanged.

**Client**
- **Editor handles.** The MCP controller (`mcp-server-editor.js`) returns, beyond today's
  members:
  - `ready()`, `values()` and `baseline()`;
  - `setType(type)`, for create forms only: the `performCancel`/`applySaved` sequence;
  - `setField(key, value)` for `name`, `url`, and `command` plus `args`. The `command`+`args`
    group goes through `deriveStdioRuntimeSelection` and is one dirty group;
  - `setRows(kind, rows)`, which merges by key. A new row gets a fresh `_rid`; an empty-valued
    row is added with `sensitive: true` and `_originalMasked: ''`. It keeps the other rows;
  - `placeNote(key, el)` and `placeTableNote(el)`;
  - `rebase(source)` and `checkDirty()`.

  The setters are silent. `connectionFields.setField`, `envHeaders.setRows` and
  `envHeaders.rebaseTo` are added.
- **The open key and the controller.**
  - The glue's existing seam `self._currentMcpEditor()` is reused.
  - The open key is `'create'` when `state.mcpSourceFormMode === 'add'`, else
    `'edit:' + state.editingMcpSource.id`.
  - Settled means: the types fetch is ready (`mcpTypesReady`), the controller is mounted, the
    key matches, the route is the MCP create or edit route, and no Save is in flight (expose
    `saving`).
  - A failed types fetch makes `whenSettled` resolve `false`, so the fill is reported
    editor-unavailable.
- **`areas/studio/mcp-editor-fill.js`** (new), mirroring `agent-editor-fill.js`:
  - `isOpen`, `whenSettled`, and `apply(view)` returning `{unavailable, written, kept}`;
  - order of writes: `type` (create only), then fields, then rows, then `checkDirty`;
  - the kept rule per key and per group (`command`+`args` count as one group, named "Command"
    in the receipt), and per row;
  - a note under each filled control;
  - one note under the env or headers table: "Filled by GleepGlorp: A, B." plus "Enter the value
    for X." for each empty Sensitive row;
  - notes cleared on Cancel, Save, remount and patch, and the old notes replaced on a refill;
  - the dev-mode settle timeout.
- **`areas/studio/mcp-editor-follow.js`** (new), with one document listener on
  `App.approvals.CONFIG_CHANGED`. For `kind === 'mcp_server'` and `target_id` equal to the open
  edit editor's id:
  - fetch the row, and update `state.editingMcpSource`;
  - rebase per field: a clean field takes the new value; a dirty field keeps the operator's
    value while its baseline moves;
  - rebase rows per key:
    - a new row is added to the table and the baseline;
    - a changed clean row takes the value;
    - a changed dirty row keeps the operator's value, with its baseline moved;
    - Sensitive rows keep their `_originalMasked` from the fetched mask;
  - on a rename, update the page title, the breadcrumb and the router name hint
    (`App.router.sync`);
  - draw the follow note (the agent follow note's layout and wording, with "Open chat"), and
    call `checkDirty`;
  - **defer the rebase while a Save is in flight,** then re-fetch. A Test in flight writes only
    `_cache` and does not block.
- **The kind's registration** (`areas/studio/mcp-kinds.js`, new), loaded after `agent-kinds.js`
  at the end of the Studio block, with late-bound calls:
  - `labels`:
    - "MCP server";
    - "The MCP server editor could not open.";
    - "That MCP server no longer exists.";
    - a `withdrawnGone` reason;
  - `openLink`: the router spec `{destination: 'library', section: 'mcp', id}` from
    `view.target_id`, text "Open MCP server", testid `proposal-open-item`; `null` with no id;
  - `store: 'mcp-sources'`;
  - `recordKey(detail)`: `detail.target_id ? {scope: 'target', id: detail.target_id} : null`;
  - `fill`:
    - `routeFor`: the create or edit spec;
    - `openKey`;
    - `exists`: from the `mcp-sources` store, free of side effects;
    - `isOpen` and `whenSettled`;
    - `select`, `beforeNavigate` and `afterNavigate`: no-ops;
    - `apply`.
- **Card rows** (`proposal-cards.js`), flattened client-side:
  - a `rows` field (`headers` or `env`) in `view.changes` renders one table row per key
    ("Header Accept", "Env LOG_LEVEL");
  - the Now column reads the nested `view.base`, with an absent row shown as "None";
  - header keys match case-insensitively for the Now lookup;
  - `fieldKeys` (used by `appliedByApproval`) keeps the stored keys `headers` and `env`;
  - the footer counts rows ("Only these 3 values change.");
  - `view.warnings` renders in the footer slot.

**Tests and seeders**
- `tests/browser/seeders.py` `seed_gleepglorp_fill` gains `target_id`, with `agent_name=None`
  allowed and the matching `target_key` (`kinds.target_key`).

## Acceptance Criteria

- [ ] **AC1. Server: fills.**
  - `fill_form` with `kind="mcp_server"` creates and changes fills.
  - A create's `type` is accepted. A change naming `type` is refused with the editor handoff.
  - An empty value for `X-Api-Key` in a **fill** is accepted. The same row in a **proposal** is
    refused, and an empty `Accept` in a fill is refused.
  - The OAuth-name and Sensitive-collision refusals hold for fills.
  - `notes_enabled` is refused for `mcp_server`.
  - The agent fill path is unchanged, with its tests unedited.
- [ ] **AC2. Server: `fill_view`.** An `mcp_server` change fill's view carries:
  - the server's name in `title`;
  - `target_gone` set once the server is deleted;
  - a `stale` row when a named field changed after the fill was made.

  The agent fill views are byte-identical.
- [ ] **AC3. Server pins.** Each is updated, and none weakened:
  - `tests/test_gleepglorp_kinds.py` (`FILLABLE` now includes `mcp_server`);
  - `tests/test_gleepglorp_kind_mcp.py` (the not-fillable and empty-row refusals become
    mode-aware);
  - the `fill_form` enum and description pins in `test_gleepglorp_fill_tool.py`,
    `test_evals_gleepglorp_fills.py` and `test_gleepglorp_build.py`;
  - the mock fill loop test.

  Before editing a pin under `tests/test_evals_*`, check `tests/test_evals_freeze.py`. If the
  file is digest-frozen, stop and report the new digest to the FD.
- [ ] **AC4. Editor seam.**
  - `setType` on a create form swaps the sections and keeps rows the operator typed.
  - `setField('command', 'npx')` plus `args ['-y', '@acme/x']` selects `npx -y` and shows
    `@acme/x`.
  - `setRows` adds an empty Sensitive row and keeps the existing rows.
  - None of these saves, runs Test or opens a popup. This is shown by the request counter: no
    `/test/connect`, no popup.
- [ ] **AC5. Create fill, HTTP.** The fill opens `#library/mcp/~new` and sets HTTP, the name, the
  URL and an empty Sensitive `X-Api-Key`.
  - **Notes:** a note under each filled control, and the table note "Filled by GleepGlorp:
    X-Api-Key. Enter the value for X-Api-Key.".
  - **Unsaved:** the caption shows, and nothing is stored (`GET /api/mcp-sources` is unchanged).
  - **Receipt:** it reads filled.
  - **After the operator types the key and saves:** the row has the header in `secrets`.
- [ ] **AC6. Stdio fills.**
  - A create fill writes the runtime, the command and the args through the collapse, plus a
    plain env row.
  - A change fill on an existing stdio server writes only the named fields, leaving the other
    fields, `cwd` and `sandbox` untouched.
- [ ] **AC7. Dirty-state navigation** (DD8):
  - **Same route, dirty.** A field (or the command group) the operator changed is kept, and the
    receipt reads partly filled and names it.
  - **Other route, dirty.** The leave guard asks. Stay means not filled with the stay reason,
    and nothing is written.
- [ ] **AC8. Follow-through.** With the editor open on server S:
  - approving an `mcp_server` proposal for S updates the clean fields and rows without a reload,
    shows the follow note, and leaves the editor clean;
  - with an unsaved edit elsewhere, that edit is kept and the editor stays dirty only for it;
  - a later Save does not undo the approved change;
  - a rename updates the title and breadcrumb;
  - an approval for another server changes nothing.
- [ ] **AC9. The card.**
  - Rows show one per key, with the Now column ("None" when a row is absent) and Proposed, plus
    the URL.
  - The footer shows the warning when present, and counts rows.
  - After apply, "Open MCP server" (`proposal-open-item`) goes to `#library/mcp/{id}` for a
    create as well as a change, using the applied `target_id`.
  - Agent cards are unchanged.
- [ ] **AC10. Registration.**
  - `App.gleepglorpKinds.names()` holds the four kinds.
  - `tests/browser/test_flow_gleepglorp_kinds.py` gets `mcp_server` added to its names, shape
    list and order checks.
  - A `config_changed` for `mcp_server` records under `forTarget('mcp_server', id)`, and a create
    without `target_id` records nothing.
- [ ] **AC11. Accessibility.**
  - Each fill note is `aria-describedby`-linked to its control. The table note is linked to the
    table region.
  - The follow note's link is a native `<a>`.
  - No live region announces values.
  - The static guards pass.
- [ ] **AC12. No regression.**
  - These lanes pass, one at a time: `gleepglorp`, `mcp`, `mcp-connection` and `library`.
  - The agent fill and follow tests pass unedited.
  - `THE_ONE_TEST_NETNS=1 make test-unit` passes with 15 skips.
  - The new browser files are added to the `gleepglorp` lane's explicit list, and
    `tests/test_run_tests_lanes.py` is updated.

## Verification Steps

- **Unit:** `.venv/bin/python -m pytest tests/test_gleepglorp_kind_mcp.py tests/test_gleepglorp_fill_*.py tests/test_gleepglorp_kinds.py tests/test_gleepglorp_build.py tests/test_evals_gleepglorp*.py tests/test_evals_freeze.py -x --timeout 60`.
- **New browser files:** `tests/browser/test_flow_gleepglorp_fill_mcp.py` and
  `test_flow_gleepglorp_follow_mcp.py`, in the `gleepglorp` lane.
- **Lanes,** one at a time in the background, then the unit tier.

## Implementation Guidance

1. **Server first** (AC1-AC3): the `mode` on `normalize`, `fillable`, the `fill/tool.py`
   generalization, `fill_view`, the seeder `target_id`. Run the unit tests.
2. **The editor seam** (AC4), with its browser test.
3. **`mcp-editor-fill.js` and `mcp-kinds.js`** (AC5-AC7, AC10).
4. **`mcp-editor-follow.js`** (AC8).
5. **Card rows and footer** (AC9).
6. **Accessibility pass** (AC11), docs (`the_one/agents.md`), the guide (check `mcp-servers.md`
   against decisions 1 and 2), lanes and the unit tier (AC12).

## Edge Cases

- **A refill on the same create form:** the old notes go, and the new ones are drawn.
- **A change fill for a deleted server:** `fill_view.target_gone` is true, and the receipt reads
  target gone, with no Fill now.
- **The editor remounts after a Create Save:** the record and notes are cleared.
- **A follow event for a server whose editor is a create form:** ignored.
- **A Sensitive row the operator then turns off:** it saves as plain, as today. The note stays
  until the row's value is edited.

## Files Affected

- **Server:** `the_one/gleepglorp/kinds/base.py`, `kinds/__init__.py`, `kinds/mcp_server.py`,
  and the other kinds' `normalize` signatures (they accept and ignore `mode`); `fill/tool.py`,
  `fill/store.py`; `outside.py` (empty strings).
- **Client:** `mcp-server-editor.js`, `mcp-glue.js`, `mcp-connection-fields.js`,
  `mcp-env-headers.js`; new `mcp-editor-fill.js`, `mcp-editor-follow.js` and `mcp-kinds.js`;
  `proposal-cards.js`; `static/index.html`.
- **Tests:** `tests/browser/seeders.py`; the new browser files; `test_flow_gleepglorp_kinds.py`;
  the AC3 pins.
- `scripts/run-tests.sh`, `tests/test_run_tests_lanes.py`, `the_one/agents.md`, and the guide
  if needed.

## Design Review

Cycle 1 (Developer, Sonnet): **needs rework.** Rewritten:
- **High:**
  - an empty Sensitive row was refused by 4a's normalize, so `mode="fill"` and decision 2;
  - a type change by fill contradicted 4a, so decision 1 makes it create-only;
  - `fillable` holds actions, not keys;
  - `fill/tool.py` was agent-only;
  - `fill_view` was agent-shaped;
  - card rows needed client-side flattening, and `fieldKeys` is kept.
- **Medium:**
  - `recordKey` reads `target_id`, or `null` for a create;
  - the router spec, the existing glue seam and the open key from state;
  - follow-through updates `editingMcpSource`, the title and breadcrumb, a per-key row rebase,
    and the Test-in-flight rule;
  - the seeder needs `target_id`.
- **Low:** the kinds browser test shape list, the script order, and the lane list.

Cycle 2 (Developer, Sonnet): **approve with changes.** Every cycle-1 finding is resolved. These
resolutions **bind over any earlier text in this leg:**
1. **The `kept` contract.** The outcome POST (`gleepglorp_fills_api.py:94-103`) accepts only
   stored keys from `fill.changes`, deduplicated.
   - A kept field or group reports its stored key: `command` for the command+args group,
     `headers` or `env` for any kept row.
   - The receipt therefore names "Command" or "Headers" from `labels`.
   - AC7 adds two assertions: the outcome POST returns 200, and the receipt names the field.
2. **`setType` on a create form** does **not** use `applySaved` or `performCancel`, which reset
   or leave the form. The sequence is:
   1. set the type select's value;
   2. call `connection.setType`, `sandbox.setType` and `envHeaders.setType` (which keeps rows);
   3. run the controller's type-change path;
   4. call `checkDirty`.

   A type the operator already changed on the create form is kept (the kept rule), and the rows
   stay as typed.
3. **`fill_view` stale for `mcp_server`:**
   - load the source through the kind (a deleted source gives `target_gone` true and `stale`
     empty);
   - call the service's stale function through a **public** alias (`stale_fields`), not an
     underscore name;
   - add `label` from the kind's labels;
   - flatten rows to the display form ("Header X"), so the client's `v.stale[].label` reads it
     as it does for agents.
4. **An empty secret-looking row whose key already exists** as a plain row on the server
   (header keys compare case-insensitively): the plain row is **kept**, and its stored key is
   reported in `kept`. A row the operator already typed a value into is likewise kept. AC6 adds
   both checks.
5. **The AC3 pins, corrected.** The real pins are:
   - `tests/test_gleepglorp_fill_tool.py:79` (enum `["agent"]`) and `:86-95` (the 90-token cap;
     add a character cap beside it);
   - `tests/test_gleepglorp_kinds.py:73` (`FILLABLE == ("agent",)`);
   - `tests/test_gleepglorp_kind_mcp.py:149`.

   `tests/test_evals_gleepglorp_fills.py` and `tests/test_gleepglorp_build.py` hold none. AC3 adds
   one new pin: an `mcp_server` fill with `agent` set is refused.
6. **The `fill_form` description draft,** measured with tiktoken (o200k_base) before the code
   lands, at no more than 90 tokens. It names the fillable kinds, says `target` is an MCP
   server's id or name, says an MCP server's type is set only on create, and teaches the handoff
   ("leave a secret's value empty, \"\", for the operator to enter"). If the draft cannot fit in
   90 tokens, stop and report it. Per the operator-approved flight plan (DD12), the eval
   measurement is Legs 6 and 7.
7. **The client applier reads `view.values`** (nested rows), never `view.changes`, which is the
   flattened display form.
8. **AC9 adds a check** that `appliedByApproval` records `fields: ['headers']` for a header
   change.
9. **The seeder.** For a create, `name` in `kinds.target_key` comes from `changes["name"]`.
   Confirm that the MCP seeding helpers (`_mcp_editor.py` `_seed_http` and `_seed_stdio`) combine
   with the fill helpers (`_bworld`, `_deliver`), or add a small MCP world helper.
10. **`outside.py` is not edited.** It already skips empty row values. A unit assertion pins that
    instead.
11. **`mode`** is added to every kind's `normalize` (`agent`, `rule`, `routine` and `mcp_server`)
    and to the `NormalizeFn` docs in `kinds/base.py`, defaulting to `"propose"`. `kinds.normalize`
    forwards `mode=`.
12. **The dev-mode settle timeout** reuses the constant and seam that `agent-editor-fill.js` uses
    (`__ggFillSettleTimeoutMs`).

The two-cycle cap is reached.

## Citation Audit

Against the working tree (Leg 4a landed):
- `kinds/mcp_server.py` `_check_rows` refuses an empty value ("A proposal can't add an empty
  row") and requires `str`; `normalize` raises `TYPE_CHANGE_MESSAGE` on a change with `type`;
  `fillable = ()` — verified (review).
- `kinds/agent.py:~286` `fillable = ("create", "change")`; `kinds.FILLABLE` is derived from
  truthiness — verified (review).
- `fill/tool.py` `_fill`: `if kind != "agent": raise ShapeError(...)`; the return text names the
  agent editor — verified (review).
- `fill/store.py:~226` `fill_view`: `target_gone` and `stale` only when `agent_name` is set;
  title via `card(action, agent_name)` — verified (review).
- `proposals/store.py` `proposal_view` uses `_display(p.changes, names)` (nested rows);
  `display_values` flattens — verified (review).
- `mcp-glue.js:~245` `self._currentMcpEditor()`; `state.mcpSourceFormMode`,
  `state.editingMcpSource`; `router.js:162-187` the Library spec — verified (review).
- `tests/browser/seeders.py` `seed_gleepglorp_fill(agent_name="plain", target_key=f"{kind}:{agent_name}")`
  — verified (review).
- `tests/browser/test_flow_gleepglorp_kinds.py:~100-125` names and shape lists — verified
  (review).
- `static/index.html`: `agent-kinds.js` at ~188, `agent-editor-fill.js` ~176, `mcp-glue.js`
  ~183 — verified (review).
