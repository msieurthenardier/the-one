# Leg: agents-md-and-readme-codify

**Status**: completed
**Flight**: [Platform-Send Built-in Tool and Outbound Routing](../flight.md)

## Objective

Codify two named project conventions that F4 either established (`protocol-widening-for-required-capability`) or finally crystallized (`optional-plugin-hook-via-getattr-sentinel` — first instance was F3's `display_channel`). Add Item 8 to the Connector type extension checklist documenting F4's tool-target validation surface (account-scope in F4; F6 layers channel/thread/peer ACLs on top). Add an "Outbound contract" subsection to the Connector subsystem section in `agents.md` documenting the platform-send tool as the only agent→platform path, the F10 baseline carve-out, and the visibility-tagging contract. Update `connectors/README.md` to (1) correct §4's forward-looking statement about F4's outbound shape (F4 chose widening, not optional-hook), (2) add a new "Required capabilities (Protocol-widening)" section, and (3) add a new "Outbound flow trace" section with file:line citations across the outbound path. Docs-only leg — no code changes beyond markdown files. Leg 5 already landed the substantive functionality + tests.

## Context

- **Parent flight design decisions** (see `flight.md` "Design Decisions"):
  - **F4 codifies the `protocol-widening-for-required-capability` convention** in `agents.md` (leg 6 owns the codification). The pattern: when a capability moves from "future" to "required by every plugin in scope," widen the `runtime_checkable` Protocol additively. Citation: `connectors/base.py:ConnectorClient.send` (F4 widening of the F1-shipped Protocol).
  - **Codify `optional-plugin-hook-via-getattr-sentinel`** (first instance was F3's `display_channel`; codify at n=1 per the F3 debrief recommendation). The pattern: an optional plugin extension accessed via `getattr(plugin, '<hook_name>', None)` with a sensible fallback at the call site. The Protocol stays at its minimal shape; future plugin authors aren't forced to write no-op stubs. Distinct from Protocol-widening which applies when ALL plugins in scope must implement.
  - **Outbound contract**: `ConnectorClient.send(target, content) → SendResult` is the only path from agent to platform. `SendToPlatformChannelTool` is the only caller of `send` in production code. F10 baseline carve-out: `send_to_platform_channel` is auto-loaded into `_compute_visible_schemas` when (`connector_attached AND tool_enabled`). Visibility-tagging contract: dispatcher post-step pass; messages get `visibility="operator"` by default; tool_result messages from a successful platform-send call get `visibility=None`.
  - **Connector type extension checklist Item 8**: tool-target validation. F4 ships account-scope validation in `SendToPlatformChannelTool.execute`; F6's `AllowlistResolver` Protocol layers channel/thread/peer ACLs on top via the documented hook point in the tool's execute body.

- **agents.md Project Conventions section structure** (verified at `the_one/agents.md:24-94`): named conventions are added as `### <name>` subsections with a 1-2 paragraph explanation + concrete citations. The new conventions follow the same shape as the existing ones (`trust-the-runtime`, `canonical-import + convenience-re-export`, `function-local-import-to-break-load-cycle`, etc.).

- **agents.md Connector subsystem section structure** (verified at `the_one/agents.md:297-344`): subsections at L301 (Typed-exception hierarchy), L307 (Worker-task-per-entry), L313 (Parallel-pool-not-shared), L319 (Per-Protocol structural-satisfaction discipline), L328 (Encryption-rotation invariant), L338 (Known Issues). The new "Outbound contract" subsection lands BETWEEN the encryption rotation block (L328-336) and Known Issues (L338) — it's a flow/invariant section, not a known-issue.

- **agents.md Connector type extension checklist** (verified at `the_one/agents.md:281-293`): Items 1-7 enumerated, terminating before the `---` divider at L295. The new Item 8 (tool-target validation) appends after Item 7.

- **README §4 "Optional hooks" tail paragraph** (verified at `the_one/connectors/README.md:233`): "Future flights (notably F4's `ConnectorClient` outbound-send extension if it lands as optional) may use the same pattern." F4 chose widening — this prediction needs correction: F4's outbound extension landed as Protocol-widening, NOT optional-hook. Rewrite to reflect the actual choice + cross-reference to the new §10/§11 sections.

- **README current §1-§9 sections** (verified): §1 Package layout, §2 Public API entry points, §3 Protocol decomposition (with the skeleton plugin example), §4 Optional hooks, §5 Test seams, §6 The 'stub' type name, §7 Encryption envelope, §8 Rotation invariant, §9 Cross-references. F4 leg 6 appends NEW sections at the end (§10, §11) to avoid renumbering existing sections.

- **F1 debrief action item ("Skeleton for a real plugin code block")**: already addressed by leg 1's split of the skeleton into `HypotheticalPlatformClient` + `HypotheticalPlatformPlugin`. Leg 6 does NOT need to revisit §3.

- **F2 debrief action item (skeleton's `doctor()` returning non-empty `message`)**: already addressed by leg 1's update — both success and error branches now pass `message=`. Leg 6 does NOT need to revisit §3.

- **F4 leg 5 already updated `agents.md:290` Connector type extension checklist Item 4** to include the v17 entry. Leg 6 does NOT renumber the checklist's other items; only ADDS Item 8.

- **agents.md L290** currently reads: "Flight 8's **v18** migration adds the CHECK via the table-rename ceremony established by v6/v12." Verified — leg 5's renumber landed correctly.

- **Cross-references inside agents.md**: Items 1-7 reference specific files (`db/models.py`, `db/_connector_types.py`, etc.). Item 8 follows the same shape — references `the_one/tools/connector_send.py:SendToPlatformChannelTool.execute` + the F6 hook-point comment marker.

- **State-machine reachability audit**: docs leg; no state machines introduced. Existing tests parse no documentation files for assertions (verified via grep — only inline comment references to `agents.md` in test files; none execute against its content).

- **Cache freshness contract**: no caches touched. Docs are read by humans, not the runtime.

## Inputs

State that must exist before this leg runs:

- F4 branch `flight/04-platform-send-tool-and-outbound`; legs 1-5 uncommitted work in place.
- `the_one/agents.md:86 — "### function-local-import-to-break-load-cycle"` — last existing Project Convention; new conventions append after.
- `the_one/agents.md:96 — "---"` — divider before `## Subsystem contracts`. New convention sections land BEFORE this divider.
- `the_one/agents.md:281-293 (Connector type extension checklist Items 1-7)` — extant; Item 8 appends after Item 7.
- `the_one/agents.md:328-336 (Encryption-rotation invariant subsection)` — extant; new "Outbound contract" subsection lands AFTER this and BEFORE the Known Issues subsection at L338.
- `the_one/connectors/README.md:198-235 (§4 Optional hooks)` — extant; tail paragraph at L233 needs correction.
- `the_one/connectors/README.md:321 (§9 Cross-references)` — last existing section; new §10 + §11 append after the existing content (the file ends partway through §9; verify by reading the tail).
- `the_one/connectors/base.py:ConnectorClient` — extant Protocol with `send` widened (F4 L1 output).
- `the_one/connectors/_session.py:_derive_title` — uses `getattr(plugin, "display_channel", None)` (F3 L3 output).
- `the_one/connectors/_inbound.py:dispatch_inbound` — extant dispatcher with visibility tagging (F4 L4 output).
- `the_one/tools/connector_send.py:SendToPlatformChannelTool` — extant tool (F4 L2 output).

## Outputs

State that must exist after this leg completes:

### agents.md Project Conventions

- New subsection `### optional-plugin-hook-via-getattr-sentinel` appended after `### function-local-import-to-break-load-cycle` (~L94, before the `---` divider at ~L96). Content:
  > An optional plugin extension that not every plugin needs to provide is accessed via `getattr(plugin, "<hook_name>", None)` with a sensible fallback at the call site. The Protocol stays at its minimal shape; future plugin authors aren't forced to write no-op stubs. The consumer's exception-catching behavior tolerates plugin-raised exceptions and falls back. Distinct from `protocol-widening-for-required-capability` (see below) which applies when ALL plugins in scope must implement the method.
  > 
  > Citation: `the_one/connectors/_session.py:_derive_title` accesses `plugin.display_channel` via `getattr(plugin, "display_channel", None)` with try/except fallback to `envelope.channel_id`. `StubPlugin` implements `display_channel` (`the_one/connectors/_stub.py:display_channel`); other plugins don't need to.

- New subsection `### protocol-widening-for-required-capability` appended after the optional-hook convention. Content:
  > When a capability moves from "future" (one plugin needs it, others don't) to "required" (every plugin in scope must implement it), widen the `runtime_checkable` Protocol additively rather than reaching for `getattr`-sentinel. The widening is non-breaking for existing `isinstance(...)` checks at the type level — Python's `runtime_checkable` Protocol checks method-name presence at call time, so existing implementers that satisfy the pre-widened shape continue to pass UNLESS they're missing the newly-required method (in which case the isinstance check correctly fails and surfaces the gap). Implementations still MUST NOT inherit from the Protocol — structural satisfaction is the rule (`structural-Protocol-satisfaction` convention).
  > 
  > Citation: `the_one/connectors/base.py:ConnectorClient.send` widening (F4 leg 1) added `async def send(target: OutboundTarget, content: str) -> SendResult` to the existing 1-method `ConnectorClient` Protocol. Every connector in scope (stub, Discord at F8, second connector at F9) MUST implement `send`; the platform-send tool depends on it being callable. F4's choice contrasts with the `optional-plugin-hook-via-getattr-sentinel` convention used for `display_channel` — outbound has no sensible default (silent drop is leakage; raise is noise) so widening is structurally right.

### agents.md Connector subsystem section

- New subsection `### Outbound contract` inserted between `### Encryption-rotation invariant (three corpora)` (ends ~L336) and `### Known Issues` (starts ~L338). Content:
  > **The platform-send tool is the only agent→platform path.** `the_one/tools/connector_send.py:SendToPlatformChannelTool.execute()` is the sole production caller of `ConnectorClient.send(target, content) → SendResult` (`connectors/base.py:ConnectorClient.send`). No other code path in the codebase reaches `send`. The mission's enforcement-by-construction stance — peer messages can be received and persisted regardless, but outbound delivery is gated solely through this one tool — is realized structurally, not by trust.
  > 
  > **F10 baseline carve-out.** `send_to_platform_channel` is pre-loaded into `_compute_visible_schemas`'s baseline-visible set at `the_one/agent/factory.py:AgentFactory.create()` time when (`bool(config.connector_account_ids) AND tool_enabled`). The two-layer enable check composes the operator gate (`ToolConfigRepository.enabled`) with the per-agent gate (`AgentConfig.is_tool_enabled`). The F10 strict-baseline comment at `the_one/agent/core.py:30-34` documents this as the second exception to the search_tools-only baseline.
  > 
  > **Visibility-tagging contract** (`the_one/connectors/_inbound.py:dispatch_inbound` post-step pass): for every connector-attached session, the dispatcher walks new messages produced by `agent.step()` and tags `Message.visibility`. `Role.USER` messages (the peer inbound) keep their default `visibility=None` (peer-visible). Tool-result messages whose parent tool_call had `name == "send_to_platform_channel"` AND whose content starts with `PLATFORM_SEND_OK_PREFIX` get `visibility=None` (peers saw this content go out via the platform-send tool). Every other new message (assistant text, intermediate tool calls / results, the `continue` virtual tool_result) gets `visibility="operator"`. F5 Chat-UI rendering uses the `visibility` tag to drive the two-layer display.
  > 
  > **System-prompt directives** (`the_one/agent/config.py:compose_system_prompt`): connector-attached agents receive an explicit directive about how their outbound flows. When the tool is operator-enabled: "to reply to peers on the platform, call the `send_to_platform_channel` tool." When operator-disabled: "the platform-send capability is currently DISABLED by the operator; your replies in this session reach the operator only — they do not reach the external platform. Do not claim to have sent anything to the platform." The pair makes the two states (enabled / disabled) deliberate operational modes, not implicit ones.
  > 
  > **Account-scope target validation**: `SendToPlatformChannelTool.execute` rejects `target.account_id ∉ agent.connector_account_ids` with `[error] [constraint] account_id '<id>' is not attached to this agent`. F6's `AllowlistResolver` Protocol will layer channel/thread/peer ACLs on top via the documented hook point in the tool's execute body (search the tool source for the `# F6: AllowlistResolver consultation lands here` marker).
  > 
  > **Cross-reference**: `the_one/connectors/README.md` §11 (Outbound flow trace) has the file:line walk through the full path.

### agents.md Connector type extension checklist

- Item 8 appended after Item 7 (between L293 and the `---` divider at L295). Content:
  > 8. **Tool-target validation** — `the_one/tools/connector_send.py:SendToPlatformChannelTool.execute`. F4 ships account-scope validation: `target.account_id ∈ agent.connector_account_ids` (rejects with the standard `[error] [constraint]` envelope on mismatch). The next layer of ACL — channel-level, thread-level, peer-level — is F6 territory; the tool's execute body carries a `# F6: AllowlistResolver consultation lands here` marker for F6's diff to replace. New connectors do NOT modify the tool; they participate by being registered (layer 3) and being attached to an agent (`AgentConfig.connector_account_ids`).

### connectors/README.md

- **§4 tail paragraph correction**. Replace the existing paragraph at ~L233 ("Future flights (notably F4's `ConnectorClient` outbound-send extension if it lands as optional) may use the same pattern.") with:
  > F4's `ConnectorClient.send` extension landed as **Protocol-widening**, NOT optional-hook — outbound is required by every connector in scope, so widening is the right shape (see §10 below and the `protocol-widening-for-required-capability` convention in `the_one/agents.md`). The `display_channel` precedent above remains the canonical optional-hook example. Future plugin extensions choose between the two patterns based on whether ALL plugins in scope must implement (widen) or only some benefit from implementing (optional hook).

- **NEW §10 "Required capabilities (Protocol-widening)"** appended after the existing §9. Content:
  > F4 widened `ConnectorClient` with `async def send(target: OutboundTarget, content: str) -> SendResult` (Mission 10 leg 1 of Flight 4). Every connector in scope (stub, Discord at F8, the second connector at F9) MUST implement this method — outbound is the only path from agent to platform, and the `SendToPlatformChannelTool` (the sole production caller) depends on the method being callable.
  > 
  > The widening is non-breaking for existing implementations that already provide all the methods the widened Protocol requires. A class missing the new method fails the `runtime_checkable` isinstance check after widening — Python's Protocol semantics check method-name presence at call time, not at type definition. `tests/test_connectors.py::test_client_missing_send_fails_check` pins this behavior.
  > 
  > The convention is codified in `the_one/agents.md` Project Conventions as `protocol-widening-for-required-capability`. Choose Protocol-widening over the optional-hook convention (§4 above) when every plugin in scope MUST implement; choose optional-hook when most plugins benefit but a sensible default exists at the call site (e.g. `display_channel` fallback to `envelope.channel_id`).

- **NEW §11 "Outbound flow trace"** appended after §10. Content:
  > End-to-end walk of an outbound delivery, from the agent's tool call to the platform message:
  > 
  > 1. **Agent invokes the tool**. The LLM's response includes a tool_call with `name="send_to_platform_channel"` and arguments `{target: {account_id, channel_id, thread_id?}, content}`. Agent core dispatches via `the_one/agent/core.py:Agent._execute_tool` (the existing per-tool dispatch path).
  > 
  > 2. **Tool execute() validates target**. `the_one/tools/connector_send.py:SendToPlatformChannelTool.execute()` validates the `target` shape (account_id, channel_id present; thread_id optional), validates `target.account_id ∈ self._connector_account_ids` (account-scope check; rejects with `[error] [constraint]` on mismatch). The `# F6: AllowlistResolver consultation lands here` marker is the hook for F6's channel/thread/peer ACL.
  > 
  > 3. **Tool acquires pool entry**. The tool calls `the_one/connectors/_pool.py:acquire(agent_name, account_id)` to fetch the warm `ConnectorClient`. The pool's worker-task-per-entry pattern ensures `connect` and `disconnect` run on the same task (anyio cross-task `CancelScope` safety). `last_activity` is touched on every successful resolve. Pool errors (`KeyError` for unknown account, `ConnectorRegistrationError` for unregistered plugin type, `ConnectorClientError` subtypes for connect failures, `RuntimeError` during shutdown) surface as `[error] <ExceptionType>: <message>` envelopes.
  > 
  > 4. **Tool calls `client.send`**. `await client.send(target_obj, content)` returns a `SendResult` (`platform_message_id: str | None`, `details: dict`). `ConnectorClientError` subtypes raised from `send` (e.g. `ConnectorRateLimitError`, `ConnectorConnectionError`) surface as the same `[error] <ExceptionType>: <message>` envelope.
  > 
  > 5. **Tool returns the success sentinel**. Format: `f"{PLATFORM_SEND_OK_PREFIX} sent to {account_id}:{channel_id}{thread_clause}: {content!r} (msg_id={result.platform_message_id})"`. The `PLATFORM_SEND_OK_PREFIX = "[platform-send-ok]"` constant lives in `the_one/connectors/__init__.py` and is the single cross-module contract between the tool and the dispatcher.
  > 
  > 6. **Agent appends the tool_result message**. Standard agent core dispatch — the tool's return string becomes a `Role.TOOL` `Message` with `tool_result.tool_call_id` matching the original tool_call's `id`.
  > 
  > 7. **Dispatcher tags visibility post-step**. `the_one/connectors/_inbound.py:dispatch_inbound`'s post-step pass walks new messages: the tool_result whose parent tool_call had `name == "send_to_platform_channel"` AND whose content starts with `PLATFORM_SEND_OK_PREFIX` gets `visibility=None` (platform-visible). Other assistant / tool-result messages produced during the turn get `visibility=OPERATOR_VISIBILITY`.
  > 
  > 8. **Dispatcher persists**. The whole updated `agent.messages` history (including the now-tagged messages) is encoded via `the_one/db/codec.py:encode_messages` and written via `ChatSessionRepository.update`. F5's Chat UI consumes the `visibility` tag for two-layer rendering.

- **Verify the file ends cleanly**. The new §11 ends with the dispatcher persist; verify no trailing whitespace or duplicate headers.

### Flight log + status

- Flight log gains a "Leg Progress: agents-md-and-readme-codify" entry summarizing the conventions codified, the Outbound contract subsection, the checklist Item 8, and the README §10/§11 additions.
- Leg status flipped to `landed` in this file's header.

## Acceptance Criteria

- [ ] `the_one/agents.md` Project Conventions section gains TWO new `### <name>` subsections in this order: `optional-plugin-hook-via-getattr-sentinel` then `protocol-widening-for-required-capability`. Both have non-empty content with at least one concrete code citation each.
- [ ] `the_one/agents.md` Connector subsystem section gains an `### Outbound contract` subsection BETWEEN `### Encryption-rotation invariant (three corpora)` and `### Known Issues`.
- [ ] `the_one/agents.md` Connector type extension checklist gains Item 8 (tool-target validation) AFTER Item 7. The Item 8 text references `the_one/tools/connector_send.py:SendToPlatformChannelTool.execute` and mentions the F6 ACL hook-point marker.
- [ ] `the_one/connectors/README.md` §4 tail paragraph corrected — no longer says "if F4's outbound extension lands as optional"; updated to reflect F4's widening choice and cross-reference §10.
- [ ] `the_one/connectors/README.md` gains a NEW `## §10. Required capabilities (Protocol-widening)` section.
- [ ] `the_one/connectors/README.md` gains a NEW `## §11. Outbound flow trace` section with 8 numbered steps walking from agent tool invocation to dispatcher persist.
- [ ] `grep -n "optional-plugin-hook-via-getattr-sentinel\|protocol-widening-for-required-capability" the_one/agents.md` returns at least two matches each (the heading + at least one in-text reference).
- [ ] `grep -n "Outbound contract\|Item 8\|Tool-target validation" the_one/agents.md` returns matches in the right sections.
- [ ] `grep -n "§10\|§11" the_one/connectors/README.md` returns the new section headings.
- [ ] No code changes (verified by `git diff --stat` showing only `.md` files modified beyond the flight artifacts).
- [ ] `docker exec the-one pytest -x --timeout 30` (full suite) passes (no regressions — docs-only leg, but sanity-check that nothing imports `agents.md` or README content via brittle string-parsing tests).
- [ ] `docker exec the-one ruff check the_one tests` clean (no code changes, but verify).
- [ ] Flight log gains a "Leg Progress: agents-md-and-readme-codify" entry; this file's `**Status**` → `landed`.

## Verification Steps

- `grep -n "### optional-plugin-hook-via-getattr-sentinel\|### protocol-widening-for-required-capability" the_one/agents.md` — both new convention headings present.
- `grep -n "### Outbound contract" the_one/agents.md` — new subsection present in Connector subsystem.
- `grep -n "^8\." the_one/agents.md` (in the Connector type extension checklist context) — new Item 8 present.
- `grep -n "## §10\|## §11" the_one/connectors/README.md` — new sections present.
- `grep -n "F4's.*outbound.*extension.*if it lands as optional" the_one/connectors/README.md` — should return ZERO matches (the corrected paragraph).
- Manual read: open `the_one/agents.md` Project Conventions section; verify the two new conventions read coherently with the existing ones in tone and content density.
- Manual read: open `the_one/connectors/README.md` §11; verify the 8-step trace is accurate against `the_one/tools/connector_send.py`, `the_one/connectors/_pool.py`, `the_one/connectors/_inbound.py`.
- `docker exec the-one pytest -x --timeout 30` — full suite green.
- `docker exec the-one ruff check the_one tests` — clean.

## Implementation Guidance

1. **Add `optional-plugin-hook-via-getattr-sentinel` to agents.md Project Conventions**:
   - Open `the_one/agents.md`. Locate the end of `### function-local-import-to-break-load-cycle` subsection (the convention added in F2 leg 0; ends ~L94, before the `---` divider at ~L96).
   - Insert the new subsection BEFORE the `---` divider. The Outputs section above has the exact content to use.

2. **Add `protocol-widening-for-required-capability` to agents.md Project Conventions**:
   - Append immediately after the `optional-plugin-hook-via-getattr-sentinel` subsection, still BEFORE the `---` divider.
   - The Outputs section above has the exact content.

3. **Add Item 8 to Connector type extension checklist**:
   - Open `the_one/agents.md:281-293`. Locate Item 7 ("`_init_*` state hook"). Append Item 8 immediately after Item 7's last line and BEFORE the `---` divider at L295.
   - The Outputs section above has the exact content.

4. **Add Outbound contract subsection**:
   - Open `the_one/agents.md:328-336` (Encryption-rotation invariant subsection). Locate the end of the subsection (the paragraph ending with "...same shape across all three corpora.").
   - Insert the new `### Outbound contract` subsection AFTER this paragraph and BEFORE `### Known Issues` (at ~L338).
   - The Outputs section above has the exact content.

5. **Update README §4 tail paragraph**:
   - Open `the_one/connectors/README.md`. Locate the paragraph at ~L233 starting with "Future flights (notably F4's `ConnectorClient` outbound-send extension if it lands as optional)...".
   - Replace with the corrected paragraph from the Outputs section above.

6. **Append README §10 + §11**:
   - At the end of `the_one/connectors/README.md` (after §9's content), add:
     ```
     ## §10. Required capabilities (Protocol-widening)
     
     [content from Outputs section]
     
     ## §11. Outbound flow trace
     
     [content from Outputs section]
     ```

7. **Verify no code paths broken**:
   - `docker exec the-one pytest -x --timeout 30` — full suite passes.
   - `docker exec the-one ruff check the_one tests` — clean.

8. **Update flight log**:
   - Append a "Leg Progress: agents-md-and-readme-codify" entry capturing: files modified (two `.md` files + flight log + leg artifact), no test count delta (docs-only), no code changes.

9. **Flip leg `**Status**` to `landed`**. Do NOT commit.

## Edge Cases

- **Section numbering collision in README**: F4 leg 6 appends §10 and §11. The existing file has §1-§9. Verify by `grep -n '^## §' the_one/connectors/README.md` after edit — should show §1 through §11 in order, no duplicates.

- **Tone consistency in agents.md Project Conventions**: existing entries follow a 2-paragraph shape (explanation + citation). Match this shape for the two new conventions.

- **Citation accuracy in the Outbound contract subsection**: every file-path reference must be current. The leg author re-checks each citation against codebase state after legs 1-5 landed.

- **Forward-references in §11 Outbound flow trace**: steps 7 (visibility tagging) and 8 (persist) reference the dispatcher. The flow trace is for outbound, but the dispatcher's post-step pass is what tags the tool_result. If a future reader gets confused that the "outbound flow" includes the inbound dispatcher, add a one-line note explaining the dispatcher is the persistence path for both inbound (peer message) and outbound (tool result) because every connector-attached turn flows through it.

- **F4 leg 5's v17 → v18 renumber in Item 4**: already done by leg 5. Leg 6 does NOT re-edit Item 4 — just adds Item 8.

- **No tests parse the markdown files** (verified via grep). Adding sections cannot break tests.

- **The `display_channel` hook is in `_session.py:_derive_title`, not `_session.py` top-level**: when citing in the optional-hook convention, point at the function symbol (`_derive_title`) rather than a specific line number — the symbol is the durable anchor.

## Files Affected

- `the_one/agents.md` — two new Project Conventions; Outbound contract subsection; Item 8 in checklist
- `the_one/connectors/README.md` — §4 tail-paragraph correction; new §10; new §11
- `missions/10-bi-directional-comms-connectors/flights/04-platform-send-tool-and-outbound/flight-log.md` — append leg-progress entry
- `missions/10-bi-directional-comms-connectors/flights/04-platform-send-tool-and-outbound/legs/06-agents-md-and-readme-codify.md` — flip status to `landed`

---

## Post-Completion Checklist

**Per agentic-workflow batched-review model: do NOT commit; defer to flight-end.**

- [ ] All acceptance criteria verified
- [ ] Full test suite passes (sanity check; no test changes expected)
- [ ] Lint clean (no code changes expected)
- [ ] Update `flight-log.md` with a "Leg Progress: agents-md-and-readme-codify" entry
- [ ] Set this leg's `**Status**` to `landed`
- [ ] Signal `[HANDOFF:review-needed]` — do NOT commit

---

## Citation Audit

All 18 code-location citations verified against current code at leg design time:

| Citation | Status | Evidence |
|---|---|---|
| `the_one/agents.md:24-94 (Project Conventions section)` | OK | Verified earlier |
| `the_one/agents.md:86 (function-local-import-to-break-load-cycle)` | OK | Verified at L86 |
| `the_one/agents.md:96 (--- divider)` | OK | Verified — divider before `## Subsystem contracts` at L98 |
| `the_one/agents.md:281-293 (Connector type extension checklist Items 1-7)` | OK | Verified — Items 1-7 enumerated; `---` at L295 |
| `the_one/agents.md:290 (Item 4 v18 renumber from leg 5)` | OK | Verified — "Flight 8's **v18** migration" |
| `the_one/agents.md:297-344 (Connector subsystem section)` | OK | Verified subsection structure |
| `the_one/agents.md:328-336 (Encryption-rotation invariant)` | OK | Verified |
| `the_one/agents.md:338 (Known Issues)` | OK | Verified — starts at L338 |
| `the_one/connectors/README.md:198-235 (§4 Optional hooks)` | OK | Verified |
| `the_one/connectors/README.md:233 (F4 forward-looking statement)` | OK | Verified |
| `the_one/connectors/README.md:321 (§9 Cross-references)` | OK | Verified — last existing section |
| `the_one/connectors/base.py:ConnectorClient.send` | OK | Verified — F4 L1 widened the Protocol |
| `the_one/connectors/_session.py:_derive_title (display_channel getattr)` | OK | Verified — F3 L3 output |
| `the_one/connectors/__init__.py:PLATFORM_SEND_OK_PREFIX` | OK | Verified — F4 L1 added |
| `the_one/connectors/_inbound.py:dispatch_inbound (post-step visibility tagging)` | OK | Verified — F4 L4 output |
| `the_one/tools/connector_send.py:SendToPlatformChannelTool.execute` | OK | Verified — F4 L2 output |
| `the_one/agent/factory.py:AgentFactory.create (F10 carve-out)` | OK | Verified — F4 L3 output |
| `the_one/agent/core.py:30-34 (F10 strict-baseline comment)` | OK | Verified — F4 L3 extended it |
| `the_one/agent/config.py:compose_system_prompt` | OK | Verified — F4 L3 output |
| `tests/test_connectors.py::test_client_missing_send_fails_check` | OK | Verified — F4 L1 added |
