# Leg: dispatcher-visibility-tagging-and-now-iso-promotion

**Status**: completed
**Flight**: [Platform-Send Built-in Tool and Outbound Routing](../flight.md)

## Objective

Land the two bundled outbound-side touches in `connectors/_inbound.py`: (1) post-step `Message.visibility` tagging for connector-attached sessions — peer-visible (`None`) for the inbound user message AND for tool_result messages whose parent tool_call was a successful `send_to_platform_channel` invocation; `OPERATOR_VISIBILITY` for every other new message in the turn; (2) promote `db/models._now_iso → now_iso` to a public symbol, delete the shadow `_now_iso` definition at `db/repositories.py:25` and the `_utc_now_iso` copies in `connectors/_session.py` and `connectors/_inbound.py`, rewire all call sites to the single public symbol. Invert the existing F3 test `test_dispatch_inbound_persists_agent_reply_with_visibility_none` (which deliberately foreshadows F4) to assert the new operator-tagging behavior, and add five new tests covering the tagging logic's branches.

## Context

- **Parent flight design decisions** (see `flight.md` "Design Decisions"):
  - **Dispatcher visibility tagging: post-step pass, USER messages skipped.** Snapshot `pre_step_len = len(agent.messages)` BEFORE the `agent.step(envelope.text)` async-iter loop. After the loop, walk `agent.messages[pre_step_len:]` and apply: SKIP `Role.USER` messages (peer inbound, already `visibility=None`); tool_result whose parent tool_call had `name == "send_to_platform_channel"` AND `m.content.startswith(PLATFORM_SEND_OK_PREFIX)` → `visibility=None` (platform-visible); else → `visibility=OPERATOR_VISIBILITY`.
  - **Correlation shape**: the `Role.TOOL` message's `m.tool_result` is a `ToolResult` dataclass (`the_one/llm/base.py:27-32`) carrying `tool_call_id: str`. The post-step walk builds a lookup map `{tc.id → tc.name}` from all new assistant messages, then resolves `m.tool_result.tool_call_id` against it. NOT `m.tool_call_id` (no such field on `Message`).
  - **Promote `db/models._now_iso → now_iso` AND rewire `db/repositories.py`'s shadow definition.** Four copies today: `db/models.py:13`, `db/repositories.py:25`, `connectors/_session.py:42`, `connectors/_inbound.py:54`. F4 leg 4 reduces to one (the public `db/models.now_iso`); deletes the other three.
  - **Mid-session enable/disable note** (from leg-3 design decisions): a `Session.agent` cached at `factory.create()` time keeps the prompt that was set then. Leg 4 doesn't change this. The dispatcher rebuilds the agent on every inbound (`factory.create(agent_name)` at `_inbound.py:176` per F3), so the connector-aware prompt + carve-out apply to every turn the dispatcher handles.

- **Dispatcher fires ONLY for connector inbound** (verified): `dispatch_inbound` is the F3-shipped entry point; the only callers are F3's stub-driven tests today and F8's Discord gateway listener later. By definition every session reaching this function is connector-attached. **The visibility-tagging logic does NOT need a per-call `is_connector_attached` predicate** — the dispatcher's existence implies it.

- **The existing F3 test that deliberately foreshadows F4** at `tests/test_connectors_inbound.py:681-702` (`test_dispatch_inbound_persists_agent_reply_with_visibility_none`): its docstring reads "F3 leaves agent replies untagged; F4 will own operator-tagging via the platform-send tool." This test MUST be inverted in leg 4 — renamed to reflect the new behavior, with the assertion flipped from `assert m.visibility is None` to `assert m.visibility == OPERATOR_VISIBILITY`. Per the state-machine reachability audit rule: a test that pins behavior the new state machine breaks must be inverted, renamed, or deleted as part of this leg — not after.

- **The user-message visibility test at `tests/test_connectors_inbound.py:659-678`** (`test_dispatch_inbound_persists_inbound_with_visibility_none`): asserts the inbound user message gets `visibility=None`. This must CONTINUE to pass after leg 4 because the post-step walk SKIPS `Role.USER` messages, preserving their default `visibility=None`.

- **`db/repositories.py:25` shadow `_now_iso`**: identical to `db/models.py:13`'s definition. The six call sites at `db/repositories.py:100, 179, 248, 389, 539, 633` all rewire to the public `now_iso` import. After deletion: `from datetime import datetime, timezone` at `db/repositories.py:6` becomes unused — ruff will flag with `F401`. Remove the import too.

- **`connectors/_session.py:42 _utc_now_iso`** and `connectors/_session.py:183` (which assigns `now_iso = _utc_now_iso()` to a LOCAL VARIABLE): the local variable name collides with the promoted public function name. Resolution: rename the local variable to `current_iso` (or another non-colliding name), import the function as `now_iso`. The cleaner shape; no aliasing.

- **`connectors/_session.py:145, 172` stale comment references** to `_utc_now_iso`: rewrite to reference `now_iso` for symmetry. Architect-flagged in flight design review.

- **`connectors/_inbound.py:54 _utc_now_iso`** and the call site at `connectors/_inbound.py:171` (`await chat_repo.update_last_inbound(session_row.id, _utc_now_iso())`): single call site; replace with `now_iso()` from the import. The header docstring at L31 mentions `_utc_now_iso` — likely needs updating too.

- **Tests touching the `_now_iso` symbol**: grep confirms only comment-level references in `tests/test_session_lifecycle.py:131` and `tests/test_db_repositories.py:1019`. No `from ... import _now_iso` anywhere. Renaming is safe. **Leg 4 ALSO updates these two test comments** to mention `now_iso` instead of `_now_iso` — stale comments mentioning a non-existent function would mislead future readers. The post-leg grep verification widens to include `tests/`: `grep -rn '_now_iso\|_utc_now_iso' the_one/ tests/` should return ZERO matches.

- **`tests/test_connectors_inbound.py` fixtures**: `_seed_provider_and_agent`, `_seed_stub_account`, `register_for_test("stub", StubPlugin)`, `_make_factory`, `_envelope`. F3 builds these in-file. F4 leg 5's planned shared-helper extraction (per F3 debrief carry-forward) is NOT in scope for leg 4 — leg 4 uses the in-file helpers as-is.

- **`Message.visibility` permissivity**: the dataclass is permissive (`visibility: str | None`, not `Literal["operator"] | None`). Mitigation is the `OPERATOR_VISIBILITY` constant published from `the_one.connectors` — leg 4 imports it as the only literal source.

- **Cross-leg impact**: leg 5 (e2e tests) will exercise the dispatcher's visibility tagging end-to-end via the platform-send tool. Leg 4 ships the tagging plumbing + unit-level tests; leg 5 ships the integration tests against `SendToPlatformChannelTool.execute()` driving the path.

## Inputs

State that must exist before this leg runs:

- F4 branch `flight/04-platform-send-tool-and-outbound`; legs 1+2+3 uncommitted work in place.
- `the_one/llm/base.py:Message.visibility` field is present (F3 L2 output, verified).
- `the_one/llm/base.py:27-32 (ToolResult dataclass with tool_call_id)` — extant since F1.
- `the_one/llm/base.py:42-90 (Message dataclass with tool_calls + tool_result)` — extant.
- `the_one/connectors/__init__.py:52 — "OPERATOR_VISIBILITY = \"operator\""` — extant since F3 L2.
- `the_one/connectors/__init__.py:PLATFORM_SEND_OK_PREFIX = "[platform-send-ok]"` — leg 1 output.
- `the_one/connectors/_inbound.py:dispatch_inbound` — extant F3 L4 dispatcher.
- `the_one/connectors/_inbound.py:54-55 — "def _utc_now_iso..."` — extant local helper to delete.
- `the_one/connectors/_inbound.py:171 — "await chat_repo.update_last_inbound(session_row.id, _utc_now_iso())"` — single call site.
- `the_one/connectors/_inbound.py:202-203 — "async for _ in agent.step(envelope.text): pass"` — async-iter loop; the visibility-tagging insertion lives AFTER this loop and BEFORE `encode_messages(agent.messages)` at L212.
- `the_one/connectors/_inbound.py:212 — "encoded = encode_messages(agent.messages)"` — the persist call. Visibility tagging happens immediately before this line.
- `the_one/connectors/_session.py:42-43 — "def _utc_now_iso..."` — extant local helper to delete.
- `the_one/connectors/_session.py:145, 172 (stale `_utc_now_iso` references in comments/docstrings)` — extant; rewrite to `now_iso`.
- `the_one/connectors/_session.py:183 — "now_iso = _utc_now_iso()"` — local-variable name collision; rename to `current_iso`.
- `the_one/db/models.py:13-14 — "def _now_iso..."` — extant canonical definition; rename to `now_iso` (drop underscore).
- `the_one/db/models.py:29-30, 70-71, 83, 94-95, 138-139, 205-206, 230-231` — internal `_now_iso` callers (Field default_factory references). All update to `now_iso`.
- `the_one/db/repositories.py:6 — "from datetime import datetime, timezone"` — sole consumer is the shadow `_now_iso`; remove the import when the shadow is deleted.
- `the_one/db/repositories.py:25-26 — "def _now_iso..."` — shadow definition to delete.
- `the_one/db/repositories.py:100, 179, 248, 389, 539, 633 (×2), 778, 800, 910 — 10 call sites of `_now_iso`` (9 lines; L633 contains two calls) — rewire ALL to public `now_iso` from `db.models`.
- `the_one/db/repositories.py:13-21 — existing `from the_one.db.models import (...)` block` — extend with `now_iso`.
- `tests/test_connectors_inbound.py:659-678 (test_dispatch_inbound_persists_inbound_with_visibility_none)` — extant; MUST continue to pass.
- `tests/test_connectors_inbound.py:681-702 (test_dispatch_inbound_persists_agent_reply_with_visibility_none)` — extant; MUST be inverted in leg 4.

## Outputs

State that must exist after this leg completes:

### `now_iso` promotion

- `the_one/db/models.py:13-14` defines `now_iso() -> str` (public; underscore dropped). All 13 internal `_now_iso` references inside `db/models.py` update to `now_iso`.
- `the_one/db/repositories.py:25-26 (shadow `_now_iso`)` deleted.
- `the_one/db/repositories.py:6 (datetime/timezone import)` deleted (no longer used after the shadow is gone).
- `the_one/db/repositories.py:13-21 (db.models import block)` extended with `now_iso`.
- `the_one/db/repositories.py` ten call sites at L100, L179, L248, L389, L539, L633 (×2), L778, L800, L910: each `_now_iso()` → `now_iso()`. L633 has two `_now_iso()` calls on the same line — both replaced.
- `the_one/connectors/_session.py:37-43` `_utc_now_iso` def + leading NOTE block: deleted.
- `the_one/connectors/_session.py` top-of-module imports: `from the_one.db.models import now_iso` added alongside the existing `from the_one.db.models import ChatSession, ConnectorAccount`. **Verify no circular-import surfaces** — `db/models.py` doesn't import from `connectors/`, so the top-level import is safe (no function-local-import-to-break-load-cycle convention needed).
- `the_one/connectors/_session.py:183` local variable renamed from `now_iso = _utc_now_iso()` to `current_iso = now_iso()`. Callers at L189, L190, L197 rewire to `current_iso`.
- `the_one/connectors/_session.py:145, 172` stale comment references rewritten: `_utc_now_iso` → `now_iso`.
- `the_one/connectors/_inbound.py:54-55` `_utc_now_iso` def: deleted.
- `the_one/connectors/_inbound.py` top-of-module imports: add `from the_one.db.models import now_iso`. The existing `from datetime import datetime, timezone` import at L31 is still consumed by the dispatcher's existing code (the leg-4 author verifies if it remains used; if not, remove). **Likely unused** post-deletion — verify and remove.
- `the_one/connectors/_inbound.py:171` call site: `_utc_now_iso()` → `now_iso()`.
- `the_one/connectors/_inbound.py:31 (header docstring)` stale `_utc_now_iso` reference (if any): rewrite to `now_iso`.
- Post-leg `grep -rn '_now_iso\|_utc_now_iso' the_one/` returns ZERO matches. Verified by the implementing agent.

### Dispatcher visibility tagging

- `the_one/connectors/_inbound.py` top-of-module imports: add `from the_one.connectors import OPERATOR_VISIBILITY, PLATFORM_SEND_OK_PREFIX`. (The package's `__init__` already exports both — single-source-of-truth import.)
- `the_one/connectors/_inbound.py:dispatch_inbound` body:
  - Insert `pre_step_len = len(agent.messages)` IMMEDIATELY BEFORE the `async for _ in agent.step(envelope.text): pass` loop at L202 (after the `try:` line at L194 and after the ContextVar set at L193).
  - After the `agent.step` loop (L203) and BEFORE the existing `encoded = encode_messages(agent.messages)` line at L212, insert the visibility-tagging pass:
    ```python
    # F4 (M10) L4: post-step visibility tagging.
    # The dispatcher fires only for connector-attached inbound; every
    # new message in the turn is tagged either platform-visible (None)
    # or operator-only ("operator") for the F5 Chat UI's two-layer
    # rendering. The mission's enforcement-by-construction stance
    # (platform-send tool is the ONLY agent→platform path) makes
    # leakage impossible regardless of tagging; visibility is a
    # presentation metadata layer, not a security gate.
    #
    # Rules:
    # - Role.USER (the inbound peer message at index pre_step_len)
    #   keeps its default visibility=None — peer-visible by definition.
    # - Role.TOOL whose parent tool_call.name == "send_to_platform_channel"
    #   AND content starts with PLATFORM_SEND_OK_PREFIX → visibility=None
    #   (peers saw this content go out via the platform-send tool).
    # - Everything else → OPERATOR_VISIBILITY (assistant text +
    #   intermediate tool calls/results stay operator-only).
    new_msgs = agent.messages[pre_step_len:]
    # Build {tool_call_id → tool_name} lookup from new assistant msgs
    tool_call_names: dict[str, str] = {}
    for msg in new_msgs:
        if msg.role == Role.ASSISTANT:
            for tc in msg.tool_calls:
                tool_call_names[tc.id] = tc.name
    # Tag each new message per the rules above.
    for msg in new_msgs:
        if msg.role == Role.USER:
            # Inbound peer message — already visibility=None.
            continue
        is_successful_platform_send = (
            msg.role == Role.TOOL
            and msg.tool_result is not None
            and tool_call_names.get(msg.tool_result.tool_call_id)
            == "send_to_platform_channel"
            and msg.content.startswith(PLATFORM_SEND_OK_PREFIX)
        )
        msg.visibility = None if is_successful_platform_send else OPERATOR_VISIBILITY
    ```
  - The tagging happens INSIDE the `try:` block (the existing `try / finally` for the ContextVar at L194/L220-223 stays), BEFORE `encode_messages` at L212. The `finally` block remains unchanged.

### Test updates

- `tests/test_connectors_inbound.py:681-702 (test_dispatch_inbound_persists_agent_reply_with_visibility_none)`: INVERTED. Rename to `test_dispatch_inbound_persists_agent_reply_with_visibility_operator`. Assertion flips: `assert m.visibility is None` → `assert m.visibility == "operator"` (import `OPERATOR_VISIBILITY` from `the_one.connectors` and use the constant). Update docstring: "F4 L4 owns operator-tagging; the dispatcher's post-step pass tags assistant text in a connector-attached session as `visibility='operator'` so the F5 Chat UI renders it in the operator-only layer."
- `tests/test_connectors_inbound.py:659-678 (test_dispatch_inbound_persists_inbound_with_visibility_none)`: NO changes; the post-step pass skips USER messages so this assertion still holds. Add a one-line comment noting "F4 L4: USER messages are skipped by the visibility-tagging pass — the peer inbound stays `visibility=None`."

- NEW tests in `tests/test_connectors_inbound.py`:
  - `test_dispatch_inbound_tags_assistant_text_as_operator` — drive an inbound through a `MockProvider` configured to respond with plain text (no tool calls). After dispatch, assert the assistant message in the persisted history has `visibility == OPERATOR_VISIBILITY`.
  - `test_dispatch_inbound_tags_successful_send_tool_result_as_platform_visible` — drive an inbound through a `_BlockingProvider`-style fixture (or scripted `MockProvider`) that returns a tool_call to `send_to_platform_channel` with valid args. The platform-send tool execute() returns the `PLATFORM_SEND_OK_PREFIX`-prefixed success string. Assert: the assistant message containing the tool_call has `visibility="operator"`; the tool_result message has `visibility=None`. Requires:
    - Seeding an agent with `connector_account_ids=["acct-test"]` so the factory's leg-3 carve-out applies AND the platform-send tool is registered in the agent's tools.
    - Stub plugin's `StubClient.send` records to `outbound_records`; the tool execute() builds the success string.
  - `test_dispatch_inbound_tags_failed_send_tool_result_as_operator` — drive an inbound similar to above but with `StubPlugin.send_should_raise = ConnectorConnectionError("test failure")`. The tool execute() returns an `[error] ConnectorConnectionError: ...` envelope (NO `PLATFORM_SEND_OK_PREFIX`). Assert: the tool_result message has `visibility=OPERATOR_VISIBILITY` (failure envelope does NOT trigger the platform-visible carve-out).
  - `test_dispatch_inbound_tagging_uses_tool_result_tool_call_id_correlation` — drive an inbound producing TWO assistant tool_calls in one assistant message: one to `send_to_platform_channel` (success), one to a non-platform-send tool (e.g. a stubbed in-test tool that returns a string starting with `PLATFORM_SEND_OK_PREFIX` to verify the prefix-alone isn't sufficient). Assert: the platform-send's tool_result has `visibility=None`; the non-platform-send tool's tool_result has `visibility=OPERATOR_VISIBILITY` EVEN IF its content has the prefix (correlation by `tool_call_id` + tool-name, not by prefix alone). This test guards against future regressions where the correlation logic is mis-simplified.
  - `test_dispatch_inbound_continue_tool_call_is_operator_visible` — drive an inbound producing an assistant message with the `continue` virtual signal tool call (no real tool dispatch). The agent's `continue` signal generates an assistant message with a `tool_calls` entry but the corresponding tool_result is synthesized by the agent core (`_handle_continue` at agent/core.py — verify behavior). Assert: any such assistant or tool_result message in a connector-attached session has `visibility=OPERATOR_VISIBILITY`. This tests the default-tagging branch.

- Flight log gains a "Leg Progress: dispatcher-visibility-tagging-and-now-iso-promotion" entry.
- Leg status flipped to `landed` in this file's header.

## Acceptance Criteria

### `now_iso` promotion

- [ ] `the_one/db/models.py` defines `now_iso() -> str` (public, no leading underscore). All 13 internal callers in `db/models.py` updated.
- [ ] `the_one/db/repositories.py:25 (shadow `_now_iso` def)` is DELETED.
- [ ] `the_one/db/repositories.py:6 (from datetime import datetime, timezone)` is DELETED (unused after shadow deletion).
- [ ] `the_one/db/repositories.py` imports `now_iso` from `the_one.db.models` (added to the existing import block).
- [ ] `the_one/db/repositories.py` ALL TEN call sites use `now_iso()` (verbatim, not aliased): L100, L179, L248, L389, L539, L633 (×2 — both calls on the same line), L778, L800, L910. Verify post-edit with `grep -n '_now_iso\|now_iso(' the_one/db/repositories.py` — should show only `now_iso()` invocations and the import line.
- [ ] `the_one/connectors/_session.py:42 (_utc_now_iso def)` is DELETED. The 6-line NOTE block above it (L37-41) is DELETED.
- [ ] `the_one/connectors/_session.py` imports `now_iso` from `the_one.db.models` at module top.
- [ ] `the_one/connectors/_session.py:183` local variable renamed from `now_iso = _utc_now_iso()` to `current_iso = now_iso()`. The 3 dependent callers at L189, L190, L197 use `current_iso`.
- [ ] `the_one/connectors/_session.py:145, 172` stale comment references rewritten to `now_iso`.
- [ ] `the_one/connectors/_inbound.py:54-55 (_utc_now_iso def)` is DELETED.
- [ ] `the_one/connectors/_inbound.py` imports `now_iso` from `the_one.db.models` at module top.
- [ ] `the_one/connectors/_inbound.py:171` call site uses `now_iso()`.
- [ ] `the_one/connectors/_inbound.py` `from datetime import datetime, timezone` (if present) verified unused after deletion of `_utc_now_iso`, removed if so.
- [ ] `grep -rn '_now_iso\|_utc_now_iso' the_one/ tests/` returns ZERO matches (stale comments in `tests/test_session_lifecycle.py:131` and `tests/test_db_repositories.py:1019` are also updated to reference `now_iso`).

### Dispatcher visibility tagging

- [ ] `the_one/connectors/_inbound.py` imports `OPERATOR_VISIBILITY` and `PLATFORM_SEND_OK_PREFIX` from `the_one.connectors`.
- [ ] `the_one/connectors/_inbound.py:dispatch_inbound` captures `pre_step_len = len(agent.messages)` BEFORE the `agent.step` async-iter loop.
- [ ] After the `agent.step` loop and BEFORE `encode_messages(agent.messages)`, the dispatcher walks `agent.messages[pre_step_len:]` and tags visibility per the rules: USER skipped; successful platform-send tool_result → `visibility=None`; everything else → `visibility=OPERATOR_VISIBILITY`.
- [ ] The correlation between tool_result and parent tool_call uses `m.tool_result.tool_call_id` (NOT `m.tool_call_id` — no such field on Message). Verified at `the_one/llm/base.py:27-32`.
- [ ] The build-and-lookup pattern (build `{tc.id → tc.name}` dict from new assistant msgs, then resolve per tool_result) is used — NOT a backwards-walk per tool_result (faster, cleaner).
- [ ] The platform-visible carve-out predicate REQUIRES ALL THREE: `msg.role == Role.TOOL` AND tool_call.name == `"send_to_platform_channel"` AND `msg.content.startswith(PLATFORM_SEND_OK_PREFIX)`. Two of three is not enough.

### Test updates

- [ ] `tests/test_connectors_inbound.py:681 (test_dispatch_inbound_persists_agent_reply_with_visibility_none)` is RENAMED to `test_dispatch_inbound_persists_agent_reply_with_visibility_operator`. Assertion flipped to `assert m.visibility == "operator"` (using `OPERATOR_VISIBILITY` constant). Docstring updated.
- [ ] `tests/test_connectors_inbound.py:659 (test_dispatch_inbound_persists_inbound_with_visibility_none)` still passes UNCHANGED (USER skip preserves visibility=None).
- [ ] NEW test `test_dispatch_inbound_tags_assistant_text_as_operator` passes.
- [ ] NEW test `test_dispatch_inbound_tags_successful_send_tool_result_as_platform_visible` passes.
- [ ] NEW test `test_dispatch_inbound_tags_failed_send_tool_result_as_operator` passes.
- [ ] NEW test `test_dispatch_inbound_tagging_uses_tool_result_tool_call_id_correlation` passes.
- [ ] NEW test `test_dispatch_inbound_continue_tool_call_is_operator_visible` passes.
- [ ] `docker exec the-one pytest tests/test_connectors_inbound.py tests/test_db_repositories.py tests/test_db_models.py tests/test_connectors_session.py -x --timeout 30` passes.
- [ ] `docker exec the-one pytest -x --timeout 30` (full suite) passes. No regression on F1/F2/F3 surfaces, legs 1-3 surfaces.
- [ ] `docker exec the-one ruff check the_one tests` clean.
- [ ] Flight log gains a "Leg Progress: dispatcher-visibility-tagging-and-now-iso-promotion" entry; this file's `**Status**` → `landed`.

## Verification Steps

- `docker exec the-one pytest tests/test_connectors_inbound.py -v -x --timeout 30` — existing tests pass (1 renamed-and-inverted, 1 unchanged); 5 new tests pass.
- `docker exec the-one pytest tests/test_db_repositories.py tests/test_db_models.py tests/test_connectors_session.py -v -x --timeout 30` — no regression on the `now_iso`-touching modules.
- `docker exec the-one pytest -x --timeout 30` — full suite green.
- `docker exec the-one ruff check the_one tests` — clean (no F401 unused-imports).
- `grep -rn '_now_iso\|_utc_now_iso' the_one/` — ZERO matches.
- `grep -n 'now_iso' the_one/db/models.py the_one/db/repositories.py the_one/connectors/_session.py the_one/connectors/_inbound.py` — only public `now_iso` references (no leading underscore on the function symbol).
- `grep -n 'visibility' the_one/connectors/_inbound.py` — multiple matches including the new tagging block.
- Manual trace: read `the_one/connectors/_inbound.py:dispatch_inbound` end-to-end and confirm the tagging block sits BEFORE `encode_messages` and AFTER `agent.step` completes.

## Implementation Guidance

1. **Promote `_now_iso → now_iso` in `the_one/db/models.py`**:

   - Rename the function at L13: `def _now_iso() -> str:` → `def now_iso() -> str:`. Body unchanged.
   - Find/replace all 13 internal references inside `db/models.py` (Field default_factory references at L29, L30, L70, L71, L83, L94, L95, L138, L139, L205, L206, L230, L231). The string `_now_iso` → `now_iso`.
   - Verify: `grep -n 'now_iso\|_now_iso' the_one/db/models.py` shows only `now_iso` (no underscored).

2. **Delete the shadow in `the_one/db/repositories.py`**:

   - Delete L25-26 (the def line + body).
   - Delete L6 (`from datetime import datetime, timezone`) — no longer used.
   - Extend the `from the_one.db.models import (...)` block at L13-21 with `now_iso`:
     ```python
     from the_one.db.models import (
         ChatSession,
         ConnectorAccount,
         KBItem,
         KnowledgeBase,
         LLMProviderConfig,
         MCPSource,
         ToolConfig,
         now_iso,
     )
     ```
   - Find/replace ALL 10 call sites (`_now_iso()` → `now_iso()`): L100, L179, L248, L389, L539, L633 (×2 on same line), L778, L800, L910. Easiest mechanical approach: `grep -n '_now_iso' the_one/db/repositories.py` to enumerate all hits, then Edit each line. After edits, re-run the grep — should return only the import line (or zero if you removed the import-alias scheme).
   - Verify: `grep -n 'now_iso\|_now_iso\|datetime\|timezone' the_one/db/repositories.py` shows only `now_iso` (and the import line); zero `_now_iso`, zero `datetime` (unless used elsewhere in the file — verify).

3. **Update `the_one/connectors/_session.py`**:

   - Delete the NOTE block at L37-41 (the entire comment block explaining why `_utc_now_iso` exists).
   - Delete the `_utc_now_iso` def at L42-43.
   - Add to imports at module top (after the existing `from the_one.db.models import ChatSession, ConnectorAccount`):
     ```python
     from the_one.db.models import ChatSession, ConnectorAccount, now_iso
     ```
   - At L145 (docstring referencing `_utc_now_iso`): rewrite to `now_iso`.
   - At L172 (comment referencing `_utc_now_iso`): rewrite to `now_iso`.
   - At L183 (`now_iso = _utc_now_iso()`): rename the LOCAL VARIABLE to `current_iso`:
     ```python
     current_iso = now_iso()
     ```
   - At L189, L190, L197 (the three call sites using the local `now_iso` variable): rewire to `current_iso`.

4. **Update `the_one/connectors/_inbound.py`**:

   - Delete the `_utc_now_iso` def at L54-55.
   - If `from datetime import datetime, timezone` is at L31 (and ONLY used by `_utc_now_iso`), delete the import. Verify by `grep -n 'datetime\|timezone' the_one/connectors/_inbound.py` after deletion — should return zero or only docstring matches.
   - Verify the header docstring (`_inbound.py:1-24`) does NOT mention `_utc_now_iso` — confirmed at design review (only the import block and the def site reference the helper). No docstring edit needed.
   - Add to imports at module top:
     ```python
     from the_one.db.models import now_iso
     from the_one.connectors import OPERATOR_VISIBILITY, PLATFORM_SEND_OK_PREFIX
     ```
   - At L171 (`await chat_repo.update_last_inbound(session_row.id, _utc_now_iso())`): replace `_utc_now_iso()` with `now_iso()`.

5. **Add the visibility-tagging block in `dispatch_inbound`**:

   - Locate the existing `try / finally` at L193-223. The structure is:
     ```python
     token = current_chat_session_id.set(session_row.id)
     try:
         async for _ in agent.step(envelope.text):
             pass
         encoded = encode_messages(agent.messages)
         updated = db_session.model_copy(...)
         await chat_repo.update(updated)
     finally:
         current_chat_session_id.reset(token)
     ```
   - INSERT `pre_step_len = len(agent.messages)` IMMEDIATELY AFTER `token = current_chat_session_id.set(...)` and BEFORE the `try:` line. This keeps the snapshot OUTSIDE the try block — it's a pure read, no exception risk.
   - INSERT the visibility-tagging block AFTER `async for _ in agent.step(envelope.text): pass` and BEFORE `encoded = encode_messages(agent.messages)`:
     ```python
     # F4 (M10) L4: post-step visibility tagging.
     # The dispatcher fires only for connector-attached inbound; every
     # new message in the turn is tagged either platform-visible (None)
     # or operator-only ("operator") for the F5 Chat UI's two-layer
     # rendering. The mission's enforcement-by-construction stance
     # (platform-send tool is the ONLY agent→platform path) makes
     # leakage impossible regardless of tagging; visibility is a
     # presentation metadata layer, not a security gate.
     #
     # Rules:
     # - Role.USER (the inbound peer message at index pre_step_len)
     #   keeps its default visibility=None — peer-visible by definition.
     # - Role.TOOL whose parent tool_call.name == "send_to_platform_channel"
     #   AND content starts with PLATFORM_SEND_OK_PREFIX → visibility=None
     #   (peers saw this content go out via the platform-send tool).
     # - Everything else → OPERATOR_VISIBILITY (assistant text +
     #   intermediate tool calls/results stay operator-only).
     new_msgs = agent.messages[pre_step_len:]
     tool_call_names: dict[str, str] = {}
     for msg in new_msgs:
         if msg.role == Role.ASSISTANT:
             for tc in msg.tool_calls:
                 tool_call_names[tc.id] = tc.name
     for msg in new_msgs:
         if msg.role == Role.USER:
             continue
         is_successful_platform_send = (
             msg.role == Role.TOOL
             and msg.tool_result is not None
             and tool_call_names.get(msg.tool_result.tool_call_id)
             == "send_to_platform_channel"
             and msg.content.startswith(PLATFORM_SEND_OK_PREFIX)
         )
         msg.visibility = None if is_successful_platform_send else OPERATOR_VISIBILITY
     ```

6. **Invert the existing F3 test in `tests/test_connectors_inbound.py`**:

   - At L681-702, rename `test_dispatch_inbound_persists_agent_reply_with_visibility_none` to `test_dispatch_inbound_persists_agent_reply_with_visibility_operator`.
   - Update the docstring:
     ```python
     async def test_dispatch_inbound_persists_agent_reply_with_visibility_operator(
         isolated_db,
     ) -> None:
         """The persisted assistant reply has ``visibility="operator"`` —
         F4 L4 tags every non-USER new message in a connector-attached
         session as operator-only by default. The successful-platform-
         send-tool_result carve-out is exercised in
         ``test_dispatch_inbound_tags_successful_send_tool_result_as_platform_visible``.
         """
     ```
   - Replace the assertion body:
     ```python
     from the_one.connectors import OPERATOR_VISIBILITY  # add to imports if absent
     ...
     assistant_msgs = [m for m in history if m.role == Role.ASSISTANT]
     assert assistant_msgs
     for m in assistant_msgs:
         assert m.visibility == OPERATOR_VISIBILITY
     ```

7. **Add the new tests in `tests/test_connectors_inbound.py`**:

   The new tests follow the existing F3 test patterns. The trickiest one — `test_dispatch_inbound_tags_successful_send_tool_result_as_platform_visible` — needs the agent to actually invoke the platform-send tool. Two constraints to understand BEFORE writing the test:

   - **MockProvider tool-call config shape** (`the_one/llm/mock.py:68-78`): the actual nesting is `config={"response": {"content": "...", "tool_calls": [{"id": ..., "name": ..., "arguments": {...}}]}}`. `tool_calls` is a key INSIDE the `response` dict, NOT at top level.
   - **MockProvider is stateless** (`mock.py:complete` returns the SAME canned response on EVERY call): if the agent emits a `send_to_platform_channel` tool_call, dispatches the tool, appends the tool_result, and loops back to the LLM, the LLM will return the SAME tool_call again — infinite loop until `max_iterations`. The agent's default `max_iterations=20` means 20 emissions, not 1.

   Two ways to work around the MockProvider statelessness:

   - **(A) Use a stateful in-test provider** mirroring the `_BlockingProvider`-style scripted-response pattern. Define an in-test subclass of `LLMProvider` that returns a tool_call response on the first call and a plain-text response on the second call (or pops from a pre-scripted list). This is the cleaner shape — it matches how legs in F3 handled multi-iteration scripted flows.
   - **(B) Set `max_iterations=2`** on the AgentConfig and tolerate the agent making the same tool_call twice. The visibility-tagging logic is correct under repetition (every successful platform-send tool_result gets `visibility=None`); the test asserts at least one such tool_result exists. Simpler but less realistic.

   **Recommended: Option (A)** — use a stateful scripted provider. The leg-4 implementer can either (i) extract a reusable `_ScriptedProvider(responses=[...])` helper at the top of the test file, or (ii) define it inline as `tool_calls=[...] if first_call else plain_text`. Either works.

   Test skeleton (the implementing agent finalizes the scripted-provider shape):

   ```python
   class _ScriptedProvider(LLMProvider):
       """Returns pre-scripted Messages in sequence; one per `complete()` call."""
       name = "scripted"

       def __init__(self, responses: list[Message]) -> None:
           super().__init__()
           self._responses = list(responses)
           self._idx = 0

       async def complete(self, messages, tools=None, temperature=0.0, max_tokens=16384):
           if self._idx >= len(self._responses):
               # Default: end the turn with a plain text response.
               return Message.assistant(content="(end)")
           response = self._responses[self._idx]
           self._idx += 1
           return response


   async def test_dispatch_inbound_tags_successful_send_tool_result_as_platform_visible(
       isolated_db,
   ) -> None:
       """When the agent calls send_to_platform_channel and the tool
       returns a success-prefixed string, the tool_result message is
       tagged visibility=None (platform-visible). The assistant message
       that REQUESTED the tool_call stays visibility=operator."""
       # Seed an agent + provider. We replace the mock-provider lookup
       # with our scripted provider via monkeypatch / factory override
       # so the agent loop drives our pre-canned sequence.
       await _seed_provider_and_agent()
       # Attach the connector account so leg-3's carve-out registers
       # send_to_platform_channel in the agent's tools.
       conn = await get_connection()
       agent_store = SQLiteAgentStore(conn)
       cfg = await agent_store.load("agent-inbound")
       cfg.connector_account_ids = ["acct-test"]
       await agent_store.save(cfg)
       await _seed_stub_account()
       register_for_test("stub", StubPlugin)
       # ... patch `the_one.agent.factory.get_provider` to return the
       #     scripted provider; or build the factory directly with the
       #     scripted LLM injected. See _BlockingProvider usage patterns
       #     in existing test_connectors_inbound.py tests for the canonical
       #     injection shape.
       # ... drive dispatch_inbound, then assert visibilities on the
       #     persisted history.
   ```

   The other four new tests follow similar patterns:
   - `test_dispatch_inbound_tags_assistant_text_as_operator` — uses MockProvider with plain-text response (single iteration; no loop concern).
   - `test_dispatch_inbound_tags_failed_send_tool_result_as_operator` — scripted provider returns the tool_call once; set `StubPlugin.send_should_raise = ConnectorConnectionError(...)`; the tool returns `[error] ConnectorConnectionError: ...` (no success prefix); tool_result gets `OPERATOR_VISIBILITY`.
   - `test_dispatch_inbound_tagging_uses_tool_result_tool_call_id_correlation` — scripted provider returns ONE assistant message with TWO tool_calls: one to `send_to_platform_channel`, one to a fake-prefix in-test tool. Register the in-test tool by extending the factory's `tool_providers` list with a custom `ToolProvider` returning the fake-prefix tool. Asserts: tool_call_id correlation is what governs the visibility carve-out, NOT the prefix alone.
   - `test_dispatch_inbound_continue_tool_call_is_operator_visible` — scripted provider returns an assistant message with `tool_calls=[ToolCall(id="x", name="continue", arguments={})]`. Verify at `agent/core.py:_handle_continue` (or equivalent — the F4 author reads the actual implementation) that this generates a tool_result message. Assert that message gets `OPERATOR_VISIBILITY`.

   The remaining four new tests follow similar shapes; the implementing agent finalizes:
   - `test_dispatch_inbound_tags_assistant_text_as_operator` — simpler (plain-text response, no tool call). Agent has empty `connector_account_ids` (no carve-out; the platform-send tool is not registered) OR `connector_account_ids=["acct-test"]` either way works for testing the operator-tagging branch — assistant text without tool call always gets `OPERATOR_VISIBILITY`.
   - `test_dispatch_inbound_tags_failed_send_tool_result_as_operator` — set `StubPlugin.send_should_raise = ConnectorConnectionError(...)`; the tool returns `[error] ...`; tool_result doesn't have the success prefix; gets `OPERATOR_VISIBILITY`.
   - `test_dispatch_inbound_tagging_uses_tool_result_tool_call_id_correlation` — agent makes two tool_calls in one message: one to platform-send (success), one to a different tool (where the in-test tool returns a string starting with `[platform-send-ok]` to verify the prefix-alone-isn't-sufficient guard). Requires registering an in-test "fake-prefix" tool with the agent — may need a custom tool provider or extending the factory's `tool_providers` list.
   - `test_dispatch_inbound_continue_tool_call_is_operator_visible` — agent returns an assistant message with the virtual `continue` tool_call. The agent core synthesizes a tool_result for `continue`. Verify that this gets `OPERATOR_VISIBILITY` (since `continue` is not `send_to_platform_channel`).

8. **Run targeted then full tests**:
   - `docker exec the-one pytest tests/test_connectors_inbound.py -v -x --timeout 30` — verify all visibility tests pass.
   - `docker exec the-one pytest tests/test_db_repositories.py tests/test_db_models.py tests/test_connectors_session.py -v -x --timeout 30` — verify no regression from the `now_iso` promotion.
   - `docker exec the-one pytest -x --timeout 30` — full suite green.
   - `docker exec the-one ruff check the_one tests` — clean.

9. **Update flight log** with a "Leg Progress: dispatcher-visibility-tagging-and-now-iso-promotion" entry. Capture: files modified, test count delta from leg-3 baseline (1929), any deviations, any anomalies.

10. **Flip leg status to `landed`**. Do NOT commit.

## Edge Cases

- **`pre_step_len` snapshot timing**: captured BEFORE `agent.step` async-iter loop. The agent's `step()` appends `Message.user(envelope.text)` at L138 (`agent/core.py`) INSIDE the loop. So `agent.messages[pre_step_len:]` includes the user message + every assistant/tool message produced by the turn. The USER skip rule correctly excludes the inbound message from re-tagging.

- **`agent.step` raises mid-stream**: the existing `try/finally` at `_inbound.py:194-223` resets the ContextVar in `finally`. F4's tagging block is INSIDE the `try`, so if `step()` raises mid-stream, the tagging block does NOT execute and the partial in-memory `agent.messages` is NOT persisted (`encode_messages` is also inside `try`). Leg 4 preserves this behavior — no new error handling needed; tagging-on-success only.

- **Multiple tool_calls in one assistant message**: the lookup dict `tool_call_names` captures every `(tc.id → tc.name)` mapping from new assistant messages. Each tool_result resolves correctly.

- **Tool_result with `tool_call_id` NOT in the `tool_call_names` dict**: `tool_call_names.get(...)` returns `None`; the predicate fails; the tool_result gets `OPERATOR_VISIBILITY`. Safe fallback.

- **`m.tool_result is None` on a `Role.TOOL` message**: shouldn't happen (tool_result construction at `Message.tool` always sets it), but defensive — predicate fails, gets `OPERATOR_VISIBILITY`.

- **Agent's `continue` virtual tool_call**: the agent core synthesizes the continue's tool_result internally. The tool_call has `name="continue"` (verified at `agent/core.py:CONTINUE_SCHEMA` — name is `"continue"`). The predicate `tool_call_names.get(...) == "send_to_platform_channel"` returns False (it's `"continue"`); the tool_result gets `OPERATOR_VISIBILITY`. Test 5 pins this.

- **Adversarial `content` starting with `[platform-send-ok]` on a non-platform-send tool result**: the 3-element predicate (role + name match + prefix) REQUIRES all three. A non-platform-send tool returning the prefix gets `OPERATOR_VISIBILITY` because the name check fails. Test 4 pins this.

- **Empty `agent.messages[pre_step_len:]` slice** (e.g. agent.step is a no-op): `new_msgs` is empty; both for-loops do nothing; encode proceeds with the pre-existing history unchanged. Safe.

- **`now_iso` import in `connectors/_session.py` introduces a circular import?**: `the_one/db/models.py` doesn't import from `connectors/`. Top-level import is safe. Verified.

- **`Role.USER` skip vs. operator-typed messages in connector-attached sessions** (F5 territory): F5 will route operator-typed messages through the dispatcher with `visibility="operator"` set EXPLICITLY at the entry point. The dispatcher's post-step pass only runs on the NEW messages produced by `agent.step`. If F5 sets the operator message's visibility BEFORE calling `dispatch_inbound`, the user-message at `pre_step_len` already has the right visibility AND the skip rule preserves it. F4 leg 4 does not need to know about this — F5 owns the operator-input path.

- **Test fixtures relying on `_seed_provider_and_agent` not setting `connector_account_ids`**: existing F3 tests (other than the visibility tests) work fine because the AgentConfig default is `[]`. The new visibility tests that need `connector_account_ids=["acct-test"]` must explicitly mutate the AgentConfig OR extend `_seed_provider_and_agent` to accept the field. Either approach works.

- **`OPERATOR_VISIBILITY` import path**: the constant is exported from `the_one.connectors` (`__init__.py`). Tests import via `from the_one.connectors import OPERATOR_VISIBILITY` — same shape as F3 L6's existing tests.

## Files Affected

- `the_one/db/models.py` — rename `_now_iso → now_iso` + 13 internal callers
- `the_one/db/repositories.py` — delete shadow def; update 6 call sites; remove unused datetime import; add `now_iso` to db.models import block
- `the_one/connectors/_session.py` — delete `_utc_now_iso` + NOTE block; import `now_iso`; rename local variable at L183 to `current_iso`; rewrite stale comments at L145, L172
- `the_one/connectors/_inbound.py` — delete `_utc_now_iso`; remove unused datetime import (if applicable); import `now_iso`, `OPERATOR_VISIBILITY`, `PLATFORM_SEND_OK_PREFIX`; update call site at L171; insert visibility-tagging block before encode_messages
- `tests/test_connectors_inbound.py` — invert existing test L681-702; 5 new tests; add `OPERATOR_VISIBILITY` import
- `missions/10-bi-directional-comms-connectors/flights/04-platform-send-tool-and-outbound/flight-log.md` — append leg-progress entry
- `missions/10-bi-directional-comms-connectors/flights/04-platform-send-tool-and-outbound/legs/04-dispatcher-visibility-tagging-and-now-iso-promotion.md` — flip status to `landed`

---

## Post-Completion Checklist

**Per agentic-workflow batched-review model: do NOT commit; defer to flight-end.**

- [ ] All acceptance criteria verified
- [ ] Full test suite passes (`docker exec the-one pytest -x --timeout 30`)
- [ ] Lint clean (`docker exec the-one ruff check the_one tests`)
- [ ] Update `flight-log.md` with a "Leg Progress: dispatcher-visibility-tagging-and-now-iso-promotion" entry
- [ ] Set this leg's `**Status**` to `landed`
- [ ] Signal `[HANDOFF:review-needed]` — do NOT commit

---

## Citation Audit

All 24 code-location citations verified against current code at leg design time:

| Citation | Status | Evidence |
|---|---|---|
| `the_one/db/models.py:13-14 — "def _now_iso..."` | OK | Verified at L13-14 |
| `the_one/db/models.py:29-30, 70-71, 83, 94-95, 138-139, 205-206, 230-231 (Field default_factory refs)` | OK | Verified via grep — 13 occurrences |
| `the_one/db/repositories.py:6 — "from datetime import datetime, timezone"` | OK | Verified at L6; sole consumer is shadow `_now_iso` |
| `the_one/db/repositories.py:13-21 (db.models import block)` | OK | Verified earlier |
| `the_one/db/repositories.py:25-26 — "def _now_iso..."` | OK | Verified — shadow def at L25-26 |
| `the_one/db/repositories.py:100, 179, 248, 389, 539, 633 (6 call sites)` | OK | Verified via grep |
| `the_one/connectors/_session.py:37-41 (NOTE block before _utc_now_iso)` | OK | Verified at L37-41 — explains rationale |
| `the_one/connectors/_session.py:42-43 — "def _utc_now_iso..."` | OK | Verified at L42-43 |
| `the_one/connectors/_session.py:145 (docstring reference to _utc_now_iso)` | OK | Verified — appears in docstring at "last_inbound_at = _utc_now_iso()" |
| `the_one/connectors/_session.py:172 (comment reference to _utc_now_iso)` | OK | Verified — "Normalise to UTC for the comparison — `_utc_now_iso` writes" |
| `the_one/connectors/_session.py:183 — "now_iso = _utc_now_iso()"` | OK | Verified — local variable assignment |
| `the_one/connectors/_session.py:189, 190, 197 (3 dependent callers)` | OK | Verified — `created_at=now_iso`, `updated_at=now_iso`, `last_inbound_at=now_iso` |
| `the_one/connectors/_inbound.py:31 — "from datetime import datetime, timezone"` | OK | Verified at L31 |
| `the_one/connectors/_inbound.py:54-55 — "def _utc_now_iso..."` | OK | Verified at L54-55 |
| `the_one/connectors/_inbound.py:171 — "await chat_repo.update_last_inbound(session_row.id, _utc_now_iso())"` | OK | Verified earlier |
| `the_one/connectors/_inbound.py:194-223 (try/finally for ContextVar)` | OK | Verified earlier |
| `the_one/connectors/_inbound.py:202-203 — "async for _ in agent.step(envelope.text): pass"` | OK | Verified earlier |
| `the_one/connectors/_inbound.py:212 — "encoded = encode_messages(agent.messages)"` | OK | Verified earlier |
| `the_one/connectors/__init__.py:51 — "OPERATOR_VISIBILITY = \"operator\""` | OK | Verified earlier |
| `the_one/connectors/__init__.py:PLATFORM_SEND_OK_PREFIX` | OK | Leg 1 just landed it |
| `the_one/llm/base.py:27-32 (ToolResult dataclass with tool_call_id)` | OK | Verified at L27-32; `tool_call_id: str` at L29 |
| `the_one/llm/base.py:42-90 (Message dataclass + classmethods)` | OK | Verified at L42-90 |
| `tests/test_connectors_inbound.py:659-678 (test_dispatch_inbound_persists_inbound_with_visibility_none)` | OK | Verified at L659-678 — assertion `user_msgs[0].visibility is None` at L678 |
| `tests/test_connectors_inbound.py:681-702 (test_dispatch_inbound_persists_agent_reply_with_visibility_none)` | OK | Verified at L681-702; docstring at L684-686 deliberately foreshadows F4 |
