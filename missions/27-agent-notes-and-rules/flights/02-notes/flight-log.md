# Flight Log: Notes

**Flight**: [Notes](flight.md)

## Summary

Planned 2026-10-09 while the operator was away overnight (authorized to plan
and execute up to the mission HAT). The research was done during Flight 1. The
key finding is that the untrusted flag can be computed without touching the
frozen loop, from a per-turn context variable that callers set around
`agent.step` (DD5, DD6). That removes the mission's pre-declared split risk.

---

## Leg Progress

### notes-store-and-prompt

Landed (leg 1). v43 (`agent_notes`, `agents.notes_enabled`, `agents.notes_next_number`), `AgentNoteRepository` and `AgentNote`, `AgentConfig.notes_enabled` with `set_notes_enabled` and preserve-on-omit, `compose_system_prompt(..., notes=None)` with `RenderedNote` (in `agent/config.py`), `render_rules_block(notes_present=)`, `build_system_prompt` loading notes, and the five REST routes (settings route registered before `/{note_id}`). No agent-facing tool exists. `make test-unit`: 5740 passed, 11 skipped (one timing-conditional skip over the known 10, within the documented 10/12 band reasoning); ruff check and format clean.

Interface for leg 2 (names and signatures exactly as the leg states):
- `AgentNoteRepository.create(name, text, *, untrusted, sources, origin_kind, origin_session_id, origin_label, origin_platform, origin_peer_id, origin_peer_name) -> (note, created)`
- `update_by_agent(name, number, text, *, untrusted, sources) -> (note, changed)`
- `forget_by_agent(name, number) -> AgentNote` (returns the removed note)
- Errors (all in `the_one/db/_notes.py`): `NotesDisabledError`, `NoteLimitError`, `NoteDuplicateError` (has `.number`); `KeyError` for a missing note or agent. Each has `.detail` (sizes/number only, never note text). Constants `NOTE_WRITES_PER_TURN`, `SOURCES_CAP` are there too.
- Differences/additions to note: the duplicate-on-`create` path returns `(existing, False)` and consumes no number; a duplicate `update_by_agent` raises `NoteDuplicateError` with the other note's `.number`. Added `list_if_enabled(name)` (prompt loader). `RenderedNote` is in `the_one/agent/config.py`; notes helpers live in `the_one/db/_notes.py` (not `the_one/notes/limits.py`).

### notes-tools-and-provenance

Landed (leg 2). AC2 first: `tests/test_notes_context.py` proved a `TurnContext` set around `Agent.step` is visible and mutable inside `tool.execute` on this Python 3.12 (no `[BLOCKED:frozen-loop]`); `the_one/agent/core.py` is unmodified. Added `TurnPeer`, `TurnContext`, `current_turn` to `the_one/agent/_context.py`; set sites (token pattern, reset in `finally`) in `_process_and_broadcast` (covers WebSocket and REST `/api/chat`), `_resume_paused_session`, `dispatch_inbound`, the CLI step and the two `selftest` steps. New package `the_one/notes/` (`tools.py`: `SaveNoteTool`/`UpdateNoteTool`/`ForgetNoteTool`, `compute_taint`, `TRUSTED_TOOL_NAMES`, `BUDGET_REFUSAL`; `tool_provider.py`: `NotesToolProvider`). `AgentFactory` gains `notes_provider`, registers the tools outside the whitelist filter, seeds them, and binds them after `agent = Agent(...)`. `SECURITY-MODEL.md` "Agent notes (M27 F2)" and `agents.md` "Notes tools, turn context and provenance" written.

Verification: `make test-unit` 5797 passed, 11 skipped (all 11 are Windows-only: 10 in `tests/test_pty_windows.py` plus `tests/test_pty_dispatch.py`'s dispatch test, confirmed with `-rs`; none is timing-conditional and none comes from this leg; the leg-1 "one over 10" is a miscount of the Windows PTY file, which has 10 skipped tests, not 9); `ruff check` and `ruff format --check` clean. The contract tests were falsified: forcing `compute_taint` to return `(False, [])` fails 24 of 50 in `tests/test_notes_tools.py` (every planted-instruction case), and replacing the backward anchor search with a forward one fails `test_ids_repeating_across_turns_are_flagged` and `test_ollama_bare_name_ids_identical_every_turn_are_flagged`.

Contract tests (`tests/test_notes_tools.py`): `test_planted_instruction_never_yields_an_unflagged_note` (parametrized over eight untrusted tool names; each case saves in a later iteration of the same turn, in a later turn, and after an encode/decode restore, and checks the flag, the source, and the `(unverified)` rendering in the rebuilt prompt) and `test_planted_instruction_from_a_peer_message_is_flagged`; the repeated-id cases `test_ids_repeating_across_turns_are_flagged` and `test_ollama_bare_name_ids_identical_every_turn_are_flagged` (a clean save under id X, a fetch, then a save under the same id X, which a forward search would call clean); `test_earlier_turn_fetch_then_save_is_flagged`, `test_fetch_and_save_in_one_assistant_message_is_not_flagged`, `test_orphaned_tool_result_is_flagged_unknown_tool`, `test_continue_result_is_not_flagged`, `test_web_operator_only_conversation_is_clean_with_web_origin`, `test_connector_peer_turn_is_flagged_with_connector_origin`, `test_restored_history_with_an_earlier_fetch_is_flagged`, `test_restored_clean_history_is_not_flagged`, `test_resume_after_auth_uses_the_resume_context_and_flags`, `test_save_in_iteration_two_after_fetch_in_iteration_one_is_flagged`, `test_budget_applies_in_order_and_sixth_is_refused`, `test_unbound_tool_fails_closed_unknown_position`, `test_none_tool_call_id_fails_closed_unknown_position`, `test_flagged_note_updated_in_a_clean_conversation_stays_flagged`, `test_newline_injection_is_one_line_and_forges_no_note_line`, `test_notes_off_mid_conversation_refuses_all_three`, `test_limits_numbering_and_refusal_texts`; the REST and tool-stream cases `test_process_and_broadcast_sets_turn_context_with_session_id` and `test_save_note_appears_as_ordinary_tool_messages_in_the_persisted_session`; the connector set site `test_dispatch_inbound_sets_turn_context_with_the_envelope_peer` (`tests/test_connectors_inbound.py`); `TestNotesToolWiring` (`tests/test_factory.py`).

### notes-ui

Landed (leg 3). The Notes section in `rules-notes-tab.js` (switch, off message with the list kept, usage line, rows with origin/time/"Edited by you"/"Check this", inline edit, armed delete, Clear all through `App.confirmDialog`, create-mode notice), the `studio.js` callbacks (also threaded through `agent-editor.js`, which hand-picks the tab's callbacks), the drawer Notes group, CSS, registry rows, docs (`agents.md`, `CLAUDE.md`). The explicit-origin fold-in: `mutate` is now one shared `makeMutate(cfg)` taking `opts.origin`; the Rules section was moved onto it, along with shared `buildInlineEditor`/`buildDeleteButton`.

Verification: new `tests/browser/test_flow_agent_notes.py` (12 tests incl. the `<b>x</b>` literal-render test, a mouse-click-style failed save, and one real-chain test where a mock turn's `tool_calls` run `save_note`); six Notes tests added to `test_flow_chat_drawer.py`; one Rules test added (`page.click` on a failing Add lands focus on the Add textarea, closing the Flight 1 cycle-3 residual). `--lane agents`: 181 passed, 363 s pytest (390 s wall including start-up) against the 510 s budget. `--lane chats`: 177 passed, 253 s (273 s wall) against 360 s. Static guards (`test_ui_guards`, `test_token_definitions`, `test_design_tokens_a11y`) pass; `make test-unit` 5796 passed, 11 skipped (the Windows-only PTY skips) plus the one fix below; ruff check and format clean.

Seeding approach (AC9): a direct `sqlite3` insert (`seeders.seed_note`, bumping `agents.notes_next_number`) for notes with a chosen origin, age, taint or peer, because the mock provider cannot make `save_note` run after an untrusted tool result with a static response (the same `tool_calls` repeat each iteration and a duplicate save is a no-op). The real chain is proved by one test whose mock provider returns a `save_note` call.

---

## Decisions

### Autonomous judgement calls (for HAT review)

- **DD1:** the notes table's columns, and the per-agent number counter on
  `agents`.
- **DD3:** the tool names `save_note`, `update_note` and `forget_note`. The
  tools are seeded into the baseline and are not built-ins, so they do not
  appear in either Built-in Tools surface.
- **DD6:** the trusted-tool set is the notes tools plus `search_tools`; every
  other tool is untrusted, fail-closed. Every connector-peer message counts as
  untrusted.
- **DD8:** limits of 400 characters per note, 4,000 characters in total, and 5
  writes per turn. Duplicate detection uses normalised exact match.
- **DD9:** the prompt wording, the `<saved_notes>` delimiters, and the
  "(unverified)" marker.
- **DD10:** layout and copy: the "Check this" badge; text editing in the tab
  only, while the drawer prunes.
- **DD11:** there is no operator create route.
- **(autonomous judgement call) Leg 1, precedence sentence placement:** "Rules take precedence over saved notes." is placed on the line right after the rules heading (before the numbered rules), not after the list.
- **(autonomous judgement call) Leg 1, loader read:** `build_system_prompt` reads the switch and notes through a new `AgentNoteRepository.list_if_enabled(name)` (rather than a raw `SELECT` in the loader), so factory tests that stub repository classes can stub it like `AgentRuleRepository`. Eleven existing patch sites in `test_factory.py`, `test_search_tools.py` and `test_mcp_tool_provider.py` gained a matching `AgentNoteRepository` stub.
- **(autonomous judgement call) Leg 1, normalisation:** after `" ".join(text.split())`, remaining `Cc` characters are removed and whitespace re-collapsed (so `"a\x00 b"` stays `"a b"`).
- **(autonomous judgement call) Leg 1, display label:** a web/connector note with a session id but no stored label and no live chat shows "Untitled chat"; an `other` note with no label stays `None`.
- **(autonomous judgement call) Leg 1, no-op/duplicate rule on operator edit:** identical normalised text returns `changed=False` (REST returns the unchanged note with 200).

- **(autonomous judgement call) Leg 2, refusal mechanism:** every refusal is raised as `ValueError(<exact text>)`; repository errors (`NotesDisabledError`, `NoteLimitError`, `NoteDuplicateError`) are re-raised as `ValueError(e.detail)` and a missing note as `ValueError("No note [n].")` (a `KeyError` would render with quotes). The loop's generic handler turns each into `is_error=True` / `[error] Tool execution failed: <text>`.
- **(autonomous judgement call) Leg 2, check order:** the per-turn budget check runs BEFORE the repository call, so an over-budget save is refused as "Note limit for this turn reached (5 writes)." even when notes are also off; the switch refusal comes from the repository. A save whose text the repository refuses (empty, too long, full) does not count toward the budget.
- **(autonomous judgement call) Leg 2, `TurnPeer`:** a frozen dataclass; `selftest` and the CLI set an empty `TurnContext()` (no session, no peer) so their notes come out "other" origin and clean unless a trusted-set violation occurs. A resumed web turn has `peer=None`; a resumed connector turn still flags through the `peer_name` on the earlier USER message, which `dispatch_inbound` binds after its step returns.
- **(autonomous judgement call) Leg 2, unbound-with-no-name:** a notes tool with no `agent_name` refuses with "Notes are unavailable: this tool is not attached to an agent." rather than writing for `None`.
- **(autonomous judgement call) Leg 2, `number` coercion:** an int, or an int-string, is accepted; a bool, float or non-numeric string is refused with "number must be an integer."
- **(autonomous judgement call) Leg 2, origin label:** read with one `SELECT title FROM chat_sessions` at write time; a missing row or any error gives `None` and the note is still saved.
- **(autonomous judgement call) Leg 3, "Changes apply..." line:** it sits in the Rules section, so the Notes section repeats the same text (`notes-applies-note`) under its switch rather than moving it to tab level.
- **(autonomous judgement call) Leg 3, usage numbers:** thousands separators ("0 of 4,000 characters"), matching DD10's wording; the limit comes from the GET's `limits.total_chars`.
- **(autonomous judgement call) Leg 3, dates:** a note's time is `App.time.formatClock` for today, else `Mon D` (the year is added only when it is not the current year); "Updated ..." replaces the created time once edited.
- **(autonomous judgement call) Leg 3, "Check this" styling:** an elevated-surface badge with a warning ring and `--fg` text (the `.badge--approved` recipe), so it needs no new contrast pair; it carries `role=note` with the sources in `aria-label` and `title`.
- **(autonomous judgement call) Leg 3, connector origins:** platform badge plus peer name, and also the chat link when the chat still exists.
- **(autonomous judgement call) Leg 3, drawer extras:** the "Edit notes" link also shows while notes are off (to reach the switch); after a delete or clear, focus goes to the neighbouring note's Delete or the link; Clear all's armed text is "Clear all {n}?".
- **(autonomous judgement call) Leg 3, create mode:** both the Rules and Notes notices show ("Save the agent first to add rules." / "Save the agent first to let it keep notes."), no controls.

---

## Deviations

- **Leg 1:** DD8's `the_one/notes/limits.py` became `the_one/db/_notes.py` (cycle-safe beside `_rules.py`, per the leg). `tests/test_db_migration.py` assertions of `CURRENT_VERSION == 42` (v41 case, `TestSchemaV42` fresh replay) were updated to 43, and `TestSchemaV42::test_rerun_on_v42_changes_nothing` now rewinds stamps `>= 42` (it deleted only stamp 42, which no longer triggers the v42 block once 43 is stamped). `test_notes_are_reserved_and_ignored` was rewritten per AC12.

- **Leg 2:** `tests/test_prompt_layers.py::test_factory_build_carries_notes_and_registers_no_notes_tool` (leg 1) asserted no notes tool exists; it is renamed `..._registers_the_notes_tools` and now asserts the three tools are registered. The `AgentFactory` constructor gained `notes_provider`; the provider's `get_tools_for_agent` returns `[]` without a database call when notes are off, so no existing factory test needed a notes stub.

- **Leg 3:** `tests/test_nav_guard_static.py` allowed `App.confirmDialog` calls only from `ui-modal-section.js`; the leg requires the Notes section's Clear all to use it, so `rules-notes-tab.js` joined the allow-list with a comment. `agent-editor.js` (not listed in the leg) hand-picks the callbacks it passes to the tab, so it gained the five notes callbacks. Shared inline-editor/delete builders cannot take a `testid` option (the registry guard needs literal ids), so callers set the `data-testid` literals on the returned nodes.

---

## Anomalies

---

## Session Notes

### Flight Director Notes
- Flight 1's debrief is deferred until after the mission HAT, by Flight Director
  judgement while the operator is away. The debrief benefits from operator
  input.
- **Design review, cycle 1** (Architect, Opus): approve with changes, 2 high
  findings. All were applied by rewriting DD1-DD13 in place, since the flight
  is still in planning.
  - **High:**
    - Ollama tool-call ids repeat across turns, so the anchor search runs
      backwards and results are attributed by position (DD6).
    - Newline injection could forge a `[n]` line, so text is collapsed to one
      line at write, with case-insensitive delimiter neutralisation (DD8,
      DD9).
  - **Medium:**
    - the signature becomes `notes=None` (None means off), with
      `RenderedNote`;
    - `build_system_prompt` loads notes itself, so `next_turn` keeps them;
    - an execute-time switch re-check stops writes from already-built agents;
    - `continue` is trusted;
    - the origin label is the live title through a LEFT JOIN;
    - the tools bind to their `Agent` instead of a list reference.
  - **Low:**
    - `notes_next_number` stays out of `AgentConfig` and the upsert;
    - route order;
    - DD2 wording;
    - `peer_name is not None`;
    - fixes to behavior-spec steps 2 and 7 and its preconditions.
  - **Questions answered:**
    - a resumed turn gets a fresh write budget;
    - `forget_note` also refuses while notes are off;
    - a `next_turn` recompose showing earlier notes in an open conversation is
      accepted.
  - A second cycle is run because the changes are substantive.
- **Design review, cycle 2** (Architect, Opus): approve with changes. The
  cycle 1 fixes were confirmed, with no contradictions between DDs. Applied:
  - **Medium:** an agent `update_note` ORs the taint flag and merges sources,
    and the origin stays the creating conversation.
  - **Low:**
    - the "any rules above" wording;
    - `render_rules_block(notes_present=False)` by default;
    - `" ".join(text.split())` as the normalisation mechanism;
    - binding details (`agent = Agent(...)`, `bind_agent` on the notes class,
      an unbound tool fails closed, `agent_name` plumbing);
    - one shared fallback counter;
    - corrected set-site wording;
    - DD12 cases split out (restored clean versus tainted history, Ollama
      bare-name ids, the update-stays-flagged case, Unicode line separators);
    - `textContent`-only rendering.
  - **Open for the HAT:** whether the operator can clear a reviewed "Check
    this" flag (no such action is built).
  - The 2-cycle maximum is reached, the remaining changes are clarifications,
    and the flight is marked `ready`.
- **Execution started:** `leg-execution.md` loaded, and the flight marked
  `in-flight`. Three autonomous legs, no HAT leg.
- **Leg 1 `notes-store-and-prompt`:** tiered **high-risk** (a schema migration,
  a change to `compose_system_prompt`'s contract with existing callers and
  tests, and the prompt every agent is built with). It gets a Developer
  leg-design review.
- **Leg 1 design review** (Developer): approve with changes, after one cycle. Applied: the TestSchemaV42 pin is named; `RenderedNote` lives in `agent/config.py` (`_notes.py` never imports `agent`); the exact `create` kwargs and `origin_kind` validation; `get` returns None while mutators raise `KeyError`; the duplicate scan excludes the note's own row, and an identical-text update is a no-op; Cc controls are stripped too; `StrictBool`; `AgentNote` in `models.py`; `total_chars(exclude_id)`; extra edge cases. These are clarifications, so there was no second cycle, and the leg is `ready`.
- **Leg 1 design review** (Developer): approve with changes, after one cycle. Applied: the TestSchemaV42 pin is named; `RenderedNote` lives in `agent/config.py` (`_notes.py` never imports `agent`); the exact `create` kwargs and `origin_kind` validation; `get` returns None while mutators raise `KeyError`; the duplicate scan excludes the note's own row, and an identical-text update is a no-op; Cc controls are stripped too; `StrictBool`; `AgentNote` in `models.py`; `total_chars(exclude_id)`; extra edge cases. These are clarifications, so there was no second cycle, and the leg is `ready`.
- **Leg 2 design review** (Developer): approve with changes. Applied:
  - the web set site moved inside `_process_and_broadcast`, which also covers the REST `/api/chat` path that DD5 missed; `TurnContext` gains `session_id` so REST notes get a web origin without changing `current_chat_session_id`;
  - the error mechanism is decided: refusals raise, and tests assert `is_error`;
  - the tool's own call id comes from `current_tool_call_id`;
  - `update_by_agent` returns (note, changed), and an unchanged update does not count;
  - the resume test recipe, same-turn, budget-order and fail-closed cases, and test doubles.
  - The leg is `ready` and waits for leg 1 to land.
- **Leg 2 design review** (Developer): approve with changes. Applied:
  - the web set site moved inside `_process_and_broadcast`, which also covers the REST `/api/chat` path that DD5 missed; `TurnContext` gains `session_id` so REST notes get a web origin without changing `current_chat_session_id`;
  - the error mechanism is decided: refusals raise, and tests assert `is_error`;
  - the tool's own call id comes from `current_tool_call_id`;
  - `update_by_agent` returns (note, changed), and an unchanged update does not count;
  - the resume test recipe, same-turn, budget-order and fail-closed cases, and test doubles.
  - The leg is `ready` and waits for leg 1 to land.
- **Leg 3 `notes-ui`:** designed and tiered **low-risk**: additive UI on Flight 1's established tab and drawer patterns. The `mutate` explicit-origin refactor is covered by the existing Rules browser tests. It skips the per-leg design review, and the flight-end Reviewer and Accessibility Reviewer cover it. The leg is `ready`.
- **Leg 1 landed** (Developer: 5740 passed, 11 skipped, ruff clean; the extra skip was not confirmed with `-rs`, so leg 2 is told to report its skips). Leg 2 Developer spawned.
- **Leg 2 landed:** 5797 passed; the 11 skips are all Windows-only, confirmed with `-rs`. The contract test `test_planted_instruction_never_yields_an_unflagged_note` was falsified against a broken taint check (24 tests failed) and a forward anchor search (the 2 repeated-id tests failed). Leg 3 Developer spawned. An early backend security review (Sonnet: a security-sensitive surface) runs in parallel, scoped to non-`static` files; any fixes wait until leg 3 lands, to avoid working-tree collisions.
- **Early backend security review** (Sonnet): `[HANDOFF:confirmed]` with no
  blocking items, and no path to an unflagged note from outside content
  (304 targeted tests pass, ruff clean, `core.py` untouched). Non-blocking:
  - **`search_tools` is trusted** although its output can carry MCP
    descriptions from outside sources. This is already documented as a
    residual risk in `SECURITY-MODEL.md` (the "Agent notes" section, which
    names `search_tools` output). Kept as DD6 states, and **flagged for HAT
    review** *(autonomous judgement call: flagging every note after a tool
    search would put a flag on nearly every note)*.
  - Category `Cf` characters (zero-width, bidi) survive normalisation. This
    is cosmetic: the delimiter cannot be forged.
  - The `update_agent` read-then-save race is the same as the approval flag's.
  - A resumed turn gets a fresh budget. This was already accepted.

  None needs a fix before the flight review.
- **Leg 3 landed:** `agents` lane 181 passed in about 390 s of a 510 s budget; `chats` lane 177 passed in 253 s. Leg 3 widened `tests/test_nav_guard_static.py`'s `confirmDialog` allow-list to include `rules-notes-tab.js`. The Flight Director judged this legitimate: the guard stops per-area *leave guards* from coming back, and Clear all is a blocking destructive decision that DD10 specifies. The flight Reviewer (Sonnet: the security-sensitive surface) and the Accessibility Reviewer were spawned over the full diff.
- **Flight review, cycle 1:**
  - **Reviewer (Sonnet):** `[HANDOFF:confirmed]`. 5797 passed and 11
    skipped; notes and rules browser files 25/25. No HTML sinks; hrefs are
    built only through `App.router.href`.
  - **Accessibility Reviewer:** 2 blocking items, both in the drawer's Notes
    group: the delete arm is not announced (4.1.3), and focus is lost after
    a failed delete (2.4.3). There are 6 non-blocking items.
  - **Fix pass spawned:** both blocking items, non-blocking items 3 and 5-8,
    and the Reviewer's test rename.
  - **Skip-count note:** the 11 skips are all Windows-only (leg 2 checked with
    `-rs`): `tests/test_pty_windows.py` now has 10 skipped tests, not the 9
    CLAUDE.md states. That is a stale doc count, and a squawk candidate for
    the debrief.

### Review fixes

- **Blocking (a11y):** the drawer's Notes group gained a polite visually hidden status line (`chat-drawer-notes-status`) that announces the Delete / Clear all arm; focus is restored after a failed delete or clear (and a failed post-delete refresh) to the same note's Delete or Clear all, falling back to "Edit notes"; a successful delete moves focus to the neighbouring Delete, else Clear all, else "Edit notes".
- **Non-blocking, fixed:** drawer "Check this" marker has `role=note` + aria-label; the tab badge's accessible name now starts with "Check this: ..." (2.5.3); `notes-off-message` is tied to the toggle with `aria-describedby` only while shown; `role="list"` on the tab's rules/notes lists and the drawer's notes list; origin link underlined; nav-guard test renamed to `..._nav_the_modal_demo_and_notes_clear_all` with docstring updated.
- **Tests:** three new drawer browser tests (arm announced, failed delete/clear focus, successful delete focus); the badge aria-label assertion updated. Static guards (264) and the drawer/notes/rules browser files (55) pass; ruff clean. The status line sits at the end of the Notes group so the existing `p.first` selectors are unaffected.
- **Flight review, cycle 2** (Accessibility re-review, Sonnet):
  `[HANDOFF:confirmed]`. Both blocking items and all non-blocking items are
  resolved. Accepted **for HAT review**, not fixed now (a full gate was
  already running; both items are minor):
  - **(a)** after an async post-delete refresh, focus is restored to the
    drawer even if the user moved focus elsewhere during the request. The
    tab's `restoreOrigin` behaves the same. The fix is to restore only when
    `activeElement` is body or inside the drawer, as `App.focusAfter` does.
  - **(b)** `announce('')` followed by the same text in one tick may be
    coalesced by some screen readers on re-arm.
- **Gate:** `make gate` is green. Unit: 5795 passed, 13 skipped (the netns
  count), in 184 s. Browser: 8 of 8 lanes `rc=0`, total wall 910 s, every
  lane within budget:

  | Lane | Wall | Budget |
  |---|---|---|
  | `agents` | 428 s | 510 s |
  | `routing` | 451 s | 600 s |
  | `settings` | 401 s | 540 s |

  The whole gate is about 18.2 min, back under 20; Flight 1's over-budget
  run was host load.
- **Legs 1-3** are marked `completed` and committed in one flight commit.
