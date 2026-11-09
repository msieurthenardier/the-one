# Flight Log: Charts in Chat

**Flight**: [Charts in Chat](flight.md)

## Summary
Ready. Flight designed 2026-11-08, two Architect review cycles folded in, approved by the operator 2026-11-08. Four implementation legs plus a HAT.

---

## Leg Progress

### chart-format-and-control
**Status**: landed (not committed)
**Changes**:
- Format and corpus: `docs/chart-format.md` (keys, limits, number display, every error sentence in one table, palette appendix); `tests/fixtures/charts/` with 23 `valid/` files, 60 `invalid/` files plus `expected.json`, and `number-format.json` (43 rows).
- Python: `the_one/visuals/chart_spec.py` (`parse_chart`, `format_tick`, `format_full`, frozen dataclasses; stdlib only); `tests/test_chart_spec.py` (147 tests).
- Browser: `js/ui/chart.js` (parse, chart, block), `js/ui/chart-placeholder.js`, `App.ui.thinking.dots()` factored in `thinking.js` (`test_ui_thinking_contract.py` untouched and green), chart CSS in `components.css`, tokens in `tokens.css`, scripts in `index.html`.
- Tokens: `--chart-1..8`, `--chart-ref` in both themes, plus `--chart-c` default in `:root`. Grid and axis reuse `--border`, `--border-strong`, `--fg-tertiary`. Mirror in `design_tokens.py`; pair tests (series x bg/surface/composited bubble, rgba parsed from tokens.css) in `test_design_tokens_a11y.py`. No `_CONTRAST_EXEMPT` needed (`--chart` is outside the fg-role prefixes).
- Catalogue: one Chart row (sub-entries parse, formatters, block, placeholder in its text), dots in the Thinking row. Contracts: `test_ui_chart_contract.py` (parse corpus parity, formatters, structure, tooltip, theme, block) and `test_ui_chart_placeholder_contract.py` (placeholder, dots).
- Lane: `contracts_chat_pat` gains `test_ui_chart*`; `test_run_tests_lanes.py` updated; CLAUDE.md prose and table updated.
**Palette (dark / light)**: 1 `#a78bfa`/`#6d28d9`, 2 `#22d3ee`/`#0e7490`, 3 `#fbbf24`/`#b45309`, 4 `#f472b6`/`#be185d`, 5 `#4ade80`/`#15803d`, 6 `#fb923c`/`#c2410c`, 7 `#60a5fa`/`#1d4ed8`, 8 `#94a3b8`/`#475569`, ref `#fbbf24`/`#b45309`. Lowest ratio 4.72:1 (light), all pass 3:1 with the board values needing no tuning.
**Lane timing**: `contracts-chat` measured 83 s and 77 s solo (host load 1.2-2.4, not a quiet `--parallel 3` reading); budget 90 -> 120 s. Re-measure at the flight's closing gate.
**Tests**: unit tier 9583 passed, 15 skipped (netns count); `contracts-chat` 336 passed (Chromium + WebKit); `contracts-controls` 1230 passed, 4 skipped (WebKit required); `test_chart_spec.py` 147 passed; static guards, ruff check and format clean.
**Decisions and notes**:
- Error sentences avoid interpolating numbers/values that need a repr; counts and names only. The values limit is checked first among limits (8 series x 200 categories is only 1600, so the 2,000 limit is otherwise unreachable); `x` log scale is an error off scatter; `x`, `y2`, `stacked`, `annotations` are dropped per type before checking.
- `block` draws a valid spec even with `closed === false`; the cut-off notice is for an invalid/truncated one.
- ResizeObserver fires for a never-attached chart in both engines, so a chart disconnects its observer on detach only after it has drawn.

### rich-visuals-switch
**Status**: landed (not committed)
**Changes**:
- Backend: `AgentConfig.rich_visuals: bool = True`; schema v52 (guarded `ALTER TABLE agents ADD COLUMN rich_visuals INTEGER NOT NULL DEFAULT 1`, `CURRENT_VERSION = 52`); `SQLiteAgentStore.save` (INSERT, ON CONFLICT update, params) and `_row_to_config`; `update_agent` keeps the stored value when the key is omitted. Responses carry it through `model_dump`. The `get_my_configuration` projection is unchanged (field list does not include it).
- Frontend: General tab Behavior `App.ui.toggle` "Rich visuals" (`agent-rich-visuals-toggle`, `dataset.field = rich_visuals`, dirty wired with `own()`), `defaults()` on, `setAgent` patches with `setChecked(c.rich_visuals !== false)`; `collectFormData` boolean branch for checkboxes; drawer group `data-group="rich-visuals"` ("On"/"Off", from `info.row`, no fetch) before Self-configuration.
- Tests: `tests/test_db_migration.py` (eleven `51` pins to 52, `TestSchemaV52`), `tests/test_agent_rich_visuals.py` (model, repository round trip, load-then-save regression, API create/omit/set/422 with `"abc"` and `null`, projection omission), `tests/browser/test_flow_agent_rich_visuals.py` (four flows, `agents` lane).
**When a change takes effect (AC9)**: at the next join of that conversation (a rejoin, reload, reconnect or switching back to it), the next new chat, or the next routine run; not on the next turn of a chat that stays open. Citations (`the_one/interfaces/web/app.py`): `_create_session` builds the `Agent` once with `factory.create(...)` (`:1717`) and caches it in `_sessions`; `_restore_session` calls `factory.create(...)` again (`:1820`) and rebinds `existing.agent = agent` (`:1892`), and `_get_or_restore_session` (`:1956-1966`) delegates to it on every call with no cache short-circuit, its docstring stating that "edits to the agent config ... propagate at the next join". The WS `join` action calls it (`:3448`); the WS turn path uses the session already bound in the socket loop and does not restore per message. While a turn is in flight the rebind is skipped (`:1795-1805`), so a change waits until the next join after the turn ends. The routines runner restores per run (`the_one/routines/runner.py:294`). The system prompt is built inside `AgentFactory.create` (`the_one/agent/factory.py:695`), so leg 4's flag reaches the prompt only at those moments.
**Notes**: the drawer reads `info.row` from the agents store, so an agent Save (which invalidates the store) updates the line at once even though the running prompt changes only at the next join.

### charts-in-chat
**Status**: landed (not committed)
**Changes**:
- `markdown.js`: `codeBlockRenderers` option (own keys, guarded, falls back to the well), re-entrant `renderOptions`, `meta.closed`.
- `ui/message.js`: `setTailHold(offset, node|null)` over a logical tail string, one `syncTail()`.
- `ui/chart.js`: `onLayout` option (also through `block`); `data-chart-type` already existed from leg 1 and is now documented.
- New `areas/chat/chart-stream.js` (`App.chat.chartStream`: `scanTail`, the confirming `plan` with the per-generation cache and poison rule, `typeOf`), loaded before `transcript.js`. It is a separate module because `transcript.js` was at 647 lines and the 800-line area rule applies (now about 715).
- `transcript.js`: chart renderer in `mdOpts()`, parser-confirmed `commitSafeBoundary`, `chartHold` lifecycle (commit, finalize, `resetStream`, new bubble), pinned sampling before insert/commit and a `pinnedFlag` for `onLayout`.
- Tests: `test_flow_chat_charts.py` (25, `chats_transcript_pat`), hold contracts in `test_ui_message_contract.py` (6 tests x 2 engines), option/re-entrancy/`closed` in `test_markdown.py` (+ the three pins gain `closed`), `onLayout` in `test_ui_chart_contract.py`. Registry rows for `chat-chart` and `chat-chart-placeholder`.
**Falsification**: cycle-2 fence regression (parse confirmation replaced by `ok = true`: the cycle-2 flow case failed, restored); parse-count bound (poison rule disabled: 30 parses against the bound of 8, restored); hold shift, empty-fragment ordering and finalize-clears-hold (each removed in turn: its contract test failed in both engines, restored). Not falsified: the pinned-scroll pair, the placeholder wording, the history/copy tests.
**Findings**:
- A fast mock stream (5 ms between chunks) never exercises the commit logic: `done` drains the whole pending text at once. The parametrized fence cases stream 5 characters every 100 ms (slower than the 16 ms pacing drains), and the first version of these cases passed even with the confirmation removed.
- Deviation: the placeholder's "Show source" holds the block body after the opener line, not `tail.slice(offset)` with the fence line, to match the error block's source.

### visuals-prompt-and-evals
**Status**: Part A landed; Part B pending (not committed)
**Changes (Part A)**:
- Product: `Capabilities.visuals` (default True), the `visuals` section ("Rich visuals", "agents with Rich visuals on") after `formatting`, kept by `tool_free_capabilities`; `visuals` keyword through `capabilities_from_registry`, `build_system_prompts`, `build_system_prompt`; `AgentFactory.create` passes `config.rich_visuals` to both and sets `agent.rich_visuals`; `pending.py` passes `getattr(agent, "rich_visuals", True)` on the main path and `caps.visuals` on the fallback. No database read.
- **Section size**: 355 characters, **108 tokens** (o200k_base through `evals/tokens.py::TiktokenCounter`, `[evals]` installed). All-on platform text 191 -> 298 tokens. Text: DD12's draft trimmed (dropped the log-scale, right-axis and annotation examples; kept the tag, `type` first, the minimal object, the six types, `title`/axis `label`/`unit`/`stacked`, and "Chart only when it makes numbers clearer").
- Evals: `reply_has_valid_chart(turn=, types=)` with a scanner that mirrors `markdown.js` `parseBlocks` (column-0 opener, first token lowercase `chart`, column-0 closer only, no `~~~`, top-level only, unterminated runs to the end); new `str_list` param kind; `rich_visuals` agent key (`scenario.py`, `harness.py`, omitted when absent); `evals/tokens.py` enumerates `visuals` in (True, False) (16 tool combinations plus tool-free in both states); four scenarios in `evals/visuals/scenarios/` (`--dry-run` loads them: 20 variants each x 3 models); `SCORING_DIGESTS` updated for `checks.py` and `harness.py` with the comment.
- Docs: `evals/README.md` (key, check row, visuals set), CLAUDE.md "Prompt evals", `the_one/agents.md` section list.
- Tests: pins (`tests/_platform_prompt_pins.py` gains `PLATFORM_VISUALS_PIN` and the visuals-off pins; the default pins are the switch-on renders), `test_platform_prompt.py` (visuals changes the text, UI rows gain `visuals` in both lists), `test_prompt_layers.py` (factory on/off for both prompts, the keyword, the timing test), `test_session_lifecycle.py` (join timing), `test_self_configuration_write.py` (pending preview, both states, both paths), `test_evals_checks.py` (20 scanner cases), new `test_evals_visuals.py` (key, harness, set shape, can-fail drive), `test_evals_scenarios.py` (`VISUALS_SCENARIOS`), `test_evals_tokens.py`, `test_evals_freeze.py`, `tests/browser/test_flow_admin_settings_nav.py` (section id, shown once, applies-when line).
**Timing test (AC3, pins the `rich-visuals-switch` finding)**: `test_a_visuals_change_takes_effect_when_the_agent_is_next_built` (a built agent keeps its prompt after the switch is saved; the next `factory.create` reflects it) and `TestRestoreSession::test_rich_visuals_change_takes_effect_at_the_next_join` (an open chat's agent is unchanged; a join while a turn is in flight keeps it; the next join rebinds it).
**Falsification**: section gate `lambda c: True` (7 tests failed: pins, factory, keyword, timing, pending, harness), factory and pending `visuals=` dropped (3 failed), scanner accepting indented fences (the indented-fence case failed) and not swallowing other fences (the json-quoted and plain-quoted cases failed); each restored. Not falsified: the scenario shape tests, token combos.
**Deviations**: the settings-lane pin also asserts the section text once and its "Applies when" line. Nothing run against models (Part B).

---

## Decisions

### Mockups approved at planning (2026-11-08)
**Context**: The flight-design crew rule (squawk 0293) needs an operator-approved mockup for every new user-facing surface.
**Decision**: The operator approved six boards on https://claude.ai/artifact/5qfTVCkB5peb1ekzi8gCTS. On the streaming board they chose option B and asked for a glimmer plus a type-aware shape; the board was revised and approved. The sparkline board was corrected to a compact row, because a fenced block cannot sit mid-sentence.
**Impact**: DD8 and the Mockups section of the flight spec.

### Chart scope: richer (2026-11-08)
**Context**: How far version 1 of the chart format goes.
**Decision**: The operator chose stacking, value tooltips, dual y-axes, log scale and reference lines.
**Impact**: DD2. Flight 3's server renderer must cover the same keys.

---

### Design review cycle 1 (2026-11-08): approve with changes
**Context**: The Architect (Opus) spot-checked 14 citations, and all held. It raised three high-severity issues (a column-0 fence rule would break code blocks nested in lists; a gap between a chart's closing fence and the commit; a prompt flag threaded through capabilities that are never rendered), seven medium and four low.
**Decision**: Folded in:
- DD10 rewritten (over-detect, never under-detect, plus a top-level close boundary).
- DD8: a top-level-only placeholder, an anchored type match, hold invariants and a cut-off notice.
- DD12: one `visuals` keyword through `build_system_prompts`, with no database read.
- DD6: re-entrant `renderOptions`, try/catch and `meta.closed`.
- DD7: contrast measured on the composited bubble, and the table scoped.
- DD4: pixel layout after attach, through a ResizeObserver.
- DD2/DD3: number and drift traps, and a locale-neutral number format.
- DD13: the `s11-routines` compare and a mid-flight commit checkpoint.
- Per-leg gate lanes and the `contracts-chat` re-budget in leg 1.
- DD15: the frozen testids listed.
- DD11 fixes: the hint names charts only, eleven pins, a missing field reads as on, and when a change takes effect.

Leg 3 is split into `rich-visuals-switch` and `visuals-prompt-and-evals`, because only the latter is operator-gated and spends quota. The suggested split of leg 1 was **not** taken: the format, the validators and the control are one library slice, and an implementing agent carries it in one pass.

Operator questions answered by the Flight Director:
- A chart cut off mid-stream gets its own muted notice.
- A chart in a list streams raw and draws at commit; the HAT confirms.
- A switch change takes effect at the agent's next prompt build; leg 3 pins the exact moment.

**Impact**: four implementation legs plus the HAT; a second review cycle follows.

### Design review cycle 2 (2026-11-08): approve with changes, folded in
**Context**: The Architect confirmed the cycle-1 fixes and every citation it re-checked. It found that DD10's closer-indent rule still under-detects: it ran three cases through the real parser, one of them a list-step code block closed at column 0. It also found five low issues.
**Decision**:
- DD10 makes every commit boundary parser-confirmed: a candidate is accepted only when the parsed prefix has no open CODE_BLOCK at any depth. It now lists three kinds of candidate and waits for the opener's newline. The Flight Director accepted the cost of one prefix parse per new candidate; it is technical and reversible, and the operator can override at sign-off.
- "When a change takes effect" is recorded in leg 3 and pinned in leg 4.
- The hold clears on `consumed > offset`, with the order fixed.
- `capabilities_from_registry` gains `visuals`.
- The eval paths are `evals/*/scenarios`.
- The placeholder is also destroyed on `clearLog` and a session switch.
- `meta.closed` is documented as conservative.

**Impact**: Two review cycles are used up (the maximum); no further review. Ready for operator approval.

## Deviations

---

## Anomalies

---

## Session Notes

### Flight Director Notes
- 2026-11-08: Execution started with `/mission-control:agentic-workflow`. Phase file `.flightops/agent-crews/leg-execution.md` loaded and valid. Branch `flight/01-charts-in-chat` created from `main` at `293a81d2`; flight status set to `in-flight`.
- **Batch plan** (the crew file's batch mode, the operator's standing preference for UI flights, combined with DD13's commit before quota):
  - **Batch A**: legs 1-3, then a code review (Reviewer plus the Accessibility Reviewer, since this is a UI flight) and a checkpoint commit.
  - **Batch B**: leg 4's product code, a review and a commit, then the eval runs and the operator's size decision, then a final commit.
  - The HAT (leg 5) closes the flight.
- **Leg 1 risk tier: HIGH.** It refactors a shared library control with existing consumers (`App.ui.thinking.dots`, pinned by `test_ui_thinking_contract.py`). It adds design tokens under contrast gates. It sets the format contract that Flight 3 and the corpus depend on, and it changes a lane budget. So it gets a per-leg Developer design review.
- Leg 1 design review (Developer, Sonnet): **approve with changes**, two medium traps and guard mechanics, all folded in:
  - The dots' stop rule keys off the dots node, and `settle` destroys the dots before clearing.
  - The contrast composite uses `_alpha_composite` with the rgba parsed from `tokens.css`.
  - One `App.ui.chart` factory, with its sub-entries in the row text; SVG classes go through a `cls` variable.
  - The lane is re-budgeted, with CLAUDE.md updated.
  - The placeholder split is now decided, not optional.
  - Nine extra corpus cases; the document is the single sentence source (AC3b); a palette appendix for Flight 3 (AC4b); the axis zero rule; a work order.

  No second cycle, since the changes were additive. Leg 1 marked `ready` and `[HANDOFF:review-needed]` passed for implementation.
- Leg 1 `[LAND:leg]` received (legs completed: 1 of 4 autonomous). The Flight Director accepted the Developer's deviations:
  - **`block` with `closed === false`:** a valid spec still draws, and the cut-off notice appears only for an invalid or truncated spec. This is better for a stream that ended without its closing fence. Leg 2's AC8.4 is adjusted to match.
  - **Format rules decided in the document:** the values limit is checked first, `x.scale: log` is refused off scatter, and keys that don't apply to a type are dropped.
  - **The `contracts-chat` budget** is 120 s from solo readings on a loaded host. The closing gate re-measures it on a quiet host.

  Follow-ups for the Batch A review:
  - axis text width is estimated, not measured;
  - light mode and WebKit have not been looked at visually;
  - `docs/ui-testid-registry.md` has not been checked for the derived testids.
- **Leg 2 risk tier: HIGH.** It changes two shared interfaces with existing consumers (`App.markdown.render`/`parse`, the `App.ui.message` streaming handle) and the streaming commit state machine, which every chat reply goes through. Developer design review follows.
- Leg 2 design review cycle 1 (Developer, Sonnet): **approve with changes**, all folded in. The two high issues:
  - the three `test_markdown.py` `meta` pins gain `closed`;
  - the kind-2 candidate needs a newline-terminated closer.

  The mediums:
  - parse confirmation is the authority over the scanner, and a placeholder is raised only after its opener candidate is accepted;
  - a per-generation cache of rejected offsets, a three-candidate cap and a perf test on `parse` calls;
  - explicit destroy points (`resetStream` destroys itself; one destroy in finalize covers every caller);
  - a normalized DOM comparison for the fence cases;
  - the hold shift only after commit's early return;
  - `onLayout` reusing the chart's observer;
  - lang token parity (`chart extra`, `Chart`).

  These are substantive, so a second design-review cycle runs.
- **Leg 3 risk tier: HIGH** (schema migration v52 plus an API write-shape change). Its design review is running in parallel with leg 2's second cycle; implementation stays sequential.
- Leg 3 design review (Developer, Sonnet): **approve with changes**, all folded in:
  - AC4's non-boolean case corrected. Validation stays lax, matching `notes_enabled` (a Flight Director decision); the tests use `"abc"` and `null`.
  - The `collectFormData` branch is mandatory and goes before `else`.
  - Toggle wiring: the testid and `data-field` sit on the input, and dirty tracking goes through `own(tg.control)`.
  - A repository omit-preserve test, the migration test style, and the timing hypothesis.

  No second cycle (clarifications, not design changes). Leg 3 `ready`.
- Leg 3 implementation started before leg 2's, because the two are independent and leg 2 was still in its second design review. Implementation stays one Developer at a time.
- Leg 2 design review cycle 2 (final, Developer, Sonnet): **approve with changes**. Every cycle-1 issue is resolved. Folded in:
  - The scroll-pinning trap: sample the pinned state before the swap, and a pinned flag for `onLayout`.
  - `onLayout` for sparklines, and the closer regex made exact.
  - The cache maps offset to verdict, including accepted-but-empty candidates, with a poisoned-prefix shortcut and perf tests for the costly case.
  - Kind-3 split regression cases (after a list, a blockquote and a table).
  - An idempotent `setTailHold`; a defensive stale-hold cleanup.
  - `data-chart-type` catalogued.

  The Flight Director accepted the known limit that a stray unclosed nested fence holds the rest of a reply until finalize; it is documented in `agents.md`. Two cycles are used up, so leg 2 is `ready`.
- **Batch plan revised (leg 4 design):** a single review and commit covers legs 1-3 plus leg 4's Part A (the product code, pins, eval check and scenarios, all offline). DD13's "commit before quota" checkpoint and the batch-end checkpoint are therefore the same commit. Leg 4 Part B (the eval runs) follows in a new Developer spawn, then the operator's size decision, the baselines and their commit, then the HAT. This replaces the earlier plan of separate Batch A and B reviews: one review pass over the product code is cheaper and catches the same things.
- **Leg 4 risk tier: HIGH.** It changes shared interfaces with existing consumers (`build_system_prompts`, `capabilities_from_registry` and `Capabilities` are used across the factory, `pending.py` and evals) and the eval scoring methodology (`SCORING_DIGESTS`), and it spends quota. Developer design review follows.
- Leg 4 design review (Developer, Sonnet): **approve with changes**, all folded in.
  - The two high issues: `scenario.py` is not a `SCORING_DIGESTS` file; the tool-free UI pin list also gains `visuals`.
  - Why plain `compare` runs, and that `--same-prompt` is only for re-baselines.
  - `--dry-run` instead of a non-existent `--list`; `VISUALS_SCENARIOS` tests; `chart-fits-data` split into two files (checks are per scenario).
  - The check's scanner mirrors `markdown.js` exactly, top-level only.
  - An explicit Part A to Part B handoff; the `test_evals_tokens.py` pins; a destination for the token count.
  - The Flight Director's answers: a chart quoted inside an outer fence does not count; if sortie 12 lands first, its baseline is the comparison target, confirmed by the Flight Director before the n=20 runs.

  No second cycle (corrections and specificity, not design changes). Leg 4 `ready`.
- Leg 3 `[LAND:leg]` received (2 of 4 autonomous legs). Timing finding: a change takes effect at the conversation's next join, a new chat or the next routine run, not mid-chat. Leg 4 pins it.
  - Gap noted: the whole unit tier was not re-run after the two guard fixes (the file-size rule and the testid registry); only the guard files were. The flight review gate covers it.
- Leg 2 implementation spawned (Developer, Sonnet).
- Leg 2 `[LAND:leg]` received (3 of 4 autonomous legs). The unit tier passed at 9596, with 15 skipped. The `chats-transcript`, `chats` and `contracts-chat` lanes pass.
  - Accepted deviations: the scanner lives in a new `areas/chat/chart-stream.js` because of the area-size rule; "Show source" shows the block body.
  - Open: `contracts-chat` measured 160 s solo on a loaded host against 120 s. It is re-measured at the quiet closing gate (squawk 0259).
- Leg 4 Part A implementation spawned (Developer, Sonnet).
- Leg 4 Part A `[LAND:leg]` received (4 of 4 autonomous legs' offline work). The section is 108 tokens (o200k_base), and the all-on platform text grows from 191 to 298. The unit tier passes at 9642, with 15 skipped.
- **Flight review (Phase 2d)** over legs 1-3 and leg 4 Part A, uncommitted.
  - **Reviewer tier: Sonnet** (the crew rule's security-sensitive tier). The flight renders model-controlled text into the app's own page (the markdown renderer option and SVG built from model JSON), which is an injection surface beside the credential-holding page.
  - **Accessibility Reviewer (Sonnet)** spawned in parallel, because this is a UI flight.
  - **Review fixes (Developer):** (1) `App.ui.chart` gained one visually hidden polite live node per chart (`ui-chart-live`, `<testid>-live`, `aria-atomic`), written only on keyboard moves (arrows, Home, End) as "{x label}: {series} {value}, ..." from the tooltip's own strings and cleared on Escape and blur; the tooltip stays `aria-hidden`; catalogue row and testid registry updated; new both-engine contract test (falsified: yes). (2) The streaming placeholder lost its `role="status"` (the chat log announces it); its contract test now asserts no live region (falsified: no, a negation of the removed attribute).
- Flight review results: the Reviewer (Sonnet, security tier) returned `[HANDOFF:confirmed]` with no issues. It found no HTML sinks, only safe SVG elements and model text through `textContent` only; the Python validator was fuzzed with adversarial inputs and never raised. The Accessibility Reviewer returned `[HANDOFF:confirmed]` with two non-blocking items, both fixed (above). There is no re-review: the fixes are small, tested and falsified, and both reviewers had already confirmed. After the fixes, the unit tier passes at 9642 with 15 skipped; `contracts-chat` has 356 passed and `chats-transcript` 122 passed.
- **Checkpoint commit** (batch end and DD13's commit before quota): legs 1-3 `completed`; leg 4 stays `landed (Part A)` until Part B. Committed by a Developer spawn.
