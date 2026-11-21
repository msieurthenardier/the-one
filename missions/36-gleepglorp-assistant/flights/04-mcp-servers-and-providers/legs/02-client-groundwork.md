# Leg: 02-client-groundwork

**Status**: completed
**Flight**: [MCP servers and model providers](../flight.md)

## Objective

Put the browser's GleepGlorp fill, receipt, card and approval code on one per-kind registry,
`App.gleepglorpKinds`. Agent, rule and routine register their existing behaviour, so nothing
the operator sees changes, and Legs 4 and 5 can add MCP servers and providers by registering
a kind. The server's `config_changed` frame also gains `target_id`.

## Context

- **Flight DD11** (one client registry per kind) and **DD8** (fills go through the kind's
  editor; navigation obeys the leave guard).
- **Today's agent-only code:**
  - `gleepglorp-drawer/fill.js`: `agentExists`, `routeFor` and `open`, which calls
    `App.studio.agentEditorFill` and `App.studio.agentsList`.
  - `areas/chat/fill-receipts.js`: the `REASONS` "The agent editor could not open." and "That
    agent no longer exists."
  - `areas/chat/proposal-cards.js`: `openAgentLink` with `AGENT_TABS`, the withdrawn reasons,
    and the `appliedByApproval` detail.
  - `approvals.js`: `record` returns false without `detail.agent`; `KIND_KEYS = {rule,
    routine}`; it invalidates only `agents`.
  - `areas/studio/agent-editor-follow.js`: the only `CONFIG_CHANGED` listener.
- **What is not in this leg:**
  - **The flight spec's "one card and receipt folding rule"** (DD11). On reading the code, the
    card states (`proposal-cards.js`) and the receipt states (`fill-receipts.js`) do not share
    a folding rule. Ordering is already shared (`App.chat.cardOrder`). Merging them would be a
    rewrite with no user-visible gain, so it is dropped; the log records this.
  - **The dirty-state navigation tests** (DD8, debrief key learnings) already exist for the
    agent kind:
    - `test_a_dirty_editor_and_stay_means_stay_nothing_written_and_focus_back_in_the_drawer`;
    - `test_an_editor_already_open_on_agents_is_written_without_navigating`;
    - `test_the_operators_unsaved_prompt_is_kept_and_the_receipt_names_it`;
    - `test_a_leave_guard_dialog_already_open_means_the_fill_does_not_navigate`.

    They are the regression net here, unedited. Legs 4 and 5 add the same pair for their
    kinds.
- **Depends on Legs 1a and 1b** (server registry, `fill_view.target_id`). Re-check
  `fill_view`'s keys after 1b lands.

## Inputs

- Legs 1a and 1b landed (uncommitted).
- `approvals.js` (91 lines), `gleepglorp-drawer/fill.js` (187), `areas/chat/fill-receipts.js`
  (368), `areas/chat/proposal-cards.js` (659), `areas/chat/window-frames.js` (71) and
  `areas/studio/agent-editor-follow.js` (342); the script order in `static/index.html`;
  `gleepglorp/proposals/apply.py`'s `config_changed` broadcast.

## Outputs

- **A new eager module, `static/js/gleepglorp-kinds.js`,** loaded in `index.html` before
  `approvals.js`. It provides `App.gleepglorpKinds`:
  - `register(name, spec)`;
  - `get(name)`, which returns `null` for an unknown name;
  - `names()`.
- **The kind spec:**
  - `labels`:
    - `{itemNoun}`, for example "agent";
    - `editorUnavailable` and `targetGone` (the receipt reasons);
    - `withdrawnGone(view)`;
  - `openLink(view)`, which returns `{spec, text, testid}` or `null`. For the agent kinds it
    reproduces `openAgentLink`, including its testid `proposal-open-agent` and the text
    "Open agent".
  - `store`, the `App.store` collection to invalidate on an approval (`'agents'` for all
    three).
  - `recordKey(detail)`, the record an approval goes under. Agent: the agent name, keyed by
    the stored field names. Rule and routine: the agent name, under `'rules'` and
    `'routines'`, as today.
  - `fill`, present only for a fillable kind (agent):
    - `{routeFor(view), openKey(view), exists(view), isOpen(key), whenSettled(key),
      select(), beforeNavigate(view), afterNavigate(), apply(view)}`;
    - these wrap today's `App.studio.agentEditorFill`, `agentsList.suppressNextCreateFocus`,
      `clearCreateFocusSuppression` and `selectGeneral` calls.

  A kind's module registers itself where the code it wraps lives.
  - For agent, rule and routine this is `areas/studio/agent-kinds.js`, loaded **at the end of
    the Studio script block** in `index.html`, after `agents-list.js`.
  - Every Studio module is eager, so registration happens during script load, before any socket
    frame or fill is handled.
  - The spec's calls into `App.studio.*` are late-bound
    (`function (v) { return App.studio.agentEditorFill.apply(v); }`).
  - `fill.exists(view)` must be re-callable and free of side effects. The drawer calls it again
    on the editor-unavailable retry path.
- **The namespace is `App.gleepglorpKinds`,** not `App.gleepglorp.kinds`.
  `static/js/gleepglorp.js:81` assigns `window.App.gleepglorp = {...}` wholesale and would
  clobber a sub-key.
- **The spec objects stay mutable** (not frozen). That is documented, so a browser test can null
  a kind's `fill` (AC8).
- **Unknown kinds, per consumer:**

  | Consumer | What it does for an unknown kind |
  |---|---|
  | drawer `fill.js` | reports `not_filled` / `editor_unavailable`, with no navigation |
  | receipts | today's generic text: "The editor could not open." and "That item no longer exists." |
  | cards | no link; withdrawn reason "the item no longer exists." |
  | `approvals.record` | returns `false` |

  These fallbacks apply only to an *unknown* kind. The agent kinds keep their exact wording
  through their `labels`.
- **The consumers read the registry:**
  - drawer `fill.js` uses the kind's `fill` spec; a kind with no `fill` spec reports
    `not_filled` / `editor_unavailable`;
  - `fill-receipts.js` reads its reasons from the kind's `labels`;
  - `proposal-cards.js` reads `openLink` and `labels.withdrawnGone`;
  - `approvals.js` generalises (AC5).
- **`config_changed`** carries `target_id` (`p.target_id`). The agent frame keeps `agent`.
- `the_one/agents.md` and the catalogue (if `App.gleepglorpKinds` belongs there) are
  updated.

## Acceptance Criteria

- [ ] **AC1.** `App.gleepglorpKinds` exists, loaded eagerly before `approvals.js`, with
  `register`, `get` and `names`. Registering the same name twice throws, so a duplicate script
  load fails loud.
- [ ] **AC2.** `agent`, `rule` and `routine` are registered during script load, before any
  socket frame or fill is handled. A browser test asserts two things after page load:
  `App.gleepglorpKinds.names()` contains exactly those three, and `App.gleepglorp.get`,
  `peek` and `prime` still exist.
- [ ] **AC3. The drawer's `fill.js` holds no agent-specific code.**
  - `grep -n "agentEditorFill\|agentsList\|destination: 'agents'\|agentExists\|agent_name\|App\.studio"
    gleepglorp-drawer/fill.js` returns nothing.
  - Every step goes through `App.gleepglorpKinds.get(view.kind).fill`: route, open key, exists,
    open or settle, apply, and the create-focus suppression.
  - A fill whose kind has no `fill` spec is reported `not_filled` with reason
    `editor_unavailable`, and nothing navigates.
- [ ] **AC4. Receipts and cards hold no agent wording.**
  - `fill-receipts.js` has no "agent" in its reason strings.
  - `proposal-cards.js` has no `AGENT_TABS`, no `openAgentLink`, and no "agent no longer
    exists", "rule no longer exists" or "routine no longer exists" (that wording moves into
    each kind's `labels.withdrawnGone`).
  - `focusTarget`'s `[data-testid="proposal-open-agent"]` (`:556`) reads the testid from
    `openLink(view).testid`.
  - `appliedByApproval` (`:565-594`) passes `kind`, `agent` and `target_id` from the view to
    `App.approvals.record`.
  - Each takes its text from the kind's `labels` and `openLink`, and the rendered text for the
    three kinds is unchanged. Every existing browser assertion passes unedited, including the
    testid `proposal-open-agent`, "Open agent", "That agent no longer exists." and the
    withdrawn reasons.
- [ ] **AC5. `approvals.js` records any registered kind.**
  - `record(detail)` accepts a detail with `kind` and either `agent` (the agent kinds, as
    today) or `target_id` (a later id-targeted kind). It records under the kind's `recordKey`,
    invalidates the kind's `store`, and emits `CONFIG_CHANGED` with `{kind, agent?,
    target_id?, fields, session_id, proposal_id, at}`.
  - An unknown kind is ignored and returns false.
  - For the agent kinds, `forAgent`, `itemsFor` and `clear` behave exactly as today.
  - A new generic reader, `forTarget(kind, id)`, returns `{field: {at, session_id}}` for a
    non-agent kind, for Legs 4 and 5's follow code. It reads a separate `byTarget[kind][id]`
    store. `forAgent`, `itemsFor` and `clear` keep using `byAgent` and `itemsByAgent`, and
    `clear` does not touch `byTarget`.
  - **For the agent kinds, `agent` decides.** A detail with `agent` is recorded exactly as
    today, whatever its `target_id` (a rule or routine proposal's `target_id` is the rule or
    routine id). `target_id` is used only for a kind whose spec has no agent `recordKey`.
  - The emitted event still carries `agent` for the agent kinds.
    `agent-editor-follow.js` ignores events without `agent` (its `onEvent` guards
    `!detail.agent`). A test shows that a `target_id`-only event reaches the bus and does not
    throw in follow.
  - The de-duplication by `proposal_id` is unchanged.
- [ ] **AC6. `config_changed` carries `target_id`.** `apply.py`'s broadcast adds
  `"target_id": p.target_id`: `null` for an agent proposal, and the rule or routine id for
  those kinds. The one exact-dict pin, `tests/test_gleepglorp_proposals_apply.py:504-512`, is
  updated and states the expected value. Grep confirms that nothing else pins it: the browser
  tests only deliver frames, and `evals/` neither builds nor asserts the frame. No other key
  changes.
- [ ] **AC7. No behaviour change.** These pass with assertions unedited, apart from AC6's
  frame-key pins:
  - `tests/browser/test_flow_gleepglorp_fill.py`, `test_flow_gleepglorp_drawer_chat.py`,
    `test_flow_gleepglorp_drawer_shell.py`, `test_flow_chat_proposals.py` and
    `test_flow_chat_gleepglorp.py` (the `gleepglorp` lane);
  - the agent editor follow tests, `tests/browser/test_flow_agent_editor_follows_approval.py`
    and any other `grep -l "follow\|approved" tests/browser/` hit. Find their lanes with
    `--list`;
  - `tests/test_gleepglorp_*.py` (unit).

  The `gleepglorp` lane and the lanes owning the follow tests are run; record the lane names.
- [ ] **AC8. New tests:**
  - **Registry unit behaviour, in a browser test** (registry and approvals): register, get and
    names; duplicate registration throws; an unknown kind's `record` is false; a stub
    id-targeted kind registered by the test records under `target_id`, invalidates its store
    and emits `CONFIG_CHANGED` with `target_id`.
  - **A drawer fill whose kind has no `fill` spec** reports `editor_unavailable`, with no
    navigation. Fills are seeded server-side (`seed_gleepglorp_fill`), and the server's
    `fill_view` requires a registered kind, so a fake kind cannot be seeded. The test therefore:
    - seeds a normal agent fill;
    - sets `App.gleepglorpKinds.get('agent').fill = null` in `page.evaluate` before
      delivering it;
    - asserts the receipt reads not filled with the editor-unavailable reason, and the route
      did not change;
    - restores the spec in a `finally`.
  - Each is reported falsified, yes or no.
- [ ] **AC9.** The static JS guards pass with no change expected:
  - `tests/test_ui_guards.py` (no HTML-string sinks, no retired APIs);
  - `tests/test_token_definitions.py` and `tests/test_design_tokens_a11y.py`;
  - `tests/test_ui_ownership.py`, `tests/test_ui_control_inventory.py` and
    `tests/test_native_bridge_guard.py`.

  No test pins the `index.html` script order or count, and the new files are not `js/ui/`
  factories.
- [ ] **AC10.** `THE_ONE_TEST_NETNS=1 make test-unit` passes, with 15 skips, run after the
  lanes, never concurrently. Ruff is clean on touched Python.
- [ ] **AC11.** `the_one/agents.md` gets a short "GleepGlorp client kinds registry (M36 F4)"
  section:
  - the spec members;
  - "a kind registers where its editor code lives";
  - the approvals record shapes;
  - `config_changed`'s `target_id`.

## Verification Steps

- AC1-AC5: the greps in AC3 and AC4; the new browser tests.
- AC6: `grep -rn "config_changed" tests/` and update the key pins. Run the unit tier.
- AC7: `THE_ONE_TEST_NETNS=1 PYTHON=.venv/bin/python bash scripts/run-tests.sh --lane gleepglorp`,
  then the follow tests' lane(s), one at a time.
- AC9-AC10: the static guards, then `THE_ONE_TEST_NETNS=1 make test-unit`.

## Implementation Guidance

1. **Re-read the five client modules and their tests.** Note every agent-specific line; the
   Context list is the starting point, so grep for `agent` in each.

2. **`gleepglorp-kinds.js`.** Plain IIFE, `'use strict'`, no DOM, defining
   `window.App.gleepglorpKinds`. Add it to `index.html` before `approvals.js`.

3. **Register the agent kinds** in `areas/studio/agent-kinds.js`, added at the end of the
   Studio script block in `index.html`. The calls are late-bound (Outputs).
   - The agent spec's `fill` wraps today's calls exactly:
     - `routeFor` is the current `routeFor`;
     - `openKey` is `'create'` or `'edit:' + view.agent_name`;
     - `exists` is the current `agentExists`;
     - `isOpen`, `whenSettled` and `select` come from `agentEditorFill.isOpen`,
       `whenSettled` and `selectGeneral`;
     - `beforeNavigate(view)` suppresses create focus on create;
     - `afterNavigate()` clears it;
     - `apply` is `agentEditorFill.apply`.
   - Rule and routine have no `fill`. Their `openLink` uses the agent tab mapping
     (`rules-and-notes`, `routines`), and their `labels` give today's withdrawn reasons.

4. **Drawer `fill.js`.** Replace the agent calls with the kind's `fill` spec. Keep the
   sequence, the reasons and the report calls exactly; only the source of each call changes.

5. **Receipts and cards.**
   - `REASONS.editor_unavailable` and `target_gone` come from `kind.labels` (fall back to
     today's text if the kind is unknown).
   - `openAgentLink` becomes `openLink(view)` through the kind.
   - The withdrawn reason comes from `kind.labels.withdrawnGone(view)`. The "replaced" reason
     stays generic.

6. **`approvals.js`.** Generalise `record` per AC5. Keep the agent paths byte-for-byte in
   behaviour. Read `agent-editor-follow.js` (`forAgent`, `itemsFor`, `clear` and the
   `CONFIG_CHANGED` listener) to be sure the event detail it reads is unchanged.

7. **The server frame.** Add `target_id` to the `config_changed` broadcast in `apply.py`. Grep
   for the frame's exact-dict pins.

8. **Tests and docs**, then the lanes, then the unit tier.

## Edge Cases

- **A stored proposal or fill of a kind the client does not know** (for example a newer
  server): the card and receipt still render with generic reasons, and there is no link.
  Never throw.
- **A `config_changed` frame that arrives before the kinds are registered** cannot happen,
  because the registry and the agent kinds load before the sockets open. Assert the script
  order in the browser test.
- **The drawer's `fill.js` and the receipts read `view.kind`.** For fills that is always
  `agent` today, so do not add a fallback that silently treats an unknown kind as agent.

## Files Affected

- `the_one/interfaces/web/static/js/gleepglorp-kinds.js` (new);
  `areas/studio/agent-kinds.js` (new, or an addition to `agent-editor-fill.js`).
- `the_one/interfaces/web/static/js/gleepglorp-drawer/fill.js`, `approvals.js`,
  `areas/chat/fill-receipts.js`, `areas/chat/proposal-cards.js`.
- `the_one/interfaces/web/static/index.html` (script order).
- `the_one/gleepglorp/proposals/apply.py` (`target_id` in the frame).
- New browser tests (in a `tests/browser/test_flow_gleepglorp_*.py` file, so they land in the
  `gleepglorp` lane); `config_changed` key pins.
- `the_one/agents.md`.
- **Registries and pins:** the `index.html` script-list pins, `tests/test_ui_ownership.py`,
  the `config_changed` frame-key pins, and the `gleepglorp` lane (new files match its glob).

## Design Review

Cycle 1 (Developer, Sonnet): **approve with changes.** All folded in above:
- **High:**
  - **The namespace** is `App.gleepglorpKinds`, because `gleepglorp.js:81` would clobber
    `App.gleepglorp.kinds`.
  - **The agent kinds load** at the end of the Studio block, with late-bound calls.
  - **The AC8 stub fill test** nulls the agent kind's `fill` spec, because a fake kind cannot be
    seeded server-side.
- **Medium:**
  - wider greps (`agent_name`, `App.studio`), `focusTarget`'s testid, `appliedByApproval`;
  - `exists` re-callable;
  - the single frame pin and `target_id` values;
  - a separate `byTarget` store;
  - follow ignores agent-less events, with a test.
- **Low:**
  - the pin expectations (no change);
  - the follow test file named in AC7;
  - an unknown-kind table.

There is no second cycle: these are corrections of fact and placement, not new design.

## Citation Audit

Verified at `9597b0f4` (these files are not touched by Legs 1a or 1b, apart from `apply.py`
and `fill_view`, which are re-checked at leg start):
- `approvals.js:29` `KIND_KEYS = { rule: 'rules', routine: 'routines' }`; `:52`
  `if (!detail || !detail.agent) return false`; it invalidates `'agents'` only; the event
  detail is `{kind, agent, fields, session_id, proposal_id, at}` — verified.
- `gleepglorp-drawer/fill.js:61` `agentExists`, `:67` `routeFor`, `:76` `open` (it uses
  `App.studio.agentEditorFill.isOpen`, `selectGeneral`, `whenSettled`, `apply`, and
  `App.studio.agentsList.suppressNextCreateFocus` and `clearCreateFocusSuppression`) — verified.
- `areas/chat/fill-receipts.js:23-28` `REASONS` (agent wording at `:26-27`) — verified.
- `areas/chat/proposal-cards.js:24` `AGENT_TABS`, `:193` `openAgentLink` (testid
  `proposal-open-agent`, text "Open agent"), `:233-244` the withdrawn reasons — verified.
- `areas/chat/window-frames.js:46-49` `config_changed` → `App.approvals.record(data)` —
  verified.
- `areas/studio/agent-editor-follow.js:328` the `CONFIG_CHANGED` listener; `:127`
  `forAgent`; `:140` `itemsFor`; `:321` `clear` — verified.
- `static/index.html:87` `approvals.js`, `:108-109` cards and receipts, `:119` drawer `fill.js`
  — verified.
- `tests/browser/test_flow_gleepglorp_fill.py` — the dirty-state and open-editor tests at
  `:658`, `:893`, `:1295` and `:1313` — verified.
