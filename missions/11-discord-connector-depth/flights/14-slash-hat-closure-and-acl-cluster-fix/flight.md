# Flight: Slash HAT closure + ACL/slash-sync cluster fix + L4-enhancement test debt

**Status**: ready
**Mission**: [Discord Connector Depth & Robustness](../../mission.md)

## Contributing to Criteria

- [ ] **#10** — All six platform-side slash commands end-to-end validated against the real Discord bot, INCLUDING the "ephemeral where appropriate" sub-bullet that F13 L6 deferred. F14 closes the criterion FULLY (not partially) by (a) fixing the 4-bug ACL/slash-sync cluster F13 L6 surfaced, (b) shipping ephemeral-where-appropriate polish for the self-only commands, and (c) re-running the HAT — both manually via operator walkthrough AND via the new `discord-slash-end-to-end` behavior-test spec that drives a 2nd Discord bot programmatically.
- [ ] **#11** (partial) — The end-to-end HAT for this mission ships as a re-runnable repository artifact. F14 ships the slash-command portion via the `discord-slash-end-to-end` behavior-test (2nd-bot driver via `discord.py`); the full multi-user / multi-channel / multi-agent / pairing / mentions-aware coverage stays scoped for a later flight.

Plus three F13 debrief carry-forwards fold in: the L4-enhancement unit-test backfill (3-5 browser tests for `populateInferenceModelDropdown` which shipped untested), the 2 pre-existing browser failures (4-flight deferral closed), and the Bug A operations note (uvicorn `--reload` doesn't refresh Pydantic class objects; container restart required after Pydantic edits — CLAUDE.md note).

---

## Pre-Flight

### Objective

Close M11's last open criterion (#10 — slash commands validated against real Discord) by repairing the substrate that blocks slash-command verification end-to-end. F13 L6 HAT surfaced a 4-bug ACL/slash-sync cluster; F14 L1-L3 fixes the 3 real bugs (Bug C was a false positive at F13 diagnosis, retired); L4-L6 closes test debt + docs; L7 ships ephemeral-where-appropriate polish (closes #10's deferred sub-bullet); L8 refactors `admits_inbound` to take an `AdmissionContext` dataclass so future ACL signature widenings surface call-site drift via the type system (closes F13 debrief Recommendation per the operator's selected Option B); L9 authors a re-runnable `discord-slash-end-to-end` behavior-test spec that drives a 2nd Discord bot programmatically via `discord.py`; L10 is the operator-driven HAT run + behavior-test execution that gates flight land.

### Open Questions

All resolved at planning (Phase 3 + Phase 4) before leg design.

- [x] Bug B fix shape (top-level `config.guilds` vs nested `allowlist.guilds`)? → see DD: Bug B reads allowlist.guilds + deprecates top-level
- [x] Bug E substrate decision (filter categories at enumerate vs UI-side guard)? → see DD: filter type=category at the Discord plugin's enumerate site
- [x] `admits_inbound` refactor shape (Option A envelope vs Option B AdmissionContext vs Option C no-defaults)? → see DD: AdmissionContext dataclass (Option B)
- [x] L5 (2 pre-existing browser failures) scope? → see DD: investigate-at-implementation with flexible fix-or-update-assertions disposition
- [x] L7 scope (verify-only vs include ephemeral polish vs include autocomplete)? → see DD: include ephemeral-where-appropriate polish for the 2-3 self-only commands (closes #10 fully); autocomplete polish stays deferred
- [x] Behavior-test authoring at design time? → see DD: author TWO specs inline at L9 design (`discord-slash-end-to-end.md` covering 6 commands with per-command ephemeral assertions + `slash-command-ephemeral-routing.md` covering L7's 4-cell substrate matrix + token-expiry fallback); both run at L10
- [x] Bug C was a false positive at F13 diagnosis? → confirmed via Phase 1b recon; retired from cluster

### Design Decisions

**Bug B reads allowlist.guilds + deprecates top-level `config.guilds`** *(operator-directed at Phase 4)*: `_sync_slash_commands` at `the_one/connectors/_discord.py:247` switches from `account.config.get("guilds") or []` to `account.config.get("allowlist", {}).get("guilds") or []`. The top-level `config.guilds` field is no longer consulted anywhere — flagged as deprecated; the L2 leg's verification gate greps `the_one/` for any orphan readers and the gate is "0 hits" at land. `_discord.py:1000` reference + `agents.md` L4 narrative (line ~797's "post-READY, the connect path calls `await tree.sync(guild=discord.Object(id=int(g)))` for each `g in account.config.get("guilds", [])`") update in lockstep.
- **Rationale**: single source of truth. The validator at `db/models.py:443` already validates `allowlist["guilds"]`; the UI at `connector-editor.js:4332` reads `allowlist.guilds`; the ACL routing axis at `_routing.py` consumes from allowlist. `_sync_slash_commands` was the lone hold-out reading top-level.
- **Trade-off**: any external script (operator HAT scripts, debug helpers) that relied on top-level `config.guilds` breaks. The F13 L6 diagnostic PUT that added top-level `config.guilds` becomes dead data on the operator's connector — L2 includes an aiosqlite-based cleanup hint (operator runs OR ignores; cleanup is non-blocking).

**Bug E filters `type=category` at the Discord plugin's enumerate site** *(operator-directed at Phase 4)*: `enumerate_discoverable_entities` in `the_one/connectors/_discord.py` filters channels to `type IN ("text", "voice", "thread")` and excludes `type="category"` before returning. The UI picker at `connector-editor.js` thus never sees categories as pickable channels.
- **Rationale**: categories are containers, not channels; the ACL channel-match never accepts a category id because messages come from child channels with their own ids. Filtering at the substrate keeps every UI consumer (current + future) automatically correct without per-UI defensive logic.
- **Trade-off**: if a future ACL feature wants category-scope semantics (e.g. "admit any channel under this category"), we'd need to re-add categories to the enumeration AND add the recursive-match logic at the ACL layer. Acceptable — that feature isn't scoped today and the substrate-side filter is trivial to revert.

**`admits_inbound` refactor uses an `AdmissionContext` dataclass (Option B)** *(operator-directed at Phase 4 after deeper context)*: define a narrow frozen dataclass `the_one.connectors._acl.AdmissionContext` with exactly the 5 fields ACL needs (`peer_id: str`, `channel_id: str`, `is_dm: bool`, `guild_id: str | None`, `member_roles: list[str]`) plus a `from_envelope(env: InboundEnvelope) -> AdmissionContext` classmethod. `admits_inbound`'s signature becomes `admits_inbound(account: Connector, agent_acl: dict | None, ctx: AdmissionContext) -> tuple[bool, str]`. All call sites (`_routing.py:180`, `_commands.py:108` post-L1 fix) build the context from the envelope and pass it.
- **Rationale**: makes the ACL→envelope contract explicit. Future ACL field additions become new `AdmissionContext` fields → type system catches every call site that hasn't been updated. Decouples ACL from envelope's broader shape. CLI tools / tests can construct `AdmissionContext` directly without synthesizing a fake envelope.
- **Trade-off**: one extra dataclass to maintain; one extra construction step at every call site (mitigated by `from_envelope` classmethod which is a one-liner). The L8 leg's diff is wider than Option C (remove kwarg defaults) but the type-system safety net pays for itself the next time the ACL widens.

**L5 investigates-at-implementation** *(operator-directed at Phase 4)*: the 2 pre-existing browser failures (`test_tablist_renders_with_three_tabs` + `test_studio_section_round_trip_preserves_agent_selection`) haven't been triaged in 4 flights. Either trivial assertion drift (e.g. tab count changed legitimately) OR real product regressions. L5's leg spec authorizes the implementing Developer to (a) diagnose first, then (b) either fix the product OR update the test assertions, depending on which side actually drifted. The leg's acceptance criteria are flexible: "after L5, neither test is failing, and the disposition (product-fix vs test-update) is documented in the flight-log L5 entry".
- **Rationale**: avoids designing a fix in the dark. The 4-flight deferral suggests these are non-load-bearing; quickest path is "diagnose + apply the right fix shape".
- **Trade-off**: scope-uncertainty in L5. If both turn out to be deep product regressions, L5 could grow. Mitigated by an explicit Divert clause: if L5's diagnosis surfaces >3-day work for either test, divert into a separate maintenance flight + restore L5 to the lighter scope.

**L7 ships ephemeral-where-appropriate polish via interaction-followup substrate** *(operator-directed at Phase 4, architect-cycle-1 corrected)*: F13 L6 deferred BOTH the "ephemeral where appropriate" sub-bullet AND the Discord-native autocomplete polish of criterion #10. F14 closes the ephemeral half (operator-scoped commands `/whoami`, `/agents`, `/help` become ephemeral; channel-affecting commands `/talk_to`, `/new`, `/reset` stay channel-visible). Autocomplete stays deferred to a later flight.

Architect cycle-1 surfaced that this is more substrate work than a flag flip — the slash command flow is `interaction.response.defer(ephemeral=True)` at `_discord.py:877` → `dispatch_inbound` → `client.send(text)` at `_inbound.py:695-728`. The dispatcher's outbound path posts via the normal `DiscordClient.send` to the channel; there's no `interaction.response.send_message` to flip a flag on. To deliver an ephemeral response, L7 must:
1. **Widen `CommandResponse`** at `connectors/base.py` to carry an opt-in `ephemeral: bool = False` field.
2. **Have the 3 self-only handlers** (`_handle_whoami`, `_handle_agents`, `_handle_help`) return `CommandResponse(text=..., ephemeral=True)`.
3. **Thread the interaction-followup token** from the slash body (`_discord.py:861-908`) through the dispatch envelope into the dispatcher's outbound site. Add an optional `interaction_followup_token` to `OutboundTarget` (or `envelope.raw`) so the dispatcher's `client.send` can choose `interaction.followup.send(text, ephemeral=True)` vs the normal channel send.
4. **Fix the unconditional defer** at `_discord.py:877` — currently `interaction.response.defer(ephemeral=True)` runs for ALL 6 commands, producing a brief ephemeral-acknowledgment followed by channel-visible response for the 3 channel-affecting commands (UX inconsistency). Change to `ephemeral=True` only for the 3 self-only commands; `ephemeral=False` (or no defer at all) for the 3 channel-affecting commands.
5. **Handle interaction-token expiry** (15-minute window) — if `dispatch_inbound` takes longer than 15 minutes (extreme edge case e.g. inference call timeout cascade), the followup token is invalid. Fall back to channel send with a `[ephemeral fallback]` prefix OR error gracefully. Per F13 L7 outbound conventions, the dispatcher's outbound is typically sub-second; this is a defensive guard.
6. **No backward-compat shim** — existing `_handle_*` handlers that DON'T set `ephemeral` get the default `False` (channel-visible), preserving the current behavior for unaffected commands and any future commands.

- **Rationale**: closes criterion #10's "ephemeral where appropriate" sub-bullet fully. Sets the substrate up for the future `app_commands.autocomplete` work which also requires interaction-context plumbing. Eliminates the unconditional-defer UX inconsistency along the way.
- **Trade-off**: 1.5-2 day leg (substrate-touching with new field on `OutboundTarget` / `envelope.raw` + dispatcher-outbound branch + token-expiry guard). Larger than originally scoped (which assumed a flag flip). Worth it — the interaction-context plumbing is reusable for autocomplete + any future Discord-native interaction surface.

**L9 authors a `discord-slash-end-to-end` behavior-test spec** *(operator-directed at Phase 4)*: re-runnable behavior test that drives a 2nd Discord bot (via `discord.py`'s programmatic client) on the test guild to invoke the 6 slash commands against the operator's bot (the connector account's bot). Closes M11 criterion #11 partially (the slash-command portion of the Chrome-driven HAT script criterion). The spec uses the **Witnessed** pattern: a 2nd-bot-driver Executor invokes each command + observes the responding bot's reply; an independent Validator judges. Browser MCP NOT required for this spec (the 2nd bot drives Discord's API directly via `discord.py`, not via the web client). Apparatus: `shell` (for `discord.py` runtime) + `http` (for Discord REST cross-checks).
- **Rationale**: per the M11 outline, the HAT-as-repeatable-artifact criterion explicitly allows "Chrome MCP or `discord.py`-as-second-bot driver (the agent runs as bot A, the HAT script runs as bot B on the same test guild)" — F14 picks the `discord.py` driver because slash invocations against Discord's REST API are programmatic without browser automation, sidestepping Discord's web-client bot-detection. The behavior-test spec lives at `tests/behavior/discord-slash-end-to-end.md`.
- **Trade-off**: requires a 2nd Discord bot user (operator must register a 2nd application + bot in Discord developer portal + invite it to the test guild). Operator-precondition documented in the spec. The spec's first re-run will be against L1-L9's post-fix substrate; gates flight land at L10.

**L10 is operator-driven** *(per flight convention)*: operator runs the manual HAT walkthrough of the 6 commands AND triggers the L9 behavior-test run. Both must produce "PASS" verdicts for F14 to land. The manual walkthrough catches operator-perceivable issues (UX wording, ephemeral-or-not, autocomplete-or-not) that the programmatic behavior-test can't judge from raw response payloads; the behavior-test catches regressions that would otherwise re-emerge silently between manual HATs.

### Prerequisites

- [ ] F13 has landed on main (commit `ed78d0e`, verified)
- [ ] Backend test suite baseline: 2796 passed / 4 skipped / 0 errors / ~243s wall (per F13 debrief test-metrics)
- [ ] Browser test suite baseline: 454 passed / 35 skipped / 12 deselected / 2 pre-existing-main failures (the 2 failures L5 will address; expected to go to 0 post-L5)
- [ ] Operator's Discord bot reachable for L10 HAT (operator confirms before L10 kickoff)
- [ ] Operator's 2nd Discord bot registered + invited to test guild (L9 + L10 prerequisite; operator sets up before L10 kickoff; documented in `discord-slash-end-to-end.md` spec preconditions)
- [ ] M11 agents.md M11 section has the 6 F13-codified conventions (the original 6 from F11/F12 + the 5 from F13 debrief) — F14 doesn't add new conventions but L8 may; verify at L8 design time

### Pre-Flight Checklist

- [x] All open questions resolved
- [x] Design decisions documented
- [x] Prerequisites listed
- [x] Validation approach defined
- [x] Legs defined

---

## In-Flight

### Technical Approach

**Leg count**: 10 legs (most are small — single-site code change + regression test; L8 is the largest substrate-touching leg).

**L1 — Bug D fix + regression test.** `the_one/connectors/_commands.py:_permitted_agents` at `:108` currently calls `admits_inbound(account, agent_acl, envelope.peer_id, envelope.channel_id)` — missing the 3 required kwargs `is_dm` / `guild_id` / `member_roles`. L1 mirrors `_routing.py:180`'s derivation, which goes through a small plugin hook chain (NOT a direct `envelope.raw.get("is_dm")` read):
- `is_dm` is derived via `_default_not_dm(envelope)` at `_acl.py:85` (plugin-hook-via-getattr-sentinel pattern per M11 convention) OR via the plugin's `is_dm_inbound` hook if it overrides. For Discord, `_default_not_dm` returns `not envelope.raw.get("is_dm", False)`. The routing site at `_routing.py:_agent_admits` already wraps this; L1 either (a) imports `_default_not_dm` directly into `_commands.py` for the secondary admission, OR (b) extracts the derivation into a shared `_envelope_is_dm(envelope, plugin)` helper that both callers use.
- `guild_id` = `envelope.raw.get("guild_id")` — direct read.
- `member_roles` = `envelope.raw.get("member_roles", [])` — direct read with default.

Surfaces:
- `the_one/connectors/_commands.py:108` — thread the 3 kwargs from envelope.raw (with `is_dm` via the shared helper). ~8-line code change vs the originally estimated ~5; the `is_dm` plumbing is the extra LOC.
- `tests/test_connectors_commands.py` — add 2 regression tests under a new class `TestPermittedAgentsAgainstStructuredAllowlist`: (a) `_handle_agents` returns the agent when the connector's structured-tuple `allowlist.channels` matches the envelope's `guild_id` + `channel_id`; (b) `_handle_agents` returns "No agents available" when guild_id is absent OR doesn't match.
- L1 backend test count target: **2796 + 2 = 2798**.

**L1 sequencing note**: L1 lands BEFORE L8 (AdmissionContext refactor) so the refactor migrates an already-correct call-site. L8 then changes the call-site shape from kwargs to `AdmissionContext.from_envelope(envelope)` — a single-line change after L1's plumbing is in place.

**L2 — Bug B fix + agents.md narrative + grep gate.** `_sync_slash_commands` reads the wrong key. Surfaces:
- `the_one/connectors/_discord.py:247` — switch from `account.config.get("guilds") or []` to `account.config.get("allowlist", {}).get("guilds") or []`. ~1-line code change.
- `the_one/connectors/_discord.py:1001` — comment-only update to reflect the new read path (the cited line is in a doc comment block at `:998-1006` referencing `account.config["guilds"]`).
- `the_one/agents.md` (around line 797's L9 narrative) — update the "for each `g in account.config.get("guilds", [])`" sentence to reflect the new read path.
- Grep gate (Phase 5c per pulled-forward methodology lesson #1): `git grep -nE 'config\.get\("guilds"\)|config\["guilds"\]' the_one/` post-L2 returns ZERO hits in source files (only allowed residue: agents.md historical narration if the L2 author chose to retain it for context).
- No new tests — Bug B's fix path is exercised by L10's L9 behavior-test (slash sync must actually fire for the 2nd-bot invocations to reach the bot). L2's verification is the grep gate + the slash-sync log line firing at container restart (operator confirms).
- L2 backend test count: unchanged at 2798.

**L3 — Bug E substrate filter (`type=category` exclusion).** Surfaces:
- `the_one/connectors/_discord.py` — locate `enumerate_discoverable_entities` (likely around the discoverable-entities Protocol hook landed at F3); add a filter that excludes channels with `metadata["type"] == "category"` from the returned `channels` list.
- `tests/test_connectors_discord.py` — add 1 unit test verifying that a guild with mixed channel types (category + text + voice + thread) returns only the non-category channels from `enumerate_discoverable_entities`.
- `tests/browser/test_flow_studio_connector_inference_provider_row.py` OR a new sibling test file — add 1 browser test verifying that the Studio channel-allowlist picker (the connector-editor's allowlist editor) does NOT show category-type entries even when the discoverable-entities response is mocked to include them. (This is a defense-in-depth check: if the substrate filter is reverted in a future flight, the UI test still pins the contract.)
- L3 backend test count: +1 = 2799. Browser test count: +1 = 455.

**L4 — L4-enhancement unit-test backfill.** The L4-enhancement (F13 L4 post-land enhancement; `populateInferenceModelDropdown` + `wireInferenceModelRepopulate` in `connector-editor.js` ~lines 3349-3431) shipped with zero unit tests. Surfaces:
- `tests/browser/test_flow_studio_connector_inference_provider_row.py` — add 3-5 new browser tests covering: (a) Ollama provider selected → model dropdown populates with 1+ models; (b) provider switch (Ollama → OpenRouter) cancels the in-flight model fetch via `AbortController` (race-guard verification); (c) persisted-but-not-enumerated value surfaces as `{value} (custom)` selected; (d) no-provider state shows "Select a provider first" disabled placeholder; (e) provider cleared via GUI fires synthetic change event so Save becomes enabled (the F13 bug-fix regression target).
- L4 browser test count: +5 = 460.

**L5 — 2 pre-existing browser failures (4-flight deferral closed).** Investigate-at-implementation per the flexible-scope DD. Surfaces:
- `tests/browser/test_flow_agent_tabs.py::test_tablist_renders_with_three_tabs` — implementer runs the test, captures the failure mode, decides product-fix-vs-test-update.
- `tests/browser/test_flow_studio_navigation.py::test_studio_section_round_trip_preserves_agent_selection` — same protocol.
- Flight-log L5 entry documents the diagnosis + the fix shape applied.
- L5 browser test count: 460 unchanged (no new tests; both failures resolved to PASS).
- Divert clause: if either test surfaces >3-day product-regression work, divert to a separate maintenance flight + restore L5's scope to the smaller test (or rationalize-only if both blocked).

**L6 — Bug A docs (CLAUDE.md note on uvicorn `--reload` Pydantic class caching).** Surfaces:
- `CLAUDE.md` — add a short subsection (~5-10 lines) under an existing "Development" or "Operations" section (or create one if absent) noting: when modifying a Pydantic class definition (e.g. `AgentConfig`, `Connector`, `ChatSession`), uvicorn's `--reload` re-imports the module but the previously-imported class object's frozen validator schema persists in memory; the running worker uses the stale schema. Fix: full container restart (`docker compose restart the-one` or equivalent), not just file save.
- No tests; doc-only.

**L7 — Ephemeral polish for self-only slash commands.** Per the DD above, this is a 1.5-2 day substrate leg (NOT a flag flip). Surfaces:
- `the_one/connectors/base.py` — widen `CommandResponse` with an opt-in `ephemeral: bool = False` field.
- `the_one/connectors/_commands.py` — `_handle_whoami` / `_handle_agents` / `_handle_help` return `CommandResponse(text=..., ephemeral=True)`. `_handle_talk_to` / `_handle_new` / `_handle_reset` keep the default (channel-visible).
- `the_one/connectors/_discord.py:861-908` — slash-body wrapper threads `interaction.followup` token (or equivalent identifier) through the dispatch path. Likely shape: add `interaction_followup_token` to `envelope.raw` for slash-originated envelopes; the dispatcher's outbound branch reads it.
- `the_one/connectors/_inbound.py:695-728` (dispatcher outbound; load-bearing site per cycle-2 architect) — extend the `client.send(OutboundTarget(...), response.text)` blocks to inspect (a) `response.ephemeral` flag from the CommandResponse + (b) `envelope.raw.get("interaction_followup_token")`. When both are present + truthy, route through `interaction.followup.send(text, ephemeral=True)` instead of the normal channel send. Otherwise default to channel send.
- `the_one/connectors/_discord.py:877` (`interaction.response.defer(ephemeral=True)` runs unconditionally for all 6 commands today, producing brief ephemeral-acknowledgment-then-channel-visible-response inconsistency for the 3 channel-affecting commands) — change to `ephemeral=True` only for the 3 self-only commands; `ephemeral=False` (or no defer) for the 3 channel-affecting. Conditional based on the resolved command name.
- Interaction-token expiry guard (15 minutes from `defer` per Discord docs, NOT from interaction creation — gives the dispatcher more headroom): if `interaction.followup.send` raises a `discord.errors.NotFound` or similar token-expired error, fall back to channel `client.send` with a `[ephemeral fallback]` prefix in the text. Per F13 L7 outbound conventions, dispatcher outbound is typically sub-second; this is a defensive guard.
- `tests/test_connectors_commands.py` — extend the existing tests for `/whoami`, `/agents`, `/help` to assert `response.ephemeral is True`; the channel-affecting commands' tests assert `response.ephemeral is False`. New test under `TestDispatcherOutboundRoutesEphemeral`: a mock `DiscordClient` with both `send` and `interaction_followup` paths; verify the dispatcher's outbound picks the right one based on `(response.ephemeral, envelope.raw.get("interaction_followup_token"))` combination (4 cells of the matrix).
- L7 backend test count: +4 (the 4 dispatcher-outbound-routing matrix tests; existing per-command tests extended in-place). Running total post-L7: 2799 + 4 = **2803**.

**L8 — `admits_inbound` → `AdmissionContext` refactor (Option B).** Substrate-touching atomic leg. **Call-site count is 5 production sites + a test-wrapper at `tests/test_connectors_acl.py:37` that proxies the public signature** (architect cycle-1 finding — initial estimate of "2-3 sites" undercounted the test surface).

Surfaces:
- `the_one/connectors/_acl.py` — define `@dataclass(frozen=True) class AdmissionContext` near the top with the 5 fields + `from_envelope(env: InboundEnvelope) -> AdmissionContext` classmethod. `InboundEnvelope` is already imported at `_acl.py:73`, so no circular-import risk. Change `admits_inbound`'s signature to `admits_inbound(account, agent_acl, ctx: AdmissionContext) -> tuple[bool, str]`. The function body unpacks the 5 fields from `ctx` and proceeds as before. Same `_admits_inbound_dm` + `_admits_inbound_guild` internal split (F12 L2 convention preserved).
- `the_one/connectors/_routing.py:180` — replace the 5-arg call with `admits_inbound(account, agent_acl, AdmissionContext.from_envelope(envelope))`.
- `the_one/connectors/_commands.py:108` (post-L1) — replace the now-correct 5-arg call with the same `AdmissionContext.from_envelope(envelope)` shape (single-line change after L1's plumbing is in).
- **`tests/test_connectors_acl.py:37-58` wrapper** — the test-helper `admits_inbound(account, agent_acl, peer_id, channel_id, **kwargs)` that translates flat-shape fixtures to v24 structured-tuple shape AND defaults `guild_id` to `DEFAULT_TEST_GUILD_ID` for non-DM contexts. L8 must migrate this wrapper. Two options:
  - **(a) Delete the wrapper; rewrite all ~8 test call sites** to construct `AdmissionContext` directly + pass the v24-shape agent_acl directly. Wider diff but cleaner final state.
  - **(b) Update the wrapper** to build `AdmissionContext` internally from the legacy kwargs + the guild_id default. Keeps existing tests readable in flat-shape; the wrapper is the adapter between legacy test conventions and the new ACL contract. Smaller diff; preserves test-readability.
  - Per F11 + F12's `test-translator-helpers-for-shape-evolution` convention (L1 of F13 codified), option (b) is the right shape — the wrapper is exactly the pattern that convention names.
- **Parallel `admits_outbound` wrapper at `:60-66`** — `admits_outbound` doesn't have an envelope (per F4 platform-send tool's no-context shape), so the AdmissionContext refactor doesn't apply to it directly. The outbound signature stays as-is per the `two-symmetric-paths-in-acl` convention (outbound has no envelope to construct a context FROM). The test wrapper for `admits_outbound` is untouched.
- `tests/_acl_shape_helpers.py` (F13 L1's shared helper module) — no signature change; the shape helpers still produce account/agent-acl shapes orthogonal to the ACL function's context shape.

Tests:
- Update the ~8 `_admits_inbound_real(...)` call sites that the wrapper proxies through to construct `AdmissionContext` (mechanical; wrapper still produces the v24-shape agent_acl).
- Add 1 new test class `TestAdmissionContextConstruction` verifying `from_envelope` correctly extracts `is_dm` (via plugin hook OR `envelope.raw.get`) / `guild_id` / `member_roles` from `envelope.raw` (defaults if absent). ~3 tests.
- **Wrapper migration decision: option (b) is the locked choice** (cycle-2 architect direction; aligns with `test-translator-helpers-for-shape-evolution` agents.md M11 convention). The L8 implementer keeps the wrapper as the adapter between legacy flat-shape test fixtures and the new ACL contract; no rewrite of the ~8 wrapper consumer sites.
- L8 backend test count: +3 = post-L7 2803 + 3 = **2806** (3 new AdmissionContext tests; existing ACL tests rewritten in-place via the wrapper update).

Phase 5c grep gate: `git grep -nE 'admits_inbound\(' the_one/ tests/` post-L8 returns ALL production call sites passing an `AdmissionContext` (or `AdmissionContext.from_envelope(...)`); zero hits with positional `peer_id, channel_id, ...` args at production sites. The wrapper's signature stays kwarg-based by design (it's a test-adapter).

**L9 — Behavior-test spec authoring (2 specs) + shared `discord.py` 2nd-bot driver implementation.** Per architect decision on behavior-test coverage, L9 authors TWO Witnessed specs that share the same 2nd-bot driver infrastructure. Decoupling them keeps the diagnostic signal sharp: an ephemeral regression points squarely at L7's substrate (not at "something somewhere in slash commands"). Surfaces:

- **`tests/behavior/discord-slash-end-to-end.md`** — covers the 6 slash commands' substantive behavior with explicit per-command ephemeral disposition assertions. `Cache:` directive: cold. Apparatus: `shell` (2nd-bot subprocess) + `http` (Discord REST cross-checks). 6 step rows, one per command:
  - `/whoami /agents /help` — Expected Result includes "driver reports the response payload's `flags` field includes bit `64` (EPHEMERAL); the responding bot's reply is visible **only to the invoking 2nd bot** (the driver's view), not to a passive observer session on the same channel."
  - `/talk_to <agent> /new /reset` — Expected Result includes "response payload's `flags` field does NOT have bit `64` set (`flags & 64 == 0`); the reply is **channel-visible** — a passive 3rd-party observer session on the same channel sees the message."
  - This binds the disposition to Discord's wire-level observable, NOT just to "response received". Per-command ephemeral verification protects L7's substrate from silent regression.

- **`tests/behavior/slash-command-ephemeral-routing.md`** — focused on L7's 4-cell substrate matrix (`CommandResponse.ephemeral` × `interaction_followup_token` present) + token-expiry fallback. `Cache:` directive: cold. Same apparatus. 4 step rows:
  1. ephemeral=True + valid token → `flags & 64 == 64`; reply absent from passive-observer session.
  2. ephemeral=False + valid token → `flags & 64 == 0`; reply visible to passive observer.
  3. ephemeral=True + token-expired (simulated via deliberate `>15min` delay OR driver's debug hook patching the token to a known-stale value) → reply appears channel-visible AND message text begins with `[ephemeral fallback]`; no exception surfaces in `docker logs the-one`; the `discord.errors.NotFound` caught + logged at INFO.
  4. ephemeral=False + no token (non-slash-originated path; driver sends a regular DM rather than slash invocation) → reply via normal channel send; `flags & 64 == 0`; no `[ephemeral fallback]` prefix.
  - **Intent**: verify L7 routes responses correctly across the 4-cell matrix AND the 15-min token-expiry fallback degrades gracefully. Exercises `_inbound.py:695-728` (dispatcher outbound branch) and `_discord.py:861-908` (slash-body token threading) end-to-end against real Discord. Witnessed pattern is the right tool — unit tests cannot observe Discord's `flags & 64` bit nor exercise real token expiry.

- **Shared 2nd-bot driver** — `tests/behavior/discord_slash_driver.py` (or sibling — implementer's call). Used by BOTH specs. The driver: logs in as the 2nd bot, sends a slash command via Discord's REST API (NOT the web client), waits for the responding bot's reply, returns the reply payload (incl. `flags` field) + visibility evidence (channel vs ephemeral observed via a passive-observer 3rd session) as JSON for the Executor to parse. Optional debug hook for token-stale-value injection (used by `slash-command-ephemeral-routing.md` step 3).

- **Spec preconditions** (BOTH specs):
  - 2nd Discord bot registered (a 2nd Discord application + bot user in Discord developer portal)
  - 2nd bot invited to test guild with `applications.commands` + `Send Messages` + `View Channels` scopes
  - 2nd bot's token in a `.env`-style file the driver points at (path documented in spec)
  - Passive-observer 3rd session — either a 3rd bot OR the operator's logged-in Discord client observing the test channel (operator's choice; spec documents both options)
  - The connector account's bot (bot A) has invited 2nd bot's user id to its allowlist (otherwise the 2nd bot's slash invocations get ACL-denied)
  - Both specs share a one-time setup checklist documented in `tests/behavior/SLASH-HAT-SETUP.md` (or co-located inside the first spec's Preconditions section)

- L9 doesn't add backend or browser tests directly — the 2 behavior-test specs ARE the new tests. Both run at L10.

**L10 — Operator-driven HAT + behavior-test runs.** Final gate. Surfaces:
- Operator runs the manual walkthrough of the 6 slash commands against their real Discord bot (per the F13 L6 walkthrough shape; now with all 4-bug-cluster fixes + ephemeral polish in place). Manual walk catches operator-perceivable UX issues (e.g. ephemeral message visibility from the operator's Discord-client perspective) that programmatic specs can't judge.
- Operator runs ALL 4 behavior tests in sequence (gates flight land):
  1. `/behavior-test connector-inference-provider-config-roundtrip` (F13 L4; re-run as regression gate) — expects PASS 8/8
  2. `/behavior-test audit-log-inspector-renders-routing-entries` (F13 L5; re-run as regression gate) — expects PASS 7/7
  3. `/behavior-test discord-slash-end-to-end` (NEW from L9; verifies all 6 slash commands + per-command ephemeral disposition) — expects PASS 6/6
  4. `/behavior-test slash-command-ephemeral-routing` (NEW from L9; verifies L7's 4-cell matrix + token-expiry fallback) — expects PASS 4/4
- All 4 spec verdicts + the manual walk must be PASS for F14 to land.
- HAT report appended to flight-log L10 entry (per the F13 L6 shape).
- If anomalies surface that are F14-caused (regression vs F13 baseline): fix in-leg. If pre-existing: file as Known Issue + defer.
- M11 criterion #10 marked `[x]` (fully closed) at L10 land; criterion #11 marked `[~]` (slash-commands-portion done; multi-user / pairing / mentions-aware portions remain for future flights).

### Checkpoints

- [ ] **L1 land**: backend at 2798 passed / 4 skipped / 0 errors; new `TestPermittedAgentsAgainstStructuredAllowlist` class with 2 tests passes; `git grep -nE 'admits_inbound\(' the_one/connectors/_commands.py` returns a call site passing all 5 required pieces of context.
- [ ] **L2 land**: backend at 2798 (unchanged); `git grep -nE 'config\.get\("guilds"\)|config\["guilds"\]' the_one/` returns 0 hits in source files; operator confirms `_sync_slash_commands` log line fires for the test guild at container restart.
- [ ] **L3 land**: backend at 2799 (+1 enumerate-test); browser at 455 (+1 picker-filter test); `enumerate_discoverable_entities` filters categories; the connector-editor picker shows only non-category channels.
- [ ] **L4 land**: browser at 460 (+5 L4-enh tests); `populateInferenceModelDropdown` has unit-test coverage for the 5 documented flows.
- [ ] **L5 land**: browser at 460 (unchanged); both pre-existing failures resolved to PASS (either product-fix or test-update; documented in flight-log).
- [ ] **L6 land**: `CLAUDE.md` has the Pydantic-class-caching note; no test changes.
- [ ] **L7 land**: backend at 2803 (+4 dispatcher-outbound-routing matrix tests); 3 self-only commands return `ephemeral=True` AND receive ephemeral responses via interaction-followup; 3 channel-affecting commands return `ephemeral=False` AND receive channel-visible responses; `_discord.py:877`'s unconditional defer becomes conditional (no more brief-ephemeral-then-channel inconsistency for the 3 channel-affecting commands); interaction-token expiry fallback to channel-send-with-prefix is exercised by 1 of the 4 matrix tests.
- [ ] **L8 land**: backend at 2806 (+3 AdmissionContext tests); `git grep -nE 'admits_inbound\(' the_one/ tests/` returns all production call sites passing `AdmissionContext.from_envelope(...)`; ACL public surface is `(account, agent_acl, ctx: AdmissionContext) -> tuple[bool, str]`; the test-wrapper at `tests/test_connectors_acl.py:37` migrated to build `AdmissionContext` internally (option b — keeps legacy test fixtures readable).
- [ ] **L9 land**: BOTH `tests/behavior/discord-slash-end-to-end.md` (6 rows, per-command ephemeral assertions) AND `tests/behavior/slash-command-ephemeral-routing.md` (4 rows, L7 matrix + token-expiry fallback) exist + are committed; shared `discord.py`-based 2nd-bot driver script exists + is committed; both specs status `draft` until L10 first PASS each.
- [ ] **L10 land**: operator's manual HAT report appended to flight log; all 4 behavior tests PASS (F13's 2 regression + L9's 2 new): `connector-inference-provider-config-roundtrip` 8/8, `audit-log-inspector-renders-routing-entries` 7/7, `discord-slash-end-to-end` 6/6, `slash-command-ephemeral-routing` 4/4; criterion #10 marked `[x]` in mission.md; both new specs' status flipped `draft → active` post-PASS.
- [ ] **Flight land**: combined diff reviewable; PR opened as draft; no new flakes; the 2 pre-existing-main browser failures resolved at L5 (no longer in the "since pre-F10" bucket); F13 debrief action items marked `[x]`.

### Adaptation Criteria

**Divert if**:
- L1's regression test surfaces additional missing-context call sites of `admits_inbound` beyond `_commands.py:108` — fold into L1, OR if scope doubles, split into L1a (Bug D fix) + L1b (regression tests covering all consumers).
- L5's diagnosis surfaces >3-day work for either pre-existing failure — divert into a separate maintenance flight + restore L5's scope to the smaller test (or rationalize-only).
- L8's refactor surfaces previously-undiscovered `admits_inbound` callers in dependency code (e.g. test helpers) — fold into L8 in lockstep.
- L9's 2nd-bot driver hits Discord rate-limit thresholds under sustained re-run — split into L9a (driver scaffolding) + L9b (rate-limit backoff + retry).
- L10's behavior-test surfaces F14-caused regressions in slash-command behavior — split into L10a (HAT documentation) + L10b (regression fixes).

**Acceptable variations**:
- L4 may absorb 1-2 additional defensive tests for `populateInferenceModelDropdown` flows the recon didn't enumerate (e.g. a network-failure-during-fetch test) — fold into L4 in lockstep.
- L7's ephemeral implementation may surface that `CommandResponse` needs a new field; verify the field is opt-in (defaults to channel-visible) so existing handlers don't accidentally flip.
- L8 may discover that `AdmissionContext.from_envelope` needs to handle pre-L4-era envelopes that don't carry `member_roles` in `raw` — default to `[]` per the existing pattern.

### Legs

- [ ] `bug-d-fix-permitted-agents-threads-envelope-context` — Bug D: `_permitted_agents` calls `admits_inbound` missing `is_dm`/`guild_id`/`member_roles` kwargs (broken since F7, latent until F12); thread them from `context["envelope"].raw`. +2 regression tests under `TestPermittedAgentsAgainstStructuredAllowlist`.
- [ ] `bug-b-fix-slash-sync-reads-allowlist-guilds` — Bug B: `_sync_slash_commands` switches from top-level `config.guilds` to nested `allowlist.guilds`; agents.md L4 narrative + Phase 5c grep gate enforce 0 orphan top-level readers.
- [ ] `bug-e-filter-categories-from-discoverable-entities` — Bug E: `enumerate_discoverable_entities` filters `type=category` channels; new substrate unit test + browser picker-filter test.
- [ ] `l4-enhancement-unit-test-backfill` — `populateInferenceModelDropdown` gets 3-5 browser tests covering the documented flows (Ollama + provider switch + custom-fallback + no-provider placeholder + GUI-clear-saves-null).
- [ ] `pre-existing-browser-failures-investigation-and-fix` — 2 pre-existing failures (4-flight deferred); investigate-at-implementation with flexible fix-or-update-assertions disposition.
- [ ] `bug-a-uvicorn-pydantic-reload-docs` — `CLAUDE.md` note on uvicorn `--reload` + Pydantic class caching + container-restart discipline.
- [ ] `slash-command-ephemeral-polish` — `/whoami`, `/agents`, `/help` flip to `ephemeral=True`; `/talk_to`, `/new`, `/reset` stay channel-visible. `CommandResponse` gains opt-in `ephemeral: bool` field.
- [ ] `admits-inbound-refactor-to-admission-context-dataclass` — define `AdmissionContext` frozen dataclass + `from_envelope` classmethod; `admits_inbound`'s signature becomes `(account, agent_acl, ctx)`; all call sites migrated; +3 AdmissionContext-construction tests.
- [ ] `behavior-test-specs-and-shared-2nd-bot-driver` — author TWO behavior-test specs inline (`discord-slash-end-to-end.md` covering all 6 commands with per-command ephemeral disposition assertions; `slash-command-ephemeral-routing.md` covering L7's 4-cell substrate matrix + token-expiry fallback) + implement the shared `discord.py`-based 2nd-bot driver. Both specs status `draft` at land; flip `active` at L10 first PASS each.
- [ ] `hat-and-behavior-test-run-against-real-discord` *(operator-driven; gated by all prior legs PASSING)* — operator runs manual walkthrough of 6 slash commands + all 4 behavior tests in sequence (F13's 2 regression + L9's 2 new); all 4 produce PASS; criterion #10 closes; HAT report appended to flight-log.

---

## Post-Flight

### Completion Checklist

- [ ] L1-L10 legs completed
- [ ] Code merged via squash-and-merge to main (matching F13's PR cadence)
- [ ] Backend test suite: **2806** passed / 4 skipped / 0 errors / 0 failures (L1 +2, L3 +1, L7 +4, L8 +3 = +10 net; L2/L4/L5/L6/L9 don't add backend tests)
- [ ] Browser test suite: **460** passed / 35 skipped / 12 deselected / 0 pre-existing failures (L3 +1 + L4 +5 + L5 resolves the 2 deferred)
- [ ] All 4 behavior tests PASS at L10: F13's 2 (`connector-inference-provider-config-roundtrip` 8/8 + `audit-log-inspector-renders-routing-entries` 7/7 — regression gates) + L9's 2 new (`discord-slash-end-to-end` 6/6 + `slash-command-ephemeral-routing` 4/4)
- [ ] `the_one/agents.md` L4 narrative reflects the post-L2 `allowlist.guilds` read path
- [ ] `the_one/connectors/_acl.py` has `AdmissionContext` dataclass; `admits_inbound` signature is `(account, agent_acl, ctx)`
- [ ] `the_one/connectors/_commands.py:_permitted_agents` calls `admits_inbound` with `AdmissionContext.from_envelope(envelope)`
- [ ] `the_one/connectors/_discord.py:_sync_slash_commands` reads `allowlist.guilds`; `enumerate_discoverable_entities` filters category-type channels
- [ ] `CLAUDE.md` has the uvicorn-Pydantic-reload note
- [ ] Mission outline `mission.md` Flight 14 entry marked `[x]` with one-line summary
- [ ] M11 criterion #10 closed (`[x]`); #11 marked `[~]` (slash-commands-portion of the HAT-as-artifact closes; multi-user / pairing / mentions-aware portions for future flights)
- [ ] F13 debrief action items closed: 4-bug cluster fixed (Bug C retired as false positive); L4-enhancement unit tests backfilled; 2 pre-existing browser failures resolved; Bug A docs note

### Verification

Five independent signals confirm the flight achieved its objective:

1. **Mechanical (grep)**:
   - `git grep -nE 'config\.get\("guilds"\)|config\["guilds"\]' the_one/` returns 0 hits in source files (post-L2)
   - `git grep -nE 'admits_inbound\(' the_one/ tests/` returns all call sites passing `AdmissionContext` (post-L8)
   - `git grep -nE 'enumerate_discoverable_entities' the_one/connectors/_discord.py` returns the filter for `type=category` (post-L3)
   - `git grep -nE 'ephemeral=True' the_one/connectors/_discord.py the_one/connectors/_commands.py` returns the 3 self-only commands' opt-in (post-L7)

2. **Regression (test suites)**: backend at 2806 passing / 0 errors / 4 skipped; browser at 460 passing / 0 pre-existing failures; all 4 behavior-test specs PASS at their final runs (F13's 2 regression + L9's 2 new).

3. **Semantic (ACL composition correctness)**: L8's AdmissionContext refactor — `admits_inbound` consumers in `_routing.py` + `_commands.py` build the context identically from envelope; the ACL function body is signature-only-changed (no semantic delta vs pre-L8). The `from_envelope` classmethod tests pin the contract.

4. **Witnessed UI flow (behavior tests)**: 4 specs PASS at L10 first run — `connector-inference-provider-config-roundtrip` 8/8 (F13 regression gate), `audit-log-inspector-renders-routing-entries` 7/7 (F13 regression gate), `discord-slash-end-to-end` 6/6 (L9 new; per-command ephemeral disposition observable via Discord's `flags & 64` bit), `slash-command-ephemeral-routing` 4/4 (L9 new; L7 4-cell substrate matrix + 15-min token-expiry fallback).

5. **Operator (manual HAT)**: operator-driven walkthrough of `/agents`, `/talk_to`, `/whoami`, `/new`, `/reset`, `/help` against real Discord on the test guild — all 6 commands behave per spec; the 3 self-only commands respond ephemeral; the 3 channel-affecting commands respond channel-visible. HAT report appended to flight-log L10 entry.
