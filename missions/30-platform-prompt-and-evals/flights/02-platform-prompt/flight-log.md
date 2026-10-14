# Flight Log: The platform prompt

**Flight**: [The platform prompt](flight.md)

## Summary
Planning, 2026-10-14. Fully agentic execution; the data are the gates.

---

## Leg Progress

### Leg `evals-readiness` (flight leg 1a) — landed

Evals only; `git diff --stat -- the_one/ evals/scenarios evals/fixtures evals/judge evals/measure` is empty.

**Changes**
- `evals/tokens.py`: structural `extract_parts` (DD10). It splits on the layer separator (a test pins it against `compose_system_prompt`), assigns layers by the known order, finds a persona by its own text first (so a persona holding the separator is safe), and treats a notes layer with no notes as platform text. The platform text is one `platform` part, with a `platform_sections` hook (`text -> [(id, text)]`) for leg 1b. Surplus layers become `unattributed`. `RawConfig.notes_present` added. DD13: `bare-connector` and `all-on-connector` (attempts 90 and 91) are built with `connector_row()`, which inserts a `stub` connector whose `default_agent` is the variant's agent name and deletes it afterwards. They are in `ALL_CONFIGS`, the prompt fingerprint, the tables, and `_script_for` (all-on plus connector gets the `search_tools` script).
- `evals/baseline.py`: `derive_bars(doc, size_ratio)`; `extra_size_gates()` (DD13: bare platform <= baseline bare minus connector parts, bare plus connector, all-on, all-on plus connector, maxima read from the baseline's `sizes`, plain sizes standing in when the baseline has no connector variants); the vacuous count in `compare`'s detail (DD14).
- `evals/report.py`: `load_runs` refuses a directory with no `measure.json` unless `--measure` (DD5.1). `evals/__main__.py`: `derive-bars --size-ratio`, `selftest`, `compare` warns on stderr when `--measure` is given and no longer measures on the fly.
- Tests: new `tests/test_evals_freeze.py`; gates, ratio and vacuous count in `test_evals_baseline.py`; refusal, warning, ratio and mixed-fingerprint tests in `test_evals_cli.py`; structural extraction and connector-variant tests in `test_evals_tokens.py`; `test_evals_scenarios.py` runs 5 variants in the unit tier (20 under `EVALS_SELFTEST_FULL=1`); `_evals_helpers.synth_measure` carries connector parts and variants and `make_run_dir` writes a measure by default (`measure=False` to omit).
- `evals/README.md` documents the new subcommand, flag, gates and refusal.

**Deviation recorded:** operator texts are subtracted from the layer that holds them (rules from the rules layer, notes from the notes layer), not from every layer. Subtracting a rule text from every layer removed a one-letter rule's "r" from the notes layer's "Rules take precedence..." sentence (the existing invariance test caught it).

**First one-time verification (DD10), product untouched, tiktoken `o200k_base`** (`make eval ARGS="measure-prompt"`):

| config | prompt sections | tool schemas | platform text |
|---|---|---|---|
| bare | 595 | 713 | 1308 |
| all-on | 862 | 927 | 1789 |
| tool-free | 84 | 0 | 84 |
| bare-connector | 595 | 713 | 1308 |
| all-on-connector | 862 | 927 | 1789 |

Matches `m30-today` exactly (595 / 862 / 84 and 1308 / 1789 / 84). Parts: platform 554 + date_line 41 (bare); connector tool schemas 251 + 210 = 461. New prompt fingerprint (five configurations): `259f0a1e0619d294a20b680c5d835f008fcabbef3c8a25506063b89a6ed767de`.

**Freeze digests (SHA-256, recorded at this leg's end; pinned in `tests/test_evals_freeze.py`)**
- scenarios fingerprint equals `m30-today`'s `66e917bb5c62d730ba058df7fee95f835d35038855ef14107a15c1b302717894`
- `checks.py` d04ffdc0a5fdc50da5aef39d7c017092ee420d2f3b13ab23fa52ace0836150d1
- `outcomes.py` 237504b33206c31673cbfc30b20c7ee8c99ddcfe8962ba45e96475a9d1b90ffd
- `judge.py` 2d341a249779c75a3e2e6ffd880953312b04841b82471909e3c3fae880543916
- `harness.py` 1f6a6bacf1e0f85c4a0658729511352ea17b04233af181cf94fd888a41a91c28
- `evals/measure/`: all-on.toml b5a2276d..., bare.toml 59979915..., tool-free.toml 987bc2b1..., fixtures/kb/measure-kb/readme.md b5fea4c9... (full digests in the test)
- `harness.py` was NOT changed (the connector row is inserted from `tokens.py`, DD12).

**Unit-tier cost (DD15):** `tests/test_evals_*.py` wall time 66.0 s (267 tests) before, 67.7 s (289 tests) after. The width cut saved only about 2 s on the scenarios file (23.0 s to 20.7 s): a scripted run is about 25 ms, and each test's fixed setup (about 0.6 s) dominates, so the flight's "about 45 s" estimate did not hold. `make eval ARGS=selftest` (34 tests, width 20) takes about 23 s. Recorded, not chased: a real saving needs a cheaper per-test setup, which is outside this leg's allowed changes.

**Gates:** `make test-unit` 6579 passed, 12 skipped; `make lint` and `ruff format --check the_one/ tests/ scripts/ evals/` clean.

**Deferred:** DD10's `selftest` size check against the current baseline (applies only while the prompt fingerprint equals the baseline's, so it can never run against `m30-today`); no `m30-platform` exists yet. Leg 1b adds it with the platform section ids.

### Leg `platform-prompt-structure` (flight leg 1b) — landed

No wording change and no condition switched on. `/api/info` and Settings › Prompts unchanged in shape.

**Changes**
- New `the_one/agent/platform_prompt.py`: `Capabilities` (frozen; `all_on()`), `Section` (`id`, `title`, `applies_when`, `applies`, `text`), `SECTIONS` (identity, identity_tool_free, tool_discovery, tool_use, execution, tool_use_tail, closing; the execution bullet sits between the two halves of "Tool use:"; each text carries its own leading whitespace, the renderer inserts nothing; `closing` carries the final newline), `sections_for`, `render_platform`, `render_tool_free`, `capabilities_from_registry` (None or a broken registry gives no tool capabilities). Only `caps.tools` selects text in this leg; `knowledge`/`exec_tools` etc. are carried for leg 1c (KB phrases stay inside `tool_discovery` verbatim).
- `config.py`: `BASE_PROMPT` and `CHAT_ONLY_PROMPT` removed. `prompt_layers.py`: `SystemPrompts`, `build_system_prompts` (new kwargs `knowledge`, `time_tool`, `exec_tools`); `build_system_prompt` is the thin `str` wrapper.
- `core.py`: `Agent(degraded_system_prompt=None)`; `_build_degraded_messages` returns it, else `system_prompt` verbatim; no `startswith` left. `factory.py` builds both prompts via `capabilities_from_registry` + `build_system_prompts`. `pending.py` (main path and fallback) sets `system_prompt`, `messages[0]` and `degraded_system_prompt`. `app.py` `/api/info` `base_prompt` is `render_platform(Capabilities.all_on())`.
- `evals/tokens.py`: `platform_prompt_sections` wired as `measure_configs`' splitter (`extract_parts` itself still defaults to one `platform` part). **Finding:** token counts are not additive across section boundaries (per-section counts summed to 600/867/85, not 595/862/84). Sections that tile the platform text are therefore counted cumulatively (each part = growth in the count of the text so far), so the parts sum exactly to the whole. `evals/README.md` and `the_one/agents.md` updated; `evals/measure/tool-free.toml` (frozen) still mentions `CHAT_ONLY_PROMPT` as history.
- No frozen file touched (`git diff --stat` on checks/outcomes/judge/harness/scenarios/fixtures/judge/measure is empty; the freeze test passes).

**Byte-identical tests** (`tests/test_platform_prompt.py`, literals in `tests/_old_prompts.py` copied exactly before the constants were removed): `test_tool_capable_render_is_byte_identical`, `test_tool_free_render_is_byte_identical`, `test_composed_prompt_matches_old_composition` (composed and degraded), plus `test_no_condition_changes_text_yet`, `test_tool_free_ignores_other_capabilities`, section/`capabilities_from_registry` tests. In `test_evals_tokens.py`: `test_platform_prompt_sections_split_matches_the_whole_count`, `test_sections_that_tile_the_platform_text_are_counted_cumulatively`. New in other files: `test_factory_passes_the_tool_free_prompt_to_agent`, `test_build_system_prompts_returns_both_variants` (`test_prompt_layers.py`); `test_settle_sets_the_degraded_prompt_with_the_revised_persona`, `test_fallback_also_sets_the_degraded_prompt` (`test_self_configuration_write.py`); `test_without_a_degraded_prompt_the_system_prompt_is_sent_verbatim` (`test_agent_degraded_injection.py`).

**Migrated tests** (constants replaced by the exact literals from `tests/_old_prompts.py`): test_config, test_prompt_layers, test_agent_degraded_injection (rewritten to `degraded_system_prompt`), test_self_configuration_write, test_connectors_inbound, test_governor, test_agent_redundant_backstop, test_factory, test_agent_search_integration, test_evals_tokens, test_evals_harness.

**Second one-time verification** (`make eval ARGS="measure-prompt"`, tiktoken `o200k_base`; fingerprint unchanged `259f0a1e0619d294a20b680c5d835f008fcabbef3c8a25506063b89a6ed767de`):

| config | prompt sections | tool schemas | platform text |
|---|---|---|---|
| bare | 595 | 713 | 1308 |
| all-on | 862 | 927 | 1789 |
| tool-free | 84 | 0 | 84 |
| bare-connector | 595 | 713 | 1308 |
| all-on-connector | 862 | 927 | 1789 |

Parts (bare / all-on): identity 22, tool_discovery 274, tool_use 61, execution 35, tool_use_tail 121, closing 41, date_line 41 (all-on adds rules_layer 39, notes_layer 228). Tool-free: identity_tool_free 16, closing 41, date_line 27. Matches `m30-today` and leg 1a exactly.

**Gates:** `make test-unit` 6594 passed, 12 skipped; `ruff check` and `ruff format --check` clean on the_one/ tests/ scripts/ evals/. `grep BASE_PROMPT|CHAT_ONLY_PROMPT` hits only the frozen toml comment and two history mentions (platform_prompt.py docstring, agents.md).

**Deferred:** none. (`m30-platform` baseline and the conditions remain leg 1c/later.)

### Leg `conditions-and-ui` (flight leg 1c) — landed

Conditions switched on, tool-free notes heading, connector seeding, Settings › Prompts by section. Frozen files untouched (freeze test passes; `git diff --stat` on `evals/scenarios|fixtures|judge|measure` and `checks|outcomes|judge|harness.py` is empty).

**Changes**
- `platform_prompt.py`: the three KB phrases in `tool_discovery` are conditional through named constants (`KB_CATALOG`/`NO_KB_CATALOG`, `KB_GROUPS`/`NO_KB_GROUPS`, `KB_EXAMPLES`/`NO_KB_EXAMPLES`, each both forms pinned verbatim); `execution` applies on `tools and exec_tools`; `Fragment`/`FRAGMENTS` (the `knowledge` row, ignored by `sections_for`, so sections still tile); `platform_sections_for_ui()`.
- `_notes.py`: `NOTES_HEADING_TOOL_FREE`, `render_notes_block(..., tools=True)`; `config.py`: `compose_system_prompt(..., tools=True)`. `prompt_layers.build_system_prompts` passes `tools=False` and a `tool_available=False` date line for the tool-free prompt; `pending.py` fallback passes `tools=False`.
- `repositories.py`: `connector_bindings(conn)`, `agent_names_in_use(conn)`; `ConnectorDirectoryRepository.search` uses them (malformed row now skipped and logged; `(ValueError, TypeError, AttributeError)` around the whole row). `factory.py`: the connector pair is seeded only for an agent a connector names; fetched once per `create()`; fails open (seeds the pair) if the read raises (this keeps the AsyncMock-connection factory tests unchanged).
- `/api/info`: `platform_sections` replaces `base_prompt`; `notes_prompt_example_tool_free` added. `system-page.js`/`admin.css`: blocks `platform-section-{variant}-{id}` (+ `-applies-when`, `-text`) under "With tools" / "Without tools" captions; `platform-sections` mount; `notes-prompt-content-tool-free`. `base-prompt-content` retired (registry, `RETIRED_SELECTORS`); `platform-section-` in the parametric table.
- `evals/tokens.py::platform_prompt_sections`: matches the text against every capability combination (tools off; tools on x knowledge x exec_tools), falls back to one `platform` part with a warning.
- Docs: `agents.md`, CLAUDE.md Prompts paragraph, SECURITY-MODEL.md (`/api/info` key name), `tests/behavior/list-and-detail.md`.

**Wording changes (logged)**
1. KB phrases removed when no KB tool: "...web fetch, etc.), tools from any MCP servers attached to this agent, AND search tools for any knowledge bases attached to this agent — they all surface" becomes "...web fetch, etc.) and tools from any MCP servers attached to this agent — they all surface"; "`built-in: …` for built-in tools, `mcp:<server>: …` for MCP server tools, `kb:<name>: …` for knowledge-base search tools." becomes "`built-in: …` for built-in tools and `mcp:<server>: …` for MCP server tools."; the example list drops "internal docs".
2. The execution (box / `host_access`) bullet is dropped unless `shell` or `python_exec` is registered.
3. `NOTES_HEADING_TOOL_FREE`: the reference-and-trust part of `NOTES_HEADING` only, "You saved these in earlier conversations" changed to "These were saved in earlier conversations".
4. The tool-free date line uses the existing without-tool wording (no new text).

**Tests**: `test_platform_prompt.py` (conditions matrix, verbatim no-KB forms, tool-free never names a tool with everything on, fragment/UI rows), `test_prompt_layers.py` (tool-free notes heading and empty state, tool-free date line, heading pinned, `parse_notes_block`, `connector_bindings` and malformed rows, seeding for default_agent / channel_map / unmapped / deleted agent, fail-open, `/api/info` shape), `test_evals_tokens.py` (every combination's parts sum to the total, fallback warning, tool-free notes needs no extra matching). Existing tests that expected the all-on text from a factory/stub agent now expect the real capabilities' render.

**Post-switch `make eval ARGS="measure-prompt"`** (tiktoken `o200k_base`; prompt fingerprint `51110b0f4293a0ccf582cd5feb1f97711f047a15c784680402679bdc644d62c7`):

| config | prompt sections | tool schemas | platform text |
|---|---|---|---|
| bare | 532 | 252 | 784 |
| all-on | 827 | 466 | 1293 |
| tool-free | 84 | 0 | 84 |
| bare-connector | 532 | 713 | 1245 |
| all-on-connector | 827 | 927 | 1754 |

Parts: bare: identity 22, tool_discovery 246, tool_use 61, tool_use_tail 121, closing 41, date_line 41 (tools: search_tools 106, continue 74, current_time 72). all-on: identity 22, tool_discovery 274, tool_use 61, tool_use_tail 121, closing 41, rules_layer 39, notes_layer 228, date_line 41 (tools: + save_note 101, update_note 68, forget_note 45). tool-free: identity_tool_free 16, closing 41, date_line 27. bare-connector: as bare, plus send_to_platform_channel 251 and find_platform_destination 210. all-on-connector: as all-on, plus the same two. KB search tool 116. The measured agents carry no `shell`/`python_exec`, so `execution` does not appear in any configuration (bare/all-on agents have no execution tools). Targets: bare prompt sections 595 -> 532 (below 595); bare platform 1308 -> 784 (down 524, at least the 461 connector tokens); bare-connector platform 1245 (connector pair re-added: 784 + 461).

**Gates**: `make test-unit`-equivalent (`pytest -m 'not browser and not live and not pixel'`): 6654 passed, 15 skipped (12 expected plus the 3 timing-conditional watcher skips on a loaded host; `test_kb_watcher`/`test_doctor`/`test_time_zones`/`test_pty_dispatch` re-run alone: 167 passed, 2 skipped). Settings lane (`THE_ONE_TEST_NETNS=1 ... --lane settings -x`): 115 passed. `test_ui_guards`, `test_token_definitions`, `test_design_tokens_a11y`, `test_nav_helper`, `test_evals_freeze`: 367 passed. ruff check and format clean on the_one/ tests/ scripts/ evals/.

**Deferred**: none. (No new baseline is cut; `m30-platform` remains for a later leg.)

---

## Decisions

---

## Flight Director Notes
- **Branch:** `flight/02-platform-prompt`, created from `flight/01-prompt-evals-baseline` (stacked).
- **Debrief carried forward:** the Flight 1 debrief's recommendations 1–5 became DD10, DD12, DD13, DD14 and DD15. DD13 adds size checks stricter than Flight 1's DD11. They tighten the gates and loosen none, so they don't refit Flight 1's data-derived bars.
- **Design review cycle 1:** approve with changes, all applied. The no-golden-files concern was resolved by design: no captured prompt fixtures; a one-time verification at the byte-identical step instead. Leg 1 is split into 1a (evals only) and 1b (product).
- **Design review cycle 2:** approve with changes, all applied: `compare` never uses `--measure` and refuses a run directory without `measure.json`; `m30-platform`'s size targets use ratio 1.0; no connector-row leakage; stale technical approach and checkpoints rewritten; the DD3/DD4 contradictions fixed. The 2-cycle cap is reached and nothing is left open. Flight `ready`.
- **Leg 1a `evals-readiness`: low risk.** It is confined to `evals/`, offline, product untouched, and every change is unit-tested. No design review.
- **Leg 1a landed:** `[LAND:leg]` received. tiktoken reproduces `m30-today`'s sizes exactly, and the freeze test is in place. **DD15 under-delivered:** the eval tests went from 66.0 s to 67.7 s with more tests. The cost is fixed per-test setup (about 0.6 s), not variant width. That is accepted for this flight and recorded for the mission debrief.
- **Leg 1 split into 1b and 1c (design review).** The original `platform-prompt-structure` leg was too large, and its byte-identical step was infeasible as written: the box bullet sits mid-block, the KB phrases sit mid-bullet, and both constants end in a trailing newline. Leg 1b (structure, byte-identical, plumbing) is **high risk** (a shared interface change across the factory, core, `pending` and the evals), and its design review is complete with all findings applied. Leg 1c (`conditions-and-ui`) is **high risk** too (UI, connector repository behaviour change); it gets its own review after 1b lands. Leg count is now 5.
- **Leg 1b landed:** `[LAND:leg]` received. Both variants are byte-identical, the second tiktoken verification is exact (595/862/84; 1308/1789/84), and the fingerprint is unchanged. Finding: token counts are not additive across section boundaries; they are now counted cumulatively, which is test-pinned. Leg 1c design review spawned.
- **Leg 1c design review:** approve with changes. The amendments are appended to the leg as binding: a tool-free date line, the `pending` fallback, a capability-aware section splitter, KB phrases as fragments, the parametric testid family and the browser test details. Decisions taken: the tool-free variant uses the without-tool date wording; the knowledge row appears under 'With tools' only; the tool-free notes heading says 'These were saved…' (logged as a wording change). Leg `ready`.
- **Leg 1c landed:** `[LAND:leg]` received. Post-switch sizes: bare 532 / 784 (sections / platform), all-on 827 / 1293, bare plus connector 1245, all-on plus connector 1754, tool-free 84. I accepted the factory's fail-open when the bindings read raises: it seeds the pair as before, so a failure costs tokens, not function.
- **Deviation: review checkpoint before tuning.** The protocol puts one review at flight end. I'm running the Reviewer on legs 1a–1c **before** leg 2, because every live screen and the final `compare` depend on this code being correct; a defect found after 6+ hours of live runs would invalidate them. Leg 2's per-candidate commits (DD5.1) need a reviewed base. Reviewer tier: **Sonnet** (prompt assembly, the self-configuration `pending` path, connector repository behaviour). The flight-end review still covers leg 2 and leg 3.
- **Pre-tuning review: `[HANDOFF:confirmed]`** (Sonnet). Unit tests: 6613 passed, 12 skipped. Settings lane: 115 passed. Static guards: 285 passed. Freeze diff against `085c15d`: empty. Non-blocking notes are recorded for the flight-end review: a hand-built `Agent` without `degraded_system_prompt` sends its tool-capable prompt to a tools-off model (production paths always set both); `Capabilities.notes` has no text consumer yet. Legs 1a–1c are committed as the reviewed checkpoint and marked `completed`.
