# Leg: discord-doctor-probe

**Status**: completed
**Flight**: [First Real Connector — Discord](../flight.md)

## Objective

Implement `DiscordPlugin.doctor(account, encryptor) -> DoctorReport` — currently raises `NotImplementedError`. Run five checks against the operator's Discord credentials WITHOUT dispatching any messages to peers:
1. **Token validity** — HTTP GET `https://discord.com/api/v10/users/@me` with `Authorization: Bot <token>`; expect 200 + bot user JSON.
2. **Application summary** — HTTP GET `https://discord.com/api/v10/oauth2/applications/@me`; expect 200 + app metadata (bot name, app id, owner).
3. **Intent coverage** — parse the application's `flags` field for `GATEWAY_MESSAGE_CONTENT_LIMITED` / `GATEWAY_GUILD_MEMBERS_LIMITED` bits; verify the bot is approved for Message Content and Guild Members intents.
4. **Gateway-connect smoke test** — open a SHORT-LIVED `discord.Client` session, await on_ready with a 30s timeout, close immediately. Confirms the token authenticates against the gateway and the intents are actually deliverable.
5. **Allowlist resolution** — for each `guild_id` in `account.config["allowlist"]["guilds"]` (if any): GET `https://discord.com/api/v10/guilds/{id}/members/{bot_user_id}`; expect 200 (bot is a member). Returns the list of unreachable guilds in `details["unreachable_guilds"]`.

Return `DoctorReport(status="ok"|"degraded"|"failed", message=..., details=...)` in the M07 inspector shape. Pass the live `encryptor` reference (do NOT capture a snapshot) per the encryption-rotation invariant.

## Context

L7 of F8. Per flight Design Decisions:

- **Doctor parallels M07 MCP inspector shape**: status ∈ {ok, degraded, failed}; one-sentence `message`; structured `details` dict for the admin UI's expanded view. Failure paths surface per-check status under `details["checks"]`.
- **Five checks, three pass/fail categories**:
  - `ok` — all five checks pass.
  - `degraded` — token valid AND gateway connects, but allowlist-resolution surfaces unreachable guilds OR intent coverage is partial (only one of MC/GM, not both).
  - `failed` — token invalid (401) OR gateway connect fails OR application metadata unreachable.
- **No message dispatch** — the probe is read-only at the platform side. The gateway smoke test connects-and-disconnects without sending any messages.
- **Live `encryptor` reference** — the `doctor` body decrypts `account.secrets["BOT_TOKEN"]` AT CALL TIME via the passed-in `encryptor`. Plaintext is not retained past the HTTP calls.
- **L8 allowlist axes extension lands AFTER L7** — the L8 guilds/roles axes don't exist yet when L7 implements. L7's allowlist-resolution check probes `account.config.get("allowlist", {}).get("guilds", [])` defensively — empty/absent guilds list means the check returns OK with no probes.

Key learnings from L1-L6:
- L3 already imports `discord` and `discord.errors` — L7 can reuse the same import patterns.
- L6 added `_default_not_dm` to `_acl.py` and codified `is_dm` as the third `optional-plugin-hook-via-getattr-sentinel` occurrence — no impact on L7.
- L5 mapped Discord HTTP errors to typed connector errors — L7 reuses that mapping for HTTP probes (Forbidden → "bot missing scope"; NotFound → "guild not joined"; HTTPException 401 → "token invalid").

## Inputs

- `the_one/connectors/_discord.py` (post-L6) — `DiscordPlugin` has 5 implemented methods + `doctor` raising `NotImplementedError`.
- `the_one/connectors/_stub.py:184-198` — `StubPlugin.doctor(account, encryptor) -> DoctorReport` signature precedent.
- `the_one/connectors/base.py:117-145` — `DoctorReport` dataclass with `status: Literal["ok", "degraded", "failed"]`, `message: str`, `details: dict[str, Any]`.
- `the_one/encryption.py:Encryptor.decrypt(...)` — the contract.
- `discord.py 2.4+` SDK — provides `discord.Client` for the gateway smoke test; provides `discord.http.HTTPClient` if direct REST is needed but `aiohttp` directly is simpler for read-only probes.
- L1-L6 test suite green (2331 passed).

## Outputs

- `DiscordPlugin.doctor(account, encryptor) -> DoctorReport` in `_discord.py`:
  - Helper structure: `_probe_token_valid`, `_probe_application_summary`, `_probe_intent_coverage`, `_probe_gateway_connect`, `_probe_allowlist_resolution` — each returns a per-check sub-result dict `{status, message, ...}` that the parent aggregates into the final `DoctorReport`.
  - HTTP probes use `aiohttp.ClientSession()` (already pulled in by discord.py); pass `headers={"Authorization": f"Bot {token}"}`.
  - Gateway smoke test: construct a fresh `discord.Client(intents=intents_with_MC_GM)`, `client.login(token)` + `await asyncio.wait_for(client.connect(), timeout=30)` watching for the `on_ready` event via an asyncio.Event; on event, `await client.close()`. The smoke test does NOT register an on_message handler.
  - Aggregation: if any of the FIRST THREE checks (token, app, intents) fails → `status="failed"`. If checks 4 (gateway) fails → `status="failed"`. If check 5 (allowlist) surfaces unreachable guilds → `status="degraded"`. Else → `status="ok"`.
  - `message` is one sentence summarizing the outcome (e.g. "Discord probe ok"; "Discord probe failed: token authentication 401"; "Discord probe degraded: 2 of 3 configured guilds are unreachable").
  - `details` is a dict with per-check sub-results plus aggregated fields: `{checks: {token, application, intents, gateway, allowlist}, application_id, bot_user_id, bot_username, unreachable_guilds: list[str]}`.

- `tests/test_connectors_discord.py` extended with doctor tests:
  - Happy path: all five checks pass → `status="ok"`, `message="Discord probe ok"`.
  - Token invalid (HTTP 401) → `status="failed"`.
  - Intent not approved (flags bit not set) → `status="failed"`.
  - Gateway smoke test times out → `status="failed"`.
  - Allowlist guild unreachable (HTTP 404 on `/guilds/{id}/members/{bot}`) → `status="degraded"` with `unreachable_guilds` populated.
  - Empty allowlist (no guilds configured) → allowlist check skipped; if 1-4 pass → `status="ok"`.
  - Encryptor decrypt fails → propagate (the F4 tool / Admin doctor route catches and surfaces as `failed`).
  - Encryptor is the LIVE reference (test pins: doctor reads encryptor via parameter, NOT captures at construction).

- L1-L6 regression: 2331 → ~2340 (~8 new tests).

## Acceptance Criteria

- [ ] **`DiscordPlugin.doctor(account, encryptor) -> DoctorReport`** implemented. Async. 5 probe sub-functions (one per check). Aggregates into a single `DoctorReport`.

- [ ] **Token-valid check**: aiohttp GET `https://discord.com/api/v10/users/@me` with `Bot <token>` header. 200 → ok with bot user metadata captured. 401 → failed. Other → degraded with status code in message.

- [ ] **Application-summary check**: aiohttp GET `https://discord.com/api/v10/oauth2/applications/@me` with `Bot <token>` header. 200 → ok; capture `id`, `name`, `flags`. 401/404 → failed. Other → degraded.

- [ ] **Intent-coverage check**: parse `flags` bitfield from the application response. Message Content intent bit is `GATEWAY_MESSAGE_CONTENT` (bit 18 / value `1 << 18` = 262144); Guild Members is `GATEWAY_GUILD_MEMBERS` (bit 14 / value `1 << 14` = 16384). Both required → ok. One missing → degraded with the missing intent in message. Both missing → failed.

- [ ] **Gateway-connect smoke test**: short-lived `discord.Client` session. `client.login(token)` + connection task spawned + asyncio.Event waits for `on_ready` with 30s timeout. `client.close()` immediately after. Returns ok on success; failed on timeout / connect exception. Test uses a stubbed discord module (no real connection).

- [ ] **Allowlist-resolution check**: read `account.config.get("allowlist", {}).get("guilds", [])`. For each guild_id: aiohttp GET `https://discord.com/api/v10/guilds/{id}/members/{bot_user_id}`. 200 → guild reachable. 403/404 → unreachable. Returns degraded if any unreachable; ok if all reachable or list is empty.

- [ ] **Aggregation**: status priority — failed > degraded > ok. First check failure short-circuits subsequent checks (efficiency + don't surface cascaded failures). Specifically:
  - If token check fails → return failed (don't run app, intent, gateway, allowlist).
  - If app check fails → return failed (don't run intent, gateway, allowlist).
  - If intent fails → return failed (don't run gateway, allowlist).
  - If gateway fails → return failed (don't run allowlist).
  - If allowlist has unreachable guilds → return degraded.
  - All pass → ok.

- [ ] **`message` is one sentence** suitable for the admin UI's inline status field; matches the M07 mcp-inspector convention.

- [ ] **`details` is structured** with `{checks: {<probe_name>: {status, ...}, ...}, application_id, bot_user_id, bot_username, unreachable_guilds}`. The admin UI's expanded view reads from this structure.

- [ ] **Live encryptor reference**: `doctor` receives `encryptor` as a parameter at every call. Does NOT capture at plugin construction. Pin with a test: rotate the encryptor between calls; the second call uses the new key without recomputing.

- [ ] **Read-only — no message dispatch**: doctor sends no platform messages. Test pins: stubbed gateway records connect-then-close; no `channel.send` calls observed.

- [ ] **Tests in `tests/test_connectors_discord.py`** — at least 7 new doctor tests covering: happy, 401, missing intent, gateway timeout, allowlist unreachable, empty allowlist, encryptor live-reference.

- [ ] **F1-F7 + L1-L6 regression**: 2331 → ~2340.

## Verification Steps

- `grep -c "async def doctor" the_one/connectors/_discord.py` — exactly 1 (the doctor method).
- `grep -c "users/@me\|oauth2/applications/@me\|/guilds/" the_one/connectors/_discord.py` — at least 3 (one per HTTP probe).
- `docker exec the-one pytest tests/test_connectors_discord.py -x --timeout 30` — all pass.
- `docker exec the-one pytest tests/ -x --timeout 30` — full suite passes.

## Implementation Guidance

1. Build the 5 probe helper functions independently (each takes `(token, ...)` or `(client, ...)` and returns a sub-result dict).
2. Build the aggregator in `DiscordPlugin.doctor`.
3. Tests: extend the existing stubbed `discord` module pattern from L3-L5. For aiohttp, use `aiohttp.ClientSession` mocking — either via `aiohttp_mock` library if available, or by patching `aiohttp.ClientSession` at the module level.
4. Run tests; fix.
5. Update flight log; mark leg landed.

### Code patterns to follow

- **`StubPlugin.doctor` at `_stub.py:184-198`** — signature precedent.
- **`DoctorReport` shape from M07 MCP inspector** — `status: Literal["ok", "degraded", "failed"]`, `message: str`, `details: dict`.
- **HTTP probe via aiohttp** — discord.py already uses aiohttp internally; reuse the dependency.
- **Live encryptor reference** — `agents.md:128` ("The repository stores the `Encryptor` as a reference, not a copy") is the precedent.

## Edge Cases

- **Bot is in a private guild that gates `GET /guilds/{id}/members`**: 403 — treat as unreachable.
- **`account.config["allowlist"]` is None or missing**: skip the allowlist-resolution check entirely. No probes; check status ok.
- **`account.config["allowlist"]["guilds"]` is an empty list**: skip. No probes; ok.
- **Gateway smoke test connects but `on_ready` never fires** (large guild chunking, weird network): the 30s timeout catches it; report `failed`.
- **`account.secrets["BOT_TOKEN"]` is missing or empty**: `Encryptor.decrypt` raises or returns empty; the token check sees a 401-shaped failure; report `failed`.
- **Discord API rate-limits the doctor probe** (429): the operator's probe path is low-volume; treat as transient. Report `degraded` with the retry-after hint in the message.
- **`/users/@me` returns 200 but missing `id` field** (malformed Discord response — shouldn't happen): defensive — report `degraded`.

## Files Affected

- `the_one/connectors/_discord.py` — `DiscordPlugin.doctor` body + 5 probe helpers + imports (aiohttp)
- `tests/test_connectors_discord.py` — extended with 7+ doctor tests

---

## Post-Completion Checklist

- [ ] All acceptance criteria verified
- [ ] Tests passing
- [ ] Update flight-log.md with leg progress entry
- [ ] Set leg status to `landed`
- [ ] Check off L7 in flight.md
- [ ] Do NOT commit — wait for flight-level review

## Citation Audit

- `the_one/connectors/_stub.py:184-198` — StubPlugin.doctor signature precedent — **OK**
- `the_one/connectors/base.py:117-145` — DoctorReport dataclass — **OK**
- `the_one/connectors/_discord.py:doctor (post-L6)` — currently NotImplementedError — **OK**
- `the_one/encryption.py:Encryptor` — live-reference pattern — exists per F1 (precedent at `agents.md:128`)

4 citations verified.
