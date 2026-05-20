# Leg: f7-carry-forward-bundle

**Status**: completed
**Flight**: [First Real Connector — Discord](../flight.md)

## Objective

Land ten F6/F7 debrief carry-forward items in a single doc-and-codification-and-test bundle: wire the F7-shipped `CommandHandler` Protocol consult into `dispatch_inbound` step 11, rewrite the step-11 docstring to match shipped F7 behavior, reconcile the F7 audit-log "original failed pick" promise via doc-fix, codify two project conventions in `agents.md` (HAT-driven contract-flip migration discipline; per-axis-tri-state-override), apply three minor doc fixes (promote `_handle_whoami` same-turn semantic, annotate pool-acquire step-10/step-12 branches, rename `_VALID_ROUTING_SCOPES` → `VALID_ROUTING_SCOPES`), correct an F7 flight-spec class-name typo (`AgentConfigRepository` → `SQLiteAgentStore`), and ship `tests/test_pairing_prefix.py` pinning whitespace-edge cases for `_validate_pairing_prefix`. No Discord-specific work; no schema changes.

## Context

This is the first F8 leg. Per Design Decisions in `flight.md`:

- **"F7 carry-forward batch — single doc-and-codification leg (F8 L1)"** — bundles 10 surfaces; all share the connector-subsystem + `agents.md` surface; each surface is independently revertible.
- **"CommandHandler Protocol consult site lands in F8 L1 (F7 debrief Critical #1)"** — F7 shipped the Protocol type at `base.py:377-419` but did NOT wire dispatcher consumption. F8 L9's slash-command work depends on this consult being live. L1 inserts the consult at `_inbound.py` step 11 BEFORE `_dispatch_builtin_command`, with the same `disposition="command-intercepted"` audit-log treatment when the plugin's `handle_command` returns non-None.
- **"Audit-log 'original failed pick' promise — Decision (b): doc fix"** — F7's `_routing.py` emits a SINGLE `RoutingDecision`; the F7 spec promised a chain of skipped candidates. L1 revises spec language post-hoc + adds a clarifying note. Richer audit deferred to F10.
- **`_VALID_ROUTING_SCOPES` → `VALID_ROUTING_SCOPES` resolved as a RENAME** (not a retroactive `__all__` addition) — `db/models.py` has no `__all__`; the rename is the smaller-blast-radius answer that lets the Studio editor import the constant directly.
- **F6 carry-forward — pairing-prefix whitespace edge cases**: F6 debrief flagged that `_validate_pairing_prefix` had no test coverage for ZWJ, NBSP, smart-quotes, leading/trailing whitespace, empty prefix, or multi-line text. F8 L4 will be the first time these cross-platform whitespace shapes hit real ingestion; pin the cases before L4.

Key learnings from prior flights (from F6 + F7 logs/debriefs):

- The F6 `optional-plugin-hook-via-getattr-sentinel` convention applies to the `CommandHandler` consult: the plugin opts in by implementing `handle_command`; the dispatcher calls via `getattr(plugin, "handle_command", None)` and short-circuits when the attribute is absent.
- The F7 routing engine + 12-step dispatcher is the substrate; L1 only modifies step 11 (insert sub-step) and step-11 docstring; steps 1-10, 12 byte-identical.
- Per `agents.md` `verbatim-message-equality` convention: error messages and audit-log strings shipped by F6/F7 stay byte-identical (substring-tested or string-equality-tested elsewhere in the suite).

## Inputs

What exists before this leg runs:

- `the_one/connectors/_inbound.py` with the 12-step `dispatch_inbound` function. Step 11 currently calls `_dispatch_builtin_command(command_name, args, context)` only (no plugin consult). Step-11 docstring at `_inbound.py:450-456` references F7 leg numbers ("L5 wires" / "L6's leg") that are stale post-F7.
- `the_one/connectors/base.py:377-419` exports `CommandHandler` Protocol with `async def handle_command(envelope, command_name, args) -> CommandResponse | None` — declared in F7 L1; no consumer yet.
- `the_one/connectors/_commands.py` exports `_handle_whoami(context) -> CommandResponse` at line 158; same-turn semantic is in its function docstring.
- `the_one/connectors/_routing.py` exports `RoutingDecision` (frozen dataclass at line 95) and `resolve_routing` (line ~200); module docstring describes single-winner emission.
- `the_one/db/models.py:121` exports `_VALID_ROUTING_SCOPES = frozenset({"channel", "thread", "dm", "peer"})`. File has NO `__all__`. Two consumers inside `db/models.py` (lines 375, 378); JS-side editor at `interfaces/web/static/js/areas/studio/connector-account-editor.js` hard-codes the array literal (independent of the Python symbol).
- `the_one/connectors/README.md` §13 "v1 command vocabulary (M10 F7 L6)" at line 444+ describes the six v1 commands.
- `the_one/agents.md` with §2 "Project conventions" (line ~26) and the Connector subsystem section (line ~310). No `hat-driven-contract-flip-migration-discipline` or `per-axis-tri-state-override` entries yet.
- F7 flight spec at `missions/10-bi-directional-comms-connectors/flights/07-multi-agent-routing-and-command-surface/flight.md` lines 38, 104, 170, 233 — four references to `AgentConfigRepository`, the actual class is `SQLiteAgentStore` (canonical at `the_one/db/repositories.py:69`).
- F6 `_validate_pairing_prefix` at `the_one/connectors/_pairing.py` (already shipped) — no whitespace-edge-case tests currently in `tests/`.
- F1-F7 test suite green on branch `flight/08-planning-discord`.

## Outputs

After this leg completes:

- `the_one/connectors/_inbound.py` step 11 calls `plugin.handle_command(...)` BEFORE `_dispatch_builtin_command(...)` via the `optional-plugin-hook-via-getattr-sentinel` pattern; non-None response emits via the same outbound + audit-log path as the built-in handler; step-11 docstring rewritten to describe shipped behavior.
- `the_one/connectors/_inbound.py` step-10/step-12 boundary annotated with a one-line comment noting the two pool-acquire branches do not share state.
- `the_one/connectors/_routing.py` module docstring carries a clarifying note about the audit-log single-winner emission semantic; the F7 spec language is updated in lockstep.
- `the_one/connectors/README.md` §13 v1 command vocabulary surfaces the `_handle_whoami` same-turn semantic.
- `the_one/db/models.py:121` exports `VALID_ROUTING_SCOPES` (renamed); two internal consumers updated.
- `the_one/agents.md` §2 Project conventions adds two named conventions: `hat-driven-contract-flip-migration-discipline` and `per-axis-tri-state-override`. The Connector subsystem section adds the audit-log single-winner clarifying note.
- F7 flight spec (`missions/.../07-.../flight.md`) corrects four `AgentConfigRepository` references to `SQLiteAgentStore`.
- `tests/test_pairing_prefix.py` (NEW) pins six whitespace edge cases for `_validate_pairing_prefix`.
- F1-F7 test suite continues to pass byte-identically; new test file adds ~6 cases.

## Acceptance Criteria

- [ ] **`CommandHandler` consult wired into step 11.** In `the_one/connectors/_inbound.py`, the `dispatch_inbound` function's step 11 block — currently the `parsed = _parse_command(working_envelope.text)` / `if parsed is not None:` block at lines ~457-493 — runs the following sub-step BEFORE `await _dispatch_builtin_command(command_name, args, context)`:
  ```python
  plugin_handle = getattr(plugin, "handle_command", None)
  if plugin_handle is not None:
      try:
          response = await plugin_handle(working_envelope, command_name, args)
      except Exception:
          logger.exception(
              "dispatch_inbound: plugin handle_command raised "
              "for (command=%s, agent=%s, account=%s); "
              "falling back to built-in handler",
              command_name, decision.agent, account_id,
          )
          response = None
      if response is not None:
          audit_entry["disposition"] = "command-intercepted"
          audit_entry["intercept_source"] = "plugin"
          await chat_repo.append_to_session_metadata(
              session_row.id, "routing", audit_entry,
          )
          try:
              await client.send(
                  OutboundTarget(
                      channel_id=working_envelope.channel_id,
                      thread_id=working_envelope.thread_id,
                  ),
                  response.text,
              )
          except Exception:
              logger.exception(
                  "dispatch_inbound: plugin command-response emit failed "
                  "for (command=%s, agent=%s, account=%s)",
                  command_name, decision.agent, account_id,
              )
          return
  # No plugin consult OR plugin returned None → fall through to the built-in handler below.
  ```
  The built-in `_dispatch_builtin_command` call at `_inbound.py:468` remains untouched; only the plugin-consult sub-step is inserted above it.

- [ ] **Step-11 docstring rewritten.** The comment block at `_inbound.py:450-456` (currently references "L5 wires" / "L6's leg" — F7 leg numbers) is rewritten to describe shipped behavior: (i) parse via `_parse_command`; (ii) plugin consult via `getattr(plugin, "handle_command", None)` per `optional-plugin-hook-via-getattr-sentinel`; (iii) built-in dispatch via `_dispatch_builtin_command`; (iv) fall-through to step 12 (`agent.step`) if neither plugin nor built-in produced a response. New comment cites M10 F8 L1.

- [ ] **Pool-acquire step-10/step-12 boundary annotated.** At the boundary between step 10 (`# 10. Pool acquire for the routed agent` — `_inbound.py:408`) and step 12's `agent.step` call (`# 12. Per-session lock + persist + agent.step + persist` — `_inbound.py:495`), add a single-line comment noting the two pool acquisitions do NOT share state (each `pool_acquire` call returns a distinct `ConnectorClient` reference; the step-10 acquire is for outbound writes from the dispatcher, step-12's `agent.step` may acquire its own clients via the agent's tool calls). Comment is informational; behavior unchanged.

- [ ] **Audit-log single-winner doc fix.** `the_one/connectors/_routing.py` module docstring (top-of-file, NOT the `RoutingDecision` class docstring at line ~94) gains a paragraph explicitly stating: a single `RoutingDecision` is emitted per `dispatch_inbound` invocation; the audit-log entry in `session_metadata["routing"]` captures the eventual winner's `agent`, `match`, `reason`, and `disposition`; rules that were considered but skipped (due to ACL denial, no-eligible-agent, etc.) are NOT enumerated in the audit log. Cross-reference the F8 L1 doc-fix decision. Cited in `agents.md` Connector subsystem section as a one-sentence clarifying note pointing at the `_routing.py` module docstring. **Placement rationale**: module-level docstring is the right home because the single-winner contract is a module-level invariant (true of `resolve_routing` as a function, not specifically of the `RoutingDecision` value type).

- [ ] **F7 spec language reconciled.** In `missions/10-bi-directional-comms-connectors/flights/07-multi-agent-routing-and-command-surface/flight.md`, locate language promising a chain of skipped candidates (the relevant Design Decisions section's audit-log paragraph) and revise post-hoc to match shipped behavior: SINGLE `RoutingDecision` emitted; richer chain-audit deferred to F10. Mark the F7 spec edit with a brief `<!-- F8 L1 post-hoc reconciliation: see flight 8 carry-forward -->` HTML comment so the edit is auditable.

- [ ] **`agents.md` codifications — two named project conventions.** In `the_one/agents.md` Project Conventions section (§2), add two entries. The section is **insertion-ordered, NOT alphabetical** (existing order: `trust-the-runtime`, `canonical-import…`, `structural-Protocol-satisfaction`, `verbatim-message-equality`, `gated-debug-instrumentation`, `host-side-bench-drift-detection`, `container-test-entrypoints-reach-via-make`, `landmark-elements-over-aria-roles`, `function-local-import-to-break-load-cycle`, `optional-plugin-hook-via-getattr-sentinel`, `protocol-widening-for-required-capability`, `live-read-across-lazy-resolver-boundary` — 12 entries total). Position the new entries near related conventions:
  - `hat-driven-contract-flip-migration-discipline` — place near `gated-debug-instrumentation` / `host-side-bench-drift-detection` (the "discipline" / methodology cluster).
  - `per-axis-tri-state-override` — place near `optional-plugin-hook-via-getattr-sentinel` / `protocol-widening-for-required-capability` (the connector-conventions cluster, since `_acl.py` is the citation).
  Entry shape mirrors the existing entries:
  - **`hat-driven-contract-flip-migration-discipline`** — when a HAT iteration flips a previously-shipped contract (semantic, schema, or behavioral default), the migration discipline is: (i) preserve the original behavior as a backward-compatible read-side coercion path; (ii) document the flip + the rationale in the flight log Deviations section; (iii) close out the read-side coercion in a follow-up flight with explicit deprecation language. F6 HAT3 (per-axis tri-state semantic flip) is the citation. Distinct from `verbatim-message-equality` (which only applies to operator-facing error strings).
  - **`per-axis-tri-state-override`** — when an allowlist or ACL composes multiple independent axes (peers, channels, guilds, roles, …), each axis carries an independent tri-state: absent (unrestricted on this axis), `[]` (unrestricted on this axis at account scope; per-agent narrowing may override), non-empty (subset allowed). The composition is per-axis AND, not single-list AND. Citations: F6 `_acl.py` admission logic (account scope); F8 L8 will extend with `guilds` + `roles` axes (n=3 occurrence).

- [ ] **`_handle_whoami` same-turn semantic surfaced in `connectors/README.md` §13.** The existing `_handle_whoami` docstring at `_commands.py:158` notes that the command returns information about the CURRENT routed agent (not a previous turn's agent). Promote to a one-sentence note in §13 v1 command vocabulary entry for `whoami`: clarifies that the response reflects the same `RoutingDecision` that the dispatcher just resolved for this inbound, not stale state from a prior message.

- [ ] **`_VALID_ROUTING_SCOPES` → `VALID_ROUTING_SCOPES` rename.** In `the_one/db/models.py`:
  - Rename the constant at line 121 from `_VALID_ROUTING_SCOPES` to `VALID_ROUTING_SCOPES`.
  - Update the two internal consumers at lines 375 and 378 to use the new name.
  - No external consumers in Python tree (grep verified — only `db/models.py` references it; JS at `connector-account-editor.js` hard-codes the array literal, independent of the Python symbol).
  - L1 does NOT yet have the Studio editor consume the renamed constant; that's a future opportunity. The rename alone unlocks the import path.

- [ ] **F7 spec class-name typo correction.** In `missions/10-bi-directional-comms-connectors/flights/07-multi-agent-routing-and-command-surface/flight.md`, replace `AgentConfigRepository` with `SQLiteAgentStore` at the four cited lines (38, 104, 170, 233). Verify against current code: the canonical class is `SQLiteAgentStore` at `the_one/db/repositories.py:69`; `AgentConfigRepository` does not exist anywhere in the codebase. **Post-edit verification**: `grep -c 'AgentConfigRepository' missions/10-bi-directional-comms-connectors/flights/07-multi-agent-routing-and-command-surface/flight.md` returns `0`; `grep -c 'SQLiteAgentStore' <same-file>` returns `≥6` (the 4 fixes plus the existing correct references at lines 213 and 245).

- [ ] **`tests/test_pairing_prefix.py` extended with four additional whitespace edge cases** (the file ALREADY EXISTS — shipped F7 L8 with 8 tests pinning byte-equality + case-sensitivity; this leg adds the cross-platform whitespace cases that weren't covered). New tests:
  1. Zero-width joiner (U+200D) in the `code` argument, absent from `text` → returns `(False, original_text)`. Explicit inputs: `_validate_pairing_prefix("PAIR ab hello", code="a‍b") == (False, "PAIR ab hello")` (byte-equality means a ZWJ-containing code only matches a ZWJ-containing prefix in text; pinning the contract against silent normalization).
  2. Non-breaking space (U+00A0) between `PAIR` keyword and code → returns `(False, original_text)` (the helper does `text.startswith("PAIR ")` with ASCII space; NBSP causes mismatch).
  3. Smart quotes (U+2018/U+2019 or U+201C/U+201D) inside or wrapping the code → returns `(False, original_text)` UNLESS the caller-provided `code` argument contains the same smart-quote bytes (byte-equality semantic).
  4. Multi-line text where the prefix is on line 1 and the message body on subsequent lines → returns `(True, remainder_including_newlines)` IF `text.startswith(f"PAIR {code} ")` — the helper does not special-case newlines; the remainder is returned verbatim.
  
  Dropped from the original L1 design (already pinned by existing tests): "empty prefix code" (already covered at `tests/test_pairing_prefix.py:29` `test_empty_code_never_matches`); "leading/trailing whitespace tolerated" (CONTRADICTS shipped behavior at `tests/test_pairing_prefix.py:52` `test_leading_whitespace_fails`, which pins `(False, ...)` for leading whitespace — the helper does `text.startswith("PAIR ")` exactly).
  
  Each test uses verbatim string equality on `_validate_pairing_prefix`'s return shape. The 4 new tests append to the existing `TestValidatePairingPrefix` class. Module docstring updated to add F8 L1 cross-reference alongside the existing F7 L8 citation.

- [ ] **Plugin-consult sub-step has at least one integration test** in `tests/test_connectors_inbound.py`. A new test function (e.g. `test_dispatch_inbound_plugin_handle_command_intercepts_before_builtin`) constructs a fixture plugin that implements `handle_command` and returns a non-None `CommandResponse`, drives `dispatch_inbound` against it with `text="/agents"`, and asserts: (i) the plugin's response was emitted via outbound; (ii) the audit log carries `disposition="command-intercepted"` AND `intercept_source="plugin"` (see AC below); (iii) `_dispatch_builtin_command` was NOT invoked (mock + assert_not_called). A second test asserts that when the plugin's `handle_command` returns `None`, the dispatcher falls through to the built-in handler.

- [ ] **Audit-log gains `intercept_source` discriminator key.** Both the plugin-consult path AND the built-in path write `audit_entry["intercept_source"] = "plugin"` or `"builtin"` respectively, in addition to the existing `disposition="command-intercepted"`. The `disposition` vocabulary stays minimal (no new disposition value) — `intercept_source` is the sibling discriminator. F10's audit-log inspector (already deferred) can surface this distinction without breaking the existing disposition contract. Update both the plugin-consult snippet in AC #1 and the existing built-in write at `_inbound.py:470` to add this key in lockstep.

- [ ] **F1-F7 regression**: `docker exec the-one pytest tests/ -x --timeout 30` — test count and pass/fail status unchanged from `flight/08-planning-discord` baseline; no new failures; new tests in `test_pairing_prefix.py` (4 cases) and `test_connectors_inbound.py` (2 plugin-consult cases) are additive.

## Verification Steps

- Run `docker exec the-one pytest tests/test_connectors_inbound.py tests/test_connectors_commands.py tests/test_pairing_prefix.py -x --timeout 30` — all pass; `tests/test_pairing_prefix.py` has 4 NEW test functions (12 total — 8 existing F7 L8 tests + 4 added by this leg); `tests/test_connectors_inbound.py` has 2 NEW test functions for the plugin-consult path.
- Run `docker exec the-one pytest tests/ -x --timeout 30` — full suite passes; no regression in F1-F7 paths.
- Grep `_VALID_ROUTING_SCOPES` across the Python tree — zero hits. Grep `VALID_ROUTING_SCOPES` — three hits (declaration + two consumers in `db/models.py`).
- Grep `AgentConfigRepository` across F7 spec — zero hits. Grep `SQLiteAgentStore` in same spec — at least four hits at lines 38, 104, 170, 233.
- Read `_inbound.py:450-490` — step-11 docstring describes shipped behavior; the plugin-consult sub-step is present BEFORE `_dispatch_builtin_command`.
- Read `agents.md` §2 Project Conventions — `hat-driven-contract-flip-migration-discipline` and `per-axis-tri-state-override` entries exist, alphabetically positioned.
- Read `_routing.py` module docstring — single-winner audit-log clarifying paragraph present.
- Read `connectors/README.md` §13 — `whoami` entry surfaces the same-turn semantic.

## Implementation Guidance

Order surfaces by dependency. Independent items first (low blast radius); CommandHandler consult last (touches the substrate hottest in dispatcher).

1. **`tests/test_pairing_prefix.py`** (NEW, independent). Mirror the existing `tests/test_connectors_pairing.py` (if it exists; otherwise mirror `tests/test_connectors_commands.py` shape). One test function per case; use `pytest.parametrize` if it reads cleaner. Module docstring cites M10 F8 L1.

2. **`_VALID_ROUTING_SCOPES` rename** (independent, small blast radius). Two consumer updates inside `db/models.py`; no other Python consumer. Run `grep -rn '_VALID_ROUTING_SCOPES' the_one/ tests/` before and after — should drop from 3 hits to 0.

3. **F7 spec typo correction** (independent, doc-only). Four sed-style replacements in `missions/.../07-.../flight.md`.

4. **`connectors/README.md` §13 `_handle_whoami` note** (independent, doc-only). One-sentence add to the existing `whoami` paragraph.

5. **`agents.md` codifications** (independent, doc-only). Two new entries in §2 Project Conventions, alphabetically positioned. Each entry follows the existing convention shape: name, one-sentence summary, citation paragraph.

6. **Pool-acquire step-10/step-12 comment** (independent, comment-only). Single line at the boundary in `_inbound.py`.

7. **Audit-log doc fix** (cross-file: `_routing.py` docstring + F7 spec language + `agents.md` Connector subsystem cross-reference). Do all three in one commit-staging pass.

8. **Step-11 docstring rewrite** (must come BEFORE consult wiring — describes the new behavior). Replace the F7-leg-referencing block at `_inbound.py:450-456` with shipped-behavior language; the new docstring should describe the consult-then-fallthrough flow the next sub-step will land.

9. **`CommandHandler` consult wiring** (final; touches the hot dispatcher path). Insert the consult sub-step in step 11 before `_dispatch_builtin_command`. After landing, run `docker exec the-one pytest tests/test_connectors_inbound.py -x --timeout 30` immediately to confirm no F7 regression — the dispatcher has the densest test coverage in M10.

10. **Full-suite green** (validation). Run `docker exec the-one pytest tests/ -x --timeout 30`. Update `flight-log.md` with the leg progress entry.

### Code patterns to follow

- **`getattr` sentinel for the plugin consult** — see `_acl.py` (post-F6) and `_session.py:_derive_title` (post-F4) for the established shape: `hook = getattr(plugin, "<name>", <default>)` then call defensively.
- **Audit-log entry shape** — match the existing `audit_entry["disposition"] = "command-intercepted"` write at `_inbound.py:470`. The plugin-intercepted path SHARES the same disposition string (no new disposition value). Reviewers can tell plugin-vs-builtin from the broader trace context if needed.
- **Exception logging** — match the existing `logger.exception("dispatch_inbound: …")` format strings; F7's `verbatim-message-equality` convention applies to operator-facing strings, NOT to internal log lines, but matching the existing format is cleaner.
- **Test file naming** — `tests/test_pairing_prefix.py` mirrors `the_one/connectors/_pairing.py` module-name; consistent with M10's test-file convention.

## Edge Cases

- **Plugin's `handle_command` raises an exception**: log via `logger.exception(...)` and fall through to `_dispatch_builtin_command` (same as a None return). Do NOT propagate — the plugin's command-handler error MUST NOT block the built-in command set. This matches the F6 `getattr`-sentinel pattern's "defensive fallback" framing.
- **Plugin's `handle_command` blocks indefinitely / runs slow**: L1 does NOT wrap the call in `asyncio.wait_for(...)`. The built-in `_dispatch_builtin_command` is also unbounded — matching the F7-shipped posture. Adding a timeout for plugin paths only (not built-in) would introduce an asymmetry the leg shouldn't carry. **Deferred to F10 hardening**: if Discord plugin HAT (F8 L11) surfaces actual stall scenarios, F10 adds a uniform per-handler timeout. Carry-forward note added to flight log.
- **Plugin's `handle_command` returns `CommandResponse` with empty `text`**: emit anyway. The plugin owns the response-shape contract; the dispatcher doesn't filter on content.
- **Plugin handles a command name that the built-in handler also recognizes**: plugin wins (consult runs first). This is the desired override behavior — plugins SHOULD only handle commands they explicitly want to intercept; for the v1 command set (`/agents`, `/talk-to`, `/whoami`, `/new`, `/reset`, `/help`), most plugins should return `None` and let the built-in handle.
- **Plugin-consult `client.send` raises after audit already persisted**: the audit entry's `disposition="command-intercepted"` + `intercept_source="plugin"` is already in `session_metadata["routing"]` before the send attempt. On send-exception the dispatcher logs and returns; no rollback. This matches the existing built-in path symmetry at `_inbound.py:470-491` (audit written before send; send failures logged-and-return). Documented here so reviewers don't read the asymmetry-that-isn't.
- **Plugin's response is byte-identical to what the built-in would have emitted**: only the plugin's send fires (built-in never runs). The audit log carries `intercept_source="plugin"`. Downstream operators inspecting the audit log can distinguish via this key.
- **`_VALID_ROUTING_SCOPES` rename collides with another constant**: grep shows the new name `VALID_ROUTING_SCOPES` does NOT currently exist anywhere in the Python tree. No collision.
- **F7 spec typo correction — 4 references**: confirm 4 hits before editing; verify post-edit count of `AgentConfigRepository` in F7 spec is 0 and `SQLiteAgentStore` is ≥5 (4 fixes + the existing correct reference at line 213).

## Files Affected

- `the_one/connectors/_inbound.py` — step-11 docstring rewrite + plugin-consult sub-step insertion + step-10/step-12 boundary comment
- `the_one/connectors/_routing.py` — module-docstring clarifying paragraph
- `the_one/connectors/README.md` — §13 `whoami` same-turn-semantic note
- `the_one/db/models.py` — `_VALID_ROUTING_SCOPES` → `VALID_ROUTING_SCOPES` rename (declaration + 2 consumers)
- `the_one/agents.md` — two new Project Conventions entries + Connector subsystem audit-log cross-reference
- `missions/10-bi-directional-comms-connectors/flights/07-multi-agent-routing-and-command-surface/flight.md` — F7 audit-log language reconciliation + 4× `AgentConfigRepository` → `SQLiteAgentStore` typo correction
- `tests/test_pairing_prefix.py` (EXISTING; F7 L8) — extend with four additional whitespace edge cases (ZWJ in code arg, NBSP between PAIR and code, smart quotes inside code, multi-line text remainder)
- `tests/test_connectors_inbound.py` (EXISTING) — extend with two new tests for the plugin-consult sub-step (plugin-intercepts; plugin-returns-None-falls-through-to-builtin)

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing (`docker exec the-one pytest tests/ -x --timeout 30`)
- [ ] Update flight-log.md with leg progress entry
- [ ] **Flight log Deviations / Carry-Forward section** explicitly names the plugin-handler-timeout deferral with cross-reference to F10 (so F10 design finds it during reconnaissance): a one-line entry under a `### F10 Carry-Forward` (or equivalent) sub-header noting "Plugin-handler-timeout (matches built-in unbounded posture) — revisit in F10 if F8 L11 HAT surfaces stall scenarios."
- [ ] Set this leg's status to `landed` (in this file's header)
- [ ] Check off this leg in flight.md
- [ ] Do NOT commit — wait for flight-level review per `/agentic-workflow`

## Citation Audit

10 code-location citations to verify against current code at design-review time. All citations use `file:line` or `file:symbol` form per the Citing Code Locations guideline. Verified at leg-design time:

- `_inbound.py:450-456` — step-11 docstring (refs "L5 wires" / "L6's leg") — **OK** (verified)
- `_inbound.py:457-493` — step-11 implementation block — **OK** (verified at line ~457 onward)
- `_inbound.py:408` — step-10 pool acquire — **OK** (verified)
- `_inbound.py:495` — step-12 agent.step boundary — **OK** (verified)
- `base.py:377-419` — `CommandHandler` Protocol — **OK** (verified)
- `_commands.py:158` — `_handle_whoami` — **OK** (verified)
- `_routing.py:95` — `RoutingDecision` dataclass — **OK** (verified)
- `db/models.py:121` — `_VALID_ROUTING_SCOPES` declaration — **OK** (verified)
- `db/models.py:375, 378` — internal consumers — **OK** (verified)
- `db/repositories.py:69` — `SQLiteAgentStore` canonical declaration — **OK** (verified)

10 citations verified against current code at leg design time. Design-review Developer should re-verify before approval.
