# Leg: probe-gateway-intents-config-driven

**Status**: landed
**Flight**: [Pool-Keying Refactor + Per-Account System-Prompt Directive Surface](../flight.md)

## Objective

Lift the hardcoded intents in `the_one/connectors/_discord.py:_probe_gateway_connect` (the doctor probe's gateway-connect smoke test) to read from `account.config["intents"]` with byte-identical fallback to F1 L2's `DiscordPlugin.connect` shape. Closes the F1 L2 known gap (one remaining hardcoded-intents site outside L2's scope) so the doctor probe tests against the same intents the production connect path will use.

## Context

- **Why now**: F1 L7 flight-log noted the gap: "one hit at line 1421" remaining after F1 L2 refactored only the `connect()` site. F1 debrief recommendation R3 flagged this for "M11 F2 or F10." F2 owns it because we're already inside the connector substrate this flight.
- **Why it matters**: today the probe uses hardcoded intents (`message_content=True, members=True, guilds=True`), but `connect()` reads from `account.config["intents"]` with the same defaults. If an operator has explicitly disabled `message_content` in config, the probe-says-OK result is misleading — `connect()` will silently receive no channel messages while the probe succeeded with full intents. Lift closes the divergence.
- **Byte-identical fallback shape** (F1 L2 precedent): `intents_cfg = account.config.get("intents", {}); intents.<axis> = intents_cfg.get("<axis>", True)`. Existing M10 F8 accounts (no `config["intents"]` key) round-trip with all three intents True — byte-identical to today's probe behavior.
- **Signature change**: `_probe_gateway_connect` currently receives only `token: str`. It needs `account: ConnectorAccount` (or just the `intents_cfg` dict) to read the per-account intents. The static method is called once from `DiscordPlugin.doctor` at `_discord.py:1171` — single call site, atomic update.

### Design Decisions (L5-internal)

- **Signature shape — pass `account`, not `intents_cfg`**: the static method currently takes `token: str`. Two extension options:
  - (a) Add `account: ConnectorAccount` as a second positional arg; the body reads `account.config.get("intents", {})` and `account.secrets["BOT_TOKEN"]` for the token (eliminating the separate `token` param). Cleaner call-site at `doctor()`.
  - (b) Add `intents_cfg: dict | None` as a second positional arg; caller computes `account.config.get("intents", {})` and passes it in. Keeps the static method narrow.
  - **Chosen**: (b) — keeps `_probe_gateway_connect`'s shape as a pure spawn-a-client + await-ready helper that doesn't reach into the full account. The doctor method already has `account` in scope (it's the method's first arg); it reads `account.config.get("intents", {})` once and passes `intents_cfg` to the probe. This matches F1 L2's plugin-side refactor shape (the production `connect()` reads `account.config.get("intents", {})` once and applies it in-line) — the probe just receives the already-resolved dict.

- **Static method or instance method?**: currently `@staticmethod`. The new `intents_cfg` param doesn't change that — still no `self` references in the body. Keep static. Caller at `_discord.py:1171` is `self._probe_gateway_connect(token)` — works either way.

- **`intents_cfg` shape contract**: caller passes `account.config.get("intents", {})` which is either an empty dict (M10 F8 accounts) or a `{message_content: bool, members: bool, guilds: bool}` triple (post-F1 L2 accounts; shape validated by F1 L2's API validator). The probe applies `.get("<axis>", True)` for each — same fallback shape as `connect()`.

- **No new WARNING log at the probe site**: F1 L2 added a WARNING log at `connect()` when `message_content` is False. The probe is a one-shot diagnostic, not the production listener; a second WARNING per probe-click would be log noise. The operator already sees the choice in the UI (F2 L4's textarea + disclosures). Skip the log at the probe site.

- **Test coverage**: pin the lift with one new test in `tests/test_connectors_discord.py`: `test_probe_gateway_intents_from_config_honored` — pass `intents_cfg = {message_content: False, members: True, guilds: True}` to the probe; assert the underlying `discord.Client`'s `_intents` has the same shape. Mirrors F1 L2's `test_intents_from_config_honored` test pattern but on the probe path instead of the connect path.

## Inputs

Files that must exist:
- `the_one/connectors/_discord.py` — `:_probe_gateway_connect` static method (line ~1411) + the single call site at `:doctor` (line ~1171)
- `tests/test_connectors_discord.py` — existing test module; the new probe-intents test extends the existing pattern (F1 L2 shipped a `test_intents_from_config_honored` for `connect()`)

State that must be true:
- F2 L1, L2, L3, L4 are `landed`
- F2 baseline (2827 from L4 ship) passes
- `account.config["intents"]` shape is validated by F1 L2's API validator (already shipped)

## Outputs

State changes after this leg:

- `the_one/connectors/_discord.py:_probe_gateway_connect`:
  - Signature changes from `_probe_gateway_connect(token: str)` to `_probe_gateway_connect(token: str, intents_cfg: dict[str, Any] | None = None)`. The `intents_cfg` default is `None` so any internal/test caller that doesn't pass it gets byte-identical legacy behavior (all-True intents).
  - Body lines 1420-1423 replaced:
    ```python
    intents = discord.Intents.default()
    # M11 F2 L5: read intents from per-account config with the same
    # fallback shape as DiscordPlugin.connect (F1 L2). Default None →
    # empty dict → all three intents True (M10 F8 byte-identical).
    cfg = intents_cfg or {}
    intents.message_content = cfg.get("message_content", True)
    intents.members = cfg.get("members", True)
    intents.guilds = cfg.get("guilds", True)
    ```
  - Docstring updated to mention the new `intents_cfg` param + the byte-identical fallback shape.

- `the_one/connectors/_discord.py:doctor` (single call site at line ~1171):
  - Change `gateway_result = await self._probe_gateway_connect(token)` to `gateway_result = await self._probe_gateway_connect(token, account.config.get("intents"))`.
  - One-line change; the `account` variable is already in scope.

- `tests/test_connectors_discord.py`:
  - Add `test_probe_gateway_intents_from_config_honored` — mirrors the existing `test_intents_from_config_honored` for the probe path. Patches the discord SDK, calls `_probe_gateway_connect(token, intents_cfg={"message_content": False, "members": True, "guilds": True})`, asserts the underlying `discord.Client`'s `_intents.message_content is False`, `.members is True`, `.guilds is True`.
  - Add `test_probe_gateway_intents_none_defaults_to_all_true` — calls `_probe_gateway_connect(token)` without `intents_cfg`; asserts all three intents True (byte-identical legacy behavior preserved).
  - Add `test_probe_gateway_intents_empty_dict_defaults_to_all_true` — calls with `intents_cfg={}`; asserts all three True (M10 F8 round-trip).

## Acceptance Criteria

- [ ] `_probe_gateway_connect` signature: `(token: str, intents_cfg: dict[str, Any] | None = None) -> dict[str, Any]`. Optional 2nd param defaults to None.
- [ ] Body reads intents from `intents_cfg` with `.get("<axis>", True)` per-axis fallback. `None` and `{}` produce all-three-True (byte-identical legacy).
- [ ] Hardcoded `intents.message_content = True; intents.members = True; intents.guilds = True` lines (current lines 1421-1423) REMOVED — verified by `grep -n "intents.message_content = True" the_one/connectors/_discord.py` returning ZERO hits (both `connect()` and `_probe_gateway_connect` now read from config post-L5).
- [ ] `doctor` call site updated: `await self._probe_gateway_connect(token, account.config.get("intents"))`. `account.config.get("intents")` returns the dict if present, None if absent — both consumed correctly by the probe.
- [ ] Three new tests in `tests/test_connectors_discord.py` pass: `test_probe_gateway_intents_from_config_honored`, `test_probe_gateway_intents_none_defaults_to_all_true`, `test_probe_gateway_intents_empty_dict_defaults_to_all_true`.
- [ ] Existing probe tests in `tests/test_connectors_discord.py` pass UNMODIFIED (any test that exercises `_probe_gateway_connect` with the old 1-arg signature gets the default `None` and produces all-True — byte-identical).
- [ ] No other source files modified. `git diff --name-only` shows only `_discord.py` + the test file + L5 leg/flight-log artifacts.
- [ ] Full suite at or above F2 L4's 2827 baseline + 3 new tests.

## Verification Steps

- `grep -n "intents.message_content = True" the_one/connectors/_discord.py` — at most 1 hit (the `connect()` site at ~631 — also config-driven post-F1 L2; actually this should be ZERO hits because both `connect()` and `_probe_gateway_connect` now read from config). Verify the count is right post-L5.
- `grep -n "intents_cfg" the_one/connectors/_discord.py` — ≥4 hits (signature, body's 3 axis reads).
- `grep -n "_probe_gateway_connect" the_one/connectors/_discord.py` — exactly 2 hits (definition + 1 call site at `doctor`).
- `docker exec the-one pytest -x --timeout 30 tests/test_connectors_discord.py` — all probe tests pass including the 3 new ones.
- `docker exec the-one pytest -x --timeout 30 -q -m "not pixel"` — full suite at or above F2 L4's 2827 + 3 new tests.

## Implementation Guidance

1. **Read the current `_probe_gateway_connect`** at `_discord.py:1411-end-of-function` (~80 lines). Identify the hardcoded intents block (lines 1420-1423) and the docstring (lines 1412-1419).

2. **Read the call site** at `_discord.py:1171`: `gateway_result = await self._probe_gateway_connect(token)`. Confirm `account` is in scope at this position (the `doctor` method's signature is `(self, account, encryptor)` — yes, `account` is in scope).

3. **Update the probe signature and body**:
   ```python
   @staticmethod
   async def _probe_gateway_connect(
       token: str,
       intents_cfg: dict[str, Any] | None = None,
   ) -> dict[str, Any]:
       """Open a short-lived gateway session; await on_ready with a 30s timeout.

       Constructs a fresh :class:`discord.Client` with intents read from
       ``intents_cfg`` (M11 F2 L5; mirrors :meth:`connect`'s F1 L2
       shape). ``intents_cfg=None`` / ``{}`` → all three intents True
       (M10 F8 byte-identical fallback). Registers ``on_ready`` only —
       NO ``on_message`` — so the probe dispatches no inbound traffic.
       Closes the SDK client (and awaits the connect task) regardless
       of outcome.
       """
       intents = discord.Intents.default()
       # M11 F2 L5: read intents from per-account config with the same
       # fallback shape as DiscordPlugin.connect (F1 L2). Default None →
       # empty dict → all three intents True (M10 F8 byte-identical).
       cfg = intents_cfg or {}
       intents.message_content = cfg.get("message_content", True)
       intents.members = cfg.get("members", True)
       intents.guilds = cfg.get("guilds", True)
       
       client = discord.Client(intents=intents)
       # ... rest of the function body UNCHANGED ...
   ```

4. **Update the `doctor` call site** at `_discord.py:1171`:
   ```python
   # M11 F2 L5: pass per-account intents so the probe tests against the
   # same intents connect() will use — closes the F1 L2 known gap where
   # probe-says-OK could mask a connect()-silently-receives-nothing case
   # when message_content is operator-disabled.
   gateway_result = await self._probe_gateway_connect(
       token, account.config.get("intents")
   )
   ```

5. **Add 3 new tests** in `tests/test_connectors_discord.py`. Locate the existing `test_intents_from_config_honored` test (F1 L2, line ~440) and add the new probe tests adjacent to it — they share the same `_patch_discord` fixture pattern. The probe is a static method that returns a `dict[str, Any]` (NOT a client), so tests cannot follow the F1 L2 pattern of reading `client._intents`. Instead, use the established `_StubDiscordClient.instances[-1].intents` access pattern (the stub at `tests/test_connectors_discord.py:_StubDiscordClient` captures every constructed instance in `instances`; F1 L2's `test_intent_construction` reads `instances[-1].intents` similarly at lines 574/596/619/642). Skeleton:
   ```python
   @pytest.mark.asyncio
   async def test_probe_gateway_intents_from_config_honored(
       monkeypatch: pytest.MonkeyPatch,
   ) -> None:
       """M11 F2 L5: probe reads intents from intents_cfg with fallback."""
       _patch_discord(monkeypatch)
       intents_cfg = {"message_content": False, "members": True, "guilds": True}
       await DiscordPlugin._probe_gateway_connect(
           "test-token", intents_cfg=intents_cfg
       )
       # Most recently constructed stub client carries the intents.
       last_intents = _StubDiscordClient.instances[-1].intents
       assert last_intents.message_content is False
       assert last_intents.members is True
       assert last_intents.guilds is True
   
   @pytest.mark.asyncio
   async def test_probe_gateway_intents_none_defaults_to_all_true(
       monkeypatch: pytest.MonkeyPatch,
   ) -> None:
       """M11 F2 L5: probe with intents_cfg=None → all True (byte-identical legacy)."""
       _patch_discord(monkeypatch)
       await DiscordPlugin._probe_gateway_connect("test-token")
       last_intents = _StubDiscordClient.instances[-1].intents
       assert last_intents.message_content is True
       assert last_intents.members is True
       assert last_intents.guilds is True
   
   @pytest.mark.asyncio
   async def test_probe_gateway_intents_empty_dict_defaults_to_all_true(
       monkeypatch: pytest.MonkeyPatch,
   ) -> None:
       """M11 F2 L5: probe with intents_cfg={} → all True (M10 F8 round-trip)."""
       _patch_discord(monkeypatch)
       await DiscordPlugin._probe_gateway_connect("test-token", intents_cfg={})
       last_intents = _StubDiscordClient.instances[-1].intents
       assert last_intents.message_content is True
       assert last_intents.members is True
       assert last_intents.guilds is True
   ```
   
   **Confirmed at cycle-1 review**: the stub's `intents` attribute is set per-instance at `_StubDiscordClient` constructor (line ~173); `instances[-1].intents` is the established access pattern used at lines 574, 596, 619, 642 in the existing connect-path tests. No stub extension needed.

6. **Run tests in order**:
   - `docker exec the-one pytest -x --timeout 30 tests/test_connectors_discord.py` — Discord plugin tests including 3 new probe tests
   - `docker exec the-one pytest -x --timeout 30 -q -m "not pixel"` — full suite final check

## Edge Cases

- **Existing probe-tests that call `_probe_gateway_connect(token)` without `intents_cfg`**: protected by the `None` default → byte-identical legacy behavior. No test rewrite needed.
- **`account.config["intents"]` shape malformed at the probe**: F1 L2's API validator enforces the shape at write time. The probe trusts the validator (per the L1-codified `trust-the-runtime` convention). If someone DB-edits malformed config, `.get("message_content", True)` on a non-dict raises `AttributeError` — the probe's existing exception handler catches and returns a failed-status diagnostic. Acceptable.
- **`account.config.get("intents")` returns None when key is absent**: the probe's `intents_cfg or {}` handles None gracefully. Empty dict produces all-True (byte-identical legacy).
- **The other hardcoded-intents site at `_discord.py:619-622` in `connect()`**: already config-driven post-F1 L2. L5 doesn't touch it.

## Files Affected

**Production source**:
- `the_one/connectors/_discord.py` — `_probe_gateway_connect` signature + body refactor + 1-line call-site update at `doctor`

**Tests**:
- `tests/test_connectors_discord.py` — 3 new probe-intents tests

**Flight artifacts**:
- `missions/11-discord-connector-depth/flights/02-pool-keying-and-directive-surface/flight-log.md` — Leg Progress entry
- `missions/11-discord-connector-depth/flights/02-pool-keying-and-directive-surface/legs/05-probe-gateway-intents-config-driven.md` — status transitions

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified
- [ ] All 3 new probe-intents tests pass
- [ ] All existing probe + connect tests in `test_connectors_discord.py` pass UNMODIFIED
- [ ] Full suite at or above F2 L4's 2827 + 3 new tests
- [ ] Update flight-log.md with Leg Progress entry
- [ ] Set this leg's status to `landed`
- [ ] Do NOT check off the leg in flight.md
- [ ] Do NOT commit

## Citation Audit

Citations verified at leg design time (2026-05-21, post-L4):

- `the_one/connectors/_discord.py:_probe_gateway_connect` — verified static method at line 1411; hardcoded intents at lines 1421-1423; docstring at lines 1412-1419 mentions the 3-intent shape currently.
- `the_one/connectors/_discord.py:doctor` call site at line 1171 — `gateway_result = await self._probe_gateway_connect(token)`; `account` in scope from the method signature.
- `the_one/connectors/_discord.py:DiscordPlugin.connect` (F1 L2 site) — config-driven at lines 631-642; reads `account.config.get("intents", {})` then per-axis `.get(axis, True)`. L5's probe mirror uses the same shape.
- `tests/test_connectors_discord.py:test_intents_from_config_honored` — F1 L2 test; pattern the new probe tests follow.
- `tests/test_connectors_discord.py:_StubDiscordClient` — fixture used by F1 L2 tests; impl agent verifies whether `last_intents` is exposed or extends the stub minimally if not.

Five citation clusters verified live against the post-L4 tree.
