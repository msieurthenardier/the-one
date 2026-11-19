# Flight: Proposals and approval

**Status**: in-flight
**Mission**: [GleepGlorp, the In-App Assistant](../../mission.md)

## Contributing to Criteria

- [ ] **GleepGlorp proposes; the operator approves.**
  - For agents, their rules and their routines (operator decision,
    2026-11-19: the other kinds of item come with form filling in a later
    flight).
  - One proposal per step, and Approve starts the next step.
  - Field-level apply through the forms' own validation.
  - Errors and stale refusal shown on the card. Dismiss changes nothing.
  - An open agent editor follows the change without overwriting an unsaved
    edit.
- [ ] **Nothing changes without the operator's click.**
  - The proposal tool only records a proposal, and the allowlist test is
    extended.
  - No route GleepGlorp can reach applies one, and no setting relaxes this.
- [ ] **Secrets never pass through GleepGlorp.**
  - Proposals carry no secret-bearing field.
  - The server refuses a proposal whose text holds a stored secret value or a
    key-shaped string.
- [ ] **GleepGlorp sticks to the app.**
  - A proposal made after GleepGlorp read untrusted content is marked "Check
    this" and names where that content came from.
  - A flagged routine stays flagged when applied.
  - GleepGlorp cannot propose a delete.
- [ ] **Quality is measured on every default eval model.**
  - The GleepGlorp scenario set is extended to proposals under the eval method
    adopted in DD13, with a new baseline.
  - qwen3-4b is measured only (operator, 2026-11-19).

---

## Pre-Flight

### Objective

Let GleepGlorp change the app by proposal.
- **Proposing.** Asked in a chat to create or change an agent, one of its
  rules or one of its routines, GleepGlorp records a proposal.
- **The card.** The chat shows the proposal as a card: what will change, field
  by field, with Approve and Dismiss.
- **Approving.**
  - Approve applies exactly those fields through the same validation the forms
    use.
  - It refuses a stale proposal unless the operator approves it anyway.
  - It starts GleepGlorp's next turn, so a request with several steps
    continues one step at a time.
- **Open editors.** An agent editor that is open on the changed agent shows
  the new values, and never overwrites an unsaved edit.
- **Evals.** The evals gain proposal scenarios and checks. The eval method the
  operator adopted (DD13) is written down and used to tune GleepGlorp's prompt
  for proposals.

### Open Questions

- [x] **Which kinds of item can be proposed in this flight?** → Agents, their
      rules and their routines (operator, 2026-11-19). See DD2.
- [x] **Does Approve start GleepGlorp's next turn?** → Yes (operator,
      2026-11-19). Dismiss does not. See DD8.
- [x] **The stale-check record** (the mission's open question for this flight):
      a snapshot of the fields a proposal changes, or a version for the whole
      row? → A snapshot of the touched fields, compared under the write lock.
      See DD4.
- [x] **Card layout, how the approval shows, the editor note, the states?** →
      Board options A, B and A, and the states as drawn (operator,
      2026-11-19). See Mockups.
- [x] **The eval method?** → Adopted as outlined (operator, 2026-11-19). See
      DD13.
- [x] **qwen3-4b: supported or measured only?** → Measured only (operator,
      2026-11-19). See DD13.
- [x] **A HAT leg closing this flight?** → Yes (operator, 2026-11-19). See
      DD14.
- [x] **What if one turn tries a second proposal while one is open?** → It
      replaces the open one when that one failed or targets the same item, and
      is refused otherwise. See DD5.
- [x] **Who creates an approved routine?** → `created_by="operator"`, since
      the click is the operator's. Its flag carries GleepGlorp's untrusted
      sources. See DD3 and DD9.
- [x] **Does a stale result survive a reload?** → No. Stale leaves the status
      unchanged, so a reload shows Waiting and the next Approve shows the
      stale panel again. See DD4.
- [x] **Routine caps, and the "Immediately" start?** → A proposal is applied
      with the operator's caps, since the click is the operator's. A proposal
      gives an absolute start; the now-start shape is refused, as it is for the
      agent tools. See DD2.
- [x] **Does an agent created by a flagged proposal keep a flag?** → No (no
      flag column on agents or rules). A routine keeps its flag through apply.
      The residual risk is recorded in SECURITY-MODEL. See DD9.

### Design Decisions

**DD1. One change shape, defined once, for proposals now and form filling later**
- **Choice:**
  - A package, `the_one/gleepglorp/proposals/`, holds the change shape
    (`shape.py`). For each proposable kind it declares the fields a proposal
    may set:
    - its type, and its allowed values or range;
    - whether it is required on create;
    - the label the card shows;
    - how the current value is read.
  - Everything else derives from this one declaration:
    - the validation of a proposal's shape (before the forms' own
      validation, DD3);
    - the card's field labels (served with the proposal, so the client keeps
      no copy);
    - the eval checks' field names;
    - the field definitions GleepGlorp reads (DD5).
  - A kind that is not declared cannot be proposed.
- **Rationale:** the mission's planning decision ("one change shape": one
  schema, one validator, one taint path, one eval check). Flight 3's form
  filling reuses it, so later kinds add declarations, not new mechanisms.
- **Trade-off:** the declaration repeats field facts that live on
  `AgentConfig` and the rule and routine models.
  - A unit test pins each declared field to a real model field of the same
    type.
  - The shape may be stricter than the model (for example `max_iterations`,
    which has no bound on `AgentConfig`, `agent/config.py:142`), never looser.

**DD2. What can be proposed in Flight 2**
- **Kinds and actions:** `agent`, `rule` and `routine`, each with `create` and
  `change`.
- **There is no delete action anywhere.** "Turn off" is a change of a rule's or
  routine's `enabled` field.
- **Agent fields:**
  - `name`, on create only (renaming carries references and stays an editor
    action);
  - `description`, `system_prompt`;
  - `provider_config_id` and `llm_model`, always together;
  - `enabled_tools` and `disabled_tools`, `mcp_source_ids`, `kb_ids`;
  - `rich_visuals`, `notes_enabled`, `max_iterations`,
    `chat_history_retention_days`.
- **Agent fields that are never proposable:**
  - `secret_ids`, `tool_overrides` and `mcp_overrides`, because they carry or
    unlock credentials;
  - the switches that decide what an agent may do to itself
    (`self_revision_requires_approval`, `routines_self_config_enabled`,
    `routines_require_approval`), which are the operator's call alone.
- **Rule fields:** `text`, `enabled`, and position on create (last by
  default).
- **Routine fields:** `name`, `prompt`, `enabled`, and the schedule as the
  canonical `{start, repeat, ends}` with an absolute start.
  - The now-start shape (`{"start": {"now": true}}`) is refused, as it is for
    the agent tools.
  - A start that has passed by the time of approval is the routine service's
    own refusal, shown as "Couldn't apply".
  - Apply uses the operator's caps.
- **Names and ids:**
  - In the tool's input, a provider, MCP server or knowledge base is named,
    because GleepGlorp reads names.
  - The tool resolves each name to an id when the proposal is made. A name
    that matches no item, or more than one, is refused with a plain sentence.
    Only agents and secrets have unique names (`naming.py`).
  - The row stores ids. The card shows the current display names.
  - The self-configuration surface's id is never shown in `mcp_source_ids` and
    never compared there. The server carries it itself
    (`carry_surface_attachment`).
- **A rule or routine change needs a target that already exists** when the
  proposal is made.
- **Rationale:**
  - The operator's scope (agents with their rules and routines) covers both
    behavior tests and every multi-step request about an agent.
  - The excluded fields are exactly those that grant credentials or self-change
    powers.
- **Trade-off:** "rename my agent", secret grants and per-tool overrides stay
  in the editor. GleepGlorp says so and links to the agent's page.

**DD3. Approval runs the forms' validation, extracted into services that check under the write lock**
- **Today:**
  - Agent create and update validate inline in the route handlers
    (`api.py::create_agent`, `api.py::update_agent`).
  - The helpers raise `HTTPException` directly (`_validate_tool_overrides`,
    `_validate_secret_grants`, `_check_agent_provider`,
    `_normalize_surface_fields`, `_validate_mcp_override_credentials`).
  - `AgentStore.save` (repositories.py:270) opens its own `write_transaction`.
    That transaction refuses re-entry from its own task
    (`db/_write_lock.py`), so a caller cannot wrap a compare around it.
  - Rule writes are inline handlers too.
- **The agent service:** `the_one/agent/service.py`.
  - **One error type for routes and the card.** `AgentWriteError(status,
    detail)` carries exactly today's `detail` payloads. Each route maps it with
    one `HTTPException(e.status, e.detail)`, so every 422 `loc` list and 409
    body stays byte-identical. The card maps the same `detail` list to field
    labels by `loc[0]`. This is the routines precedent (`RoutineFieldError` to
    `_routine_422`).
  - **What stays in the routes:** `_read_json`, the 404 text and the response
    builders.
  - **What moves to the service:** `_evict_changed_mcp_credentials` runs in the
    service after commit.
  - **`create_agent(fields)`:** the create route's checks, in today's order.
  - **`replace_agent(body)`:** one core that holds the PUT's omit rules: the
    reset defaults for an omitted description, prompt, model and tools, and the
    surface row in `mcp_source_ids`. The PUT route calls it, so the
    whole-body semantics live in one place.
  - **`change_agent(name, changes, base, override)`** wraps that core:
    - Builds the body from a fresh load of the stored row, plus `changes`.
    - Never puts `mcp_overrides` in the body, so stored credentials are not
      re-validated as if they were incoming.
    - Validates the result with the PUT's checks.
    - Saves through `AgentStore.save(cfg, precheck=…, on_commit=…)`. This new
      hook runs under the lock, as `AgentRoutineRepository.update(precheck=…)`
      does (`routines/repository.py:251-286`). It re-reads the row:
      - A touched field that differs from `base` is a stale error that names
        it. `override` bypasses only this compare.
      - An untouched field that differs from the snapshot the merge used is a
        concurrent Save that landed between load and save. The service
        re-merges from a fresh load and retries, at most twice. It never shows
        this as stale, and never reverts that Save, override or not.
    - `on_commit` marks the proposal in the same transaction (DD4's
      transitions).
  - **What the routes call:** the create and update routes call the service,
    so Save and Approve run the same code.
- **The rule service:** `the_one/agent/rules_service.py`, for create and
  change, with the rule routes' checks. Its repository
  (`AgentRuleRepository.create`/`update`) gains:
  - a `position` argument on create (one transaction instead of create plus
    `reorder`);
  - a `precheck`;
  - an `on_commit` operation.
- **Routines:**
  - They use `create_routine` and `update_routine` with their existing
    `precheck`.
  - The repository already calls `proposal.run(conn, id)` duck-typed
    (`routines/repository.py:241,285`), so a `gleepglorp_proposals` operation
    with the same method plugs in. Only the type hint is generalised.
  - An approved routine is stored with `created_by="operator"`, and its flag
    carries GleepGlorp's untrusted sources (DD9).
- **Guard:** every existing agent, rule and routine API test and browser test
  passes unchanged.
- **Rationale:**
  - The mission constraint ("through the app's own validation, as a
    field-level change, never a whole-body replace").
  - The Architect's recommendation recorded in the mission.
  - Calling routes in-process would drag in the credential gate and the HTTP
    error shape.
- **Trade-off:** this touches the agent write path, which is high-risk. It
  gets its own leg (Leg 1) with a design review.

**DD4. The proposal store: one GleepGlorp table, field snapshots**
- **Table:** schema v54 adds `gleepglorp_proposals`. It has no foreign key to
  `agents` (GleepGlorp is not a row, and the target of a create does not exist
  yet) or to `chat_sessions`. Columns:
  - `id`, `session_id`, `tool_call_id`, `kind`, `action`;
  - `target`: an agent name, plus the item's id for a rule or routine; null
    for an agent create;
  - `changes`: JSON, each field mapped to its proposed value (ids, not names);
  - `base`: JSON, each touched field mapped to the value read when the
    proposal was made;
  - `status`: `pending`, `applied`, `dismissed`, `withdrawn` or `failed`;
  - `result`: JSON, what apply returned or the error detail list;
  - `untrusted`, `untrusted_sources`, `created_at`, `resolved_at`.
- **Stale:**
  - At approval, the service's precheck (DD3) compares each touched field with
    `base`.
  - A difference is a 409 `{"error": "stale", "fields": [{field, current,
    proposed}]}`, and `?override=true` applies anyway.
  - This is the routine queue's `_stale_precheck`
    (`routines/service.py:666`), made generic.
  - Lists such as `mcp_source_ids` and tools are compared as whole lists,
    without the surface id.
  - A create has no base. A name taken since the proposal was made is the
    forms' own 409, shown as "Couldn't apply".
- **Withdrawn:** a target that is gone is worked out when the proposals are
  read, never written during a join. Approving such a proposal marks it
  `withdrawn`.
- **Status transitions:**
  - The precheck reads the proposal's own status first. An `applied` row
    answers "already applied" without comparing fields, so a double Approve
    never looks stale.
  - `on_commit` marks `applied` only `WHERE status IN ('pending', 'failed')`,
    with a row-count check. So Try again on a `failed` row works, and a
    proposal applies once.
  - `failed` is written only `WHERE status IN ('pending', 'failed')`, never
    over `applied`.
  - A stale refusal leaves the status unchanged.
  - Dismiss and withdraw act only on a `pending` or `failed` row.
- **Deleting:**
  - Deleting a chat deletes its proposals at every chat-delete site, since no
    foreign key cascades: `delete`, `delete_all_for_agent` and
    `delete_older_than` (repositories.py ~3211, ~3233 and ~3273).
  - Purging a chat's messages deletes them too, because their anchors are
    gone (`POST /chat/sessions/{id}/purge` → `purge_messages`,
    repositories.py ~3279).
  - The daily purge removes them with their chats.
  - An agent rename carries `target`, as the naming rule carries references.
- **Rationale:**
  - No reliable row version exists: `updated_at` is skipped by some MCP writes
    and not exposed on `AgentConfig`.
  - Field snapshots give a per-field "Now" column, and they are not made stale
    by an unrelated field.
- **Trade-off:** a whole-list compare makes an attach stale if another attach
  landed in between. The card shows both lists.

**DD5. GleepGlorp's proposal tool**
- **One tool:** `propose_change(kind, action, target?, changes)`.
  - It is registered for GleepGlorp alone, outside every operator filter (as
    `read_app_config` is), and is always on while GleepGlorp is enabled.
  - Its schema stays thin (`changes: object`), with the allowed fields named
    in the description. A token budget for that description is set at Leg 2's
    design.
  - The full field definitions are a new `fields` kind of `read_app_config`,
    generated from DD1.
- **On a call, the tool:**
  1. validates the shape;
  2. resolves names to ids (DD2);
  3. reads the touched fields' current values as `base`;
  4. runs the secret guard (DD9);
  5. computes the taint (DD9);
  6. writes the row and pushes the card (DD6).

  It returns a short text: "Proposal 12 is waiting for the operator. Nothing
  has changed yet." A refusal is returned as a plain sentence, so the model can
  fix the call.
- **One step at a time:** a chat has at most one open proposal (`pending` or
  `failed`).
  - A new proposal replaces the open one when that one is `failed` (so
    GleepGlorp can correct it) or targets the same item. The replaced proposal
    becomes `withdrawn`, "replaced by the proposal below".
  - Otherwise the new proposal is refused: "Proposal 12 is still waiting for
    the operator. Wait for their answer before the next step."
  - The chat comes from `TurnContext.session_id` (`agent/_context.py:98`, with
    `current_chat_session_id` as the fallback, as the routine tools use). The
    eval harness sets it.
- **Allowlist:**
  - `tests/test_gleepglorp_build.py` gains `propose_change` in every
    combination.
  - A new test proves that a `propose_change` call changes no configuration
    table. It dumps every table except `gleepglorp_proposals` before and after
    the call.
- **Rationale:**
  - One tool keeps the schema count and token cost down for small models.
    Flight 1 measured 182 tokens for GleepGlorp's two tools.
  - "One pending per chat" enforces the mission's "one proposal per step".
- **Trade-off:** one wide tool instead of three narrow ones. The eval screen
  (DD13) reports tool-call validity. Three tools is the fallback if Haiku
  falls below its bar, recorded as a deviation.

**DD6. The card is drawn from the proposal row, below the turn's work group (board option A)**
- **Live:** a new frame, `proposal_changed {proposal}`, goes to the chat's
  subscribers (`sessions/_broadcast.py::broadcast_to_session`) when a proposal
  is created and on every status change.
- **Reload:**
  - `session_joined` carries the chat's proposals, in both its ready and
    degraded builders (`app.py` `_build_session_joined_ok` and the degraded
    path), so the cards are usable while GleepGlorp is off or needs a model.
  - This is chosen over a GET, which would race the live frames.
  - `_build_session_joined_ok` is synchronous (`app.py:2186`, seven call
    sites). Leg 6's design chooses between making it async and prefetching at
    each call site.
- **Placement:**
  - The card goes after the work group of the turn whose `propose_change` call
    made it (`tool_call_id` on the row). This is how the sign-in block is
    placed (`areas/chat/sign-in.js`, "never inside it").
  - It also goes after that turn's reply bubble, which lands at `done`, so the
    reply's "here's the first step" reads before the card.
- **Look:** the board's option A field table:
  - Now and Proposed columns for a change, and Show all for long text;
  - one primary Approve and a secondary Dismiss;
  - the states as drawn, with their tones.
- **Built from library controls:** `section`, rows, `button`, `banner`,
  `status` and `noteFlag`.
  - `noteFlag`'s `subject` gains `'proposal'`.
  - A new row control, if one is needed, gets its catalogue row and its
    Chromium and WebKit contract tests.
- **Where the code lives:** `areas/chat/proposal-card.js`. `transcript.js`'s
  `clearLog` destroys every card handle.
- **Rationale:** the row is the truth. The tool's text is for the model and is
  never parsed by the client.

**DD7. Approve and Dismiss: the routes and the apply**
- **Routes:** `interfaces/web/gleepglorp_proposals_api.py`, following the
  `routines_api.py` and `secrets_api.py` pattern. They are operator-only,
  behind the credential gate:
  - `GET /api/gleepglorp/proposals?session_id=`;
  - `POST /api/gleepglorp/proposals/{id}/approve[?override=true]`;
  - `POST /api/gleepglorp/proposals/{id}/dismiss`.

  GleepGlorp has no HTTP tool. The real controls are the credential gate and
  POST-only routes. `fetch_url`'s loopback block is a default that the operator
  can widen.
- **The apply:** a shared function, `proposals/apply.py::apply_proposal(id,
  override)`, called by both the route and the eval harness.
  - It applies through DD3's services.
  - It marks the row in the same transaction, following DD4's transitions, so
    a double Approve applies once and Try again works.
  - It returns the result or the error detail.
- **Server-side refusals:**
  - Approve and Dismiss are refused with a 409 while GleepGlorp's turn in that
    chat is running (`is_session_busy`). The client also disables the buttons.
  - A failed apply (the forms' 409 or 422) leaves the row `failed`, with its
    errors, which the card shows.
- **After an apply:** the route pushes `proposal_changed` and `config_changed`
  (DD10), then hands over to DD8.
- **Dismiss:** marks the row `dismissed`, pushes `proposal_changed`, and hands
  over to DD8 with no turn.

**DD8. Approve starts GleepGlorp's next turn (board option B)**
- **The turn seam:**
  - The `TurnHost` protocol moves out of `routines/runner.py` to a neutral
    module, `the_one/sessions/turn_host.py`, so routes in `api.py` modules can
    reach it without importing `app.py`.
  - It gains `append_marked_message(session, text, marks)`. That takes the
    session lock, updates the cached `Session` (messages and history), stores
    the message and pushes its frame. A database-only write would be
    overwritten by a running turn's save.
- **On Approve, with GleepGlorp ready:**
  - The approval text is `spawn_turn`'s prompt, for example: "Approved
    proposal 12: created agent Issue digest. Continue with the next step, if
    there is one."
  - The turn appends it as its own user message (`_process_and_broadcast`,
    `app.py:1366-1376`), so it is never added twice.
  - The proposal mark rides in `turn_info` to `_bind_turn_user_marks`
    (`app.py:2528`) and the live `user_event`. `_spawn_routine_turn` hard-codes
    `source="routine"` today.
  - The codec stores and projects the mark, as it does a routine run's
    `routine_id`.
  - The transcript draws it as the quiet line "You approved this change.
    GleepGlorp is continuing." (board option B), never as a bubble.
- **When GleepGlorp is not ready** (off, or with no model):
  - Approve still applies, because it is the operator's action.
  - `append_marked_message` stores the marked approval with no turn, and the
    line reads "You approved this change."
  - This covers the race too. If GleepGlorp becomes unready between the
    route's check and the turn lock, `_locked_message_processing` returns
    early and drops the prompt (app.py ~1298-1310). The turn path detects a
    dropped marked prompt and appends it.
- **On Dismiss:**
  - `append_marked_message` stores "You dismissed proposal 12" with no turn.
    GleepGlorp reads it with the operator's next message.
  - The transcript does not draw it, because the card's Dismissed line already
    says so.
  - Leg 5 checks that two user messages in a row convert correctly for every
    provider type.
- **A chat no socket has joined** still runs the turn. It is saved, and
  `track_turn` pushes `sessions_changed`.
- **Rationale:**
  - The operator's decision.
  - The routine-run seam already starts a server-side turn and pushes its
    frames.
- **Trade-off:** a new primitive (a marked message with no turn), and a
  moved protocol. Both get their own leg (Leg 5).

**DD9. Taint, the "Check this" flag, and the secret guard**
- **The flag:**
  - The tool computes it with `agent/taint.py::compute_taint`, as the routine
    tools do.
  - The row stores it with its sources.
  - The card shows the chip and the line naming the sources (board state 1).
- **A finer `read_app_config`:**
  - **The marker.** No tool can set result metadata without the frozen
    `agent/core.py` (`_execute_tool` builds `ToolResult(content=...)`, and only
    the MCP auth path sets metadata). So the marker goes in the content,
    following `FLAGGED_CONTENT_MARK` (taint.py:50).
    - A `read_app_config` result counts as trusted only when its first line is
      a fixed "operator-typed fields only" line.
    - Any other result stays untrusted.
    - Free text is never emitted at position 0, so it cannot forge the line.
      A failed read returns a sentence without the line, so it fails closed.
    - The rule is one predicate, `taint.py::is_trusted_result(name, content)`.
      `compute_taint`, the evals' `_taint_expected` (`evals/checks.py:554-565`,
      which imports `TRUSTED_TOOL_NAMES` today) and the new
      `proposals_flagged_if_untrusted` all use it, so they cannot drift.
    - Every other tool is unchanged.
  - **Classified by provenance, not shape:**
    - **Operator-typed:** agent, provider, knowledge-base and secret names;
      ids; counts; the operator's model choice; enums; switches; schedules.
    - **Written by an agent or a server:** descriptions, prompts, rule text,
      routine prompts and routine names (an agent can write them), MCP tool
      names and descriptions, server-reported info and model ids, notes.
  - **View changes**, so the reads GleepGlorp needs most before proposing come
    back operator-typed:
    - The `agents` list summary becomes the model plus counts, instead of the
      description, which an agent can write (`view_agents.py:34-36`).
    - The `agent` detail gains a `fields_only` form (names, model,
      attachments, switches, with no prompt or rule text). The `fields` kind
      (DD5) is operator-typed by construction.
- **What this unflags:** "create an agent" after listing agents, and "attach
  my MCP server" after reading the agent's fields and the server list. What it
  does not unflag: anything after reading a prompt, rule text, a server's tool
  descriptions or a web page. Taint accumulates over the whole chat.
- **Side effect:** GleepGlorp's notes saved after such reads are no longer
  flagged, through the same shared function.
- **Through apply:**
  - A flagged routine proposal passes its flag into `create_routine` and
    `update_routine` (`("merge", sources)`, as `approve_proposal` does), so a
    routine made after untrusted content runs flagged.
  - Agents and rules have no flag column. That residual risk is recorded in
    `SECURITY-MODEL.md`: rule text and prompts become operator text once
    approved, and the approval click is the control.
- **The secret guard:**
  - The tool refuses a proposal where any string value in `changes` (names
    included) contains a stored secret value. The values are gathered with `db/encryption_corpora.py::
    gather_corpora(conn, enc, strict=False)`, which rotation shares, so it
    cannot drift.
  - A new `secret_leaves(corpora, min_len=8)` helper skips:
    - non-secret blob leaves (an OAuth `token_type`, expiry times, scopes);
    - header and environment values the operator marked non-sensitive
      (`plain_names`).
  - The tool also refuses a key-shaped string. The token prefixes and the
    entropy and length thresholds are named constants.
  - The model is told, in a plain sentence, to leave keys to the operator and
    link to the page where they are entered. The value is never echoed or
    logged.
- **Rationale:**
  - The flag stays meaningful, and fails closed.
  - The secret rule is enforced by the server, not only by the prompt. The
    `pasted-key` eval scenario is the behavioural side.
- **Trade-off:**
  - `taint.py` and the views are shared or model-facing. The views change
    GleepGlorp's eval inputs, and the new baseline covers that (DD13).
  - A false positive blocks a proposal with a clear sentence, and the operator
    can type that text in the editor.

**DD10. Open editors follow an approved change (board option A)**
- **The event:**
  - After an apply, the server broadcasts `config_changed {kind: "agent" |
    "rule" | "routine", agent, fields, session_id, at}` to every socket
    (`broadcast_to_all`).
  - The window that clicked Approve also refreshes from the approve response,
    so it does not depend on the socket.
- **What the client does:**
  - It invalidates `App.store` `agents` and refreshes the chat drawer's Rules
    and Routines groups.
  - If the agent editor is open on that agent, it refetches the agent and
    applies each changed field to a clean control. That extends
    `general-tab.js::applyStored` and the self-configuration refresh path
    (`agent-editor-selfconfig.js`, which covers `description`, `system_prompt`
    and `mcp_source_ids` today) to:
    - the model picker;
    - the Tools tab tiles (`enabled_tools: null` means all);
    - Knowledge;
    - the Behavior fields.
  - A dirty control keeps its text, with today's caption: "The stored {label}
    changed. Save will replace it with your text."
  - Each control or tile that took a new value shows the quiet note (board
    option A): "Changed by a change you approved in a GleepGlorp chat · {time}
    · Open chat". The HAT settles the wording.
  - The Rules and Routines tabs reload their lists, and an open Add or Edit
    form keeps its text.
- **Where the code lives:** `agent-editor-controller.js` is at 798 of 800
  lines, so Leg 7 first moves the selection and refresh plumbing out (as
  squawk 0386 split the drawer) and never condenses lines.
- **Rationale:**
  - The mission criterion ("shows the new values without a reload, and an
    unsaved edit is never overwritten silently").
  - The self-configuration refresh is the proven precedent.
- **Trade-off:** only the agent editor follows changes in this flight.

**DD11. Prompt and guide**
- **The prompt** gains a proposals section:
  - propose one step at a time;
  - say a change is proposed, not done;
  - read `fields` before proposing;
  - never propose a delete or a secret;
  - send a secret or sign-in to its page.
- It drops Flight 1's line that it cannot change anything.
- The text is tuned by the eval method (DD13), within the 450-token cap.
- The guide gains a topic on proposals: the card, Approve, Dismiss, "Check
  this" and stale. It is checked by the guide's drift test and follows the
  project convention.
- Settings › Prompts shows the new prompt with no change of its own.

**DD12. Where the new code lives**
- **Domain:** `the_one/gleepglorp/proposals/` holds `shape.py`, `store.py`
  (the repository), `tool.py`, `guard.py` and `apply.py`.
- **Services:** `the_one/agent/service.py` and `the_one/agent/rules_service.py`.
  They shrink `api.py`, which is 7,537 lines.
- **Routes:** `interfaces/web/gleepglorp_proposals_api.py`.
- **Turn seam:** `the_one/sessions/turn_host.py`.
- **Client:**
  - `areas/chat/proposal-card.js` (`transcript.js` is 433 lines and
    `turn-work.js` 536, so both have room);
  - a new studio module for the editor follow-through.

**DD13. Evals: the adopted method, the extended set, a new baseline**
- **The method** (operator, 2026-11-19) is written into `evals/README.md` as
  the standing method:
  1. **A check is code under test.** Every new check gets offline tests with a
     recorded transcript that passes and one that fails.
  2. **Fairness before quota.** One live attempt per new scenario, with the
     transcripts reviewed against each check before any larger run.
  3. **Two kinds of check.** Safety checks must never fail; ranking checks only
     compare prompts.
  4. **Screen at a small sample.** Candidates run in parallel on Haiku at n=5,
     always with the current prompt as the control. The screen reads totals
     and safety checks only.
  5. **Shorten at the ceiling.** Drop one section at a time and keep a cut
     only if the result is no worse.
  6. **Confirm once.** One n=20 confirmation on Haiku and qwen3-4b.
  7. **Approve before quota.** Each round's quota estimate, and any re-pin of
     the frozen modules, is shown to the operator first.
  8. **Re-baseline on a changed set.** A changed scenario set gets a new
     baseline with the same prompt, never a comparison across sets.
- **New scenarios:**
  - propose creating an agent;
  - attach an MCP server to an agent;
  - a three-step request continued through two approvals;
  - add a rule;
  - schedule a routine;
  - a request to delete (declined, no proposal);
  - a pasted key in a create request (no secret in any proposal);
  - an injected page followed by a proposal (flagged);
  - a claim that the change is done before approval.
  - `no-change-claim` is rewritten for the proposal world.
- **New checks:**
  - `proposal_made(kind, action, fields)`, `no_proposal`;
  - `no_secret_in_proposal`, `no_delete_proposed`;
  - `proposals_flagged_if_untrusted`, which uses `is_trusted_result` (DD9),
    the same predicate as `compute_taint`;
  - plus the existing reply checks.
- **Harness changes:**
  - An approve step between conversation turns calls `apply_proposal` (DD7)
    and the same continuation text as the route.
  - It reads `gleepglorp_proposals` into its run trace.
  - The frozen scoring modules (`tests/test_evals_freeze.py`) are re-pinned
    once, with the operator's approval and a Reviewer confirmation, as in
    Flight 1 Leg 9.
  - This re-pin is not purely additive. `_taint_expected` moving to
    `is_trusted_result` changes the existing notes and routine flag checks for
    GleepGlorp. The operator is told this at the gate.
- **Baseline:** `evals/baselines/m36f2-gleepglorp.json`.
  `m36-gleepglorp.json` becomes history.
- **qwen3-4b is measured only:**
  - Its numbers, safety included, are reported every round and never block a
    prompt change.
  - The Settings hint that small models may struggle stays.
- **Rationale:** Flight 1's lessons. Unfair checks cost a full round, and the
  parallel screen with shortening found a prompt about 35% smaller.

**DD14. The HAT and the behavior tests (operator: a HAT closes this flight)**
- **The HAT:**
  - As in Flight 1 DD13, the crew confirms each step's state on a scratch
    instance (port 8486 or higher, scratch data directory, a real Claude
    provider) before the operator walks it.
  - Two-tab steps are left out (operator preference, Flight 1).
  - One step covers state the operator is not looking at: an agent editor open
    in Agents while a proposal is approved in Chats.
- **The behavior tests:**
  - `tests/behavior/gleepglorp-proposal-create-agent.md` and
    `tests/behavior/gleepglorp-proposal-attach-mcp.md` drive a real chat with
    Haiku on that instance through the browser.
  - They act by typing in the chat and clicking Approve.
  - They observe through the card's states in the transcript, `GET
    /api/gleepglorp/proposals?session_id=`, and `GET /api/agents/{name}` (the
    applied fields).
  - Their contract (the card's testids and the routes) is recorded in Leg 6.
    A HAT change to it is a spec re-author.

### Mockups (operator-approved, 2026-11-19)

**Option board:** https://claude.ai/artifact/Y99KpiQHEzW7Lo6SZLrBKH (private
to the operator), on the GleepGlorp AI tokens, in dark and light. It holds:
- three card layouts;
- the states, and the rule and routine cards;
- two ways to show an approval;
- two editor notes, beside the unsaved-edit sibling screen.

**Chosen (operator, 2026-11-19):**
- **Card: option A, the field table.**
  - A create lists every field it sets, with "Other settings keep their
    defaults."
  - A change has Now and Proposed columns, and "Only these {n} fields change."
  - Long text is cut, with Show all.

  ```
  PROPOSED CHANGE                                 3:46 PM
  Change agent "Issue digest"
  ------------------------------------------------------
                  NOW                 PROPOSED
  MCP servers     None                GitHub
  Prompt          …Use Fetch a web…   …Use the GitHub server's…
  ------------------------------------------------------
  [Approve] [Dismiss]               Only these two fields change.
  ```
- **States, as drawn:**
  1. Waiting, with the "Check this" chip and a line naming the source.
  2. Applying (busy buttons).
  3. Applied: folds to one line, with Open agent and Details.
  4. Dismissed: a quiet line.
  5. Couldn't apply: danger status. The card stays open, with Try again and
     Dismiss.
  6. Changed since proposed: a warning banner, Now and Proposed for the
     changed fields, and Approve anyway.
  7. Withdrawn: the target is gone, or a newer proposal replaced it.

  Warning is used only for "Check this" and changed-since. Danger is used only
  for couldn't apply.
- **The approval shows on the card only (option B),** plus the quiet line "You
  approved this change. GleepGlorp is continuing."
- **The editor shows a note beside each changed field or tile (option A):**
  "Changed by a change you approved in a GleepGlorp chat · 3:46 PM · Open
  chat".
  - The board draws it under an MCP server tile. The same note goes under the
    General fields, the model picker and the Tools and Knowledge tiles. The
    HAT checks those placements.
  - An unsaved edit keeps today's caption.
- **Rule and routine cards:** "Add a rule to …" and "Change rule N of …";
  "Schedule a routine for …" (with the server's schedule sentence and next
  runs) and "Change routine …".

They are references for layout and wording, not pixel contracts.

### Citation Audit

Verified against the working tree at `b3ee1b91` (main after the #380 merge).
Sources: two read-only surveys, spot checks by the Flight Director, and the
Architect's re-check (cycle 1).

| Citation | Status |
|---|---|
| `the_one/interfaces/web/api.py::create_agent` (~L1477): validation is inline (`_checked_agent_name`, `_normalize_surface_fields`, `AgentConfig.model_validate`, `_validate_tool_overrides`, `_validate_secret_grants`, `_check_agent_provider`, 409 on an existing name); the helpers raise `HTTPException` | verified |
| `api.py::update_agent` (~L1536): whole-body replace. Omitting a field resets description, prompt, model and tools (and `mcp_source_ids` to the surface row) but keeps `kb_ids`, `secret_ids`, `tool_overrides`, the `mcp_overrides` credentials and the switches. Ends in `store.save(cfg)` | verified |
| `api.py` rule routes (inline): `/agents/{name}/rules` GET/POST L2097/L2105, `/rules/order` L2117, `/rules/{rule_id}` PUT/DELETE L2129/L2143 | verified |
| `the_one/db/repositories.py::AgentStore.save` L270: a full upsert in its own `write_transaction`. `compare_and_set_field` L392: a field CAS over whitelisted fields | verified |
| `the_one/db/_write_lock.py::write_transaction`: raises `RuntimeError` when re-entered by its own task | verified |
| `the_one/routines/service.py::create_routine` L222, `update_routine` L278, `_stale_precheck` L666 (touched base keys only), `approve_proposal` L683 (passes `("merge", sources)`) | verified |
| `the_one/routines/proposals.py::ProposalOp` (~L137): hard-wired to `agent_routine_proposals` | verified (Architect) |
| `the_one/agent/taint.py::compute_taint` L67 `(agent, tool_call_id, turn) -> (bool, list[str])`; `TRUSTED_TOOL_NAMES` L36; `FLAGGED_CONTENT_MARK` ~L50 | verified |
| `the_one/agent/core.py::Agent._execute_tool`: builds `ToolResult(content=...)`; only the MCP auth path sets `metadata` (frozen module) | verified (Architect) |
| `the_one/gleepglorp/view_agents.py` ~L34-36: the agents list summary is `cfg.description` | verified (Architect) |
| `the_one/db/encryption_corpora.py::gather_corpora` L89, shared with rotation | verified |
| `the_one/sessions/_broadcast.py::broadcast_to_all` L44, `broadcast_to_session` L87 | verified |
| `the_one/routines/runner.py::TurnHost.spawn_turn(session, prompt, turn_info)` (~L60), `set_turn_host` L74; `app.py::_spawn_routine_turn` hard-codes `source="routine"` | verified (Architect for the latter) |
| `app.py::_locked_message_processing` (~L1294-1310): returns before `agent.step` for an unready GleepGlorp | verified (Architect) |
| `the_one/db/schema.py` `CURRENT_VERSION = 53` L18 | verified |
| `static/js/areas/studio/agent-editor-selfconfig.js`: `applyStored` / `rebaseBaseline_` / `setStoredChangeNote` cover `description`, `system_prompt`, `mcp_source_ids` | verified |
| `static/js/areas/chat/sign-in.js` (~L234): the block is placed after the work group, never inside it | verified (survey) |
| `static/js/ui/feedback.js::App.ui.noteFlag` L197 (the subject check is L199-201): `subject` must be `"note"` or `"routine"` | verified |
| `the_one/routines/repository.py::AgentRoutineRepository.update(precheck=…)` L251-286: re-reads the row in its own `write_transaction` and calls a sync `precheck`; `proposal.run(conn, id)` is called duck-typed (L241, L285) | verified (Architect, cycle 2) |
| `app.py::_bind_turn_user_marks` L2528; `_process_and_broadcast` (L1366-1376) appends the turn's prompt as a user message | verified (Architect, cycle 2) |
| `evals/checks.py::_taint_expected` L554-565: mirrors `compute_taint` through `TRUSTED_TOOL_NAMES` | verified (Architect, cycle 2) |
| `agent-editor-controller.js` is 798 lines; `tests/test_area_module_size.py` sets `LIMIT = 800` | verified |
| `tests/test_gleepglorp_build.py` allowlist tests (L74, L200); `tests/test_evals_freeze.py` `SCORING_DIGESTS` | verified |

### Prerequisites

- [x] Flight 1 merged (#380, `b3ee1b91`). Squawks 0386-0390 landed with it.
- [ ] The eval apparatus is ready for Leg 9, re-verified at that leg: the plan
      token in `~/.config/the-one-evals/plan-token`, Ollama with `qwen3-4b`,
      and `pip install -e ".[evals]"`.
- [ ] A scratch dev instance with a real Claude provider for the HAT and the
      behavior tests, re-verified at Leg 10.
- [ ] Squawk 0385 (the shell-write hook skips `sorties/`, `squawks/` and
      repo-root files). Routine and not in this flight's path; completed at a
      turnaround when the operator chooses.

### Pre-Flight Checklist

- [x] All open questions resolved
- [x] Design decisions documented
- [x] Citation Audit complete
- [ ] Prerequisites verified (apparatus re-verified at Legs 9 and 10)
- [x] Validation approach defined
- [x] Legs defined

---

## In-Flight

### Technical Approach

- **Services first (Leg 1),** so the write boundary is proved unchanged before
  anything new uses it.
- **One capability per leg after that,** each with its own risk:
  - proposals are recorded (Leg 2);
  - guarded (Leg 3);
  - applied (Leg 4);
  - continued (Leg 5);
  - drawn (Leg 6);
  - followed by the editor (Leg 7).
- **Evals:** set up autonomously and committed (Leg 8), then tuned in
  operator-gated rounds (Leg 9) against the real tool and card.
- **The HAT closes the flight (Leg 10).**
- **Batches:**
  - A: Legs 1-3, reviewed and committed.
  - B: Legs 4-5, reviewed and committed.
  - C: Legs 6-8, with the Accessibility Reviewer, reviewed and committed.
  - Then Leg 9, Leg 10 under its gate, and the HAT (Leg 11).
  - Leg 7 was split into Legs 7 and 8 at its design review. The evals and HAT
    legs were renumbered 9-11, so "Leg 8", "Leg 9" and "Leg 10" earlier in
    this spec mean the eval setup, the eval rounds and the HAT.
- **The quiet-host gate:** taken at the first full gate that starts on a quiet
  host (owed since Flight 1, squawk 0389).

### Checkpoints

- [ ] Save behaves exactly as before through the new services. The existing
      agent, rule and routine API and browser tests are unchanged and green.
- [ ] A `propose_change` call writes only `gleepglorp_proposals`.
- [ ] Stored secrets and key-shaped strings are refused. A read of the agent
      fields alone does not flag a proposal.
- [ ] Approve applies only the named fields, once. It refuses a stale proposal
      and keeps concurrent Saves. Dismiss changes nothing.
- [ ] Approve continues the chat. An unready GleepGlorp records the approval
      with no turn.
- [ ] The card and its states render live and after a reload.
- [ ] An open agent editor follows an approval without losing an unsaved edit.
- [ ] A new baseline, with Haiku at or above its bars and zero safety failures.

### Adaptation Criteria

**Divert if**:
- Extracting the agent service changes any existing API response or test
  expectation: stop and re-plan Leg 1.
- The continuation cannot reuse the routine-run seam without changing the
  turn lock: re-plan DD8 with the operator.
- Haiku's tool-call validity on `propose_change` is below its bar after the
  screen: DD5's fallback is three tools, recorded as a deviation.

**Acceptable variations**:
- A small library control for the field table instead of plain rows.
- The wording of the card lines and the editor note, settled at the HAT.
- Leg 7 split into the General tab, and then the tiles and tabs, if its design
  review finds it too large.

**Note**: from Leg 2 until Leg 9 ships the new prompt, `propose_change` is
live while GleepGlorp's prompt still says it cannot change anything. Nothing
merges in between, but no eval round or behavior test is run on that tree.

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned
> and created one at a time as the flight progresses.

- [x] `01-agent-and-rule-services`
  - The agent and rule services: `AgentWriteError`, create, the
    `replace_agent` core holding the PUT's omit rules, and a field-level change
    with `save(precheck=…, on_commit=…)` under the lock (touched fields are
    compared with `base`; an untouched-field race is re-merged).
  - The rule repository gains `position`, `precheck` and `on_commit`. Routines'
    `proposal=` type hint is generalised.
  - The routes call the services, and Save is unchanged.
  - High-risk (shared write path).
- [x] `02-proposal-store-and-tool`
  - Schema v54 `gleepglorp_proposals` and its repository.
  - The change shape and its pin test, and the `fields` read kind.
  - `propose_change`: name-to-id resolution, one pending per chat, supersede.
  - Proposals deleted at every chat-delete site, and the purge.
  - The allowlist and no-write tests.
  - High-risk (schema, new write).
- [x] `03-proposal-guards`
  - The secret guard (`secret_leaves`, key-shape constants).
  - The `read_app_config` content marker and the provenance classification.
  - The view changes (operator-typed agent summary, `fields_only` detail).
  - Taint on proposals.
  - High-risk (shared `taint.py`, security surface).
- [x] `04-proposal-apply`
  - The proposals routes module: list, approve with stale and override,
    dismiss, withdrawn.
  - `apply_proposal` through the services, marking the row in the same
    transaction (agent, rule, routine), with the routine flag carried through.
  - A 409 while a turn is running, and the `proposal_changed` and
    `config_changed` frames.
  - High-risk (write boundary).
- [x] `05-approval-continuation`
  - `sessions/turn_host.py`, `append_marked_message`, the proposal mark
    through `turn_info`, the codec and the live `user_event`.
  - The continuation turn, Dismiss and unready GleepGlorp, and consecutive user
    messages per provider.
  - High-risk (turn lifecycle).
- [ ] `06-proposal-card`
  - The chat card (option A) and its states, placed after the work group and
    the reply.
  - Live and reload (`session_joined`, ready and degraded), the quiet approval
    line (option B), the "Check this" chip, the busy rules.
  - The behavior-test specs, with their testid contract.
- [ ] `07-editors-follow-approvals`
  - The controller split first.
  - The eager `App.approvals` record.
  - The store, list and drawer follow `config_changed`.
  - The General tab fields follow, with a central clean or dirty decision and
    the option A notes drawn at every mount.
  - The same-window return path.
- [ ] `08-tabs-follow-approvals` (split from Leg 7 at its design review,
      2026-11-19)
  - The Tools, MCP and Knowledge tiles follow on the same mechanism.
  - The Rules reload keeps an inline edit's text, and the Routines tab reloads.
- [ ] `09-proposal-evals-setup` (autonomous, reviewed and committed before any
      quota)
  - The `evals/README.md` method section.
  - Scenarios, and checks with their offline pass and fail tests.
  - The harness approve step and trace.
  - The frozen re-pin (operator-approved), and the one-attempt fairness pass.
- [ ] `10-proposal-evals-rounds` (operator-gated)
  - Screen, shorten, confirm, baseline.
  - Ship the prompt and the guide topic.
- [ ] `11-hat`: the guided HAT with the crew-checked apparatus, and the two
      behavior tests.

---

## Post-Flight

### Completion Checklist
- [ ] All legs completed
- [ ] Code merged
- [ ] Tests passing: the unit tier and every browser lane, with
      `THE_ONE_REQUIRE_WEBKIT=1` on the contract lanes
- [ ] Documentation updated:
  - `CLAUDE.md` (a GleepGlorp proposals paragraph);
  - `the_one/agents.md`;
  - `SECURITY-MODEL.md` (the proposal boundary, the secret guard, the residual
    risk of approved rule and prompt text);
  - `evals/README.md`;
  - the app guide.

### Verification
- `/mission-control:behavior-test gleepglorp-proposal-create-agent` and
  `gleepglorp-proposal-attach-mcp` pass against the scratch instance.
- In the unit tier: the allowlist and no-write tests; the stale, override,
  concurrent-Save and double-Approve tests; and the secret-guard and taint
  tests.
- `make eval ARGS="compare --baseline evals/baselines/m36f2-gleepglorp.json"`
  reproduces the recorded baseline's bars for Haiku.
