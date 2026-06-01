# Leg: bug-e-filter-categories-from-discoverable-entities

**Status**: completed
**Flight**: [Slash HAT closure + ACL/slash-sync cluster fix + L4-enhancement test debt](../flight.md)

## Objective

Fix Bug E: `DiscordPlugin.enumerate_discoverable_entities` returns `CategoryChannel` entries in its `channels` list, so the connector allowlist picker offers category ids; an operator who picks one gets every inbound message silently denied (messages arrive from child text channels with their own ids, never the category id). Exclude category-type channels at the substrate enumerate site so no UI consumer ever offers them.

## Context

- **Design decision (flight, operator-directed Phase 4)**: filter at the Discord plugin's `enumerate_discoverable_entities` site (substrate-side), NOT with per-UI defensive logic. Rationale: categories are containers, not channels; the ACL channel-match never accepts a category id. Filtering once at the substrate keeps every current + future UI consumer automatically correct.
- **Site**: `_discord.py:1823-1835` — the `for channel in discord_client.get_all_channels():` loop appends a `DiscoverableEntity` for EVERY channel, tagging `metadata={"type": str(channel.type)}`. For a `CategoryChannel`, `str(channel.type) == "category"`.
- **Filter shape — exclude `category` specifically** (not a positive allowlist). The flight DD sketched `type IN ("text", "voice", "thread")`, but a positive allowlist would also drop announcement/news, forum, and stage channels — some of which ARE text-postable and have real message ids, so dropping them would be a NEW bug. **Design-review confirmed**: the ACL inbound channel-match (`_acl.py:_admits_inbound_guild` `:614-627`) is purely id/guild-based and **type-agnostic** — any channel that can produce an inbound message envelope is matchable, and in discord.py 2.x voice/forum/announcement/stage channels all carry text messages. Categories are the SOLE type that can never be a message's channel (messages always arrive from a child channel). So exclude exactly `"category"`; leave every other type pickable. (Threads are already absent — `Thread` is not a `GuildChannel`.) If a future flight wants a strict postable-only allowlist, that's a separate, explicit decision.
- **No browser test for this leg — and why** (design-review correction): the flight sketched a "+1 browser picker-filter (defense-in-depth)" test on the assumption the UI dropdown could filter by type. It cannot and must not: `discoverable-dropdown.js` (`_renderMenu`/`_buildMenuItem`) renders EVERY channel the API returns, with no `metadata.type` awareness — by design, because the operator's Bug E decision was explicitly substrate-only ("filtering at the substrate keeps every UI consumer automatically correct WITHOUT per-UI defensive logic"). A browser test that `page.route()`-stubs the discoverable-entities response bypasses the substrate filter entirely (the stub IS the response), so it would be circular; and adding `metadata.type` filtering to the JS would CONTRADICT the operator's substrate-only choice. The honest, sufficient coverage is the backend unit test that calls `enumerate_discoverable_entities` directly (the one place the filter lives). The browser test is therefore dropped from this leg with rationale, not silently omitted.

## Inputs

- `the_one/connectors/_discord.py:1750-1869` — `enumerate_discoverable_entities`; channels loop at `:1823-1835`; docstring at `:1779-1785` (mentions `CategoryChannel` is currently included with a render-layer-filter note — update it).
- `tests/test_connectors_discord.py` — existing `enumerate_discoverable_entities` unit tests (e.g. `test_discord_plugin_enumerate_*`) to extend.
- The connector allowlist channel picker — `connector-editor.js` channels slot (the discoverable-entities-fed dropdown) — for the browser defense-in-depth test.
- Discoverable-entities browser test file: `tests/browser/test_flow_studio_connector_inference_provider_row.py` (flight-named candidate) OR a more apt sibling covering the allowlist picker — implementer picks the file that actually exercises the channel picker.

## Outputs

- `enumerate_discoverable_entities` omits `category`-type channels from `channels`.
- Docstring updated: categories excluded at enumerate (not "filtered at render layer").
- +1 backend unit test: mixed-type guild → no category in returned channels AND non-category types (text/voice/forum/announcement) retained (pins the exclude-only-category deviation).

## Acceptance Criteria

- [ ] The channels loop in `enumerate_discoverable_entities` skips channels whose type is `category` via `str(channel.type) == "category"` (NOT `isinstance(...)` — the existing test fakes use a string `.type`, so isinstance wouldn't match them; and the string form matches the existing `metadata={"type": str(channel.type)}` tagging at `:1833`). No `CategoryChannel` appears in the returned `channels`; all other channel types still appear.
- [ ] The method docstring (`:1779-1785`, the whole `channels` bullet incl. the `metadata["type"]` clause) is rewritten to state categories are excluded at the enumerate site (drop the false "filter at render layer" framing — there is no render-layer filter).
- [ ] `tests/test_connectors_discord.py` gains 1 unit test: a guild whose `get_all_channels()` yields a mix (category + text + voice + forum/announcement) → the returned `channels` EXCLUDES the category id AND INCLUDES the text/voice/forum/announcement ids (assert both directions — the inclusion half pins the deviation against a future over-broad allowlist). Reuse `_StubDiscoverableChannel`/`_StubDiscoverableGuild`/`_populate_discoverable_caches` (`tests/test_connectors_discord.py:3305-3413`).
- [ ] Backend suite: prior backend passed-count **+1** / 0 errors (record the actual absolute number in the flight-log L3 entry — the working-tree baseline drifts across L1–L5, so the relative delta is the contract, not a fixed absolute).
- [ ] No browser test added (see Context — substrate-only design; a browser test would be circular). No JS change.
- [ ] Backend tests run via the bounded wrapper (`scripts/run-tests.sh`).

## Verification Steps

- `docker exec the-one bash /app/scripts/run-tests.sh tests/test_connectors_discord.py -x --timeout 30 -q` — enumerate test passes (both exclusion + inclusion assertions).
- `docker exec the-one bash /app/scripts/run-tests.sh -m 'not browser and not live and not pixel' -q` — full backend at prior+1 / 0 errors (leg-end).
- `git grep -n "category" the_one/connectors/_discord.py` — shows the new exclusion in `enumerate_discoverable_entities`.

## Implementation Guidance

1. **Add the category exclusion** in the channels loop (`_discord.py:~1824`). Before appending, `if str(channel.type) == "category": continue`. Place a short comment citing Bug E (F14 L3). Use the string form (`str(channel.type) == "category"`) — confirmed `str(discord.ChannelType.category) == "category"` (discord.py 2.4.0) and it matches the existing `metadata={"type": str(channel.type)}` convention; do NOT use `isinstance(channel, discord.CategoryChannel)` (the unit-test fakes carry a plain string `.type`, so isinstance wouldn't exercise the path).
2. **Update the docstring** (`:1779-1785`): rewrite the whole `channels` bullet — currently says `CategoryChannel` is yielded and `metadata["type"]` lets L5/L6 "filter to text-postable channels at the render layer" (the render-layer filter does NOT exist). Change to: categories are excluded at the enumerate site; all other `GuildChannel` types are returned with their `metadata["type"]` token.
3. **Backend unit test**: extend `tests/test_connectors_discord.py` (reuse `_StubDiscoverableChannel(id, name, type=)` `:3305`, `_StubDiscoverableGuild` `:3325`, `_populate_discoverable_caches` `:3352`; model on `test_discord_plugin_enumerate_returns_populated_axes` `:3430`). `get_all_channels()` yields category + text + voice + forum/announcement. Assert BOTH: the category id is absent AND the text/voice/forum/announcement ids are present (inclusion half pins the deviation).
4. **Run via the wrapper** and record the actual backend count + confirm no orphans. No browser test, no JS change.

## Edge Cases

- **`str(channel.type)` token stability**: discord.py renders `ChannelType.category` as `"category"`. If the implementer uses the `isinstance(channel, discord.CategoryChannel)` form instead, no token dependency — pick one and be consistent with the existing `metadata["type"]` tagging.
- **Forum / Stage / Announcement channels**: NOT excluded — only `category`. They have real ids and may be legitimate targets; excluding them is out of scope for Bug E.
- **Empty channels list** (bot in a guild with only a category and no child channels): returns an empty `channels` list for that guild — fine; nothing to offer, which is correct.

## Files Affected

- `the_one/connectors/_discord.py` — category exclusion in `enumerate_discoverable_entities` + docstring.
- `tests/test_connectors_discord.py` — +1 enumerate unit test (exclusion + inclusion assertions).
- (No JS change, no browser test — substrate-only design; see Context.)

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]` — except commit, which is deferred to Phase 2d per agentic-workflow batch protocol:**

- [ ] All acceptance criteria verified
- [ ] Backend at prior+1 / 0 errors (wrapper used; actual count recorded)
- [ ] Update flight-log.md with L3 leg progress entry (actual backend count, exclusion confirmed)
- [ ] Set this leg's status to `landed`
- [ ] Do NOT check off this leg in flight.md yet (Phase 2d)
- [ ] Do NOT commit (batched at Phase 2d)
