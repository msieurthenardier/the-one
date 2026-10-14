# Flight: The platform prompt

**Status**: completed
**Mission**: [Agents know how to use the platform, measured across models](../../mission.md)

## Contributing to Criteria
- [x] An agent's system prompt carries guidance only for what it has: none about knowledge bases without one attached, none about notes with notes off, none about rules without rules, and none about tools when the model cannot use them. An agent with everything on still gets one consistent prompt, and its own prompt is appended unchanged.
- [x] The platform's prompt text is as short as it can be while meeting the bars: the bare-agent and all-on size targets, with every added word earning a measured gain.
- [x] Settings › Prompts shows each part of the platform prompt and when it applies.
- [x] Agents reply with clickable markdown links rather than bare URLs in chat, and links stay usable through the Discord connector. Backed by the evals, plus a live check through Discord.
- [ ] On both models, the new prompt text is no worse than the baseline on any scenario under the pre-declared rule, and meets each per-scenario bar derived from the baseline. "Never saves a secret" and "flags a note saved after planted content" pass on every run.
  - *Partially met: every hard gate passes, and every safety cell passes on every run. One best-effort bar is unmet: gpt-oss `planted-instruction` 3/20 against a bar of 0.30, while the untrusted flag caught every planted note. gpt-oss `rule-beats-note` passed the no-worse rule only narrowly (8/20 against 14/20, p = 0.056).*
- [x] Existing behaviour holds: notes, rules, the date line, self-configuration and the tool-free path keep working, their behavior specs pass, and the unit and browser suites pass.
- [x] (completes) The convention is recorded: a change to platform prompt text carries an eval run against the baseline, including its token cost, and evals stay out of CI and the test gate.

---

## Pre-Flight

### Objective
Replace today's fixed `BASE_PROMPT` with a platform prompt built from sections, each applying only when the agent has that capability. Write each section, the rules and notes layers, the tool-free prompt, and the notes and knowledge-base tool descriptions as tersely as the evals allow, and teach link formatting (#282). Show each section and its condition on Settings › Prompts.

Every wording choice is made by eval data. The final text must pass every hard gate of the Flight 1 baseline (`evals/baselines/m30-today.json`) on Haiku 4.5 and `gpt-oss:20b`. Best-effort cells are reported as measured.

Today's baseline, the starting point:
- **Hard fail:** bare prompt sections are 595 tokens; the target is ≤ 357.
- **Best-effort misses:** `markdown-links` at 2/20 on both models; `notes-proactive` and `planted-instruction` at 0/20 on gpt-oss.
- **Room to improve:** `rule-beats-note` is 8/20 on Haiku and 14/20 on gpt-oss, a `hold` cell.

### Open Questions
- [x] How does the tool-free path find the platform part once the base varies? → DD2
- [x] Do conditional sections hurt prompt caching? → No. There is no `cache_control` anywhere, the date line already changes the prompt daily, and each agent's prefix is stable across its own turns. Closed by evidence.
- [x] Does Discord render `[text](url)` from a bot? → Undocumented. The live check (DD9) observes the delivered content directly. The criterion is "links stay usable", which is met either way as long as the URL arrives intact.
- [x] Connector tools are seeded for every agent → DD7
- [x] Do self-configuration and `current_time` need sections? → No. `current_time` is covered by the date line, and self-configuration's tools carry their own descriptions (DD3).
- [x] The closing "persona may be appended" sentence → kept only if the evals show it earns its tokens (DD5)
- [x] How to avoid tuning on the test set → DD5 (tune on fact 0 only; gate once on all 20; log every compare)
- [x] Are the evals' measurement and scoring inputs frozen? → DD12

### Design Decisions

**DD1: The platform prompt is a list of sections, each with a condition.**
- A new module, `the_one/agent/platform_prompt.py`, defines:
  - `Capabilities(tools, knowledge, notes, rules, time_tool, exec_tools)`, all bools
  - an ordered tuple `SECTIONS` of `Section(id, title, applies_when, applies, text)`. `applies` is a predicate on `Capabilities`; `applies_when` is the plain-language condition shown in the UI.
  - `render_platform(caps) -> str`
- **Tool guidance never reaches a tool-free prompt.** Every section that mentions tools has a predicate that requires `tools`. For example, `knowledge` applies when `tools and knowledge`.
- **The tool-free variant** is `render_platform(replace(caps, tools=False, time_tool=False))`.
- **The identity line has two variants.** Today they differ: "You are an AI agent with access to a set of tools…" versus "You are an AI assistant…". So the `core` section has a tools-dependent variant.
- **`BASE_PROMPT` and `CHAT_ONLY_PROMPT` are removed.** Their consumers move to the new module:
  - `core.py`, `self_configuration/pending.py`, `interfaces/web/app.py` `/api/info`, `evals/tokens.py`
  - the tests: `test_config.py`, `test_prompt_layers.py`, `test_agent_degraded_injection.py`, `test_self_configuration_write.py`, `test_connectors_inbound.py`, `test_governor.py`, `test_agent_redundant_backstop.py`, `test_factory.py`, `test_agent_search_integration.py`, `test_evals_tokens.py` and `test_evals_harness.py`
- **Step 1 is byte-identical** (leg 1b). Today's text is split into sections with every condition true. The rendered tool-capable all-on text must equal today's `BASE_PROMPT`, and the tool-free text must equal today's `CHAT_ONLY_PROMPT`, both pinned by a test.
- **Step 2 switches the conditions on.** Today's KB mentions sit inside the "Tool discovery" bullets, so splitting them out is itself a wording change. The flight log records it as such.
- **The box / `host_access` rule** cannot be measured, because eval agents have their execution tools disabled. So it applies only when `exec_tools` (`shell` or `python_exec` is registered), and DD5 never trims its text.
- **Rationale:** one source for assembly, the degraded path, the pending fallback, `/api/info`, the evals' part extraction and Settings › Prompts.

**DD2: Both system prompts are built at build time; nothing is recovered by prefix.**
- **The new signature:**
  ```python
  build_system_prompt(agent_name, persona, *, conn=None, knowledge: bool, time_tool: bool, exec_tools: bool, now=None) -> SystemPrompts
  ```
  - `SystemPrompts` is a named pair, `(tool_capable: str, tool_free: str)`.
  - `notes` and `rules` stay read inside it: notes is `list_if_enabled(...) is not None`, rules is at least one enabled rule. That way the factory and `pending` share one source.
- **The factory** passes both prompts to `Agent`, which gains `degraded_system_prompt`.
- **`Agent._build_degraded_messages`** uses that attribute instead of `startswith(BASE_PROMPT)`. If the attribute is absent, it falls back to `system_prompt` verbatim, as today's non-prefix branch does.
- **`pending.apply_pending_revision`:**
  - Its main path derives `knowledge` and `exec_tools` from the live agent's registry, and `time_tool` from `time_tool_available` as today.
  - Its error fallback composes both prompts from the same registry-derived capabilities.
- **The per-turn choice** on `supports_tools()` is unchanged.
- **The tool-free prompt is never persisted.** Web restore and connector inbound rebuild through the factory and keep the fresh `messages[0]`, so this is unchanged.
- **The rules and notes layers take `Capabilities`.** The tool-free notes layer never tells the model to call `update_note` or `forget_note`.

**DD3: Where each capability comes from**, at factory build time.

| capability | source |
|---|---|
| `tools` | true for the tool-capable variant, false for the tool-free variant |
| `knowledge` | at least one `kb__` tool registered after filtering |
| `notes` | `AgentNoteRepository.list_if_enabled(...) is not None`, read inside `build_system_prompt` (DD2) |
| `rules` | at least one enabled rule (read inside `build_system_prompt`, as today) |
| `time_tool` | `time_tool_available(registry, llm)` (unchanged, fails closed); forced false in the tool-free variant |
| `exec_tools` | `shell` or `python_exec` registered after filtering |

Self-configuration needs no section; its MCP tools describe themselves.

**DD4: The starting section set.** Leg 2 writes the wording; the evals decide what stays.
- **`core`** (always): identity, plus following the operator's instructions that come after. At most two sentences.
- **`tools`** (tools on):
  - discovery through `search_tools` (found tools stay loaded for the conversation)
  - the `continue` turn rule
  - act rather than describe
- **`execution`** (`tools and exec_tools`): the box versus `host_access` rule, today's text verbatim. It is exempt from DD5 trimming, because eval agents have their execution tools disabled and the evals cannot measure it.
- **`knowledge`** (knowledge on): attached knowledge bases are searched with their search tools. Search them before answering from memory on matters they may cover.
- **`formatting`** (always, tool-free included): replies are Markdown, and links are written as `[text](url)`.
- **The notes layer** keeps its guidance in its own heading, trimmed. It covers:
  - when to save
  - wording a note as told (the operator-approved Puerto Rico example)
  - no secrets
  - never saving from tool or web content
  - what `(unverified)` means
- **The rules layer** keeps its heading, trimmed.
- **The date line** keeps its two wordings (`time_zones.render_date_line`), trimmed only if the evals allow.
- **The `pending` contract stays exactly as it is:** the `<saved_notes>` block, its `[n]` line format, `NOTES_EMPTY_TEXT`, and the coupling with "Rules take precedence over saved notes".

**DD5: Wording is chosen by data, by a fixed protocol.**
1. **Pinned prompt per run.**
   - Before every screening or final run, the prompt under test is committed (clean tree), and `measure-prompt --json <run-dir>/measure.json` is written into that run's directory.
   - `compare` never takes `--measure`, because that flag overrides every directory and skips the mixed-prompt check.
   - `compare` reads each run directory's own `measure.json`. Under DD12 it **refuses a run directory that has none**, and it refuses directories whose prompt fingerprints differ, so runs of different wordings can never be merged.
2. **The reference screen.** The first screened candidate is the **minimal** set: `core`, `tools`, `knowledge`, the trimmed notes and rules layers, and the date line, with no `formatting` section and no extra guidance. Its screen becomes the reference for every later screen.
3. **Screening.** Each run screens fact 0 × 4 phrasings (`--n 4`; variants are fact-major) for all 12 run sets on both models, about 25 minutes, and `measure-prompt` gives its size.
4. **Rejection.** A candidate is rejected if any of these hold:
   - any size gate fails: Flight 1's targets (bare prompt sections ≤ 357, all-on ≤ 1789) or DD13's checks. Size is measured with `measure-prompt` before screening, at no model cost.
   - any `safety` cell has a single failure
   - any other cell is 2 or more of 4 below the baseline's fact-0 count for that cell, read from the baseline's per-fact counts
5. **Additions.** Each later iteration adds **one** wording addition: `formatting` (#282), proactive-notes wording, planted-content wording, KB seeding (DD6b), and so on.
   - An addition is kept only if, against the reference screen, at least one cell gains 2 or more of 4 and no cell drops by 2 or more.
   - Additions that are kept accumulate into the reference.
   - A kept addition may then be shortened, provided its gain holds.
6. **Final run.** The final candidate runs the full n = 20 on both models, then `compare` against `m30-today.json`.
7. **Budget.** At most 6 screening iterations and 2 full runs, about 6.5 hours of live time in total.
   - Only screens count against the budget. Re-trimming for size before a screen is free.
   - If the minimal candidate's first screen is rejected, a re-trimmed minimal candidate is screened as iteration 2 and becomes the reference.
   - Shortening a kept addition may be folded into the next addition's iteration.
8. **Logging.** Every screen, every `compare` and every rejection is logged in the flight log with its numbers.
9. **Overfitting.** Tuning sees only fact 0, so facts 1–4 (16 of 20 variants per cell) are unseen until the final run. The final report gives per-fact counts.
10. **Statistical power.** At temperature 0, outcomes cluster by fact (effective sample about 5), so the `hold` gate catches only large drops. This is stated in the final report.

**DD6: Tool descriptions.**
- `save_note`, `update_note`, `forget_note` and the KB tool's `build_description` are trimmed under DD5.
- **KB discovery** has two candidates:
  - **(a) Prompt only:** the `knowledge` section points at `search_tools`.
  - **(b) Seeding:** attached KB search tools are added to the starting set, like the notes tools, at about 116 tokens per KB.
- **Choosing between them.** (b) is a DD5 addition. Fact 0 can't show a `kb-find` gain (the baseline is 4/4 on Haiku and 3/4 on gpt-oss), so screening chooses on "no cell drops, and smaller measured size" instead. The `kb-find` bar is checked at the final run.

**DD7: The connector tools are seeded only for agents a connector uses.**
- `send_to_platform_channel` and `find_platform_destination` (461 tokens today) are seeded only when the agent is some connector's `default_agent` or appears in its `channel_map`.
- **New helper.** A module-level `connector_bindings(conn) -> dict[connector_id, set[agent_name]]` lives in the repositories module. It reads raw connector rows and needs no `Encryptor`, keeping `ConnectorDirectoryRepository`'s DD-4 boundary.
  - `agent_names_in_use(conn)` is the union of its sets.
  - `ConnectorDirectoryRepository.search` is refactored to call it.
  - A row whose config fails to parse is skipped and logged, so one corrupt connector cannot break every `create()`.
- **Unmapped agents** keep the tools registered and discoverable through `search_tools`.
- **Inbound connector sessions** only reach mapped agents (`connectors/inbound.py::_resolve_agent_name`) and rebuild per message, so they always see current mappings.
- **Known accepted gap:** an open web session picks up a mapping change only when it is rejoined.
- **Unchanged:** `api.py::_connector_doctor_warnings`, because the tool stays registered. The send tool's description is not edited here (squawk 0207, out of scope).

**DD8: Settings › Prompts shows the sections.**
- `/api/info` replaces `base_prompt` with `platform_sections: [{id, title, applies_when, text}]`. The tool-free text is shown as its own entry. The date, rules and notes examples stay, rendered by the real functions.
- `system-page.js::renderPromptsPage` renders one block per section, with its "Applies when …" line, using DOM APIs (no HTML-string sinks), and updates its intro copy.
- Tests to update:
  - `test_flow_admin_settings_nav.py::test_general_pages_each_render_their_own_block` (browser, settings lane)
  - `test_aiat.py`'s key presence check
  - `test_prompt_layers.py`'s `/api/info` assertions
- The static JS/CSS guards run (squawk 0106).
- `docs/ui-testid-registry.md` retires `base-prompt-content` (which the retired-selector guard enforces) and adds the new testids.
- The CLAUDE.md "Settings › Prompts (M27 F3 L3)" paragraph and `evals/README.md` are updated.
- `test_credential_gate.py` and `test_desktop_shell.py` are unaffected: their assertions concern `/api/live` and a fake body.

**DD9: A behavior test checks Discord live.**
- **Spec:** a new `tests/behavior/discord-markdown-links.md`, reusing the `discord-live-round-trip` apparatus:
  - a dev instance on port 8486 with a scratch data directory, never 8484 or 8485
  - the driver bot and the main bot from `tests/behavior/.env.hat`
  - Haiku 4.5 through the plan token
- **No fetch.** The driver's message itself contains the URL and asks for a link to it, so there is no fixture page and no SSRF opt-out.
- **Pass:**
  - the bot's reply, read back over REST, contains the URL unbroken
  - `[text](url)` arrives intact if it was used
  - the message stays under 2000 characters
- **Leg 3 re-verifies first:** the driver token, the main bot token and the main bot's Message Content intent. `discord-live-round-trip` once needed a mid-run amendment for that intent.

**DD10: The evals' part extraction becomes structural.**
- `evals/tokens.py::extract_parts` stops matching headings or `BASE_PROMPT`. The layer order is known from the inputs: platform, then persona, rules, notes and date, each present or absent by configuration. The function:
  1. splits on the product's layer separator
  2. assigns layers by that known order
  3. subtracts the operator's own text (persona, rule texts, note texts) in every layer
  4. attributes platform sections by id from `platform_prompt`, with an `unattributed` bucket
- **No captured prompt fixtures are committed** (the operator's no-golden-files rule). Instead there are two checks:
  - **Unit tests** compose synthetic prompts in-test from `compose_system_prompt` and the stand-in counter, and pin the structural attribution.
  - **A one-time leg verification** comes at leg 1b's byte-identical step. `measure-prompt` with tiktoken must reproduce the baseline's sizes exactly (prompt sections 595 / 862 / 84; platform text 1308 / 1789 / 84), and the result is logged.
- **The one-time tiktoken verification runs twice:**
  - in leg 1a, right after the DD10 rewrite, with the product untouched
  - again at leg 1b's byte-identical step, **before DD7 lands** (after DD7, bare platform reads 847, not 1308)
- **`selftest`** gains a size check against the current baseline file. It applies only while the prompt fingerprint equals that baseline's, so it never runs against `m30-today`: DD13's connector-mapped configurations enter the `prompt` fingerprint. That is accepted.

**DD11: The convention.**
- The CLAUDE.md "Prompt evals" section gains this rule: a change to platform prompt text lands with an eval run compared with the current baseline, including its token cost. Platform prompt text means `the_one/agent/platform_prompt.py`, the rules and notes layers, the date line, and the starting tool descriptions.
- When Flight 2 lands, its final run becomes the new baseline, `evals/baselines/m30-platform.json`, so the next change compares against it.
  - Its pass-rate bars are derived with the same rules.
  - Its **size targets use ratio 1.0, "no larger than this baseline"**, for every size gate (bare prompt sections, bare, bare plus connector, all-on, all-on plus connector). Re-applying Flight 1's 0.60 bare ratio would demand another 40% cut on every future change.
  - (a′)'s carried-over form is the baseline's bare platform minus the connector parts its bare configuration contains (zero for `m30-platform`).
  - `derive-bars` gains a `--size-ratio` option, default 0.60 (unchanged for `m30-today`). It runs after the final `compare`, so it never affects this flight's gating.
- `the_one/agents.md` gets a "Platform prompt" section describing the structure.

**DD12: The measurement and scoring inputs are frozen** (Flight 1 debrief).
- **Content hashes, not git history.** A unit test checks that `scenarios_fingerprint(...)` equals `m30-today.json`'s `scenarios` fingerprint, which covers the scenarios, fixtures and judge files. It also pins digests of `evals/measure/` and of the scoring modules: `checks.py`, `outcomes.py`, `judge.py` and `harness.py`.
- **The only `evals/` code changes allowed** are DD10 in `tokens.py`, DD13, DD14, DD15, `compare` refusing a run directory with no `measure.json` (DD5.1), and `derive-bars --size-ratio` (DD11). Each is unit-tested.
- **DD13(b)'s connector row** is inserted by `tokens.py` through the scratch connection, keyed by the run's agent name, with no `harness.py` edit.
- **Model pins.** Ollama stays at 0.34.0 and `gpt-oss:20b` at digest `17052f91…`. Each live leg re-probes both. A change makes the `models` fingerprint differ and `compare` refuse.

**DD13: Stricter size checks**, added on top of Flight 1's DD11. They tighten the gates and loosen none. Each maximum is read from the baseline file's `sizes`, so the checks carry over to `m30-platform.json`.
- **(a) Bare plus connector.** A bare agent that is mapped to a connector must have a whole platform text, prompt sections plus tool schemas, of at most today's bare 1308.
- **(a′) Bare without connector.** Its platform text must be at most today's bare minus today's two connector parts: 1308 − 461 = 847.

  Together, (a) and (a′) stop text from moving unseen into tool descriptions after DD7 removes the connector pair.
- **(b) All-on plus connector.** It must be at most today's all-on 1789.
- **Built in code.** The connector-mapped variants are built from the frozen `evals/measure/*.toml` plus a connector row. They enter the `prompt` fingerprint, and `compare` reports them as hard gates.
- **No leakage.** Each mapped variant uses a distinct agent name (a distinct attempt number), and its connector row is inserted, measured, then deleted. Plain bare and all-on are therefore never measured as mapped.
- **Scripts.** Both variants are added to `_script_for`: all-on plus connector needs the `search_tools` script.

**DD14: `compare` reports `planted-flagged`'s non-vacuous count.** Baseline Haiku saved 0 planted notes. If Flight 2 makes Haiku save more eagerly, the safety cell goes live, and the count shows it.

**DD15: Unit-tier cost of the eval tests.**
- The per-scenario "passing script passes all 20 variants" tests run 5 variants, one per fact, in the unit tier.
- The full 20 run under `make eval ARGS=selftest`, a new subcommand that runs the can-fail suite at full width.
- This cuts about 45 s from `make test-unit` (the Flight 1 debrief measured 67 s for the eval tests).

### Citation Audit

Verified against the working tree at `085c15d` by a read-only code interrogation (2026-10-14), plus the Flight 1 debrief Architect. Line numbers are approximate; symbols are authoritative.

| Citation | Status |
|---|---|
| `the_one/agent/core.py::Agent._build_degraded_messages` swaps `BASE_PROMPT` for `CHAT_ONLY_PROMPT` by `startswith`, otherwise sends the system prompt verbatim; it is called when `supports_tools()` is False (DD2) | verified |
| `the_one/self_configuration/pending.py` falls back to `compose_system_prompt(BASE_PROMPT, system_prompt)` when `build_system_prompt` raises (DD2) | verified |
| `the_one/interfaces/web/app.py` `/api/info` returns `base_prompt=BASE_PROMPT` plus the date, rules and notes examples (DD8) | verified |
| `the_one/agent/prompt_layers.py::build_system_prompt(agent_name, persona, *, conn=None, tool_available=False, now=None)` always passes `BASE_PROMPT`. Its production callers are the factory and `pending.apply_pending_revision` (DD2) | verified |
| `the_one/agent/factory.py` seeds `send_to_platform_channel`, `find_platform_destination` and `current_time` into the starting set when registered, and the notes tools when notes are on. It has no connector query (DD7) | verified |
| `ConnectorRepository` has only list/get/create/update/delete. `ConnectorDirectoryRepository.search` scans `default_agent` and `channel_map` inline (DD7) | verified |
| `the_one/connectors/inbound.py::_resolve_agent_name` routes only to mapped agents, and `factory.create(agent_name)` is called without a connector flag (DD7) | verified |
| `parse_notes_block` depends on the `<saved_notes>` delimiters, `NOTES_EMPTY_TEXT` and `^\[(\d+)\] `, not on `NOTES_HEADING`. `tests/test_notes_tools.py` counts `(unverified)` occurrences, relying on the heading containing it (DD4) | verified |
| `the_one/knowledge/tool.py::build_description` is the only text `search_tools` matches a KB on. The `search_tools` schema description does not mention knowledge bases (DD6) | verified |
| `system-page.js::renderPromptsPage` fetches `/api/info` and fills five `<pre>` blocks. The browser test checks exactly five blocks and their titles (DD8) | verified |
| No `cache_control` exists in the providers (closes the caching question) | verified |
| The Discord connector posts `{"content": …}` with no markdown transformation and no length splitting (`connectors/discord/_rest.py`) (DD9) | verified |
| `evals/tokens.py::extract_parts` uses `startswith(BASE_PROMPT)` and a hard-coded separator, otherwise taking `head = ""` with no split (DD10) | verified (Flight 1 debrief Architect) |

### Prerequisites
- [x] Flight 1 landed and completed, with `evals/baselines/m30-today.json` committed (`085c15d`).
- [ ] The plan token works for Haiku 4.5. **Re-probe at the start of each live leg** (status only).
- [ ] Ollama 0.34.0 with `gpt-oss:20b` digest `17052f91…`. **Re-probe at the start of each live leg.**
- [x] `tests/behavior/.env.hat` has all six keys set (checked 2026-10-14; values not read).
- [ ] The behavior-test dev instance runs on port 8486 with a scratch data directory. Check the port is free at leg 3.

### Pre-Flight Checklist
- [x] All open questions resolved
- [x] Design decisions documented
- [x] Citation Audit complete
- [ ] Prerequisites verified (live probes per leg)
- [x] Validation approach defined
- [x] Legs defined

---

## In-Flight

### Technical Approach
1. **Leg 1a, evals readiness** (product untouched):
   - structural `extract_parts` (DD10), then the first one-time tiktoken verification against `m30-today`
   - the content-hash freeze test (DD12)
   - the extra size checks and connector-mapped measurements (DD13)
   - the vacuous count (DD14) and the unit-tier reduction (DD15)
   - the `measure.json` refusal and `derive-bars --size-ratio`
1. **Leg 1b, the structure:**
   - Introduce `platform_prompt`, with today's text split verbatim into sections and every condition true. The tool-capable all-on text must equal `BASE_PROMPT` and the tool-free text must equal `CHAT_ONLY_PROMPT`, both pinned.
   - Rewire the degraded path, the pending fallback, `/api/info`, Settings › Prompts, and `evals/tokens.py`'s section ids.
   - Run the second tiktoken verification.
   - Then switch the conditions on (DD3) and the connector seeding on (DD7).
   - The unit tests, static guards and settings-lane browser tests pass.
2. **Leg 2** writes the terse wording and runs DD5's screening loop on both models, including the DD6 KB comparison. It then makes the final n = 20 run, runs `compare`, and writes the new baseline (`m30-platform.json`).
3. **Leg 3** runs the Discord behavior test and re-runs the four prompt-sensitive behavior specs (`agent-notes-round-trip`, `agent-rules-round-trip`, `agent-tells-the-time`, `agent-self-revision-propagation`; the last is in `draft` status, and a defect in the spec itself is corrected at run time, not treated as a product regression), updating any expected wording first. It then writes the DD11 convention and the docs, and runs the full gate (`make gate` under `THE_ONE_TEST_NETNS=1`).

### Checkpoints
- [x] Leg 1a: the structural extraction is unit-tested, and the one-time tiktoken check reproduces `m30-today`'s sizes exactly. The freeze test, the extra size checks and the refusals are in place, and `make test-unit` passes.
- [x] Leg 1b: the byte-identical step pins both variants, and the second tiktoken check passes before DD7. After the switch, a bare agent's prompt contains no knowledge, notes or rules guidance, and a tool-free prompt contains no tool guidance. The unit suite, static guards and settings lane pass.
- [x] Leg 2: the final `compare` shows no hard-gate failure, and every screening and compare run is logged.
- [x] Leg 3: the Discord behavior test passes, and the full gate is green.

### Adaptation Criteria

**Divert if**:
- **No candidate passes the hard gates within DD5's budget.** Stop, record every candidate's numbers, and report the mission criterion unmet. Never relax a gate.
- **The plan token is refused, or Ollama's version or digest changes.** Pause the live work. A changed model needs a same-prompt re-baseline, recorded as a deviation.
- **Discord rejects or mangles the message in a way the prompt cannot fix** (for example, the connector splits the URL). Log a squawk against the connector, and record the criterion's status.

**Acceptable variations**:
- Section ids and titles may change during leg 2.
- Merging or splitting sections is allowed if the size checks and conditions hold.
- KB discovery may use (a) or (b) per DD6.

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses. This list will evolve based on discoveries during implementation.

- [x] `evals-readiness`: evals only, product untouched. Covers DD10 (structural extraction and unit tests), DD12, DD13, DD14 and DD15.
- [x] `platform-prompt-structure` (1b): DD1, DD2 and the DD10 hook. A byte-identical restructure, both prompts built at build time, every consumer migrated, and the second tiktoken verification.
- [x] `conditions-and-ui` (1c): DD3, DD7 and DD8. Conditions switched on, the tool-free notes heading, connector-only seeding, Settings › Prompts.
- [x] `wording-and-tuning`: DD4–DD6, DD5's protocol, the final n = 20 run, `compare`, the new baseline
- [x] `live-check-and-convention`: the DD9 behavior test, the four prompt-sensitive behavior specs, DD11, the full gate

---

## Post-Flight

### Completion Checklist
- [x] All legs completed
- [ ] Code merged (stacked PR; the operator merges)
- [x] Tests passing (`make gate` under `THE_ONE_TEST_NETNS=1`; ruff clean)
- [x] Documentation updated (CLAUDE.md, `the_one/agents.md`, `evals/README.md`)

### Verification
- `python -m evals compare --baseline evals/baselines/m30-today.json <final run dirs>` reports no hard-gate failure, with best-effort cells listed as measured. Its output is in the flight log.
- `make eval ARGS="measure-prompt"` shows these sizes:
  - bare prompt sections ≤ 357
  - bare platform text ≤ 847
  - bare plus connector ≤ 1308
  - all-on ≤ 1789
  - all-on plus connector ≤ 1789
- `/mission-control:behavior-test discord-markdown-links` passes.
- `make gate` passes.
- Behavior specs `agent-notes-round-trip`, `agent-rules-round-trip`, `agent-tells-the-time` and `agent-self-revision-propagation` pass on a dev instance (port 8486, scratch data directory) against the new prompt. Expected wording is updated first where the platform text changed, and each run log is referenced in the flight log.
