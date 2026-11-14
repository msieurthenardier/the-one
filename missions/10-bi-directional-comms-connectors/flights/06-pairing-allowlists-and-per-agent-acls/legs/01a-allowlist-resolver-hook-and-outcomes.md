# Leg: allowlist-resolver-hook-and-outcomes

**Status**: completed
**Flight**: [Pairing, Allowlists, and Per-Agent ACLs](../flight.md)

## Objective

Land the type-level surface for F6's gating substrate in `the_one/connectors/base.py`: the three-outcome ADT (`Permit | NeedsPairing | Deny`), the `_default_permit` fallback callable, and the documented expected signature of the optional `resolve(account, envelope)` plugin hook. The `ConnectorPlugin` Protocol is NOT widened; the hook is discovered at consult sites via `getattr(plugin, "resolve", _default_permit)` — same convention as F3's `display_channel`. The stub plugin is NOT updated to implement `resolve` in this leg — preserving F1–F5 byte-identical regression. F6 legs 2 and 3 are the first consumers.

## Context

- **Flight Design Decision — "Three-outcome resolver shape"** (flight.md): `Permit | NeedsPairing(reason) | Deny(reason)`. The hook signals shape; the dispatcher (leg 2) owns pairing-code validation within `NeedsPairing`.
- **Flight Design Decision — "Optional plugin hook via getattr"** (flight.md): Resolver discovered by `getattr(plugin, "resolve", _default_permit)`. No `AllowlistResolver` Protocol; the stub does NOT implement `resolve`; F1–F5 tests pass byte-identically.
- **Project convention `optional-plugin-hook-via-getattr-sentinel`** (`the_one/agents.md:96`): F3's `display_channel` is the precedent. Hook is documented on plugins but NOT declared on the Protocol; consumers tolerate exceptions and fall back.
- **F1 docstring promises that contradict this leg's framing**:
  - `the_one/connectors/base.py:11-15` — "supports allowlists ... structurally satisfies ... `AllowlistResolver` ... Protocols ... All three Protocols will live in this file"
  - `the_one/connectors/base.py:222-227` — "Flights 6 and 7 do NOT widen this Protocol — they introduce separate `AllowlistResolver` and `CommandHandler` Protocols, also in this file"
  - `the_one/connectors/README.md:29` — "Future home of AllowlistResolver (Flight 6)"
  - `the_one/connectors/README.md:82` — "`AllowlistResolver` (Flight 6) — ACL-aware connectors will additionally satisfy this Protocol"
  - `the_one/agents.md:306` — "carries a `# F6: AllowlistResolver consultation lands here` marker for F6's diff to replace"
  - `the_one/agents.md:336,339,361` — predicts `AllowlistResolver` Protocol

  All six prose sites are revised in this leg to reflect the chosen getattr-hook shape. F7 `CommandHandler` predictions (`base.py:13,225`, `README.md:30,84`, `agents.md:337`) stay untouched — different leg, different flight scope.

- **Deferred to leg 3 (NOT this leg)**: `the_one/connectors/README.md:363` quotes the literal source-code marker text `# F6: AllowlistResolver consultation lands here` that lives at `tools/connector_send.py:131`. The marker text changes when leg 3 wires the consultation; README:363's quoted text changes alongside it. Leg 1a does NOT touch either. Documented here so the deferral is explicit, not an oversight.

- **`optional-plugin-hook-via-getattr-sentinel` convention variation**: the convention at `the_one/agents.md:96-100` cites `getattr(plugin, "<hook>", None)` with `None` as the sentinel default — `display_channel`'s pattern. F6's `resolve` hook uses a named callable (`_default_permit`) as the fallback instead, because the default outcome is structured (a `Permit()` instance) rather than implicit. Leg 1a appends one sentence to the convention block describing this variation so future readers understand both shapes are legitimate.

- **`_default_permit` lives in `connectors/base.py`** alongside the outcome ADT — it is THE canonical fallback that both leg 2 (inbound) and leg 3 (outbound) import. The `display_channel` precedent uses an inline `getattr(plugin, "display_channel", None)` with a literal fallback, but the resolver's fallback is non-trivial (returns a structured `Permit()`), so promoting it to a named symbol is cleaner than open-coding `lambda *_, **__: Permit()` at every consult site.

- **Stub plugin discipline**: `StubPlugin` in `the_one/connectors/_stub.py` does NOT gain a `resolve` method in this leg. F1–F5 tests that drive inbound through the stub MUST observe the `_default_permit` fallback path (every envelope → `Permit`) and pass byte-identically. Leg 2's pairing tests will introduce a stub variant (or monkeypatch site) — that decision is leg 2's, not this leg's.

- **Type-level outcomes** use `@dataclass(frozen=True, slots=True)` per the codebase convention (`InboundEnvelope`, `OutboundTarget`, `SessionKey`, `DoctorReport`, `SendResult` all use this pattern). `Permit` has no fields; `NeedsPairing` and `Deny` each carry a `reason: str` for audit-log surfacing.

- **Union type alias**: `ResolveOutcome = Permit | NeedsPairing | Deny`. Exported from `connectors/base.py` and re-exported from `connectors/__init__.py` per the canonical-import + convenience-re-export convention.

## Inputs

- `the_one/connectors/base.py` — current shape (4 dataclasses + `ConnectorPlugin` Protocol + `ConnectorClient` Protocol); `Permit`/`NeedsPairing`/`Deny`/`ResolveOutcome`/`_default_permit` are absent (grep verified, zero hits across `the_one/` and `tests/`)
- `the_one/connectors/__init__.py` — public re-export surface (mirror for adding the new symbols)
- `the_one/connectors/README.md` — "§4. Optional hooks (additive plugin extension)" section that documents `display_channel`; leg 1a appends a parallel entry for `resolve`. README:363 quotes the source-code marker text — DEFERRED to leg 3 (the marker text changes there).
- `the_one/agents.md` — Connector subsystem section that predicts an `AllowlistResolver` Protocol; leg 1a revises those predictions AND appends one sentence to the `optional-plugin-hook-via-getattr-sentinel` convention block (line 96-100) documenting the `_default_permit` fallback variation
- `the_one/connectors/_stub.py` — stub plugin; UNCHANGED in this leg (regression-net preservation)
- `tests/test_connectors.py` — F1 Protocol / registry test suite; tests that assert `isinstance(StubPlugin(), ConnectorPlugin)` and similar MUST continue to pass byte-identically (no widening of `ConnectorPlugin`)
- `tests/test_connectors_inbound.py`, `tests/test_connectors_e2e_session.py`, `tests/test_connectors_pool.py` — F3/F4/F5 regression net that drives the stub end-to-end; MUST pass byte-identically after this leg
- `tests/_connector_dispatch_helpers.py:128` — `_create_test_account` shared fixture builder; reference shape for `ConnectorAccount` construction
- `tests/_connector_dispatch_helpers.py:151-169` — `_envelope` factory; reference shape for `InboundEnvelope` construction
- `tests/test_connectors.py:210-219` — inline minimal-fixture style for type-level tests (preferred over heavyweight helper import in this leg's tests; matches the F1 surface-test convention)

## Outputs

- `the_one/connectors/base.py` — three new dataclasses (`Permit`, `NeedsPairing(reason: str)`, `Deny(reason: str)`); `ResolveOutcome` type alias; `_default_permit(account, envelope) -> Permit` callable; module-level docstring revised to remove the "future `AllowlistResolver` Protocol" prediction and replace it with the optional-hook framing
- `the_one/connectors/__init__.py` — re-exports `Permit`, `NeedsPairing`, `Deny`, `ResolveOutcome` (public surface). `_default_permit` is NOT re-exported (private to the package — only `_inbound.py` and `tools/connector_send.py` import it, both intra-package or via canonical path). `_default_permit.__module__ == "the_one.connectors.base"` is asserted in tests to pin the canonical import path.
- `the_one/connectors/README.md` — "§4. Optional hooks" section gains a `resolve` entry documenting the expected signature `(account: ConnectorAccount, envelope: InboundEnvelope) -> ResolveOutcome`, the three outcomes, and the `_default_permit` fallback
- `the_one/agents.md` — five Connector-subsystem docstring sites updated (lines listed in Inputs); the `# F6: AllowlistResolver consultation lands here` marker at `tools/connector_send.py:131` and its description in `agents.md:306` reframed as `# F6: optional resolver hook consultation lands here`. The marker source-code edit itself stays in leg 3's territory; leg 1a updates the `agents.md` prose pointing at it.
- `tests/test_connectors_resolver.py` — NEW test module (sibling of `test_connectors_pool.py`, `test_connectors_inbound.py`, `test_connectors_e2e_session.py`, `test_connectors_session.py`) that asserts:
  - `Permit()`, `NeedsPairing("...")`, `Deny("...")` construct + equality + hashability
  - `ResolveOutcome` accepts each as a member
  - `_default_permit(account, envelope)` returns a `Permit()` for any inputs
  - `getattr(StubPlugin(), "resolve", _default_permit)` returns `_default_permit` (stub does not implement)
  - One end-to-end smoke: drive a stub-backed inbound through `_inbound.dispatch_inbound` and assert F1–F5 tests still pass — this is REGRESSION coverage, not new coverage. Achieved by adding zero new assertions; the existing dispatcher test suite (`test_connectors_inbound.py`) running clean is the assertion.

## Acceptance Criteria

- [ ] `Permit`, `NeedsPairing`, `Deny` are exposed from `the_one.connectors.base` as frozen, slotted dataclasses (`Permit` has no fields; `NeedsPairing` and `Deny` each have one `reason: str` field)
- [ ] `ResolveOutcome` is exposed from `the_one.connectors.base` as a `Union[Permit, NeedsPairing, Deny]` (or `Permit | NeedsPairing | Deny` PEP-604 form — match the codebase's prevailing style; `connectors/base.py` already uses `str | None` so PEP-604 is the right choice)
- [ ] `_default_permit` is defined in `the_one.connectors.base` with signature `(account: ConnectorAccount, envelope: InboundEnvelope) -> Permit` and returns a fresh `Permit()` (equivalent literal `Permit()` per call is fine; `Permit` instances are frozen-dataclass-equal so callers can compare against a sentinel without identity reliance)
- [ ] `_default_permit` is NOT exported from `the_one.connectors.__init__.py`'s `__all__` (private to the package — consumers in `_inbound.py` and `tools/connector_send.py` import via the canonical path `the_one.connectors.base`)
- [ ] `Permit`, `NeedsPairing`, `Deny`, `ResolveOutcome` ARE re-exported from `the_one.connectors.__init__.py` (public surface — operator code, tests, future plugin authors may consult)
- [ ] `ConnectorPlugin` Protocol is UNCHANGED (no `resolve` method added; the method count stays at 4 — `connect`, `disconnect`, `doctor`, `normalize_session_key`)
- [ ] `the_one/connectors/_stub.py` is UNCHANGED (no `resolve` method added; the stub's structural Protocol satisfaction shape stays identical)
- [ ] `the_one/connectors/base.py` module docstring revised: the "Flights 6 and 7 do NOT widen this Protocol — they introduce separate `AllowlistResolver` and `CommandHandler` Protocols" prediction is replaced with a description that names F6's actual shape (optional `resolve` hook + outcome ADT) and leaves F7's prediction intact (F7 remains future work; its prediction in the docstring stays untouched in this leg)
- [ ] `the_one/connectors/README.md` §4 "Optional hooks" gains a `resolve` entry below the existing `display_channel` entry, naming the signature, the three-outcome shape, the `_default_permit` fallback, and pointing leg-2/leg-3 consumers at it
- [ ] `the_one/agents.md` Connector-subsystem references to a future `AllowlistResolver` Protocol are reframed as optional-hook-via-getattr (lines `306`, `336`, `339`, `361` per the recon of base.py/README.md/agents.md); the F7 `CommandHandler` predictions are untouched
- [ ] Test coverage lands in a NEW file `tests/test_connectors_resolver.py` (matches the per-feature module convention: `test_connectors_pool.py`, `test_connectors_inbound.py`, `test_connectors_e2e_session.py`, `test_connectors_session.py` are sibling modules). Tests cover: outcome construction, equality, hashability; `_default_permit` return; `_default_permit.__module__` canonical-path pinning; stub's lack-of-`resolve`; `ResolveOutcome` membership; a smoke-import check that `from the_one.connectors.base import Permit, NeedsPairing, Deny, ResolveOutcome, _default_permit` succeeds (catches "added symbol broke base.py at import time")
- [ ] `tests/test_connectors.py`, `tests/test_connectors_inbound.py`, `tests/test_connectors_e2e_session.py`, `tests/test_connectors_pool.py` pass BYTE-IDENTICALLY — no count/timing change; the dispatcher's behavior is unchanged because leg 1a adds the surface but no consumer yet
- [ ] `mypy` / `ruff` clean on the modified files
- [ ] Full test suite `docker exec the-one pytest -x --timeout 30` passes (regression net)

## Verification Steps

- `cd ~/projects/the-one && grep -n "Permit\|NeedsPairing\|Deny\|ResolveOutcome\|_default_permit" the_one/connectors/base.py` — confirm the four new symbols exist
- `python -c "from the_one.connectors.base import Permit, NeedsPairing, Deny, ResolveOutcome, _default_permit; p1 = Permit(); p2 = Permit(); assert p1 == p2 and hash(p1) == hash(p2); print(NeedsPairing('test'), Deny('test'))"` (run inside the container)
- `python -c "from the_one.connectors import Permit, NeedsPairing, Deny, ResolveOutcome; print('public exports ok')"` — confirm public re-exports
- `python -c "from the_one.connectors import _default_permit"` should FAIL (private; not re-exported) — `python -c "from the_one.connectors.base import _default_permit"` should succeed
- `python -c "from the_one.connectors._stub import StubPlugin; p = StubPlugin(); assert not hasattr(p, 'resolve'); print('stub unchanged')"`
- `docker exec the-one pytest -x --timeout 30 tests/test_connectors.py tests/test_connectors_inbound.py tests/test_connectors_e2e_session.py tests/test_connectors_pool.py` — F1/F3/F4/F5 regression net byte-identical
- `docker exec the-one pytest -x --timeout 30 tests/test_connectors_resolver.py` — leg 1a coverage passes
- `docker exec the-one pytest -x --timeout 30` — full suite passes (final regression check)
- `grep -n "AllowlistResolver" the_one/ -r` from the project root — should show ONLY (a) the source-code marker `# F6: AllowlistResolver consultation lands here` at `the_one/tools/connector_send.py:131` (deferred to leg 3), and (b) the quoted marker text in `the_one/connectors/README.md:363` (also deferred to leg 3). Zero standalone `AllowlistResolver` Protocol predictions remain (all six F6-prediction sites reframed)
- `grep -n "CommandHandler" the_one/` — line SET (file:line tuples) must be identical before and after this leg. Hit COUNT on `agents.md:339` decreases by 1 (one of the two `CommandHandler` mentions on that line is reframed alongside the `AllowlistResolver` removal; see Edge Cases). F7 territory remains intact at `base.py:12,225`, `README.md:30,84`, `agents.md:337,339`.

## Implementation Guidance

1. **Define the outcome ADT in `connectors/base.py`** — place AFTER the existing supporting dataclasses (immediately after `SendResult` ends around line 165) and BEFORE the `ConnectorClient` Protocol at line 168. This ordering avoids any forward-reference fragility on `InboundEnvelope` / `ConnectorAccount` in `_default_permit`'s signature (those types are imported / defined above this point). `from __future__ import annotations` is already present at line 23, so PEP-563 would defer evaluation anyway — but committing to the placement removes the "could read backwards" objection. The revised `ConnectorPlugin` Protocol docstring (step 4 below) references these symbols by name; module-load order is `dataclasses → outcomes → `_default_permit` → `ConnectorClient` → `ConnectorPlugin`. A zero-field frozen+slots dataclass (`Permit`) constructs cleanly with a docstring as the body — no `pass` needed.

   ```python
   @dataclass(frozen=True, slots=True)
   class Permit:
       """Resolver outcome: the envelope is admitted; agent.step proceeds normally."""

   @dataclass(frozen=True, slots=True)
   class NeedsPairing:
       """Resolver outcome: the peer is unknown; the dispatcher must validate a pairing prefix.

       The plugin signals the SHAPE ("this peer isn't on the allowlist; pair-or-deny");
       the dispatcher (F6 leg 2) owns prefix validation against
       ``account.config["pairing"]["code"]``. ``reason`` surfaces in audit log
       entries written to ``chat_sessions.session_metadata``.
       """
       reason: str

   @dataclass(frozen=True, slots=True)
   class Deny:
       """Resolver outcome: the envelope is rejected outright; no pairing path.

       The dispatcher logs the outcome to ``session_metadata`` and returns
       without invoking ``agent.step``. From the peer's perspective the bot
       is silent. ``reason`` surfaces in audit log entries.
       """
       reason: str

   ResolveOutcome = Permit | NeedsPairing | Deny
   ```

2. **Define `_default_permit`** below the ADT:

   ```python
   def _default_permit(
       account: ConnectorAccount,
       envelope: InboundEnvelope,
   ) -> Permit:
       """Default resolver fallback when a plugin does not implement ``resolve``.

       Used by F6's inbound dispatcher (``connectors/_inbound.py``) and
       outbound tool (``tools/connector_send.py``) via
       ``getattr(plugin, "resolve", _default_permit)``. Returns ``Permit()``
       unconditionally — the plugin opted not to gate, so the subsystem
       does not gate either.

       Private to the connector package: consumers import via the canonical
       path ``the_one.connectors.base._default_permit``, not via the
       ``__init__.py`` convenience re-export.
       """
       return Permit()
   ```

3. **Revise the module docstring at `connectors/base.py:9-15`** — drop ONLY the `AllowlistResolver` Protocol prediction; PRESERVE the F7 `CommandHandler` Protocol prediction (different leg, different flight scope). Replace with a paragraph naming F6's actual shape:

   - Before: "A connector that supports allowlists and platform-side commands additionally satisfies the :class:`AllowlistResolver` and :class:`CommandHandler` Protocols (introduced by flights 6 and 7 of mission 10). All three Protocols will live in this file ..."
   - After: "A connector that supports per-(peer, channel) gating implements the OPTIONAL ``resolve(account, envelope) -> ResolveOutcome`` hook (introduced by flight 6 of mission 10). The hook is discovered by consumers via :func:`getattr` with :func:`_default_permit` as the fallback — same convention as F3's ``display_channel``. It is NOT declared on the :class:`ConnectorPlugin` Protocol; plugins opt in by exposing the method. A connector that handles platform-side commands additionally satisfies the :class:`CommandHandler` Protocol introduced by flight 7. The three-outcome ADT (:class:`Permit`, :class:`NeedsPairing`, :class:`Deny`) and the :class:`CommandHandler` Protocol live in this file alongside :class:`ResolveOutcome`."

   The post-edit grep-invariant: `grep -n "CommandHandler" the_one/connectors/base.py` returns lines `{12, 225}` (line 12 is the new F7 mention after the revision; line 225 is unchanged in the `ConnectorPlugin` docstring).

4. **Revise the `ConnectorPlugin` Protocol docstring at `connectors/base.py:222-227`** — same reframing: drop the "introduce separate `AllowlistResolver` and `CommandHandler` Protocols" prediction; replace with "F6 introduces the OPTIONAL `resolve(account, envelope) -> ResolveOutcome` hook discoverable via `getattr` (not a Protocol widening); F7 will introduce `CommandHandler`."

5. **Update `the_one/connectors/__init__.py`** — add `Permit`, `NeedsPairing`, `Deny`, `ResolveOutcome` to the import list and `__all__`. Read the current file first; the existing pattern shows the right shape (canonical-import + convenience-re-export). Do NOT add `_default_permit` — private.

6. **Update `the_one/connectors/README.md` §4 "Optional hooks"** — append a `resolve` subsection below the existing `display_channel` entry:

   ```markdown
   Second instance: **`resolve(account: ConnectorAccount, envelope: InboundEnvelope) -> ResolveOutcome`**
   for per-(peer, channel) gating in `the_one.connectors._inbound.dispatch_inbound`
   and `the_one.tools.connector_send.SendToPlatformChannelTool.execute`
   (M10 F06 L2 + L3). Plugins that implement it return one of three outcomes:
   `Permit()` (admit), `NeedsPairing(reason)` (dispatcher validates a pairing
   prefix), or `Deny(reason)` (reject silently). Plugins that don't implement
   it fall through to `_default_permit` at the consult sites — always
   `Permit()`. The `StubPlugin` does NOT implement `resolve`; F1–F5
   regression coverage exercises the `_default_permit` path.
   ```

7. **Update `the_one/agents.md` Connector subsystem references** — lines `306`, `336`, `339`, `361`. For each, reframe `AllowlistResolver` Protocol language as optional-hook-via-getattr. Specifically:
   - L306: the description of the source-code marker at `tools/connector_send.py:131`. Leg 1a reframes the PROSE here from "AllowlistResolver consultation" → "optional resolver hook consultation". The SOURCE-CODE marker text at `connector_send.py:131` is leg 3's edit; `the_one/connectors/README.md:363`'s quoted marker text is leg 3's edit. Leg 1a touches NEITHER source-code file nor README:363.
   - L336: drop the `AllowlistResolver (Flight 6) — per-(agent, peer) and per-(agent, group/channel) ACL resolution` Protocol-list line OR rewrite as "Optional `resolve` hook (Flight 6) — per-(peer, channel) ACL resolution via `getattr` consult site"
   - L339: surgically reframe the `AllowlistResolver` token in this line ONLY. The sentence currently reads: "A connector that supports allowlists structurally satisfies BOTH `ConnectorPlugin` AND `AllowlistResolver`. Per the `structural-Protocol-satisfaction` convention, implementations do NOT inherit from the Protocols — they just expose the right methods. **Structural satisfaction is per-Protocol, not subsystem-wide**: a connector that claims to satisfy `Plugin` + `AllowlistResolver` + `CommandHandler` MUST be asserted via `isinstance(conn, ProtocolType)` for each Protocol it claims, separately. ..." The two `AllowlistResolver` mentions in L339 are reframed (one of them disappears because `AllowlistResolver` is no longer a Protocol; the other is replaced with optional-hook language). The TWO `CommandHandler` mentions in L339 — `CommandHandler` in the "claims to satisfy `Plugin` + ... + `CommandHandler`" list AND the surrounding structural-satisfaction prose — MUST be preserved. Concretely: replace the sentence pair with "A connector that supports per-(peer, channel) gating implements the optional `resolve` hook (see §4 in `connectors/README.md`); the `ConnectorPlugin` Protocol stays at its 4-method shape. Per the `structural-Protocol-satisfaction` convention, implementations do NOT inherit from the Protocols — they just expose the right methods. **Structural satisfaction is per-Protocol, not subsystem-wide**: a connector that claims to satisfy `ConnectorPlugin` + `CommandHandler` MUST be asserted via `isinstance(conn, ProtocolType)` for each Protocol it claims, separately. ..." Post-edit, L339's `CommandHandler` mention count goes from 2 → 1 (lost the list entry that included AllowlistResolver). The Edge Cases CommandHandler-grep invariant (below) acknowledges this drop.
   - L361: replace the `AllowlistResolver Protocol will layer channel/thread/peer ACLs on top via the documented hook point` sentence with optional-hook framing — e.g. "F6's optional `resolve` hook layers channel/thread/peer ACLs on top via the documented hook point"
   - ALSO append one sentence to the `optional-plugin-hook-via-getattr-sentinel` convention block at L96-100, e.g. "The fallback may be `None` (consult site short-circuits — `display_channel`'s shape) OR a named callable that returns the default outcome (when the default outcome is structured — F6's `_default_permit` returns a `Permit()` instance)."

   F7 `CommandHandler` predictions at `agents.md:337` are NOT touched (different leg, different flight scope).

8. **Write tests** in a NEW file `tests/test_connectors_resolver.py` (per-feature test module — matches the F1 convention; `test_connectors_pool.py`, `test_connectors_inbound.py`, `test_connectors_e2e_session.py`, `test_connectors_session.py` are siblings). Use inline minimal-fixture style (mirrors `tests/test_connectors.py:210-219`); heavyweight helpers from `tests/_connector_dispatch_helpers.py` are overkill for type-level surface tests. Tests:

   ```python
   from the_one.connectors import Permit, NeedsPairing, Deny, ResolveOutcome
   from the_one.connectors.base import _default_permit, InboundEnvelope
   from the_one.db.models import ConnectorAccount


   def _account() -> ConnectorAccount:
       # Minimal fixture; only id/type are consulted in this leg's tests.
       return ConnectorAccount(
           id="acc-1",
           name="test",
           type="stub",
           config={},
           secrets={},
           created_at="2026-05-18T00:00:00Z",
           updated_at="2026-05-18T00:00:00Z",
       )


   def _envelope() -> InboundEnvelope:
       return InboundEnvelope(
           platform="stub",
           account_id="acc-1",
           channel_id="c",
           thread_id=None,
           peer_id="p",
           peer_name="P",
           text="t",
           raw={},
       )


   def test_smoke_import_canonical_path():
       # Catches "added symbol broke base.py at import time".
       from the_one.connectors.base import (  # noqa: F401
           Permit, NeedsPairing, Deny, ResolveOutcome, _default_permit,
       )
       assert _default_permit.__module__ == "the_one.connectors.base"


   def test_outcomes_construct_and_equate():
       assert Permit() == Permit()
       assert NeedsPairing("x") == NeedsPairing("x")
       assert Deny("x") != Deny("y")
       assert hash(Permit()) == hash(Permit())  # frozen+slots → hashable


   def test_resolve_outcome_union_accepts_all_three():
       outcomes: list[ResolveOutcome] = [Permit(), NeedsPairing("r"), Deny("r")]
       for o in outcomes:
           assert isinstance(o, (Permit, NeedsPairing, Deny))


   def test_default_permit_returns_permit_for_any_inputs():
       result = _default_permit(_account(), _envelope())
       assert isinstance(result, Permit)


   def test_stub_plugin_does_not_implement_resolve():
       from the_one.connectors._stub import StubPlugin
       assert not hasattr(StubPlugin(), "resolve")
       # The getattr-discovery convention falls back to _default_permit:
       hook = getattr(StubPlugin(), "resolve", _default_permit)
       assert hook is _default_permit


   def test_default_permit_is_not_publicly_reexported():
       import the_one.connectors as pkg
       assert "_default_permit" not in getattr(pkg, "__all__", [])
   ```

   The `ConnectorAccount` constructor field shape comes from `the_one/db/models.py` — verify the exact field set before writing the fixture (the recon walk at design time named the conventional shape, but the implementing agent must confirm).

9. **Run the regression net** as the final acceptance check: `docker exec the-one pytest -x --timeout 30 tests/test_connectors*.py` should pass byte-identically. Then the full suite.

## Edge Cases

- **`Permit()` identity vs. equality**: Two `Permit()` instances are equal (frozen-dataclass equality) but are NOT the same object. Consumers MUST compare with `==` / `isinstance`, not `is`. Documented in the `_default_permit` docstring.
- **Hashability of `NeedsPairing` / `Deny` with mutable `reason`**: `reason: str` is immutable. `frozen=True` + `slots=True` gives free hashability. No edge case here unless a future leg adds a mutable field — at which point `hash=False, compare=False` on that field (the `InboundEnvelope.raw` precedent).
- **Stub plugin's lack of `resolve`**: a `hasattr(stub, "resolve")` check returns `False`. The `getattr(stub, "resolve", _default_permit)` returns the `_default_permit` callable. Both consult sites in legs 2 and 3 will invoke it: `getattr(plugin, "resolve", _default_permit)(account, envelope)`. Test the equivalence explicitly (see test 4 above).
- **Future plugin's `resolve` raising**: NOT this leg's concern — the consult sites in legs 2 and 3 own the exception-catching contract (mirror `_session._derive_title`'s try/except). Leg 1a just defines the surface.
- **`_default_permit` accepting unused parameters**: keep the signature `(account, envelope)` even though the body ignores both. The signature matches what real `resolve` implementations have, so the `getattr` fallback is type-equivalent at the consult site.
- **Docstring drift in `agents.md`**: the file is large; sed/grep carefully to ensure only the four cited lines + the convention-block append (L96-100) change. F7 `CommandHandler` predictions are preserved (`base.py:12,225`, `README.md:30,84`, `agents.md:337` UNTOUCHED). The exception is `agents.md:339` — one of its two `CommandHandler` mentions (the one bundled into the `Plugin + AllowlistResolver + CommandHandler` list) is reframed alongside the `AllowlistResolver` removal; the surrounding structural-satisfaction prose still mentions `CommandHandler`. Post-edit `grep -n "CommandHandler" the_one/agents.md` returns `{337, 339}` (same two lines) but L339's hit-count goes from 2 → 1. Post-edit `grep -c "CommandHandler" the_one/agents.md` decreases by exactly 1. The grep-line-set invariant holds; the grep-hit-count invariant does NOT — by design.
- **Test fixture imports**: `ConnectorAccount` requires several constructor fields (`id`, `name`, `type`, `config`, `secrets`, `created_at`, `updated_at`); grep existing tests for the conventional minimal-fixture shape. The `_default_permit` test does not exercise any account field; a stub-shaped account is fine.

## Files Affected

- `the_one/connectors/base.py` — add 3 dataclasses + 1 type alias + 1 callable; revise 2 docstring blocks
- `the_one/connectors/__init__.py` — re-export 4 public symbols
- `the_one/connectors/README.md` — append `resolve` entry to §4 "Optional hooks"
- `the_one/agents.md` — reframe 4 `AllowlistResolver` Protocol predictions + append one sentence to the `optional-plugin-hook-via-getattr-sentinel` convention block (L96-100)
- `tests/test_connectors_resolver.py` — NEW file (6 type-level surface tests per Implementation Guidance §8)
- `the_one/connectors/_stub.py` — UNCHANGED
- `the_one/connectors/_inbound.py` — UNCHANGED (leg 2 wires consult site)
- `the_one/tools/connector_send.py` — UNCHANGED (leg 3 wires the consult site AND updates the `# F6:` marker text; leg 3 also updates `connectors/README.md:363`'s quoted marker text)

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `completed` (in this file's header)
- [ ] Check off this leg in flight.md
- [ ] If final leg of flight: update flight.md status to `landed`, check off flight in mission.md
- [ ] Commit all changes together (code + artifacts)

> **Note**: Under the deferred-batched workflow for F6, the implementing
> Developer stops at `[HANDOFF:review-needed]` and does NOT commit. The
> Flight Director batches review + commit after the last autonomous leg.
> Leg status transitions to `landed` (not `completed`) at implementation
> end; the batched commit advances all legs to `completed`.

## Citation Audit

Citations verified against current code at leg design time (cycle-1 + cycle-2 design review):
- `the_one/connectors/base.py:11-15` — confirmed (Protocol-prediction docstring block)
- `the_one/connectors/base.py:222-227` — confirmed (ConnectorPlugin docstring with `AllowlistResolver` prediction; literal text on line 224)
- `the_one/connectors/README.md:29` — confirmed (`Future home of AllowlistResolver`)
- `the_one/connectors/README.md:82` — confirmed (Protocol-list line)
- `the_one/connectors/README.md:363` — confirmed (prose quoting the source-code marker; DEFERRED to leg 3)
- `the_one/agents.md:96-100` — confirmed (`optional-plugin-hook-via-getattr-sentinel` convention block; receives one-sentence append for the named-callable variation)
- `the_one/agents.md:306` — confirmed (prose describing the source-code marker; reframed in leg 1a)
- `the_one/agents.md:336` — confirmed (Protocol-list line; reframed)
- `the_one/agents.md:337` — confirmed (F7 `CommandHandler` parallel; UNTOUCHED)
- `the_one/agents.md:339` — confirmed (structural-satisfaction statement; reframed)
- `the_one/agents.md:361` — confirmed (`AllowlistResolver Protocol will layer ...` sentence; reframed)
- `the_one/connectors/_stub.py:209` — confirmed (`display_channel` precedent on the stub)
- `the_one/connectors/_session.py:90` — confirmed (`getattr(plugin, "display_channel", None)` precedent)
- `the_one/tools/connector_send.py:131` — confirmed (`# F6: AllowlistResolver consultation lands here` marker; DEFERRED to leg 3)
- `tests/_connector_dispatch_helpers.py:128` — confirmed (`_create_test_account` reference)
- `tests/_connector_dispatch_helpers.py:151-169` — confirmed (`_envelope` factory reference)
- `tests/test_connectors.py:210-219` — confirmed (inline minimal-fixture style)

All 14 citations verified clean. README:363 and connector_send.py:131 are explicitly deferred to leg 3 (the source-code marker change is leg 3's edit; the README quote follows).
