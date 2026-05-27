# Leg: discord-resolve-hook

**Status**: completed
**Flight**: [Pairing Resolution + Connectors-Screen Detach](../flight.md)

## Objective

Add a `resolve(account, envelope) -> ResolveOutcome` method to `DiscordPlugin` that returns `NeedsPairing` for DMs from peers not on `account.config["allowlist"]["peers"]`, and `Permit` for all other cases — making the F9 pending-approval branch reachable in the dispatcher.

## Context

**Why this leg.** Cycle-1 architect found that `DiscordPlugin` does not currently define `resolve`; the dispatcher at `the_one/connectors/_inbound.py:392` discovers it via `getattr(plugin, "resolve", _default_permit)` and falls through to `_default_permit` (returns `Permit()`). Today, unknown DMs reach `agent.step` directly — i.e., the F9 pending-approval emit point in `_inbound.py:410-449` is structurally unreachable for Discord. L1 fixes that by giving the Discord plugin a real resolver that flags DM-from-stranger.

**Design Decision §1 (operator-locked, DM-only)**: this hook returns `NeedsPairing` ONLY when (a) `envelope.raw["is_dm"]` is `True` AND (b) `envelope.peer_id` is not in `account.config["allowlist"]["peers"]`. Guild messages and already-allowlisted peers return `Permit`. Mission text aligns ("when an unknown user DMs the bot"); F7 mentions-aware gates the engagement decision for guild messages downstream at dispatcher step 11.5 (different concern).

**Pattern precedent.** `DiscordPlugin` already exposes `is_dm(envelope)` (line 1595) and `is_mention(envelope)` (line 1619) as optional plugin hooks discovered via `getattr` (the M10 `optional-plugin-hook-via-getattr-sentinel` convention). L1 follows the same convention shape — the method is added directly on `DiscordPlugin`; `_default_permit` remains the fallback for any other plugin (e.g. test stubs) that does not implement it. `resolve` is **synchronous** (matches `_default_permit`'s signature at `base.py:264` and the call site at `_inbound.py:393` which invokes it without `await`).

**Downstream contract preserved.** The L2 dispatcher extension reads the `NeedsPairing` branch in `_inbound.py:410-449`; L1 does not modify the dispatcher — the wiring is via the existing `getattr` discovery. Existing PAIR-prefix tests pass unchanged because the dispatcher's `_validate_pairing_prefix` call inside the NeedsPairing arm is preserved.

## Inputs

- `the_one/connectors/_discord.py:579` — `class DiscordPlugin:` declared but lacks a `resolve` method. `is_dm` (line 1595) and `is_mention` (line 1619) are already on the class as plugin hooks.
- `the_one/connectors/base.py:222-261` — `Permit`, `NeedsPairing`, `Deny` frozen dataclasses + `ResolveOutcome = Permit | NeedsPairing | Deny` union; `_default_permit` at `base.py:264` returns `Permit()`.
- `the_one/connectors/_inbound.py:392-393` — dispatcher resolver discovery: `resolver = getattr(plugin, "resolve", _default_permit); outcome = resolver(account, envelope)` (sync call).
- `ConnectorAccount.config["allowlist"]["peers"]` — list of platform-id strings; mutated by the dispatcher pairing-success path at `_inbound.py:428-438`. May be absent (older accounts); default to empty list.
- `envelope.raw["is_dm"]` — populated by `_discord_translate._translate_discord_message_to_envelope` (already shipped; the existing `is_dm` plugin method reads it via `raw.get("is_dm", False)`).
- `tests/test_connectors_discord.py` — existing test file for the Discord plugin (test patterns established for `is_alive`, `connect`, intents, presence).
- `tests/conftest.py` — fixture conventions; check for an existing Discord/InboundEnvelope fixture or build a minimal one inline.

## Outputs

- `the_one/connectors/_discord.py` — `DiscordPlugin.resolve(self, account, envelope) -> ResolveOutcome` added (synchronous; sits near `is_dm`/`is_mention` in the file).
- `tests/test_connectors_discord.py` — new unit tests covering the resolve hook's three observable branches (DM-from-stranger → NeedsPairing; DM-from-allowlisted → Permit; guild message → Permit). Plus malformed-envelope defensive cases parallel to the existing `is_dm`/`is_mention` patterns.

No production code outside `_discord.py` changes. No dispatcher change. No new imports outside the connector base ADT.

## Acceptance Criteria

- [ ] `DiscordPlugin` has a public `def resolve(self, account: ConnectorAccount, envelope: InboundEnvelope) -> ResolveOutcome` method.
- [ ] When `envelope.raw["is_dm"]` is `True` AND `envelope.peer_id` is NOT in `account.config["allowlist"]["peers"]`, the method returns `NeedsPairing(reason="discord_dm_unknown_peer")`. The reason literal is contractual — L2's pending-approval emit path and the existing dispatcher audit-log entry both rely on a stable, greppable value. Pin it as written.
- [ ] When `envelope.raw["is_dm"]` is `True` AND `envelope.peer_id` IS in `account.config["allowlist"]["peers"]`, the method returns `Permit()`.
- [ ] When `envelope.raw["is_dm"]` is `False` (guild message), the method returns `Permit()` regardless of allowlist membership.
- [ ] Missing `account.config["allowlist"]` or missing `peers` key is treated as "no allowlist entries" — the DM-from-stranger branch fires (not a crash, not a Permit-by-default).
- [ ] Malformed `envelope.raw` (missing `is_dm` key) defaults to `is_dm=False` → `Permit()`, matching the existing `is_dm` method's defensive contract at `_discord.py:1602-1617`.
- [ ] New unit tests in `tests/test_connectors_discord.py` cover all five branches above and pass.
- [ ] Existing `tests/test_connectors_discord.py` tests pass unchanged.
- [ ] Existing pairing tests (`tests/test_pairing_prefix.py`) pass unchanged.
- [ ] Existing dispatcher tests (`tests/test_connectors_inbound.py`) pass unchanged. **Expected outcome (verified at design time)**: dispatcher tests exercise `StubPlugin` / `StubPluginWithResolver`, not `DiscordPlugin`; grep shows zero `DiscordPlugin` references in the file. Breakage risk is essentially nil. The implementer still re-runs the suite per the cross-subsystem-pattern-premise-revalidation convention and **records the verification finding in the flight-log L1 entry** ("verified: zero `DiscordPlugin` references in `tests/test_connectors_inbound.py`; no fixes needed") whether or not any fix was made.

## Verification Steps

```bash
# Run new + existing Discord plugin tests
docker exec the-one pytest tests/test_connectors_discord.py -x --timeout 30 -v

# Run pairing prefix tests (must remain unchanged)
docker exec the-one pytest tests/test_pairing_prefix.py -x --timeout 30 -v

# Run dispatcher tests (audit for any prior-behavior coupling to _default_permit-for-Discord)
docker exec the-one pytest tests/test_connectors_inbound.py -x --timeout 30 -v

# Quick scan: ensure the new method is exported via class attributes (not inadvertently in a helper module)
grep -n "def resolve" the_one/connectors/_discord.py
```

Expected: all three test suites green; `grep` shows exactly one new `def resolve` inside `DiscordPlugin`.

## Implementation Guidance

1. **Inspect existing dispatcher tests for prior coupling to `_default_permit`-via-Discord** (cross-subsystem-pattern-premise-revalidation convention). Grep `tests/test_connectors_inbound.py` for `DiscordPlugin`. Design-time expectation: zero matches; dispatcher tests use `StubPlugin` / `StubPluginWithResolver`. If a match exists (i.e., reality drifted between leg design and leg implementation), update the test either to use a stub plugin without `resolve` OR to add the test peer to `account.config["allowlist"]["peers"]`. Record the inspection result in the flight-log L1 entry whether the grep was empty or surprised us.

2. **Add the `resolve` method to `DiscordPlugin`** in `the_one/connectors/_discord.py`. Sit it adjacent to `is_dm` (line 1595) and `is_mention` (line 1619) — same optional-plugin-hook family.

   ```python
   def resolve(
       self,
       account: ConnectorAccount,
       envelope: InboundEnvelope,
   ) -> ResolveOutcome:
       """Discord resolver: DM-from-stranger gates on pairing/approval.

       F9 L1 (M11 mission 11). Returns ``NeedsPairing`` ONLY when the
       envelope is a DM AND the peer is not in
       ``account.config["allowlist"]["peers"]``. Guild messages and
       already-allowlisted peers return ``Permit``. Scope is DM-only
       per F9 §1 design decision; guild-mention scoping is deferred to
       a future flight.

       The dispatcher (``_inbound.py:392``) discovers this method via
       ``getattr(plugin, "resolve", _default_permit)`` and consults its
       outcome at dispatcher step 6, BEFORE routing and the per-session
       lock. The downstream ``NeedsPairing`` arm handles PAIR-prefix
       validation; F9 L2 extends that arm with the pending-approval
       emit path.
       """
       is_dm = bool(envelope.raw.get("is_dm", False))
       if not is_dm:
           return Permit()
       allowlist = account.config.get("allowlist") or {}
       peers = allowlist.get("peers") or []
       if envelope.peer_id in peers:
           return Permit()
       return NeedsPairing(reason="discord_dm_unknown_peer")
   ```

   The literal reason `"discord_dm_unknown_peer"` is contractual (per AC #2) — pin it as written; L2 will grep for it.

3. **Import `Permit`, `NeedsPairing`, `ResolveOutcome` from `.base`** by extending the existing `from the_one.connectors.base import (...)` block at `_discord.py:62-74`. (Currently imports `InboundEnvelope`, `OutboundTarget`, `SendResult`, etc.; add the three new symbols alphabetically in-block.)

4. **Write unit tests** in `tests/test_connectors_discord.py`. Tests should NOT instantiate the full Discord SDK and should NOT use `_make_account` (line 380, encryptor-bound, secrets-touching, overkill for a pure resolver test).

   **Envelope construction**: extend the existing `_dm_test_envelope(raw)` helper at `tests/test_connectors_discord.py:1290` to accept an optional `peer_id="peer-1"` kwarg, OR add a sibling `_resolve_test_envelope(raw, peer_id)` adjacent to it. Pick whichever minimizes diff; do NOT duplicate near-identical fixture code.

   **Account construction**: inline. `ConnectorAccount(id="acc-1", name="...", type="discord", config={"allowlist": {"peers": [...]}})` — resolve does not read `secrets`, so omit that field entirely (let the dataclass default apply, or pass `secrets={}` if the dataclass requires it). The `peers` list contents drive the branch under test (`["peer-1"]` for allowlisted; `[]` or missing key for stranger).

   Required test cases (one test function each):
   - `test_resolve_dm_from_stranger_returns_needs_pairing`
   - `test_resolve_dm_from_allowlisted_peer_returns_permit`
   - `test_resolve_guild_message_returns_permit_regardless_of_allowlist`
   - `test_resolve_missing_allowlist_treats_as_empty_returns_needs_pairing_for_dm`
   - `test_resolve_missing_is_dm_key_defaults_to_permit`

   The `NeedsPairing(reason=...)` assertion in `test_resolve_dm_from_stranger_returns_needs_pairing` MUST pin the literal `"discord_dm_unknown_peer"` (per AC #2).

5. **Run tests with the discipline from the phase file**: `docker exec the-one pytest tests/test_connectors_discord.py -x --timeout 30`. Use `-x` to bail on first failure and `--timeout 30` to prevent any hangs.

6. **Re-confirm dispatcher tests pass** (criterion #9 above). Design-time expectation: clean run (no DiscordPlugin references in `tests/test_connectors_inbound.py`). If a test breaks, fix in-leg: swap to a non-Discord stub plugin OR add the test peer to the account's allowlist. Document the outcome (clean or fixed) in the flight-log L1 entry.

7. **Update flight-log.md** with an L1 entry under "Leg Progress" — list the changes made (file:line touched), the cross-subsystem inspection result from step 1 (record even if empty), and any dispatcher-test outcome from step 6.

8. **Update leg status** to `landed` (NOT `completed`; the commit is deferred to Phase 2d per the agentic-workflow's batch-commit posture). Do NOT signal `[COMPLETE:leg]`. Do NOT commit. Signal `[HANDOFF:review-needed]` when implementation is done — Flight Director routes review at Phase 2d.

## Edge Cases

- **`account.config` is `None`**: not expected (the DB enforces config-shape via the account constructor), but defensively `account.config or {}` covers it. Optional: skip — the DB invariant is the contract.
- **`account.config["allowlist"]` exists but is `None`** (vs. missing key): the `account.config.get("allowlist") or {}` idiom in step 2 handles both shapes.
- **`peers` value is not a list** (e.g. string): defensively coerce — `allowlist.get("peers") or []` returns `[]` for `None` but lets a string through. Treat anything non-list as empty (the DB shape is `list[str]`; non-list arrival means data corruption, not normal traffic). Pick: tighten to `isinstance(peers, list)` check OR trust the DB invariant. Default: trust DB invariant; do NOT add an `isinstance` check (over-defensive; mission's M10 `cross-subsystem-pattern-premise-revalidation` convention notwithstanding — this is single-subsystem).
- **`envelope.peer_id` is `None`**: not reachable. `InboundEnvelope.peer_id: str` is non-optional per the dataclass at `the_one/connectors/base.py:72` — no None-handling needed.
- **Bot itself DMs the bot** (sender_id == bot_id): not addressable here — `_discord_translate` should filter self-messages before they reach the dispatcher. If it doesn't, that's a different bug; this leg does NOT bear the burden of handling it.
- **Allowlist contains the peer but with a different id shape** (e.g. integer vs string): treat as "not in list" — `peer_id` is a string per the envelope contract; allowlist entries are strings per the dispatcher's `peers.append(envelope.peer_id)` write path at `_inbound.py:434`. Any mismatch is data corruption (same disposition as above).

## Files Affected

- `the_one/connectors/_discord.py` — add `resolve` method on `DiscordPlugin` (sits near line 1595, adjacent to `is_dm`/`is_mention`). Possibly add `Permit, NeedsPairing, ResolveOutcome` to the `.base` import line if missing.
- `tests/test_connectors_discord.py` — five new test functions.
- `tests/test_connectors_inbound.py` — possible defensive fixups if existing tests assumed `_default_permit` semantics for Discord DMs; document any change in the flight-log.
- `missions/11-discord-connector-depth/flights/09-pairing-resolution-and-detach/flight-log.md` — append L1 progress entry.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified (run the three `pytest` commands above; all green)
- [ ] Tests passing (new + existing)
- [ ] Update flight-log.md with L1 progress entry (changes made, inspection notes, any defensive test fixups)
- [ ] Set this leg's status to `landed` (in this file's header)
- [ ] Do NOT check off this leg in flight.md (deferred to Phase 2d commit)
- [ ] Do NOT commit (deferred to Phase 2d batch commit)
- [ ] Signal `[HANDOFF:review-needed]` to the Flight Director

## Citation Audit

5 citations verified against current code at leg design time:
- `the_one/connectors/_discord.py:579` (`class DiscordPlugin:`) — OK
- `the_one/connectors/_discord.py:1595` (`def is_dm`) — OK
- `the_one/connectors/_discord.py:1619` (`def is_mention`) — OK
- `the_one/connectors/_inbound.py:392-393` (resolver discovery + sync call) — OK
- `the_one/connectors/base.py:222-261` (Permit/NeedsPairing/Deny/ResolveOutcome) — OK; `_default_permit` at `base.py:264` returns `Permit()` — OK.
