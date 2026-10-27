# Flight Debrief: Safe names

**Date**: 2026-10-27
**Flight**: [Safe names](flight.md)
**Status**: completed
**Duration**: 2026-10-26 (planned and flown) - 2026-10-27 (merged as PR #329, `3b3d42a`)
**Legs Completed**: 4 of 4
**Plugin version**: mission-control 1.2.3

## Outcome Assessment

### Objectives Achieved
One naming rule (`the_one/naming.py::check_name`) now guards every API path that sets the name of an agent, model provider, knowledge base or MCP server. A refusal is a pydantic-shaped 422 on `loc ["name"]` that all four forms show on their Name field. Creating an agent with an existing name is a 409 instead of a silent upsert. Renames carry their references: agent → connector bindings, MCP server → attached agents' overrides and disabled tools, and the KB carry is now a reusable helper. The agent editor's load failure is an error toast plus a lasting header line tied to the disabled Save by `aria-describedby`. An idempotent startup repair renames any stored rule-breaking name through the same carries and never blocks startup. The operator's original defect was a `/` in an agent name that 404'd every `/api/agents/{name}…` route; it is closed for new names and repaired for existing ones.

### Charter Criteria
| Criterion | Status | Notes |
|---|---|---|
| A rule-breaking name is refused on create, edit and rename of all four, on the name field, nothing saved, API included | met | `tests/test_api_name_rule.py`: every POST/PUT under the four prefixes is classified CHECKED or EXEMPT, and each CHECKED route refuses `a/b` and stores nothing. `tests/browser/test_flow_name_rule_forms.py` covers the four forms plus MCP. |
| After upgrade, every stored rule-breaking row has a safe, unique name, references attached, normal open/save/rename/delete | met in tests; **not yet field-checked** | `tests/test_name_repair.py` seeds one bad row of each kind with every reference type, and a lifespan test returns `GET /api/agents/{repaired}` → 200. The operator's stuck macOS agent has not been upgraded yet (operator, 2026-10-27). |
| A load failure appears where the operator will see it, explains the disabled Save, Save stays disabled | met | Toast plus header line; the testid lives on the header slot only while the load has failed; `aria-describedby` on Save (review fix). |

### Was a sortie the right vehicle?
Yes. It entered as a squawk request and correctly failed the squawk gate (several items, design calls, a data repair). It stayed one decision cluster ("what is a safe name, and how do existing names get there safely"), even after the operator widened it from agents to four entity types; the widening added call sites, not decisions. Two signals to record: the operator reversed one chartered item (reserving `default`) after Architect review 1 showed a stored `default` configures every no-agent chat; and the legs grew from 2 to 4 (over the sortie soft limit of 2 plus HAT) when Architect review 2 asked for the rename carries to be split out. The work never stopped behaving like one flight. The operator found the planning rounds "worth it" (2026-10-27).

## What Went Well
- **Reviews caught real defects before code.** Architect 1 caught the `default` contradiction (DD11/DD12), the JSON import re-importing a bad name on every start, `" self-configuration "` slipping past the reserved-name check after trimming, Windows-invalid scratch paths and non-unique MCP names. Architect 2 caught that a route walk can't infer which routes take a name, the missing never-raise contract on the MCP carry, PUT bodies without `name`, a repair failure example that could not fail, a scan that would decrypt, and a citation drift (`connector_bindings`). Each leg's Developer review then caught implementation-level traps: legacy rows becoming uneditable, the two KB route-test contracts, the undecryptable-agent recipe, `setError`'s collapsed slot, whitespace controls being deleted rather than spaced, and the raw provider `UPDATE`.
- **Validate at the boundary, never on the model.** Keeping `name: str` on the models let legacy rows still load, so the repair could exist at all.
- **One error shape, one client path.** A pydantic-shaped 422 meant `App.api.fieldErrors` served all four forms with no client copy of the rule.
- **The repair reuses the operator's rename paths.** Repair and operator renames behave identically, and fixing the carries fixed two real pre-existing gaps (agent rename dropped connector bindings; MCP rename orphaned overrides).
- **A structural route-classification test** (`CHECKED`/`EXEMPT`, unclassified fails) instead of a list someone has to remember.
- **Recording the worktree's baseline failure list before leg 1** made every later leg's comparison mechanical.
- **Worktree isolation** kept the work clear of the main checkout.

## What Could Be Improved

### Process
- **The baseline covered the unit tier only.** The worktree's fresh venv also fails one knowledge browser test on the base code. Nobody knew until leg 3 hit it, and leg 3's triage then misattributed it to `usearch` 2.26.6. The Flight Director pinned `usearch`, and the landing gate showed the pin didn't help. Running the test on the base code with the same venv settled it as pre-existing. Cost: a second Developer spawn, a wrong anomaly entry, and one gate re-triage. A sortie in a fresh worktree should baseline every lane it will gate, not just the unit tier.
- **`make gate` stops after a non-zero unit tier.** With known environment failures in the baseline, the browser half never ran, and the Flight Director had to run `--parallel 3` by hand.
- **A Developer stopped mid-verification** (leg 3) with background runs still going, after the `--parallel 3` lane run and several targeted reruns. A second Developer finished from the first one's handover. The leg's verification step (six lanes plus static guards plus unit) was too much for one agent pass.
- **Never-raise contracts weren't required as tests.** Two of the three review-fix items were contract gaps. `carry_kb_rename` computed tool names outside its guard, and the repair called each carry outside a per-step guard. The legs stated "never raises" in prose. The fix is to require one injected-failure test per call site.

### Technical
- **The rule's character set has gaps** (debt, not a bug): zero-width `Cf` characters (e.g. U+200B) and U+2028/U+2029 pass, there is no NFC normalisation, and duplicate checks are case-sensitive on create/rename but case-insensitive in the repair.
- **Rename carries live in four places** (`SQLiteAgentStore.rename`, `cascade_rename`, `the_one/mcp/rename_references.py`, `the_one/knowledge/kb_rename.py`). A future named entity has to remember all four.
- **Accepted trade-offs, recorded in `the_one/agents.md`:**
  - The MCP carry runs after the source commit, not in its transaction.
  - `mcp__foo__` also prefixes a `foo__bar` source's tools.
  - A `disabled_tools` rewrite can disable a same-named tool of another attached source that normalises to the new prefix.
  - The create check-then-save race.
- **The 64-character limit broke one existing browser seed** (`test_shell_rail.py`'s 125-character KB name). It was not in the flight's risk list.
- **The agent editor's other header errors are not announced to screen readers** (no `errorRole`). This predates the sortie; the accessibility review found it.

### Documentation
- **Release notes:** the next release notes must say that unsafe names are renamed once at startup and logged. There is no unreleased notes file yet.
- **Checklist:** a short "add a new named entity" checklist (rule call, route classification, carry, repair scan, form mapping) would make the pattern reusable. Today it lives across `the_one/agents.md` "Naming rule" and CLAUDE.md's watch-out.

## Deviations and Lessons Learned

| Deviation | Reason | Standardize? |
|---|---|---|
| `default` reservation withdrawn after the operator had chosen it | A stored `default` configures every no-agent chat (`AgentFactory._load_config`) | No (specific), but yes to the pattern: when a review shows a chartered item breaks existing behaviour, go back to the operator rather than design around it |
| Legs re-cut 2 → 3 → 4 | Architect 1 wanted forms apart from the server; Architect 2 wanted the MCP carry in its own leg for review focus | Yes: when one commit lands the whole flight, splitting a leg for review focus costs nothing |
| PUTs check `name` only when it is sent (vs DD4's "check the merged name") | Otherwise a legacy bad row could not be edited until the repair ran | Yes, for any rule added over existing data |
| `shell.setError` on state transition (vs DD10's direct `textContent`) | A direct write leaves the slot `data-empty` (collapsed, invisible) | Yes: verify a review's "precedent" against the control's internals before it becomes a DD |
| JSON import also skips by body name | Skipping by stem alone re-saved mismatched files every start | No (one-off fix) |
| `usearch` pinned in the worktree venv | Attempted fix for the knowledge failure; superseded by the base-code repro | No |

## Key Learnings
- A rule added over existing data needs three parts in this codebase: a checker at the write boundary, a reader that tolerates bad legacy values, and a repair that goes through the real write paths. Leaving out any one breaks either the API or the upgrade.
- "Agents can only narrow" made the repair safe. Every carry moves or copies an existing value and never grants one.
- In this project, a fresh install is not a green install. Expect environment failures in any new worktree, and baseline them before trusting any red result.

### Test metrics
- **Unit tier** (debrief run, netns, start load 1.44): 9 failed / 7765 passed / 23 skipped, 340 s. That's identical to the landing gate (334 s). Against the worktree baseline (10 / 7650 / 20, 371 s), the sortie added ~115 tests at no visible wall cost. The 9 failures are the fresh-venv set (credential-gate exemption, desktop host ×3, MCP trust store, OpenRouter wire ×4). The `test_vector_store` parametrisation is intermittent: it failed in the baseline and in leg 1, and passed at the gate and here.
- **Browser** (`--parallel 3`, netns, WebKit, start load 1.44): `PARALLEL_RESULT rc=1 total=1648s lanes=13 failed=knowledge`.
  - **Knowledge:** the one failure is the fresh-venv `test_detail_view_indexing_poll_reindex_and_search` ("indexed: 2"), also failing on base with this venv.
  - **Budgets:** no lane over budget. `chats` 395 and `library` 352 confirm that the landing gate's over-budget flags (467 and 423 at load ~2.0) were host contention.
  - **Against M31 F5 L12** (1693 s): no lane moved 15% or more. `shared`, which holds the sortie's only new browser file, is +17 s.

## Methodology Observations
All observed with mission-control **1.2.3**.

1. **Sortie skill, Plan step 5 (re-check the gate).** The legs reached 4, over the soft limit of 2 plus an optional HAT. The skill says to say so and ask the operator whether to consolidate or escalate. The Flight Director said so in the flight log and the operator-facing summary, but did not ask a separate question, because the operator had already authorised execution after the review. Expected: either the skill notes that the gate question can be folded into an existing authorisation, or the Flight Director asks anyway. Cost: none observed, but the gate was effectively skipped.
2. **Agentic workflow, Phase 2b (Developer implement).** A Developer returned interim handbacks ("waiting on its own background work") three times, then a "not finished" report. It never resumed on its own after its last background run completed. Expected: the agent finishes, or the workflow says how to detect and recover a stalled Developer. Cost: one extra Developer spawn and about 40 minutes of wall time. The spawn prompt for later legs gained "don't stop with background work still running", and leg 4 still produced one interim notification.
3. **Agentic workflow, Phase 1 / prerequisites (fresh worktree).** The project's leg-execution crew and the skill ask for a unit baseline. Nothing prompts a browser-lane baseline in a fresh environment. Expected: a prerequisite of "baseline every lane the landing gate will run, in the environment the legs will run in". Cost: a misdiagnosed anomaly, a dependency pin that didn't help, and a gate re-triage.
4. **Agentic workflow, Phase 2d (gate).** The project's `make gate` is unit-then-browser and stops when the unit tier is non-zero. With baseline environment failures, the documented gate can never reach the browser half. Expected: a project-side gate option that compares against a recorded baseline. This is project tooling more than skill, recorded so a sweep can see it. Cost: a manual browser run.
5. **Flight skill, Phase 5b (Architect review) feeding a DD.** Architect review 2 recommended writing `shell.errorEl.textContent` directly (DD10) on the strength of a precedent. Leg 3's Developer review found that it leaves the slot collapsed. Expected: the Citation Audit requires a precedent that a DD copies to be checked for the specific behaviour copied, not just for existence. Cost: a DD contradicted at leg design, recorded as a deviation; no rework, because it was caught before code.
6. **Squawk skill, Log verb.** It worked as designed: a request phrased as a squawk was correctly gated to a sortie on three named criteria. Credit, not a defect.

## Recommendations
1. **Make a fresh install reproduce a green suite** (critical for every future worktree). Pin the dependency set with a constraints or lock file, or bisect the drift. That covers the 9 unit failures and the knowledge browser failure. This joins squawk 0241 with new evidence rather than starting a new item.
2. **Baseline every gated lane at sortie or flight start in the environment the legs use,** and give the gate a baseline-aware mode, so known environment failures neither hide the browser half nor send a leg chasing them.
3. **Write "never raises" as a test requirement.** Each call site of a never-raise helper needs an injected-failure test in the leg's acceptance criteria.
4. **Size verification into the leg.** Leg 3's six lanes plus guards plus unit exceeded one Developer pass. Split verification-heavy UI legs, or have the Flight Director run the lanes.
5. **Settle the name rule's remaining character questions** (`Cf`, U+2028/2029, NFC, case-insensitive duplicates) the next time names are touched. That needs a design call, so it is not a squawk.

## Action Items
- [x] Added this sortie's evidence to squawk 0241: the knowledge browser test also fails under a fresh venv, and the 9-test set (recommendation 1)
- [x] Squawk 0273: the agent editor's header save errors are not announced to screen readers (pre-existing; accessibility review)
- [x] Release-notes line for the startup name repair: written into the v0.12.2 notes (no squawk needed)
- [x] Squawk 0274: scrub the operator's username and home paths from older mission docs (this sortie's own log was scrubbed on the debrief branch)
- [ ] Agent tool overrides (found 2026-10-27 on the Windows build): Save accepts a value outside the app-wide setting, opening a panel and saving copies inherited values into the override, and the chat-start refusal names neither tool nor field. A sortie charter was drafted and agreed, then the operator chose to do discovery first; no sortie is logged yet
- [ ] Carry: Windows-appropriate default denied paths (design; a separate sortie or squawk after sortie 07)
- [ ] Carry: name-rule character questions (recommendation 5)
