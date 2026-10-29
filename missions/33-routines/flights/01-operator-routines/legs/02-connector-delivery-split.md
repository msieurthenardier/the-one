# Leg: connector-delivery-split

**Status**: completed
**Flight**: [Operator Routines, End to End](../flight.md)

## Objective

Make connector delivery and the channel's agent-authorization rule reachable
without an inbound envelope. This leg extracts `deliver_final_reply` (which
returns a result), `send_step_limit_line` (which takes a target) and
`authorized_agent_for` from the inbound pipeline and the send tool. Today's
behaviour is unchanged: every existing inbound and send-tool test passes
unedited.

## Context

- Flight DD6, "Delivery extraction (its own leg)", and DD8, "The DM
  approximation".
- This is the mission's pre-declared split point. **Divert criterion:** if any
  existing test in `tests/test_connectors_inbound.py`,
  `tests/test_inbound_session_updated.py` or
  `tests/test_connector_send_tool.py` must be edited to pass, stop and report
  `[BLOCKED:delivery-split-not-contained]`. The flight then re-plans the
  connector half as its own flight.
- Leg 3 (`routine-run-path`) is the consumer. It calls `deliver_final_reply`
  with `keying_to_target(row)`, `send_step_limit_line` with the same target,
  and `authorized_agent_for` in its pre-check.
- Independent of leg 1. Batch A runs legs 1 to 4 in order, with no commit
  between them.

## Inputs

- `the_one/connectors/inbound.py`:
  - `_auto_deliver_reply(messages, pre_step_len, envelope, connector_id, manager) -> None`:
    a skip rule after a successful `send_to_platform_channel` (content starts
    with `_PLATFORM_SEND_OK_PREFIX`); the final ASSISTANT str content;
    `manager.client_for`; `client.send`; on success it flips `visibility` to
    `None`, and it never raises;
  - `_reply_target(envelope, connector_id)`;
  - `_send_step_limit_line(envelope, connector_id, manager)`.
- `the_one/tools/connector_send.py` `SendToPlatformChannelTool.execute`.
  - **Channel target:** the authorized agent is
    `channel_map.get(channel_id) or default_agent`.
  - **Peer target:** it is `default_agent`, after the allowlist check.
- `the_one/connectors/base.py` `keying_to_target(session)`. It returns a
  `ChannelTarget` whenever `channel_id is not None`, which includes `""`.
- The existing tests. Inbound covers delivery
  (`test_auto_reply_delivers_plain_text_channel_target_with_thread_id`,
  `…_dm_peer_target`, `…_no_live_client_…`, `…_connector_client_error_…`,
  `test_round_trip_cross_channel_tool_send_suppresses_auto_reply`) and the
  step-limit line (`test_step_limit_line_*`). The send-tool tests cover the
  authorization matrix (`test_mapped_channel_*`, `test_dm_*`,
  `test_dangling_default_agent_*`).

## Outputs

- `the_one/connectors/delivery.py` (new) holds the envelope-free delivery
  primitives.
  - **`DeliveryResult`.** A frozen dataclass with `status: Literal["delivered",
    "already_sent", "no_text", "no_client", "send_failed"]` and
    `error: str | None`.
  - **`deliver_final_reply(messages, pre_step_len, target, connector_id, manager) -> DeliveryResult`.**
    Today's `_auto_deliver_reply` body, with `target` passed in.
    - It never raises.
    - `send_failed` carries a one-line `error`:
      `f"{type(exc).__name__}: {exc}"`, truncated to 200 characters.
    - It logs exactly what it logs today.
  - **`send_step_limit_line(target, connector_id, manager) -> None`.** Today's
    `_send_step_limit_line` body, with `target` passed in. It never raises.
  - **`authorized_agent_for(connector, *, channel_id: str | None) -> str | None`.**
    With `channel_id` not `None`, it returns
    `channel_map.get(channel_id) or default_agent`; with `None`, it returns
    `default_agent`.
- `inbound.py`:
  - `_auto_deliver_reply` keeps its signature and return type (`None`), and
    becomes a thin wrapper: `await deliver_final_reply(messages, pre_step_len,
    _reply_target(envelope, connector_id), connector_id, manager)`, with the
    result discarded.
  - `_send_step_limit_line` keeps its signature and delegates to
    `send_step_limit_line`.
- `connector_send.py`: `execute` computes `authorized_agent` through
  `authorized_agent_for(connector, channel_id=channel_id)` for a channel
  target, and `channel_id=None` for a peer target. The allowlist check, the
  error strings and their order are unchanged.
- `tests/test_connector_delivery.py` (new) holds direct unit tests of the
  three primitives and the `keying_to_target` shapes.
- `the_one/connectors/README.md` and `the_one/agents.md` gain a short note:
  delivery primitives live in `connectors/delivery.py`, which has no envelope
  dependency.

## Acceptance Criteria

- [ ] AC1. **Characterization first.** Before any production edit, run the
      three existing test files and record their pass counts in the flight log.
      `tests/test_connector_delivery.py`'s characterization cases are written
      against the CURRENT `_auto_deliver_reply` and `_send_step_limit_line`,
      driven through them with a stub envelope, and must pass both before and
      after the extraction. They cover:
      - (a) no ASSISTANT message: nothing sent;
      - (b) a final ASSISTANT with empty or non-str content: nothing sent;
      - (c) a generic `Exception` from `send`: stays operator-only, no raise;
      - (d) the skip rule when the tool-send succeeded to a different channel;
      - (e) a failed tool-send (content not prefixed `[platform-send-ok]`):
        auto-delivery still happens.
- [ ] AC2. **Existing tests are not edited.** After the extraction, every test in
      `tests/test_connectors_inbound.py`, `tests/test_inbound_session_updated.py`
      and `tests/test_connector_send_tool.py` passes, with the same counts as
      AC1. `git diff` shows no change to those three files. If one must change,
      the leg stops with `[BLOCKED:delivery-split-not-contained]`.
- [ ] AC3. `deliver_final_reply` returns a result for every branch:
      - `already_sent` after a successful tool-send;
      - `no_text` with no or empty final text;
      - `no_client` when `client_for` is `None`;
      - `send_failed` with `error` set, for `ConnectorClientError` and for a
        generic exception;
      - `delivered`, which flips the final message's `visibility` to `None`.

      Only `delivered` mutates any message, and it never raises.
- [ ] AC4. `deliver_final_reply` sends to exactly the `target` it is given:
      - a `ChannelTarget` with a `thread_id` reaches the client unchanged;
      - a `PeerTarget` reaches it unchanged;
      - `keying_to_target` on a stored row gives the shapes DD8 records:
        - a Discord-style DM row with `channel_id="D1"` gives
          `ChannelTarget("D1")`;
        - a stub DM row with `channel_id=""` gives `ChannelTarget("")`;
        - a row with `channel_id=None` and a `peer_id` gives a `PeerTarget`;
        - a web row with no `connector_id` gives `None`.
- [ ] AC5. `authorized_agent_for` returns:
      - the mapped agent for a mapped channel;
      - `default_agent` for an unmapped channel;
      - `default_agent` for `channel_id=""`, which is the stub-DM case;
      - `default_agent` for `None`;
      - `None` when neither is configured.

      The send tool's authorization tests pass unchanged (AC2).
- [ ] AC6. `send_step_limit_line(target, …)` sends `STEP_LIMIT_LINE` to the
      given target, and logs and drops a failure or a missing client without
      raising. The existing step-limit tests pass unchanged (AC2).
- [ ] AC7. `THE_ONE_TEST_NETNS=1 make test-unit` is green with the expected skip
      count; `make lint` and `ruff format --check` are clean.

## Verification Steps

- AC1: `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_connectors_inbound.py tests/test_inbound_session_updated.py tests/test_connector_send_tool.py -x --timeout 30`
  before editing. Then write and run the characterization cases.
- AC2: the same command after the edit, plus
  `git diff --stat -- tests/test_connectors_inbound.py tests/test_inbound_session_updated.py tests/test_connector_send_tool.py`,
  which must print nothing.
- AC3-AC6: `tests/test_connector_delivery.py`.
- AC7: `THE_ONE_TEST_NETNS=1 make test-unit`, then `make lint`.

## Implementation Guidance

1. Run the three files and note the counts (AC1).
2. Write the characterization cases in `tests/test_connector_delivery.py`,
   calling `inbound._auto_deliver_reply` with a small envelope and a fake
   manager and client.
   - The fakes follow the existing pattern in `tests/test_connectors_inbound.py`
     (find its fake client and manager and reuse them, importing from that
     module or copying a minimal fake).
   - Confirm the cases pass against the current code.
3. Create `the_one/connectors/delivery.py`.
   - Move `_SEND_TO_PLATFORM_CHANNEL_TOOL_NAME` and `_PLATFORM_SEND_OK_PREFIX`
     there, or import them from where they live. `inbound.py` keeps
     re-exporting any name tests import from it (grep the tests for
     `from the_one.connectors.inbound import`).
   - Keep the log messages' wording, including the `dispatch_inbound:` prefix,
     so log-asserting tests (`caplog`) are unaffected.
4. Re-point `_auto_deliver_reply` and `_send_step_limit_line` at the
   primitives.
5. Re-point the send tool at `authorized_agent_for`.
6. Add the direct tests for AC3-AC6, and run the gate.
7. Docs: one paragraph each in `the_one/connectors/README.md` and
   `the_one/agents.md`.

## Edge Cases

- **Import cycles.** `delivery.py` must not import `inbound.py` or `app.py`.
  For `ConnectorManager`, import types under `TYPE_CHECKING`, as `inbound.py`
  does.
- **`DeliveryResult.error`** never includes the reply text. It is the
  exception type and message only.
- **The skip rule's "different channel" trade-off** (DD-10) is kept as is.
  `already_sent` does not say which channel the tool-send went to.

## Files Affected

- `the_one/connectors/delivery.py`: new.
- `the_one/connectors/inbound.py`: delegate to the primitives.
- `the_one/tools/connector_send.py`: use `authorized_agent_for`.
- `tests/test_connector_delivery.py`: new.
- `the_one/connectors/README.md`, `the_one/agents.md`: notes.

## Citation Audit

Checked at `c2366221`:
- `inbound.py:250` `_reply_target`, `:257` `_send_step_limit_line`, `:285`
  `_auto_deliver_reply` (body quoted above in Inputs).
- `connector_send.py:170-185`: the authorization branch in `execute`.
- `base.py:70` `keying_to_target`.
- The test names listed in Inputs exist (grep of `def test_`).

All verified.

---

## Post-Completion
Completion steps (status transitions, the flight-log update, checking off the
leg in the parent flight, and the commit) are Flight Control protocol, driven
by the execution workflow, and are not repeated here.
