# Leg: codify-m10-conventions

**Status**: landed
**Flight**: [Discord Connector-Type Registration + Discord-Shaped Creation Form](../flight.md)

## Objective

Codify the six M10-debrief-recommended conventions in `the_one/agents.md` so subsequent M11 legs (and all future flights) can reference them by name, and restructure the Project Conventions section to distinguish project-wide patterns from mission-specific ones per M10 mission-debrief recommendation #8.

## Context

- **Why now**: M11's Constraints section binds this mission to six conventions (`encryptor-parameter-receive-but-not-consume`, `cross-subsystem-pattern-premise-revalidation`, `prompt-discipline-needs-mechanical-fallback`, `mechanical-fallback-prompt-truth-pairing`, `lifespan-wiring-same-leg-as-installation`, `atomic-leg-pattern`). None of them appear in `the_one/agents.md` today; M11 Known Issue #1 calls them out. Subsequent M11 legs (L2's `atomic-leg-pattern` reference; future flights' premise-revalidation reviews) need named anchors.
- **Source of conventions**: `missions/10-bi-directional-comms-connectors/mission-debrief.md` §§ "What Could Be Improved → Process / Documentation", "Methodology Feedback → `agents.md` Codification", and "Action Items". Five conventions originate from F8 debrief; `atomic-leg-pattern` is the Architect's addition.
- **Scope discipline**: doc-only change. No source modifications. No re-derivation of decisions — operator and Architect already approved these; this leg writes them down.
- **Methodological framing** *(per flight.md L1 note)*: codifying conventions as a leg vs. as a pre-flight artifact is the looser of two valid readings of M11 Known Issue #1; operator preference (Phase-3 interview, 2026-05-21) chose the leg framing to keep all M11 work under flight-log discipline.
- **Prior-art organisational pattern**: the existing `## Project Conventions` section (line ~24 in `the_one/agents.md`) is a flat list of named conventions (`trust-the-runtime`, `canonical-import + convenience-re-export`, `structural-Protocol-satisfaction`, `verbatim-message-equality`, `gated-debug-instrumentation`, `host-side-bench-drift-detection`, `hat-driven-contract-flip-migration-discipline`, `live-read-across-lazy-resolver-boundary`, `container-test-entrypoints-reach-via-make`, `landmark-elements-over-aria-roles`, `function-local-import-to-break-load-cycle`, `optional-plugin-hook-via-getattr-sentinel`, `per-axis-tri-state-override`, `protocol-widening-for-required-capability`). M10 debrief recommendation #8 wants project-wide vs mission-specific distinguished; current file conflates them.

## Inputs

Files that must exist:
- `the_one/agents.md` (target file; existing Project Conventions section to extend)
- `missions/10-bi-directional-comms-connectors/mission-debrief.md` (source for the six conventions)
- `the_one/connectors/_discord.py:DiscordPlugin.connect` (line ~587 — `encryptor` parameter site for citation)
- `the_one/connectors/_pool.py` and the F8 L11 Fix #6 sentinel-wrapper (for `cross-subsystem-pattern-premise-revalidation`)
- `the_one/agent/config.py:_CONNECTOR_TOOL_ENABLED_DIRECTIVE` and `_CONNECTOR_AUTO_RELAY_DIRECTIVE` (lines ~54-93 — for the prompt-discipline / mechanical-fallback pair)
- `the_one/agent/factory.py:set_factory` (line ~168) and `the_one/interfaces/web/app.py` lifespan (line ~88) — for `lifespan-wiring-same-leg-as-installation` citation
- M11 mission file Constraints section (line ~60) — names all six conventions verbatim

## Outputs

State changes after this leg:
- `the_one/agents.md` `## Project Conventions` section restructured into two subsections — "Project-wide" and "Mission-specific (M10)" — preserving every existing convention's content and order within the new grouping
- Six new conventions appended with the same shape as existing entries (definition + applicability boundary + exemplar citation + back-reference to M10 debrief)
- No source code, test, or migration changes

## Acceptance Criteria

- [ ] `the_one/agents.md` `## Project Conventions` section is restructured to distinguish "Project-wide" (cross-mission patterns) from "Mission-specific (M10)" (patterns emerged in this mission that may not yet generalize). Every existing convention is preserved verbatim under the appropriate subsection — no content lost.
- [ ] All six new conventions are added by name, each with: (a) a 2-4 sentence definition; (b) an explicit applicability boundary ("applies when X; does NOT apply when Y"); (c) at least one exemplar citation in the `file:symbol` or `file:line — "snippet"` form per agents.md guidelines; (d) a back-reference to the M10 mission-debrief recommendation or action-item that introduced it.
- [ ] `encryptor-parameter-receive-but-not-consume` is added under "Mission-specific (M10)" — M10-specific shape per M10 debrief Documentation §1.
- [ ] `cross-subsystem-pattern-premise-revalidation` is added under "Project-wide" — explicit per M10 debrief Process §2 ("project-wide, highest leverage").
- [ ] `prompt-discipline-needs-mechanical-fallback` is added under "Project-wide" — explicit per M10 debrief Process §3 ("project-wide; will recur").
- [ ] `mechanical-fallback-prompt-truth-pairing` is added under "Project-wide" — explicit per M10 debrief Documentation §1 (companion to above).
- [ ] `lifespan-wiring-same-leg-as-installation` is added under "Project-wide" — explicit per M10 debrief Process §6 / Documentation §1.
- [ ] `atomic-leg-pattern` is added under "Project-wide" — Architect addition per M10 debrief Documentation §1 ("Pydantic field + migration + repository + ripple-sites in one leg; F4 L5 + F6 L1c are n=2").
- [ ] Each new convention's exemplar citation points at a real symbol or line that exists in the current tree (verified by the implementing agent via `grep` / `Read` before signaling `[HANDOFF:review-needed]`).
- [ ] No source file under `the_one/`, `tests/`, `static/`, or `interfaces/` is modified. The only diff is to `the_one/agents.md`.

## Verification Steps

- `git diff the_one/agents.md` — shows the structural restructure (two subsections) and the six new convention entries; no other source diffs.
- `git status` — should show only `the_one/agents.md` modified plus the leg artifact and `flight-log.md` (no other source touched).
- `grep -n "encryptor-parameter-receive-but-not-consume\|cross-subsystem-pattern-premise-revalidation\|prompt-discipline-needs-mechanical-fallback\|mechanical-fallback-prompt-truth-pairing\|lifespan-wiring-same-leg-as-installation\|atomic-leg-pattern" the_one/agents.md` — every name returns at least one hit.
- For each new convention's exemplar citation, run a `grep` confirming the cited symbol or snippet exists in the current source. Example: `grep -n "encryptor parameter is received to satisfy the F1 Protocol" the_one/connectors/_discord.py` should match the docstring at `_discord.py:DiscordPlugin.connect`.
- Run `pytest --collect-only -q tests/test_agents_md.py 2>/dev/null || true` — no test file exists for this (no tests gate agents.md); the doc-only diff cannot break the test suite. Optionally run `pytest -x --timeout 30 -q` once to confirm the broader suite stays at the M10 F8 baseline.

## Implementation Guidance

1. **Read the M10 mission debrief in full** (`missions/10-bi-directional-comms-connectors/mission-debrief.md`). Specifically:
   - "What Could Be Improved → Process" (§§ 1-4) — sources `cross-subsystem-pattern-premise-revalidation`, `prompt-discipline-needs-mechanical-fallback`, `mechanical-fallback-prompt-truth-pairing` rationale
   - "What Could Be Improved → Documentation" (§1) — sources `encryptor-parameter-receive-but-not-consume`, `atomic-leg-pattern`, and the project-wide-vs-mission-specific distinction
   - "What Could Be Improved → Process" (§6) — sources `lifespan-wiring-same-leg-as-installation`
   - "Methodology Feedback → `agents.md` Codification" (§§ 8, 9) — the canonical six-convention list + the distinction recommendation

2. **Read the current `the_one/agents.md` `## Project Conventions` section** end-to-end. The section runs from the `## Project Conventions` heading through the last existing convention (`protocol-widening-for-required-capability`), ending at the `---` separator that introduces "Subsystem contracts". Note the convention-entry shape: heading (`### \`name\``), 2-5 paragraphs covering definition + applicability boundary + exemplar citations.

3. **Introduce a minimum-diff structural split** so the project-wide vs mission-specific distinction lands without churning every existing entry's heading level or breaking `git blame` on convention bodies:
   - Immediately AFTER the `## Project Conventions` section's introductory paragraph and BEFORE the first existing convention (`trust-the-runtime`), insert an `### Project-wide` subsection marker (a `###` heading; the existing convention entries remain at `###` directly below it — heading levels are NOT demoted, accepting that the markdown renderer will display sibling `### Project-wide` and `### \`trust-the-runtime\`` headings at the same level. The visual hierarchy comes from the marker heading appearing without a following body, immediately followed by the convention entries).
   - AFTER the last existing project-wide entry (`protocol-widening-for-required-capability`) and BEFORE the `---` separator, insert an `### Mission-specific (M10)` subsection marker, then add the single mission-specific convention (`encryptor-parameter-receive-but-not-consume`) as a `### \`name\`` entry beneath it.
   - The remaining five new conventions (`cross-subsystem-pattern-premise-revalidation`, `prompt-discipline-needs-mechanical-fallback`, `mechanical-fallback-prompt-truth-pairing`, `lifespan-wiring-same-leg-as-installation`, `atomic-leg-pattern`) land under the `### Project-wide` subsection, appended after the existing 14 entries in the order listed above (preserving the file's existing convention-ordering principle of "in the order they were codified").
   - **Rationale**: this approach preserves `git blame` on every existing convention body (no heading-level rewrites), produces a small focused diff, and achieves the structural distinction via marker headings rather than nested heading levels. The alternative (demoting all `### \`name\`` to `#### \`name\`` under a `### Project-wide` parent) is rejected because git has no semantic awareness of markdown heading shifts — a level-promotion diff churns 14 lines' blame attribution unnecessarily.

4. **Categorize the conventions**. All 14 existing entries are project-wide patterns observed across multiple flights and missions (M03-M10); leave them in place under `### Project-wide`. Append the five new project-wide conventions per §3 above. Create the `### Mission-specific (M10)` subsection containing only `encryptor-parameter-receive-but-not-consume`.

5. **Add the six new conventions** with the citations and shapes below. Write them in the same voice and shape as existing entries (compare `optional-plugin-hook-via-getattr-sentinel` and `protocol-widening-for-required-capability` for tone).

   **5a. `encryptor-parameter-receive-but-not-consume`** (under "Mission-specific (M10)"):
   - Definition: A plugin Protocol method receives an `Encryptor` parameter but does not call it because the repository's contract already delivers plaintext secrets in `account.secrets[...]`. The parameter is present to satisfy the Protocol signature and to allow future plugins that need encryption-aware paths to opt in, NOT because every call site decrypts.
   - Applicability boundary: applies to any plugin where the repository already performs the encryption boundary crossing (`ConnectorAccount`, `MCPSource`) and hands the plugin already-decrypted secrets. Does NOT apply when the plugin is the encryption boundary itself (e.g., a future plugin that handles per-call ephemeral key derivation).
   - Exemplar citation: `the_one/connectors/_discord.py:DiscordPlugin.connect` — the docstring at line ~596 explicitly states "encryptor parameter is received to satisfy the F1 Protocol but not consumed at this site"; same pattern at `_discord.py:1050+` (`doctor` method).
   - Back-reference: M10 mission-debrief "Documentation §1" (the F8 L11 BOT_TOKEN double-decrypt bug — the spec said `encryptor.decrypt(account.secrets["X"])` but the repository had already decrypted; the convention prevents the recurrence).
   - Tagged "Mission-specific (M10)" because M10 debrief Documentation §1 explicitly calls it "M10-specific shape; project-wide principle" — the project-wide form ("repository contract delivery is part of any Protocol's contract") is captured by `cross-subsystem-pattern-premise-revalidation` below.

   **5b. `cross-subsystem-pattern-premise-revalidation`** (under "Project-wide"):
   - Definition: Every "mirror X" rationale invoked in a design must include an explicit paragraph: "the original design rests on premise P; does P hold here?" Pattern-transfer without premise validation ships defects that survive design review.
   - Applicability boundary: applies to any cross-subsystem pattern reuse where the precedent's premise is implicit. Does NOT apply to local refactors within a subsystem (a single-subsystem change can mirror its own siblings without re-deriving the premise).
   - Exemplar citation: `the_one/connectors/_pool.py` — F1 mirrored `mcp/_pool.py`'s per-agent pool keying without re-validating the gateway-protocol-vs-MCP premise mismatch (gateway protocols are one-IDENTIFY-per-token; per-agent keying is incompatible). The mismatch surfaced at F8 L11 HAT seven flights after the original commit; Fix #6 shipped the sentinel-wrapper `_CONNECTOR_POOL_AGENT_SENTINEL = "__connector__"` at `the_one/connectors/_pool.py:148` and the convenience `connector_acquire(account_id)` at `the_one/connectors/_pool.py:512-530` as a tactical patch (call sites: `tools/connector_send.py:194`, `connectors/_inbound.py:140`). M11 F2 owns the proper refactor to an account-keyed primitive.
   - Back-reference: M10 mission-debrief "Process §2" — "Codify as `agents.md` convention `cross-subsystem-pattern-premise-revalidation`." Also listed in "Action Items → Codify 6 new agents.md Project Conventions."

   **5c. `prompt-discipline-needs-mechanical-fallback`** (under "Project-wide"):
   - Definition: Any agent behavior the system depends on but the LLM controls requires either empirical HAT validation against the production model OR a mechanical dispatcher-side fallback that enforces the behavior without relying on prompt compliance. Decision-only (prompt-only) paths are not production contracts.
   - Applicability boundary: applies to any system-level invariant whose enforcement passes through the LLM (outbound channels, tool-call-mandatory flows, content-filter directives). Does NOT apply to UX-only directives that fail soft if ignored (style guidance, persona instructions).
   - Exemplar citation: `the_one/agent/config.py:_CONNECTOR_TOOL_ENABLED_DIRECTIVE` at lines ~54-67 — the original F4 directive "MUST call the `send_to_platform_channel` tool to deliver your reply." Sonnet 4.7 ignored the directive at F8 L11 HAT (twice, with strengthened versions). F8 L11 Fix #4 shipped the mechanical fallback at `the_one/connectors/_inbound.py:711` — `account.config.get("auto_relay_platform_replies", True)` defaults ON and auto-relays the assistant text via `client.send` regardless of whether the tool was called.
   - Back-reference: M10 mission-debrief "Process §3" — "Codify `prompt-discipline-needs-mechanical-fallback`." Also "Lessons Learned §11" (LLM directive compliance is not a production contract).

   **5d. `mechanical-fallback-prompt-truth-pairing`** (under "Project-wide"):
   - Definition: When a mechanical fallback ships alongside a system-prompt directive (per `prompt-discipline-needs-mechanical-fallback`), the prompt must accurately describe the actual behavior the dispatcher delivers. Lying in the prompt about what auto-runs (e.g., still saying "MUST call tool X" when the dispatcher now auto-relays anyway) confuses LLMs trained for honesty and produces hedging / over-explanation. The directive and the dispatcher's truth ship in the same diff.
   - Applicability boundary: applies whenever a mechanical fallback exists for a behavior the system-prompt also describes. Does NOT apply when the dispatcher honors the original prompt's contract verbatim (no fallback divergence).
   - Exemplar citation: `the_one/agent/config.py:_CONNECTOR_AUTO_RELAY_DIRECTIVE` at lines ~69-84 — F8 L11 Fix #4 shipped the paired directive when auto-relay is ON: "Auto-relay is ON: your plaintext replies in this session ARE automatically delivered to platform peers." The original `_CONNECTOR_TOOL_ENABLED_DIRECTIVE` survives at lines 54-67 for the (currently unreachable but conceptually distinct) "tool-mandatory-no-auto-relay" composition; `compose_system_prompt` at `agent/config.py:96+` selects between them via the `auto_relay: bool` parameter.
   - Back-reference: M10 mission-debrief "Documentation §1" — companion to `prompt-discipline-needs-mechanical-fallback`. Also "Lessons Learned §4" (Auto-relay default-on with a mechanical fallback is the right shape for bot UX).

   **5e. `lifespan-wiring-same-leg-as-installation`** (under "Project-wide"):
   - Definition: Event-handler installation (registering a handler that depends on application-level state) and the lifespan-time call site that triggers it land in the same leg, OR the leg's acceptance criteria include a runtime end-to-end test exercising the installed handler. Installing a handler without wiring the lifespan that fires it leaves the entire code path unreachable in production.
   - Applicability boundary: applies to any event-driven handler (gateway listeners, periodic sweeps, background workers, lifespan-startup callbacks) that depends on application-level dependency injection. Does NOT apply to handlers wired into a synchronous import path that runs at module-load. The pattern is connector-agnostic and applies project-wide to any lifespan-driven handler.
   - Exemplar citation: F8 L4 installed Discord's `on_message` at `the_one/connectors/_discord.py:DiscordPlugin.connect` line ~731 but deferred lifespan-time `pool.acquire(...)` wiring to L11; the entire L4 inbound code path was end-to-end unreachable in production until F8 L11 Fix #3 added the lifespan walk. The canonical wiring shape: `the_one/agent/factory.py:set_factory` at line ~168 (module-level accessor) consumed by `the_one/interfaces/web/app.py` lifespan startup at line ~88 (`_set_module_factory(_state["factory"])`); the gateway listeners call `get_factory()` at dispatch time per the convention codified in agents.md's "Gateway-listener factory access (M10 F8 L4)" subsection.
   - Back-reference: M10 mission-debrief Process §6 — "Add `lifespan-wiring-same-leg-as-installation` to `/leg` and `/flight` design guidance." Also Methodology Feedback §4.

   **5f. `atomic-leg-pattern`** (under "Project-wide"):
   - Definition: When a single contract change touches multiple coordinated sites (Pydantic field + DB migration + repository CRUD + downstream ripple-sites that load or persist the value), all sites land in the same leg. Splitting the contract across legs leaves intermediate commits where one half of the contract exists without the other — the column exists in the schema but the Pydantic model doesn't know to write to it, or the model has the field but the repository drops it on save.
   - Applicability boundary: applies whenever a contract change crosses two or more of {Pydantic schema, DB schema, repository codec, runtime consumer that reads the value}. Does NOT apply to contract-additive changes that are fully optional at every site (e.g., adding a Pydantic field with a default that no existing consumer reads).
   - Exemplar citations (n=2 — pattern is at codification threshold per `function-local-import-to-break-load-cycle` precedent):
     - F4 L5: `AgentConfig.connector_account_ids` field landed alongside schema v17 migration, `AgentConfigRepository` insert/load codec, and `AgentFactory.create` consumer in a single leg. See `the_one/db/_connector_types.py:22` for the migration index "v17 → ``agents.connector_account_ids`` persistence (F4 L5)."
     - F6 L1c: `AgentConfig.connector_acls` field landed alongside schema v18 migration, `AgentConfigRepository` codec, and `_acl.admits_inbound` consumer in a single leg. See `the_one/db/_connector_types.py:22` for the migration index "v18 → ``agents.connector_acls`` persistence (F6 L1c)."
   - Back-reference: M10 mission-debrief "Documentation §1 (Architect addition)" — "`atomic-leg-pattern` (Pydantic field + migration + repository + ripple-sites in one leg; F4 L5 + F6 L1c are n=2)." Also "Methodology Feedback §8."

6. **Cross-link existing references**. M11 mission.md Constraints (line ~60) names all six conventions. After codification, M11 legs L2-L6 can reference the conventions by name without re-defining them. No edit to M11 artifacts is required here — they already reference the names.

7. **Do NOT modify any other file**. The agents.md edit is the only diff this leg produces. Do not touch source code, tests, README, CLAUDE.md, or any flight/mission artifact. The flight-log.md update is appended at leg-completion under "Leg Progress" (see Post-Completion Checklist below).

## Edge Cases

- **Existing convention with overlapping shape**: `hat-driven-contract-flip-migration-discipline` (already in agents.md) shares some shape with `mechanical-fallback-prompt-truth-pairing` (both about HAT-driven mid-mission contract changes). Keep them distinct — the existing convention governs schema/contract flips at HAT; the new one governs prompt/dispatcher pair synchronization. Do not merge.
- **Convention name collisions**: Verify each of the six new convention names is unique in agents.md before adding (`grep -n "name-of-convention"` should return zero hits prior to the new edit). The implementing agent confirms before writing.
- **Subsection ordering**: Place "Project-wide" first (longer, contains the existing 14 + 5 new), "Mission-specific (M10)" second (shorter, contains the 1 new entry). Future missions extending the file add their own `### Mission-specific (M{NN})` subsection per the same pattern.
- **Diff-size concern**: Option A (single-level promotion of every existing `###` to `####`) produces a large mechanical diff. This is acceptable — it's a one-time structural improvement and `git blame` will still walk through to the original `###` commit per Git's rename-detection on heading hierarchy. Reviewers may prefer Option B if the diff is judged too noisy.

## Files Affected

- `the_one/agents.md` — `## Project Conventions` section restructured; six new conventions added per §5 above.
- `missions/11-discord-connector-depth/flights/01-discord-connector-type-and-creation-form/flight-log.md` — Leg Progress entry appended at leg-completion.
- `missions/11-discord-connector-depth/flights/01-discord-connector-type-and-creation-form/legs/01-codify-m10-conventions.md` — status updates only (planning → ready → in-flight → completed); this leg artifact itself is otherwise immutable once `in-flight`.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All acceptance criteria verified (eight items above)
- [ ] No source code, test, migration, or static asset modified — `git diff --name-only` shows only `the_one/agents.md` plus the two M11 leg/flight-log artifacts
- [ ] Each new convention's exemplar citation grepped against current code and confirmed live
- [ ] Update flight-log.md with leg progress entry (Started / Completed timestamps, Changes Made summary, Notes on any decisions)
- [ ] Set this leg's status to `completed` (in this file's header)
- [ ] Check off this leg in flight.md (the `codify-m10-conventions` entry under In-Flight Legs)
- [ ] Per agentic-workflow v2 protocol: do NOT commit this leg in isolation — the Flight Director runs a single code review + commit after L6 lands. Mark status `landed` (not `completed`) at signal time; the commit step transitions to `completed`.

## Citation Audit

Citations verified at leg design time (2026-05-21):

- `the_one/connectors/_discord.py:DiscordPlugin.connect` — verified by `grep -n "encryptor parameter is received to satisfy the F1 Protocol"` at lines 596 and 1077 (two sites: `connect` and `doctor`); both carry the docstring substring verbatim.
- `the_one/agent/config.py:_CONNECTOR_TOOL_ENABLED_DIRECTIVE` and `_CONNECTOR_AUTO_RELAY_DIRECTIVE` — verified at lines 54-67 and 69-84 respectively; both module-level constants exist; the `compose_system_prompt` function at line 96 selects between them via the `auto_relay: bool` parameter (default True).
- `the_one/connectors/_inbound.py` auto-relay site — verified at lines 687, 711-714 (`auto_relay = account.config.get("auto_relay_platform_replies", True); if auto_relay: ...`).
- `the_one/agent/factory.py:set_factory` and `the_one/interfaces/web/app.py` lifespan — verified at `factory.py:168` (`def set_factory(factory: "AgentFactory | None") -> None:`) and `app.py:88` (`_set_module_factory(_state["factory"])`).
- `the_one/db/_connector_types.py` migration index docstring — verified to carry the "v17 → ``agents.connector_account_ids`` persistence (F4 L5); v18 → ``agents.connector_acls`` persistence (F6 L1c)" substring in the module docstring block.
- `the_one/connectors/_pool.py` F8 L11 Fix #6 sentinel-wrapper — verified: `_CONNECTOR_POOL_AGENT_SENTINEL = "__connector__"` at line 148, the `connector_acquire(account_id)` convenience function at lines 512-530, and call sites at `tools/connector_send.py:194` and `connectors/_inbound.py:140`.

Six citation clusters verified live against current code. No drift.
