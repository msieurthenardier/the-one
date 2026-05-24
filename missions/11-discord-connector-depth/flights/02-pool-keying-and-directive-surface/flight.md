# Flight: Pool-Keying Refactor + Per-Account System-Prompt Directive Surface

**Status**: completed
**Mission**: [Discord Connector Depth & Robustness](../../mission.md)

## Contributing to Criteria

- [x] The lifecycle pool keying for connector accounts is refactored from M10 F8's sentinel-wrapper (`acquire("__connector__", account_id)`) to an account-keyed primitive at the connector layer; the per-agent-keyed pool stays as MCP-only territory; the API surface no longer presents `pool_acquire(agent_name, account_id)` as a footgun to connector authors; the M10 debrief's "F1 pool keying needs proper refactor" critical action item is closed.
- [x] The system-prompt directive that the connector layer injects into a connector-attached agent's effective system prompt is operator-editable per connector account, with a per-account override surface in the Discord connector detail page; the default directive is visible in the same surface so the operator understands what the agent runs under without needing to read source; the M10 debrief's "Three hard-coded constants in agent/config.py:54-93" critical action item is closed.

---

## Pre-Flight

### Objective

F2 closes the two M10 F8 debrief critical action items in one flight by landing two substrate-touching refactors that gate the more visible UX work in subsequent flights. The pool-keying refactor replaces F8 L11 Fix #6's sentinel-wrapper (`acquire("__connector__", account_id)`) with a clean two-primitive surface on `connectors/_pool.py` — `agent_acquire(agent, account)` for MCP-style per-agent pools (used by the F6 resolver pattern), `account_acquire(account)` for connector-style account-keyed pools (one entry per Discord account, regardless of how many agents are attached); `_CONNECTOR_POOL_AGENT_SENTINEL` is DELETED and the bare `acquire()` is no longer exported. The per-account directive surface adds `account.config["system_prompt_directive"]: str | None` as an APPEND-mode override (operator's text gets stuck onto the end of whichever hardcoded default fires per `(connector_attached, send_tool_enabled, auto_relay)` state) and ships a Studio General-tab section that shows the operator's text-area plus three read-only `<details>` disclosures rendering the verbatim defaults so the operator sees what their text composes with. The `mechanical-fallback-prompt-truth-pairing` convention (L1-codified in F1) binds: replacing the default would let the operator overwrite the substrate's MUST-call-tool / auto-relay-truth contract; APPEND is the only safe mode. F2 also folds in three F1 debrief minor action items that share the studio surface (`MASKED_SENTINEL` shared constant; `_resolveAccountFromContainer` hash-parse → `data-account-id` attribute) and one F1 deferred-item (lift `the_one/connectors/_discord.py:_probe_gateway_connect` hardcoded intents to `account.config["intents"]` reads with the same fallback shape F1 L2 shipped at `DiscordPlugin.connect`). F2's first leg codifies two F1 debrief conventions (`optional-registry-entry-hook`, `registry-dispatch-create-mode-AC`) so legs 2-5 can reference them by name.

### Open Questions

*Planning-time open questions resolved at the Phase 4 crew interview (2026-05-21). Resolutions promoted to Design Decisions below.*

### Design Decisions

**Pool-keying refactor — two-primitive split + clean break** *(resolved at crew interview)*:
- Export two primitives from `connectors/_pool.py`: `agent_acquire(agent_name: str, account_id: str) -> ConnectorClient` (rename of the existing `acquire`); `account_acquire(account_id: str) -> ConnectorClient` (rename of the existing `connector_acquire`). Both use ONE internal storage dict (`_entries: dict[tuple[str, str], _RegistryEntry]`) with composite keys; the second tuple slot carries the account ID, the first slot is either the agent name (MCP-style) OR a fixed module-level sentinel (NEW name: `_ACCOUNT_POOL_AGENT_SLOT`, the `__connector__` literal value is reused so existing warm entries persist across deployment — but the sentinel is internal-only, never exported).
- `_CONNECTOR_POOL_AGENT_SENTINEL` is DELETED from the module namespace. Anyone importing it gets `ImportError` — clean break per operator decision. `connector_acquire` is also removed; the bare `acquire` symbol is RENAMED to `agent_acquire` at the export boundary — no shim, no deprecation.
- **In-tree consumers updated lockstep** (verified at design review — 6 production sites + 4 test files; architect cycle 1 found `interfaces/web/app.py:lifespan` was missed in the planning spec's initial 5-site count):
  - Production: `tools/connector_send.py:SendToPlatformChannelTool.execute` (uses `connector_acquire`); `connectors/_inbound.py:dispatch_inbound` (4 sites: pool-acquire imports + 3 call sites in step-10 routing + auto-relay + system-outbound); `interfaces/web/app.py:lifespan` warm-up (uses `connector_acquire`). All migrate to `account_acquire`.
  - Tests: `tests/test_connectors_pool.py` (multi-line import group at the top); `tests/test_connectors_e2e.py` (two import groups); `tests/test_db_api.py` (7 sites — line numbers will drift; grep `from the_one.connectors._pool import acquire` at impl time); docstring sweep in `tests/test_connectors_inbound.py`, `tests/test_connector_send_tool.py`, `tests/test_lifespan.py:228 comment`; cross-references in `the_one/connectors/README.md`, `the_one/connectors/base.py:cross-reference docstring`, `the_one/connectors/_session.py:docstring`, `the_one/agent/_context.py:docstring`. The doc-comment scrub at `the_one/agents.md:_CONNECTOR_POOL_AGENT_SENTINEL citation` (lifted in F1 L1, currently quotes the sentinel as exemplar code) — L2 updates the citation to reflect post-refactor state OR leaves it as a historical-context reference per L1's call (resolve at L2 design).
- Per `atomic-leg-pattern` (L1-codified): rename + call-site updates + tests + docstring sweep in one leg.
- Eviction, encryption-rotation, and the reaper loop walk the single composite-key dict uniformly; no behavior change from the operator's view.
- **`cross-subsystem-pattern-premise-revalidation` (L1-codified F1) check** *(applied at design review per F2 methodology pass)*: the original F1 pool inherited the MCP-style per-agent keying without re-validating whether gateway-protocol connectors fit. Premise re-walk: MCP's per-agent keying serves the F6 resolver pattern that legitimately produces different credentials per agent; gateway connectors (Discord, Slack Socket Mode) are one-IDENTIFY-per-token by physical necessity, so per-agent keying is incompatible. The two-primitive split preserves both shapes — MCP keeps `agent_acquire` for its `(agent, source)` axis; connectors get `account_acquire` for the single-account-shared axis. Documented in the F2 L2 leg artifact's Design Decisions when L2 is designed.
- **Test seam for HAT inspection** (per architect suggestion): L2 adds a `_keys_for_test() -> list[tuple[str, str]]` helper that returns the current composite-key set. Used by L6 HAT verification step 8 to assert ONE pool entry handles two agents on one Discord account.
- **Rationale**: clean break eliminates the footgun. The M10 F8 debrief's "F1 pool keying needs proper refactor" recommendation is specifically about removing the sentinel-wrapper from the public API surface; deprecation paths preserve the footgun in service of test-seam stability, which is not what the operator wants.
- **Trade-off**: any out-of-tree code importing `acquire`/`connector_acquire`/`_CONNECTOR_POOL_AGENT_SENTINEL` breaks. Operator confirmed clean break is the right call (single-user local tool; no external consumers).

**Per-account system-prompt directive — APPEND mode** *(resolved at crew interview)*:
- New field `account.config["system_prompt_directive"]: str | None` (optional; defaults to None). When set, the operator's text is APPENDED after whichever hardcoded default `compose_system_prompt` selects for the active `(connector_attached, send_tool_enabled, auto_relay)` triple. The hardcoded defaults at `agent/config.py:_CONNECTOR_TOOL_ENABLED_DIRECTIVE / _CONNECTOR_AUTO_RELAY_DIRECTIVE / _CONNECTOR_TOOL_DISABLED_DIRECTIVE` (the three module-level string constants) are UNCHANGED — F2 doesn't edit their text.
- `compose_system_prompt` (`agent/config.py:compose_system_prompt`) gains a 4th keyword parameter `operator_directive: str | None = None`; when truthy, appended to `parts` after the selected default and BEFORE the persona separator. **The default value MUST be `None`** so existing callers (notably the WS handler's prompt-equivalence checks at `agent/config.py:get_system_prompt` and the non-connector edit-form callers per the F4-invariant docstring) produce byte-identical output to today's compose; the new param is purely additive.
- `AgentFactory.create()` (`the_one/agent/factory.py:AgentFactory.create — compose_system_prompt call`) extends the per-attached-account iteration (the same loop currently used to derive `auto_relay`) to ALSO collect `system_prompt_directive` from each attached connector account. Drops None entries; joins remaining directives with `\n\n` in `sorted(account_ids)` order; passes the joined string as `operator_directive`. **Architect cycle 1 fix**: the current `for account_id in config.connector_account_ids` loop iterates persisted list order, NOT alphabetical. L3 explicitly uses `sorted(config.connector_account_ids)` for directive collection — this is a deliberate divergence from the existing `auto_relay`-aggregation iteration shape (which keeps list-order because its first-opt-out short-circuit semantics are order-sensitive but tolerable for the rare multi-account case). Documented as an L3 Design Decision with rationale at L3 design time.
- L2 (F1)'s API validator `_validate_connector_account_config` (Discord branch) extends to accept the optional `system_prompt_directive` key — must be string if present; no length cap at the validator (the LLM provider's context limits are the real bound; substrate-side caps would be premature).
- **Stability rationale**: `sorted()` on Python `str` is lexicographic-by-Unicode-codepoint, deterministic, Timsort-stable, locale-independent. Identical orderings across all current CPython 3.x runtimes; safe for prompt-cache stability.
- **Rationale**: APPEND mode honors `mechanical-fallback-prompt-truth-pairing` (L1-codified). Replacing the default would let the operator overwrite the substrate's MUST-call-tool / auto-relay-truth contract — exactly the prompt-discipline failure mode the convention warns against. The operator's text adds shape to the agent (persona, formatting preferences, peer-engagement guidance) without overriding the substrate's behavioral contract.
- **Trade-off**: operator cannot fully replace the default (e.g., to ship an agent that NEVER mentions auto-relay even when auto-relay is on). This is a deliberate constraint — full replacement is the trap. Operators who genuinely need a different default-contract can change the substrate.

**Directive UI shape — textarea + three read-only `<details>` previews on the General tab** *(resolved at crew interview)*:
- New `editor-section` on the General tab, placed BETWEEN Pairing and Test Connection (edit-mode only, like the F1 L5 Invite section). Section title: "System Prompt Directive."
- Top half: a `<textarea data-field="system-prompt-directive" data-testid="connector-account-system-prompt-directive">` with help text "Your text is appended to whichever default fires for this account's current state. Empty = no override."
- Bottom half: three `<details>` disclosures, one per hardcoded default state. Each renders the verbatim hardcoded text in a `<pre><code>` block (escaped, monospace, scrollable if it overflows the editor width). The label of the disclosure for the CURRENTLY-ACTIVE state (per the account's `auto_relay_platform_replies` checkbox value — that toggle lives on the same tab) carries an annotation: "(this account's current)." Toggling the auto-relay checkbox repaints the annotation; tool-enabled/disabled is per-agent so all three disclosures are always shown.
- Registered via L3's (F1's) `connector-form-registry` as a NEW optional entry hook `renderDirectiveSection(account)` (matches the F1 debrief's `optional-registry-entry-hook` pattern). Bundles with the `connector-form-discord.js` entry; stub-type accounts get no directive section.
- **Dirty-tracker integration** (architect cycle 1 correction):
  - The textarea's value participates in `snapshot` via the **discord entry's** `connector-form-discord.js:snapshot(container)` (NOT via the substrate's `getFormSnapshot`). The substrate dispatches `typedFields` to the entry; the entry reads the textarea by `data-field="system-prompt-directive"` and adds it to the returned object.
  - The directive-textarea `input` listener AND the auto-relay annotation-repaint `change` listener are installed via the entry's `wireEvents(container, checkDirty, account)` (already 3-arg per F1 L5 extension). This is a SEPARATE listener from the substrate's existing `change` listener on the auto-relay checkbox at `connector-account-editor.js:attachStaticListeners` — both fire on the same `change` event without conflict (one repaints the annotation, the other calls `checkDirty`).
  - `collect` emits `config.system_prompt_directive` when the textarea is non-empty; OMITS the key when empty (so the L2 validator's "must be string IF present" branch never sees the empty-string edge; persisted config doesn't accrete empty-string noise).
- **Create-mode behavior**: the directive section is edit-mode-only (matches Pairing's edit-only render at `connector-account-editor.js:renderPairingSection`). Create mode renders NO directive section. The L1-codified `registry-dispatch-create-mode-AC` convention still applies — the AC verifies that the F1 L7 type-pick re-mount path doesn't crash when traversing the directive section's render code (the consult returns "no section to render" in create mode, no exception).
- **Rationale**: shows the operator exactly what their text composes with, in all three states. Honest UI — no hidden modes; operator sees the substrate contract verbatim. The `<details>` pattern is reused from F1 L4's Advanced kv-table disclosure — established UX shape in this editor.
- **Trade-off**: ~3 paragraphs of verbatim default text rendered in the editor consume vertical space. Acceptable: closed by default; the operator opts in to seeing them.

**Multi-account directive composition — alphabetical-account-id join** *(resolved at crew interview)*:
- When an agent has multiple connector accounts attached AND multiple of them have `system_prompt_directive` set, the directives are joined with `\n\n` in order of account_id alphabetical (stable, deterministic). Each directive carries an implicit account-scope, but the system does NOT prefix each with "from account X:" — the operator's text is their own; substrate doesn't decorate it.
- **Rationale**: multi-account-per-agent is M11 mission scope; the most common shape is one-Discord-account-per-agent so the join is rarely exercised, but the deterministic shape matters for prompt-cache stability (a non-deterministic order would silently bust the cache on every restart).

**Probe-gateway intents lift — same fallback shape as F1 L2** *(resolved at crew interview)*:
- `the_one/connectors/_discord.py:_probe_gateway_connect` (static method, currently called from the doctor probe's `gateway-connect` check) gains the same `intents = discord.Intents.default(); intents_cfg = account.config.get("intents", {}); intents.<axis> = intents_cfg.get(...)` shape that F1 L2 shipped at `DiscordPlugin.connect`. Requires extending the static method's signature to receive `account` (or just the resolved `intents_cfg` dict), since today it only receives a token.
- **Rationale**: closes the F1 L2 known gap. The probe should test against the same intents the production connect path will use — otherwise probe-says-OK can diverge from connect-actually-fails for an operator with `message_content=False`.

**Studio polish bundling** *(resolved at crew interview)*:
- L4 (directive Studio surface) bundles two F1 debrief minor action items that share the studio surface:
  - `MASKED_SENTINEL` lifted to a shared studio constant (single declaration; `connector-account-editor.js:MASKED_SENTINEL` + `connector-form-discord.js:MASKED_SENTINEL` both reference it). Candidate location: `window.App.studio.MASKED_SENTINEL = '__MASKED__'` set in the earliest-loading studio module.
  - `_resolveAccountFromContainer` hash-parse replaced with a `data-account-id` attribute set on the editor's mount node. The hash-parse helper lives in `connector-form-discord.js:_resolveAccountFromContainer` (NOT in `connector-account-editor.js`); L4 deletes it and reads the attribute instead. The editor's mount path sets the attribute at render time. Single source of truth; route-shape-decoupled. **Cross-reference** the other hash-consumer at `mcps-tab.js` for the analogous pattern (a future cleanup may apply the same lift there; out of F2 scope but worth a one-line forward note in the L4 leg artifact).
- **Rationale**: shared-surface bundling per `/flight` skill guideline. Both refactors touch only studio JS; bundling avoids a separate cleanup leg or letting them decay.

**HAT-and-alignment leg — required, Chrome-MCP-driven** *(resolved at crew interview)*:
- F1 debrief recommended promoting HAT from optional to required when a flight touches registry-mediated UI dispatch. F2 L4 adds a `renderDirectiveSection` registry hook → required HAT.
- Walk shape: Chrome MCP-driven (operator watches, Flight Director drives) like F1 L7. Not a committed repeatable script (that's M11 F8 scope per the mission's tentative flight plan).
- Verification steps in the HAT leg artifact (created at L6 design time).

**Design-review methodology — three Architect-checklist items applied** *(resolved at crew interview)*:
- F1 debrief recommended (operator-confirmed) codifying three Architect-checklist items: (a) grep every cited symbol; (b) walk event-delegation/dirty-tracker/lifecycle paths; (c) compute and verify numeric constants. Per the F1 debrief action item, codification in mission-control skills is a separate methodology pass. APPLY the three checks at every F2 leg design-review cycle in spirit, even before the skills are updated.
- Symbolic-anchor citations (not line numbers): default discipline for F2 leg specs.

**Atomic-leg-pattern bindings** *(carried from L1)*:
- L2 (pool refactor): primitive rename + call-site updates + tests atomic.
- L3 (directive substrate): config field + validator + `compose_system_prompt` extension + factory call-site + tests atomic.
- L4 (directive Studio + polish bundle): registry hook + studio module + `MASKED_SENTINEL` lift + `data-account-id` refactor + tests atomic.

### Prerequisites

- [x] F1 is `completed` (confirmed: PR #69 merged status TBD; flight artifact status `completed`).
- [x] M10 F8 debrief critical action items list still names "F1 pool keying needs proper refactor" + "Operator-editable connector system-prompt directive" (confirmed).
- [x] F1 debrief recommendations list still names the convention codification + Architect-checklist + symbolic-anchor methodology (confirmed; file at `flight-debrief.md`).
- [x] Discord developer application available for the HAT leg (operator has gleepglorp; reuse from F1 L7).
- [x] `chrome-devtools` MCP is registered (confirmed from F1 L7).
- [x] No new external dependencies — F2 stays inside `discord.py 2.4.x`, the existing Pydantic + FastAPI stack, the existing studio JS bundle.

### Pre-Flight Checklist

- [x] All open questions resolved (pool API shape; directive override semantics; UI placement; HAT shape — all locked at Phase 4)
- [x] Design decisions documented (above)
- [x] Prerequisites verified
- [x] Validation approach defined (per-leg ACs + L6 HAT)
- [x] Legs defined (below; planned one-at-a-time per Flight Control convention but tentatively scoped here)

---

## In-Flight

### Technical Approach

**Substrate-first sequencing.** L1 codifies the two F1-debrief conventions doc-only so subsequent legs can invoke them by name. L2 lands the pool-keying refactor — pure substrate, no UI dependency, no upstream consumers blocked. L3 lands the directive's substrate half (config field + validator + composer + factory). L4 lands the Studio UI on top of L3's substrate and bundles the F1-debrief minor polish items. L5 lifts the probe's hardcoded intents — independent of L2-L4; could ship at any point but bundled here as the last substrate cleanup. L6 is the required HAT, walking the operator through the directive editing flow + verifying the pool-keying refactor under multi-agent traffic.

**Pool refactor is the load-bearing piece.** F2 L2 is the smallest substrate touch with the largest blast radius. The clean break (no shim, no deprecation, sentinel deleted) eliminates the M10 F8 footgun in one commit. Every connector-subsystem caller (**6 production sites**: 4 in `connectors/_inbound.py:dispatch_inbound`, 1 in `tools/connector_send.py:SendToPlatformChannelTool.execute`, 1 in `interfaces/web/app.py:lifespan` warm-up) gets updated atomically. The MCP-side pool consumers (`mcp/_pool.py` consumers, separate codebase region) are unaffected — F1 audit confirmed MCP has its own pool module; the rename only touches the connector pool's exports.

**Directive composer is a single read-site change.** `AgentFactory.create()` already pulls the auto-relay flag from `account.config` per-attached-account at `factory.py:AgentFactory.create — auto-relay aggregation`; the directive read at L3 collects from the SAME attached-accounts set but applies `sorted(...)` for stable order. The composer's APPEND mode is one line in `compose_system_prompt`: append after the selected default, before the persona separator.

**Studio UI on top of L3's data layer.** L4 reuses L4 of F1's patterns wholesale — register a new optional entry hook (`renderDirectiveSection`), thread `vocab` if the section needs vocabulary (probably not — "System Prompt Directive" is connector-agnostic), extend `wireEvents` for the textarea + auto-relay-checkbox change listeners, extend `snapshot` for the textarea value, extend `collect` to emit `config.system_prompt_directive` when non-empty.

**Probe lift mirrors F1 L2 verbatim.** Same fallback shape, same WARNING-log convention. The signature extension on `_probe_gateway_connect` is the only structural change — the probe was previously token-only; needs the account context for the intents read.

### Checkpoints

- [x] L1 — Two F1-debrief conventions (`optional-registry-entry-hook`, `registry-dispatch-create-mode-AC`) codified in `the_one/agents.md` Project-wide with definitions, applicability boundaries, exemplar citations, and back-references to F1 debrief.
- [x] L2 — `_pool.py` exports two primitives `agent_acquire` + `account_acquire`; `_CONNECTOR_POOL_AGENT_SENTINEL` deleted; bare `acquire`/`connector_acquire` removed from exports; **6 production call sites** updated lockstep; tests pinned; `_keys_for_test()` test seam added.
- [x] L3 — `account.config["system_prompt_directive"]: str | None` field accepted by L2 (F1) API validator; `compose_system_prompt` gains `operator_directive: str | None` parameter; `AgentFactory.create()` collects + joins per-account directives; tests pin all four touchpoints.
- [x] L4 — Studio General-tab section renders textarea + 3 read-only `<details>` defaults; "current state" annotation reacts to auto-relay-checkbox toggle; dirty-tracker integrated via existing `wireEvents`/`snapshot`/`collect` registry hooks; `MASKED_SENTINEL` lifted to shared studio constant; `data-account-id` attribute on editor mount replaces hash-parse.
- [x] L5 — `_discord.py:_probe_gateway_connect` reads `account.config["intents"]` with byte-identical fallback to F1 L2's `connect()` shape; signature extended to receive account context; tests pin the lift.
- [x] L6 — HAT walk: edit directive → save → confirm next agent build carries the operator's appended text; toggle auto-relay → confirm the "current state" annotation moves; verify pool-keying refactor: multiple agents attached to one Discord account hit ONE pool entry under real traffic (verify via the L2 `_keys_for_test()` seam OR log lines); verify probe-intents lift: probe + connect both observe the same `account.config["intents"]` shape; verify verbatim defaults from the UI match the hardcoded text at `agent/config.py:_CONNECTOR_TOOL_ENABLED_DIRECTIVE / _CONNECTOR_AUTO_RELAY_DIRECTIVE / _CONNECTOR_TOOL_DISABLED_DIRECTIVE` byte-for-byte.

### Adaptation Criteria

**Divert if**:
- L2's clean break exposes an out-of-tree consumer of `acquire`/`connector_acquire`/`_CONNECTOR_POOL_AGENT_SENTINEL` that this audit missed. Pause, document the consumer, decide whether to add a shim or update the consumer.
- L3's directive-collection iteration order (alphabetical-by-account_id) produces a prompt that the LLM mishandles in HAT (e.g., the LLM treats the first directive as authoritative and ignores the second). Pause, escalate; the join shape might need to change.
- L4's `renderDirectiveSection` hook adds a 4th optional entry hook to the registry. If the entry-shape validator at `connector-form-registry.js:_validateEntry` needs structural extension beyond the existing `optionalFns` loop, pause and escalate — that's a substrate change deserving its own design pass.
- HAT (L6) surfaces a substrate-contract reversal (per `prompt-discipline-needs-mechanical-fallback`, L1-codified F1) — pauses the flight and triggers fresh design review.

**Acceptable variations**:
- L2 and L5 are independent of L3-L4; L5 may ship before L4 if the architect prefers (probe-intents-lift is the smaller change).
- L3 and L4 may merge if the directive-substrate code surface is tiny enough that bundling the Studio UI in the same leg stays under ~400 LOC source.
- The directive-section's tab placement may shift to "Access and Routing" if the General tab grows too tall in HAT review.
- Multi-account directive composition order may switch from alphabetical-by-account_id to insertion-order (the order the operator attached the accounts) if the HAT operator finds alphabetical surprising. Document any change in the flight log.

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses. This list will evolve based on discoveries during implementation.
>
> **Dependency ordering**: L1 lands before L2-L5 (legs reference codified conventions by name). L3 lands before L4 (L4's textarea posts a field L3's validator must accept; UI without substrate would fail save). L2 and L5 are independent of each other and of L3-L4. L6 lands last (required HAT verifies the integrated stack).

- [x] `codify-f1-debrief-conventions` — Doc-only L1 mirroring F1 L1. Add `optional-registry-entry-hook` and `registry-dispatch-create-mode-AC` to `the_one/agents.md` Project-wide subsection. Each gets a definition + applicability boundary + exemplar citation from F1 (registry's 3 optional hooks + L7 HAT-fix's create-mode AC). Back-references to F1 debrief recommendations. No source modifications.

- [x] `account-keyed-pool-primitive` — Clean-break refactor of `connectors/_pool.py`. Rename `acquire` → `agent_acquire`; rename `connector_acquire` → `account_acquire`; DELETE `_CONNECTOR_POOL_AGENT_SENTINEL` from module exports (keep `__connector__` as an internal-only string literal for the composite-key shape so warm entries persist across deployment). Add `_keys_for_test()` helper. Update **6 production call sites** lockstep (`tools/connector_send.py:SendToPlatformChannelTool.execute`; `connectors/_inbound.py:dispatch_inbound` 4 sites; `interfaces/web/app.py:lifespan` warm-up). Update test imports: `tests/test_connectors_pool.py` import group, `tests/test_connectors_e2e.py` two import groups, `tests/test_db_api.py` 7 import sites (grep at impl time). Sweep docstring references in `tests/test_connectors_inbound.py`, `tests/test_connector_send_tool.py`, `tests/test_lifespan.py`. Sweep code-comment cross-references in `the_one/connectors/README.md`, `the_one/connectors/base.py`, `the_one/connectors/_session.py`, `the_one/agent/_context.py`. Decide at L2 design whether to update the `the_one/agents.md:_CONNECTOR_POOL_AGENT_SENTINEL` exemplar citation (L1 F1 codified it as a historical example; post-refactor the citation reads as past-tense). Per `atomic-leg-pattern` (M10 convention, codified F1 L1): primitive rename + call-site updates + tests + docstring sweep in one leg. Eviction, reaper, and encryption-rotation invariants verified unchanged (single composite-key dict — no behavior delta).

- [x] `directive-substrate` — Add `account.config["system_prompt_directive"]: str | None` validation to the F1 L2 API validator's Discord branch (must-be-string-if-present; no length cap). Extend `the_one/agent/config.py:compose_system_prompt` with 4th keyword parameter `operator_directive: str | None = None` defaulting to None — when truthy, appended to `parts` AFTER the selected default and BEFORE the persona separator. Existing non-connector and prompt-equivalence callers pass nothing → byte-identical legacy output preserved (the F4 invariant at the existing `compose_system_prompt` docstring). Extend `the_one/agent/factory.py:AgentFactory.create` to collect `system_prompt_directive` from each attached connector account (drop None), join with `\n\n` in **`sorted(config.connector_account_ids)`** order — explicit divergence from the existing auto-relay-aggregation iteration (which keeps list-order because its first-opt-out semantics are order-sensitive). Pass as `operator_directive`. Per `atomic-leg-pattern`: validator + composer + factory + tests land together. Pin with: validator rejects non-string; composer appends correctly when truthy AND is byte-identical to legacy when None; factory joins multi-account in stable sorted order; existing prompt-equivalence checks at the WS handler still pass.

- [x] `directive-studio-surface` — Register `renderDirectiveSection(account)` as a NEW optional entry hook on L3-of-F1's `connector-form-registry` (per `optional-registry-entry-hook` convention codified L1). Mount the section on the General tab between Pairing and Test Connection (edit-mode only). Textarea + 3 read-only `<details>` disclosures (verbatim hardcoded text from `agent/config.py:_CONNECTOR_TOOL_ENABLED_DIRECTIVE / _CONNECTOR_AUTO_RELAY_DIRECTIVE / _CONNECTOR_TOOL_DISABLED_DIRECTIVE`). The "current state" annotation on the auto-relay-state disclosure repaints when the auto-relay checkbox toggles, wired via the entry's `wireEvents(container, checkDirty, account)` (3-arg per F1 L5). The textarea participates in `snapshot` via the entry's `snapshot(container)` (NOT the substrate's `getFormSnapshot`). `collect` emits `config.system_prompt_directive` when non-empty; OMITS when empty. **Bundle** (shared studio surface): lift `MASKED_SENTINEL` to `window.App.studio.MASKED_SENTINEL` (single declaration); delete `connector-form-discord.js:_resolveAccountFromContainer`, replace with reads of a new `data-account-id` attribute set on the editor's mount node. Per L1-codified `registry-dispatch-create-mode-AC`: ACs cover create-mode-after-type-pick (no directive section rendered; F1 L7 re-mount path traverses the new render without crashing) AND edit-mode-with-type-set (full directive section renders + dirty-tracker works + save round-trips).

- [x] `probe-gateway-intents-config-driven` — Lift `the_one/connectors/_discord.py:_probe_gateway_connect` hardcoded intents (one site outside F1 L2's `connect()` scope) to `account.config["intents"]` reads with byte-identical fallback. Extend the static method's signature to receive `account` (or just the resolved `intents_cfg` dict — decide at L5 design based on what the doctor probe's call site has in scope). Pin with a test that the probe's intents match what `connect()` will use, eliminating probe-says-OK-but-connect-fails divergence.

- [x] `uat-and-alignment` *(required, per F1 debrief recommendation — registry-mediated UI dispatch touched)* — Chrome-MCP-driven HAT against gleepglorp. Verification steps: (1) directive textarea renders on the Discord Constellation General tab; (2) all 3 `<details>` defaults render their verbatim text; (3) the "current state" annotation labels the active default per auto-relay toggle; (4) toggling auto-relay repaints the annotation live; (5) typing a directive + saving round-trips through the API (verify via GET response); (6) a NEW agent built on this account (or a session restart) carries the appended directive in its system prompt (verify via the agent's edit-view system-prompt preview); (7) toggling auto-relay off + saving + re-checking carries the operator's directive appended to the OFF-state default; (8) pool-keying verification — attach a second agent to Discord Constellation, send a peer message through Discord, confirm ONE pool entry handles both agents (inspect via L2's `_keys_for_test()` seam OR a `_pool` log line); (9) verbatim defaults from the UI match the hardcoded text at `agent/config.py:_CONNECTOR_TOOL_ENABLED_DIRECTIVE / _CONNECTOR_AUTO_RELAY_DIRECTIVE / _CONNECTOR_TOOL_DISABLED_DIRECTIVE` byte-for-byte. HAT-discovered fixes land in the flight-log L6 Anomalies section. Substrate-contract reversals pause the flight per Adaptation Criteria above.

---

## Post-Flight

### Completion Checklist

- [ ] All required legs (L1-L5) completed
- [ ] L6 HAT completed with operator-confirmed pass on all 9 verification steps
- [ ] Code merged on `main`
- [ ] Tests passing at or above F1 baseline (2804 + new test counts)
- [ ] `the_one/agents.md` updated with the two codified conventions
- [ ] `_pool.py` exports `agent_acquire` + `account_acquire`; `_CONNECTOR_POOL_AGENT_SENTINEL` deleted; bare `acquire`/`connector_acquire` removed
- [ ] `compose_system_prompt` accepts and appends `operator_directive`
- [ ] Studio General tab renders directive section with textarea + 3 disclosures
- [ ] `MASKED_SENTINEL` declared once; `_resolveAccountFromContainer` removed
- [ ] `_discord.py:_probe_gateway_connect` reads `account.config["intents"]`

### Verification

**Mechanical verification** (CI / scripted):
- `pytest tests/test_connectors_pool.py` — pool primitives + composite-key storage + eviction
- `pytest tests/test_connectors_inbound.py tests/test_connector_send_tool.py` — call-site updates
- `pytest tests/test_agent_config.py` (or wherever `compose_system_prompt` lives) — append-mode composer
- `pytest tests/test_factory.py` — multi-account directive collection + stable join order
- `pytest tests/test_api_connector_account_config_validation.py` — new `system_prompt_directive` field validation
- `pytest tests/test_connectors_discord.py::test_probe_intents_from_config` — probe lift
- `pytest tests/browser/test_flow_studio_connector_directive_section.py` (new) — registry hook + UI render + dirty tracking + save round-trip
- Full suite stays at or above F1 baseline (2804 passed)

**Operational verification** (L6 HAT):
- Directive editing round-trip works end-to-end
- Pool-keying refactor verified under multi-agent traffic on one Discord account (one pool entry; one IDENTIFY frame)
- Probe's intent check now matches production connect behavior

**Methodology verification**:
- L1's codified conventions are referenceable by name in subsequent flights' design decisions (per F1 debrief recommendation #2)
- Three Architect-checklist items (grep cited symbols; walk delegation paths; verify computed constants) APPLIED at every F2 leg design-review cycle in spirit; observe whether cycle-1 HIGH-severity catches drop relative to F1 (cycle-1 HIGH in 4 of 6 F1 legs).
- Symbolic-anchor citations default discipline; track whether citation drift recurs.
