# Leg: agent-config-and-protocol-widen

**Status**: completed
**Flight**: [Platform-Send Built-in Tool and Outbound Routing](../flight.md)

## Objective

Land the data-model + Protocol-surface scaffolding for outbound: add `AgentConfig.connector_account_ids` (F1 deferred this field to F4), widen the `ConnectorClient` Protocol with `async def send(target, content) -> SendResult`, define the `SendResult` frozen dataclass, publish the `PLATFORM_SEND_OK_PREFIX` constant from `the_one.connectors`, implement `StubClient.send` (records to the existing `StubPlugin.outbound_records` buffer), add `StubPlugin.send_should_raise` for failure injection, and update the `connectors/README.md` §3 skeleton-plugin example so future plugin authors see the full required surface.

## Context

- **Parent flight design decisions** (see `flight.md` "Design Decisions"):
  - **`ConnectorClient` Protocol widening, NOT `getattr`-sentinel optional hook.** The mission constraint "every platform message originates from an explicit tool call" makes outbound mandatory for every connector in scope. `getattr`'s optional-hook pattern (F3's `display_channel`) is for genuinely-optional hooks where a sensible default exists at the call site. Outbound has no sensible default — silent drop is leakage, raise is noise. F1's `ConnectorClient` docstring explicitly invited F4 to widen here (cf. `connectors/base.py:142-164`).
  - **`AgentConfig.connector_account_ids` mirrors `mcp_source_ids` exactly.** Plain `list[str] = Field(default_factory=list)`, mirror-positioned next to `mcp_source_ids`. No `Optional`-as-locked-down-NULL — empty list is the no-attached state. `extra="ignore"` on `AgentConfig` means pre-F4 stored agent rows deserialize cleanly (the field defaults to `[]`).
  - **`SendResult` shape**: `platform_message_id: str | None` + `details: dict[str, Any]` with `field(hash=False, compare=False)`. Mirror of `DoctorReport.details`. Future flights (F10 hardening, edit/delete correspondence) extend `details` with rate-limit headers, edit timestamps, etc.
  - **`PLATFORM_SEND_OK_PREFIX = "[platform-send-ok]"`** constant lives in `the_one/connectors/__init__.py` next to `OPERATOR_VISIBILITY`. Single source of truth — `SendToPlatformChannelTool.execute()` (leg 2) constructs the success string with the prefix; `_inbound.dispatch_inbound`'s visibility-tagger (leg 4) consumes it. Import-cycle-safe: the constant is a plain string literal, not a reference to anything in `tools/` or other downstream modules.
  - **`StubClient.send` routes through the existing `StubPlugin.record_outbound` classmethod** (`_stub.py:127-134`). `StubClient` doesn't carry a reference to its parent plugin, but classmethods are accessible on the class itself: `StubPlugin.record_outbound(target, content)` works from inside `StubClient.send`. The existing `outbound_records: list[tuple[OutboundTarget, str]]` buffer is the recording target. Architect-clarified.
  - **`SendToPlatformChannelTool.__init__` zero-arg compatibility is a LEG-2 concern**, not leg 1 — but leg 1 establishes the `SendResult` shape leg 2 returns. Leg 1 does NOT register the tool in `_TOOL_CLASSES` (leg 2 owns that).
  - **F4 codifies the `protocol-widening-for-required-capability` convention** in `agents.md` (leg 6 owns the codification — leg 1 just lands the first instance). The pattern: when a capability moves from "future" to "required by every plugin in scope," widen the `runtime_checkable` Protocol additively.

- **`runtime_checkable` Protocol widening semantic**: Python's `runtime_checkable` Protocols check method-name presence on the object at `isinstance(...)` time. Widening the Protocol with a new method MEANS that objects missing the new method will FAIL the isinstance check after widening. Architect-flagged note in the flight artifact says "isinstance over a hand-built class implementing only `is_alive` ALSO still passes (Protocol checks names; `send` being absent does NOT break the structural satisfaction at runtime)" — this claim is INCORRECT per the actual `runtime_checkable` semantic (verified at `tests/test_connectors.py:150-151` `test_plugin_missing_method_fails_check` which asserts a plugin missing `connect` fails `isinstance(..., ConnectorPlugin)`). Leg 1 MUST update the `_MinimalClient` test fixture at `tests/test_connectors.py:126-130` to add `async def send(...)` so the existing assertion `assert isinstance(_MinimalClient(), ConnectorClient)` at `tests/test_connectors.py:160` continues to pass. Leg 1 ALSO adds a new symmetric test asserting a client without `send` fails the widened isinstance check (mirror of `test_plugin_missing_method_fails_check`).

- **Other consumers of the `ConnectorClient` Protocol**:
  - `tests/test_connectors_pool.py:84 — "class _StubClient"` — has only `is_alive`. The pool tests use concrete-class `isinstance(client, _StubClient)` checks (`:169`, `:196`, `:278`), NOT Protocol-isinstance checks. The pool tests never invoke `client.send(...)`. **No change needed** in this file for the leg-1 widening.
  - `tests/test_connectors_e2e.py`, `tests/test_connectors_inbound.py`, `tests/test_connectors_session.py`, `tests/test_connectors_e2e_session.py` — verified by grep (`isinstance.*ConnectorClient` / `is_alive` / `class.*Client`): no Protocol-isinstance checks on `ConnectorClient`. No changes needed in these files.
  - `the_one/connectors/_pool.py` — production pool. Returns `ConnectorClient` via `acquire`. Doesn't call `send` directly. **No change needed.**
  - `the_one/connectors/_inbound.py` — F3 dispatcher. Calls `pool_acquire` for the touch effect; doesn't consume the returned client. **No change needed.**

- **Skeleton plugin in `connectors/README.md` §3 (L102-160) has a bug** that F4 must fix: `doctor` returns `DoctorReport(status="error", details={...})` at L139 — missing the required `message: str` field. `DoctorReport` requires `message` per `connectors/base.py:120-128`. F2 debrief recommendation #5(b) flagged this; leg 1's README scope includes the fix.

- **The README §4 "Optional hooks" section at L198-199** speculates: "Future flights (notably F4's `ConnectorClient` outbound-send extension if it lands as optional) may use the same pattern." F4 chose Protocol-widening, NOT optional-hook. Leg 6 owns the docs cleanup for §4. Leg 1 leaves §4 untouched.

- **F3 carry-forward action item: "Decide: optional-hook convention vs. Protocol-widening for ConnectorClient's outbound-send method"** — RESOLVED in F4 flight spec Design Decisions as Protocol-widening. Leg 1 is the realization of that decision.

## Inputs

State that must exist before this leg runs:

- F4 branch `flight/04-platform-send-tool-and-outbound` checked out (verified at flight-start).
- Working tree is the post-F3-debrief state (F3 `completed` per artifacts; `the_one/llm/base.py:Message.visibility`, `the_one/connectors/__init__.py:OPERATOR_VISIBILITY`, `the_one/connectors/_inbound.py:dispatch_inbound`, v16 schema all in place — F4 stacks on F3's tip per the flight log Flight Director Notes).
- `the_one/agent/config.py:76 — "mcp_source_ids: list[str] = Field(default_factory=list)"` — extant field; leg 1 adds `connector_account_ids` after it.
- `the_one/connectors/base.py:OutboundTarget` — extant frozen dataclass (lines 78-86). `SendResult` will use the same `field(hash=False, compare=False)` pattern as `DoctorReport`.
- `the_one/connectors/base.py:DoctorReport` — extant frozen dataclass (lines 111-139). `SendResult` mirrors its shape for `details`.
- `the_one/connectors/base.py:142 — "@runtime_checkable\nclass ConnectorClient(Protocol):"` — extant 1-method Protocol; leg 1 widens with `send`.
- `the_one/connectors/__init__.py:51 — "OPERATOR_VISIBILITY = \"operator\""` — extant constant; leg 1 adds `PLATFORM_SEND_OK_PREFIX` next to it. `__all__` at L53-72 lists the public surface; leg 1 extends with `SendResult` and `PLATFORM_SEND_OK_PREFIX`.
- `the_one/connectors/_stub.py:42 — "class StubClient:"` — extant 1-method client; leg 1 adds `send`.
- `the_one/connectors/_stub.py:52 — "class StubPlugin:"` — extant rich plugin with ClassVar scenario knobs; leg 1 adds `send_should_raise`.
- `the_one/connectors/_stub.py:104 — "def reset_for_test(cls) -> None:"` — extant classmethod; leg 1 extends to clear `send_should_raise`.
- `the_one/connectors/_stub.py:127 — "def record_outbound(cls, target: OutboundTarget, content: str) -> None:"` — extant classmethod; `StubClient.send` calls into it.
- `the_one/connectors/README.md` §3 skeleton (lines 102-161) — extant 4-method shape; leg 1 adds `send` method + fixes the missing `message` field on `doctor`'s error-branch `DoctorReport`.
- `tests/test_connectors.py:126 — "class _MinimalClient:"` — extant 1-method client fixture; leg 1 adds `send`.
- `tests/test_connectors.py:158 — "class TestConnectorClientProtocol:"` — extant test class; leg 1 extends with the new `client-missing-send-fails-check` test.
- `tests/test_config.py:14 — "class TestAgentConfigConstruction:"` — extant test class; leg 1 extends with `connector_account_ids` defaults + round-trip + back-compat tests.

## Outputs

State that must exist after this leg completes:

- `the_one/agent/config.py:AgentConfig` has a new field `connector_account_ids: list[str] = Field(default_factory=list)` mirror-positioned immediately after `mcp_source_ids` (likely at line 77, but the exact line number is post-edit).
- `the_one/connectors/base.py` defines a new `SendResult` frozen-slotted dataclass between `DoctorReport` (L111-139) and `ConnectorClient` (L142+):
  ```python
  @dataclass(frozen=True, slots=True)
  class SendResult:
      """Result of a successful :meth:`ConnectorClient.send` call.
      ...docstring...
      """

      platform_message_id: str | None
      """Best-effort platform-native message id for the delivered message.
      Some platforms return one (Discord); others don't (webhooks-only
      flows). ``None`` is a valid value, not an error signal.
      """

      details: dict[str, Any] = field(hash=False, compare=False)
      """Required structured detail surface mirroring :attr:`DoctorReport.details`
      — rate-limit headers, edit timestamps, attachment id arrays, etc.
      Plugins MAY pass an empty dict when there is nothing platform-specific
      to surface. Excluded from ``__hash__`` and ``__eq__`` — same rationale
      as :attr:`InboundEnvelope.raw`.
      """
  ```
- `the_one/connectors/base.py:ConnectorClient` Protocol gains an `async def send(self, target: OutboundTarget, content: str) -> SendResult` method, placed AFTER `is_alive` for readability. The Protocol's class docstring is updated to note that F4 has landed the widening (currently L153 says "Flight 4 widens this to add an outbound-send method when the platform-send tool needs it" — change to past tense and reference `send`).
- `the_one/connectors/__init__.py` exports `SendResult` (re-exported from `the_one.connectors.base`) and defines `PLATFORM_SEND_OK_PREFIX = "[platform-send-ok]"` as a module-level constant alongside `OPERATOR_VISIBILITY`. Both are added to `__all__`.
- `the_one/connectors/_stub.py:StubClient` has an `async def send(self, target: OutboundTarget, content: str) -> SendResult` method. Logic:
  1. If `StubPlugin.send_should_raise is not None`, raise it.
  2. Otherwise call `StubPlugin.record_outbound(target, content)`.
  3. Return `SendResult(platform_message_id="stub-msg-id", details={})`.
- `the_one/connectors/_stub.py:StubPlugin` has a new ClassVar `send_should_raise: ClassVar[BaseException | None] = None` documented in the scenario-knobs block (mirror the docstring shape of `connect_should_fail` at L92-94 and `doctor_should_raise` at L95-100).
- `the_one/connectors/_stub.py:StubPlugin.reset_for_test` (L104-114) is extended to set `cls.send_should_raise = None` alongside the other reset assignments.
- `the_one/connectors/README.md` §3 skeleton plugin (L102-161):
  - Splits into TWO classes: `HypotheticalPlatformPlugin` (carrying `connect`, `disconnect`, `doctor`, `normalize_session_key` — the four `ConnectorPlugin` methods) AND `HypotheticalPlatformClient` (carrying `is_alive` and the new `send` — the two `ConnectorClient` methods). `HypotheticalPlatformPlugin.connect()` returns an instance of `HypotheticalPlatformClient`. The split makes `send` land on the correct Protocol and resolves the existing skeleton's mental-model ambiguity.
  - Fixes the `doctor` error-branch `DoctorReport(status="error", details={...})` to `DoctorReport(status="failed", message=str(e), details={})` — `"error"` is NOT a valid `DoctorReport.status` literal (the type is `Literal["ok", "degraded", "failed"]` per `connectors/base.py:120`); for an unconditional `except` branch the correct sentinel is `"failed"`.
  - Updates the success-branch `DoctorReport(status="ok", details={...})` to include a non-empty `message=` string like `message=f"connected as {info['bot_user']}"` (F2 debrief recommendation #5(b)).
- `tests/test_connectors.py:_MinimalClient` (L126-130) gains an `async def send(self, target, content)` method returning a `SendResult` so the existing `test_minimal_client_satisfies_protocol` (L159-160) continues to pass after the widening.
- `tests/test_connectors.py:TestConnectorClientProtocol` (L158) gains a new test `test_client_missing_send_fails_check` mirroring `test_plugin_missing_method_fails_check` (L150-151). The new test defines an in-test class with `is_alive` only (no `send`) and asserts `not isinstance(...)` against `ConnectorClient`.
- `tests/test_connectors.py:TestConnectorPackageExports` (L169) gains:
  - `test_send_result_round_trip` — construct a `SendResult(platform_message_id="x", details={"k": "v"})`, verify it's frozen (assignment raises `FrozenInstanceError`), verify it's hashable (the `details` dict is excluded from hash/compare per the dataclass field metadata).
  - `test_platform_send_ok_prefix_constant` — assert `the_one.connectors.PLATFORM_SEND_OK_PREFIX == "[platform-send-ok]"`. Documents the cross-module contract.
  - `test_canonical_and_re_exports_resolve_to_same_object` (L170-180) — extend to also assert `the_one.connectors.SendResult is the_one.connectors.base.SendResult`.
- `tests/test_config.py:TestAgentConfigConstruction` (L14) gains:
  - `test_connector_account_ids_defaults_to_empty_list` — construct `AgentConfig(name="t")`, assert `cfg.connector_account_ids == []`.
  - `test_connector_account_ids_round_trip` — construct with non-empty list, dump, re-validate, assert equality.
  - `test_pre_f4_row_deserializes_with_empty_connector_account_ids` — `AgentConfig.model_validate({"name": "t"})` (no `connector_account_ids` key) yields `cfg.connector_account_ids == []` (back-compat against any pre-F4 stored agent rows).
- Flight log gains a "Leg Progress: agent-config-and-protocol-widen" entry summarizing what landed and noting any deviations.
- Leg status flipped to `landed` in this file's header (NOT `completed` — agentic-workflow batched-review defers `completed` to flight-end commit).

## Acceptance Criteria

- [ ] `AgentConfig` has a new field `connector_account_ids: list[str] = Field(default_factory=list)` placed immediately after `mcp_source_ids` in the model definition.
- [ ] `connector_account_ids` defaults to `[]` on `AgentConfig(name="t")` construction.
- [ ] `AgentConfig.model_validate({"name": "t"})` succeeds with `connector_account_ids == []` (back-compat for pre-F4 stored rows).
- [ ] `AgentConfig(name="t", connector_account_ids=["acc-a", "acc-b"]).model_dump()["connector_account_ids"] == ["acc-a", "acc-b"]` and round-trips through `model_validate`.
- [ ] `SendResult` frozen-slotted dataclass exists in `the_one/connectors/base.py` with `platform_message_id: str | None` and `details: dict[str, Any] = field(hash=False, compare=False)`.
- [ ] `SendResult` instances are frozen (`dataclasses.FrozenInstanceError` on assignment) and hashable (the dict field is excluded from hash/compare so the dataclass remains hashable on its scalar field).
- [ ] `ConnectorClient` Protocol in `the_one/connectors/base.py` declares `async def send(self, target: OutboundTarget, content: str) -> SendResult`.
- [ ] `the_one.connectors.SendResult` is `is`-identical to `the_one.connectors.base.SendResult` (canonical-import + re-export discipline).
- [ ] `the_one.connectors.PLATFORM_SEND_OK_PREFIX == "[platform-send-ok]"`.
- [ ] `the_one.connectors.__all__` includes `"SendResult"` and `"PLATFORM_SEND_OK_PREFIX"`.
- [ ] `StubClient.send(target, content)` returns `SendResult(platform_message_id="stub-msg-id", details={})` and appends `(target, content)` to `StubPlugin.outbound_records` via `StubPlugin.record_outbound`.
- [ ] When `StubPlugin.send_should_raise` is set, `StubClient.send(...)` raises that exception (does NOT record outbound, does NOT return). Mirror of `connect_should_fail` semantics.
- [ ] `StubPlugin.reset_for_test()` clears `send_should_raise` to `None` alongside the other reset assignments.
- [ ] `_MinimalClient` in `tests/test_connectors.py` has an `async def send(target, content) -> SendResult` method.
- [ ] `tests/test_connectors.py::TestConnectorClientProtocol::test_minimal_client_satisfies_protocol` still passes (was passing before; must still pass after the widening because `_MinimalClient` now implements `send`).
- [ ] `tests/test_connectors.py::TestConnectorClientProtocol::test_client_missing_send_fails_check` (new) asserts that a class with `is_alive` only (no `send`) fails `isinstance(..., ConnectorClient)` after the widening.
- [ ] `tests/test_connectors.py::TestConnectorPackageExports::test_canonical_and_re_exports_resolve_to_same_object` extended to verify `the_one.connectors.SendResult is the_one.connectors.base.SendResult`.
- [ ] `tests/test_connectors.py::TestConnectorPackageExports::test_send_result_is_hashable_despite_dict_field` (new) pins the frozen + dict-excluded-from-hash invariant.
- [ ] `tests/test_connectors.py::TestConnectorPackageExports::test_send_result_accepts_none_platform_message_id` (new) pins `platform_message_id: str | None` permissivity.
- [ ] `tests/test_connectors.py::TestConnectorPackageExports::test_platform_send_ok_prefix_constant` (new) pins the literal `"[platform-send-ok]"`.
- [ ] `tests/test_config.py::TestAgentConfigConstruction` covers the three `connector_account_ids` scenarios listed in Outputs.
- [ ] `connectors/README.md` §3 skeleton is split into separate `HypotheticalPlatformPlugin` (carrying `connect`/`disconnect`/`doctor`/`normalize_session_key`) and `HypotheticalPlatformClient` (carrying `is_alive`/`send`) classes.
- [ ] `HypotheticalPlatformPlugin.connect()` returns a `HypotheticalPlatformClient` instance (the wiring that ties the two classes together as a coherent example — the connect method must instantiate and return a `HypotheticalPlatformClient`, not the raw platform session).
- [ ] `connectors/README.md` §3 skeleton's `send` method demonstrates the `SendResult` return shape on `HypotheticalPlatformClient`.
- [ ] `connectors/README.md` §3 skeleton's `doctor` method passes non-empty `message=` on BOTH the success-branch (with `status="ok"`) and the error-branch (with `status="failed"`, NOT `"error"`) `DoctorReport` constructors. The example compiles and is consistent with `DoctorReport.status: Literal["ok", "degraded", "failed"]` at `connectors/base.py:120`.
- [ ] `docker exec the-one pytest tests/test_config.py tests/test_connectors.py -x --timeout 30` passes.
- [ ] `docker exec the-one pytest -x --timeout 30` (full suite) passes — F1 stub-driven e2e tests, F2 admin-surface tests, F3 session-model + dispatcher tests, and all other suites green; no regression.
- [ ] `docker exec the-one ruff check the_one tests` (or `make lint`) clean.
- [ ] Flight log gains a leg-progress entry; this file's `**Status**` flipped to `landed`.

## Verification Steps

- `docker exec the-one pytest tests/test_config.py::TestAgentConfigConstruction -x --timeout 30` — assert all three new tests pass.
- `docker exec the-one pytest tests/test_connectors.py -x --timeout 30` — assert `_MinimalClient` still satisfies the widened Protocol; the new client-missing-send test passes; the new SendResult round-trip + prefix-constant tests pass.
- `docker exec the-one pytest -x --timeout 30` — full suite green.
- `docker exec the-one ruff check the_one tests` — clean.
- `grep -n "connector_account_ids" the_one/agent/config.py` — exactly one match (the new field).
- `grep -n "SendResult\|PLATFORM_SEND_OK_PREFIX" the_one/connectors/__init__.py` — at least one match for each (in the import block + `__all__`).
- `grep -n "send_should_raise" the_one/connectors/_stub.py` — at least three matches (ClassVar declaration, `reset_for_test` clear, `StubClient.send` consult).
- Visual inspection: `connectors/README.md` §3 skeleton has 5 methods on the plugin (`connect`, `disconnect`, `doctor`, `normalize_session_key`, `send`) and `doctor` returns `DoctorReport(..., message="...", ...)` on both branches.

## Implementation Guidance

1. **Widen `ConnectorClient` Protocol** (in `the_one/connectors/base.py`):
   - Place `SendResult` dataclass between `DoctorReport` (currently ending ~L139) and `ConnectorClient` (currently starting ~L142). The class order in `base.py` is: `InboundEnvelope`, `OutboundTarget`, `SessionKey`, `DoctorReport`, **`SendResult` (new)**, `ConnectorClient`, `ConnectorPlugin`.
   - `SendResult` shape mirrors `DoctorReport` for the `details` field. The `field(hash=False, compare=False)` discipline keeps the dataclass hashable on its scalar field.
   - Add `send` to the `ConnectorClient` Protocol body AFTER `is_alive`. Use the existing `is_alive` shape for docstring style.
   - Update the `ConnectorClient` class docstring (currently L142-155): change the "Flight 4 widens this to add an outbound-send method when the platform-send tool needs it" wording to past tense, e.g. "Flight 4 widened this Protocol with `send` to carry outbound platform-bound messages. The widening is additive — existing `isinstance(client, ConnectorClient)` checks remain valid for clients that implement both `is_alive` and `send`; clients missing `send` after F4 now fail the Protocol check at runtime."

2. **Add the `PLATFORM_SEND_OK_PREFIX` constant + `SendResult` re-export** (in `the_one/connectors/__init__.py`):
   - Add `SendResult` to the `from the_one.connectors.base import (...)` block (alphabetical preserved; before `SessionKey` or after `OutboundTarget` per existing ordering).
   - Add `PLATFORM_SEND_OK_PREFIX = "[platform-send-ok]"` immediately after the `OPERATOR_VISIBILITY = "operator"` line (~L51). Document it briefly: "Success-prefix sentinel for `SendToPlatformChannelTool.execute()` (F4 leg 2). The dispatcher's visibility-tagger (F4 leg 4) matches on this prefix to decide `visibility=None` on the tool_result message."
   - Extend `__all__` (L53-72) with `"SendResult"` and `"PLATFORM_SEND_OK_PREFIX"`, alphabetically positioned.

3. **Widen `StubClient` + add `StubPlugin.send_should_raise`** (in `the_one/connectors/_stub.py`):
   - Import `SendResult` from `the_one.connectors.base` (extend the existing import block at lines 31-37).
   - Add `send_should_raise: ClassVar[BaseException | None] = None` to `StubPlugin`'s scenario-knobs section (after `doctor_should_raise` at line 95-100). Docstring shape mirrors `connect_should_fail`.
   - Extend `StubPlugin.reset_for_test` (lines 104-114) to set `cls.send_should_raise = None`.
   - Implement `StubClient.send`:
     ```python
     async def send(
         self,
         target: OutboundTarget,
         content: str,
     ) -> SendResult:
         if StubPlugin.send_should_raise is not None:
             raise StubPlugin.send_should_raise
         StubPlugin.record_outbound(target, content)
         return SendResult(platform_message_id="stub-msg-id", details={})
     ```
   - Place the method immediately after `is_alive` (line 48-49) for symmetry with the Protocol order.

4. **Add `AgentConfig.connector_account_ids`** (in `the_one/agent/config.py`):
   - Add the field immediately after `mcp_source_ids: list[str] = Field(default_factory=list)` (~line 76). Use the exact same shape:
     ```python
     connector_account_ids: list[str] = Field(default_factory=list)
     ```
   - Optionally a one-line comment: `# M10 F4: connector accounts attached to this agent. Mirror of mcp_source_ids.`

5. **Update `connectors/README.md` §3 skeleton — split into two classes**:
   The existing skeleton has ONE class (`HypotheticalPlatformPlugin`) that carries the 4 plugin methods. F4 widens `ConnectorClient` with `send`, so the skeleton MUST split into two classes to keep `send` on the right Protocol. Replace the current skeleton with this shape:
     ```python
     # Registered via register_builtin_connectors() in connectors/registry.py.
     from typing import Any

     from the_one.connectors.base import (
         ConnectorClient,
         DoctorReport,
         InboundEnvelope,
         OutboundTarget,
         SendResult,
         SessionKey,
     )
     from the_one.db.models import ConnectorAccount
     from the_one.encryption import Encryptor


     class HypotheticalPlatformClient:
         """Structural ConnectorClient — `is_alive` + `send`."""

         def __init__(self, platform_session: Any) -> None:
             self._session = platform_session

         def is_alive(self) -> bool:
             return self._session.is_open()  # pseudo-code

         async def send(
             self, target: OutboundTarget, content: str
         ) -> SendResult:
             # pseudo-code — real SDK call to deliver `content` to `target`:
             platform_msg = await self._session.post(
                 channel_id=target.channel_id,
                 thread_id=target.thread_id,
                 content=content,
             )
             return SendResult(
                 platform_message_id=platform_msg.id,
                 details={"channel": target.channel_id},
             )


     class HypotheticalPlatformPlugin:
         """Structural ConnectorPlugin — `connect` + `disconnect` + `doctor` +
         `normalize_session_key`. `connect()` returns a HypotheticalPlatformClient."""

         async def connect(
             self, account: ConnectorAccount, encryptor: Encryptor
         ) -> ConnectorClient:
             secrets = account.secrets  # already-decrypted dict
             token = secrets["bot_token"]
             platform_session: Any = await _open_platform_session(token)
             return HypotheticalPlatformClient(platform_session)

         async def disconnect(self, client: ConnectorClient) -> None:
             # idempotent close; do not raise if already closed
             await _close_platform_session(client)

         async def doctor(
             self, account: ConnectorAccount, encryptor: Encryptor
         ) -> DoctorReport:
             try:
                 client = await self.connect(account, encryptor)
             except Exception as e:  # noqa: BLE001
                 return DoctorReport(status="failed", message=str(e), details={})
             try:
                 info = await _platform_self_check(client)
                 return DoctorReport(
                     status="ok",
                     message=f"connected as {info['bot_user']}",
                     details={"identity": info["bot_user"]},
                 )
             finally:
                 await self.disconnect(client)

         def normalize_session_key(self, inbound: InboundEnvelope) -> SessionKey:
             return SessionKey(
                 platform=inbound.platform,
                 account_id=inbound.account_id,
                 channel_id=inbound.channel_id,
                 thread_id=inbound.thread_id,
             )


     # pseudo-code — replace with real platform SDK functions
     async def _open_platform_session(token: str) -> Any: ...
     async def _close_platform_session(client: Any) -> None: ...
     async def _platform_self_check(client: Any) -> dict[str, Any]: ...
     ```
   Key callouts for the implementing agent:
   - `SendResult` and `OutboundTarget` MUST be added to the skeleton's imports.
   - `HypotheticalPlatformPlugin.connect()` returns a `HypotheticalPlatformClient` instance (NOT the raw platform session) — this is the wiring that makes the two classes a coherent example.
   - `doctor`'s error-branch uses `status="failed"` (NOT `"error"`) per `connectors/base.py:120`'s `Literal["ok", "degraded", "failed"]` constraint.
   - `doctor`'s success and failure branches both pass `message=...` (the required field on `DoctorReport`).

6. **Update `_MinimalClient` + add new isinstance-fails test** (in `tests/test_connectors.py`):
   - Add `async def send(self, target, content)` to `_MinimalClient` (line 126-130). Return a `SendResult` (import it from the test imports if not already imported).
   - Add a new test in `TestConnectorClientProtocol` (after `test_client_missing_is_alive_fails_check` at line 162-166):
     ```python
     def test_client_missing_send_fails_check(self) -> None:
         """After F4 widening, a client missing `send` fails the Protocol check."""
         class _OnlyAlive:
             def is_alive(self) -> bool:
                 return True

         assert not isinstance(_OnlyAlive(), ConnectorClient)
     ```

7. **Extend `TestConnectorPackageExports`** (in `tests/test_connectors.py`):
   - Extend the existing `test_canonical_and_re_exports_resolve_to_same_object` (line 170-180) to also assert `SendResult` identity:
     ```python
     from the_one.connectors import SendResult as SRViaPackage
     from the_one.connectors.base import SendResult as SRViaCanonical
     assert SRViaPackage is SRViaCanonical
     ```
   - Add `test_send_result_round_trip` (new method on the class, after `test_doctor_report_is_hashable_despite_dict_field` at ~L240-247). Same invariant-pin shape as `test_doctor_report_is_hashable_despite_dict_field`: bare `frozen+slots+dict` would raise `TypeError: unhashable type` at `hash()` without the `field(hash=False, compare=False)` discipline — this test locks the discipline:
     ```python
     def test_send_result_is_hashable_despite_dict_field(self) -> None:
         """SendResult.details is excluded from hash + eq — same contract
         as InboundEnvelope.raw and DoctorReport.details. Bare frozen+slots
         with a dict field constructs but blows up on hash() — locked here."""
         r = SendResult(platform_message_id="msg-1", details={"k": "v"})
         h = hash(r)  # must not raise
         r2 = SendResult(platform_message_id="msg-1", details={"different": "x"})
         # Same hash and equal — details doesn't participate in identity.
         assert hash(r2) == h
         assert r == r2
         # Frozen — assignment raises FrozenInstanceError specifically.
         with pytest.raises(dataclasses.FrozenInstanceError):
             r.platform_message_id = "edited"  # type: ignore[misc]

     def test_send_result_accepts_none_platform_message_id(self) -> None:
         """``platform_message_id: str | None`` permits None for platforms
         that don't return a native message id. Pins the permissivity that
         leg 2's SendToPlatformChannelTool.execute() exploits."""
         r = SendResult(platform_message_id=None, details={})
         assert r.platform_message_id is None
         assert r.details == {}
     ```
   - Add `test_platform_send_ok_prefix_constant` (new method):
     ```python
     def test_platform_send_ok_prefix_constant(self) -> None:
         """The PLATFORM_SEND_OK_PREFIX literal is the cross-module contract."""
         from the_one.connectors import PLATFORM_SEND_OK_PREFIX
         assert PLATFORM_SEND_OK_PREFIX == "[platform-send-ok]"
     ```

8. **Extend `TestAgentConfigConstruction`** (in `tests/test_config.py`):
   - Add three tests after the existing tests (the class starts at line 14):
     ```python
     def test_connector_account_ids_defaults_to_empty_list(self) -> None:
         cfg = AgentConfig(name="t")
         assert cfg.connector_account_ids == []

     def test_connector_account_ids_round_trip(self) -> None:
         cfg = AgentConfig(name="t", connector_account_ids=["acc-a", "acc-b"])
         dumped = cfg.model_dump()
         assert dumped["connector_account_ids"] == ["acc-a", "acc-b"]
         revived = AgentConfig.model_validate(dumped)
         assert revived.connector_account_ids == ["acc-a", "acc-b"]

     def test_pre_f4_row_deserializes_with_empty_connector_account_ids(self) -> None:
         """Back-compat: pre-F4 stored agent rows have no
         `connector_account_ids` key; field defaults to []."""
         cfg = AgentConfig.model_validate({"name": "t"})
         assert cfg.connector_account_ids == []
     ```

9. **Run the full test suite** (`docker exec the-one pytest -x --timeout 30`) and `make lint` to confirm no regression.

10. **Update flight log** with a "Leg Progress: agent-config-and-protocol-widen" entry covering: what landed (the bullet list from Outputs), any deviations from this leg artifact (none expected), test trajectory (delta from F3's 1881 unit-test baseline), any anomalies.

11. **Flip leg status to `landed`** in this file's header. Do NOT commit (agentic-workflow batched-review model).

## Edge Cases

- **`SendResult.details` mutation after construction**: Since `field(hash=False, compare=False)` is used, the dict object itself is mutable even though the dataclass is frozen. This matches `DoctorReport.details` and `InboundEnvelope.raw` — a caller that mutates `details` after construction sees the mutation. Not a leg-1 concern; documented for completeness.

- **`StubPlugin.send_should_raise` set to a non-`BaseException`**: Type-checked by `BaseException | None`; Pydantic isn't involved (ClassVar). If a test sets it to a non-exception, `raise <non-exception>` at the call site raises `TypeError`. Acceptable — the failure mode is loud.

- **Multiple concurrent `StubClient.send` calls**: The class-level `outbound_records` buffer accumulates in call order. The `record_outbound` method appends without locking. Concurrent tests that race on `outbound_records` need explicit serialization or pre-test reset via `reset_for_test`. Leg 1 doesn't add concurrency tests; leg 5 covers e2e under event-coordinated patterns.

- **`AgentConfig` with both `mcp_source_ids` and `connector_account_ids` populated**: Independent fields, no validation interaction. The factory (leg 3) iterates each list independently.

- **Pre-F4 agent row with `connector_account_ids: null` in JSON**: Per `AgentConfig`'s `extra="ignore"` + Pydantic strictness on declared fields, `null` for `list[str]` defaults to a Pydantic validation error (cannot coerce None to list). The mitigation: `Field(default_factory=list)` only applies when the key is absent; when present-but-null, Pydantic surfaces the validation error. This is the same failure mode `mcp_source_ids: null` would produce today; the agent-editor JSON serializer always emits `[]`, never `null`. Acceptable; tests cover the absent-key path, not the null-value path.

- **`_MinimalPlugin` (line 103, distinct from `_MinimalClient`) returns `_MinimalClient()` from `connect`**: The plugin tests (line 147) invoke `isinstance(_MinimalPlugin(), ConnectorPlugin)` — unchanged by the client-Protocol widening. The plugin Protocol is NOT widened in this leg.

- **`tests/test_connectors_pool.py:_StubClient`**: Concrete-class isinstance checks only; not affected by the Protocol widening. No changes required.

## Files Affected

- `the_one/agent/config.py` — add `connector_account_ids` field
- `the_one/connectors/base.py` — add `SendResult` dataclass; widen `ConnectorClient` Protocol with `send`; update Protocol docstring
- `the_one/connectors/__init__.py` — re-export `SendResult`; add `PLATFORM_SEND_OK_PREFIX` constant; update `__all__`
- `the_one/connectors/_stub.py` — implement `StubClient.send`; add `StubPlugin.send_should_raise` ClassVar; extend `reset_for_test`
- `the_one/connectors/README.md` — §3 skeleton: add `send` method, fix `doctor` to use `message=`
- `tests/test_connectors.py` — extend `_MinimalClient` with `send`; new tests for client-missing-send-fails-check, SendResult round-trip, PLATFORM_SEND_OK_PREFIX constant; extend the re-export-identity test
- `tests/test_config.py` — new tests for `connector_account_ids` defaults, round-trip, pre-F4-back-compat
- `missions/10-bi-directional-comms-connectors/flights/04-platform-send-tool-and-outbound/flight-log.md` — append leg-progress entry
- `missions/10-bi-directional-comms-connectors/flights/04-platform-send-tool-and-outbound/legs/01-agent-config-and-protocol-widen.md` — flip status to `landed`

---

## Post-Completion Checklist

**Per agentic-workflow batched-review model: do NOT commit; defer to flight-end.**

- [ ] All acceptance criteria verified (run the Verification Steps above)
- [ ] Full test suite passes (`docker exec the-one pytest -x --timeout 30`)
- [ ] Lint clean (`make lint` or equivalent)
- [ ] Update `flight-log.md` with a "Leg Progress: agent-config-and-protocol-widen" entry
- [ ] Set this leg's `**Status**` to `landed` in this file's header
- [ ] Signal `[HANDOFF:review-needed]` to the Flight Director — do NOT commit, do NOT check off in flight.md, do NOT mark `completed` (flight-end Reviewer + commit step owns those)

---

## Citation Audit

All 24 code-location citations verified against current code at leg design time:

| Citation | Status | Evidence |
|---|---|---|
| `the_one/agent/config.py:76 — "mcp_source_ids: list[str] = Field(default_factory=list)"` | OK | Verified at L76 |
| `the_one/connectors/base.py:111-139 (DoctorReport)` | OK | Spans L111-139; `message: str` required field at L125 |
| `the_one/connectors/base.py:142 (ConnectorClient Protocol)` | OK | `@runtime_checkable` decorator L142; class def L144 |
| `the_one/connectors/base.py:142-164 (ConnectorClient docstring)` | OK | "Flight 4 widens this to add an outbound-send method when the platform-send tool needs it" at L153-154 |
| `the_one/connectors/__init__.py:51 — "OPERATOR_VISIBILITY = \"operator\""` | OK | Verified at L51 |
| `the_one/connectors/__init__.py:53-72 (__all__)` | OK | Verified |
| `the_one/connectors/_stub.py:42 — "class StubClient:"` | OK | Verified at L42 |
| `the_one/connectors/_stub.py:52 — "class StubPlugin:"` | OK | Verified at L52 |
| `the_one/connectors/_stub.py:92-94 (connect_should_fail)` | OK | Verified at L92-93 |
| `the_one/connectors/_stub.py:95-100 (doctor_should_raise)` | OK | Verified at L95-101 |
| `the_one/connectors/_stub.py:104-114 (reset_for_test)` | OK | `@classmethod` L104, def L105, body L106-114 |
| `the_one/connectors/_stub.py:127-134 (record_outbound)` | OK | `@classmethod` L126, def L127, body L128-134 |
| `the_one/connectors/README.md:102-161 (skeleton plugin)` | OK | Skeleton block verified |
| `the_one/connectors/README.md:139 (DoctorReport error-branch missing message=)` | OK | Verified — bug confirmed at L139 |
| `the_one/connectors/README.md:143 (DoctorReport success-branch missing message=)` | OK | Verified — same bug at L143 |
| `tests/test_connectors.py:126-130 (_MinimalClient)` | OK | Verified — class def L126, `is_alive` only |
| `tests/test_connectors.py:150-151 (test_plugin_missing_method_fails_check)` | OK | Verified — asserts `not isinstance` on incomplete plugin |
| `tests/test_connectors.py:158 (TestConnectorClientProtocol)` | OK | Verified at L158 |
| `tests/test_connectors.py:159-160 (test_minimal_client_satisfies_protocol)` | OK | Verified at L159-160 |
| `tests/test_connectors.py:162-166 (test_client_missing_is_alive_fails_check)` | OK | Verified at L162-166 |
| `tests/test_connectors.py:169 (TestConnectorPackageExports)` | OK | Verified at L169 |
| `tests/test_connectors.py:170-180 (canonical-and-re-exports test)` | OK | Verified |
| `tests/test_config.py:14 (TestAgentConfigConstruction)` | OK | Verified — class at L14 per earlier survey |
| `tests/test_connectors_pool.py:84 (_StubClient — concrete-class isinstance only)` | OK | Verified — `isinstance(client, _StubClient)` at L169, L196, L278; no Protocol-isinstance checks |
