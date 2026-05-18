# Leg: extract-visibility-tagger-shared-helper

**Status**: completed
**Flight**: [Chat UI — Unified History, Visibility Distinction, Operator Console](../flight.md)

## Objective

Extract the F4-leg-4 post-step visibility-tagging walk — currently
inline in `the_one/connectors/_inbound.dispatch_inbound` at lines
204-229 — into a free function `tag_post_step_visibility(messages,
pre_step_len)`. The dispatcher becomes a single call site. Leg 4's
WS-storage-edge shim will call the same helper. No behavior change at
this leg — pure refactor.

## Context

- **Flight slot**: F5 L3 — the prep leg for leg 4's WS-shim. The
  tagging rules are identical for inbound (dispatcher) and operator-
  typed (WS) paths: the only difference is the entry-point USER
  message's default visibility, which the caller sets at construction
  time before invoking `agent.step`. Both paths share the post-step
  walk.
- **Flight design decision — "Storage-edge shim for operator-visibility
  tagging — factor the post-step walk into a shared helper"** (flight.md
  L64-68): the shared helper signature is
  `tag_post_step_visibility(messages: list[Message], pre_step_len: int) -> None`,
  mutates in place; entry-point USER message tagging happens at the
  caller before `agent.step`.
- **Flight In-Flight § Leg 3** (flight.md L141-146): defines the
  helper signature, notes that the original `operator_default: bool`
  parameter is misleading and was REVISED OUT — both paths use the
  same post-step logic. Reads: "no operator_default kwarg; both paths
  use the same post-step logic."
- **Mission constraint**: agent loop is not modified by this flight.
  Verified — `agent/core.py` is untouched here; this leg only moves
  code within `the_one/connectors/`.
- **F5 L2 closure**: the shared session-lock + subscribers registry
  has landed at `the_one/sessions/`. Leg 3 doesn't interact with it
  directly — the visibility helper is presentation metadata, not
  session-state coordination — but the registry's existence means
  leg 4's WS-shim can confidently call this helper from inside the
  shared lock.
- **No schema change.** Helper is pure-function over an existing
  in-memory list. The `Message.visibility` field already exists on
  the dataclass (F3 L2); the codec already persists it (F3 L2-L3);
  the dispatcher already sets it (F4 L4). Leg 3 just moves the SET
  site.
- **F4 dispatcher post-step pass** is the only current consumer of
  the rules being extracted. After leg 3 the dispatcher's tagging
  loop is replaced by a one-line `tag_post_step_visibility(...)`
  call.

## Inputs

- `the_one/connectors/_inbound.py:204-229` — the inline tagging walk
  to extract. The rules block:
  - `pre_step_len` is captured at line 192 (BEFORE the `agent.step`
    loop) — already a local variable, no refactor needed.
  - Lines 212-217: first pass — build `tool_call_names: dict[str, str]`
    by walking new messages and recording `tool_call.id → tool_call.name`
    for every `ASSISTANT` message's `tool_calls`.
  - Lines 218-230: second pass — for each non-USER new message,
    compute `is_successful_platform_send` (TOOL role + tool_result is
    not None + parent tool_call's name == `"send_to_platform_channel"`
    + content starts with `PLATFORM_SEND_OK_PREFIX`); set
    `msg.visibility = None if is_successful_platform_send else OPERATOR_VISIBILITY`.
- `the_one/connectors/__init__.py:52,62` — `OPERATOR_VISIBILITY` and
  `PLATFORM_SEND_OK_PREFIX` module-level constants. The helper will
  import these from `the_one.connectors` (or rely on package-internal
  visibility via `the_one.connectors.OPERATOR_VISIBILITY` if hosted
  inside the package).
- `the_one/llm/base.py:48-90` — `Message` dataclass with `role`,
  `content`, `tool_calls`, `tool_result`, `visibility` fields;
  `Role.USER`, `Role.ASSISTANT`, `Role.TOOL` enum members.
- `tests/test_connectors_inbound.py:568-700+` — the F4 L4 dispatcher
  tagging tests. The "ground truth" assertions for tagging behavior.
  After the refactor, these MUST continue to pass byte-identically
  (no behavior change).
- `tests/test_connectors_e2e_session.py:127,145,159` — e2e
  visibility-tagging assertions in connector-session tests. Same
  regression-net requirement.
- The hard-coded literal `"send_to_platform_channel"` at
  `the_one/connectors/_inbound.py:224` — this is the platform-send
  tool's NAME (registered as a built-in tool per F4 L1-2). The leg
  PRESERVES this string literal in the extracted helper; promoting it
  to a constant is OUT OF SCOPE (would touch leg 4 of F4's territory).

## Outputs

- New module `the_one/connectors/visibility.py` exporting one
  function: `tag_post_step_visibility(messages, pre_step_len)`.
  No leading underscore on the module name: leg 4 imports it from
  `the_one/interfaces/web/app.py` (a different package), so a
  leading-underscore name would violate Python's package-internal
  convention. The consumer surface is intentionally narrow (the
  dispatcher today; leg-4's WS shim soon) but cross-package, so the
  public-module naming is correct.
- `the_one/connectors/_inbound.py` — `dispatch_inbound` replaces the
  inline tagging walk with a single call
  `tag_post_step_visibility(agent.messages, pre_step_len)`. Verified
  line ranges at design time (re-verify at impl start, since legs 1+2
  may have shifted offsets):
  - Lines 195-202: high-level "enforcement-by-construction stance"
    paragraph — KEEP as 2-line condensed comment in the dispatcher.
  - Lines 203-211: rules-enumeration comment block — MOVES verbatim
    into the helper's module docstring.
  - Lines 212-230: the two-pass loops — DELETE entirely, replaced by
    the single helper call.
- New test file `tests/test_connectors_visibility_helper.py` — unit
  tests for the helper in isolation. Faster than driving the full
  dispatcher; covers the rules at a single seam:
  - `test_user_messages_keep_defaultvisibility` — USER messages at or
    after `pre_step_len` are not touched by the walk. (Asserts neither
    None nor OPERATOR_VISIBILITY is forced — the helper SKIPS USERs.)
  - `test_assistant_text_gets_operatorvisibility` — assistant message
    with text-only (no tool_calls) → OPERATOR_VISIBILITY.
  - `test_assistant_with_tool_calls_gets_operatorvisibility` —
    assistant message that issued tool_calls → OPERATOR_VISIBILITY
    (intermediate tool-call messages stay operator-only).
  - `test_tool_result_of_non_platform_send_gets_operatorvisibility`
    — TOOL message whose parent tool_call is NOT
    `send_to_platform_channel` → OPERATOR_VISIBILITY.
  - `test_tool_result_of_platform_send_with_success_prefix_gets_none`
    — TOOL message whose parent tool_call IS `send_to_platform_channel`
    AND content starts with `PLATFORM_SEND_OK_PREFIX` → None (peer-
    visible).
  - `test_tool_result_of_platform_send_without_success_prefix_gets_operator`
    — TOOL message whose parent tool_call IS `send_to_platform_channel`
    but content does NOT start with the success prefix (error case)
    → OPERATOR_VISIBILITY (a failed platform-send doesn't leak to
    peers because it didn't reach them).
  - `test_helper_mutates_in_place` — assert that the function returns
    None and that the caller's `messages` list is the same object
    with mutated `visibility` attributes.
  - `test_messages_before_pre_step_len_are_untouched` — messages at
    indices `< pre_step_len` (i.e. the pre-existing history) MUST NOT
    have their visibility modified.
- The dispatcher's existing tests (`tests/test_connectors_inbound.py`
  and `tests/test_connectors_e2e_session.py`) continue to pass
  byte-identically.

## Acceptance Criteria

- [ ] `the_one/connectors/visibility.py` exists with a single
      module-private exported function:
      `tag_post_step_visibility(messages: list[Message], pre_step_len: int) -> None`.
      Signature matches the flight design decision exactly. Docstring
      enumerates the four tagging rules (USER skip, successful
      platform-send → None, everything else → OPERATOR_VISIBILITY,
      pre-step messages untouched) with the same fidelity as the
      current inline comment block at `_inbound.py:196-211`.
- [ ] `the_one/connectors/_inbound.py` no longer contains the inline
      tagging walk. The dispatcher's `try` block (lines ~194-260)
      makes a single call `tag_post_step_visibility(agent.messages, pre_step_len)`
      after the `agent.step` async-iter loop completes, before
      persisting. A brief comment (2-3 lines) explains what the
      helper does and points readers at `visibility.py` for the
      rule details.
- [ ] `tests/test_connectors_visibility_helper.py` exists with the
      eight test cases enumerated under Outputs.
- [ ] `tests/test_connectors_inbound.py` and
      `tests/test_connectors_e2e_session.py` pass byte-identically —
      no test rewrites, no new assertions removed. The visibility-
      tagging coverage section at `tests/test_connectors_inbound.py:622-700+`
      is the regression net.
- [ ] `make test-unit` clean. F5 L2 baseline was 1960 passed;
      expected ~+8 from this leg's new helper-tests. Confirm the
      delta is the new tests, not unrelated breakage.
- [ ] `make lint` clean.
- [ ] No new imports of `visibility` from outside
      `the_one/connectors/`. Verified by a one-liner grep at leg end.
- [ ] The agent loop in `the_one/agent/core.py` is untouched.

## Verification Steps

- **Focused helper test**:
  `docker exec the-one pytest tests/test_connectors_visibility_helper.py -x --timeout 30 -v`
  — new test file passes.
- **Dispatcher regression net**:
  `docker exec the-one pytest tests/test_connectors_inbound.py -x --timeout 30 -v`
  — all dispatcher tests including the F4 L4 tagging coverage at
  line 622+ pass byte-identically.
- **e2e session regression**:
  `docker exec the-one pytest tests/test_connectors_e2e_session.py -x --timeout 60 -v`
  — visibility-tagging assertions in e2e tests pass.
- **F4 platform-send e2e**:
  `docker exec the-one pytest tests/test_connectors_e2e_platform_send.py -x --timeout 60 -v`
  — F4 e2e tests (which exercise the dispatcher's tagging) pass.
- **Full suite**: `make test-unit` clean.
- **Lint**: `make lint` clean.
- **Import-scope grep**:
  `grep -rn "from the_one.connectors.visibility\|from the_one.connectors import.*tag_post_step_visibility" the_one/ tests/`
  — returns at most TWO matches at leg-3 completion:
  (1) `the_one/connectors/_inbound.py` (the dispatcher consumer),
  (2) `tests/test_connectors_visibility_helper.py` (the focused test).
  Leg 4 will add a third match (`interfaces/web/app.py`); no other
  consumer at leg-3 end.

## Implementation Guidance

The refactor is small. Recommended order:

1. **Create `the_one/connectors/visibility.py`** with the extracted
   function. Copy the rules block verbatim from `_inbound.py:204-229`,
   wrap in a function:

   ```python
   """Post-step visibility tagging for connector-attached sessions.

   M10 F05 L03: factored out of ``the_one.connectors._inbound.dispatch_inbound``
   so the F5 L4 WS-storage-edge shim can apply the SAME rules when an
   operator types into a connector-attached session from the Chat UI.
   The rules are identical for both call sites — the only difference
   is the entry-point USER message's default visibility, which the
   caller sets at construction time BEFORE invoking ``agent.step``.

   Tagging rules (preserved verbatim from F4 L4):
   - ``Role.USER`` messages at or after ``pre_step_len`` are SKIPPED.
     The peer-inbound dispatcher constructs USER with ``visibility=None``
     (peer-visible); the operator-input WS shim constructs USER with
     ``visibility=OPERATOR_VISIBILITY``. Either way, the post-step
     pass doesn't touch the USER message — its visibility is the
     caller's contract.
   - ``Role.TOOL`` whose parent ``tool_call.name == "send_to_platform_channel"``
     AND content starts with ``PLATFORM_SEND_OK_PREFIX`` → ``visibility=None``
     (peer-visible — the platform-send tool already pushed the content
     to peers).
   - Everything else → ``OPERATOR_VISIBILITY`` (assistant text +
     intermediate tool calls/results stay operator-only).
   - Messages at indices ``< pre_step_len`` (the pre-existing history)
     are NEVER touched.

   The hard-coded ``"send_to_platform_channel"`` literal matches the
   built-in tool's registered name (F4 L1-2). Promoting to a constant
   is deferred — out of scope for this refactor leg.
   """
   from __future__ import annotations

   from the_one.connectors import OPERATOR_VISIBILITY, PLATFORM_SEND_OK_PREFIX
   from the_one.llm.base import Message, Role


   def tag_post_step_visibility(
       messages: list[Message],
       pre_step_len: int,
   ) -> None:
       """Apply post-step visibility rules to messages appended by ``agent.step``.

       Mutates ``messages`` in place. Returns None. Caller is
       responsible for tagging the entry-point USER message at
       construction time (BEFORE ``agent.step``); this helper does
       not touch it.

       ``pre_step_len`` is the length of ``messages`` BEFORE the
       ``agent.step`` call. The helper iterates ``messages[pre_step_len:]``
       and applies the rules in the module docstring.
       """
       new_msgs = messages[pre_step_len:]
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
           msg.visibility = (
               None if is_successful_platform_send else OPERATOR_VISIBILITY
           )
   ```

   Run `make lint`; green. No tests yet; full-suite still passes
   because nothing imports this helper yet.

2. **Wire the dispatcher to the helper** (`the_one/connectors/_inbound.py`):
   - Add `from the_one.connectors.visibility import tag_post_step_visibility`
     to the imports.
   - **Delete lines 203-230** (the "Rules:" comment block AND both
     pass loops). Re-verify the exact range at impl start with
     `grep -n "Rules:\|tool_call_names\|is_successful_platform_send" the_one/connectors/_inbound.py`
     — F5 L1/L2 don't touch this file, but a defensive re-check is
     cheap.
   - Replace the deletion with this two-line pointer:
     ```python
     # F5 L3: visibility-tagging rules live in ``connectors.visibility``.
     tag_post_step_visibility(agent.messages, pre_step_len)
     ```
   - **Preserve lines 195-202** (the high-level "enforcement-by-
     construction stance" comment). That context — "the dispatcher
     fires only for connector-attached inbound; visibility is
     presentation metadata, not a security gate" — explains WHY
     tagging happens at this seam, which the helper docstring
     doesn't repeat.
   - **Remove the now-unused imports**: after the deletion, both
     `OPERATOR_VISIBILITY` and `PLATFORM_SEND_OK_PREFIX` are
     guaranteed to be unused in `_inbound.py` (the only references
     were the deleted loop). The import line at `_inbound.py:31`
     reads `from the_one.connectors import OPERATOR_VISIBILITY,
     PLATFORM_SEND_OK_PREFIX, registry` — trim it to `from
     the_one.connectors import registry`. `make lint` will catch
     the unused symbols anyway, but doing it deliberately keeps the
     diff clean.
   - Run `pytest tests/test_connectors_inbound.py tests/test_connectors_e2e_session.py
     tests/test_connectors_e2e_platform_send.py -x --timeout 60 -v`;
     all green (the helper produces byte-identical results).

3. **Add `tests/test_connectors_visibility_helper.py`**:
   - Import: `from the_one.connectors.visibility import tag_post_step_visibility`.
   - Import: `from the_one.connectors import OPERATOR_VISIBILITY, PLATFORM_SEND_OK_PREFIX`.
   - Import: `from the_one.llm.base import Message, Role, ToolCall, ToolResult`.
   - Build small synthetic message lists for each test case. The shape
     of `Message`, `ToolCall`, and `ToolResult` is in `the_one/llm/base.py`
     — read that file at implementation start for the exact
     constructors.
   - Each test follows the pattern:
     1. Build a `messages: list[Message]` with a known shape.
     2. Capture `pre_step_len = X` (often 0 or 1 — the simplest case
        is "all the messages are post-step").
     3. Call `tag_post_step_visibility(messages, pre_step_len)`.
     4. Assert `messages[i].visibility` for the relevant indices.
   - For `test_messages_before_pre_step_len_are_untouched`: seed the
     pre-step messages with a deliberate marker visibility (e.g.
     `"sentinel"`), confirm it's untouched after the call.
   - For `test_helper_mutates_in_place`: capture `id(messages)` and
     `messages[…].visibility` before; assert ID-equality and
     attribute mutation.
   - Run `pytest tests/test_connectors_visibility_helper.py -x --timeout 30 -v`;
     green.

4. **Full suite + lint**:
   - `make test-unit` clean.
   - `make lint` clean.
   - Import-scope grep verifies only two consumers of `visibility`
     at this leg's end.

5. **Update flight log** with leg 3's outcomes — files touched, test
   count, refactor framing ("no behavior change; rules block moved to
   helper").

## Edge Cases

- **`pre_step_len == len(messages)`** — no new messages; `new_msgs` is
  empty; both passes iterate nothing; no visibility mutation. The
  helper returns cleanly. Test it: build a list, call with
  `pre_step_len = len(messages)`, assert no exception and no
  mutation.

- **`pre_step_len > len(messages)`** — degenerate input; Python's slice
  semantics make `messages[pre_step_len:]` an empty list. Same as
  above. No defensive bounds check needed; the helper trusts its
  caller.

- **`pre_step_len < 0`** — degenerate input; the slice would walk
  some prefix of the list. The helper is a private utility; callers
  always pass `len(messages_before_step)`. Trust the runtime.

- **`tool_call.id` collisions across two ASSISTANT messages in one
  turn** — the `tool_call_names` dict overwrites; the last ASSISTANT's
  tool_calls win. In practice tool_call ids are unique per turn (LLM
  provider contract); the F4 L4 inline code has the same behavior and
  the regression net pins it. Acceptable.

- **TOOL message whose parent `tool_call.id` is NOT in
  `tool_call_names`** — `tool_call_names.get(...)` returns None;
  `is_successful_platform_send` is False; the message gets
  OPERATOR_VISIBILITY. This matches the current F4 L4 behavior
  byte-identically.

- **ASSISTANT message with no `tool_calls`** — the inner for-loop
  iterates an empty list; nothing is added to `tool_call_names`. The
  message itself gets OPERATOR_VISIBILITY in the second pass
  (assistant text path). Correct.

- **Message with `visibility` ALREADY set to something** — the helper
  overwrites unconditionally (`msg.visibility = ...`). This matches
  current F4 L4 behavior. The caller (dispatcher + leg-4 shim)
  intentionally lets the post-step pass be the source of truth for
  non-USER post-step messages.

- **Mixed-role TOOL message ordering across multiple ASSISTANT
  parents** — the two-pass structure (first build `tool_call_names`,
  THEN tag) means order independence. Tested implicitly by the
  existing dispatcher tests; explicitly by a new test if cheap to
  add.

## Files Affected

- `the_one/connectors/visibility.py` (new) — the helper.
- `the_one/connectors/_inbound.py` — `dispatch_inbound` is shortened
  by ~25 lines; one new import; one new call site.
- `tests/test_connectors_visibility_helper.py` (new) — 8 unit tests.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing (`make test-unit`, `make lint` clean)
- [ ] Import-scope grep confirms two consumers max at leg-3 end
- [ ] Update flight-log.md with Leg 3 progress entry
- [ ] Set this leg's status to `completed` (in this file's header)
- [ ] Check off this leg in flight.md
- [ ] Per the agentic-workflow protocol: do NOT commit until end-of-flight
      review.

## Citation Audit

9 citations verified against current code at leg design time:

- `the_one/connectors/_inbound.py:204-229` — inline tagging walk
  (verified at lines 204-230 in current code).
- `the_one/connectors/_inbound.py:192` — `pre_step_len` snapshot
  (verified).
- `the_one/connectors/__init__.py:52` — `OPERATOR_VISIBILITY = "operator"`
  (verified).
- `the_one/connectors/__init__.py:62` — `PLATFORM_SEND_OK_PREFIX =
  "[platform-send-ok]"` (verified).
- `the_one/llm/base.py:48-56` — `Message.visibility` field declaration
  (verified).
- `tests/test_connectors_inbound.py:568` — `test_dispatch_inbound_persists_inbound_withvisibility_none`
  (verified — F4 L4 ground-truth test for USER-skip behavior).
- `tests/test_connectors_inbound.py:594` —
  `test_dispatch_inbound_persists_agent_reply_withvisibility_operator`
  (verified — F4 L4 ground-truth test for assistant-tagging).
- `tests/test_connectors_inbound.py:622` — F4 L4 visibility-tagging
  coverage section header (verified).
- `tests/test_connectors_e2e_session.py:127,145,159` — e2e visibility
  assertions (verified).
