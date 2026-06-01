# Flight Log: Slash HAT closure + ACL/slash-sync cluster fix + L4-enhancement test debt

**Flight**: [Slash HAT closure + ACL/slash-sync cluster fix + L4-enhancement test debt](flight.md)

## Summary

Flight in planning. F14 closes M11 criterion #10 (slash commands validated against real Discord) by repairing the 4-bug ACL/slash-sync cluster F13 L6 surfaced (Bug C retired as false positive at recon time; Bugs B + D + E are real; Bug A is ops/docs) + shipping ephemeral-where-appropriate polish for the self-only commands + backfilling the L4-enhancement unit tests + resolving the 2 pre-existing browser failures (4-flight deferral closed) + refactoring `admits_inbound` to take an `AdmissionContext` dataclass (Option B) + authoring a re-runnable `discord-slash-end-to-end` behavior-test spec driven by a 2nd Discord bot via `discord.py`. 10 legs. Per agentic-workflow protocol, code review + commit deferred to Phase 2d.

---

## Flight Director Notes

### Session start (agentic-workflow)
- Loaded `leg-execution.md` crew phase file — validated `## Crew` / `## Interaction Protocol` / `## Prompts` present; well-formed. Developer=Sonnet, Reviewer=Haiku.
- Flight status `ready` → `in-flight`. Branch `flight/14-slash-hat-closure-and-acl-cluster-fix` already exists with planning commit `0d7a08c`; F13 landed at `ed78d0e`.
- State consistency check: flight log shows all legs empty, leg artifacts dir empty, leg statuses unset → consistent with a fresh `ready` flight. No remediation needed.
- `docker-compose.yml` shows as modified (operator-local state per pulled-forward methodology lesson #4) — stays unstaged across all legs.
- Execution plan: L1–L9 are autonomous (design+review per leg, batch implement, no per-leg commit); single review+commit at Phase 2d; L10 is operator-driven (manual HAT + 4 behavior-test runs) and gates flight land. L1 (Bug D fix) designed/implemented before L8 (AdmissionContext refactor) per the flight's sequencing note so the refactor migrates an already-correct call site.

### L1 design (Bug D)
- Designed leg 01. One deliberate correction to the flight spec: the flight sketched L1 option (a) "import `_default_not_dm` directly into `_commands.py`". Recon found `DiscordPlugin.is_dm` is a real override (`_discord.py:1598`); hardcoding `_default_not_dm` (which returns plain `False`) would deny DM-invoked slash commands on a channels-restricted account. Leg takes option (b): a shared `is_dm` derivation helper honoring the plugin hook + thread `plugin` into the command context dict. Keeps the command path byte-for-byte aligned with `_routing.py:_agent_admits`.
- **Flight-spec inaccuracy noted for L8's author**: flight.md:96 describes `_default_not_dm` as returning `not envelope.raw.get("is_dm", False)`; the real function (`_acl.py:85`) returns a plain `False`. L8's `AdmissionContext.from_envelope` derives `is_dm` too — it should reuse L1's `envelope_is_dm` helper, not the flight's mis-stated formula.
- Design review (Developer, 1 cycle): **approve with changes**. High-severity catch: the shared `_build_context` test helper carries no `plugin` key → a bare `context["plugin"]` production read would `KeyError` across 25+ existing command tests. Incorporated: leg step 5 now adds `"plugin": None` to `_build_context`. Low/suggestions (helper-as-L8-home note, flight-spec inaccuracy) folded into the leg. Changes are guidance clarifications, not a design change → no second design-review cycle. Leg status → `ready`.

### L2 design (Bug B) — ESCALATED: flight DD premise contradicted by codebase
- Designed leg 02 per the flight's Bug B Design Decision (switch `_sync_slash_commands` from top-level `config.guilds` to `allowlist.guilds`). Design review (Developer, cycle 1): **needs rework** — surfaced a factual contradiction, verified independently by the Flight Director:
  - **`config.guilds` (top-level) is NOT an orphan key.** It is the live "Scope to servers" Runtime Config field, written by `connector-form-discord.js:417`, validated at `api.py:1089-1116`, and *deliberately disambiguated* from the allowlist "Servers" axis (form comments `:95`, `:200-205`, "HAT round-2 fix #2"). The flight DD's premise ("UI stores guilds under `config.allowlist.guilds`; top-level is `None` post-creation") is false.
  - **`config.guilds` ("which servers to register slash commands in") ≠ `allowlist.guilds` ("which guilds may send inbound to the bot," the ACL admission axis at `_acl.py`).** Pointing slash-sync at `allowlist.guilds` would couple command registration to the admission allowlist — a semantic change, not a key-rename.
  - **The flight's "2798 unchanged / no new tests" is false**: 3 existing tests (`test_connectors_discord.py:2838/2909/2951`) construct `config={"guilds": [...]}` top-level and assert `tree.sync` fires; switching the read breaks all three.
  - **Real defect candidate**: the "Scope to servers" tooltip (`:207`) says *"Leave blank to allow all servers the bot is in,"* but `_sync_slash_commands:248` SKIPS registration entirely on blank. The operator left it blank → `/agents` never registered → their F13 L6 workaround (adding top-level `config.guilds`, mission.md:117) is precisely what fixed it. So slash-sync reading `config.guilds` is correct; the bug is the blank-handling semantic mismatch.
- **Decision**: do NOT implement the flight's Bug B fix as written (it would introduce a behavior regression on a false premise). Escalated to operator for the fix-shape call, since the original DD was operator-directed. L2 paused pending operator direction; L3–L9 unaffected (independent surfaces). Per agentic-workflow "Mid-execution scope changes," the flight's original Bug B framing is preserved as commentary; the pivot is recorded here, not by rewriting the flight DD in place.

#### Operator decision (2026-06-01): UNIFY onto `allowlist.guilds`
- Operator chose option **"Unify onto allowlist.guilds"** (over "honor blank = all guilds" and "reframe as non-bug"). `allowlist.guilds` becomes the single source of truth for guild scoping — governing BOTH inbound admission (existing ACL meaning) AND slash-command registration. The separate "Scope to servers" `config.guilds` field is retired.
- L2 re-scoped from a 4-edit mechanical leg into a unification leg: **v27 data migration** (fold top-level `config.guilds` → `allowlist.guilds`, dedup-union, then drop top-level), `_sync_slash_commands` reads `allowlist.guilds`, retire the "Scope to servers" form field (KEEP the unrelated `intents.guilds` "Server info" gateway-intent checkbox), remove the redundant `api.py:1088-1116` validator, migrate the 3 existing slash-sync tests + add a v27 migration test, update agents.md + doc comments.
- Confirmed the operator retains a guild-setting UI surface post-retirement: the connector allowlist editor's "Servers" section (`connector-editor.js:2294-2314`, F12 L5) already binds `allowlist.guilds`.
- **Blank-handling**: preserved existing skip-on-blank (empty `allowlist.guilds` → slash-sync registers nowhere; ACL empty-axis still = admit-all). The "blank = all guilds" behavior was a separate option the operator did not select; documented as a localized future change. Asymmetry is intentional.
- Leg 02 rewritten with a "Scope pivot" banner at top citing the false premise + operator direction. Flight.md Bug B DD annotated at its header (body preserved as commentary). Re-running design review on the substantially-changed leg before implementation.
- **Design review cycle 2 (re-scoped leg): needs rework → incorporated.** Caught concrete build-breakers, all folded into the leg: (1) `CURRENT_VERSION` must bump 26→27 at `schema.py:15`; (2) `test_db_migration.py:261-264` hardcodes `assert CURRENT_VERSION == 26` → update to 27; (3) `test_connectors_discord.py:2951` uses raw int guild ids — the `allowlist.guilds` model validator (`db/models.py:443`) enforces `list[str]`, so migrate to string ids + rename (int support intentionally dropped under unification); (4) two browser tests definitely break — `test_guilds_add_saves` + `test_additional_config_hides_reserved_keys` in `test_flow_studio_connector_discord_form.py` (promoted to named required edits); (5) two missed JS sites — `snapshot()` read `:464` + dirty listener `:580`; `_splitGuildsList:381` safe to delete (single caller); (6) agents.md slash-sync narrative is located by the `for each g in ...` sentence in the M10 F8 L9 CommandHandler section, NOT line 797 (the L8 ACL section). (7) prefer `.pop("guilds")` migration idiom for a clean grep gate.
- **Non-empty coupling FYI (cycle-2 finding, operator-surfaced, not blocking)**: unification fuses `allowlist.guilds` to govern inbound-admission + DM-deny posture + slash-registration simultaneously. Pre-pivot, slash scope was separable from admission via the standalone `config.guilds`. The operator's connector is already guild-scoped so it costs them nothing live; F12 `dm_admission`/`dm_allowed` still decouples DMs. Documented in the leg + agents.md ACL section; flagged to operator at session level; carry to debrief.
- 2 design-review cycles used (protocol max). Cycle-2 issues were concrete fixes (not design-direction disputes) → incorporated without a 3rd cycle; Phase 2d code review backstops. Leg → `ready`. Proceeding to implementation.

### L3 design (Bug E)
- Designed leg 03 (exclude category-type channels at `enumerate_discoverable_entities`). Deviation from the flight DD: flight sketched a positive allowlist `type IN (text,voice,thread)`; leg excludes ONLY `category`. Design review confirmed the deviation correct — ACL channel-match (`_acl.py:614-627`) is type-agnostic, so voice/forum/announcement/stage ids are legitimately matchable; a positive allowlist would be a NEW bug dropping text-postable channels. Categories are the sole never-matchable type.
- Design review (Developer, cycle 1): **approve with changes**. HIGH: the planned browser "defense-in-depth" test is unachievable — `discoverable-dropdown.js` renders every channel with NO `metadata.type` awareness, so a `page.route()`-stubbed test is circular, and adding JS filtering would contradict the operator's substrate-only Bug E decision. **Resolution**: dropped the browser test with rationale (backend unit test calling `enumerate` directly is the real coverage); strengthened the unit test to assert BOTH exclusion (category) AND inclusion (text/voice/forum/announcement), pinning the deviation. MEDIUM: stale absolute count (2800) → relative "prior+1" (working-tree baseline drifts L1–L5). LOW: `str(channel.type) == "category"` not `isinstance` (stub fakes carry string `.type`). All incorporated; corrections not a new design direction → no cycle 2. Leg → `ready`.

### L4 design (L4-enhancement test backfill) — uncovered a stale-fixture regression + flight-baseline error
- Designed leg 04 (backfill `populateInferenceModelDropdown` coverage). Design review (Developer, cycle 1): **needs rework** — found that **3 of the 5 existing tests in `test_flow_studio_connector_inference_provider_row.py` already FAIL on the branch**: `test_inference_rows_visible_when_always_listen_on`, `test_inference_provider_and_model_save_roundtrip`, `test_inference_provider_clear_saves_null`. They target `connector-config-inference-model-input`, but the F13 L4-enhancement (commit `ed78d0e`) shipped the model field as a `<select>` (`-model-select`) and `.fill()`s a `<select>` — impossible. The enhancement landed a regression in its own (untested) test file. **These are stale TEST fixtures, not production bugs** → repairing them is L4's purpose.
- **Re-scoped L4**: (1) fix the 3 stale tests (input→select, `.select_option()`, model value from the seeded provider's served models), (2) add 3-5 new flows. Net file state: 8-10 passing / 0 failing. "Report don't fix" narrowed to PRODUCTION defects only; test-fixture repair authorized.
- **⚠ Flight browser-baseline is WRONG (affects L5)**: flight.md:76/125/212 claim "454 passed / 2 pre-existing-main failures" naming only L5's two tests (`test_tablist_renders_with_three_tabs`, `test_studio_section_round_trip_preserves_agent_selection`). These 3 inference-file failures are NOT in that inventory — the true main browser-failure set is ≥5, not 2. **Disposition**: L4 owns these 3 (its file); L5 stays scoped to its 2 named. The flight's "460" arithmetic is stale → counts recorded as actuals, reconciled at Phase 2d. L5 design must NOT assume a 2-failure baseline.
- Harness facts confirmed by review (mock providers self-serve `config["models"]` via `api.py:3576`; model testid `connector-config-inference-model-select`; race-guard precedent `test_flow_studio_openrouter_picker.py:177-207`). Changes are verified corrections, fully specified → no cycle 2. Leg → `ready`.

### Test-infra remediation (operator "just fix it") — surfaced + closed mid-flight
- Operator flagged "significant delays." FD probe: container pegged 100% CPU by an orphaned `pytest -m browser` run (PPID 0, 10+ min) holding chromium + a stack of `<defunct>` zombies. Root causes: (1) no init-reaper (PID 1 = `uvicorn --reload`); (2) `docker exec ... pytest` doesn't propagate client-death so interrupted runs orphan unbounded. Killed the orphan (100%→0.5%). Built `scripts/run-tests.sh` (setsid process-group + watchdog group-SIGKILL + EXIT-trap; correct exit codes) and repointed Makefile targets; all subsequent F14 agents run tests via it. A follow-up watchdog-reap bug (the watchdog `sleep` lingered after normal completion, reparented to init, hanging piped invocations) was fixed by putting the watchdog under its own `setsid` + group-killing it. Verified: no lingering live sleep, piped calls don't hang, timeout path still 137+clean. Residue: 1 inert `<defunct>` zombie per timeout-kill (harmless; tini-as-PID-1 noted as the rebuild-gated follow-up). Full anomaly + resolution in the Anomalies section.

### L5 design (pre-existing browser failures) — diagnosed: both TEST-UPDATE
- Design-review/diagnosis (Developer): ran both target tests via the now-clean wrapper. BOTH are TEST-UPDATE, no product regression; both trace to the SAME commit `93c4120` (flight/06 #65) — byproducts of one feature landing, deferred 4 flights.
  - **Test 1** (`test_tablist_renders_with_three_tabs`): a 5th "Connectors" tab was legitimately added (`agent-editor.js:104-106`); `to_have_count(4)` → actual 5. Fix: count→5, add `tab-connectors` aria-selected assertion, rename `..._with_five_tabs`, fix docstring.
  - **Test 2** (`test_studio_section_round_trip_preserves_agent_selection`): contract DELIBERATELY inverted (`studio.js:444-452`, M10 F6 L7 HAT) — leaving Agents clears selection → return lands on the tile grid (editor hidden). Test encodes the OLD contract. Fix: invert is-hidden assertions, DROP the misleading line-279 `editor-title` check (passes only on stale DOM), rewrite docstring. Sibling `test_studio_editor_hidden_on_knowledge_section` already asserts the new contract + passes.
- Both trivial (~15 / ~30-45 min); no >3-day divert. Sibling scan: fix is exactly these 2, not broader. Dispositions baked into the leg ACs. **Note for leg-04 owner (low)**: test-2's docstring tied the old behavior to leg-04's dirty-state confirm; diagnosis confirms the confirm now fires on the clear path (`studio.js:441-481` `_confirmLeaveImpl`), so the inversion doesn't break it — flagged for awareness, not a blocker. Leg → `ready`.

### L7 design (ephemeral polish) — core mechanism corrected (Webhook.partial → from_state)
- Designed leg 07 (the substrate ephemeral leg). Design review (Developer, cycle 1): **needs rework** — the leg's core followup mechanism was WRONG, verified live against discord.py 2.4.0:
  - `discord.Webhook.partial(app_id, token).send(ephemeral=True)` raises `ValueError: ephemeral messages can only be sent from application webhooks` (partial = type=1 incoming; ephemeral requires type=3 application).
  - **Correct mechanism**: `discord.Webhook.from_state(data={"id": int(app_id), "type": 3, "token": token}, state=self._client._connection).send(content, ephemeral=True)` — verified to honor ephemeral. `app_id = self._client.application_id` (real attr, populated at READY; the leg's cited `:1160/:1344` doctor-path was wrong).
  - My "keep envelope.raw serializable" rationale was moot — `_build_slash_envelope:229` already stashes a live `raw["discord_interaction"]` (unused). Architecture decision: still carry a token STRING on `OutboundTarget` (keeps it connector-agnostic); the `from_state` + private `self._client._connection` coupling lives inside the Discord adapter (acceptable; commented).
- Other confirmations folded in: matrix tests at the `DiscordClient.send` level (harness `_make_discord_client_with_sdk` at `test_connectors_discord.py:1639`; patch `from_state`, no real network); `OutboundTarget`/`CommandResponse` are frozen+slots, all call sites kwarg → trailing-default fields safe (agent-reply path unaffected); ephemeral followup forces `wait=True` → returns a Message so `SendResult` works; token-expiry = `NotFound` (404) + `HTTPException` 401; `application_id` None (pre-READY) → channel-send + WARNING (near-impossible since slash requires READY; accepted leak-on-pre-READY); `talk_to`/`talk-to` spelling coupling noted. All incorporated into the leg; mechanism now verified-correct → no cycle 2. Leg → `ready`.

### L8 design (AdmissionContext refactor) — approve with changes
- Designed leg 08 (refactor `admits_inbound` to take a frozen `AdmissionContext`, Option B). Grounded in post-L1 reality: exactly 2 production call sites (`_routing.py:177`, `_commands.py:124`), both with identical inline `is_dm`(via L1's `envelope_is_dm`)/`guild_id`/`member_roles` derivation → L8 folds it into `AdmissionContext.from_envelope(envelope, plugin)`. Wrapper = option (b) (`test_connectors_acl.py:37` builds the context internally; ~30+ flat-shape call sites unchanged). `admits_outbound` untouched (two-symmetric-paths; no envelope).
- Design review (Developer, cycle 1): **approve with changes**. All 6 validation points CONFIRMED: only 2 production callers + the wrapper (no missed callers, no re-exports); no test bypasses the wrapper (only `test_connectors_acl.py` imports the real fn, aliased, used solely in the wrapper); `from_envelope(envelope, plugin)` has `plugin` in scope at both sites; `admits_outbound` deliberately `del`s guild_id/member_roles (no envelope) → correctly no-change; the `_admits_inbound_dm`/`_admits_inbound_guild` split takes individual fields so unpack-then-delegate is a no-op on them. MEDIUM catch incorporated: the wrapper must CONSUME `is_dm`/`guild_id`/`member_roles` into the context and STOP forwarding them as `**kwargs` (else `TypeError` against the new `(account, agent_acl, ctx)` signature); preserve the DM-context `guild_id=None` (no DEFAULT_TEST_GUILD_ID default when `is_dm=True`). Added as an explicit AC. No cycle 2 (tightening, not redesign). Leg → `ready`.

### L9 design (behavior-test spec) — re-scoped to single Chrome-MCP spec after the infeasibility finding
- The flight DD's 2-specs-plus-2nd-bot-driver was found infeasible (see Anomalies); operator chose Chrome MCP. Operator further confirmed: **one dedicated Discord user is logged into the Chrome-MCP browser session**, so the spec drives Discord-side tasks (slash invocations + observation) through that single user's web client.
- L9 re-scoped to author ONE spec, `tests/behavior/discord-slash-end-to-end.md` (browser apparatus; `Cache:` cold): 6 command rows + an autocomplete-probe precondition row. Ephemeral verified via the web client's "Only you can see this" rendered treatment on the 3 self-only commands (screenshot/a11y evidence) — single-user is sufficient (the label IS the observable). The spec implicitly exercises L1 (`/agents` lists agents, not "No agents available"), L2 (commands appear in `/` autocomplete → slash-sync fired), and L7 (ephemeral). Dropped: `slash-command-ephemeral-routing.md` + `discord_slash_driver.py` (L7 backend unit tests own the 4-cell matrix + token-expiry; `flags & 64` not DOM-observable). L10 now runs 3 behavior tests + manual walk.
- **FD decision on review cadence**: L9 is spec-only (no code/driver). The feasibility question a design review would surface is already resolved (FD investigation + operator decision), and the format is grounded against `discord-engagement.md` + the ARTIFACTS spec format. So I skip a separate pre-authoring design review (authoring a spec IS its design); the authored spec is reviewed at Phase 2d alongside all changes. Leg → `ready`.

### Phase 2d — review + commit
- **Reviewer**: Sonnet (chosen given the batch complexity — never Opus, per protocol). Signaled `[HANDOFF:confirmed]` with 2 non-blocking items: (1) an N806 lint (a local variable not in `snake_case`) in `the_one/connectors/_discord.py`; (2) a stale `defer`-behavior description at `the_one/agents.md:797`. **Both fixed pre-commit.**
- **Full suites green** (true baseline): backend **2811 passed / 4 skipped / 0 failures**; browser **460 passed / 35 skipped / 0 failures**. This 460/35 is the *correct* browser baseline — the flight's planning-time "454 passed / 2 pre-existing failures" figure was wrong: L4 found + fixed 3 stale inference-fixture failures and L5 fixed the 2 deferred browser failures, and the real collected count was higher than the flight assumed.
- **Disposition**: L1-L9 committed in this Phase-2d ceremony. The flight does **not** land — L10 (operator-driven HAT + behavior-test runs against real Discord) gates flight landing; `flight.md` status stays `in-flight`, the L10 checklist entry stays unchecked.
- **For the debrief**: note (a) the **N806 rename** in `_discord.py` (a lint the leg agent missed, caught at review); (b) the **test-infra remediation** — `scripts/run-tests.sh`, the bounded/self-cleaning process-group test runner committed mid-flight (see Anomalies → "Orphaned browser-test run") + the Makefile retarget; and (c) the planning-baseline error on browser-test counts.

---

## Reconnaissance Report

Per `/flight` Phase 1b. Source artifacts:
- F13 debrief at `flights/13-audit-log-inspector-and-connector-inference-config/flight-debrief.md` (action items + 4-bug cluster + L4-enhancement test debt + 2 pre-existing browser failures)
- F13 L6 leg `flights/13-.../legs/06-slash-command-hat-against-real-discord.md` (cluster Known Issue with diagnostic evidence per bug)
- M11 mission outline F14 entry (`mission.md:131-134` pre-debrief shape; reshaped post-F13 to subsume slash-HAT closure)
- M11 Known Issues "F13 L6 HAT findings — ACL / slash-sync surface cluster" entry

Walked each item against current code (post-F13 commit `ed78d0e` on main):

| Item | Classification | Evidence | Recommendation |
|------|----------------|----------|----------------|
| Bug A — uvicorn `--reload` keeps stale Pydantic class objects | `confirmed-live` | Verified during F13 L6 diagnostic walk; uvicorn re-imports modules on file change but in-memory class objects (with frozen Pydantic validator schemas) from prior imports persist in the running worker | L6 leg: `CLAUDE.md` note + "restart container after Pydantic edits" discipline. NOT a code fix. |
| Bug B — `_sync_slash_commands` reads top-level `config.guilds`; UI writes `allowlist.guilds` | `confirmed-live` | `the_one/connectors/_discord.py:247` reads `account.config.get("guilds")`; validator at `db/models.py:443` validates `allowlist["guilds"]`; UI at `connector-editor.js:4332` reads `allowlist.guilds`; `_routing.py` consumes from `allowlist`. Top-level `config.guilds` is the lone hold-out. | L2 leg: single-site fix at `_discord.py:247`. Phase 5c grep gate enforces 0 orphan top-level readers post-L2. agents.md L4 narrative (line ~797) updated in lockstep. |
| Bug C — Discord plugin not passing `member_roles` to `admits_inbound` | `already-satisfied` (FALSE POSITIVE at F13 diagnosis) | `the_one/connectors/_discord.py:207-228` extracts `member_roles` from `interaction.user.roles` and embeds in `envelope.raw["member_roles"]`; `the_one/connectors/_routing.py:178-188` reads `envelope.raw.get("member_roles", [])` and forwards to `admits_inbound`. The F13 L6 diagnostic Python test bypassed the dispatcher's plumbing layer and called `admits_inbound` directly without `member_roles` — spurious denial in the test, not in production. | RETIRE from cluster. Document the false-positive lineage in this flight's recon report for traceability. |
| Bug D — `_commands.py:_permitted_agents` missing kwargs to `admits_inbound` | `confirmed-live` | `the_one/connectors/_commands.py:108` passes `(account, agent_acl, envelope.peer_id, envelope.channel_id)` — only 4 positional args; the `is_dm`/`guild_id`/`member_roles` kwargs use their defaults (False/None/None). The dispatcher's `_routing.py:180` call site DOES pass all 5; commands' secondary admission re-check doesn't. Latent since F7 (commit `dfff8ac`, 2026-05-19); unmasked by F12's structured-tuple allowlist requiring `guild_id` to match channel entries. Verified live via F13 L6 HAT. | L1 leg: ~5-line code change at `_commands.py:108` + 2-3 regression tests under `TestPermittedAgentsAgainstStructuredAllowlist` exercising `_handle_agents` against a structured-tuple allowlist. |
| Bug E — Channel allowlist accepts category ids | `confirmed-live` | F13 L6 diagnostic evidence: `enumerate_discoverable_entities` returns channels with `metadata.type` of `category`, `text`, `voice`, `text` (subchannel), etc. UI picker doesn't filter; operator picks a category id (e.g. `1447766673108107396` = `#Text Channels` category); ACL channel-match silently denies because messages come from child text-channels with their own ids. | L3 leg: filter `type=category` at the Discord plugin's `enumerate_discoverable_entities` site (substrate-side; cleanest separation per operator's selected Option). +1 unit test + 1 browser picker-filter test. |
| L4-enhancement unit-test backfill | `confirmed-live` | `grep -n "populateInferenceModelDropdown\|wireInferenceModelRepopulate" tests/browser/test_flow_studio_connector_inference_provider_row.py` returns 0 hits. The F13 L4-enhancement (model dropdown + race-guard + `(custom)` fallback) shipped with zero unit-test coverage; the behavior test caught the recapture-regression that unit tests missed | L4 leg: 3-5 browser tests covering Ollama + provider-switch + custom-fallback + no-provider placeholder + GUI-clear-saves-null. |
| 2 pre-existing browser failures | `confirmed-live` | `tests/browser/test_flow_agent_tabs.py::test_tablist_renders_with_three_tabs` (test name says "three" but asserts 4 tabs — likely name-vs-assert drift) and `tests/browser/test_flow_studio_navigation.py::test_studio_section_round_trip_preserves_agent_selection` (state preservation) exist at the cited locations. Both have persisted across F10 → F13 unaddressed (4-flight deferral). | L5 leg: investigate-at-implementation with flexible fix-or-update-assertions disposition. Divert clause if either surfaces >3-day work. |

**Classification summary**: 6 confirmed-live items drive F14 scope (10 legs total); 1 item (Bug C) retired as false positive.

**Recon adjustments to F13 debrief framing**:
- F13 debrief Recommendation #1 enumerated "4 substrate-touching bugs"; F14 recon retired Bug C as a false positive (Discord plugin + dispatcher do plumb `member_roles` correctly — the F13 L6 isolated Python test omitted it). Cluster narrows from 4 to 3 real bugs.
- The slash-command HAT closure scope EXPANDS at F14 vs F13's verify-only stance: F14 L7 adds ephemeral-where-appropriate polish for the 3 self-only commands (`/whoami`, `/agents`, `/help`) per operator's planning decision, closing M11 criterion #10's "ephemeral where appropriate" sub-bullet that F13 L6 deferred. Autocomplete polish stays deferred to a later flight.
- The L8 `admits_inbound` refactor uses Option B (`AdmissionContext` dataclass) per operator's selection after Phase 4 context. Option C (no-defaults) would prevent Bug D's exact failure mode but doesn't structurally prevent the broader signature-widening hazard; Option A (full envelope) couples ACL to envelope shape.
- The L9 behavior-test uses `discord.py`-as-second-bot driver (NOT Chrome MCP) per the M11 mission outline's explicit allowance ("Chrome MCP or `discord.py`-as-second-bot driver, resolved at flight planning"). Slash invocations against Discord's REST API are programmatic without browser automation, sidestepping web-client bot-detection.

---

## Pulled-Forward F13 Debrief Methodology Lessons

Per F13 debrief recommendations + F11/F12 carry-forwards still relevant:

1. **Grep-gate-scope-is-a-design-decision** (F11 lesson #1, F12 + F13 application): F14 L2 + L8 verification gates enumerate allowed residue explicitly.
2. **Phase 5c architect cycle for grep-gate flights** (F11 lesson #2): F14 L2 + L8 specify a Phase 5c architect cycle that runs the literal grep against the codebase pre-implementation.
3. **Mechanical-prereq-leg-before-semantic-changes** (F11 L1, F12 L1, F13 L1 pattern): F14 doesn't have a pure mechanical-prereq leg, but L1 (Bug D fix) lands BEFORE L8 (AdmissionContext refactor) so the refactor lands against a corrected call-site rather than threading two changes through `_commands.py:108` in opposite directions.
4. **Operator-local-state preservation discipline** (`docker-compose.yml` stays unstaged): preserved as F14 implementation guidance across all 10 legs.
5. **Consumer-callsite-audit-on-public-api-signature-widening** (F13 debrief codification): L8's AdmissionContext refactor is the structural implementation of the convention's process recommendation — instead of relying on architect-cycle grep discipline, the type system enforces it.
6. **Diagnostic-surface-co-ships-with-decision-path** (F13 debrief codification): F14 doesn't introduce new dispatcher paths but L7's ephemeral-polish surfaces extend an existing observable (the slash command response shape); no new audit-log surface needed.
7. **Detail-endpoint-attaches-rich-payload** (F13 debrief codification): F14 doesn't add new REST surfaces.
8. **In-memory-snapshot-from-db-restore** (F13 debrief codification): F14 doesn't add new in-memory snapshot fields.
9. **Provider-aware-model-dropdown-with-custom-fallback** (F13 debrief codification): L4 backfills test coverage for the F13 L4-enhancement that established this pattern.
10. **Two-symmetric-paths-in-acl** (F11 lesson #5, F12 L2 codification): F14 L8's AdmissionContext refactor touches `admits_inbound`; recon verified `admits_outbound` doesn't have the kwargs-omitted hazard (no F12-shape requirement), so the symmetric path is satisfied trivially. L8 still verifies both at recon.

---

## Leg Progress

### L1 — Bug D fix: `_permitted_agents` threads full envelope context (landed)

**Changes:**
- `the_one/connectors/_acl.py` — added shared `envelope_is_dm(envelope, plugin)` helper beside `_default_not_dm` (honors the plugin's `is_dm` hook via the getattr-sentinel; `plugin is None` falls back to `_default_not_dm`). Added to `__all__`.
- `the_one/connectors/_routing.py` — `_agent_admits` now calls `envelope_is_dm` instead of the inline `if plugin is None / getattr(...)` block; dropped the `_default_not_dm` import (only a docstring reference remains). Behavior identical — routing tests pass unchanged.
- `the_one/connectors/_inbound.py` — `dispatch_inbound` command `context` dict now carries `"plugin": plugin` (resolved upstream at `:347`).
- `the_one/connectors/_commands.py` — `_permitted_agents` reads `context["plugin"]`, derives `is_dm` via `envelope_is_dm`, reads `guild_id = envelope.raw.get("guild_id")` and `member_roles = envelope.raw.get("member_roles", [])`, and passes all three to `admits_inbound`. Docstring updated.
- `tests/test_connectors_commands.py` — `_build_context` gains a `plugin` param defaulting to `None` and carries `"plugin"` in the context dict (the design-review high-severity catch — prevents `KeyError` across the 25+ existing command tests on the new `context["plugin"]` read). Added `TestPermittedAgentsAgainstStructuredAllowlist` (2 tests) plus a `_StubPluginWithIsDm` stub that *implements* `is_dm`. Tests drive `_handle_agents` against a structured-tuple `allowlist.channels` `(DEFAULT_TEST_GUILD_ID, "ch-1")`: (a) matching envelope `guild_id` → agent listed; (b) absent `guild_id` → "No agents available for this conversation."

**Tests:** scoped run `tests/test_connectors_commands.py` + `tests/test_connectors_routing.py` = 96 passed. Full suite: **2798 passed / 4 skipped / 0 errors** (baseline 2796 + 2). Target met.

**Notes:**
- The two new test allowlists required `"peers": []` alongside `"channels"` — the `Connector` Pydantic validator requires both keys (`{'peers', 'channels'}` minimum). `peers: []` is unrestricted at account scope per the per-axis tri-state semantic.
- The duplicated `getattr(plugin, "is_dm", ...)` expression is now gone from both call sites — verified via `git grep envelope_is_dm`.
- Per the leg's Note for L8: the `envelope_is_dm` helper is the natural home for L8's `AdmissionContext.from_envelope` `is_dm` derivation. Also re-confirmed during this leg: `_acl.py:_default_not_dm` returns a plain `False` (flight.md:96's `not envelope.raw.get("is_dm", False)` description is wrong — L8's author should not be misled).
- No anomalies. One pre-existing benign warning during the full-suite run (`aiosqlite` "Event loop is closed" `PytestUnhandledThreadExceptionWarning`) present at baseline too — not introduced by this leg.

### L2 — Bug B fix: unify guild scoping onto `allowlist.guilds` (landed)

Scope-pivot rationale (false-premise escalation → operator "unify" decision) and the test-infra remediation are in the FD Notes / Anomalies above — not duplicated here.

**Migration version:** schema `CURRENT_VERSION` 26 → **27** (`the_one/db/schema.py:15`). The v27 data migration row-rewrites every `connectors.config`: `cfg.pop("guilds", None)`, and when the popped list is non-empty folds it into `allowlist.guilds` via order-preserving dedup-union (existing allowlist ids first, then folded ids); empty/None top-level `guilds` is dropped silently (no gratuitous empty allowlist); `INSERT OR IGNORE schema_version (27)` last (idempotent + partial-apply safe). A fresh allowlist created during the fold carries the validator-required empty `peers`/`channels` axes so the row still passes `Connector.model_validate`.

**Changes:**
- `the_one/db/schema.py` — `CURRENT_VERSION` bump + v27 migration (above).
- `the_one/connectors/_discord.py` — `_sync_slash_commands` reads `account.config.get("allowlist", {}).get("guilds") or []`; docstring (`:237`) + connect-path doc-comment (`:1000`) describe the unified `account.config["allowlist"]["guilds"]` path; skip-on-blank INFO behavior preserved.
- `the_one/interfaces/web/static/js/areas/studio/connector-form-discord.js` — "Scope to servers" text field (`data-testid="discord-guilds-list"`) retired at all six sites (read/render/write-back/`snapshot()`/dirty-listener/`reservedConfigKeys`); `_splitGuildsList` deleted. The `intents.guilds` "Server info" gateway-intent checkbox (`data-field="intent-guilds"`) is untouched — post-edit grep confirms `discord-guilds-list` gone AND `intent-guilds` present.
- `the_one/interfaces/web/api.py` — redundant top-level `config.guilds` validator block (`:1088-1116`) removed; the `allowlist.guilds` guard in `db/models.py` remains the guild-list validator.
- `the_one/agents.md` — M10 F8 L9 CommandHandler slash-sync narrative updated to the `account.config["allowlist"]["guilds"]` read path; coupling note added to the L8 4-axis ACL section (non-empty `allowlist.guilds` now ALSO scopes slash-registration; DM independence preserved via the orthogonal `dm_admission` axis).
- `tests/test_db_migration.py` — `assert CURRENT_VERSION == 26` → `27` (message refreshed to M11 F14 L02); added 3 v27 tests (`test_v27_fresh_db_shape`, `test_v27_idempotent_on_rerun`, `test_v27_folds_top_level_guilds_into_allowlist` — covers union/overlap-dedup, only-top→allowlist-created, empty-top-dropped, none-untouched, plus `Connector.model_validate` round-trip proving no top-level `guilds` survives). Bare `await conn.close()` teardown (latent aiosqlite pattern not widened).
- `tests/test_connectors_discord.py` — 3 slash-sync tests migrated to `config={"allowlist": {"guilds": [...], "peers": [], "channels": []}}`; `:2951` renamed to `test_connect_int_coerces_string_guild_id_for_sync` and switched to string id `["987654321"]` (int-id support intentionally dropped under the `list[str]` validator).
- `tests/test_api_connector_config_validation.py` — top-level `config.guilds` rejection-case tests retired (consequence of the api.py validator removal); doc-comment updated to point at the `allowlist.guilds` guard.
- `tests/browser/test_flow_studio_connector_discord_form.py` — `test_guilds_add_saves` removed (field no longer exists); `test_additional_config_hides_reserved_keys` drops the top-level-`guilds` fixture line and the `"guilds" not in keys` assert (`guilds` no longer reserved).

**Grep gate:** `git grep -nE 'config\.get\("guilds"\)|config\["guilds"\]|"guilds"\s*in\s*cfg|config\.guilds\b' the_one/` → **0 hits** (the `.pop("guilds", None)` idiom + variable name `config` keep the gate clean).

**Tests (via `scripts/run-tests.sh`):**
- Backend full suite: **2799 passed / 4 skipped / 0 errors** (517 deselected) — delta +1 vs L1's 2798 baseline (3 discord tests migrated in-place + 1 api-validation happy-path consolidated; several top-level-guilds rejection tests removed; 3 new v27 migration tests added; the CURRENT_VERSION assert edited in place).
- Browser (scoped to `test_flow_studio_connector_discord_form.py`): **10 passed** (was 12 — `test_guilds_add_saves` removed; `test_additional_config_hides_reserved_keys` rewritten).
- No orphan `pytest`/`chromium`/`playwright` processes after either run (confirmed empty per the wrapper convention).

**Notes:**
- Pre-existing benign `aiosqlite` "Event loop is closed" warning still present (baseline; not introduced here).
- Non-empty `allowlist.guilds` coupling (admission + DM-deny + slash-registration fused) documented in agents.md ACL section per the cycle-2 FYI; carry to debrief.

### L3 — Bug E fix: exclude category channels from discoverable-entities (landed)

Substrate-only fix per the operator's Bug E decision (design-review correction recorded in FD Notes above: the flight's sketched browser "defense-in-depth" test was dropped as unachievable/circular — `discoverable-dropdown.js` has no `metadata.type` awareness and adding it would contradict the substrate-only choice; the backend unit test is the coverage).

**Changes:**
- `the_one/connectors/_discord.py` — `enumerate_discoverable_entities` channels loop skips `str(channel.type) == "category"` (string form, matching the existing `metadata={"type": str(channel.type)}` tagging; NOT `isinstance`, since the unit-test fakes carry a plain string `.type`) with a comment citing Bug E (F14 L3). Docstring `channels` bullet (`:1779-1785`) rewritten: dropped the false "filter at the render layer" framing (no such filter exists) and the claim that `CategoryChannel` is yielded; now states categories are excluded at the enumerate site and every other message-bearing `GuildChannel` type is returned with its `metadata["type"]` token.
- `tests/test_connectors_discord.py` — +1 test `test_discord_plugin_enumerate_excludes_category_channels`: a mixed-type guild (`category` + `text` + `voice` + `forum` + `news`) → asserts the category id is ABSENT and the text/voice/forum/announcement ids are PRESENT (`channel_ids == {text,voice,forum,news}`). The inclusion half pins the exclude-only-category deviation against a future over-broad positive allowlist. Reuses `_StubDiscoverableChannel`/`_StubDiscoverableGuild`.

**Category-excluded + others-retained confirmed:** the new test asserts both directions; targeted `test_connectors_discord.py` run = 84 passed.

**Grep gate:** `git grep -n "category" the_one/connectors/_discord.py` → exclusion present at the loop (`:1838 if str(channel.type) == "category": continue`) plus the docstring rationale.

**Tests (via `scripts/run-tests.sh`):**
- Targeted `tests/test_connectors_discord.py -x --timeout 30 -q`: **84 passed**.
- Backend full suite (`-m 'not browser and not live and not pixel' -q`): **2800 passed / 4 skipped / 0 errors** (517 deselected) — **+1 vs L2's 2799** (the one new enumerate test; no migrations or removals this leg).
- No orphan `pytest`/`chromium`/`playwright` processes after the run (wrapper convention).

**Notes:**
- No JS change, no browser test (substrate-only design — see FD L3-design notes).
- Pre-existing benign `aiosqlite` "Event loop is closed" teardown warning still present (baseline; not introduced here).

---

### L4 — L4-enhancement model-dropdown test backfill (landed)

Test-only leg. NO production JS/backend change (the "report don't fix" constraint held — no production defect surfaced; both the race-guard cancel and the `(custom)` fallback behaved as documented under live test).

**Before/after (this one file, via the bounded wrapper):**
- Before: `tests/browser/test_flow_studio_connector_inference_provider_row.py` = **2 passed / 3 failed** (confirmed by a baseline run on the branch).
- After: **10 passed / 0 failed** (= 3 repaired + 2 already-green + 5 new). 0 orphaned chromium/pytest/playwright after the run.

**Part 1 — 3 stale-fixture repairs** (the failures were stale TEST fixtures, not production bugs): `test_inference_rows_visible_when_always_listen_on`, `test_inference_provider_and_model_save_roundtrip`, `test_inference_provider_clear_saves_null`. All three referenced the non-existent `connector-config-inference-model-input`; the F13 L4-enhancement (commit `ed78d0e`) renders the model field as a `<select>` at `connector-config-inference-model-select` (connector-editor.js:556-558). Repairs: `input`→`select` testid, `.fill()`→`.select_option()`, and the round-trip/clear tests now seed the mock provider with `config={"models":[...]}` so the model value the test selects (and the persisted value the clear test expects) is one the provider's `/models` endpoint actually serves — otherwise the `<option>` wouldn't exist.

**Part 2 — 5 new model-dropdown tests** (all 5 documented flows, top of the 3-5 target):
- (a) populate — provider `config={"models":["m1","m2"]}` → model select gets both options.
- (b) race-guard — see rigor note below.
- (c) custom-fallback (the highest-value live-only coverage) — connector persists `inference_model` NOT in the provider's list → model select carries a selected `"{value} (custom)"` option (connector-editor.js:3420-3423). Confirmed rendered live.
- (d) no-provider placeholder — provider unset → disabled "Select a provider first" option, select value empty.
- (e) GUI-clear synthetic change (F13 recapture regression target) — pristine mount Save disabled; `select_option(value="")` on the provider fires the synthetic change (connector-editor.js:3385) → Save re-enables, model select resets to empty.

**Models-endpoint approach:** no `page.route()` stub for (a)/(c)/(d)/(e) — a `type=="mock"` provider's `GET /api/providers/{id}/models` self-serves `config["models"]` directly (api.py:3576-3586), so seeding `seed_mock_provider(..., config={"models":[...]})` is sufficient. Matches the existing browser-harness precedent (no invented stubs).

**Race-guard rigor (b):** chose the FULL-rigor mirror of `test_flow_studio_openrouter_picker.py:177-207`, verbatim in shape — `page.route` provider-A's `/models` with `time.sleep(0.6); route.continue_()`, two mock providers with DISJOINT model lists (`alpha-only-*` vs `beta-only-*`), select A (slow fetch in flight) → switch to B mid-flight → `wait_for_timeout(1500)` → assert A's ids are ABSENT and B's PRESENT. The lighter fallback assertion (allowed by the leg's edge-case note) was NOT needed — the deterministic 0.6s-route timing was stable and the AbortController + `_connectorModelsActiveProviderId` equality guard (connector-editor.js:3362-3401) cancelled the stale fetch cleanly. No real `sleep` in test code (only inside the route handler, per precedent).

**Tests (via `scripts/run-tests.sh`):**
- `TEST_TIMEOUT=600 ... -m browser tests/browser/test_flow_studio_connector_inference_provider_row.py -q`: **10 passed** in ~17s.
- Did NOT run the full browser suite (scoped to this one file per leg instruction).
- No orphan `pytest`/`chromium`/`playwright` processes after the run.

**Flight-baseline note (for L5 reconciliation):** these 3 inference-file failures were genuine pre-existing branch failures NOT in flight.md's "454 passed / 2 named pre-existing failures" inventory — L4 owned and cleared them; L5 stays scoped to its 2 named ones. The flight's "460" arithmetic remains stale and is reconciled at Phase 2d.

---

### L5 — pre-existing browser failures: both TEST-UPDATE (landed)

TEST-ONLY leg — edited 2 browser test files; **no product/JS change**. Both failures trace to the SAME root cause, commit `93c4120` (M10 F6, per-agent ACLs / Connectors tab) — byproducts of one feature landing, deferred across 4 flights. Diagnosis (design-review-confirmed) held under implementation; no surprise product issue surfaced, so no `[BLOCKED]`.

**Test 1 — `test_flow_agent_tabs.py::test_tablist_renders_with_three_tabs`**
- **Failure mode:** `to_have_count(4)` failed — actual **5**. A 5th tab **Connectors** (`data-testid="tab-connectors"`) was legitimately added by `93c4120` (`agent-editor.js:104-106`); render order is General / Knowledge / MCPs / Connectors / Built-in Tools.
- **Disposition: TEST-UPDATE** (legit product DOM growth, test stale). Bumped count `4 → 5` + comment; added the `tab-connectors` `aria-selected="false"` assertion (matching the sibling per-tab pattern); renamed `test_tablist_renders_with_three_tabs → test_tablist_renders_with_five_tabs`; rewrote the stale docstring (was "MCPs tab so count is now 4") to describe the 5-tab tablist incl. Connectors.

**Test 2 — `test_flow_studio_navigation.py::test_studio_section_round_trip_preserves_agent_selection`**
- **Failure mode:** `.studio-editor` carried `is-hidden` after the Agents→Knowledge→Agents round-trip. The navigation contract was DELIBERATELY INVERTED by `93c4120` (M10 F6 L7 HAT, `studio.js:444-452`): leaving Agents now clears `_selectedAgent`, so returning lands on the tile grid with the editor hidden. The test still encoded the OLD "editor stays mounted" contract. Sibling `test_studio_editor_hidden_on_knowledge_section` already asserts the new contract and passes — confirms the inversion is intended.
- **Disposition: TEST-UPDATE** (intentional contract inversion, test stale). Inverted the assertions: `.studio-editor` now SHOULD have `studio-editor is-hidden`; `.studio-section-content` should NOT have `is-hidden` (grid visible). DROPPED the `editor-title == agent_name` post-round-trip assertion entirely (it passed only on stale hidden-editor DOM and would assert a misleading observable — not flipped). Renamed `..._preserves_agent_selection → ..._returns_to_agent_listing` and rewrote the docstring to the listing-on-return contract.

**File results:** scoped run via the bounded wrapper (`TEST_TIMEOUT=300 ... -m browser <both files> -q`) → **22 passed, 1 skipped** (both files fully green). Post-run straggler check `ps -eo pid,cmd | grep -iE "chrome-headless|pytest|playwright"` → empty (no orphaned chromium). No other browser tests touched; `docker-compose.yml` untouched.

---

### L6 — Bug A docs: uvicorn/Pydantic stale-schema reload note (landed)

Doc-only leg — edited `CLAUDE.md` `## Local dev with Docker` only. No code, no tests.

**Added** a concise INTERMITTENT-gotcha note under the Docker section: under `uvicorn --reload`, most host edits hot-reload fine, but editing a Pydantic **class definition** (`AgentConfig`, `Connector`, `ChatSession`, provider config models) can leave the worker validating against a stale compiled core schema (a surviving reference to the pre-reload class object). Symptom = a `ValidationError` on a just-added field or a new validator not firing; remedy = `docker compose restart the-one` (targeted) or `make rebuild` (hammer). Used the phrase "compiled core schema bound to the class object" — deliberately NOT "frozen" (verified these models are Pydantic v2 `BaseModel`, none `frozen=True`).

**Corrected** the two now-stale lines (`:37` and `:58` in the pre-edit file) so the section is internally consistent with the COMMITTED compose dev default. Both lines previously asserted host edits never reach the running app / live-reload is never enabled — true only for the image-baked `the-one serve` path (`Dockerfile CMD` → `main.py` `uvicorn.run(...)`, no `--reload`, `COPY`-baked). The committed `docker-compose.yml:18-23` dev command bind-mounts `./the_one:/app/the_one` and runs `uvicorn ... --reload --reload-dir /app/the_one`, so on `docker compose up` host edits DO propagate and hot-reload. Reworded both lines to distinguish the two paths; kept the `make rebuild` guidance intact (still correct for the image/COPY path).

**Verification:** confirmed against the COMMITTED command via `git show HEAD:docker-compose.yml` (`--reload` + `./the_one` bind-mount present), `Dockerfile` CMD `["the-one","serve"]`, and `main.py` `uvicorn.run(app, ...)` (no `--reload`). Confirmed `AgentConfig` (`agent/config.py:157`, `model_config = {"extra": "ignore"}`), `Connector` / `ChatSession` (`db/models.py`) are Pydantic v2 `BaseModel`, none `frozen=True` (the only `frozen` token in models.py is an unrelated `frozenset`). `git diff CLAUDE.md` shows only the doc additions/corrections. Operator-local `docker-compose.yml` modification (2 env vars) left untouched/unstaged per leg instruction; wording based on the committed command.

---

### L7 — slash-command ephemeral polish (landed)

Made `/whoami`, `/agents`, `/help` deliver **ephemerally** (only the invoker sees them); `/talk_to`, `/new`, `/reset` stay channel-visible. Substrate work (interaction-followup plumbing), not a flag flip.

**Mechanism realized via `Webhook.from_state` (NOT `Webhook.partial`) — the design-review correction held.** `DiscordClient.send` (`_discord.py`) now branches at the top: when `target.ephemeral and target.interaction_followup_token and self._client.application_id` it reconstructs an **application** webhook —
```python
discord.Webhook.from_state(
    data={"id": int(application_id), "type": 3, "token": token},
    state=self._client._connection,
)
```
— and `await wh.send(content, ephemeral=True)`, returning `SendResult(platform_message_id=str(sent.id), details={"channel_type": "ephemeral_followup"})`. The `"type": 3` (application) is load-bearing: a type=1 (incoming) webhook — what `Webhook.partial(app_id, token)` builds — raises `ValueError: ephemeral messages can only be sent from application webhooks`, so `partial` is unusable here. `ephemeral=True` forces `wait=True` internally, so `wh.send` returns a `Message` (not `None`) → the `.id` read is safe. The `self._client._connection` private-attr coupling is commented and isolated inside the Discord adapter (which already reaches into `self._client` internals).

**Threading path (token as a plain STRING across the connector-agnostic boundary):**
- `CommandResponse` (`base.py`) gained `ephemeral: bool = False`; the 3 self-only handlers (`_commands.py`) return `ephemeral=True` (both `/agents` return paths), the other 3 keep the default.
- `OutboundTarget` (`base.py`) gained `interaction_followup_token: str | None = None` + `ephemeral: bool = False` (trailing defaults — every existing call site uses kwargs / is unaffected; agent-reply path untouched).
- `_build_slash_envelope` stashes `raw["interaction_followup_token"] = interaction.token` (a string, distinct from the pre-existing unused live `raw["discord_interaction"]`).
- BOTH dispatcher command-outbound sites (`_inbound.py` plugin + builtin) build the `OutboundTarget` with `ephemeral=response.ephemeral, interaction_followup_token=working_envelope.raw.get("interaction_followup_token")`.
- Conditional defer: the slash-body's `interaction.response.defer(ephemeral=…)` is now keyed on the slash command `name` — `True` for `{whoami, agents, help}`, `False` (public ack) for `{talk_to, new, reset}` — eliminating the brief-ephemeral-then-channel flip. The deliberate two-site name-keyed coupling (handler-set ephemeral keyed on PARSED name vs defer-set keyed on SLASH name; they agree because whoami/agents/help spell identically in both vocabularies) is commented at the `_EPHEMERAL_SLASH_NAMES` declaration.

**Token-expiry fallback:** the followup send is wrapped in `except (discord.errors.NotFound, discord.errors.HTTPException)` → on `NotFound` (404) or `HTTPException` with `status == 401` it logs INFO and falls through to the channel ladder with `content = "[ephemeral fallback] " + content`. A non-401 `HTTPException` during the followup re-raises (a genuine send failure, not token-expiry — not masked). `application_id is None` (pre-READY, near-impossible since slash commands aren't invokable until READY) → channel send + WARNING (accepted channel-leak edge, doesn't crash/queue). The existing channel-resolution ladder + its Forbidden/NotFound/429 mapping is unchanged.

**discord.py-idiom notes:** (1) `Webhook.from_state(data=…, state=…)` is the documented constructor for an existing-context webhook; the `data` dict mirrors the REST webhook object shape (`id`/`type`/`token`), and `"type": 3` is `WebhookType.application`. (2) `application_id` is a real `discord.Client` attr populated at READY (not the doctor REST path) — present on `MagicMock(spec=discord.Client)`, so the tests set it explicitly. (3) `ephemeral=True` implies `wait=True`, so no separate `wait=` arg is needed.

**Tests / counts:**
- Per-command ephemeral assertions folded **in place** (0 net-new) into the existing `_commands.py` per-handler tests: whoami / agents (both branches) / help → `ephemeral is True`; talk_to / new / reset → `is False`.
- `tests/test_connectors_discord.py`: **+6** net-new at the `DiscordClient.send` level via the `_make_discord_client_with_sdk` harness — the **4 matrix cells** (`ephemeral ∈ {T,F}` × `token ∈ {present,absent}`: only ephemeral+token fires the followup; the other 3 fire the channel send), patching `discord.Webhook.from_state` with a recorder (NO real network), plus a **NotFound→`[ephemeral fallback]`** unit test and a **pre-READY `application_id=None`→channel** edge test.
- `tests/test_connectors_inbound.py`: **+2** net-new — the thin dispatcher pass-through assertions (both `OutboundTarget` flags threaded from `response.ephemeral` + `raw.get("interaction_followup_token")`), one for the ephemeral `/whoami` path and one for the channel-visible `/new` path.
- **2 existing slash-body tests UPDATED in place** (not net-new): the `_make_interaction` fixture gained a `token` attr (was raising `AttributeError` on the new `interaction.token` read); `test_slash_command_body_dispatches_envelope` flipped its `talk_to` defer assertion to `ephemeral=False` (matching the new conditional public ack) and added a `raw["interaction_followup_token"]` assertion.
- Targeted run (commands + discord + inbound) via the bounded wrapper: **204 passed**.
- **Backend full suite (`-m 'not browser and not live and not pixel' -q`): 2808 passed / 4 skipped / 0 errors** (522 deselected, ~269s).

**COUNT DEVIATION (flag for Phase 2d review):** the leg's acceptance-criteria count line said **prior+4** (its arithmetic tallied only the 4 matrix cells, assuming per-command assertions extend tests in place — which they do). Actual delta is **+8 vs L3's 2800 baseline** (L4–L6 added no backend tests). The extra +4 are all spec-sanctioned by the SAME criterion's prose: the **2 dispatcher pass-through tests are REQUIRED** ("a thin dispatcher assertion that both sites pass the flags through"), the **NotFound→fallback test was "welcome if cheap"**, and the **pre-READY edge test** pins a documented Edge Case. The "+4" was an internal inconsistency in the count line, not an over-test — no tests were padded; per-command assertions were correctly folded in place per the spec rather than added as new functions. Recording the actual count per the "record actuals" instruction.

**OPERATOR-LOCAL STATE:** `docker-compose.yml` untouched.

---

### L8 — admits_inbound → AdmissionContext refactor (landed)

Closed the Bug-D failure mode STRUCTURALLY (option-b per the operator's Phase 4 selection). L1 fixed the one call; L8 makes the whole CLASS impossible.

**Signature change.** `admits_inbound(account, agent_acl, peer_id, channel_id, *, is_dm=False, guild_id=None, member_roles=None)` → `admits_inbound(account, agent_acl, ctx: AdmissionContext)`. A new ACL axis now becomes a new REQUIRED `AdmissionContext` field = a type error at every unmigrated call site (no more silent kwarg-default defaulting).

**`AdmissionContext`** — `@dataclass(frozen=True)` added near the top of `_acl.py` (after imports, before `_default_not_dm`); fields `peer_id: str`, `channel_id: str`, `is_dm: bool`, `guild_id: str | None`, `member_roles: list[str]`; exported via `__all__`. The `from_envelope(cls, envelope, plugin)` classmethod owns the derivation formerly duplicated at both call sites: `is_dm` via the shared `envelope_is_dm(envelope, plugin)` helper (NOT a raw `raw["is_dm"]` read — flight.md:96/161's `_default_not_dm`=`not raw.get("is_dm")` formula is wrong; `_default_not_dm` returns plain `False`, and `from_envelope` reuses the helper per the L1 flight-log note), `guild_id = envelope.raw.get("guild_id")`, `member_roles = envelope.raw.get("member_roles", [])`. `admits_inbound`'s body unpacks the 5 fields from `ctx` and delegates UNCHANGED to the `_admits_inbound_dm`/`_admits_inbound_guild` split (no semantic change vs post-L1). Added `from dataclasses import dataclass`.

**2 production call sites migrated** (both now `admits_inbound(account, agent_acl, AdmissionContext.from_envelope(envelope, plugin))`; inline `is_dm`/`guild_id`/`member_roles` derivation deleted; the now-unused `envelope_is_dm` import dropped, `AdmissionContext` imported in both):
- `_routing.py:_agent_admits` — single call.
- `_commands.py:_permitted_agents` — context built ONCE before the eligible-agents loop (it's agent-independent) and reused per agent.

**Test wrapper = option-b (flat→context adapter).** `tests/test_connectors_acl.py:38` keeps its flat `(account, agent_acl, peer_id, channel_id, **kwargs)` signature; internally applies the existing v24 `agent_acl` translation + the `is_dm`-false→`DEFAULT_TEST_GUILD_ID` default (suppressed under `is_dm=True` so DM-context fixtures keep `guild_id=None`), then CONSUMES `is_dm`/`guild_id`/`member_roles` from kwargs to build the `AdmissionContext` and calls `_admits_inbound_real(account, v24_acl, ctx)`. CRITICAL design-review catch honored: the consumed kwargs are NOT forwarded onward (the new signature would `TypeError`). The ~30+ flat-shape call sites in the file are UNCHANGED.

**+3 `TestAdmissionContextConstruction` tests** — `from_envelope` extracts `is_dm` via the plugin hook (and `plugin=None`→`_default_not_dm`=False fallback, ignoring a raw `is_dm=True`), `guild_id`, and `member_roles` (defaulting `[]` when `raw` lacks the key). Built a minimal `InboundEnvelope` (`platform`/`account_id`/`channel_id`/`thread_id`/`peer_id`/`peer_name`/`text`/`raw`) + a local `_IsDmPlugin` stub.

**`admits_outbound` + its test wrapper UNTOUCHED** (no inbound envelope at outbound time — two-symmetric-paths convention; recon-confirmed; the only diff line referencing it is the `__all__` context).

**Grep gate (Phase 5c)** — `git grep -nE 'admits_inbound\(' the_one/ tests/`: both production sites (`_routing.py:173`, `_commands.py:127`) pass an `AdmissionContext`; ZERO production positional `peer_id, channel_id` sites. The `_acl.py:371` hit is the `def`; `agents.md:515` is historical Bug-D narration (not a call site, left per spec); all `tests/test_connectors_acl.py` flat-shape hits route through the wrapper definition at line 38 — the kwarg signature is allowed residue BY DESIGN (the flat→context adapter).

**Tests / counts:**
- Targeted (acl + routing + commands) via the bounded wrapper: **192 passed** (the ~30+ flat ACL tests green UNCHANGED through the wrapper).
- **Backend full suite (`-m 'not browser and not live and not pixel' -q`): 2811 passed / 4 skipped / 0 errors** (522 deselected, ~256s) — exactly prior+3 (2808→2811). The 3 warnings are pre-existing aiosqlite event-loop-teardown `ResourceWarning`s, unrelated to this leg.

**OPERATOR-LOCAL STATE:** `docker-compose.yml` untouched.

---

### L9 — behavior-test spec authored (single Chrome-MCP slash spec) (landed)

Spec-only leg — authored ONE behavior-test spec; no production code, no driver script, no unit tests.

**Deliverable:** `tests/behavior/discord-slash-end-to-end.md` (status `draft`, `Created: 2026-06-01`, `Last Run: never`, `Cache:` cold/default). Browser apparatus (Discord web client rendered state via chrome-devtools MCP; screenshot + a11y primary, DOM supplementary). 7 step rows: a leading autocomplete-probe precondition row (type `/`, confirm the six commands appear in Discord autocomplete → proves L2 slash-sync fired) + one row per command. The three self-only commands (`/whoami`, `/agents`, `/help`) assert the user-perceivable "Only you can see this" ephemeral treatment (reply absent from channel history); the three channel-affecting commands (`/talk_to`, `/new`, `/reset`) assert a channel-visible reply that persists. `/agents` pins the L1 Bug D fix (≥1 agent listed, NOT "No agents available"); `/talk_to`/`/new`/`/reset` ordered last so the session resets don't break an earlier row. Pure browser frame — no `[mixed-frame]` markers. `agent` variant parameterizes the `/talk_to` target (operator supplies a known-attached, ACL-permitted agent at run time).

**Scope pivot (per the operator decision — see Anomalies "L9/L10 verification approach is INFEASIBLE"):** the flight DD's TWO specs + shared `discord.py` 2nd-bot driver were dropped. A bot cannot invoke another bot's slash commands and cannot observe another user's ephemeral followup, so the 2nd-bot wire-level approach is impossible; the operator redirected to the mission's preferred Chrome-MCP surface driving the single dedicated logged-in Discord user's web client. DROPPED: `slash-command-ephemeral-routing.md` (its 4-cell `ephemeral × token` substrate matrix + token-expiry are L7-unit-tested at the `DiscordClient.send` level and aren't DOM-observable) and `discord_slash_driver.py`. The single Chrome-MCP spec implicitly exercises L1 (`/agents` lists agents), L2 (commands appear in `/` autocomplete), and L7 (ephemeral treatment) end-to-end against real Discord — criterion #10's closure surface.

**Verification:** spec parses as the ARTIFACTS.md "Behavior Test — Spec" format (Intent / Preconditions / Observables Required / Steps / Out of Scope + header block); every Expected Result references the browser observable and is user-perceivable; autocomplete-probe precondition row present; no production code / driver / unit tests added. The spec RUNS at L10 via `/behavior-test discord-slash-end-to-end` (not in this leg). L10 now runs 3 behavior tests (2 F13 regression specs + this one) + the manual walkthrough.

**OPERATOR-LOCAL STATE:** `docker-compose.yml` untouched.

---

## Decisions

(empty — populated during execution; planning-time decisions live in flight.md Design Decisions)

---

## Deviations

(empty — populated during execution)

---

## Anomalies

### L9/L10 verification approach (2nd-bot slash driver) is INFEASIBLE — escalated
**Observed**: at L9 design, FD verified the flight DD's core L9 mechanism ("a `discord.py` 2nd bot invokes the operator's bot's 6 slash commands and reads the response `flags & 64` ephemeral bit") is impossible:
- `discord.Client` has NO command/interaction-invoke methods (`dir` → `[]`); discord.py provides no way for a bot to invoke another bot's slash command.
- Discord's API has no bot-facing "create interaction" endpoint — slash invocations are USER-initiated; bots only receive interactions. An ephemeral followup is delivered only to the invoking user, so a 2nd bot couldn't read `flags & 64` even if it could invoke.
- The repo's existing `discord-engagement.md` drives Discord via **Chrome MCP** (operator logged into the web client) and explicitly defers slash to "a future spec" — the 2nd-bot-driver pattern was never real here.
**Severity**: blocking for L9/L10 as the flight DD specified them (the `discord-slash-end-to-end.md` + `slash-command-ephemeral-routing.md` specs both assume the 2nd-bot driver + wire-level `flags & 64`).
**Context**: M11 constraints designated Chrome MCP as the PREFERRED HAT surface, with the `discord.py`-2nd-bot as a fallback "if web-client bot-detection makes browser automation unreliable." F14 Phase-4 chose the fallback — but on the false premise that a bot can invoke slash commands. The premise is wrong; the correct default is the mission's preferred Chrome MCP surface.
**Resolution**: escalated to operator (the L9 driver choice was operator-directed at Phase 4). **Operator chose Chrome MCP web-client driver** (the mission's preferred surface, the proven `discord-engagement.md` pattern). L9 re-scoped to a SINGLE Chrome-MCP behavior-test spec (`discord-slash-end-to-end.md`) driving the operator's logged-in Discord web client through the 6 commands; ephemeral verified via the web client's "Only you can see this" treatment (NOT wire `flags & 64`). The 2nd spec (`slash-command-ephemeral-routing.md`, wire-level 4-cell matrix + token-expiry) and the `discord_slash_driver.py` 2nd-bot driver are DROPPED — the 4-cell `(ephemeral × token)` routing + the `NotFound`→fallback are already covered by L7's backend unit tests (`DiscordClient.send` level), and `flags & 64` / real token-expiry aren't observable via the DOM. L10 consequently runs 3 behavior tests (2 F13 regression + the new Chrome-MCP slash spec) + the manual walkthrough, not 4. Criterion #11's slash-portion still ships as a re-runnable artifact (the Chrome-MCP spec).

### Orphaned browser-test run pegging container CPU (operator-flagged "significant delays")
**Observed**: mid-L2, operator flagged test delays. FD probe found the `the-one` container at 100% CPU while idle, caused by an orphaned `pytest -m browser` run (PID 16627, PPID 0, 10+ min elapsed) holding a playwright/chromium + test-uvicorn (port 56057) subtree, plus a pile of `<defunct>` chrome-headless zombies.
**Severity**: degraded (no data loss; slows every concurrent test run — the L1 Developer's suite run took ~13 min vs the ~243s baseline, consistent with CPU contention).
**Root cause** (two compounding): (1) container has NO init/reaper — PID 1 is `uvicorn --reload` (`entrypoint.sh` does `exec "$@"`, no tini), so orphaned chromium children become unreaped zombies; (2) `docker exec ... pytest` does not propagate exec-client death to the in-container process, so when a test-launching agent is interrupted, pytest + chromium keep running unbounded. The full `-m browser` suite (~288 browser tests) legitimately runs ~10 min, so an orphaned one burns CPU a long time.
**Immediate resolution**: FD killed the orphaned tree (PID 16627 + playwright driver 26060 + test-uvicorn 26226 + pkill of stragglers); container CPU 100% → 0.5%, mem 984MiB → 616MiB. Verified backend tests snappy again (8 tests / 0.03s).
**Durable fix** (operator-directed "just fix it" — remediation task #12, DONE): committed `scripts/run-tests.sh` — runs `python -m pytest "$@"` in its own process group via `setsid`, with a watchdog that SIGKILLs the entire group (`kill -KILL -$pgid`, reaping chromium grandchildren) at `TEST_TIMEOUT` (default 1200s) and an EXIT-trap doing the same defensively. Propagates pytest's real exit code. Makefile `test`/`test-unit`/`test-browser`/`test-pixel` repointed at `bash /app/scripts/run-tests.sh …` (markers preserved; `_ensure-playwright` prereq kept). No container rebuild needed.
**FD verification** (independent of the implementing agent, whose report truncated): (a) normal unit run → completes, **0 stragglers**, CPU→0.6%; (b) forced `TEST_TIMEOUT=2` on a real chromium-launching browser test → wrapper logged "TIMEOUT after 2s — killed process group", **0 stragglers incl. chromium**, CPU→0.5% (proves group-kill reaps chromium); (c) exit codes correct — timeout=137, pass=0, real pytest codes propagated (no-collect=5). 
**Convention for remainder of F14**: all subsequent leg agents invoke tests via the wrapper (`docker exec the-one bash /app/scripts/run-tests.sh <pytest args>`) or `make test-unit`/`test-browser`, NOT raw `docker exec the-one pytest`. The wrapper's own code review folds into Phase 2d. **Follow-up (not blocking)**: add `tini` as PID 1 (Dockerfile) to reap the current `<defunct>` zombie pile + future orphans — needs a container rebuild; zombies are CPU/mem-free so deferred.

---

## Session Notes

### L10 HAT outcome (2026-06-01) — criterion #10 NOT closed; flight does NOT land
- **Execution-mode note**: this session lost agent-continuation (`SendMessage`) — verified by registry search + a probe agent that ran to completion rather than awaiting continuation. Behavior tests ran in one-shot-Executor + one-shot-Validator mode (Witnessed separation preserved; no per-step intervention). Operator-approved.
- **Test 1 `connector-inference-provider-config-roundtrip`: PASS 8/8** (run log `runs/2026-06-01-16-55-14.md`). Regression gate green — F14's `_commands`/`_inbound`/`_acl`/`base` changes did not regress the F13 inference-config round-trip. Cosmetic side-finding: provider display name "Antrhopic" is a typo of "Anthropic".
- **Test 2 `audit-log-inspector-renders-routing-entries`: DEFERRED (not run).** Seeding a stable session blocked by the live environment: real sessions drift under live bot traffic (a `stepped` entry appended mid-seed), and a freshly-created message-less session did not persist `session_metadata` via PUT (an F13-L5/repo quirk: `repo.update` left `session_metadata=None` despite a 200). Neither is an F14 regression. Given test 1 already confirmed the substrate and the panel-render code is untouched by F14, deferred to a fast-follow.
- **Test 3 `discord-slash-end-to-end`: FAIL 0/7** (run log `runs/2026-06-01-17-08-00.md`). **Root cause: the bot's slash commands are NOT registered as Discord application commands** — `/` autocomplete shows none of the six; all invocations fell through to the text-prefix `on_message` path (channel-visible, never ephemeral). Most likely the bot lacks the `applications.commands` OAuth scope → `tree.sync` Forbidden (consistent with F13 L6 also only ever seeing channel-visible text-prefix replies; app logs not in `docker logs` so unconfirmed directly). L2's read is correct (`allowlist.guilds` = the test guild) — the blocker is downstream of L2.
  - **CONFIRMED working**: L1 Bug D fix — `/agents` lists "Sonos Agent" with channel-history before/after evidence (May 31 "No agents available" → Jun 1 lists the agent). The flight's headline cluster fix is verified against real Discord.
  - **NEW bugs surfaced (text-prefix path, pre-existing)**: (1) `/talk_to` underscore unrecognized (only `/talk-to` hyphen parsed); (2) `/talk-to <multi-word agent>` parses only the first token ("Sonos Agent" → "Sonos"). Likely moot under real slash invocation (single named arg) but live while slash registration is broken. (The L7 design review pre-flagged the talk_to/talk-to spelling split.)
- **Disposition (initial)**: criterion #10 stays OPEN; flight stays `in-flight`; PR #83 stays draft.

### L10 slash HAT RE-RUN (2026-06-01-17-42-40) after operator re-invited bot with `applications.commands` + restarted — STILL FAIL 0/7
- Slash commands STILL absent from Discord autocomplete after the re-invite + container restart. So the missing-scope hypothesis did NOT pan out (or the scope still isn't effectively granted). `/agents` again lists "Sonos Agent" (L1 fix still confirmed); `/talk_to` underscore still no-reply; everything still text-prefix + channel-visible.
- **Code read (FD)**: the connect path DOES add all 6 commands to the `CommandTree` (`_discord.py:1064-1067`) and DOES call `_sync_slash_commands(tree, account)` after READY (`:1147`); post-L2 it reads `account.config.allowlist.guilds`. So the registration logic is present and correct on its face.
- **Observability gap blocking diagnosis**: `docker logs the-one` captures ONLY uvicorn lines + WS open/close — NONE of the connector's `logger.info/warning` output (no gateway/READY/slash-sync/Forbidden lines at all). So I cannot see whether `_sync_slash_commands` read an empty guild list at connect time vs `tree.sync` raised Forbidden vs the connector connected with a stale account config. App-level logging is not reaching stdout/stderr that docker captures — itself a gap that hampers any slash-sync diagnosis.
- **Hypotheses still open** (need instrumentation to distinguish): (a) bot still lacks effective `applications.commands` authorization (re-invite didn't take); (b) `_sync_slash_commands` reads empty guilds at connect because the `account` object the connect path uses differs from the API-visible config (stale/cached account, or connect happens before the config is in the expected shape); (c) `tree.sync` raises silently. The operator is checking Discord → Server Settings → Integrations → GleepGlorp → Commands to narrow registered-but-hidden vs not-registered.
- **Assessment**: this is a genuine defect investigation in the connect→slash-sync path (or bot authorization), NOT a quick fix, and is hampered by the app-log-capture gap. Criterion #10 cannot close tonight. The flight's committed code (L1–L9) remains correct + suites green + L1 verified live. Recommending criterion #10 (slash HAT) be carried to a focused follow-up: (1) fix app-log capture so the connector's connect/sync logs are visible; (2) instrument/diagnose why slash-sync registers nothing; (3) fold in the 2 `/talk_to` text-prefix bugs. Flight stays `in-flight`; PR #83 stays draft pending operator direction.

### L11 Bug F leg progress (2026-06-01) — `copy_global_to` fix landed

**Root cause (diagnosed + confirmed live at L10 HAT):** commands are registered globally via `tree.command(name=..., description=...)` (no `guild=`), so they live in discord.py's global registry. But `_sync_slash_commands` called `tree.sync(guild=discord.Object(id=...))` without first copying the global commands into the per-guild bucket. `tree.sync(guild=g)` PUTs only the per-guild bucket for `g`, which starts empty — so Discord received 0 commands ("This application has no commands"). The standalone in-container diagnostic confirmed: `tree.sync(guild=...)` on a global-only tree returns 0 commands; adding `tree.copy_global_to(guild=...)` first → all 6 registered.

**Fix applied (`_discord.py`):** in `_sync_slash_commands`'s per-guild loop, build `guild_obj = discord.Object(id=int(guild_id))` once per iteration, then call `tree.copy_global_to(guild=guild_obj)` BEFORE `await tree.sync(guild=guild_obj)`. Both calls are wrapped by the existing per-guild `try/except` (Forbidden/HTTPException → WARNING + continue). Docstring updated to explain the global→guild copy requirement.

**Regression test added (`tests/test_connectors_discord.py`):** `test_sync_copies_global_commands_into_each_guild_before_sync` — drives a full `plugin.connect()` with two configured guilds and asserts: (a) each guild's bucket in `_StubCommandTree.guild_buckets` is populated with all 6 commands (would KeyError pre-fix); (b) `call_log` ordering confirms `copy_global_to` precedes `sync` per guild. `_StubCommandTree` extended with `copy_global_to` (populates `guild_buckets`) and a `call_log` list recording all `("copy"|"sync", guild_obj)` tuples in order. Existing tests unchanged (stub is backward-compatible; `sync` still records `sync_calls` and `call_log`).

**Test counts:** discord module: 91 passed (was 90, +1). Full backend: 2812 passed, 4 skipped (was 2811, +1). 0 errors, 0 orphans.

**Pending (at re-HAT, not this leg):** container restart + Discord autocomplete verification — 6 commands appear in `/` + Server Settings → Integrations lists them. L11 status: `landed`.

### L12 Bug G leg progress (2026-06-01) — `/talk_to` handler-miss + multi-word agent name (landed)

Two `/talk_to`-specific defects, both confirmed live at L10 and pre-flagged at the L7 design review, are fixed. Files touched: `the_one/connectors/_commands.py` and `tests/test_connectors_commands.py` only.

**Fix 1 — handler-key mismatch (Bug G.1, "stuck thinking" cause):** `_dispatch_builtin_command` previously did `handler = _HANDLERS.get(command_name)`. Discord slash names cannot contain hyphens so the slash form is `talk_to` (underscore), but `_HANDLERS` keys on `"talk-to"` (hyphen) — the lookup returned `None` and fell through to `agent.step`, causing the "thinking…" ack to never resolve. Fixed: `handler = _HANDLERS.get(command_name) or _HANDLERS.get(command_name.replace("_", "-"))` — tries the exact key first (no-op for the other 5 commands which have no underscore/hyphen mismatch), then normalises underscore→hyphen. A comment at the lookup site explains the Discord-names-use-underscore / v1-vocab-uses-hyphen split. Unknown commands with an underscore (e.g. `foo_bar`) still return `None` (both lookups miss). The other 5 commands are unaffected.

**Fix 2 — multi-word agent name truncation (Bug G.2):** `_handle_talk_to` previously set `target = args[0]`, so "Sonos Agent" (two tokens after parsing) became "Sonos" → "No such agent or you don't have permission: Sonos". Fixed: `target = " ".join(args)` (the agent slug is the rest of the command line). The empty-args Usage guard (`if not args: return CommandResponse(text="Usage: /talk-to <agent-slug>")`) is kept BEFORE the join. Docstring updated to document the full-join contract and the slash-body re-parse reason for multi-word tokenisation. Single-word names are unaffected (`" ".join(["alice"]) == "alice"`).

**Existing test updated:** `TestHandleTalkTo::test_multiple_args_only_first_consumed` encoded the OLD `args[0]` behavior and would have passed pre-fix / failed post-fix (inverted sense). Updated to `test_multiple_args_joined_as_agent_name`: registers a two-word agent `"alice extra"` and asserts that args `["alice", "extra"]` routes to it (confirming the full-join), keeping the same functional structure.

**Regression tests added:**
- `TestBugGHandlerKeyMismatch` (3 tests): (a) `_dispatch_builtin_command("talk_to", ["alpha"], ctx)` returns a non-None `CommandResponse` and routes correctly — pre-fix: returns `None`; (b) hyphen form `"talk-to"` still resolves (exact-match path unaffected); (c) unknown underscore command `"foo_bar"` still falls through to `None`.
- `TestBugGMultiWordAgentFix` (3 tests): (a) `_handle_talk_to` with `args=["Sonos","Agent"]` and a permitted agent `"Sonos Agent"` returns "Now routing your messages to Sonos Agent." and writes `routing_override="Sonos Agent"` — pre-fix: "No such agent … Sonos"; (b) single-word name still works; (c) a single-token `"Sonos"` is correctly DENIED when only `"Sonos Agent"` is permitted (confirms the pre-fix failure mode is eliminated).

**Test counts:**
- Targeted `tests/test_connectors_commands.py`: **62 passed** (was 50 — +6 new regression tests + the 1 renamed/rewritten existing test; net +6 new functions, the 1 renamed counts as edit-in-place).
- Full backend (`-m 'not browser and not live and not pixel' -q`): **2818 passed, 4 skipped, 0 errors** (522 deselected). Prior: 2812 (L11). Delta: +6. No orphans.
- Pre-existing benign `aiosqlite` "Event loop is closed" warning (`TestSchemaV17`) still present at baseline; not introduced by this leg.

**Grep gate:** `git grep -nE 'replace\("_", "-"\)|" ".join\(args\)' the_one/connectors/_commands.py` → both fixes present at `_commands.py:171` and `_commands.py:300`.

**Pending (at re-HAT, not this leg):** container restart + Discord real-slash verification — `/talk_to Sonos Agent` → channel-visible "Now routing your messages to Sonos Agent." L12 status: `landed`.

### L13 Bug H leg progress (2026-06-01) — `/talk_to` envelope text hyphenation (landed)

**Root cause (Validator source-analysis, confirmed):** Bug G.1's normalization in `_dispatch_builtin_command` was unreachable. `_parse_command` (`_commands.py`) defines `_NAME_TAIL_CHARS = frozenset('abcdefghijklmnopqrstuvwxyz0123456789-')` — underscore is excluded. When `_build_slash_envelope` synthesized `/talk_to Sonos Agent`, `_parse_command` hit the `_` and returned `None` immediately; the dispatcher fell through to `agent.step` (stuck "thinking…") before ever reaching `_dispatch_builtin_command`. The G.1 unit test passed only because it called `_dispatch_builtin_command("talk_to", ...)` directly, bypassing `_parse_command`.

**Primary fix (`the_one/connectors/_discord.py`, `_build_slash_envelope`):** Before synthesizing the envelope `text`, hyphenate the command name: `cmd_text = command_name.replace("_", "-")`. For `talk_to` with `args="Sonos Agent"` the text becomes `/talk-to Sonos Agent` — `_parse_command` yields `("talk-to", ["Sonos", "Agent"])` — `_HANDLERS["talk-to"]` → `_handle_talk_to` runs. The other five v1 commands (`agents`, `whoami`, `new`, `reset`, `help`) have no underscore; the replacement is a no-op for them.

Updated `_build_slash_envelope`'s docstring (previously claimed `/talk_to my-agent` reached the dispatcher unchanged — that was the bug) and the `_SLASH_COMMAND_VOCAB` module-level comment to describe the hyphenation bridge.

**G.1 normalization retained as belt-and-suspenders:** The `_dispatch_builtin_command` normalization (`_HANDLERS.get(command_name.replace("_", "-"))`) is kept but now carries a multi-line comment labeling it as a backstop for hypothetical direct callers. The PRIMARY fix is in `_build_slash_envelope`.

**Regression tests added (`tests/test_connectors_discord.py`):**
- `test_build_slash_envelope_talk_to_hyphenates_command_name`: calls `_build_slash_envelope(command_name="talk_to", args="Sonos Agent", ...)` and asserts (a) `envelope.text == "/talk-to Sonos Agent"` (hyphen) AND (b) `_parse_command(envelope.text)` returns `("talk-to", ["Sonos", "Agent"])` — exercises the real parse path, the G.1 blind spot. Would FAIL pre-fix.
- `test_build_slash_envelope_non_underscore_commands_unchanged`: verifies the other 5 commands still produce correct unhyphenated text and parse cleanly.

**Existing test corrected (`tests/test_connectors_discord.py`):** `test_slash_command_body_dispatches_envelope` previously asserted `envelope.text == "/talk_to my-agent"` — it was encoding the bug. Updated to `"/talk-to my-agent"` with a Bug H comment.

**G.1 test docstrings updated (`tests/test_connectors_commands.py`):** `TestBugGHandlerKeyMismatch` class and `test_talk_to_underscore_routes_to_handler` docstrings updated with a Bug H note clarifying the normalization is now a belt-and-suspenders backstop, not the primary fix, and that coverage must NOT be removed.

**Test counts:**
- Targeted (`tests/test_connectors_discord.py tests/test_connectors_commands.py -x --timeout 30 -q`): **155 passed** (was 153, +2 new).
- Full backend (`-m 'not browser and not live and not pixel' -q`): **2820 passed, 4 skipped, 0 errors** (522 deselected). Prior: 2818 (L12). Delta: +2. No orphans.
- Pre-existing benign `aiosqlite` "Event loop is closed" warning still present at baseline; not introduced by this leg.

**Pending (at re-HAT, not this leg):** container restart + Discord real-slash verification — `/talk_to Sonos Agent` → channel-visible "Now routing your messages to Sonos Agent." L13 status: `landed`.

---

### L10 HAT RESOLVED → criterion #10 CLOSED → flight LANDED (2026-06-01)
- After L11 (Bug F) + L12 (Bug G) + L13 (Bug H) + restarts, the focused `/talk_to` re-verify (run `2026-06-01-19-08-36`) confirmed "Now routing your messages to Sonos Agent." (channel-visible, full multi-word name). **All 6 slash commands pass end-to-end** — `discord-slash-end-to-end` PASS 7/7 (run log `runs/2026-06-01-18-39-11.md`): `/whoami`+`/agents`+`/help` ephemeral; `/talk_to`+`/new`+`/reset` channel-visible; `/agents` lists the agent (L1 Bug D fix, live before/after evidence). Ephemeral-where-appropriate (L7) verified against the real client.
- **HAT value**: caught THREE pre-existing, real-traffic-only slash-registration bugs (F/G/H) that all prior HATs (incl. F13 L6) missed (they used text-prefix). Diagnosed without app-log visibility (a standalone in-container `tree.sync` isolated Bug F + proved the scope works; a Validator source-analysis isolated Bug H's `_parse_command` underscore rejection — which made the L12 G.1 normalization unreachable), fixed, unit-tested, re-verified live.
- **Behavior-test tally**: `connector-inference-provider-config-roundtrip` 8/8 (regression, `2026-06-01-16-55-14`); `discord-slash-end-to-end` 7/7 (new, status `active`); `audit-log-inspector-renders-routing-entries` DEFERRED (live-traffic seeding friction + a freshly-created-session `session_metadata`-not-persisting quirk — both environment, not F14; panel-render code untouched by F14; carried to a fast-follow).
- **Final suites**: backend **2820 passed / 4 skipped / 0 errors**; browser **460 passed / 35 skipped / 0 failures**.
- **Carried to follow-up (F15+/Known Issues)**: (1) `audit-log-inspector` behavior-test re-run after the seeding friction is resolved; (2) app-level connector logging not captured by `docker logs` (observability gap that slowed slash diagnosis) — wire app loggers to stdout; (3) `/help` text shows `/talk-to` (hyphen) vs the `/talk_to` slash name (cosmetic copy); (4) provider display name "Antrhopic" typo (cosmetic); (5) the original F14 "live-traffic multi-user + rate-limiting HAT" framing (superseded by slash-HAT-closure) still owed.
- Criterion #10 `[x]`; criterion #11 `[~]` (slash portion shipped as the re-runnable Chrome-MCP spec). Flight 14 checked off in mission.md. Flight status → `landed`. L11/L12/L13 are post-Phase-2d code changes → committed at flight-land (no amend; new commit).
