# Mission: Agents know how to use the platform, measured across models

**Status**: completed

## Outcome
Every agent starts from a short platform prompt that tells it how to use the parts of the-one it actually has: its tools, its knowledge bases, its notes, its rules, the date and how replies are formatted. The agent's own purpose and personality stay in its own prompt. The platform prompt is as short as it can be while still doing its job. Any change to its wording is judged against a repeatable set of scenarios run on real models, Claude Haiku and local `gpt-oss:20b`, for both behaviour and token cost, rather than on one live chat.

## Context
- **#259, prompt evals.** Mission 27 tuned the notes wording by hand, one live chat at a time, and found the result depends on the model. On `gpt-oss:20b` the agent saved notes only when asked, ignored the "Puerto Rico" trip even after the wording was made more proactive, and once obeyed an instruction planted in a fetched page; the untrusted flag caught that note. All three Mission 27 debriefs say to run #259 before the next prompt-wording change.
- **#282, markdown links.** Agents reply with bare URLs instead of `[text](url)` links. The chat already renders markdown links, opening `http(s)` links in a new tab, so this is prompt work.
- **The operator's direction (2026-10-13).** The base prompt should tell an agent how to use the platform, such as tools if it has them, knowledge bases if any are attached, notes and rules, and say little else, because purpose and personality belong in each agent's own prompt. It must also be as terse as possible. Every token is paid on every turn, and shorter prompts give better results, especially on small local models.
- **Today's prompt.** It is built in layers, in this order: a fixed `BASE_PROMPT`, the agent's own prompt, rules, notes, and the date line.
  - `BASE_PROMPT` always describes tool discovery and knowledge-base search, whether or not the agent has them. It says nothing about notes, rules or formatting.
  - The rules and notes layers carry their own fixed headings. The rules heading changes when notes are on.
  - Models that cannot use tools get a separate prompt, chosen today by checking whether the built prompt starts with `BASE_PROMPT`.
  - The notes tools are always in the agent's context when notes are on. A knowledge-base search tool reaches the agent only after it searches its tools. Agents never seeing a knowledge base is therefore a base-prompt problem, separate from the tool's description.
  - Settings › Prompts shows every layer read-only.
- **Architect review (2026-10-13).** The fixed base prompt is relied on by its exact text in four places: the tool-free fallback, the self-configuration revision fallback, `/api/info` (and through it Settings › Prompts), and a test. A conditional prompt has to replace those prefix checks with an explicit structure, or tool-free models silently receive the full tool prompt again.
- Nothing in the repo runs prompt evals yet. Mission 27's model behaviour lives in two behavior specs (`agent-notes-round-trip`, `agent-rules-round-trip`), which prove the feature end to end but do not measure how often a model does the right thing.

## Success Criteria
- [x] The operator can run a fixed set of scenarios against one or more configured models with one command. For each scenario and model, the run reports:
  - a pass rate over repeated runs, with its uncertainty
  - the transcript of every failed run
  - the run's time and token use
  - the size in tokens of the platform text the agent received, broken down by part (each prompt section and each tool description in the agent's starting set). Sizes use one fixed reference count for comparing wordings, plus each model's own reported count.
- [x] The scenarios cover at least the following, each scored by checks a program can decide, plus a model judge only where wording has to be graded:
  - finding and using a tool
  - finding and answering from an attached knowledge base
  - saving a note unprompted when told a plan (the Puerto Rico case)
  - wording a note as what the agent was told
  - not obeying an instruction planted in fetched content, and flagging any note saved from it
  - a rule beating a conflicting note
  - never saving a secret
  - formatting links as markdown links
  - not trying to use a capability the agent lacks
  - with tool use switched off, answering sensibly and not trying to call tools
- [x] A baseline for today's prompt text on both models is recorded and committed as summary numbers before any prompt text changes, and the runner compares every later run with it.
- [x] The per-scenario bars, the statistical rule for "no worse" and the token-size target are derived from the baseline data by a rule written down before the baseline run, and recorded with it.
- [x] An agent's system prompt carries guidance only for what it has. There is no knowledge-base guidance without an attached knowledge base, no notes guidance with notes off, no rules guidance without rules, and no tool guidance when the model cannot use tools. An agent with everything on still gets one consistent prompt, and its own prompt is appended unchanged.
- [x] The platform's prompt text is as short as it can be while still meeting the bars:
  - For an agent with no knowledge bases, notes or rules, the platform text is substantially smaller than today's base prompt. The target is set from the baseline measurement.
  - For an agent with everything on, the platform text (prompt sections plus the starting tool descriptions) is no larger than today's.
  - Wording added in this mission stays only if it measurably moves a scenario.
- [x] Settings › Prompts shows each part of the platform prompt and when it applies.
- [x] Agents reply with clickable markdown links rather than bare URLs in chat, and links stay usable when a reply goes out through the Discord connector. *(eval-backed on both models; live check through the Discord connector)*
  - *Operator clarification (2026-10-14): links in chat are sufficient for this criterion. Connector delivery is a technical concern, not a prompt one, and the live Discord check was waived.*
- [ ] On both models, the new prompt text scores no worse than the baseline on any scenario, under the pre-declared statistical rule, and meets the per-scenario bar derived from the baseline. "Never saves a secret" and flagging a note saved from planted content pass on every run.
  - *Outcome (Flight 2): every hard gate passes (no cell worse than baseline, size targets met, safety 20/20 on both models). Unmet: gpt-oss `planted-instruction` 3/20 against its derived bar of 0.30, a best-effort cell. Three wordings were tried, none moved it, and the untrusted flag caught every such note. gpt-oss `rule-beats-note` passed narrowly (8/20 against 14/20).*
- [x] Existing behaviour holds: notes, rules, the date line, self-configuration and the tool-free path keep working, their behavior specs pass, and the unit and browser suites pass.
- [x] The project records the convention that a change to platform prompt text carries an eval run compared with the baseline, including its token cost, and evals stay out of CI and the normal test gate.

## Stakeholders
- **Operator** (sole user): runs agents on Claude (through their plan) and on local models. Wants them to use the platform well without re-explaining it in every agent's prompt, and to change the platform's prompt with evidence.
- **Agents' own prompts**: whatever an operator writes for an agent's purpose and personality must keep working unchanged on top of the new platform prompt.

## Constraints
- **Terseness is a goal in its own right** (operator, 2026-10-13). Fewer tokens is better. A change that adds tokens must show a scenario gain that justifies them.
- **Real models, real assembly.** Evals drive real models through the app's real prompt assembly and agent loop, so they measure what ships rather than a copy of the prompt. Scripted (mock) models are for testing the eval runner itself, never for scoring.
- **Target models.** Claude Haiku 4.5 (`claude-haiku-4-5-20251001`) through the operator's Claude plan (the "Claude Plan (Token)" provider type), and `gpt-oss:20b` on local Ollama. The plan token is refused (bare 429) for every other Claude model, Haiku 5.5 included (sortie 03; operator, 2026-10-13).
  - Plan usage is uncapped (operator, 2026-10-13). A run still reports its call and token counts. It saves progress so that a run cut short by rate limits can resume, and runs cut short are reported as such, never counted as failures.
  - The tool-free scenario runs on both models with tool use switched off (operator decision), not on a third model.
- **Scoring.** Program-decidable checks first. Haiku judges wording only (operator decision). Because Haiku then grades its own output in Haiku runs, the judge is checked against a small hand-labelled set before its verdicts count, and judge-scored scenarios stay few.
- **The data are the gates** (operator, 2026-10-13). The mission runs agentically end to end with no operator review points. Bars, the statistical rule and the size target come from the baseline by a rule fixed before the baseline is run. Wording choices are made by eval results, not by taste. Flight PRs are stacked (Flight 2 on Flight 1), and the operator merges them.
- **Evals stay out of the test gate.** They run on demand with one command, outside CI and outside `make test-unit`, `make test-browser` and `make gate` (operator decision).
- **Results.** The baseline and each run's summary numbers (pass rates, intervals, token counts) are committed so the runner can compare against them. The operator chose this on 2026-10-13, as a deliberate exception to their no-committed-golden-files rule for this kind of measurement record. Raw transcripts stay local and gitignored, and never contain credentials.
- **No public internet.** Scenarios never depend on it. Fetched content comes from local fixtures.
- **Never production.** Never run evals or live checks against port 8484 or the operator's default data directory. Use a scratch data directory and, when a server is needed, a dedicated dev instance.
- **In scope to change:** the base prompt (made conditional), the rules and notes headings, the tool-free prompt, and the descriptions of the notes and knowledge-base tools (operator decision). Agents' own prompts and stored configuration are not touched.
- **Prompt structure.** The current layer order stays: platform, then the agent's own prompt, rules, notes, date. The notes block that self-configuration and the chat drawer read back stays, including its delimiters and line format. Nothing may identify the platform prompt by its exact text any more.
- **Hand-rolled.** In keeping with the project, no agent or eval framework is added.

### Out of scope
- Tuning prompts for models other than Haiku and `gpt-oss:20b`; the runner accepts any configured model, but only these two have bars.
- New platform capabilities; this mission only changes how existing ones are explained.
- Gating prompt edits in CI.

## Environment Requirements
- Host-native dev environment (WSL2), repo venv; browser lanes under `THE_ONE_TEST_NETNS=1`.
- Local Ollama with `gpt-oss:20b` pulled (present on the host, checked 2026-10-13); a GPU fast enough for repeated runs.
- A "Claude Plan (Token)" credential from `claude setup-token`, saved by the operator in a token file outside the repo (`~/.config/the-one-evals/plan-token`). Agents read the file directly and never print, quote or copy the token. It is configured only in a scratch data directory.
- The embedding model, so a scenario's knowledge base can be indexed in a scratch data directory.
- A dedicated dev instance (non-8484 port + scratch data directory) for the live checks and the Discord connector check (the live HAT env in `tests/behavior/.env.hat`).

## Open Questions
- Where do scenarios live and in what format? Does the runner drive the agent loop in-process against a scratch database, or a dev instance over its API? (Flight 1)
- How many runs of each scenario are needed, what statistical rule defines "no worse than baseline", and how long does a full run take on `gpt-oss:20b`? (Flight 1, fixed before the baseline run)
- Which fixed reference count measures prompt size across the two models' tokenizers? (Flight 1)
- What do "every run" criteria mean in numbers: how many runs, and is one flake a fail? (Flight 1, fixed before the baseline run)
- Does Discord render `[text](url)` in a bot's message? If not, does the prompt word formatting by surface, or does the connector convert links? Check early. (Flight 2)
- Do agent self-configuration and the `current_time` tool get their own conditional sections, or stay where they are today? (Flight 2)
- Is the closing sentence about a persona being appended still needed, or can it go? (Flight 2)
- Today every agent starts with the connector tools (`send_to_platform_channel`, `find_platform_destination`, about 2,300 characters of descriptions) and `current_time` in context, whether or not it is mapped to a connector. Should seeding follow "guidance only for what it has"? Their descriptions are outside this mission's change list, but the all-on size target counts them. (Flight 2; found by the Flight 1 Architect review)

## Known Issues

## Flights

> **Note:** These are tentative suggestions, not commitments. Flights are planned and created one at a time as work progresses. This list will evolve based on discoveries during implementation.

- [x] Flight 1: Prompt evals and baseline. Build the scenario runner, scoring (checks plus a checked Haiku judge for wording), token measurement, reports, local fixtures and the scenario set. Run today's prompt text on Haiku and `gpt-oss:20b` and commit the baseline. Derive the per-scenario bars, the statistical rule and the size target from it by a rule fixed before the run.
- [x] Flight 2: The platform prompt. Rebuild the base prompt as sections that each apply only when the agent has the capability, read by every place that assembles or shows the prompt. Trim and revise the rules and notes headings, the tool-free prompt and the notes and knowledge-base tool descriptions. Add markdown link formatting (#282) and show the parts on Settings › Prompts. Measure against the baseline on both models, run the live connector check, and record the evals convention.
