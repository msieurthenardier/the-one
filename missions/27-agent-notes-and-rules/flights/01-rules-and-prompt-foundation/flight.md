# Flight: Rules and the Prompt Foundation

**Status**: completed
**Mission**: [Agent Notes and Rules](../../mission.md)

## Contributing to Criteria

- [ ] **Rules shape new conversations** (whole criterion). The operator adds,
      edits, reorders, enables, disables and deletes rules. Every new web or
      connector conversation follows the enabled rules in order. A disabled rule
      has no effect.
- [ ] **Rules outrank notes, and the agent cannot touch rules** (the "cannot
      touch" half). No capability offered to the agent writes rules. The "rules
      outrank notes" half lands in Flight 2, once notes exist.
- [ ] **An agent's rules and notes follow it** (rules and revision-history half).
      Renaming an agent keeps its rules and its self-configuration revision
      history. Deleting removes them. Existing installs upgrade with no data
      loss. Flight 2 adds notes to the same cascade.
- [ ] **The UI says when changes apply** (rules half).

---

## Pre-Flight

### Objective

Give every agent an operator-authored, ordered list of rules that reaches each
newly built agent's system prompt after the persona. The operator manages the
list from a new **Rules and notes** tab in the agent editor (this flight builds
its Rules section). The open conversation's agent panel shows the rules
read-only, with a link to edit them. Underneath, the flight builds the one place
that composes an agent's full system prompt (base, persona, rules, and a slot
Flight 2 fills with notes). It moves the self-configuration `next_turn` path onto
that place, which fixes its dropped-base-prompt bug. And it makes agent rename
cascade through every agent-keyed table, which fixes the rename failure for
agents with revision history.

### Open Questions

- [x] How are rules keyed for the synthesized "default" agent? → DD3
- [x] `agent_revisions` fix: table rebuild or an explicit update in `rename`? → DD3
- [x] Where does the composition live, and how does the async `next_turn`
      settle path reach the rules store? → DD1, DD2
- [x] Rule limits and their unit → DD4
- [x] What does "in order" mean to the model? → DD5
- [x] Tab id, label, position and save model → DD6
- [x] What the chat agent panel shows → DD7
- [x] How the behavior test observes the composed prompt, given that no API
      returns a running agent's prompt → DD9

### Design Decisions

Decisions marked *(autonomous judgement call)* were made while the operator was
away (operator authorization, 2026-10-09). They are reviewed at the mission HAT
(Flight 3).

**DD1 — One prompt composer, extended.**
- `compose_system_prompt(base, persona, *, rules=(), notes=())` in
  `the_one/agent/config.py` stays pure and synchronous.
- Layers are joined in this fixed order: base, persona, rules, notes. They use
  the existing `\n\n---\n\n` separator, and an empty layer is omitted entirely
  (no stray separator, no empty heading).
- `notes` is accepted and ignored in this flight (always empty). Flight 2 fills
  it.
- The composed prompt always starts with `BASE_PROMPT`, so the degraded
  chat-only path (`core.py:459`, `startswith(BASE_PROMPT)`) keeps rules for
  chat-only models.
- Rationale: one function means no second composition can drift. That drift is
  exactly the cause of Known Issue 2.
- Trade-off: the signature grows by keyword arguments only, so existing
  positional callers and tests keep working.

**DD2 — An async layer loader shared by the factory and the `next_turn` path.**
- A new `the_one/agent/prompt_layers.py` exposes
  `async build_system_prompt(conn, agent_name, persona) -> str`. It loads the
  agent's enabled rules in position order, then calls `compose_system_prompt`.
- Its two callers:
  - `AgentFactory.create` step 3 (`factory.py:515`), which already holds `conn`.
  - `self_configuration/pending.py::apply_pending_revision`, which becomes
    `async`.
- The two settle sites (`app.py:2422` in `_process_and_broadcast` and
  `app.py:2495` in `_resume_paused_session`) are already `async def`. They
  `await` the call, keeping the load-bearing `or "default"`.
- The pending entry still carries only the raw persona text. The base and rules
  are recomposed at apply time.
- Rationale: fixes Known Issue 2 at its root, and keeps the rules read in one
  place.
- **Connection:** `build_system_prompt` takes an optional `conn`. When it is
  not given (the settle path), it calls `the_one.db.connection.get_connection()`
  itself.
- **Failure at settle must never break the turn.** The two settle sites sit
  directly before `{"type": "done"}`. If loading the rules raises (a locked
  database, a missing table in a test fixture), `apply_pending_revision` logs a
  warning and composes base + persona with no rules. It consumes the entry
  either way, so the turn still sends `done` and the base prompt is never lost.
  A test pins this with the rules read made to fail.
- **Existing tests that pin the bug.** They change as an intended contract
  change, not a regression:
  - `tests/test_self_configuration_write.py:426-433`;
  - `TestAC4HookRunsAtNonPausedSettleOnly` (`:502-560`).

  They assert `agent.system_prompt == "NEW"`, the raw persona. They now expect
  the composed prompt. All six callers are already async tests, so the only
  other change is `await`.
- **`AgentConfig.get_system_prompt()`** (`config.py:193-197`) is a second
  composition that only tests call. Delete it, and move its tests to
  `compose_system_prompt`, so no second composition can drift.
- **Known limitation, documented in `the_one/agents.md`:**
  - A self-revision that settles in an open web conversation reloads the rules
    at that moment. Rules can therefore reach an open conversation earlier than
    the UI line says.
  - An agent renamed while a web conversation is open settles under the old
    name and gets no rules until the next rejoin. This is rare and was accepted.
- Trade-off: `apply_pending_revision` now does a DB read at turn settle. It is
  one indexed `SELECT`, and only when an entry is pending.

**DD3 — Foreign keys that follow renames; `agent_revisions` rebuilt to match.**
- A new table `agent_rules`:
  - columns: `id TEXT PRIMARY KEY`,
    `agent_name TEXT NOT NULL REFERENCES agents(name) ON DELETE CASCADE ON UPDATE CASCADE`,
    `text TEXT NOT NULL`, `enabled INTEGER NOT NULL DEFAULT 1`,
    `position INTEGER NOT NULL`, `created_at TEXT NOT NULL`,
    `updated_at TEXT NOT NULL`;
  - index `(agent_name, position)`.
- The same migration rebuilds `agent_revisions` with `ON UPDATE CASCADE` added
  to its `agent_name` foreign key. It follows the v37 rebuild ceremony
  (`schema.py:2180-2220`: `executescript` with `PRAGMA foreign_keys=OFF`, copy
  all columns, drop, rename, recreate the index, foreign keys back on), with
  two corrections:
  - **The self-reference names the final table.** Declare
    `restored_from TEXT REFERENCES agent_revisions(id) ON DELETE SET NULL`, not
    `agent_revisions_new(id)`. The v37 form relies on `ALTER TABLE ... RENAME`
    rewriting the reference, which happens only while `legacy_alter_table` is
    off. That is an environment default the packaged build's bundled SQLite
    library could flip. Naming the final table is correct under both settings
    (prototyped at review).
  - **The idempotency guard reads `PRAGMA foreign_key_list(agent_revisions)`.**
    It rebuilds only when the row whose `table` is `agents` has
    `on_update != 'CASCADE'`. It runs only when the table exists, as v37 guards
    (`schema.py:2172-2175`).
- **The migration test** lives in `tests/test_db_migration.py`, which is
  already allowed to call `ensure_schema` directly. It migrates a populated v41
  database (revisions including a `restored_from` chain), then asserts:
  - every row and the index are kept;
  - `PRAGMA foreign_key_list(agent_revisions)` shows `agents` with update and
    delete `CASCADE`, and `agent_revisions` (not `_new`) with delete
    `SET NULL`;
  - a rename inside a transaction succeeds and carries revisions and rules.
- This is migration **v42**, and `CURRENT_VERSION` becomes 42. Flight 2 adds its
  own.
- `SQLiteAgentStore.rename` stays a plain `UPDATE agents SET name`: the cascade
  does the rest. It also keeps the manual `chat_sessions` update, since that
  table has no foreign key.
- `agent_revisions` is the only table with a foreign key to `agents(name)` in
  a migrated database. `chat_sessions` lost its foreign key in v5. Confirmed at
  review.
- `SQLiteAgentStore.save` upserts with `ON CONFLICT ... DO UPDATE`
  (`repositories.py:224`), not `REPLACE`, so a General-tab save cannot delete
  rules through the cascade.
- "default" has no special case. Rules are reachable only through routes that
  404 for an agent with no stored row, and the synthesized default agent has no
  provider, so it cannot chat (`factory.py:304-309`). A rules lookup for an
  agent with no row returns no rules.
- Rationale: the cascade removes the trap for every future agent-keyed table
  instead of patching `rename` once per table.
- Trade-off: a table rebuild migration is more ceremony than a one-line
  `UPDATE`. The v37 precedent makes it routine.

**DD4 — Rule limits, counted in characters** *(autonomous judgement call)*.
- Each rule is 1 to **500** characters after trimming whitespace.
- All of an agent's rules together, enabled or not, total at most **4,000**
  characters.
- The total counts disabled rules, so enabling a rule can never fail.
- A violation is a 422 with a plain message ("Rules are limited to 4,000
  characters in total; this would make 4,212."). The UI shows the message
  inline and a live character count.
- Constants live in one place (`the_one/agent/rules.py` or beside the
  repository) and are returned by `GET .../rules` as `limits`.
- Rationale: about 1,000 tokens at most, which fits small local context windows
  beside the 2,547-character base prompt. Rules are meant to be short
  directives.
- Trade-off: a long policy document does not fit. That belongs in the persona or
  a knowledge base.

**DD5 — How rules read to the model** *(autonomous judgement call)*.
- The rules layer is:
  ```
  Rules set by the operator for this agent. Follow every rule. If two rules
  conflict, the one listed first wins.

  1. {rule}
  2. {rule}
  ```
- Only enabled rules appear, numbered in position order.
- Flight 2 adds the sentence placing rules above saved notes, when it adds
  notes.
- Rationale: "in order" in the mission becomes a concrete conflict rule the
  operator can steer by reordering.

**DD6 — The Rules and notes tab** *(label, position and save model are an
autonomous judgement call)*.
- **Position:** a new agent-editor tab, label **"Rules and notes"**,
  `data-tab-id="rules-and-notes"`, testid `tab-rules-and-notes`, route
  `#agents/{name}/rules-and-notes`. It sits second, after General, because it
  is the closest to the persona.
- **Rules section** (heading "Rules"):
  - an ordered list, each row with the rule text, an `App.ui.toggle` (on/off),
    Edit, Move up, Move down and Delete (arm, then confirm, via
    `App.confirmDelete`);
  - an "Add rule" textarea with a live character count;
  - the line "Changes apply to new and reopened chats, and to the next message
    in connector channels.";
  - an empty state when there are no rules.
- **Save model:** every control saves immediately through the REST API, like
  the Self-configuration tab. None of it joins the General form's Save/Cancel
  dirty state, so the leave guard ignores it.
- **Reordering** uses buttons, not drag, for keyboard and screen-reader access.
- **Create mode** (no saved agent) shows "Save the agent first to add rules."
- **Construction:** the tab is DOM-built (no HTML-string sinks) from `App.ui`
  controls in a new `areas/studio/rules-notes-tab.js`.
- **Wiring:** the editor scaffold (`agent-editor.js:56-62` `PANEL_IDS`, tab
  buttons, panels) and studio's tab whitelist (`studio.js:248`) gain the id.
- **Existing tests and docs this breaks**, which leg 2 updates:
  - `tests/browser/test_flow_agent_tabs.py:85` expects 5 tabs.
  - `test_flow_agent_tabs.py:124` and `:147` press ArrowRight from General and
    expect Knowledge.
  - `tests/browser/test_flow_agents_scale.py:260` expects 5 tabs.
  - `docs/ui-testid-registry.md:293` calls `tab-self-configuration` the "fifth"
    tab.
- **Width at the supported minimum.** `test_flow_agents_scale.py:261-263`
  asserts the tab strip fits on one row with no overflow at 1024×768, in
  Chromium and WebKit. Measure the strip with the new tab before settling the
  label. If "Rules and notes" does not fit, label it **"Rules"** for this
  flight and keep the id `rules-and-notes`, with Flight 2 to revisit. Never
  relax the no-overflow assertion.
- **Unsaved text is not guarded.** Text typed into Add rule or an inline edit
  is lost on navigation without a prompt, as on the Self-configuration tab,
  because the tab's controls do not join `App.nav`. This is accepted for this
  flight and documented, and flagged for the HAT *(autonomous judgement
  call)*.
- Rationale: the operator decided one tab with two sections. Immediate saves
  suit a list (M21 precedent).
- Trade-off: two save styles exist within the agent editor, one per tab, as
  they already do with Self-configuration.

**DD7 — Rules in the chat agent panel** *(autonomous judgement call)*.
- `agent-drawer.js` gains a **Rules** group inside "What it can use", built with
  the existing `group(...)` helper (`agent-drawer.js:276`).
- It lists the enabled rules in order, each clamped to two lines with the full
  text in a `title`.
- When some rules are off it adds "{n} off". With none it shows "No rules".
- An "Edit rules" link goes to `#agents/{name}/rules-and-notes`.
- The `group(...)` helper (`agent-drawer.js:276-290`) only takes `{name, meta}`
  items and renders "None" when the list is empty. Extend it, or add a sibling
  builder, for "No rules", "{n} off" and the link.
- A 404 from the rules route (an agent with no stored row) shows "No rules", not
  "Couldn't load".
- The rules are fetched once per panel open, beside the existing
  self-configuration fetch (`agent-drawer.js:430`).
- The panel shows the rules as **saved**, which is what the next build of the
  agent uses. It does not claim they are in an already-open conversation.

**DD8 — REST surface.** All routes 404 for an unknown agent and sit behind the
existing credential gate.
- `GET /api/agents/{name}/rules` returns `{rules: [{id, text, enabled, position,
  created_at, updated_at}], limits: {rule_chars, total_chars}}`.
- `POST /api/agents/{name}/rules` takes `{text, enabled?}` and appends. It
  returns 201 with the rule.
- `PUT /api/agents/{name}/rules/{id}` takes `{text?, enabled?}`.
- `DELETE /api/agents/{name}/rules/{id}`.
- `PUT /api/agents/{name}/rules/order` takes `{ids: [...]}`. It must be an exact
  permutation of the agent's rule ids, or it is a 422. Positions are rewritten
  densely inside one transaction.
- A rule id belonging to another agent is a 404.
- `PUT /api/agents/{name}` (the General form) never touches rules.
- No agent-facing tool, MCP source or self-configuration capability reaches
  these routes. The self-configuration surface's read projection and write
  allowlist are unchanged.

**DD9 — Behavior-test apparatus: act through browser and HTTP, observe through
replies and the stored session** *(autonomous judgement call)*.
- **Act:** the browser drives the Rules and notes tab and the chat. HTTP (with
  the credential) and the stub connector seam drive the connector conversation.
- **Observe, model adherence:** the first reply of a **fresh** conversation,
  carrying a sentinel. The `agent-self-revision-propagation` spec established
  that a sentinel is reliable only on a fresh conversation's first turn.
- **Observe, composition:** the persisted session's system message. It is the
  read path: `_save_session_to_db` encodes `agent.messages` including the system
  message (`app.py:1621-1640`, `encode_messages`), and so does the connector
  path (`inbound.py:458`). The Executor reads it with `sqlite3` from the scratch
  data directory's database (shell apparatus). This shows rule order,
  disabled-rule absence and the base-prompt prefix without trusting the model.
- **Provider:** the operator's local Ollama (`localhost:11434`; `gpt-oss:20b`
  and `qwen3:30b` present at planning) as an `ollama` provider in the scratch
  instance. No key or external account is needed.
- Spec: `tests/behavior/agent-rules-round-trip.md`.

**DD10 — Test placement.**
- Unit tests build databases from the schema template.
- The migration test replays the real chain and is added to `tests/test_schema_template.py`'s
  `ALLOWED_DIRECT_CALLERS` only if it calls `ensure_schema` directly.
- The new browser test file is `tests/browser/test_flow_agent_rules.py`, which
  lands in the `agents` lane through its `test_flow_agent_*` glob. That lane is
  at 394 s of a 510 s budget.
- Drawer additions go into `tests/browser/test_flow_chat_drawer.py` (`chats`
  lane, 271 s of 360 s).
- No lane-table change is needed.

### Citation Audit

Verified against the working tree at `77308c5`:

| Citation | Status |
|---|---|
| `the_one/agent/config.py::compose_system_prompt` (`:82`) — pure, sync, `(base, persona)`, joins with `"\n\n"` and a `"---"` part | verified |
| `the_one/agent/factory.py::AgentFactory.create` step 3 (`:515`) — the single production caller; `conn` already in scope (`:319`). `AgentConfig.get_system_prompt()` (`config.py:193-197`) is a second, test-only composition, which DD2 deletes | verified (corrected at review) |
| `the_one/agent/factory.py:304-309` — `create` raises `ProviderNotConfiguredError` when `provider_config_id` is None (the synthesized default has none, `:553-558`) | verified |
| `the_one/agent/core.py:459` — degraded path checks `self.system_prompt.startswith(BASE_PROMPT)` | verified |
| `the_one/self_configuration/pending.py::apply_pending_revision` (`:75`, `:94-97`) — sync; sets `agent.system_prompt` and `messages[0]` to the raw persona text | verified |
| `the_one/interfaces/web/app.py:2422`, `:2495` — the two settle call sites, both inside `async def` (`_process_and_broadcast` `:2027`, `_resume_paused_session` `:2430`), passing `session.agent_name or "default"` | verified |
| `the_one/db/schema.py:2061`, `:2195` — `agent_revisions.agent_name ... REFERENCES agents(name) ON DELETE CASCADE`, no update action | verified |
| `the_one/db/schema.py:2180-2220` — v37 rebuild ceremony (`executescript`, FK off, copy, drop, rename, index, FK on) | verified |
| `the_one/db/repositories.py::SQLiteAgentStore.rename` (`:323`) — updates `agents` and `chat_sessions` only, in one `write_transaction` | verified |
| SQLite semantics — parent-key `UPDATE` with a child row and no update action fails `FOREIGN KEY constraint failed` (reproduced on a minimal schema, 2026-10-09) | verified |
| `the_one/db/connection.py:55`, `tests/_schema_template.py:45,95,111` — `PRAGMA foreign_keys=ON` on production and template connections | verified |
| `the_one/interfaces/web/app.py:1621-1640` / `connectors/inbound.py:458` — sessions persist `encode_messages(agent.messages)` including the system message | verified |
| `the_one/interfaces/web/static/js/areas/studio/agent-editor.js:56-62` (`PANEL_IDS`) and `areas/studio.js:248` (tab whitelist) | verified |
| `the_one/interfaces/web/api.py::delete_agent` (`:933`) / `rename_agent` (`:948`) — store call, then `self_configuration_manage` cascade | verified |

### Prerequisites

- [x] Mission 27 approved and active.
- [x] Working tree clean on `main` at `77308c5`.
- [x] Local Ollama reachable at `localhost:11434` with a tool-capable model
      (`gpt-oss:20b`, `qwen3:30b`). **Re-verify before the behavior-test run**:
      it is an external daemon.
- [ ] Dev instance port for the behavior test: 8490 or higher, never 8484 or
      8485, with a scratch data directory. Check at run time that the port is
      free.

### Pre-Flight Checklist

- [x] All open questions resolved
- [x] Design decisions documented
- [x] Citation Audit complete
- [x] Prerequisites verified (the Ollama re-check is at run time)
- [x] Validation approach defined
- [x] Legs defined

---

## In-Flight

### Technical Approach

**Leg 1 (backend)** lands first, since the UI depends on it:
- migration v42;
- the repository;
- the composer and loader;
- factory and `next_turn` wiring;
- the REST routes;
- unit tests for each, including:
  - the rename and delete cascade with revisions and rules present;
  - a `next_turn` revision that keeps the base prompt and rules;
  - the chat-only degraded path keeping rules;
  - a mock-provider web turn and a stub-connector turn whose persisted system
    message holds the rules.

**Leg 2 (UI)** builds:
- the tab;
- the drawer group;
- testid registration (`docs/ui-testid-registry.md`);
- the `the_one/agents.md` and CLAUDE.md entries;
- browser tests.

The behavior test runs after both legs land, on a dev instance built from the
flight branch.

### Checkpoints

- [x] v42 migrates a populated v41 database: revisions are kept, and renaming an
      agent that has revisions now succeeds.
- [x] A built agent's system prompt is base, persona, then numbered enabled
      rules, on web, connector and chat-only paths.
- [x] A `next_turn` self-revision keeps the base prompt and rules.
- [x] Studio's Rules and notes tab manages rules end to end, and the drawer
      shows them.
- [x] `make gate` is green.
- [x] `agent-rules-round-trip` behavior test passes.

### Adaptation Criteria

**Divert if**:
- The `agent_revisions` rebuild cannot keep its data (`restored_from`
  self-references) or index under the guarded ceremony.
- Making `apply_pending_revision` async reveals a sync caller outside the two
  settle sites.

**Acceptable variations**:
- Limit values, prompt wording, the drawer's clamping and the tab's internal
  layout. Record each in the flight log for the HAT.
- Module placement of the rules constants and repository.

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned
> and created one at a time as the flight progresses. This list will evolve
> based on discoveries during implementation.

- [x] `rules-backend` — v42 (`agent_rules` + the `agent_revisions` rebuild), the
      rules repository and limits, the extended composer and async loader,
      factory and `next_turn` wiring (fixes Known Issues 1 and 2), REST routes,
      unit and migration tests, and `the_one/agents.md` for the backend
      contract. If it overruns, split the REST routes into their own leg.
- [x] `rules-ui` — the Rules and notes tab (Rules section), the drawer's Rules
      group, testid registry, browser tests, and the CLAUDE.md and
      `the_one/agents.md` UI entries

No HAT leg: the mission ends with a dedicated HAT flight (operator decision).

---

## Post-Flight

### Completion Checklist
- [x] All legs completed
- [ ] Code merged
- [x] Tests passing (`make gate`)
- [x] Documentation updated (`the_one/agents.md`, CLAUDE.md, testid registry)
- [x] Behavior test `agent-rules-round-trip` run and logged

### Verification
- `make gate` green (unit, then all browser lanes).
- `tests/behavior/agent-rules-round-trip.md` passes against a dev instance on
  the local Ollama provider.
- Mission Known Issues 1 and 2 ticked, each with its pinning test named.
