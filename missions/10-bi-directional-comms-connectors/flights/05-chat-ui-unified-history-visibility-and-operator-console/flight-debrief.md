# Flight Debrief: Chat UI — Unified History, Visibility Distinction, Operator Console

**Date**: 2026-05-18
**Flight**: [Chat UI — Unified History, Visibility Distinction, Operator Console](flight.md)
**Status**: landed
**Duration**: 2026-05-18 (single-day flight; all eight leg entries dated 2026-05-18)
**Legs Completed**: 8 of 8 (7 autonomous + 1 required HAT closer)

## Outcome Assessment

### Objectives Achieved

F5 landed the operator-facing surface of the connector subsystem end-to-end:

- **Read surface** (L1): connector-keying fields surface in the WS
  `list_sessions` projection (`platform`, `connector_account_id`,
  `channel_id`, `thread_id`, `peer_id`, `last_inbound_at`); the Chat
  sidebar renders a typed source badge (`.session-item-source` +
  `.session-item-source--{type}`) on connector-bound rows.

- **Cross-subsystem state extraction** (L2): the per-session
  `asyncio.Lock` and the WS subscriber registry both moved out of
  `Session` and into a new neutral `the_one/sessions/` package with
  one-way imports (`interfaces.web.app → the_one.sessions` and
  `connectors._inbound → the_one.sessions`; verified by grep at leg
  end). `Session.processing_lock` and `Session.subscribers` removed
  (Shape A); 14 in-app + 5 test-file call sites migrated; three lock
  read paths consolidated through a single `is_session_processing(sid)`
  helper that does NOT lazy-create empty entries.

- **Visibility-tagging consolidation** (L3): the F4-era inline rules
  block extracted into a pure-function helper
  `the_one/connectors/visibility.py:tag_post_step_visibility(messages,
  pre_step_len)` shared by both call sites; byte-identical refactor
  (F4 ground-truth tests passed unchanged).

- **Write surface** (L4): WS-typed operator messages on connector-
  attached sessions get `visibility=OPERATOR_VISIBILITY` at the
  storage edge in `_process_and_broadcast`. Symmetric shim landed
  in `_resume_paused_session`. `Session.platform` field added,
  populated from `db_session.platform` at restore. The agent loop
  in `the_one/agent/core.py` was untouched — the shim mutates
  `Message.visibility` via direct attribute write on a dataclass.

- **Render layer** (L5): `App.chat.renderMessage` reads
  `opts.visibility`; bubbles tagged `"operator"` get the
  `msg-operator-only` class + inline `[operator-only]` label
  (HAT subsequently suppressed both on `.msg.user` bubbles — see
  Deviations). CSS rules in `chat.css` use verified M04/M06 tokens
  (`--border-strong`, `--fg-tertiary`, `--font-family-mono`,
  `--font-size-tiny`).

- **Live-broadcast surface** (L6): the dispatcher's `dispatch_inbound`
  projects new messages via `messages_to_ui_events(new_msgs,
  index_offset=pre_step_len)` and broadcasts each event via
  `broadcast_to_session` inside the per-session lock after
  persistence. Codec gained an `index_offset: int = 0` keyword-only
  parameter to keep `parent_message_id` values unique across
  consecutive inbound turns on the same session (closes a real
  collision bug surfaced during leg design review).

- **End-to-end coverage** (L7): two browser tests (source-badge
  contract + operator-input write-path with web-native negative
  control); written design-language audit (PASS on all three F5-
  introduced visual surfaces in the original audit; HAT later
  surfaced two contrast issues fixed inline).

- **HAT closer** (L8, REQUIRED): operator drove the live surface
  through six verification steps (steps 6 + 8 SKIPPED with
  automated equivalents in `test_connectors_inbound_broadcast.py` +
  `test_session_registry_lock_unification.py`). HAT surfaced and
  applied four inline fixes (dark-mode contrast on `--fg-tertiary`
  and `--fg-faint`, marker suppression on `.msg.user`, Studio
  "Connector Accounts" → "Connectors" rename + dropdown ladders +
  button styling); deferred three findings to follow-on flights.

### Mission Criteria Advanced

| Mission success criterion | F5 contribution |
|---|---|
| "When the operator opens Chat for an agent that has connector-attached sessions, those sessions are listed alongside the Chat-UI-native sessions; opening one shows the full unified conversation history" | **Met** (L1 + L5: source badge + unified-history render with visibility distinction). Persisted-state path is correct; live-broadcast tagging on the WS-typed path is a documented follow-on. |
| "Two visibility layers — platform channel + operator console" | **Met** (L4 + L5: WS-typed messages tagged operator-only at storage edge; render layer surfaces the distinction; HAT verified the persisted contract end-to-end). |
| "Agent has context awareness across both visibility layers" | **Structurally met** (F3's single-history model + F4's visibility-tag-as-metadata; first time exercised end-to-end with operator-typed messages landing in connector-attached sessions). |
| "Admin connector-account surface, Studio connector-attach surface, doctor probe, and in-Chat connector-session view all meet the M04/M06 design-language quality bar without alignment-flight rework" | **Met** for in-Chat view + Admin connector-account surface (HAT confirmed; inline fixes applied within F5 scope, no alignment-flight needed). Studio connector-attach surface still ships in F6. |
| "Each layer of the integration has automated coverage proving its contract" | **Advanced**: F5 added 9 new test files + 3 browser tests covering the projection contract, lock-unification, visibility-tagging rules, WS storage-edge shim, dispatcher broadcast, codec `index_offset`, and the operator-only marker render. |

**Mission Known Issue closed**: "Per-session lock unification (surfaced
in Flight 3 planning, owned by Flight 5)" (mission.md L101-102) — the
WS handler and the F3 dispatcher now converge on
`the_one.sessions.session_locks[session_id]`. Mission checkbox ticked.

## What Went Well

- **Architectural-first ordering paid off.** L2's lift of subscribers
  + broadcast helper to the neutral package meant L6's dispatcher
  broadcast was a 4-line change with zero new function-local-imports.
  Doing the refactor (L3) before the consumer (L4) made the
  diff easy to review and the test surface clean (the F4 ground-
  truth tests served as the regression net for L3's "pure refactor"
  claim).

- **Pre-leg design reviews caught real bugs before code was written.**
  L2's first-pass design missed five subscriber call sites in
  `test_app_websocket_pause_resume.py` + `test_auto_load.py`; the
  reviewer caught it. L3 caught an import-cycle concern that the
  helper-module placement resolved. L4's first pass didn't include
  the `_resume_paused_session` symmetric shim; the reviewer flagged
  it as a real UX defect (resumed assistant messages would persist
  as peer-visible) and the leg added it inline. L5's first draft
  cited wrong selectors (`#chat-input` vs. `[data-testid="chat-input"]`)
  and design tokens that didn't exist (`--accent-muted`,
  `--space-2`); the reviewer surfaced them and the leg was rewritten
  before implementation. L6's first design had a `parent_message_id`
  collision across consecutive inbound turns; the reviewer caught
  the `enumerate(messages)` restart-from-0 issue and the leg added
  the codec `index_offset` parameter. **Net**: design-review cycles
  paid for themselves multiple times over.

- **HAT-required (not optional) was strongly validated.** HAT
  surfaced four issues that automated tests couldn't have caught:
  the operator-only-marker noise on `.msg.user` bubbles, two dark-
  mode contrast failures (`--fg-tertiary` ~3.4:1 and `--fg-faint`
  ~2:1 — both below WCAG AA), and the F2 Studio Connectors surface
  polish pass. The original flight design's prediction of "design-
  language drift, two-layer rendering ambiguity, and operator-mental-
  model gaps" was accurate.

- **Per-flight test-suite metrics tracking.** First flight in M10
  to capture per-suite wall-clock + pass counts + flake observations.
  Unit suite ran +38 tests faster than F4 (-2.04s, throughput
  recovered from F4's 14.5 to 15.06 tests/s); no new warnings; zero
  flakes. Browser suite added 7 tests for +20s wall-clock,
  dominated by subprocess-spawn overhead per file.

- **One-way import direction preserved throughout.** Despite F5
  introducing a new cross-subsystem surface (the `the_one/sessions/`
  package), no `connectors → interfaces.web` or
  `sessions → connectors/interfaces` import was added. Grep-verified
  at leg-2 and leg-6 ends.

- **Clean Shape-A migration of `Session.subscribers`.** The leg-2
  design offered a Shape B fallback (keep field as back-reference);
  Shape A held across all 14 in-app call sites without needing the
  fallback. The dataclass is leaner (two fields removed, one added).

## What Could Be Improved

### Process

- **Live-broadcast visibility-tagging asymmetry was buried in a leg
  log instead of surfaced as a flight-level Known Issue.** L5's
  flight-log entry calls out that the WS-typed path's live broadcast
  doesn't carry `visibility` until refresh; L6's dispatcher path
  closes the same gap naturally because its broadcast fires AFTER
  tagging. The asymmetry has operator-visible UX impact (operator
  refreshes the browser to see the marker on their own just-typed
  turn). Should have lived in the flight's Known Issues section,
  not buried in code comments + leg-log. **Recommendation**: future
  flights that knowingly defer an operator-visible behavior gap
  must surface it to the flight artifact's Known Issues section,
  not only the leg-level log.

- **The leg-3 `operator_default: bool` kwarg confusion was caught at
  implementation time, not design time.** The leg author had to
  re-do the analysis to realize both call sites share post-step
  logic and the entry-point USER tagging belongs at the caller.
  Flight design should have factored more precisely; instead the
  flight artifact records "REVISED OUT" inline (flight.md:144).
  **Recommendation**: when a design specifies a divergence-flag
  parameter on a helper, the design review should ask "does the
  divergence belong on the caller, not the callee?" before the leg
  artifact ships.

- **HAT-surfaced F2/F4-territory findings (system-prompt account-id
  enumeration; pre-existing data validator violations; stub plugin
  not in production) were correctly handled by the HAT-as-catch-all
  model** — operator explicitly endorsed this model in the debrief
  interview ("Right model — HAT is the catch-all"). No process
  change recommended; just keep using HAT for cross-flight bleed
  detection.

### Technical

- **Live-broadcast visibility gap on WS-typed path** (acknowledged
  in L5 + L8 + Developer debrief). The frontend channel is wired
  (`data.visibility` forwarded through `addMsg`, `buildToolMsg`,
  the streaming-bubble closure); closure requires either pre-step
  USER tagging or post-step broadcast deferral. Operator endorsed
  scope discipline ("Right scope discipline — defer is fine"); the
  fix should land in F6 or F10. **Severity**: Important (UX),
  not Critical.

- **HAT-surfaced F4 design-completeness gap**: `compose_system_prompt`
  (`the_one/agent/config.py:72-108`) advertises the platform-send
  tool but does NOT enumerate the agent's attached `account_id` /
  `channel_id` values, so the LLM has no way to formulate a valid
  `send_to_platform_channel` invocation. Operator-in-HAT could not
  get the agent to call the tool without manual hand-holding. F4
  territory; **F8 (Discord) cannot land without this closure** —
  it's the first real-platform exercise.

- **Stale `agents.md:357` visibility-tagging contract paragraph.**
  Says "the dispatcher walks new messages produced by `agent.step()`
  and tags `Message.visibility`" — F5 L3 lifted this into the
  shared helper at `the_one/connectors/visibility.py`; the WS
  storage-edge shim now calls it too. Doc rewrite needed.

- **`connectors/README.md` §11 (outbound flow trace) needs a sibling
  §12 (WS storage-edge shim path).** Currently makes no mention of
  `tag_post_step_visibility` or the WS-side shim. F5 is the
  significant architectural change to the visibility-tagging
  contract; the README's outbound-flow narrative should grow.

- **Hard-coded `"send_to_platform_channel"` string literal in
  `visibility.py:66`** carried forward from F4 (out of scope for
  L3's pure-refactor). Becomes real debt if F8/F9 adds a second
  platform-affecting tool or the tool is renamed. Trivial to
  promote to `connectors.PLATFORM_SEND_TOOL_NAME`; defer to a
  maintenance pass.

- **JS literal `'operator'` vs. Python `OPERATOR_VISIBILITY = "operator"`
  cross-language sentinel drift risk.** The JS render layer hard-
  codes the string at `message-bubble.js:35,44,55`; no test pins
  the cross-language invariant. If the Python constant ever changes,
  the JS comparison silently breaks. **Recommendation**: a unit
  test that imports the Python constant and asserts the JS file
  contains the same literal would lock the contract.

- **`session_locks` defaultdict memory growth** inherited from F3:
  monotonic accumulation per session_id over process lifetime; no
  eviction. Documented in `the_one/sessions/_locks.py:14-19`. F10
  hardening territory (`WeakValueDictionary` / TTL / LRU).

- **Pre-F2 data row with `idle_timeout_seconds=0`** surfaced during
  HAT preflight; the F2 validator rejected it on every
  `/api/connector-accounts` GET (HTTP 500). Resolved via SQL UPDATE
  during HAT; no backfill migration was added. Same shape will
  recur for any operator who upgrades through F2 with pre-existing
  rows. F2 carry-forward; recommend a one-shot backfill in F10 or
  routine maintenance.

- **`Session.platform` cached-field staleness.** Set at restore time;
  never invalidated mid-process. F6's pairing/detach flow may need
  to invalidate. No test pins propagation of admin-side `platform`
  changes into cached Sessions without process restart.

### Documentation

- **`agents.md:357` visibility-tagging contract paragraph is stale**
  (see Technical above).

- **`connectors/README.md` needs a §12 WS storage-edge shim path
  walkthrough** (see Technical above).

- **No documented "how to debug the visibility-tagging chain."** The
  chain is: `agent.step()` appends → storage-edge shim tags
  `Message.visibility` → `encode_messages` persists →
  `decode_messages` re-hydrates → `messages_to_ui_events` projects
  `visibility` key → JS `renderMessage` consumes `opts.visibility`.
  A one-paragraph traceback walk would help future maintainers
  diagnose "marker missing on bubble X" reports.

- **F4 design-completeness recommendation for `compose_system_prompt`
  to enumerate attached `account_id` values** (HAT-surfaced; see
  Technical) should land in the mission's Known Issues so F8 can't
  miss it.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|---|---|---|
| L1 author pre-emptively extracted `_session_to_list_payload` helper (instead of using TestClient/WS path) | Leg authorized either; helper produced a cleaner test surface | Yes — when leg authorizes "refactor if cumbersome", prefer the refactor if the test-surface gain is real |
| L4 added a symmetric shim to `_resume_paused_session` (not in original flight spec; surfaced in design review) | Resume path also appends messages that need tagging; otherwise persisted as peer-visible | Yes — any storage-edge shim should be applied at every entry point that appends to `agent.messages`, not just the primary one |
| L5 changed module name `_visibility.py` → `visibility.py` (no leading underscore) | Leg-4 imports from a different package; leading underscore violates Python convention | Yes — single-character naming choice; "underscore = package-internal" convention should be followed when cross-package imports are planned |
| L5 bumped CSS specificity to `.area-chat .msg.msg-operator-only` (0,2,0 vs. design's 0,1,0) | Existing `.msg.tool` border-left wins at 0,1,0 specificity; needs 0,2,0 to override | Yes — when adding a class that visually competes with role-class rules (e.g. `.msg.tool`, `.msg.assistant`), use class-on-class specificity (0,2,0) |
| L6 codec `messages_to_ui_events` gained `index_offset: int = 0` kwarg-only parameter (added during design review) | Without it, consecutive dispatcher inbounds on the same session emit colliding `parent_message_id="replay-msg-0"` values | Yes — when reusing a slice-projecting helper across multiple turns, pass absolute indices via offset to keep generated ids unique |
| HAT bumped `--fg-tertiary` from `#666666` to `#999999` and `--fg-faint` from `#444444` to `#808080` (dark mode) | Failed WCAG AA contrast (~3.4:1 and ~2:1 respectively); fix benefits all 18+5 token consumers | Yes — verify WCAG AA contrast (4.5:1 for normal text) for every token used in dark-mode text consumers; the existing palette had pre-F5 gaps that F5 exacerbated |
| HAT suppressed `msg-operator-only` class + label on `.msg.user` bubbles (operator's own typed messages) | Marker is "this message is NOT visible to peers" — addressed FROM the system TO the operator, makes no sense on the operator's own messages | Yes — visibility markers signaling "what's hidden from X" should suppress on bubbles authored BY the addressee |
| HAT renamed Studio "Connector Accounts" → "Connectors" + dropdowns + button restyling | F2 surface had design-language drift surfaced when HAT exercised the surface end-to-end | Process: HAT-as-catch-all model worked; no rename guideline needed |
| HAT skipped acceptance steps 5, 6, 8 (live platform-send, live dispatcher-inbound, concurrent-turn serialization) | Stub plugin is `register_for_test`-only; not registered in production | Process note: a production-registered stub OR a real plugin is required for full HAT coverage; F8 closes this for Discord |
| Pre-existing `connector_accounts` row with `idle_timeout_seconds=0` blocked the Admin surface (HTTP 500 on GET) | F2's validator (1..604800s) was added after the row was created; pre-F5 data | One-off; document for F10 maintenance backfill |

## Key Learnings

1. **Architectural extraction before consumption is the right ordering.**
   L2's lift of subscribers/broadcast to the neutral `the_one/sessions/`
   package paid off in L6, which became a 4-line consumer with zero
   new function-local-imports. If L6 had been first, the dispatcher
   would have needed an `interfaces.web.app` function-local-import
   that inverted the established direction.

2. **Storage-edge shim shape is reusable.** `pre_step_len = len(messages)`
   → `agent.step` → `tag_post_step_visibility(messages, pre_step_len)`
   is now applied at three sites (`_process_and_broadcast`,
   `_resume_paused_session`, `dispatch_inbound`). Future "tag-
   something-at-storage-edge" needs (cost telemetry per-turn, F10
   hardening, etc.) should adopt the same pattern.

3. **Visibility markers signaling "what's hidden from X" should
   suppress on bubbles authored BY X.** Generalizes the HAT-surfaced
   `.msg.user` suppression: any UI marker addressing the operator
   about peer visibility should not appear on the operator's own
   bubbles. Worth a design-language guideline.

4. **Pre-leg design reviews are cost-effective.** Across F5,
   reviewer feedback caught a missed test-file set (L2), a placement
   error (L3), an unplanned symmetric shim (L4), wrong selectors +
   missing tokens (L5), and a `parent_message_id` collision (L6).
   Each would have produced rework or shipped as a bug. Cost was
   ~20% of leg planning time; benefit was substantial.

5. **HAT as the catch-all for cross-flight bleed works.** F5 HAT
   surfaced three F2/F4-territory issues that automated tests
   couldn't have caught. Operator explicitly endorsed the model.
   Future flights touching operator-visible surfaces should
   inherit the required-HAT pattern (F6, F8, F9 in particular).

6. **Codec `index_offset` is a small but architecturally correct
   pattern**: when a slice-projecting helper is reused across turns,
   the absolute index should be passed in via an offset parameter
   to keep generated ids unique. Default-0 preserves byte-identical
   behavior for the original call sites.

7. **Per-flight test-suite metrics tracking is valuable.** F5's
   debrief is the first flight to capture per-suite wall-clock +
   pass counts + flake observations. Future flights should
   inherit this; comparison across F1-F5 immediately revealed
   that F5 ran +38 tests in -2.04s (throughput recovered).
   Standardize this in the debrief skill's prompt going forward.

## Recommendations

1. **Close the live-broadcast visibility gap on the WS-typed path
   in F6 or F10.** The asymmetry (inbound side tagged in live
   broadcasts; WS-typed side requires refresh) is operator-visible
   UX debt with two viable closure paths (pre-step USER tagging
   or post-step broadcast deferral). Surface it to the mission's
   Known Issues so F6 author sees it.

2. **F4 design-completeness pass: enumerate attached `account_id` /
   `channel_id` in the connector-aware system prompt.** F8 cannot
   land without this — the HAT operator couldn't get the agent to
   call the platform-send tool because the LLM had no way to
   discover its valid targets. The `_CONNECTOR_TOOL_ENABLED_DIRECTIVE`
   in `the_one/agent/config.py` is already the site-of-extension;
   just needs to be data-driven from `config.connector_account_ids`.

3. **Update stale documentation.** Three concrete edits:
   (a) rewrite `agents.md:357` visibility-tagging contract paragraph
   to reflect the shared-helper bilateral architecture;
   (b) add `connectors/README.md` §12 (WS storage-edge shim path)
   walking through the operator-typed-into-connector-attached flow
   with file:line references;
   (c) add a "how to debug the visibility-tagging chain" paragraph
   to `connectors/README.md` covering the full chain from
   `agent.step()` through to JS `renderMessage`.

4. **Make HAT-required (not optional) the default for operator-
   visible flights.** Codify in the mission's design-language
   quality bar criterion (mission.md L45) that any flight touching
   operator-visible surfaces ends in a required HAT closer. F6
   (pairing/ACLs), F8 (Discord), F9 (second connector) should all
   inherit. F10 (hardening) may not need one.

5. **Standardize per-flight test-suite metrics in the debrief skill.**
   F5 is the first flight to capture per-suite wall-clock + pass/
   skip counts + flake observations. Codify this in the
   flight-debrief skill prompt so every future flight captures the
   same shape; comparison across flights is the value, and it only
   works if every flight contributes a row.

## Action Items

- [ ] **F6 or F10**: close the live-broadcast visibility gap on
      the WS-typed path. Pre-step USER tagging is the simpler
      option.
- [ ] **F8 prerequisite**: extend `compose_system_prompt` to
      enumerate the agent's attached `account_id` / `channel_id`
      values from `config.connector_account_ids`.
- [ ] **Documentation pass** (small, can land independently):
      rewrite `agents.md:357` visibility-tagging contract;
      add `connectors/README.md` §12 (WS storage-edge shim path);
      add visibility-tagging-chain debugging paragraph.
- [ ] **Mission Known Issues update**: add the live-broadcast
      visibility-asymmetry as an explicit Known Issue (currently
      only in code comments + flight-log).
- [ ] **F10 maintenance**: backfill migration for
      `connector_accounts` rows with `idle_timeout_seconds` outside
      the validator's range; lock-registry memory-growth mitigation
      (`WeakValueDictionary` / TTL); platform-send tool_result
      first-class-bubble render improvement.
- [ ] **Methodology**: codify per-flight test-suite metrics capture
      in the flight-debrief skill prompt; codify "operator-visible
      flights end in required HAT" in the mission's design-language
      quality-bar criterion.
- [ ] **Cross-language sentinel pin** (small): a unit test that
      imports `OPERATOR_VISIBILITY` from Python and asserts the
      string literal `'operator'` appears in
      `the_one/interfaces/web/static/js/areas/chat/message-bubble.js`.

---

## Test-Suite Metrics

| Suite | Pass | Skip | Deselect | Warning | Failed | Flakes | Wall (s) | Throughput |
|---|---|---|---|---|---|---|---|---|
| `make test-unit` | **1983** | 4 | 409 | 1 (pre-existing aiosqlite teardown) | 0 | 0 | 131.69 | 15.06 tests/s |
| `make test-browser` | **352** | 35 (pre-existing M07 F8 deferrals) | 12 | 0 | 0 | 0 | 315.75 | 1.11 tests/s |

**Cross-flight comparison (M10):**

| Flight | Unit tests | Unit Wall (s) | Unit Throughput | Browser tests | Browser Wall (s) |
|---|---|---|---|---|---|
| F1 | 1774 | 100.58 | 17.6 | — | — |
| F2 | 1805 | 106.69 | 16.9 | 345 | 295.21 |
| F3 | 1881 | 127.40 | 14.8 | — | — |
| F4 | 1945 | 133.73 | 14.5 | — | — |
| **F5** | **1983** | **131.69** | **15.06** | **352** | **315.75** |

F5 added +38 unit tests vs. F4 but ran -2.04s faster (throughput
recovered from 14.5 to 15.06 tests/s); browser suite added +7 tests
for +20.54s wall-clock dominated by per-file subprocess-spawn
overhead. No new warnings, no flakes.
