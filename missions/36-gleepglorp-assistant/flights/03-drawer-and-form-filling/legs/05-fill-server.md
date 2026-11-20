# Leg: fill-server

**Status**: completed
**Flight**: [The GleepGlorp drawer and form filling](../flight.md)

## Objective

GleepGlorp can **fill** the agent editor, through the server side of a fill:
- `fill_form` records a fill and sends it to the operator's screen. It works
  only in a turn sent from the drawer. It changes nothing in the app's
  configuration.
- The fill is a row in a new `gleepglorp_fills` table (schema v55), and it
  follows its chat as proposals do.
- Two frames tell every socket on the chat: `fill_requested` (new) and
  `fill_changed` (each status change).
- Two authenticated routes let the browser that applies the fill claim it
  and report its outcome.
- Fills reach a joining socket in the `proposals_snapshot` frame, under a
  `fills` key.

No browser code changes in this leg. Leg 6 applies fills in the agent editor
and draws the receipts. Until then, a client ignores the new frames and the
new snapshot key.

## Context

- **The design is flight DD6 and DD8.** DD7 is Leg 6.
- **Leg 4 (landed, batch B):** `TurnContext.page` is `{line, descriptor}`
  for a GleepGlorp turn sent from the drawer, including the drawer's
  step-limit Continue, which goes through `send.sendText` like any drawer
  message. A drawer `continue` turn may therefore fill, and that is
  intended. `TurnContext.page` is `None` for every other turn:
  - a Chats turn;
  - an approval continuation (`sessions/turn_host.py`);
  - the sign-in resume (the bare `TurnContext` at `app.py` ~:3242);
  - a routine run;
  - connector turns (`inbound.py` ~:451);
  - the CLI;
  - `/api/selftest`;
  - any other agent.

  `the_one/agent/_context.py:TurnContext` — `page: dict | None = None`.
  The design review found no path to `fill_form` without a page.
- **Flight 2 (`the_one/gleepglorp/proposals/`)** is the pattern, reused
  rather than copied:
  - `shape.normalize`: declared fields, names resolved to ids, `base` read
    for a change;
  - `guard.check`: the secret guard;
  - `agent.taint.compute_taint`;
  - `store.display_values` and `_name_map`: ids shown as names;
  - `events.push_proposal_changed` and `snapshot_frame`;
  - the router file `interfaces/web/gleepglorp_proposals_api.py`, attached in
    `api.py` (~:7124);
  - the tool's `bind_agent`, called by the factory (`agent/factory.py`
    ~:817).
- **Operator rule (2026-11-20):** the evals freeze hashes are data integrity,
  so the Flight Director applies them by hand. **This leg touches nothing
  under `evals/`.** The harness clean-up of fill rows
  (`_clean_proposal_state`, `evals/harness.py` ~:583) moves to Leg 7. That
  leg changes the harness anyway for its fill scenarios, and no eval
  scenario can produce a fill before then (no scenario has a page turn yet).

## Design decisions made in this leg (within DD6)

1. **There is no CHECK on `kind`.** Only `agent` is accepted in this flight,
   enforced in code by the tool's enum and `normalize`. Later flights add
   kinds, and a CHECK would need a table rebuild, which is the very cost DD6
   cites against reusing `gleepglorp_proposals`. `status` keeps its CHECK,
   since the lifecycle is fixed.
2. **`target_key`** (`agent:{name}`) is stored next to `agent_name`, as on
   proposals. The rename carry can then be the same loop, and a later
   rule or routine fill has its key.
3. **A newer fill replaces older ones that never applied.** A new fill marks
   every fill of the same chat in `sent` or `not_filled` as **`replaced`**,
   in the same transaction as the insert, and pushes `fill_changed` for
   each. A `replaced` fill cannot be claimed, so Fill now can never put an
   older fill's values over a newer one. Fills in `applying`, `filled` or
   `partly_filled` are left alone.
4. **A claim token and a lease.**
   - A claim stores a fresh random `claim_token` and returns it. The outcome
     route requires that token. A late outcome from an earlier claim is
     therefore a 409, never a second write.
   - A claim succeeds from `sent`, from `not_filled`, or from an `applying`
     row whose `claimed_at` is more than `CLAIM_LEASE_SECONDS = 120` old (the
     claiming window went away mid-apply). Without the lease, a receipt
     could stay "applying" forever.
5. **The outcome's reason is a code, not free text.** It is one of
   `in_chats`, `stay`, `editor_unavailable` or `target_gone`, and Leg 6 owns
   the sentences. `kept` lists stored field names and must be a non-empty
   subset of the fill's `changes` keys. No text from the browser is ever
   stored.
6. **`notes_enabled` is refused** by the tool before `normalize`, with one
   sentence: notes save at once and are not a form field.
7. **The view carries both the values and the display.**
   - `values` are the stored changes as the editor needs them: ids for the
     provider, MCP servers and knowledge bases. They are not secret, and the
     browser already lists them.
   - `changes` and `base` are the display forms, ids shown as names, from
     `display_values`.
   - The view also has `labels`, `title`, `field_count` and `target_gone`.
   - `stale` lists the fields whose stored value now differs from `base`,
     as `[{field, label, current, proposed}]`. It is computed when the view
     is read, using the same `comparable_value` / `_agent_base` read as
     `normalize`, and is empty for a create.
   - It never includes `claim_token`.

## Inputs

- Leg 4 landed (`TurnContext.page`).
- Schema v54 is current (`the_one/db/schema.py:CURRENT_VERSION`).

## Outputs

**Schema v55** (`the_one/db/schema.py`):
- a `CREATE TABLE IF NOT EXISTS gleepglorp_fills`, idempotent, with no
  foreign keys (same reasoning as v54), and `CURRENT_VERSION = 55`.
- **Columns:**
  - `id INTEGER PRIMARY KEY AUTOINCREMENT`
  - `session_id TEXT NOT NULL`
  - `tool_call_id TEXT`
  - `kind TEXT NOT NULL`
  - `action TEXT NOT NULL CHECK (action IN ('create','change'))`
  - `agent_name TEXT NOT NULL`
  - `target_key TEXT NOT NULL`
  - `changes TEXT NOT NULL`
  - `base TEXT`
  - `status TEXT NOT NULL DEFAULT 'sent' CHECK (status IN ('sent','applying','filled','partly_filled','not_filled','replaced'))`
  - `outcome TEXT` (JSON `{kept: [..], reason: code|null}`)
  - `claim_token TEXT`
  - `untrusted INTEGER NOT NULL DEFAULT 0`
  - `untrusted_sources TEXT`
  - `created_at TEXT NOT NULL`
  - `claimed_at TEXT`
  - `resolved_at TEXT`
- **Indexes:** `(session_id, status)` and `(agent_name)`.

**`the_one/gleepglorp/fill/`** (new package):
- **`store.py`:**
  - `NewFill`, `Fill` and `GleepGlorpFillRepository`.
    - `insert(new) -> (id, replaced_ids)` does the insert and the
      replacement in one `write_transaction`.
    - `get(id)`.
    - `list_for_session(session_id)` returns rows in id order.
    - `claim(id, now) -> (Fill, token)` raises `FillNotFound` or
      `FillClaimRefused(status)`. Its write is one conditional `UPDATE ...
      WHERE id = ? AND (status IN ('sent','not_filled') OR (status =
      'applying' AND claimed_at < ?))`, checked by `rowcount`.
    - `record_outcome(id, token, status, kept, reason) -> Fill` raises
      `FillNotFound` or `FillOutcomeRefused`. It writes `WHERE id = ? AND
      status = 'applying' AND claim_token = ?`.
  - `fill_view(conn, fill)` builds the view (DD 7 above).
  - Constants: `STATUSES`, `CLAIMABLE`, `OUTCOME_STATUSES = ('filled',
    'partly_filled', 'not_filled')`, `REASONS`, `CLAIM_LEASE_SECONDS`.
- **`tool.py`:** `FillFormTool`, name `FILL_FORM_TOOL_NAME = "fill_form"`.
  - **Parameters:** `kind` (enum `["agent"]`), `action` (enum
    `create|change`), `agent` (string or null) and `changes` (object).
  - **Gate order:**
    1. **A chat session:** none gives the `NEEDS_CHAT`-style sentence.
    2. **A page:** if `current_turn.get()` is `None` or its `page` is
       `None`, return `NEEDS_PAGE` and record nothing. The sentence says
       filling works only when the operator asks from the drawer on an app
       page, so propose the change with `propose_change` instead.
    3. **No `notes_enabled`.** It is refused with one sentence.
    4. **`shape.normalize("agent", ...)`.** A `ShapeError` comes back as its
       text.
    5. **`guard.check`.** A refusal comes back as its text.
    6. **`compute_taint`.**
    7. **The insert,** then pushes: `fill_changed` for each replaced id,
       then `fill_requested`.
  - **Result text** (shipped text, fixed apart from the id): `Fill {id} is
    on the operator's screen as unsaved edits in the agent editor. Nothing is
    saved until they click Save.`
  - **Failures:** an unexpected exception is logged and gives `Could not
    fill the form right now.` The tool never raises.
  - **The description** is short, because it is platform prompt text and
    Leg 7 measures it. It says what a fill is, that it works only from the
    drawer, the create and change usage, and that the fields are those of
    `propose_change` for an agent except `notes_enabled`. It names no
    route.
- **`events.py`:**
  - `push_fill_requested(session_id, view)` sends `{"type":
    "fill_requested", "session_id", "fill"}`.
  - `push_fill_changed(session_id, view)` sends `{"type": "fill_changed",
    "session_id", "fill"}`.
  - Both go through `broadcast_to_session` and never raise.
  - `snapshot_fills(conn, session_id)` returns the newest 200 views in id
    order.

**`the_one/agent/taint.py`:** `"fill_form"` joins `TRUSTED_TOOL_NAMES`, with
a comment line; the literal matches `FILL_FORM_TOOL_NAME`.

**`the_one/agent/factory.py`:**
- `FillFormTool` is registered beside `ProposeChangeTool`, in the
  GleepGlorp branch only, and bound with `bind_agent` beside
  `propose_tool.bind_agent`.

**`the_one/gleepglorp/proposals/events.py::snapshot_frame`:**
- The frame gains `"fills": [...]`, read in its own `try`. A fills read
  failure logs a warning and sends `"fills": []`, and the proposals still
  go.
- The proposals read keeps its current failure behaviour.

**`the_one/interfaces/web/gleepglorp_fills_api.py`** (new), attached in
`api.py` beside the proposals router:
- `GET /api/gleepglorp/fills?session_id=` returns `{"fills": [views]}`. An
  empty `session_id` gives `{"fills": []}`.
- `POST /api/gleepglorp/fills/{fill_id}/claim`:
  - 200 `{"fill": view, "claim": token}`;
  - 404 for an unknown id;
  - 409 `{"error": "claimed", "status": s}` when the fill is not claimable.
    That includes `replaced`, any final status, and an `applying` row
    inside its lease.
  - On a 200 it pushes `fill_changed`.
- `POST /api/gleepglorp/fills/{fill_id}/outcome`:
  - **Body:** a pydantic model with `extra="forbid"`: `{claim: str, status:
    one of OUTCOME_STATUSES, kept: list[str] = [], reason: one of REASONS |
    None}`.
  - **The body must be consistent, or it is a 422:**
    - `filled` has empty `kept` and no `reason`;
    - `partly_filled` has a non-empty `kept`, a subset of the fill's
      `changes` keys, and no `reason`;
    - `not_filled` has a `reason` and empty `kept`.
  - 404 for an unknown id. 409 `{"error": "not_applying"}` for a wrong token
    or a status other than `applying`.
  - On a 200, `{"fill": view}`, and it pushes `fill_changed`.
- **Nothing is echoed:** neither the request body nor any input appears in
  a response or a log line.

**`the_one/db/repositories.py`:** the five sites that handle
`gleepglorp_proposals` handle `gleepglorp_fills` the same way, in the same
transaction:
- `rename` (~:503-517), with the same prefix rewrite of `target_key`;
- `delete` (~:3304);
- `delete_all_for_agent` (~:3322);
- `delete_older_than` (~:3367);
- `purge_messages` (~:3387).

Before writing, grep for any other `DELETE FROM chat_sessions` or chat
`messages='[]'` site. If one exists that does not handle proposals, report
it in the flight log, and do not fix it silently.

**Docs:**
- `the_one/agents.md`: a section "GleepGlorp fills, server (M36 F3 L5)"
  covering the table, lifecycle, routes, frames, gate, replacement,
  lease/token and snapshot key.
- `CLAUDE.md`: one paragraph after "Page awareness (M36 F3 L4)".
- `SECURITY-MODEL.md`:
  - The fill routes change only a fill's status, never configuration.
  - The browser writes the values as unsaved edits, and only the
    operator's Save stores them (Leg 6).
  - The outcome takes codes only.
  - The tool is trusted in the taint rule, and the fill carries the flag.

## Acceptance Criteria

**AC1 — Schema v55.**
- A fresh database and a v54 database both reach v55 with the table, the
  columns above and both indexes.
- Running the migration twice is a no-op.
- The `status` CHECK rejects an unknown status.
- The session template (`tests/_schema_template.py`) has the table.
- `CURRENT_VERSION == 55`.

**AC2 — Store.**
- `insert`, `get` and `list_for_session` round-trip `changes`, `base` and
  the sources.
- A second insert in the same chat marks the earlier `sent` and
  `not_filled` fills `replaced`, returns their ids, and leaves `applying`,
  `filled` and `partly_filled` untouched.
- `claim` moves `sent` and `not_filled` to `applying` with a token and
  `claimed_at`.
- A second claim inside the lease is refused. A claim of an `applying` row
  older than the lease succeeds with a new token, and the old token's
  outcome is then refused.
- `record_outcome` writes the status, the `outcome` JSON and `resolved_at`
  only with the matching token and `applying`.
- `insert` with a kind other than `agent` raises `ValueError` (the store
  guard behind the tool's enum).
- `claim(id, now)` takes a tz-aware `datetime` and formats it with
  `.isoformat()` itself, so the lease comparison runs on the `now_iso()`
  format. Tests that inject a clock pass tz-aware UTC datetimes.
- `fill_view` has no `claim_token`, shows ids as names in `changes`, keeps
  ids in `values`, and computes `stale` (for a change whose stored field
  moved) and `target_gone`.

**AC3 — The tool's gate and refusals.** `fill_form` returns `NEEDS_PAGE`,
records no row and pushes nothing in each of these turns:
- a turn with no `TurnContext`;
- a GleepGlorp turn with `page=None` (a Chats turn);
- an approval continuation through `turn_host`, the real seam.

A drawer `continue` turn carries a page and may fill. AC3 asserts no
refusal for it.

In a page turn, the following are each refused with one sentence and record
nothing:
- `notes_enabled`;
- an unknown key;
- a reserved or existing name on create;
- a missing agent on change;
- a secret-bearing value (the guard).

**AC4 — The tool records and sends.** In a GleepGlorp page turn,
`fill_form`:
- records one `sent` row with `tool_call_id`, `target_key` and the `base`
  of the touched fields (on change);
- pushes `fill_requested` with the view to the chat's subscribers;
- returns the result text exactly.

A fill after an untrusted `read_app_config` result carries `untrusted` and
its sources. A `save_note` after a `fill_form` result is not flagged,
because `fill_form` is in `TRUSTED_TOOL_NAMES`.

**AC5 — Nothing is written but the fills table.** The Flight 2 no-write test
(`tests/test_gleepglorp_proposals_tool.py` ~:186, "it writes nothing but its
own table") gets a `fill_form` sibling. The `agents`, `agent_rules`,
`agent_routines`, MCP, knowledge and settings rows are byte-identical before
and after a successful fill.

**AC6 — Registered for GleepGlorp alone.**
- GleepGlorp's toolset includes `fill_form`.
- No other agent gets it, and it is not in `tools.builtins._TOOL_CLASSES`.
- The allowlist tests list it. See "Assertion edits allowed".

**AC7 — Routes.**
- The GET returns the chat's views.
- The claim and outcome paths behave as above, with 404, 409 and 422 as
  listed, each refusal writing nothing.
- `fill_changed` is pushed on every successful claim, outcome and
  replacement, and never on a refusal.
- Without a credential each route is a 401.
- `tests/test_api_name_rule.py` gets the two new POST routes as rows in its
  `EXEMPT` dict, each with a reason string, like the proposal approve and
  dismiss rows (~:57-62). That is adding data, not editing an assertion.
- `tests/test_credential_gate.py` passes.

**AC8 — Follows its chat.**
- Deleting a chat removes its fills.
- `delete_all_for_agent`, `delete_older_than` (the retention purge) and
  `purge_messages` remove them.
- Renaming an agent rewrites `agent_name` and `target_key` on its fills.

There is one test per site.

**AC9 — The snapshot.**
- A GleepGlorp join's `proposals_snapshot` carries `fills` (views, id
  order).
- With the fills read forced to fail, it still carries the proposals and
  `"fills": []`.
- The reverse is not promised. A failed proposals read still returns
  `None`, so the fills don't go either; that is today's behaviour.
- A non-GleepGlorp chat gets no frame, as today.
- `tests/browser/test_flow_chat_proposals.py` and the drawer chat tests
  pass unchanged: a client ignores the new key and frames.

**AC10 — Falsifications** (each edited out, run, restored by editing, and
recorded in the flight log):
- the page gate (AC3 fails);
- the `status`/`claimed_at` condition in `claim` (double-claim test fails);
- the token condition in `record_outcome` (stale-token test fails);
- the replacement `UPDATE` (AC2 replacement test fails);
- `fill_form` in `TRUSTED_TOOL_NAMES` (the taint test fails);
- the fills line in `ChatSessionRepository.delete` (AC8 delete test
  fails).

## Assertion edits allowed (and only these)

- **`tests/test_gleepglorp_build.py`:** add `"fill_form"` to the exact
  toolset sets (~:93, ~:103, ~:123, ~:137, `_BASE` ~:202), and change
  `len(agent._loaded_schemas) == 4` (~:109) to `== 5`. Add `fill_form`
  lines beside the `propose_change` not-in lines (~:155, ~:160). The matrix
  test (~:228) derives from `_BASE` and needs no edit.
- **`tests/test_notes_tools.py` ~:188:** add `"fill_form"` to the
  trusted-names list.
- **`tests/test_db_migration.py`:** the assertions that pin the **latest**
  version go from `54` to `55`: `CURRENT_VERSION == 54` and `== 54 ==
  CURRENT_VERSION`, plus the bare `== 54` reads of `MAX(version)` after a
  full `ensure_schema`. An assertion that pins a historical migration step
  stays as it is. If you can't tell which kind an assertion is, read the
  test.
  - The review's candidate list, each still to be checked: ~:5035, 5391,
    5537, 5678, 5684, 5817, 5969, 6016, 6375, 6388, 6580, 6875 (inside
    `TestSchemaV54`, but a latest-version pin), 7069, 7119 and 7141.
- **Any other test that pins `TRUSTED_TOOL_NAMES`, GleepGlorp's toolset or
  the latest schema version exactly:** add the new value and record each
  file and line in the flight log.
- **Nothing else.** Any other failing assertion is a `[BLOCKED]`.

## Verification Steps

1. Run the new tests and `tests/test_db_migration.py`,
   `tests/test_gleepglorp_build.py`, `tests/test_notes_tools.py`,
   `tests/test_gleepglorp_proposals_tool.py`, `tests/test_taint_results.py`,
   `tests/test_api_name_rule.py`, `tests/test_credential_gate.py`,
   `tests/test_gleepglorp_proposals_card_payload.py`,
   `tests/test_gleepglorp_proposals_store.py`,
   `tests/test_schema_template.py` and `tests/test_tool_exposure.py` with
   `-x -q`.
2. Run the unit tier once under `THE_ONE_TEST_NETNS=1`, recording the start
   `uptime`.
3. Run the static guards and `ruff check` / `ruff format --check` on
   `the_one/ tests/ scripts/ evals/`.
4. Run the browser lanes one at a time under `THE_ONE_TEST_NETNS=1` and
   `THE_ONE_REQUIRE_WEBKIT=1`: `chats-transcript` (the proposal cards and
   the snapshot), then `shared` (the drawer chat). **There is no full
   parallel run in this leg.** The batch B end runs it.
5. Run the AC10 falsifications.

## Implementation Guidance

- **Mirror the proposals store's style:** dataclasses, `_COLS`, `_row`,
  `write_transaction`, `now_iso`. Make the token with `secrets.token_urlsafe(18)`.
- **Lease comparison:** store `claimed_at` with `now_iso()`, and compare
  against `(now - 120 s).isoformat()` the way `delete_older_than` compares
  `updated_at` (lexical comparison on the same format).
- **Pushes happen after commit.** The view needs a read, so build it after
  the transaction.
- **The route module** follows `gleepglorp_proposals_api.py`: the `_api`
  late-binding shim and `get_connection` through it.
- **Building the tool:** take the agent's `TurnContext` with
  `current_turn.get()`, and the session from it or
  `current_chat_session_id`, exactly as `ProposeChangeTool.execute` does.
- **Test the approval-continuation refusal through the real seam**
  (`the_one/sessions/turn_host.py`), with a GleepGlorp agent scripted
  through `FakeLLM` to call `fill_form`. A hand-built `TurnContext` is not
  enough for that case.
- **No detached background loops.** Run the lanes one at a time, kill only
  recorded PIDs, and leave no process running.

## Edge Cases

- **A fill for an agent renamed after the fill:** the rename carry keeps it
  pointing at the agent. A fill for an agent deleted since: the view
  answers `target_gone: true`, and the claim still succeeds (Leg 6 reports
  `not_filled` / `target_gone`).
- **Two fills in one turn:** the second replaces the first if the first is
  still `sent`.
- **A fill in a chat with no subscribers** (the drawer socket closed): the
  row stays `sent`, the push is a no-op, and Fill now after a reload
  claims it.
- **The proposals snapshot and fills:** `proposal-cards.js` reads only
  `proposals`, which this leg must not change.
- **A `create` fill:** `base` is `None` and `stale` is `[]`.

## Hand-off to Leg 6 (recorded here so Leg 6's design picks it up)

- **`replaced` is "superseded", not an error.**
  - A claim 409 whose `status` is `replaced` means a newer fill took this
    one's place. The applier skips it quietly.
  - A `fill_changed` to `replaced` folds the receipt to one quiet line with
    no Fill now.
- **An `applying` fill is never replaced.** The applier in a window applies
  fills one at a time, in id order: it queues a `fill_requested` that
  arrives while another fill is applying. Two fills therefore never
  interleave in one editor.
- **Any window can claim.** The server can't tell which window sent the
  turn, so the sender-only rule (DD7) is the browser's. A losing window's
  claim is a 409, and it draws the receipt only.
- **Reason codes and receipt sentences:**
  - `in_chats`: "You were in Chats";
  - `stay`: the operator chose Stay;
  - `editor_unavailable`: the editor could not open;
  - `target_gone`: the agent no longer exists.

  Leg 6 owns the sentences.
- **A create fill's `values` include `name`.** It is written through the
  new `name` handle.

## Files Affected

- New:
  - `the_one/gleepglorp/fill/__init__.py`, `store.py`, `tool.py`,
    `events.py`;
  - `the_one/interfaces/web/gleepglorp_fills_api.py`;
  - `tests/test_gleepglorp_fill_store.py`,
    `tests/test_gleepglorp_fill_tool.py`,
    `tests/test_gleepglorp_fills_api.py` (names indicative).
- Changed:
  - `the_one/db/schema.py`, `the_one/db/repositories.py`;
  - `the_one/agent/taint.py`, `the_one/agent/factory.py`;
  - `the_one/gleepglorp/proposals/events.py`;
  - `the_one/interfaces/web/api.py` (router attach only);
  - the tests listed under "Assertion edits allowed";
  - `tests/test_db_migration.py` (new v55 tests);
  - the docs.
- **Not touched:**
  - `evals/` (Leg 7);
  - `the_one/agent/core.py`;
  - every file under `static/` (Leg 6);
  - the GleepGlorp prompt and guide (Leg 7).

## Citation Audit (2026-11-20, against the working tree on 0163769d + Leg 4)

| Citation | Checked |
|---|---|
| `schema.py` v54 block ~:3427-3462, `CURRENT_VERSION = 54` :18 | yes |
| `repositories.py` rename ~:503-517, delete ~:3304, delete_all_for_agent ~:3322, delete_older_than ~:3367, purge_messages ~:3387 | yes |
| `proposals/tool.py` `ProposeChangeTool.execute` / `_propose` | yes |
| `proposals/events.py::snapshot_frame` ~:37 | yes |
| `proposals/store.py::proposal_view`, `display_values`, `_name_map` | yes |
| `proposals/shape.py::normalize` ~:395, `AGENT_FIELDS` ~:71, `_agent_base` ~:499 | yes |
| `agent/taint.py::TRUSTED_TOOL_NAMES` ~:39 | yes |
| `agent/factory.py` ProposeChangeTool register ~:579, bind ~:817 | yes |
| `api.py` proposals router attach ~:7124 | yes |
| `_context.py::TurnContext.page` ~:108 | yes |
| `tests/test_gleepglorp_build.py` ~:93/103/123/137/155/160/202 | yes |
| `tests/test_notes_tools.py` ~:188 | yes |
| `tests/test_db_migration.py` `== 54` pins (~:5035, ~:5391, …) | yes |
| `tests/test_api_name_rule.py` proposals rows ~:57-62 | yes |
| `evals/harness.py::_clean_proposal_state` ~:583 (deferred to Leg 7) | yes |
