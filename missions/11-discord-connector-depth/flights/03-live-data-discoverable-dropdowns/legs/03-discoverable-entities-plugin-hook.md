# Leg: discoverable-entities-plugin-hook

**Status**: completed
**Flight**: [Live-Data Discoverable Dropdowns](../flight.md)

## Objective

Land the substrate-side surface for live-data discoverable dropdowns: add the `DiscoverableEntity` + `DiscoverableEntities` frozen dataclasses to `the_one/connectors/base.py`, document `enumerate_discoverable_entities(client: ConnectorClient) -> DiscoverableEntities` as an OPTIONAL plugin hook discoverable via the `getattr` sentinel (per the L1-codified `optional-plugin-hook-via-getattr-sentinel` convention — **NOT** a Protocol widening), and implement the hook on `DiscordPlugin` by reading the live `discord.Client` view. Stub plugin remains intentionally unimplemented (fallback path). Unit tests in `tests/test_connectors_discord.py` pin both paths.

## Context

- Design Decision **Substrate plugin hook — optional via `optional-plugin-hook-via-getattr-sentinel` convention** (flight.md): the `class ConnectorPlugin(Protocol)` body stays at 4 required methods (`connect`, `disconnect`, `doctor`, `normalize_session_key`). The new hook lives ONLY in the module docstring + the plugin implementation. Consumers (L4 cache sweep + the Studio API endpoints) consult via `getattr(plugin, "enumerate_discoverable_entities", None)` with `None` as the fallback sentinel.
- Design Decision **Signature: `client: ConnectorClient`** (the wrapper, not the raw SDK type) — Discord's implementation type-narrows from `ConnectorClient` to `DiscordClient` internally via `cast(DiscordClient, client)` (the established precedent at `_discord.py:1068`, where `disconnect` uses the same pattern). `cast` is already imported at `_discord.py:55`. The plugin then reaches into `DiscordClient._client` for the live `discord.Client` view, per the existing `_client`-access practice (cf. `_user` capture at L350 and `disconnect` at L1068). Future Slack/Matrix plugins receive the wrapper they already manage; substrate-neutral.
- Design Decision **Hook signature is SYNC** (`def enumerate_discoverable_entities(...) -> DiscoverableEntities`, not `async def`). Discord's reads are cache-only sync (`Client.users`, `Client.guilds`, `Client.get_all_channels()`, `Guild.roles` are all in-memory data the SDK gateway listener populated). The L4 cache sweep is an asyncio task; it can call the sync hook directly without `await`. Future Slack/Matrix plugins fetching via REST would need an async variant — but rather than forcing every plugin into async to accommodate the hypothetical, the substrate keeps the contract sync at this leg; an additive `enumerate_discoverable_entities_async` hook can be discovered alongside the sync one if/when a plugin needs it. Justification: keep the simpler contract for the only F3 implementer; widen additively when a real second consumer surfaces.
- Design Decision **Channel scope** — the Discord implementation emits ALL `GuildChannel`s from `client.get_all_channels()` (TextChannel, VoiceChannel, CategoryChannel, ForumChannel, StageChannel — all subclasses), with `metadata["type"]` carrying the channel-type token (e.g. `"text"`, `"voice"`, `"category"`, `"forum"`, `"stage"`) so L5/L6 can filter to text-postable channels at the render layer. Thread channels (`Guild.threads`) are NOT included in this leg — Threads are not `GuildChannel`s (verified against discord.py 2.4.0 `Thread.__mro__`), and the L6 routing/allowlist surfaces don't require them yet. F3 explicitly defers thread-target discoverability to a future leg.
- Design Decision **`fetched_at` format** — stdlib `datetime.now(UTC).isoformat()` emits the `+00:00` offset form (e.g. `2026-05-22T12:42:24.527680+00:00`). The substrate stays with this default — both `+00:00` and `Z`-suffix are valid ISO 8601, and downstream consumers (L4 API JSON-serialization; L5 frontend) can transform if needed. No `.replace("+00:00", "Z")` at the substrate layer.
- Design Decision **`DiscoverableEntities` shape** — single structured return per `agents.md`'s convention for hook return values:
  - `DiscoverableEntity { id: str; label: str; group: str | None = None; metadata: dict[str, Any] = {} }`
  - `DiscoverableEntities { peers: list[DiscoverableEntity]; channels: list[DiscoverableEntity]; groups: list[DiscoverableEntity]; roles: list[DiscoverableEntity]; fetched_at: str }`
- Design Decision **Substrate vocabulary**: the four axis names are `peers`/`channels`/`groups`/`roles` at the storage and API layers (matching the existing `account.config.allowlist` shape). Discord's plugin returns peers labeled `@username`, channels labeled `#channel-name`, groups labeled by guild name, roles labeled by role name. Vocabulary substitution to "users / servers" happens at the Studio render layer in L6 — NOT at this substrate layer.
- Codebase recon (verified at design review):
  - `the_one/connectors/base.py`: `ConnectorPlugin` Protocol body at L278-355 has 4 required methods. OPTIONAL hooks documented in the module docstring at L1-27 (`resolve` at L11-16; `display_channel` referenced at L15). `_default_permit` fallback function at L216 is the precedent for documented fallback functions, but the new hook does NOT need a fallback function — `None` returned by `getattr(plugin, "enumerate_discoverable_entities", None)` is the sentinel itself (consumer checks `if hook is None: …`).
  - `the_one/connectors/_discord.py`: `DiscordClient` class at L306+; `_client: discord.Client` set at L341, `_user` captured at L350 with the inline `# Captured at READY by the on_ready handler…` comment that documents the deliberate SDK boundary breach. `_DiscordPlugin` at L575+ with `connect` (L587), `disconnect` (L1053), `doctor` (L1070), `is_dm` (L1591 — optional hook), `handle_command` (L1615 — optional hook from a separate Protocol), `normalize_session_key` (L1656). No current direct access to `client.guilds` / `client.users` / `client.get_all_channels()` / `guild.roles` — this leg is the first to read those collections.
  - `the_one/connectors/_stub.py`: `StubPlugin` at L72-207. Implements 4 required + `display_channel` (L209). Does NOT implement `resolve` / `is_dm` / `handle_command`. This leg explicitly does NOT add `enumerate_discoverable_entities` to `StubPlugin` — the stub-doesn't path is the fallback contract the test pins.
  - `tests/test_connectors_discord.py`: pattern uses inline SDK type stubs (`_StubIntents`, `_StubActivityType`, `_StubChannelType`, `_StubActivity` at L51-99); monkeypatches `the_one.connectors._discord.discord` at consumer-import site.
  - Hook name `enumerate_discoverable_entities` is fresh — grep returns zero hits across the codebase.
- L1's two new conventions (`primitive-rename-test-classification`, `flight-spec-dom-order-audit`) are referenceable here but do not constrain this leg's design.
- F1 L1's `optional-plugin-hook-via-getattr-sentinel` IS the binding convention. F1's `optional-registry-entry-hook` is the JavaScript-side cousin (registry-entry shape); the Python plugin pattern is `getattr(plugin, "name", sentinel)`.

## Inputs

- `the_one/connectors/base.py` exists with `ConnectorPlugin` Protocol at L278+ and the established typed-export region (InboundEnvelope, OutboundTarget, SessionKey, DoctorReport, SendResult, Permit/NeedsPairing/Deny, CommandResponse).
- `the_one/connectors/_discord.py` exists with `DiscordClient` + `DiscordPlugin`.
- `the_one/connectors/_stub.py` exists with `StubPlugin`.
- `tests/test_connectors_discord.py` exists with the inline-SDK-stub pattern.
- F3 L1 (agents.md codifications) and L2 (test-connection-button triage) have landed in the working tree.

## Outputs

- `the_one/connectors/base.py` grows:
  - Two new frozen dataclasses: `DiscoverableEntity` and `DiscoverableEntities`, inserted at the blank line between `CommandResponse` (ends L376) and the `@runtime_checkable` decorator of `CommandHandler` (L378) — i.e., insert at L377. This preserves the "dataclass exports clustered before each Protocol" rhythm. Walk verified at design review.
  - Module docstring extension: document `enumerate_discoverable_entities` as the 3rd-listed OPTIONAL hook, matching the existing `resolve` + `display_channel` lines at L11-16. Brief language: "Connectors that can enumerate the platform entities the bot has live visibility into (users, channels, guilds, roles) implement the OPTIONAL `enumerate_discoverable_entities(client) -> DiscoverableEntities` hook (introduced by flight 3 of mission 11). Discovered via `getattr(plugin, "enumerate_discoverable_entities", None)`; consumers fall back to the chip-list editor when the hook is absent." Cross-reference the L1-codified convention.
- `the_one/connectors/_discord.py` grows:
  - `_DiscordPlugin.enumerate_discoverable_entities(self, client: ConnectorClient) -> DiscoverableEntities` method. Inserts between `handle_command` (ends ~L1654) and `normalize_session_key` (L1656) — i.e., at L1655 — preserving the existing "optional hooks chronologically, with `normalize_session_key` as the structurally-final required method" rhythm. Type-narrows `client` to `DiscordClient` via `cast(DiscordClient, client)` matching the precedent at `_discord.py:1068`. Reaches into the narrowed client's `_client` attribute for the live `discord.Client` view, with an inline comment: "M11 F3 L3: deliberate `discord.Client` cache read — same `_client`-access practice as `disconnect` at L1068 and the `_user` capture at L350. The SDK's gateway listener populates the cache; we read from it under the plugin's existing connection lifetime guarantees."
  - Maps:
    - `client._client.users` → `peers` axis. `id = str(user.id)`, `label = f"@{user.global_name or user.name}"` (Discord's username-system migration: `global_name` is the new display field, fallback to `name` for older accounts), `group = None` (users span guilds), `metadata = {"bot": bool(user.bot)}`. **Note**: `discord.Client.users` is already deduplicated at the SDK layer (`return list(self._connection._users.values())`). The implementation uses a dict-keyed-by-id loop as defensive idempotence (against scaffold-only duplication in tests, or future SDK behavior change); the leg pins this with a test that exercises the defensive branch via a stubbed `users` list containing duplicates.
    - `client._client.get_all_channels()` → `channels` axis. Emit ALL `GuildChannel` subclasses (TextChannel, VoiceChannel, CategoryChannel, ForumChannel, StageChannel). `id = str(channel.id)`, `label = f"#{channel.name}"`, `group = f"guild:{channel.guild.id}"` (every channel from `get_all_channels()` has a guild — the SDK iterates `for guild in self.guilds: yield from guild.channels`). `metadata = {"type": str(channel.type)}` carries the type token so L5/L6 can filter to text-postable channels at the render layer. Threads (`Guild.threads`) are explicitly OUT of scope for this leg — `get_all_channels()` doesn't yield them and the L6 routing surfaces don't require them in F3.
    - `client._client.guilds` → `groups` axis. `id = str(guild.id)`, `label = guild.name`, `group = None`, `metadata = {"member_count": guild.member_count or 0}` (the `or 0` collapses `None` to `0` for shape stability; the intent-gated case is rare in practice but the substrate stays defensive).
    - For each guild in `client._client.guilds`, iterate `guild.roles` and emit each role as a `DiscoverableEntity` on the `roles` axis. `id = str(role.id)`, `label = f"@{role.name}"`, `group = f"guild:{guild.id}"`, `metadata = {"position": role.position, "mentionable": role.mentionable}`.
    - `fetched_at` = `datetime.now(UTC).isoformat()` at call time. `UTC` is available in Python 3.11+ (project pins `requires-python = ">=3.11"` at `pyproject.toml:5`).
- `tests/test_connectors_discord.py` grows new test cases:
  - `test_discord_plugin_implements_enumerate_discoverable_entities` — asserts `hasattr(DiscordPlugin(), "enumerate_discoverable_entities") is True` AND `getattr(plugin, "enumerate_discoverable_entities") is not None` AND `callable(getattr(plugin, "enumerate_discoverable_entities"))`.
  - `test_discord_plugin_enumerate_returns_populated_axes` — uses the existing **Path B** test pattern (extend `_StubDiscordClient` via the plugin's `connect()` to produce a real `DiscordClient` wrapping a stubbed SDK client). The stubbed SDK client carries `users` (list of `_StubUser`), `guilds` (list of `_StubGuild`, each with `.roles` and `.channels`), and `get_all_channels()` (generator over guild channels). Calls `plugin.enumerate_discoverable_entities(connected_client)`. Asserts: `result` is `DiscoverableEntities`; `result.peers` has the stubbed users with `@`-prefixed labels (using `global_name` when present, falling back to `name`); `result.channels` has the stubbed channels with `#`-prefixed labels and `guild:{id}` group; `result.groups` has the stubbed guilds; `result.roles` has the stubbed roles with `guild:{id}` groups; `result.fetched_at` matches an ISO 8601 with `+00:00` offset (e.g. regex `^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?\+00:00$`).
  - `test_stub_plugin_does_not_implement_enumerate_discoverable_entities` — imports `StubPlugin` from `the_one.connectors._stub`, asserts `getattr(StubPlugin(), "enumerate_discoverable_entities", None) is None`. This pins the fallback contract.
  - `test_discord_plugin_enumerate_tolerates_unknown_member_count` — exercise the defensive branch where `guild.member_count is None`. The result still produces a `DiscoverableEntity` for the guild with `metadata["member_count"] == 0`.
  - `test_discord_plugin_enumerate_user_label_falls_back_to_name_when_global_name_missing` — exercise the `global_name or name` branch: a user with `global_name = None` produces a label of `f"@{user.name}"`; a user with `global_name = "Display Name"` produces `f"@Display Name"`.
  - `test_discord_plugin_enumerate_dedupes_users_defensively` — even though the SDK guarantees `Client.users` returns unique users, the implementation defensively deduplicates by id. Test passes a stubbed `users` list containing two entries with the same `id`; assert `result.peers` has exactly one entry for that id (the first occurrence). Test docstring explicitly notes this is defensive, not exercising a real SDK shape.

## Acceptance Criteria

- [x] `the_one/connectors/base.py` declares `DiscoverableEntity` as `@dataclass(frozen=True, slots=True)` with fields `id: str`, `label: str`, `group: str | None = None`, `metadata: dict[str, Any] = field(default_factory=dict)`.
- [x] `the_one/connectors/base.py` declares `DiscoverableEntities` as `@dataclass(frozen=True, slots=True)` with fields `peers: list[DiscoverableEntity]`, `channels: list[DiscoverableEntity]`, `groups: list[DiscoverableEntity]`, `roles: list[DiscoverableEntity]`, `fetched_at: str`. All four list fields use `field(default_factory=list)`.
- [x] `the_one/connectors/base.py` module docstring documents `enumerate_discoverable_entities(client: ConnectorClient) -> DiscoverableEntities` as an OPTIONAL plugin hook, discovered via `getattr(plugin, "enumerate_discoverable_entities", None)`, with `None` as the fallback sentinel. The new docstring paragraph follows the same shape as the existing `resolve` docstring paragraph (L11-16) and cross-references the L1-codified `optional-plugin-hook-via-getattr-sentinel` convention.
- [x] `the_one/connectors/base.py` does NOT add `enumerate_discoverable_entities` to the `ConnectorPlugin` Protocol class body. The Protocol's 4 required methods (`connect`, `disconnect`, `doctor`, `normalize_session_key`) remain unchanged.
- [x] `the_one/connectors/_discord.py` declares `_DiscordPlugin.enumerate_discoverable_entities(self, client: ConnectorClient) -> DiscoverableEntities` (the public name `DiscordPlugin` is the same class). The method type-narrows `client` to `DiscordClient` (assert / cast / runtime check — match the existing internal pattern of other DiscordPlugin methods).
- [x] `_DiscordPlugin.enumerate_discoverable_entities` returns a `DiscoverableEntities` whose four axes are populated from the live `client._client` view as specified in Outputs above. The implementation uses `cast(DiscordClient, client)` (matching the precedent at `_discord.py:1068`); `cast` is imported from `_discord.py:55`. An inline comment at the `_client` access point cross-references the established practice (e.g. "M11 F3 L3: `discord.Client` cache read — same `_client`-access practice as `disconnect` at L1068 and the `_user` capture at L350").
- [x] User-axis entries are deduplicated by user id (defensive idempotence — Discord's SDK already guarantees `Client.users` uniqueness via `list(self._connection._users.values())`; this AC pins the implementation's defense against scaffold-only duplication in tests or future SDK behavior change).
- [x] Guild `member_count is None` is tolerated: the guild still emits a `DiscoverableEntity` with `metadata["member_count"] = 0`.
- [x] `fetched_at` is an ISO 8601 timestamp produced via `datetime.now(UTC).isoformat()` at call time.
- [x] `the_one/connectors/_stub.py` is NOT modified. `StubPlugin` still does NOT implement `enumerate_discoverable_entities`.
- [x] `tests/test_connectors_discord.py` grows the six new tests enumerated in Outputs:
  - [x] `test_discord_plugin_implements_enumerate_discoverable_entities`
  - [x] `test_discord_plugin_enumerate_returns_populated_axes`
  - [x] `test_stub_plugin_does_not_implement_enumerate_discoverable_entities`
  - [x] `test_discord_plugin_enumerate_tolerates_unknown_member_count`
  - [x] `test_discord_plugin_enumerate_user_label_falls_back_to_name_when_global_name_missing`
  - [x] `test_discord_plugin_enumerate_dedupes_users_defensively`
- [x] All five new tests pass: `docker exec the-one pytest tests/test_connectors_discord.py -x --timeout 30 -q` reports 0 failures and the new tests appear in the pass count.
- [x] Existing tests in `tests/test_connectors_discord.py` continue to pass byte-identically (no regression on prior tests).
- [x] The full connector test suite continues to pass: `docker exec the-one pytest tests/test_connectors_discord.py tests/test_connectors_pool.py tests/test_connectors_inbound.py tests/test_connectors_e2e_platform_send.py -x --timeout 30 -q` reports 0 failures.
- [x] No JavaScript / frontend / API code is modified in this leg. `git diff --stat` shows changes only in `the_one/connectors/base.py`, `the_one/connectors/_discord.py`, `tests/test_connectors_discord.py`, plus the F3 sibling artifacts.
- [x] No imports of the new dataclasses are added in any consumer (`_pool.py`, `interfaces/web/api.py`, etc.) — those consumers land in L4. The L3 surface is dataclass-declaration + hook-implementation + tests only.

## Verification Steps

- `grep -n "class DiscoverableEntity\b\|class DiscoverableEntities\b" the_one/connectors/base.py` — exactly one hit each.
- `grep -n "enumerate_discoverable_entities" the_one/connectors/base.py the_one/connectors/_discord.py the_one/connectors/_stub.py` — appears in `base.py` docstring AND `_discord.py` method definition; ZERO hits in `_stub.py`.
- `grep -n "enumerate_discoverable_entities" tests/test_connectors_discord.py` — appears in five new tests.
- `python -c "from the_one.connectors.base import DiscoverableEntity, DiscoverableEntities; print('ok')"` — succeeds.
- `python -c "from the_one.connectors._discord import DiscordPlugin; p = DiscordPlugin(); print(callable(getattr(p, 'enumerate_discoverable_entities', None)))"` — prints `True`.
- `python -c "from the_one.connectors._stub import StubPlugin; p = StubPlugin(); print(getattr(p, 'enumerate_discoverable_entities', None) is None)"` — prints `True`.
- `docker exec the-one pytest tests/test_connectors_discord.py -x --timeout 30 -q` — all tests pass; the five new tests appear in the run.
- `docker exec the-one pytest tests/test_connectors_discord.py tests/test_connectors_pool.py tests/test_connectors_inbound.py tests/test_connectors_e2e_platform_send.py -x --timeout 30 -q` — full connector test suite passes.
- `git diff --stat` — changes confined to `the_one/connectors/base.py`, `the_one/connectors/_discord.py`, `tests/test_connectors_discord.py`, plus F3 sibling artifacts.
- `grep -rn "enumerate_discoverable_entities" the_one/ --exclude=__pycache__` — appears in `base.py` (docstring) and `_discord.py` (method). No spurious hits in `_pool.py`, `_inbound.py`, `interfaces/`, etc. (those consumers land in L4+).

## Implementation Guidance

1. **Read the actual current state of `the_one/connectors/base.py` around the typed-export block** (lines 30-376) and the `ConnectorPlugin` Protocol body (L278-355). Confirm the structural position to insert `DiscoverableEntity` + `DiscoverableEntities`. The existing pattern is: dataclasses interleaved with type aliases and helper functions, then `ConnectorClient` Protocol at L235, then `ConnectorPlugin` Protocol at L278, then `CommandResponse` dataclass at L358, then `CommandHandler` Protocol at L378+. The cleanest insertion point: **after `CommandResponse` (L376), before `CommandHandler` Protocol (L378)** — keeps the F3 substrate dataclasses adjacent to the most recently-added typed export and preserves the dataclass/Protocol rhythm.

2. **Declare `DiscoverableEntity` first** with module-docstring-grade inline `"""..."""` documentation: what the platform-native id is for; what `label` should look like (platform-native display form, e.g. `#general`); what `group` is for (cross-axis grouping in the Studio render layer); what `metadata` is for (platform-specific extras). Mention that the substrate treats the dataclass as opaque except for `id` (the platform-native ID used for round-tripping back to `account.config.allowlist`).

3. **Declare `DiscoverableEntities` second** with module-docstring-grade inline documentation: what each axis represents at the substrate layer (`peers` = platform users; `channels` = platform channels; `groups` = platform guilds/workspaces; `roles` = platform roles); that `fetched_at` is the ISO-8601 timestamp of the live read; that the substrate stays neutral on vocabulary (Discord renders these as users/channels/servers/roles via the L5/L6 Studio layer).

4. **Extend the module docstring** at L1-27 to add a paragraph documenting the new optional hook. Insert BETWEEN the existing paragraph 2 (`resolve` / `display_channel`, L11-21) and paragraph 3 (`canonical-import`, L23-26) — NOT appended after paragraph 3. Suggested wording:

   > Per ``agents.md`` ``optional-plugin-hook-via-getattr-sentinel`` (L1-codified
   > by flight 1 of mission 11): connectors that can enumerate the platform
   > entities the bot has live visibility into implement the OPTIONAL
   > ``enumerate_discoverable_entities(client: ConnectorClient) -> DiscoverableEntities``
   > hook (introduced by flight 3 of mission 11 for live-data discoverable
   > dropdowns). Discovered via ``getattr(plugin, "enumerate_discoverable_entities", None)``
   > with ``None`` as the fallback sentinel — consumers (the L4 pool cache
   > refresh sweep and the per-account Studio API endpoint) treat the
   > ``None`` return as "this plugin doesn't expose live data; fall back to
   > the chip-list editor."

5. **Do NOT add the method to the `ConnectorPlugin` Protocol class body.** The Protocol stays at 4 required methods. The hook is opt-in via `getattr` discovery, NOT widening. Confirm by `grep -n "async def\|def " the_one/connectors/base.py | grep -A 0 "class ConnectorPlugin"` after editing — should still show only the 4 existing methods.

6. **In `_discord.py`**, add the `enumerate_discoverable_entities` method to `_DiscordPlugin`. Insert at L1655 — between `handle_command` (ends ~L1654) and `normalize_session_key` (L1656) — preserving the "optional hooks chronologically, `normalize_session_key` structurally-final" rhythm. Use `cast(DiscordClient, client)` for type-narrowing per the precedent at `_discord.py:1068` (`cast` is already imported at L55).

7. **Read the live discord.Client view**. The method body:
   ```python
   def enumerate_discoverable_entities(self, client: ConnectorClient) -> DiscoverableEntities:
       """[docstring]"""
       # M11 F3 L3: `discord.Client` cache read — same `_client`-access
       # practice as `disconnect` at L1068 and the `_user` capture at
       # L350. The SDK's gateway listener populates `users`, `guilds`,
       # and per-guild `channels`/`roles`; we read from those caches
       # under the plugin's existing connection-lifetime guarantees.
       discord_client = cast(DiscordClient, client)._client

       peers_by_id: dict[str, DiscoverableEntity] = {}
       for user in discord_client.users:
           uid = str(user.id)
           if uid in peers_by_id:
               continue  # defensive dedup; SDK already unique by id
           label = f"@{user.global_name or user.name}"
           peers_by_id[uid] = DiscoverableEntity(
               id=uid,
               label=label,
               group=None,
               metadata={"bot": bool(user.bot)},
           )

       channels: list[DiscoverableEntity] = []
       for channel in discord_client.get_all_channels():
           # Every channel from get_all_channels() has a guild (the SDK
           # iterates `for g in self.guilds: yield from g.channels`).
           channels.append(DiscoverableEntity(
               id=str(channel.id),
               label=f"#{channel.name}",
               group=f"guild:{channel.guild.id}",
               metadata={"type": str(channel.type)},
           ))

       groups: list[DiscoverableEntity] = []
       roles: list[DiscoverableEntity] = []
       for guild in discord_client.guilds:
           groups.append(DiscoverableEntity(
               id=str(guild.id),
               label=guild.name,
               group=None,
               metadata={"member_count": guild.member_count or 0},
           ))
           for role in guild.roles:
               roles.append(DiscoverableEntity(
                   id=str(role.id),
                   label=f"@{role.name}",
                   group=f"guild:{guild.id}",
                   metadata={"position": role.position, "mentionable": role.mentionable},
               ))

       return DiscoverableEntities(
           peers=list(peers_by_id.values()),
           channels=channels,
           groups=groups,
           roles=roles,
           fetched_at=datetime.now(UTC).isoformat(),
       )
   ```

   Note: the above is *guidance*, not a code drop. The developer adapts to the file's actual conventions (logging style, error-handling posture, import location). Do NOT add an `isinstance` runtime gate — `cast()` is the established precedent (silences the type checker without a runtime check, since the pool's contract guarantees the shape).

8. **Imports**: ensure `DiscoverableEntity` and `DiscoverableEntities` are imported from `the_one.connectors.base`; add `from datetime import datetime, UTC` if not already present. Use the file's existing import-block conventions.

9. **Tests**: add the six tests to `tests/test_connectors_discord.py`. Mirror the existing inline-SDK-stub pattern. For `_StubGuild`, define `id`, `name`, `member_count`, `roles` (list of `_StubRole`), `channels` (list of `_StubChannel`); for `_StubRole`, define `id`, `name`, `position`, `mentionable`; for `_StubChannel`, define `id`, `name`, `type`, `guild` (reference to a `_StubGuild`); for `_StubUser`, define `id`, `name`, `global_name`, `bot`. The `_StubClient` exposes `users`, `guilds`, and `get_all_channels()` (`get_all_channels` yields `for g in self.guilds: yield from g.channels` matching the real SDK iteration).

   **Use Path B**: extend the existing `_StubDiscordClient` (the SDK-stub the test file already uses for `plugin.connect`) to populate `users` / `guilds` / `get_all_channels()`; then call `plugin.enumerate_discoverable_entities(connected_client)` on the real `DiscordClient` produced by `plugin.connect(...)`. This reuses the established connect-path fixture pattern and avoids hand-constructing `DiscordClient` with its 5 internal fields (`client`, `connection_task`, `ready_event`, `intents`, `account_id`). The dedupe and member_count-None tests stub `users` / `guilds` directly on the connected client's `_client` for the specific scenario.

10. **Run tests**. `docker exec the-one pytest tests/test_connectors_discord.py -x --timeout 30 -q`. Address any failures by diagnosing root cause (not by `xfail`/`skip`). When all pass, run the broader connector-subsystem set: `docker exec the-one pytest tests/test_connectors_discord.py tests/test_connectors_pool.py tests/test_connectors_inbound.py tests/test_connectors_e2e_platform_send.py tests/test_connectors_acl.py -x --timeout 30 -q` (the ACL suite participates in `optional-plugin-hook-via-getattr-sentinel`'s primary citation — `resolve` hook discovery — so any regression in hook-discovery code paths would surface there).

11. **Sibling artifact bookkeeping**. Check off L3 in flight.md (Checkpoints + Legs sections). Append L3 leg-progress entry to flight-log.md.

12. **Update leg status header**. `ready → in-flight → landed`. Do NOT commit; do NOT signal `[HANDOFF:review-needed]` — F3 batches review + commit at flight end.

## Edge Cases

- **`UTC` import on older Python**: `from datetime import UTC` requires Python 3.11+. The project pins 3.11+ (confirmed at design recon). If the developer hits an `ImportError`, use `datetime.timezone.utc` instead and document the deviation in the leg log.

- **Discord SDK type narrowing**: `_DiscordPlugin.disconnect` (at `_discord.py:1068`) uses `cast(DiscordClient, client)` with NO runtime `isinstance` gate. This leg follows the same precedent — `cast()` only, no `assert`. The file's `cast` import is at L55.

- **`get_all_channels()` scope**: per discord.py 2.4.0's `Client.get_all_channels` definition, the generator yields `for guild in self.guilds: yield from guild.channels` — i.e., guild channels ONLY (no DMs, no threads). Every yielded channel has a `.guild` attribute by construction; no defensive `getattr` needed. The implementation accesses `channel.guild.id` directly.

- **`user.global_name` is None for older Discord accounts**: the SDK exposes `global_name` (introduced in the Discord username-system migration). Fall back to `user.name` when `global_name is None`. The test exercises both branches.

- **Stub-doesn't path: do NOT add the method to `StubPlugin`.** The test pins this absence as the fallback contract. If a future maintenance leg adds `enumerate_discoverable_entities` to `StubPlugin`, the test must rotate.

- **Vocabulary substitution is OUT of scope here.** The substrate returns `@username`, `#channel-name`, etc. — Discord-native conventions, NOT generic-vocabulary "peer / group". The substrate vocabulary discipline lives at the Studio render layer (L5/L6), not at the substrate. Per F1 L6 vocabulary discipline.

- **Pickle / serialization**: the dataclasses are frozen + slots. The L4 leg will serialize them for the API response (likely via `dataclasses.asdict`). Confirm the field types are JSON-serializable: `id` str, `label` str, `group` str|None, `metadata` dict[str, Any]. The `Any` in metadata may contain Discord-native types that need stringification at the API layer — that's an L4 concern, not L3. L3's job is to produce the dataclass shape; L4's job is to serialize it.

- **Coherent substrate landing (not `atomic-leg-pattern`)**: this leg touches THREE source files (base.py, _discord.py, test file). The L1-codified `atomic-leg-pattern` convention specifically scopes to {Pydantic schema, DB schema, repository codec, runtime consumer} crossings AND explicitly excludes "contract-additive changes that are fully optional at every site" (per `agents.md:162-172`). This leg is purely substrate-additive with NO consumer (L4 lands the consumer). The 3-file co-shipment is justified by the simpler "coherent surface" reasoning: dataclass declaration without plugin impl is a half-baked surface; plugin impl without tests is undefended; tests without the dataclass declaration fail to import. They land together for coherence, not under the atomic-leg-pattern convention.

- **`tests/test_connectors_discord.py` imports**: the test file already imports `DiscordClient` and `DiscordPlugin`. The new tests additionally need `DiscoverableEntity`, `DiscoverableEntities` from `the_one.connectors.base` AND `StubPlugin` from `the_one.connectors._stub` (for the stub-doesn't test). The developer adds these imports if not present.

## Files Affected

- `the_one/connectors/base.py` — `DiscoverableEntity` + `DiscoverableEntities` dataclasses added; module docstring extended with the new optional-hook paragraph.
- `the_one/connectors/_discord.py` — `_DiscordPlugin.enumerate_discoverable_entities` method added; necessary imports updated.
- `tests/test_connectors_discord.py` — five new tests added; SDK-stub fixtures extended to cover users/guilds/channels/roles.
- `missions/11-discord-connector-depth/flights/03-live-data-discoverable-dropdowns/flight.md` — L3 checkpoint + L3 leg checklist item checked off.
- `missions/11-discord-connector-depth/flights/03-live-data-discoverable-dropdowns/flight-log.md` — L3 leg-progress entry appended.
- `missions/11-discord-connector-depth/flights/03-live-data-discoverable-dropdowns/legs/03-discoverable-entities-plugin-hook.md` — this artifact's status header progresses through its lifecycle.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [x] All acceptance criteria verified
- [x] Tests pass: `docker exec the-one pytest tests/test_connectors_discord.py -x --timeout 30 -q` reports 0 failures with the 5 new tests present
- [x] Broader connector suite passes: `docker exec the-one pytest tests/test_connectors_discord.py tests/test_connectors_pool.py tests/test_connectors_inbound.py tests/test_connectors_e2e_platform_send.py -x --timeout 30 -q` reports 0 failures
- [x] Update `flight-log.md` with L3 leg-progress entry
- [x] Set this leg's status to `landed`
- [x] Check off L3 in `flight.md` (Checkpoints + Legs sections)
- [x] Do NOT commit (F3 batches review + commit at flight end per the agentic-workflow protocol)
