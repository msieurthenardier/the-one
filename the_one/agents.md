# agents.md

Development-facing reference for the-one. This file **codifies decisions, contracts, and invariants** that aren't visible from reading the code. For module layout, exports, and dependency direction, read the code — `ls the_one/`, `grep`, and the package-level READMEs (`the_one/mcp/README.md`, `tests/CONVENTIONS.md`) are the truth.

For usage, commands, and conventions, see `CLAUDE.md`. For the security threat model, see `SECURITY-MODEL.md`.

---

## Architecture Overview

Four layers, bottom-up:

```
Interfaces (cli.py, web/app.py)         — user-facing shells
Agent (core.py, factory.py, ...)        — loop, config, persistence
Tools / LLM / MCP                       — peer subsystems
Config (config.py)                      — pydantic-settings singleton
```

Rules: `config.py` is the leaf (imported by everything, imports nothing). `llm/`, `tools/`, and `mcp/` are peers — none imports the others. `agent/` imports from all three. `interfaces/` only imports `agent/factory.py`. No circular imports.

---

## Project Conventions

Named project-wide patterns. Apply across the codebase, not only where they were first introduced. Reviewers flag deviations by name.

### Project-wide

### `trust-the-runtime`

Don't validate at the API layer what the runtime will catch with a clear error. Pre-validation duplicates the check, introduces TOCTOU windows, and bloats the surface translating good-enough runtime errors into hand-written API errors.

Applies whenever the runtime emits a clear, actionable error that can be matched + translated. Does NOT apply when the runtime's error is opaque (a generic `OSError` with no discriminator) — pre-check + named exception is the right call then.

### `canonical-import + convenience-re-export`

Each symbol has ONE canonical import path; lower packages MAY re-export for convenience. Code that touches the symbol's identity (subclassing, isinstance, exception handlers) MUST use the canonical path. Re-export, never re-define.

Example: `MCPSandboxError` is canonical at `the_one.mcp.errors`; `the_one.platform.sandbox.__init__` re-exports for convenience but the canonical import is `from the_one.mcp.errors import MCPSandboxError`.

### `structural-Protocol-satisfaction`

Classes structurally satisfy `runtime_checkable` Protocols WITHOUT inheriting from them. `runtime_checkable` already gives `isinstance` semantics; inheritance couples implementers to the Protocol's identity and forces no-op defaults across all implementers when the Protocol grows. Multiple unrelated classes can satisfy the same Protocol with zero retrofit.

### `verbatim-message-equality`

Error messages are tested via verbatim string equality (or substring `in str(exc)` when the message interpolates values), NOT regex. Verbatim equality pins the operator-facing wording, surfaces rephrasings as deliberate test updates, and avoids regex-overkill on string literals. Applies only to operator-facing error strings, not log messages or internal debug text.

### `gated-debug-instrumentation`

Debug-only / measurement-only modules are gated by **both** a URL query-string flag and a `localStorage` key, capture the enabled state at module-load time, and short-circuit to no-ops when disabled. Production pays zero cost; the gate survives SPA navigation. Two activation channels by design: URL is ad-hoc (no operator commitment); localStorage is sticky (survives reloads).

Reference: `App.perf` in `static/js/perf.js` — `?perf=1` or `localStorage.getItem('the-one-perf') === '1'`.

### `host-side-bench-drift-detection`

Targets that detect drift between the host bench and the canonical container run on the host (not `docker exec`), surface a clean diagnostic on failure, and are invoked manually (not on every dev iteration). Container-first tooling (`make test`, `make lint`) cannot see host venv drift.

Pattern: live under `# ── Drift detection (host-side) ──` in the `Makefile`; use `.venv/bin/python3 -c "..."` (NOT bare `python -c`, which has a PATH foot-gun); exit 0 if clean, non-zero with a clear `ModuleNotFoundError` / `AssertionError` if drift detected. Spec MUST include both a positive probe (clean → exit 0) AND a negative probe (deliberate violation → non-zero) — "clean tree exits 0" alone doesn't prove detection. For `git grep` recursive `**` pathspecs, use the `:(glob)` prefix; git's default mode treats `**` literally.

Reference: `make doctor`, `make audit`, `make audit-bytes`.

### `hat-driven-contract-flip-migration-discipline`

When a HAT iteration flips a previously-shipped contract (semantic, schema, or behavioral default), apply a three-part migration discipline: (i) preserve the original behavior as a backward-compatible read-side coercion path so existing data round-trips through the new shape without operator intervention; (ii) document the flip plus the rationale in the flight log Deviations section so reviewers can audit the contract change post-hoc; (iii) close out the read-side coercion in a follow-up flight with explicit deprecation language (the coercion is migration scaffolding, not a permanent compatibility shim). Distinct from `verbatim-message-equality` — that convention pins operator-facing error strings byte-for-byte; this one governs operational contract changes mid-mission.

Citation: M10 F6 HAT3 — the per-axis tri-state semantic flipped under operator review (legacy `match: str` form coerced in-place to the multi-value `match: list[str]` form on next save; deviation logged; coercion explicitly tagged for follow-up cleanup).

### `live-read-across-lazy-resolver-boundary`

When a provider field is **lazily resolved** on first call (sentinel → real value after a one-time upstream probe), every downstream consumer must read the field **live at the point of use**, not pre-capture it at the entry of a surrounding function. Eager capture sees the pre-resolution sentinel; the resolver fires later inside the provider call, but the captured local is never re-read.

Example: `LLMProvider.max_context_tokens` (Ollama queries `/api/show` once per model and caches on the instance). The contract is pinned by `test_usage_event_reflects_live_max_context_tokens_at_emission`.

Generalises to any field where the upstream value is unknown until a per-model / per-session probe completes. Lazily-resolved fields are owned by the provider and must be read through the provider, never copied across a function boundary.

### `container-test-entrypoints-reach-via-make`

Tests run in the container image (the canonical test environment). The `make test-*` targets chain required preconditions; raw `docker exec the-one pytest -m <marker>` bypasses them.

Concrete foot-gun: `make rebuild` wipes `~/.cache/ms-playwright/`; raw `docker exec the-one pytest -m browser` then produces hundreds of "Executable doesn't exist" errors. `make test-browser` chains `_ensure-playwright` (conditional re-install, no-op when present). Raw `docker exec ... pytest` is a debugging tool — fine for one isolated failure, wrong as the default invocation.

Before adding a NEW mitigation to a recurring foot-gun, audit whether the existing `make` chain already mitigates and the bug is in invocation form, not infrastructure form.

### `landmark-elements-over-aria-roles`

For shell-level navigation surfaces, prefer native HTML5 landmark elements (`<nav>`, `<main>`, `<aside>`, `<header>`, `<footer>`) over `<div role="...">`. Native semantics survive ARIA spec churn and tooling improvements; ARIA roles on generic containers carry the same semantic load but require explicit role-assignment plus dev-mode regression guards.

Canonical shape for active-item nav: `<nav aria-label="..."><ul><li><button [aria-current="page"]>item</button></li>…</ul></nav>`. Active-item toggle uses `setAttribute('aria-current', 'page')` on the new active + `removeAttribute('aria-current')` on the prior — NOT `setAttribute('aria-current', 'false')` (ambiguous to AT). `role="listbox"` is INVALID when descendants are interactive (`<button>` inside `role="option"`); use `<nav>` + `<ul>` + `<button>` with `aria-current` instead.

**Selector-continuity tax**: when a leg restructures DOM (changing the container element, ARIA roles, or class hierarchy), distinguish **class-name preservation** (lexical — the class still exists) from **selector-continuity preservation** (structural — descendant/sibling selectors still resolve). Class names can survive a `<div>` → `<nav>` change while `.parent .child` descendant selectors silently break. Pre-edit, enumerate test selectors touching the restructured surface and mark each as SURVIVES or UPDATES.

### `function-local-import-to-break-load-cycle`

When two modules transitively import each other (e.g. `connectors/_pool.py` ↔ `db/repositories.py` via `agent/__init__.py` → `agent.core` → `mcp.errors` → `mcp/__init__.py` → `mcp/_pool.py` → back to `repositories.py`), top-level imports can fail with `ImportError` if the cycle is initiated from one entry but not another. The fix is **function-local imports at the call site**: defer the cycle-crossing import to runtime so module load completes cleanly, regardless of which module the importer reaches first. Apply this pattern when (and only when) the cycle is real and load-order-dependent — at the top-level when no cycle exists, prefer the top-level form. Every function-local import that exists to break a cycle MUST carry an inline comment naming the cycle so future readers can verify the motivation.

Citations:
- `db/repositories.py: MCPSourceRepository.find_by_runtime_package` — `from the_one.mcp.cache_cleanup import extract_runtime_package` inside the function body, with the inline comment "Local import to avoid a circular: cache_cleanup is in the_one.mcp, which transitively imports db modules through other helpers."
- `connectors/_pool.py: _load_account` — `from the_one.db.connection import get_connection` + `from the_one.db.repositories import ConnectorAccountRepository` inside the function body, with the docstring block explicitly tracing the `repositories.py` → `mcp/__init__.py` → `mcp/_pool.py` → `repositories.py` cycle and noting that `mcp/_pool.py` only avoids the failure because its callers always prime the cycle via `the_one.mcp` first.

Pattern is at the 2-occurrence threshold pending a clearer 3rd documented occurrence. The function-local imports in `mcp/_pool.py` are not load-cycle-breaks (no inline comment documenting the motivation; `mcp/_pool.py` already imports `the_one.db.repositories` at the top level cleanly) and are deliberately excluded from this citation list — naming the pattern matters more than padding the count.

### `optional-plugin-hook-via-getattr-sentinel`

An optional plugin extension that not every plugin needs to provide is accessed via `getattr(plugin, "<hook_name>", None)` with a sensible fallback at the call site. The Protocol stays at its minimal shape; future plugin authors aren't forced to write no-op stubs. The consumer's exception-catching behavior tolerates plugin-raised exceptions and falls back. Distinct from `protocol-widening-for-required-capability` (see below) which applies when ALL plugins in scope must implement the method. The fallback may be `None` (consult site short-circuits — `display_channel`'s shape) OR a named callable that returns the default outcome (when the default outcome is structured — F6's `_default_permit` returns a `Permit()` instance).

Citations: `the_one/connectors/_session.py:_derive_title` accesses `plugin.display_channel` via `getattr(plugin, "display_channel", None)` with try/except fallback to `envelope.channel_id`; `StubPlugin` implements `display_channel` (`the_one/connectors/_stub.py:display_channel`), other plugins don't need to. F6's `the_one/connectors/_inbound.py:dispatch_inbound` consults `plugin.resolve` via `getattr(plugin, "resolve", _default_permit)` for per-(peer, channel) ACL resolution (`_default_permit` returns a `Permit()` sentinel; `StubPlugin` opts in via `_stub.py:resolve`). F8 L6's `the_one/connectors/_routing.py:_agent_admits` consults `plugin.is_dm` via `getattr(plugin, "is_dm", _default_not_dm)` for the per-agent DMs-only ACL branch in `_acl.py:admits_inbound` / `admits_outbound` (`_default_not_dm` at `the_one/connectors/_acl.py:_default_not_dm` returns False, preserving fail-closed back-compat for plugins without the hook — e.g. the test-only stub; `DiscordPlugin.is_dm` opts in via `the_one/connectors/_discord.py:DiscordPlugin.is_dm`).

### `per-axis-tri-state-override`

When an allowlist or ACL composes multiple independent axes (peers, channels, guilds, roles, …), each axis carries an independent **tri-state**: **absent** ⇒ unrestricted on this axis; **`[]`** ⇒ unrestricted on this axis at account scope, with per-agent narrowing free to override; **non-empty list** ⇒ subset allowed. The composition across axes is **per-axis AND, not single-list AND** — an inbound is admitted only when every axis admits independently. Per-agent overlays narrow per-axis on top of the account scope using the same tri-state.

Citations: `the_one/connectors/_acl.py:admits_inbound` (F6 — account-scope admission across `peers` + `channels`); F8 L8 extends with `guilds` + `roles` axes for the Discord plugin (third occurrence — the framing generalizes naturally across connectors that distinguish workspace-style and role-style axes).

### `protocol-widening-for-required-capability`

When a capability moves from "future" (one plugin needs it, others don't) to "required" (every plugin in scope must implement it), widen the `runtime_checkable` Protocol additively rather than reaching for `getattr`-sentinel. The widening is non-breaking for existing `isinstance(...)` checks at the type level — Python's `runtime_checkable` Protocol checks method-name presence at call time, so existing implementers that satisfy the pre-widened shape continue to pass UNLESS they're missing the newly-required method (in which case the isinstance check correctly fails and surfaces the gap). Implementations still MUST NOT inherit from the Protocol — structural satisfaction is the rule (`structural-Protocol-satisfaction` convention).

Citation: `the_one/connectors/base.py:ConnectorClient.send` widening (F4 leg 1) added `async def send(target: OutboundTarget, content: str) -> SendResult` to the existing 1-method `ConnectorClient` Protocol. Every connector in scope (stub, Discord at F8, second connector at F9) MUST implement `send`; the platform-send tool depends on it being callable. F4's choice contrasts with the `optional-plugin-hook-via-getattr-sentinel` convention used for `display_channel` — outbound has no sensible default (silent drop is leakage; raise is noise) so widening is structurally right.

### `cross-subsystem-pattern-premise-revalidation`

Every "mirror X" rationale invoked in a design must include an explicit paragraph: "the original design rests on premise P; does P hold here?" Pattern-transfer without premise validation ships defects that survive design review. Reviewers must demand the premise-revalidation paragraph before approving any cross-subsystem mirror.

Applies to any cross-subsystem pattern reuse where the precedent's premise is implicit. Does NOT apply to local refactors within a subsystem — a single-subsystem change can mirror its own siblings without re-deriving the premise.

Citation: `the_one/connectors/_pool.py` — F1 mirrored `mcp/_pool.py`'s per-agent pool keying without re-validating the gateway-protocol-vs-MCP premise mismatch (gateway protocols are one-IDENTIFY-per-token; per-agent keying is incompatible). The mismatch surfaced at F8 L11 HAT seven flights after the original commit; that flight shipped a sentinel-wrapper as a tactical patch. M11 F2 L2 closed the convention's loop by splitting the public API into two semantic primitives: `the_one/connectors/_pool.py:agent_acquire` (MCP-style per-agent keying for the F6 resolver pattern) and `the_one/connectors/_pool.py:account_acquire` (gateway-protocol account-keyed, one entry per account). The proper refactor invoked this convention by name; the citation here documents both the original violation and the eventual resolution.

Source: M10 mission-debrief "Process §2" — codify `cross-subsystem-pattern-premise-revalidation`; also listed in "Action Items → Codify 6 new agents.md Project Conventions."

### `prompt-discipline-needs-mechanical-fallback`

Any agent behavior the system depends on but the LLM controls requires either empirical HAT validation against the production model OR a mechanical dispatcher-side fallback that enforces the behavior without relying on prompt compliance. Decision-only (prompt-only) paths are not production contracts — LLM directive compliance is not a contract the system can build on.

Applies to any system-level invariant whose enforcement passes through the LLM (outbound channels, tool-call-mandatory flows, content-filter directives). Does NOT apply to UX-only directives that fail soft if ignored (style guidance, persona instructions).

Citation: `the_one/agent/config.py:_CONNECTOR_TOOL_ENABLED_DIRECTIVE` at lines ~54-67 — the original F4 directive "MUST call the `send_to_platform_channel` tool to deliver your reply." Sonnet 4.7 ignored the directive at F8 L11 HAT (twice, with strengthened versions). F8 L11 Fix #4 shipped the mechanical fallback at `the_one/connectors/_inbound.py:711` — `auto_relay = account.config.get("auto_relay_platform_replies", True)` defaults ON and the dispatcher auto-relays the assistant text via `client.send` regardless of whether the tool was called.

Source: M10 mission-debrief "Process §3" — codify `prompt-discipline-needs-mechanical-fallback`; also "Lessons Learned §11" (LLM directive compliance is not a production contract).

### `mechanical-fallback-prompt-truth-pairing`

When a mechanical fallback ships alongside a system-prompt directive (per `prompt-discipline-needs-mechanical-fallback`), the prompt must accurately describe the actual behavior the dispatcher delivers. Lying in the prompt about what auto-runs (e.g., still saying "MUST call tool X" when the dispatcher now auto-relays anyway) confuses LLMs trained for honesty and produces hedging / over-explanation. The directive and the dispatcher's truth ship in the same diff.

Applies whenever a mechanical fallback exists for a behavior the system-prompt also describes. Does NOT apply when the dispatcher honors the original prompt's contract verbatim (no fallback divergence).

Citation: `the_one/agent/config.py:_CONNECTOR_AUTO_RELAY_DIRECTIVE` at lines ~69-84 — F8 L11 Fix #4 shipped the paired directive when auto-relay is ON: "Auto-relay is ON: your plaintext replies in this session ARE automatically delivered to platform peers." The original `_CONNECTOR_TOOL_ENABLED_DIRECTIVE` survives at lines 54-67 for the (currently unreachable but conceptually distinct) "tool-mandatory-no-auto-relay" composition; `compose_system_prompt` at `the_one/agent/config.py:96+` selects between them via the `auto_relay: bool` parameter. Distinct from `hat-driven-contract-flip-migration-discipline` — that convention governs schema/contract flips at HAT; this one governs prompt/dispatcher pair synchronization.

Source: M10 mission-debrief "Documentation §1" — companion to `prompt-discipline-needs-mechanical-fallback`; also "Lessons Learned §4" (Auto-relay default-on with a mechanical fallback is the right shape for bot UX).

### `lifespan-wiring-same-leg-as-installation`

Event-handler installation (registering a handler that depends on application-level state) and the lifespan-time call site that triggers it land in the same leg, OR the leg's acceptance criteria include a runtime end-to-end test exercising the installed handler. Installing a handler without wiring the lifespan that fires it leaves the entire code path unreachable in production — silently, until somebody triggers the handler end-to-end.

Applies to any event-driven handler (gateway listeners, periodic sweeps, background workers, lifespan-startup callbacks) that depends on application-level dependency injection. Does NOT apply to handlers wired into a synchronous import path that runs at module-load. The pattern is connector-agnostic and applies project-wide to any lifespan-driven handler.

Citation: F8 L4 installed Discord's `on_message` at `the_one/connectors/_discord.py:DiscordPlugin.connect` (line ~731) but deferred lifespan-time `pool.acquire(...)` wiring to L11; the entire L4 inbound code path was end-to-end unreachable in production until F8 L11 Fix #3 added the lifespan walk. The canonical wiring shape: `the_one/agent/factory.py:set_factory` at line ~168 (module-level accessor) consumed by `the_one/interfaces/web/app.py` lifespan startup at line ~88 (`_set_module_factory(_state["factory"])`); gateway listeners call `get_factory()` at dispatch time per the convention codified in the "Gateway-listener factory access (M10 F8 L4)" subsection below.

Source: M10 mission-debrief "Process §6" — add `lifespan-wiring-same-leg-as-installation` to `/leg` and `/flight` design guidance; also "Methodology Feedback §4."

### `atomic-leg-pattern`

When a single contract change touches multiple coordinated sites (Pydantic field + DB migration + repository CRUD + downstream ripple-sites that load or persist the value), all sites land in the same leg. Splitting the contract across legs leaves intermediate commits where one half of the contract exists without the other — the column exists in the schema but the Pydantic model doesn't know to write to it, or the model has the field but the repository drops it on save.

Applies whenever a contract change crosses two or more of {Pydantic schema, DB schema, repository codec, runtime consumer that reads the value}. Does NOT apply to contract-additive changes that are fully optional at every site (e.g., adding a Pydantic field with a default that no existing consumer reads).

Citations (n=2 — pattern is at codification threshold per `function-local-import-to-break-load-cycle` precedent):
- F4 L5: `AgentConfig.connector_account_ids` field landed alongside schema v17 migration, `AgentConfigRepository` insert/load codec, and `AgentFactory.create` consumer in a single leg. See `the_one/db/_connector_types.py:22` — "v17 → ``agents.connector_account_ids`` persistence (F4 L5)".
- F6 L1c: `AgentConfig.connector_acls` field landed alongside schema v18 migration, `AgentConfigRepository` codec, and `_acl.admits_inbound` consumer in a single leg. See `the_one/db/_connector_types.py:22` — "v18 → ``agents.connector_acls`` persistence (F6 L1c)".

Source: M10 mission-debrief "Documentation §1 (Architect addition)" — `atomic-leg-pattern` (Pydantic field + migration + repository + ripple-sites in one leg; F4 L5 + F6 L1c are n=2); also "Methodology Feedback §8."

### `optional-registry-entry-hook`

When a registry entry needs to participate in substrate machinery — dirty tracking, namespace exposure, lifecycle hooks, render-time integrations — add OPTIONAL function fields to the entry's contract, validated as "must be a function IF present" but absent without error. Required entry fields are the render-time contract (the substrate calls them to produce the entry's per-type UI); optional fields are substrate-integration opt-ins (the substrate calls them when its machinery has work to dispatch to the entry, but absence means "this entry doesn't participate at that integration site"). The validator extends linearly: a new optional hook adds one name to an `optionalFns` list, no structural validator change.

Applies when a registry/dispatch primitive owns substrate-touching machinery (event listeners, snapshot serialization, lifecycle callbacks) where some per-type entries opt in and others don't. Does NOT apply to dispatch tables where every entry must implement every method (use Protocol-widening then; see `protocol-widening-for-required-capability`).

Citations (n=5 from M11 F1+F2+F3):
- `the_one/interfaces/web/static/js/areas/studio/connector-form-registry.js:_validateEntry` — the `optionalFns = ['snapshot', 'wireEvents', 'renderInviteSection', 'renderDirectiveSection', 'renderDiscoverableDropdown']` array; each name is an optional entry-shape hook. The per-name validation is "must be a function IF present" — absent without error.
- F1 L4 added `snapshot(container) → object` (entry's typed-input state for dirty-tracker) + `wireEvents(container, checkDirty, account)` (entry's own listener wiring for typed inputs outside the substrate's delegation scope). See `the_one/interfaces/web/static/js/areas/studio/connector-form-discord.js:snapshot` and `:wireEvents`.
- F1 L5 added `renderInviteSection(account) → string` (entry-rendered detail-page section). See `the_one/interfaces/web/static/js/areas/studio/connector-form-discord.js:renderInviteSection`.
- F2 L4 added `renderDirectiveSection(account) → string` (entry-rendered System Prompt Directive section on the General tab). See `the_one/interfaces/web/static/js/areas/studio/connector-form-discord.js:renderDirectiveSection`.
- F3 L5 added `renderDiscoverableDropdown(account, axis, currentValues, vocab, onChange) → HTMLElement | null` (entry-rendered live-data combobox for allowlist + routing surfaces). See `the_one/interfaces/web/static/js/areas/studio/connector-form-discord.js:renderDiscoverableDropdown` and the shared component at `the_one/interfaces/web/static/js/areas/studio/discoverable-dropdown.js`.

Source: M11 F1 flight-debrief "Key Learnings §3" (the F1 added three optional hooks; the additive-extension shape is generalizable) + "Recommendations §2" (operator-confirmed codification at debrief).

### `registry-dispatch-create-mode-AC`

Any registry-mediated typed-render path requires BOTH "create-mode-after-dispatch-key" AND "edit-mode-with-dispatch-key-set" as explicit acceptance criteria. The dispatch key (the value the registry uses to pick a per-type entry — connector type, provider type, plugin type) may be absent at first render in create mode and only populated when the operator picks it; the AC must verify that the post-pick render produces the typed entry's content, not the substrate's fallback. Edit-mode tests alone are insufficient — they exercise the dispatch-key-set path and miss the dispatch-key-absent-then-set transition that operators actually hit.

Applies when a registry/dispatch primitive renders different content based on a dispatch key that may be absent on first render (operator-picked type in a create form; post-fetch resolved key in an async-populated editor). Does NOT apply when the dispatch key is structurally guaranteed at mount (e.g., the key is part of the URL route fragment and a renderer is mounted at all only when the key is present).

Citation (n=1 from M11 F1 L7, codified by methodology-promotion per F1 debrief Recommendations §2 — operator-confirmed): F1 L4's tests exercised only edit-mode-with-type-set; the create-mode-after-type-pick path was bug-prone because `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js:renderConnectionFields` zeroed the dispatch key (`connActiveType`) in create mode regardless of the operator's pick, so `registry.get('')` always returned undefined and the substrate fallback rendered instead of the typed entry. HAT-caught at F1 L7; the fix removed the create-mode zeroing and added a `forceCreate` 5th-arg type-change re-render path (see `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js:renderConnectorAccountEditor`) so picking Discord re-mounts the editor against the typed entry. The resolution test `tests/browser/test_flow_studio_connector_account_create_and_test.py:test_create_mode_pick_discord_renders_typed_form` now pins the AC.

This is the first codification under the n=1-by-methodology-promotion shape — the F1 debrief elevated this convention on the strength of the methodology lesson (registry-mediated dispatch is a structural pattern that demands symmetric ACs), not on a recurring-pattern threshold. Future occurrences citing this convention re-validate the structural claim; if they don't, the convention is a candidate for retirement at a later mission debrief.

Source: M11 F1 flight-debrief "Recommendations §2" + "Key Learnings §5" (HAT essential signal even at the end of autonomous flights) + F1 L7 leg-progress entry.

### `primitive-rename-test-classification`

When a leg spec touches a primitive's name (rename, split, consolidation), every test file that contains the primitive's name is default-classified as `code-update` — i.e., the leg must read the test to determine whether the rename ripples into functional code. Downgrade to `docstring-sweep` (the rename only changes prose in test docstrings) ONLY after `grep` verifies the name appears solely inside `"""..."""` docstring blocks across the entire file. The cycle-0 default of "docstring-sweep until proven otherwise" inverts the safe direction — it treats a name appearance as docstring noise until refuted, when the truth-table is the opposite (a name appearance is functional usage until refuted).

Applies whenever a leg's scope includes renaming, splitting, or consolidating a named primitive (function, class, dataclass, constant, or method) that is referenced by tests. Does NOT apply to leg-internal symbol renames whose names never appear in test files (grep returns zero hits in `tests/`).

Citations (n=1 trigger, n=3 evidence files from M11 F2 L2 cycle-1):
- `tests/test_connectors_inbound.py` — monkeypatch + sentinel filter (functional, ~5 lines).
- `tests/test_lifespan.py` — getattr/setattr sites + assertion (functional, multi-site).
- `tests/test_connectors_e2e_platform_send.py` — monkeypatch + assertion + function rename (functional).

Source: M11 F2 flight-debrief "Recommendations §Important — codify two methodology rules as agents.md project conventions" (convention 1) + "What Could Be Improved §Important — primitive-rename test classification rule."

### `flight-spec-dom-order-audit`

At flight-design time, when a flight or leg artifact's natural-language wording describes adjacency between rendered DOM sections (e.g., "between section X and section Y" in Design Decisions, leg objectives, or implementation guidance), the architect must re-walk the current DOM order in the live source before committing the wording. Memory of a prior DOM walk is unreliable across flight boundaries — sections may have been added, removed, or reordered between the original audit and the current flight-design session.

Applies whenever a flight or leg artifact's natural-language wording describes adjacency between rendered DOM sections (Studio editor sections, Chat UI panels, settings sub-pages, connector account detail page sub-surfaces). Does NOT apply to logical ordering claims that are not DOM-rendered (file ordering in a directory, leg execution ordering within a flight, mission flight ordering).

Citation (n=1 from M11 F2 L4 cycle-1, codified by methodology-promotion per the same F1-L7-derived precedent as `registry-dispatch-create-mode-AC`): F2 flight.md Design Decisions §3 originally claimed the directive section landed "between Pairing and Test Connection," but a fresh DOM walk at cycle-1 showed Attached Agents between Pairing and Test Connection in the current source, so the correct placement was "between Pairing and Attached Agents." The reviewer caught the divergence; the leg spec was reworded to match the actual DOM; no structural harm done at L4 itself, but the symptom indicates the flight spec was written without a fresh DOM-order audit.

Source: M11 F2 flight-debrief "Recommendations §Important — codify two methodology rules as agents.md project conventions" (convention 2) + "What Could Be Improved §Minor — flight-spec wording drift from DOM order."

### Mission-specific (M10)

Patterns that emerged in Mission 10 (bi-directional comms connectors) whose project-wide generalization has not yet been demonstrated. They live here until a second-mission citation lifts them into `### Project-wide` above. Future missions extending this file add their own `### Mission-specific (M{NN})` subsection per the same pattern.

### `encryptor-parameter-receive-but-not-consume`

A plugin Protocol method receives an `Encryptor` parameter but does not call it because the repository's contract already delivers plaintext secrets in `account.secrets[...]`. The parameter is present to satisfy the Protocol signature and to allow future plugins that need encryption-aware paths to opt in, NOT because every call site decrypts. Each receive-but-not-consume call site documents the contract in its docstring so reviewers and future authors don't reintroduce a double-decrypt.

Applies to any plugin where the repository already performs the encryption boundary crossing (`ConnectorAccount`, `MCPSource`) and hands the plugin already-decrypted secrets. Does NOT apply when the plugin is itself the encryption boundary (e.g., a future plugin that handles per-call ephemeral key derivation).

Citation: `the_one/connectors/_discord.py:DiscordPlugin.connect` — the docstring at line ~596 explicitly states "`encryptor` parameter is received to satisfy the F1 Protocol but not consumed at this site"; same pattern at `the_one/connectors/_discord.py:DiscordPlugin.doctor` (docstring at line ~1077).

Source: M10 mission-debrief "Documentation §1" — F8 L11 BOT_TOKEN double-decrypt bug (the spec said `encryptor.decrypt(account.secrets["X"])` but the repository had already decrypted; the convention prevents the recurrence). Tagged "Mission-specific (M10)" because M10 debrief Documentation §1 explicitly calls it "M10-specific shape; project-wide principle" — the project-wide form ("repository contract delivery is part of any Protocol's contract") is captured by `cross-subsystem-pattern-premise-revalidation` above.

---

## Subsystem contracts

These sections record decisions and invariants. Module layout, exports, and per-file behaviour live in the code and package-level READMEs (especially `the_one/mcp/README.md`).

### Encryption rotation invariant

`POST /api/encryption/rotate` re-encrypts ALL provider credentials AND ALL MCP source secrets in a single crash-safe transaction, commits the DB, then atomically replaces the key file via `os.replace`. The single-pass rotation is authoritative: a partial rotation that handled only one of the two surfaces would leave the other encrypted under a key no longer on disk.

### `__MASKED__` sentinel (LLM providers)

The provider edit form sends the literal string `__MASKED__` for unchanged `api_key` values. `update_provider` in `interfaces/web/api.py` detects this sentinel and preserves the stored value. Anyone touching the provider edit form needs to know this contract.

The same form-side validator (`_is_safe_provider_url`) must run on the **resolved** `base_url` post-`model_copy(update=data)`, not on the request payload — `__MASKED__` would otherwise fail validation.

### MCP source secrets storage

`mcp_sources` (schema v10) uses **field-segregated encryption with two columns**: `config TEXT` holds plaintext non-sensitive fields (transport-aware: `command`/`args`/`env` for `'stdio'`, `url`/`headers` for `'streamable-http'`); `secrets TEXT` holds a single Fernet-encrypted JSON blob whose decoded value is a dict of operator-marked sensitive field values. Encryption is per-row (one `Fernet.encrypt/decrypt` per row), NOT per-field inside the JSON.

The repository stores the `Encryptor` **as a reference, not a copy**, so post-rotation `install_key()` propagates to live repository instances.

**Per-key `__MASKED__` semantics**: GET returns `{secrets: {key: "***...{tail4}", ...}}` with each VALUE masked individually. On PUT, `secrets[key] == "__MASKED__"` preserves the existing stored value for that key; other keys overwrite.

**OAuth-managed secret keys**: `dcr_credentials`, `access_token`, `refresh_token`, `token_expires_at`. Written exclusively by `MCPSourceTokenStorage`; stripped + preserved on PUT by the API layer's `_OAUTH_MANAGED_SECRET_KEYS` logic.

### MCP F2 Client Foundation (authoritative for F3+)

1. **Module layout** — `the_one/mcp/` is a peer of `the_one/llm/`, NOT a sub-package of `the_one/tools/`. `MCPClient` is a service abstraction; `MCPToolProvider` wraps individual `MCPTool`s into the project's `Tool` abstraction.

2. **`_PINNED_PROTOCOL_VERSION`** — Defined in `the_one/mcp/__init__.py`. **Read at call time** via `the_one.mcp._PINNED_PROTOCOL_VERSION`, NOT `from the_one.mcp import _PINNED_PROTOCOL_VERSION` — the latter binds at module-load time and breaks `monkeypatch.setattr` in tests. Upgrade procedure: bump SDK pin → re-read `LATEST_PROTOCOL_VERSION` → update the constant → run `test_pinned_protocol_version_matches_sdk`.

3. **Pool-compat invariants** — `MCPClient` exposes `is_alive: bool` (false until `connect()` returns, false from `disconnect()` start) and `last_activity: float` (monotonic, updated per `list_tools`/`call_tool`). `disconnect()` is **idempotent and never raises**. No thread-locals, no module-globals. Naming is aligned with `PtySession` so the pool builds one reaper code path.

4. **`build_stdio_environ`** — `(source, allowlist_env) -> dict[str, str]` performs a 2-layer flat merge: `allowlist_env ∪ (config.env ∪ secrets)`, secrets winning on collision. **Do NOT consume `MCPSource.merged_config()`** for stdio env assembly — that helper produces a flat top-level merge that would inject `command`/`args` as env-var-shaped keys.

5. **Fail-hard version handshake** — `connect()` raises `MCPVersionMismatch` when `protocolVersion != _PINNED_PROTOCOL_VERSION` (exact match required). Narrower than the SDK's `SUPPORTED_PROTOCOL_VERSIONS` whitelist; the SDK's own `RuntimeError` is caught and re-raised as `MCPVersionMismatch` so operators see one error type. Pre-release stance; revisit at 1.0.

For runtime invariants (test-seam pattern, AsyncExitStack composition, `_DEFAULT` sentinel rationale, env-var assembly, sandbox-wrap composition, pool semantics), see `the_one/mcp/README.md`.

### MCP F3 Sandbox (authoritative for F4+)

1. **Strict-by-default trust** — Locally-spawned stdio MCP servers run in a bubblewrap jail: read-only filesystem outside an operator-configured `writable_paths` list; network OFF unless `network_allowed=True`. Operator-trust threat model: the sandbox does not defend against operator mistakes (broad `writable_paths`, `network_allowed=True` on untrusted sources), only against MCP-author mistakes / supply-chain compromise within the sandboxed scope.

2. **Profile storage** — `MCPSource.config["sandbox"] = {"writable_paths": list[str], "network_allowed": bool}` lives plaintext alongside `command`/`args`/`env`. Both fields optional; defaults `[]` and `false`. Namespace-flag fields (`pid_unshare`, `ipc_unshare`, `uts_unshare`, bool-defaulting-True) are JSON-edit-only advanced knobs — API validator passes them through unchanged.

3. **`MCPSandbox` Protocol** — `prepare_spawn(profile, command, args, env, cwd=None) -> SpawnSpec`. `SpawnSpec` is `@dataclass(frozen=True)` with `command/args/env/cwd` plus Windows-only `creation_flags: int = 0` and `attribute_list`. Windows fields exist purely so a future backend can populate them without changing the Protocol.

4. **`MCPSandboxError` boundary** — Failures BEFORE bwrap successfully wraps-and-execs raise `MCPSandboxError` (bwrap missing, writable_paths entry doesn't exist, `EPERM` on `unshare`, container lacks §10 privilege grants). Failures AFTER (target spawned but exits non-zero, init handshake fails) raise `MCPConnectionError` / `MCPVersionMismatch`. NO unsandboxed fallback in production; `THE_ONE_SANDBOX_DISABLED` is never read in production paths. Catalog messages (operator-facing, verbatim-tested) live in `the_one/mcp/errors.py`.

5. **Privilege model** — Dev container: `cap_add: [SYS_ADMIN]` AND `security_opt: [seccomp:unconfined]` (BOTH — SYS_ADMIN alone is filtered by docker's default seccomp profile). Browser-test CI: no privilege grants; `THE_ONE_SANDBOX_DISABLED=1` AND `THE_ONE_TEST_MODE=1` (BOTH; set ONLY by `tests/conftest.py::pytest_configure`). Production: no flags — bwrap is mandatory.

   **Operational guardrail**: `THE_ONE_TEST_MODE` MUST NOT appear in any Dockerfile, compose env, entrypoint script, k8s manifest, or CI variable. Presence outside pytest is a deployment defect.

6. **HOME override** — `BubblewrapSandbox.prepare_spawn` forces `env["HOME"] = "/tmp"` regardless of operator config. Reasoning: inherited HOME (`/root` in dev) becomes read-only-but-not-writable under `--ro-bind / /`; subprocess writes to `~/.cache` would EACCES; `/tmp` is writable via `--tmpfs`. Operators cannot override HOME via kv-table — sandbox policy, not configurable.

### MCP error translation

`MCPClient.{connect, list_tools, call_tool}` raise one of: `MCPVersionMismatch`, `MCPAuthRequired`, `MCPSandboxError` (stdio only), or `MCPConnectionError` (catchall). `MCPToolProvider.get_tools_for_agent` graceful-skips all four. Adding a fifth typed exception requires updating BOTH the translator AND the consumer's match list.

**Nested `try/except*` in `connect()`** — Python (PEP 654) forbids mixing `except` and `except*` in one block. The OAuth `except*` nests inside an inner `try` so the version-mismatch `except RuntimeError` can stay flat. `list_tools`/`call_tool` use a flat shape because they have no `except` siblings. Don't "tidy up" the asymmetry.

**Three 401 sources in `connect()`** — inner `except* (OAuthFlowError, OAuthTokenError)`, outer `BaseExceptionGroup.subgroup(httpx.HTTPStatusError)` walk, and `except asyncio.CancelledError` (narrowed to non-OAuth/non-401 only). Narrowing is preserved by comments; don't collapse them.

**`MCPAuthRequired` propagation** — `connect()`'s outer `except (MCPClientError, NotImplementedError): … raise` already propagates `MCPAuthRequired` cleanly. `list_tools`/`call_tool` DO need an explicit `except MCPAuthRequired: raise` guard because their outer `except McpError` would re-wrap. Asymmetry by design.

**Synthetic csid pattern** — Three csid shapes pass through `oauth/handlers.py::redirect_handler`: real csids (12-char hex), `f"test:{source_id}"` (Test connection endpoint), `f"agent_build:{source.id}"` (pool entry-worker). Disjoint by character-set construction — hex cannot produce `:`. Synthetic csids no-op the `auth_required` broadcast.

### Tool authorship contract (F4+)

Tools subclass `Tool` and declare:

- `Config: type[BaseModel]` — per-tool config schema (per-category Config classes: `FilesystemConfig`, `ExecutionConfig`/`PythonExecConfig`, `WebConfig`).
- `Requires: tuple[type[BaseModel], ...]` — opts into the shared `cross_configs` view.
- `__init__(config, cross_configs=None, agent_name=None)`.
- `execute(**kwargs) -> str`.

The two-clause `try/except` envelope (catch `ConstraintError` → `[error] [constraint] {e}`, catch other exceptions → `[error] {e}`) IS the authorship contract. `ConstraintError` lives at `the_one.tools.base` (canonical) for that reason.

**Tool policy resolver** (`the_one/tools/resolver.py`) composes tool-level config with agent-level overrides per per-key marker semantics on the tool's `Config` schema:

- `Annotated[type, Narrow]` — agent override must not widen the value (bool, int/float lower-cap, list/tuple subset). Other types raise `NotImplementedError`.
- `Annotated[type, NarrowPrefix]` — `list[str]` of paths is narrowing iff every agent entry is descendant-of (or equal to) at least one tool entry. Used by `FilesystemConfig.path_allowlist`.
- `Annotated[type, NarrowSuperset]` — `list[T]` is narrowing iff every tool entry is also in the agent value (agent ⊇ tool — agent adds restrictions). Used by `FilesystemConfig.path_denylist`. Membership uses raw `==`; canonicalisation is consumer-side.
- `Annotated[type, Substitute]` — agent override replaces (no comparison).
- Unmarked field — agent override raises `ValueError("... no Narrow/Substitute marker ...")`.

Session-bound freshness: mid-session operator updates apply at the next `AgentFactory.create()`.

**Cross-Config dispatch**: tools declaring `Requires` receive a per-`get_tools()`-call shared `cross_configs: dict[type[BaseModel], BaseModel]` view. Configs are `frozen=True` so one tool cannot mutate the view to corrupt another's read. Both `BuiltinToolProvider` and tests inject via the same dict (e.g. fake `SearchBackend` for tests).

### Constraint surface

Active constraint types after F5:

| Type | Config field(s) | Marker(s) | Applies to |
|------|-----------------|-----------|------------|
| Path scope | `FilesystemConfig.path_allowlist`, `path_denylist` | `NarrowPrefix` + `NarrowSuperset` | 9 filesystem tools + cwd validation in 6 execution tools (cross-Config) + `download_file` destination |
| Read-size cap | `FilesystemConfig.read_size_cap_bytes`, `allow_binary_files` | `Narrow` × 2 | `read_file`, `grep`, indirect via `edit_file` pre-read |
| Output cap | `ExecutionConfig.output_cap_bytes` | `Narrow` | 6 execution tools (combined stdout+stderr, tail-preserving) |
| Timeout caps | `ExecutionConfig.timeout_seconds_default`, `timeout_seconds_max` | `Narrow` × 2 + `default <= max` model_validator | 6 execution tools |
| Command denylist | `ExecutionConfig.command_denylist` | `NarrowSuperset` | `shell`, `python_exec`, `shell_session_send` (per-call re-check). Substring match with trailing-space convention to avoid the `sudoku` false-positive class. |
| URL/host scope + SSRF | `WebConfig.*` (see below) | mixed | 4 web tools |

**`WebConfig.redirect_cap`** is `Field`-only — NO `Annotated` marker. Tool-level only; agent override raises `ValueError`.

**SSRF "no full-disable" mission invariant**: `WebConfig` has no `disable_ssrf` / `ssrf_disabled` / `disable_ssrf_protection` field. SSRF protection is always-on; operators reaching internal hosts list them in `extra_allowed_hosts` (host-by-host opt-in), not a global kill-switch. The invariant is encoded by the field's ABSENCE — no enforcement code needed. Sweep: `grep -rn 'disable_ssrf\|ssrf_disabled' the_one/` must return zero source hits (only docs allowed).

**Two-layer SSRF enforcement**: (1) `_url_check(url, cfg)` at the tool boundary refuses non-`http(s)` schemes, enforces host allowlist/denylist. (2) `SSRFGuardedTransport` resolves DNS once and pins the connect target to the resolved IP, refusing loopback / link-local / RFC1918 / cloud-metadata / IPv6 ULA + ULL by default. **IP-literal hosts** are also gated by `_is_ssrf_blocked(host)` in the transport's IP-literal short-circuit branch (gated BEFORE `super().handle_async_request`). `extra_allowed_hosts` is the operator override for both paths. DNS-rebind protection: the resolve-then-pin strategy means the second-call rebind to a private IP never reaches the connect layer.

### Subprocess environment invariant

All three execution call sites — `the_one/platform/shell.py`, `the_one/platform/interpreter.py`, `the_one/platform/pty.py::UnixPtySession` — pass an explicit subprocess env built from a hardcoded 8-key allowlist defined as `_ENV_ALLOWLIST` in `the_one/platform/env.py`:

```
PATH, HOME, USER, LOGNAME, LANG, LC_ALL, TERM, TZ
```

**NOT operator-configurable** — part of the F4 trust contract: the agent has no path to read or carry through host secrets via subprocess inheritance. `the_one/platform/pty.py` consumes `_build_subprocess_env` directly to avoid a backwards `platform/ → tools/` dependency.

### Threat model — trip-wire, not fence

The `command_denylist` is a **trip-wire** catching obvious-stupid (agent typos, prompt-injection telegraphs in plaintext, operator-specific dangerous patterns). It is **NOT a fence** against adversarial agents — `bash -c "$(echo c3VkbyB3aG9hbWk= | base64 -d)"` is not in the denylist. The trip-wire produces a clean small-model-readable error rather than a destructive side-effect; bypasses are accepted because the operator-trust threat model assumes the agent is not actively adversarial. Operators wanting fence-grade isolation run the agent in a sandbox (container, VM, namespace).

False-positive surface is also accepted: `echo "do not run sudo"` is refused; workaround documented in `shell_session_send`'s tool description.

### PTY session lifecycle

- **Addressing** (Decision 4): per-explicit-handle. `shell_session_start` returns a `pty-{12hex}` token; the agent passes it back into `_send`/`_close`. Four discrete tools (`_start`, `_send`, `_close`, `_list`), not an action-enum.
- **Per-agent isolation**: registry keyed on `(agent_name, session_id)`. Cross-agent `_send`/`_close` returns the SAME error shape as a non-existent session ("not owned by this agent or does not exist") — agents cannot probe for other agents' session ids.
- **Idle reap**: single lazy asyncio reaper; wakes every 30s; closes sessions where `monotonic() - last_activity > pty_session_idle_ttl_seconds` (default 5min, `Narrow`). Registered with FastAPI lifespan for clean drain on shutdown.
- **Max concurrent**: `count_for_agent < max_concurrent_sessions` (default 5, `Narrow`). The L6 spec accepts a documented race on concurrent `_start` calls; the registry's internal lock has so far serialised correctly under single-process asyncio.
- **Idle-mark prompt detection**: `_read_until_idle` blocks until the master_fd has been silent for 100ms (2s hard cap). Robust against inconsistent shell prompts (zsh themes, sudo prompts).
- **Per-call denylist re-check** (Decision 11): every `_send` runs `_command_check(input, exec_cfg)` BEFORE forwarding. Agents cannot pre-stage a denylisted command behind an open session.

Windows: `UnixPtySession` raises `NotImplementedError("Windows ConPTY support deferred")` on import under `os.name == "nt"`.

### Origin allowlist

`OriginAllowlistMiddleware` gates state-mutating HTTP (POST/PUT/PATCH/DELETE) and WS upgrades by `Origin`/`Referer` against `THE_ONE_ORIGIN_ALLOWLIST`. Default: `http://127.0.0.1:*` and `http://localhost:*` — port-wildcard with strict-digits enforcement to reject `http://127.0.0.1.evil.com`-class confusion attacks. Missing-Origin requests pass through (server-to-server clients are NOT browser-originating). WS upgrades close at the ASGI layer (`{"type": "websocket.close", "code": 1008}`) BEFORE the route handler can `accept()` — `Depends()` runs post-`accept()` and cannot do this. Policy: `SECURITY-MODEL.md`.

### Continue Signal

A virtual tool (`CONTINUE_SCHEMA`, defined inline in `core.py`) that the LLM calls to indicate it needs another iteration. Not a real tool — the agent loop intercepts it and loops.

**Capability gate**: `Agent.step()` consults `LLMProvider.supports_tools()` once per turn. When tools are unsupported (e.g. Ollama Gemma — `/api/show` capabilities lack `"tools"`), the agent drops EVERYTHING from the wire payload — both real tool schemas AND `CONTINUE_SCHEMA` — and runs a single LLM iteration as plain chat. Silent fallback is deliberate; Studio's red `no tools` chip on the model selector is the only operator-facing signal.

### Model capability surface

`LLMProvider.supports_tools()` is async, default `True` for cloud providers (OpenAI, Anthropic, mock). `OllamaProvider` overrides via `ollama_api.get_model_capabilities(base_url, model)`:

- Fetches `/api/show`, reads the `capabilities` array.
- Caches per `(base_url, model)` with 5-minute TTL.
- Returns `frozenset[str] | None`. `None` means "couldn't determine" — the agent treats that as `True` (trust the provider; surface errors via the 400-body diagnostic).

`GET /api/providers/{id}/models` async-gathers per-model capabilities for Ollama providers. Failures are non-fatal: a single capability fetch failing degrades to `null`, the rest of the list still renders.

The Pull Model dropdown is **deliberately NOT enriched** — `/api/tags` doesn't carry capabilities, so per-option chips would mean N×`/api/show` round-trips per dropdown open.

### Dev iteration

The dev container at `localhost:8484` runs `uvicorn ... --reload --reload-dir /app/the_one`. Host edits under `./the_one/` trigger a graceful uvicorn restart within ~1s. `./tests/` is bind-mounted but **not** watched (test edits don't bounce the server). Run tests with `docker exec the-one pytest ...` — fresh interpreters always see latest test code.

---

## Provider type extension checklist

Six layers must coordinate. Missing any one causes either silent rejection (validation) or runtime errors.

### Provider URL validation

`_is_safe_provider_url` (`interfaces/web/api.py`) enforces `https://` for non-localhost hosts on LLM provider `base_url`. Called at endpoint time from `create_provider`, `update_provider`, and `test_provider` — NOT a Pydantic validator (must run on the resolved `base_url` post-`model_copy`, after `__MASKED__` substitution). Two skip layers: (a) `_URL_VALIDATION_SKIPPED_TYPES = frozenset({"mock", "ollama"})` bypass entirely; (b) for the rest, `http://` is allowed only when host is `localhost`, `127.0.0.1`, `::1`, or `*.localdomain`. RFC1918 / link-local / `0.0.0.0` require `https://`.

### Checklist

1. **Pydantic `Literal`** — `db/models.py` `LLMProviderConfig.type`. Add the new value to the `Literal[...]` tuple, or `model_validate` rejects.
2. **`_PROVIDER_TYPE_MAP`** — `agent/factory.py`. Add `"<type>": "<registry-name>"`, or `AgentFactory.create()` raises `ValueError`.
3. **Registry `loaders`** — `llm/registry.py:_try_load_builtin`. Add the lazy-loader lambda, or `get_provider("<type>")` raises a misleading `ImportError("requires extra dependencies")`.
4. **SQLite `CHECK` constraint** — `db/schema.py` (table definition AND migration). The `llm_providers.CHECK (type IN (...))` clause hard-codes allowed values. Adding a new type requires a schema migration (see v6 for the pattern: `PRAGMA foreign_keys=OFF` + table rebuild). Without this, `INSERT` fails with `IntegrityError`.
5. **API gating / branches** — `interfaces/web/api.py`: type-specific gating in `create_provider`/`update_provider` (e.g. dev-mode gate for `mock`); branch in `test_provider`; branch in `list_provider_models`; inclusion/exclusion in `GET /api/providers/types`.
6. **Frontend** — `interfaces/web/static/js/areas/admin.js`: add `TYPE_DEFAULTS["<type>"]` (unconditional — needed for editing existing providers even if hidden from creation); add `<type>` to `KNOWN_BADGE_TYPES`; add `--badge-<type>` token in `tokens.css` + matching `.admin-provider-badge--<type>` rule in `admin.css`.
7. **`_init_provider_state(self, kwargs)`** (optional hook on `LLMProvider`) — when the new provider needs to capture configuration outside the base field set (e.g. OpenRouter's `app_url`/`app_name` analytics headers; Ollama's lazy `max_context_tokens` state).

---

## Connector type extension checklist

Parallel to the provider-type extension checklist above. When a future flight adds a new connector type (Flight 8 — `'discord'`; Flight 9 — the second connector), the same kind of cross-layer coordination is required. Flight 1 of Mission 10 ships the contract scaffolding (the `connectors/` package, persistence, lifecycle pool, registry, encryption-rotation integration); the layers below name which flight owns each subsequent coordination point.

### Checklist

1. **Pydantic `Literal`** — `db/models.py` `ConnectorAccount.type`. F8 L2 narrowed to `Literal["discord", "stub"]` (`'stub'` included per the M07 `'mock'`-in-`PROVIDER_TYPES` precedent — see `_connector_types.py` docstring) and landed the `assert set(get_args(...)) == set(CONNECTOR_TYPES)` invariant alongside `LLMProviderConfig`'s assert. Future connector types add their value to the `Literal[...]` arg-set in the same leg they're added to `CONNECTOR_TYPES`.
2. **`CONNECTOR_TYPES` tuple** — `db/_connector_types.py`. F8 L2 populated to `("discord", "stub")`. Canonical single-source-of-truth pinned to layers 1, 3, and 4 by `tests/test_connector_types_consistency.py`.
3. **Registry registration** — `connectors/registry.py:register_builtin_connectors`. F8 L2 registers `register("discord", DiscordPlugin)` via a function-local import per the `function-local-import-to-break-load-cycle` convention. Layers 2 (`CONNECTOR_TYPES`) and 3 must agree — a type in `CONNECTOR_TYPES` without a registration produces a `ConnectorRegistrationError` at first dispatch (the `'stub'` carve-out is documented in the consistency test).
4. **SQLite `CHECK` constraint** — `db/schema.py`. v13/v14 deliberately shipped without a CHECK on `connector_accounts.type` (`CONNECTOR_TYPES` was empty at v13 landing; the v3/v6 precedent of CHECK-in-CREATE-TABLE didn't apply because there was nothing to constrain initially). v14 is claimed by leg 02's `name` column on `connector_accounts` (F1 L2); v15 by leg 02 of Flight 2 — `idle_timeout_seconds`; v16 by leg 01 of Flight 3 — chat_sessions external-key columns + `session_continuation_seconds` on `connector_accounts`; v17 by leg 05 of Flight 4 — `agents.connector_account_ids` persistence (closes the F4 L1/L4 leg-4 monkeypatch workaround); v18 by leg 1c of Flight 6 — `agents.connector_acls` persistence (closes the F6 per-agent ACL substrate atomically per F4 debrief rec #1). **v19 (F8 L2)** added `CHECK (type IN ('discord', 'stub'))` via the table-rename ceremony established by v6/v12 (CHECK literal list sourced from `_CONNECTOR_TYPES_SQL` mirroring `_PROVIDER_TYPES_SQL`).
5. **API gating / branches** — `interfaces/web/api.py`: `/api/connector-accounts/*` create/update/delete/test branches. Flight 2 lands the admin REST surface; Flight 8 lands any Discord-specific gating on top.
6. **Frontend** — `interfaces/web/static/js/areas/studio/connector-accounts-grid.js` + `studio/connector-account-editor.js` + integration in `static/js/areas/studio.js`. Badge styles land in `tokens.css` + the corresponding studio CSS rule. Flight 2 landed the Studio connector pages + Studio attach surface; **F8 L2 shipped the `--badge-discord` token (`tokens.css:158`) + `.admin-connector-badge--discord` rule (`studio.css` Connector Type Badges section).** (Admin only if a future surface needs it.)
7. **`_init_*` state hook** *(optional)* — if a future plugin needs to capture configuration outside the base `ConnectorAccount` fields (analog to `_init_provider_state` on `LLMProvider`), expose a hook on the plugin class. Not needed for Flight 1's stub or any Flight-8/9 design currently on the table; revisit per real plugin.
8. **Tool-target validation** — `the_one/tools/connector_send.py:SendToPlatformChannelTool.execute`. F4 ships account-scope validation: `target.account_id ∈ agent.connector_account_ids` (rejects with the standard `[error] [constraint]` envelope on mismatch). The next layer of ACL — channel-level, thread-level, peer-level — is F6 territory; the tool's execute body carries a `# F6: optional resolver hook consultation lands here` marker for F6's diff to replace. New connectors do NOT modify the tool; they participate by being registered (layer 3) and being attached to an agent (`AgentConfig.connector_account_ids`).

---

## Connector subsystem

Decisions, invariants, and known issues encoded by Mission 10 Flight 1. The code in `the_one/connectors/` implements them; this section is the human-readable index for maintainers. For a package-layout / entry-point reference, see `the_one/connectors/README.md`.

### Typed-exception hierarchy

`connectors/errors.py` defines 6 producer-side types: `ConnectorClientError` (base) → `ConnectorConfigError`, `ConnectorConnectionError`, `ConnectorAuthRequired`, `ConnectorRegistrationError`, `ConnectorRateLimitError`.

Mirrors the MCP precedent in shape (`mcp/errors.py` has 10 producer-side types accreted across 11 M07 flights; the consumer-side match list in this file's MCP section collapses them into 4 categories — the "four-typed-exceptions" wording refers to that consumer surface, not the producer hierarchy). The connector hierarchy starts smaller; the **grow deliberately** stance applies — new types land only when a real platform reveals a distinct error mode that doesn't fit any existing type. `ConnectorRateLimitError` is shipped from Flight 1 specifically because Flight 10 owns rate-limit handling for both Discord and Slack outbound, and retrofitting the translation path in Flight 8/9 is structurally worse than carrying the type now.

### Worker-task-per-entry pattern

`connectors/_pool.py:_entry_worker` holds the platform connection on a single asyncio task. **Connect AND disconnect run on the same task**, satisfying anyio's cross-task `CancelScope.__aexit__` guard. The eviction path signals via `entry.evict_event` rather than cancelling the worker — the worker's `finally:` clause runs `plugin.disconnect(client)` on the same task that ran `plugin.connect(...)`. Mirrors `mcp/_pool.py:_entry_worker`; see the "AsyncExitStack pattern + worker-task pattern" discussion in `the_one/mcp/README.md` §3 for the canonical cross-task-safety rationale.

Concurrent-acquire-same-key races to a shared worker: the lock-held branch in `connectors/_pool.py:acquire` checks `entry is None` (NOT `entry.client is None`); subsequent callers fall through to `entry.client_ready.wait()` outside the lock. The worker is the sole writer of `entry.client` and `entry.failure`; both are written BEFORE `entry.client_ready.set()`. Mirrors MCP's cycle-2 race-fix invariant.

### Parallel-pool-not-shared decision

`connectors/_pool.py` is a fresh implementation, not a refactor of `mcp/_pool.py` into a shared primitive. ~300 LoC of structural duplication accepted because the alternative (extracting a generic `AsyncConnectionPool[T, K]` and retrofitting the production-load-bearing MCP pool to use it) is a cross-cutting refactor that doesn't belong in a foundation flight. M07's debrief framed the same test-isolation debt as "cross-cutting refactor, deferred to follow-up architectural flight"; that framing still holds. The connector pool ships with M07's test-isolation lesson applied from day one (`_clear_for_test` resets `_shutting_down = False` along with clearing the registry — see `connectors/_pool.py:_clear_for_test`); MCP's `_shutting_down` test-isolation debt remains in `mcp/_pool.py`.

**Extraction trigger**: a **third network-keyed pool**. The existing PTY session registry at `the_one/tools/_session_registry.py` is NOT counted toward this trigger — it is *process-lifecycle-keyed* (a pty either has a child process or doesn't) with no warm-connection keep-alive, no heartbeat, and no reconnect lifecycle. PTY, MCP, and Connector pools share the per-entry-worker-task hygiene pattern superficially but diverge structurally on what an "entry" represents and what eviction means; that divergence is what makes a generic extraction speculative until two true network-keyed peers exist. When a third subsystem holds warm protocol connections keyed by `(agent, source)` (e.g. a hypothetical "external workers" subsystem), extraction becomes mandatory rather than optional.

### Per-Protocol structural-satisfaction discipline

`connectors/base.py` declares **Protocols, plural**. Flight 1 ships `ConnectorPlugin` (4 methods: `connect`, `disconnect`, `doctor`, `normalize_session_key`) and `ConnectorClient` (1 method: `is_alive`). Flights 6 and 7 will land **additional Protocols in the same file**:

- Optional `resolve` hook (Flight 6) — per-(peer, channel) ACL resolution via `getattr` consult site (NOT a Protocol — see `optional-plugin-hook-via-getattr-sentinel`)
- `CommandHandler` (F7 L1) — optional platform-side command-handler Protocol; structural satisfaction in addition to `ConnectorPlugin`; v1 vocabulary (`/agents`, `/talk-to`, `/whoami`, `/new`, `/reset`, `/help`) is handled by the dispatcher's built-in text-prefix parser, with plugins free to register platform-native equivalents that supersede the built-in handler.

A connector that supports per-(peer, channel) gating implements the optional `resolve` hook (see §4 in `connectors/README.md`); the `ConnectorPlugin` Protocol stays at its 4-method shape. Per the `structural-Protocol-satisfaction` convention, implementations do NOT inherit from the Protocols — they just expose the right methods. **Structural satisfaction is per-Protocol, not subsystem-wide**: a connector that claims to satisfy `ConnectorPlugin` + `CommandHandler` MUST be asserted via `isinstance(conn, ProtocolType)` for each Protocol it claims, separately. The per-platform integration tests (Flight 8 Discord, Flight 9 second connector) carry those assertions. "Single contract file" is the mission criterion; multiple Protocols in one file satisfy it.

### Encryption-rotation invariant (three corpora)

`POST /api/encryption/rotate` (`interfaces/web/api.py:rotate_encryption_key`) re-encrypts every credential ciphertext in **one atomic transaction**. As of Mission 10 Flight 1 the rotation covers three corpora:

1. `llm_providers.api_key` (Mission 03)
2. `mcp_sources.secrets` (Mission 07)
3. `connector_accounts.secrets` (Mission 10 Flight 1)

A failure in any of the three UPDATE loops calls `conn.rollback()` and re-raises, so a partial rotation that handled only a subset is impossible. The single `await conn.commit()` is the authoritative commit point; the on-disk key file is replaced atomically via `os.replace` only AFTER the DB commit succeeds. Migration-residue rows (plaintext `'{}'` carried over from the column default) are tolerated via `InvalidToken`-swallowing decrypt and normalized to proper ciphertext for `{}` as a side-effect — same shape across all three corpora.

### Outbound contract

**The platform-send tool is the only agent→platform path.** `the_one/tools/connector_send.py:SendToPlatformChannelTool.execute()` is the sole production caller of `ConnectorClient.send(target, content) → SendResult` (`connectors/base.py:ConnectorClient.send`). No other code path in the codebase reaches `send`. The mission's enforcement-by-construction stance — peer messages can be received and persisted regardless, but outbound delivery is gated solely through this one tool — is realized structurally, not by trust.

**F10 baseline carve-out.** `send_to_platform_channel` is pre-loaded into `_compute_visible_schemas`'s baseline-visible set at `the_one/agent/factory.py:AgentFactory.create()` time when (`bool(config.connector_account_ids) AND tool_enabled`). The two-layer enable check composes the operator gate (`ToolConfigRepository.enabled`) with the per-agent gate (`AgentConfig.is_tool_enabled`). The F10 strict-baseline comment at `the_one/agent/core.py:30-34` documents this as the second exception to the search_tools-only baseline.

**Visibility-tagging contract** (`the_one/connectors/_inbound.py:dispatch_inbound` post-step pass): for every connector-attached session, the dispatcher walks new messages produced by `agent.step()` and tags `Message.visibility`. `Role.USER` messages (the peer inbound) keep their default `visibility=None` (peer-visible). Tool-result messages whose parent tool_call had `name == "send_to_platform_channel"` AND whose content starts with `PLATFORM_SEND_OK_PREFIX` get `visibility=None` (peers saw this content go out via the platform-send tool). Every other new message (assistant text, intermediate tool calls / results, the `continue` virtual tool_result) gets `visibility="operator"`. F5 Chat-UI rendering uses the `visibility` tag to drive the two-layer display.

**System-prompt directives** (`the_one/agent/config.py:compose_system_prompt`): connector-attached agents receive an explicit directive about how their outbound flows. When the tool is operator-enabled: "to reply to peers on the platform, call the `send_to_platform_channel` tool." When operator-disabled: "the platform-send capability is currently DISABLED by the operator; your replies in this session reach the operator only — they do not reach the external platform. Do not claim to have sent anything to the platform." The pair makes the two states (enabled / disabled) deliberate operational modes, not implicit ones.

**Account-scope target validation**: `SendToPlatformChannelTool.execute` rejects `target.account_id ∉ agent.connector_account_ids` with `[error] [constraint] account_id '<id>' is not attached to this agent`. F6's optional `resolve` hook layers channel/thread/peer ACLs on top via the documented hook point in the tool's execute body (search the tool source for the `# F6:` marker — leg 3 of F6 updates the marker text alongside wiring the consult site).

**Cross-reference**: `the_one/connectors/README.md` §11 (Outbound flow trace) has the file:line walk through the full path.

**Routing convention** (M10 F7 L5): the inbound dispatcher composes two pure functions to pick which attached agent handles an inbound. The routing engine at `the_one/connectors/_routing.py:resolve_routing(account, envelope, eligible_attached_agents, session_metadata) -> RoutingDecision` is pure (no I/O); it walks the 5-step algorithm (override → rule-walk → default → first-eligible-alphabetical → no-eligible). The ACL gate at `the_one/connectors/_acl.py:admits_inbound` (symmetric to `admits_outbound`) is also pure; the routing engine calls it for every candidate it considers, so the dispatcher does NOT re-check ACL on the engine's output. The L5 dispatcher composes them in canonical step 7 (routing engine consult) of its 12-step body — pure pieces, integration at the call site. Routing decisions are audit-logged under `session_metadata["routing"]` via the F6 list-append primitive (`ChatSessionRepository.append_to_session_metadata`); each entry carries `{ts, agent, rule_index, scope, match, reason, disposition}` where `disposition ∈ {"stepped", "command-intercepted", "no-eligible"}` discriminates routed-and-stepped from command-intercepted from no-eligible-error-emitted (pool-failure-overload collapses onto `"no-eligible"`). The audit-entry shape mirrors F6's `session_metadata["audit"]` entry shape — `ts` and `reason` keys reuse F6's naming so a single Studio renderer walks both logs uniformly. The F7 L6 `/talk-to` handler writes `session_metadata["routing_override"] = "<slug>"` via the sibling primitive `ChatSessionRepository.set_session_metadata_key` (last-writer-wins concurrency posture); the engine reads that override in step 1 of its 5-step algorithm. `the_one/connectors/README.md` §12 (Inbound flow trace) carries the file:line walk through the full 12-step dispatcher body.

**Audit-log single-winner semantic** (M10 F8 L1 clarification): a single `RoutingDecision` is emitted per `dispatch_inbound` invocation; only the eventual winner's path lands in `session_metadata["routing"]`. Candidates the engine considered and skipped (ACL-denied, missing-attachment, unknown-slug) are NOT enumerated in the audit entry; see `the_one/connectors/_routing.py` module docstring for the canonical contract and the F10 deferral for richer chain-audit.

**v1 command surface** (M10 F7 L6): the dispatcher's command-intercept path (step 11 of the 12-step body) consults `the_one/connectors/_commands.py:_dispatch_builtin_command`. The L1 parser `_parse_command(text)` extracts `(command_name, args)` from any envelope whose `text` starts with a single forward slash followed by a lowercase-letter-led `[a-z0-9-]` word. Six v1 commands intercept and emit via the system-outbound path (NOT through the platform-send tool): `/agents`, `/talk-to <slug>`, `/whoami`, `/new`, `/reset` (alias for `/new`), `/help`. Two `session_metadata` keys carry the command-side state: `"routing_override"` (written by `/talk-to`, consumed by the L4 engine on the NEXT inbound — current inbound was already routed) and `"ended_at"` (written by `/new` / `/reset`, consumed by `_session.resolve_session`'s reuse path to skip an existing row and create a fresh one on the next inbound). Both keys are written via `ChatSessionRepository.set_session_metadata_key` (last-writer-wins overwrite). Unknown command names (e.g. `/foo`) fall through to `agent.step` as regular user messages — the v1 vocabulary's six names are the only short-circuits. `/agents` and `/help` are permission-filtered: `_permitted_agents(context)` applies the per-agent `admits_inbound` ACL on top of the dispatcher's `eligible_attached_agents` list; `/agents` returns the byte-identical no-eligible string when the filter is empty, and `/help` lists `/agents` + `/talk-to` only when the filter is non-empty (the four agent-independent commands are always listed). Cross-reference: `the_one/connectors/README.md` §13 (v1 command vocabulary).

### 4-axis allowlist + outbound fallback (M10 F8 L8)

The account-scope `config["allowlist"]` and per-agent `AgentConfig.connector_acls[account_id]` admission surfaces both carry four parallel axes: `peers`, `channels` (cross-platform, F6 baseline), plus `guilds` and `roles` (Discord-flavored, F8 L8). Each axis is independently tri-state per the `per-axis-tri-state-override` convention — composition is per-axis AND, never single-list AND. `peers` and `channels` remain REQUIRED on the inner-dict shape (back-compat with all pre-L8 rows); `guilds` and `roles` are OPTIONAL — absent axis = unrestricted on that axis. The L4 Discord plugin populates `envelope.raw["guild_id"]` (str or None for DMs) and `envelope.raw["member_roles"]` (list of str role IDs, empty for DMs); `_routing._agent_admits` threads both into `_acl.admits_inbound`, which evaluates the guilds axis as set-membership and the roles axis as any-of overlap against `member_roles`. **DM-with-guild-restriction posture**: when `allowlist["guilds"]` is non-empty AND the envelope is a DM (`guild_id=None`), the guild check denies — the operator narrowed to specific guilds, DMs are out-of-scope. Operators wanting DMs admitted under a guild-restricted account leave the axis absent or empty. **Outbound fallback**: `_acl.admits_outbound` accepts the new kwargs for signature uniformity but does NOT consult them — the F4 platform-send tool has no envelope context (just `account, channel_id, thread_id`), so there is no `guild_id` / `member_roles` to evaluate at outbound time. The kwargs are silently ignored; this is consistent with the F6 channel-axis fallback rationale. F10 hardening can revisit if HAT surfaces concrete outbound needs (e.g. plugin-resolved `send_target_guild_id`).

### Slash commands via `CommandHandler` (M10 F8 L9)

Platform-native command surfaces (Discord application commands; Slack slash commands in F9; …) plug into the F7 v1 command vocabulary via the `CommandHandler` Protocol consult site at `_inbound.py:494` — a plugin that opts in implements `async def handle_command(envelope, command_name, args) -> CommandResponse | None`, returning `None` to fall through to the F7 built-in handlers and a `CommandResponse` to short-circuit with a platform-customized reply. DiscordPlugin structurally satisfies the Protocol (in addition to `ConnectorPlugin`); `isinstance(DiscordPlugin(), CommandHandler)` is True after L9. **L9 fall-through default**: `DiscordPlugin.handle_command` returns `None` for every command (the six v1 names AND unknown commands), so slash invocations inherit the F7 v1 vocabulary byte-for-byte; Discord-native ephemeral-response customization (e.g. `/help` visible only to the invoking peer) is deferred to F10 hardening — the simpler uniform fall-through keeps L9 scope tight and avoids the "two response paths" branching the dispatcher's outbound shape would force. **Registration shape**: a `discord.app_commands.CommandTree` is built inside `DiscordPlugin.connect` post-client-construction and decorated with the six commands (`agents`, `talk_to`, `whoami`, `new`, `reset`, `help` — note: `talk_to`, NOT `talk-to`, because Discord's application-command name regex rejects ASCII hyphens; the F7 `_parse_command` whitespace-splits, so the synthesized envelope text `/talk_to my-agent` reaches the dispatcher unchanged). **Per-guild PUT-style sync**: post-READY, the connect path calls `await tree.sync(guild=discord.Object(id=int(g)))` for each `g in account.config.get("guilds", [])`. Sync is a PUT — it replaces the guild's command list with the current `tree` contents, never appends; idempotent on every reconnect. Empty / absent guild list → skip with an INFO log (slash commands won't appear in any guild). Per-guild sync failures (`discord.errors.Forbidden` when the bot lacks the `applications.commands` scope; network blip; guild not found) log at WARNING and continue — the gateway connection still goes live, and subsequent guilds are still attempted. **Global registration deferred to F10** (per-guild registers in ≤5 minutes vs ≤1 hour for global; F8 HAT iteration is faster on per-guild). **Slash-command body**: each registered callback acks via `interaction.response.defer(ephemeral=True)` to satisfy Discord's 3-second interaction timeout, then translates the `Interaction` into an `InboundEnvelope` (text synthesizes the F7 form `/<name> <args>`; `peer_id` / `peer_name` from `interaction.user`; `channel_id` / `thread_id` follow L4's thread/channel convention; `raw` carries `is_dm` for the L6 consult site, `guild_id` and `member_roles` for the L8 4-axis allowlist) and calls `dispatch_inbound(account.id, envelope, factory=get_factory())` — the same path the `on_message` handler uses. The visible reply is posted by the dispatcher's outbound `client.send` path in the same channel; the ephemeral defer is just the Discord-required handshake.

### Gateway-listener factory access (M10 F8 L4)

Gateway listeners spawned inside `plugin.connect` (Discord's `on_message` in F8 L4, Slack's event handler in F9, …) cannot receive an `AgentFactory` reference through the `plugin.connect(account, encryptor)` signature — they fire from inside the pool's per-(agent, account) worker task, BEFORE any caller has a handle to set attributes on the returned client. Adding the factory to `connect`'s signature would also break the stateless-plugin contract.

The codified convention: `the_one.agent.factory` exports a module-level accessor pair — `set_factory(factory: AgentFactory | None) -> None` and `get_factory() -> AgentFactory | None`. FastAPI's lifespan startup calls `set_factory(...)` once after constructing the application factory; the lifespan teardown calls `set_factory(None)` to release the reference. Gateway listeners call `get_factory()` at dispatch time; `None` (pre-startup race / post-shutdown / test fixtures that never set it) means log at WARNING and return — the platform message is effectively dropped for the brief race window. The pattern mirrors the existing precedent at `interfaces/web/app.py:_get_factory` (which reads from a private dict for the web routes); the module-level accessor is the canonical subsystem-facing surface for gateway listeners and applies uniformly to Discord (F8), Slack (F9), and any future platform whose SDK delivers inbounds via event-handler registration.

### Known Issues

Carry-forward items future flights must respect or close:

- **Deferred shared-pool extraction**. `connectors/_pool.py` duplicates ~300 LoC of structural lifecycle machinery from `mcp/_pool.py`. M07's `_shutting_down` test-isolation debt remains in MCP; the connector pool ships with the fix from day one. Extraction trigger: a third **network-keyed** pool (see "Parallel-pool-not-shared decision" above for the PTY-exclusion rationale — process-lifecycle-keyed pools do not count). When a third network-keyed peer emerges, extracting `AsyncConnectionPool[T, K]` and retrofitting both pools becomes mandatory rather than optional.

- **Flight 3 ratified `last_activity` tracking via acquire-per-inbound** (M10 F03 L04). `connectors/_pool.py:_RegistryEntry.last_activity` is updated by `acquire()` on every call (warm and cold paths converge — see `_pool.py:479`). The reaper consumes this value to decide eviction. The dispatcher at `connectors/_inbound.py:dispatch_inbound` calls `acquire(agent_name, account_id)` per inbound envelope — `last_activity` is touched per inbound, NOT per session-key resolution or per agent.step iteration. This is the contract: any future code path that bypasses the pool (e.g. caches a `ConnectorClient` reference outside the pool) is responsible for re-touching `last_activity` itself OR for accepting that the reaper may evict actively-used gateway connections.

---

## Streaming protocol

Provider-agnostic at the agent layer; per-provider native streaming sits behind `LLMProvider.stream(...)`. The base class supplies a default implementation that calls `complete()` and yields exactly one `StreamChunk(is_final=True, ...)`. Subclasses MAY override.

### `StreamChunk` contract

```python
@dataclass
class StreamChunk:
    content: str = ""               # NEW tokens since last chunk; delta semantics
    is_final: bool = False
    tool_calls: list[ToolCall] = []  # populated on final chunk
    usage: TokenUsage | None = None  # populated on final chunk where exposed
    message: Message | None = None   # synthesised assistant Message; final chunk
```

**Delta semantics**: `content` is NEW tokens, NOT cumulative. The agent accumulates by string concatenation. The final chunk MAY carry a delta (some providers emit stop-event trailing text); the accumulator checks `chunk.content` regardless of `is_final`.

**Final-chunk contract**: providers populate `message` so `Agent.step` can prefer it. When `message` is None, the agent rebuilds from accumulated `content` + `tool_calls` + `usage`.

### Per-provider notes

- **Anthropic**: native via `client.messages.stream(...)`. Catches `BadRequestError` mentioning "temperature", strips the kwarg, retries once. Gated by `yielded_any` so the retry is only safe BEFORE any chunk has emitted (Anthropic raises pre-stream in practice).
- **OpenAI**: native via `chat.completions.create(stream=True, stream_options={"include_usage": True}, ...)`. The `include_usage` flag is **required** — without it the trailing metadata chunk has no `usage` and end-of-stream telemetry breaks. Tool-call deltas accumulate by `index`.
- **Ollama**: native via `ollama_api.chat_stream`. True SSE (`data: {...}` + `data: [DONE]` terminator), distinct from `pull_model`'s JSONL. Reuses the OpenAI-shape tool-call accumulation.
- **Mock**: honours `config["stream_chunks"]: list[str]`. When unset, falls back to default-impl **inline** (NOT `super().stream(...)` delegation) for clarity.

### WS event vocabulary

| Event | When | Notes |
|------|-----|-------|
| `assistant_chunk` | Per-content-delta during streaming | |
| `assistant` | Direct-action shortcut path only | Suppressed when chunks fire |
| `tool_call` | Tool-call emitted by the model | Carries `parent_message_id` + `tool_call_id` |
| `tool_result` | Tool execution result | Carries the same pair |
| `usage` | Per-iteration final-chunk usage | |
| `done` | End of agent step | |

The streaming WS contract is **chunks-only-no-final-assistant**: when the chunk path fires, the legacy `assistant` event is suppressed server-side. The client has the accumulated text via chunks. The legacy event survives for the direct-action shortcut path (early-return in `Agent.step` before any LLM call).

**`parent_message_id` namespace convention**: live sessions use `{session.id}-msg-N`; replayed sessions use `replay-msg-N`. The frontend treats these as opaque grouping keys — different namespace prefixes between live and replay are not collisions.

### `chunks_seen` invariant

The server distinguishes streaming from direct-action via a per-iteration `chunks_seen` flag captured in the agent-step closure. The flag is set inside `_broadcast_chunk` and reset **unconditionally at the end of each Role.ASSISTANT block** in the `async for msg in agent.step(...)` loop. Unconditional matters for multi-iteration loops: a tool-call-only iteration (empty content, non-empty `tool_calls`) must still reset the flag for iteration N+1.

### Persistence contract

The synthesised final assistant `Message` is **NOT broadcast** as `{"type": "assistant"}` over the WS during streaming (the client already has the text). It IS:

- Appended to `session.history` via `session.add_event` so rejoin/refresh re-renders from server-side history.
- Appended to `result_messages` so the HTTP API caller receives the full message list.

This split — stream-deltas-over-WS, persist-full-message-server-side — is the F4 leg-04 contract. Enforced end-to-end by `test_streaming_message_persists_to_history`.

---

## Markdown rendering

Hand-rolled CommonMark-subset library at `static/js/markdown.js`. Public API: `App.markdown.parse(text) → AST`, `App.markdown.render(text) → DocumentFragment`, `App.markdown.NodeType`.

### Supported subset (v1) — contract for callers

paragraphs, ATX headers (`#`..`######`), fenced code blocks with language tag, blockquotes (single level), unordered + ordered lists (one nesting level), horizontal rules (`---`/`***`), emphasis (`*` or `_`), strong (`**` or `__`), inline code, links (including balanced-paren URLs), soft breaks (single `\n`), hard breaks (trailing TWO spaces + `\n`).

**Out of subset (v1 non-goals)**: tables, footnotes, definition lists, autolinks, reference-style links, HTML passthrough, recursive nested emphasis. The test corpus locks v1 in; expanding requires a new flight with test-case expansion.

### Nested-emphasis v1 contract

`***word***` renders as `<em><strong>word</strong></em>` (outer-em-first). Recursive nested emphasis is v2 scope. `**bold *with em***` renders as `<strong>bold *with em*</strong>` — the inner `*with em*` is literal. Mechanism: `inEmphasisRun` suppression flag once an emphasis run opens.

### XSS guarantee

Renderer constructs DOM via `document.createElement` + `textContent` exclusively. The library NEVER uses `innerHTML` — `grep -n innerHTML markdown.js` returns zero hits (including comments). SVG icon injection on the copy button uses `DOMParser().parseFromString(svg, 'image/svg+xml').documentElement` to keep the invariant. Link `href` values pass through a scheme allow-list (`http`, `https`, `mailto`, `tel`, `/`, `#`); other schemes (`javascript:`, `data:`, `vbscript:`, `file:`) are stripped to `#`. "No innerHTML anywhere in the markdown pipeline" is a structural property — future contributors cannot accidentally introduce XSS via crafted markdown.

### Robustness for streaming

`parse(null)`, `parse(undefined)`, `parse('')` all return `{type: 'document', children: []}` — no exception. Streaming callers can pass partial buffers without try/catch ceremony.

### Mid-stream rendering NOT supported

Partial markdown syntax has no canonical semantics (`**bold` mid-token has no end). The streaming path uses `textContent` accumulation followed by a single swap on `done`. Chat integration: `App.chat.renderMessage(cls, text)` markdown-renders assistant messages by default; user/tool/system stay `textContent`. Detection uses a first-token whitespace split (`cls.split(' ')[0] === 'assistant'`) so `'assistant-error'` would NOT trigger markdown.

### Extension contract

Adding a new construct: (1) `NodeType` constant, (2) tokeniser/parser case, (3) renderer branch, (4) ≥3 parametrised test cases. All four in the same leg. PRs missing test cases fail review.

---

## Design system

### Color contrast (WCAG AA regression contract)

Token contrast pairs are audited by `tests/test_design_tokens_a11y.py` against:
- **4.5:1** for body text (WCAG 1.4.3)
- **3.0:1** for large text, UI components, non-text contrast (WCAG 1.4.11)

The test file hardcodes token values to mirror `tokens.css`; canonical mirror lives in `tests/browser/design_tokens.py` (`DARK` / `LIGHT` dicts). **Before changing a color token, re-run `pytest tests/test_design_tokens_a11y.py`.** If CSS values change, update `design_tokens.py` in lockstep — the brittleness is intentional (lightweight; no CSS-parser dependency).

`tests/test_token_definitions.py` parses every `var(--x)` reference across `static/css/*.css` and asserts each token has a definition. Catches typos like `var(--accnet)` that CSS silently treats as `unset`.

### Deliberate AA exceptions

`--fg-faint` (dark `#444` on `#0a0a0a` ≈ 2.03:1; light `#94a3b8` on `#fafbfc` ≈ 2.47:1) is intentionally below body AA. Used for de-emphasized annotation labels (telemetry "in:"/"out:"/"ctx:", env-var hints), disabled placeholders, decorative recessive marks. NEVER body prose, NEVER an interactive UI affordance. Each carries a `# DELIBERATE EXCEPTION` comment in the test file; the assertion bands trip if a future retune drifts the value out of "faint" territory.

### Focus visibility convention

All `:focus-visible` rules use the same pattern: `outline: 1px/2px solid var(--accent); box-shadow: 0 0 0 3px var(--accent-glow);`. Both themes meet the 3:1 non-text contrast threshold against adjacent surfaces.

### Theme switching contract

Tri-state preference (`'dark'` | `'light'` | `'auto'`) persisted in `localStorage` under `theme-preference`. `<html data-theme="dark|light">` is applied synchronously by `static/js/theme.js` BEFORE any stylesheet load — the `<script>` is in `<head>` ahead of `<link rel="stylesheet">` to avoid FOUC.

API on `App.theme`:
- `get()` → preference or `'auto'` if unset
- `resolved()` → currently-applied theme (reads `data-theme`)
- `set(pref)` — throws on values other than `'dark'`/`'light'`/`'auto'`. `'auto'` REMOVES the localStorage key (page falls back to OS).

Auto-mode resolution: `darkMedia.matches` → dark, else `lightMedia.matches` → light, else **dark** (canonical default — the design language is dark-first). Reads/writes are try/catch-wrapped so private-browsing degrades to in-memory non-persistent.

Test environment: Playwright pins `color_scheme="no-preference"` so tests don't inherit host OS preference. To capture a specific theme: `page.evaluate("App.theme.set('light')")` + wait for `App.theme.resolved() === 'light'`.

### Typography & icons

Sizes / weights / families / icons are defined in `static/css/fonts.css` and `static/js/icons.js` — read the source rather than mirror the catalog here. Icons pinned to `lucide@v0.265.0`; the pin matters for snapshot-test stability. Add icons by appending to `Icons` in `icons.js` (preserve Lucide's `width="24" height="24" viewBox="0 0 24 24" stroke="currentColor"`).

### App shell — invariants

- The `<a class="skip-link" href="#main-content">` is the FIRST element in `<body>` (before topbar). Activating it sets `location.hash = '#main-content'`; the `hashchange` listener bails because `main-content` is not a registered area. `<main tabindex="-1">` receives programmatic focus.
- App-picker (hamburger) wiring lives INSIDE `renderTopBar()` so `closePicker` is in shared closure scope — no separate `wirePicker` function (that pattern introduced a closure-scope hazard in F3 design review).
- `App.registerArea({sidebarLabel})` — after each `switchTo`, `<aside id="app-sidebar">` receives `aria-label` = `descriptor.sidebarLabel` OR `descriptor.label + ' sidebar'`.

### Hash routing

URL format: `#area[/sub]`. `area` ∈ `{chat, studio, admin}` (defaults to `chat`); `sub` is area-specific (`sessions/<uuid>`, `agents/<name>`, bare admin-category id).

**Critical history invariant**: cross-area navigation uses `location.hash =` (pushes history); area-internal sub-change uses `history.replaceState` (replaces). `replaceState` does NOT fire `hashchange`. If this invariant is broken by using `location.hash =` for sub-navigation, a recursion loop results: `switchTo` → `replaceSub` → `hashchange` → `switchTo` → ...

Net effect: browser back exits the area entirely (or returns to the previous area) — it does NOT walk back through sub-page history within an area.

**Lifecycle**: cold entry runs `init() → activate() → hydrateState(sub)`; same-area sub-change runs `hydrateState(sub)` only. `hydrateState` runs synchronously after `activate` returns, but `activate` may have kicked off async work — `hydrateState` MUST stash a pending target and resolve it when async work completes; it MUST NOT assume data is ready synchronously.

### Keyboard operability patterns

**Listbox/option** — used where a parent row is clickable AND contains a child action affordance (the nested-button rule prohibits `<button>` inside `<button>`). Parent stays `<div role="listbox">`; rows are `<div role="option" tabindex="0" aria-selected="...">`. Keydown fires the activation handler on Enter or Space (preventDefault on Space). All options use `tabindex="0"` (no roving) — WCAG-compliant for 5-20 items.

**Deliberate accepted deviation**: `role="option"` technically should not contain interactive children. In practice NVDA and VoiceOver handle this correctly (announce the option, then the inner button separately).

**Button reset for `<span>` → `<button>` conversions**: add `background: transparent; border: none; cursor: pointer; padding: 0;`.

**SVG-resilient click dispatch**: use `e.target.closest('.chip-remove')` (not `e.target.classList.contains`). Clicking on a child SVG yields `e.target = <svg>` and the `classList` check fails silently.

**`:focus-within` reveal**: hover-only delete affordances (hidden by `display: none`) reveal via the parent's `:focus-within` selector when the user Tabs into the child button.

---

## Testing patterns

### Pytest markers

| Marker | Tests | Default `pytest` | CI |
|---|---|---|---|
| (none) | unit | runs | runs |
| `live` | real LLM APIs (paid) | skipped | skipped |
| `browser` | Playwright functional | skipped (`-m browser`) | runs `-m browser` |
| `pixel` | Playwright visual snapshot | skipped (`-m pixel`) | **never runs** |
| `requires_bwrap` | bwrap integration | skipped | skipped |

Default `addopts` deselects `live`, `browser`, `pixel`, and `requires_bwrap`.

### Test fixtures and conventions

Tests monkeypatch built-in tool registration via `the_one.tools.builtins._TOOL_CLASSES` (module-level dict) — the supported seam; do NOT reach into `BuiltinToolProvider` internals.

The four established test patterns (asyncio_mode auto; `monkeypatch.setenv` HOME for tilde-expansion tests; httpx `MockTransport` `_install_mock` recursion avoidance; kill+reap timeout-budget assertions) live in `tests/CONVENTIONS.md`.

Tests inject a fake `SearchBackend` (and other Protocol-keyed services) by overriding `cross_configs[SearchBackend]` on the per-call view — no monkeypatching of module internals. This IS the supported test seam.

### Browser test isolation

Each browser test gets its own app subprocess on a random port (`socket.bind(('', 0))`) with isolated `tmp_path` data_dir. Teardown sends SIGTERM, escalates to SIGKILL after 10s. Browser navigates to `http://127.0.0.1:{port}` (not `localhost`) to avoid IPv6 first-attempt delay on WSL2.

Playwright fixtures (`playwright_instance`, `browser`) are **module-scoped**, NOT session-scoped — session scope kept the asyncio loop alive across modules and broke standalone smoke tests. Module scope still amortises Chromium within a module.

Tests rely on `data-testid` attributes on load-bearing UI elements rather than CSS classes, so they survive UI redesigns.

### Visual snapshots — local-only

Baselines under `tests/browser/__snapshots__/` are **gitignored** — local regression artifacts, not shared source. First run: `pytest -m pixel --snapshot-update`. Subsequent runs compare; >2% diff fails and writes `<name>-actual.png` + `<name>-diff.png`. CI never runs `-m pixel`. Pixel diffs are a developer's local feedback loop, not a regression gate.

### UI schema metadata

Pydantic Config schemas may declare UI-presentation hints via `Field(json_schema_extra={"ui_hint": "...", "ui_choices": [...]})`. `ui_hint` is the rendering strategy (`"dropdown"`, future: `"slider"`, `"toggle"`); `ui_choices` is a list of `{"value": ..., "label": ...}` dicts. The F6 admin form generator (`App.adminFormHelpers.renderField`) renders finite-set fields as dropdowns rather than free-form inputs. Server-side `_enrich_schema_with_markers` injects `x_marker` per property so the renderer can dispatch on marker class — admin and Studio share the same renderer with mode-specific widget shapes.

---

## Performance instrumentation

`App.perf` (`static/js/perf.js`) is the canonical surface for ad-hoc UI performance measurement. Gated per `gated-debug-instrumentation` convention (URL `?perf=1` OR `localStorage.getItem('the-one-perf') === '1'`). The `enabled` flag is captured at module-load time — toggling localStorage mid-session requires a reload.

**Browser support**: `performance.memory` is Chromium-only and only exposed in same-origin-isolated contexts; values are throttled to 100KB precision. `App.perf.captureHeap()` returns `null` when unavailable; callers must handle null.

Public surface: `mark`, `measure`, `captureHeap`, `dump`, `summary`, `reset`. Every method short-circuits when disabled. Measurement procedures and budgets for specific scenarios (area-switch cycles, long-chat rendering, large session-history list, many-agents-in-studio) live in flight design documents, not this file.

### `make rebuild` wipes Playwright Chromium

After `make rebuild`, `~/.cache/ms-playwright/` is gone — raw `docker exec the-one pytest -m browser` errors with hundreds of "Executable doesn't exist" failures. Recovery: `make _ensure-playwright` (idempotent re-install, ~30-60s). The `make test-browser` chain already chains this; only the raw invocation hits the foot-gun. See `container-test-entrypoints-reach-via-make` convention.
