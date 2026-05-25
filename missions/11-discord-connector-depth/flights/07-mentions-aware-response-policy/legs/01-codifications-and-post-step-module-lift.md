# Leg: codifications-and-post-step-module-lift

**Status**: completed
**Flight**: [Mentions-Aware Response Policy](../flight.md)

## Objective

Lift the post-step Message-mutator idiom into a shared `connectors/post_step_metadata.py` module (n=3 trigger condition met by F7's incoming `channel_name`/`channel_id` binding) and add the optional `is_mention(envelope) -> bool` plugin hook (with `_default_no_mention` sentinel fallback at `_acl.py` and a Discord implementation), so subsequent F7 legs can compose against named, testable substrate functions rather than inline mutations.

## Context

- **Flight DD §6 (lift the mutators)** — F6's post-step Message-mutation idiom is now codified at n=2 in `the_one/agents.md` (visibility + peer_name). F7 adds a third (channel context, lands in L3), tripping the lift threshold the convention itself names. The module home must exist BEFORE L3 (channel-binding) so L3 has somewhere to add `bind_channel_context`. L1 ships the lift; the visibility helper moves; peer_name binding moves out of the inline `_inbound.py` block into a named `bind_peer_name`.
- **Flight DD §7 (`is_mention` plugin hook)** — F7's policy gate (L8) consults `getattr(plugin, "is_mention", _default_no_mention)` to decide path 3 of the decision tree (`@mention` → engage). The substrate side of that consult — the plugin hook + the default — lands here so L8 can wire the gate against a hook that exists. Note: the flight DD describes a `self._user.id` snapshot on the plugin, but `_user` lives on `DiscordClient`, not `DiscordPlugin`; the plugin is stateless. Resolution: the Discord `is_mention` implementation reads the bot identity from the raw `discord.Message` itself (`message.guild.me.id` for guild messages) — DMs bypass `is_mention` at gate step 1 so the guild-only path covers the call site.
- **Flight DD §1 step 3 (where the hook is consulted)** — `is_mention` is consulted by the policy gate (L8), not by `_agent_admits` (which uses `is_dm`). L1 does NOT wire a consult site; it only ships the hook + default + Discord implementation. L8 will consult.
- **`agents.md` citations** — both touched conventions get updated: `post-step-dispatcher-message-metadata-binding` is rewritten to reference the lifted module instead of inline mutations and lists three citations (visibility + peer_name + channel_name/channel_id-via-L3); `optional-plugin-hook-via-getattr-sentinel` adds the `is_mention` citation.

## Inputs

- `the_one/connectors/visibility.py` exists at HEAD with `tag_post_step_visibility(messages, pre_step_len) -> None` (only symbol exported).
- `the_one/connectors/_inbound.py` has the F6 L3 inline peer_name mutation at lines 646–663 (comment block 646–659 + assert at 660–662 + assignment at 663), inside the per-session lock + try-block at line 590/620, with the visibility call at line 644. The functional mutation (what L1 moves to `bind_peer_name`) is lines 660–663; the comment block 646–659 is preserved at the call site since it documents WHY the call happens here.
- `the_one/connectors/_acl.py` has `_default_not_dm` at lines 65–78 — the template `_default_no_mention` mirrors.
- `the_one/connectors/base.py:ConnectorPlugin` Protocol at lines 289–367 — minimal-shape Protocol, optional hooks via getattr-sentinel (NOT added to the Protocol body).
- `the_one/connectors/_discord.py:DiscordPlugin` at lines 578+ with `is_dm` at 1594–1616 — sibling location for `is_mention`.
- `the_one/connectors/_discord_translate.py` at lines 119–134 builds `envelope.raw["discord_message"]` as the raw `discord.Message` SDK object (which has `.mentions: list[User | Member]`).
- `tests/test_connectors_visibility_helper.py` covers the current visibility function — relocates with the function.
- `tests/test_connectors_inbound.py` covers the dispatcher; tests that exercise the peer_name binding need to keep working with the extracted `bind_peer_name` function.
- `the_one/agents.md` has `optional-plugin-hook-via-getattr-sentinel` at ~lines 104–108 (n=4 citations) and `post-step-dispatcher-message-metadata-binding` at ~lines 288–306 (n=2 citations).

## Outputs

- New file: `the_one/connectors/post_step_metadata.py` exporting `tag_post_step_visibility` (relocated) and `bind_peer_name` (extracted from `_inbound.py` inline block). Each function documents which `Role`s it touches and which it skips so non-overlap is verifiable by inspection (per the codified composition contract).
- `the_one/connectors/visibility.py` becomes a deprecation re-export shim: `from the_one.connectors.post_step_metadata import tag_post_step_visibility` plus a docstring/comment naming the new home so any external importer hits the re-export rather than `ImportError`. (Internal importers all migrate inline in this leg.)
- `the_one/connectors/_inbound.py`:
  - Imports `tag_post_step_visibility` and `bind_peer_name` from `the_one.connectors.post_step_metadata` (replaces the existing `visibility` import).
  - The inline peer_name mutation at 646–663 is replaced with a single `bind_peer_name(agent.messages, pre_step_len, working_envelope.peer_name)` call; the explanatory comment block is preserved (it documents the WHY and is cited by the `bind_peer_name` docstring).
- `the_one/connectors/_acl.py`: new `_default_no_mention(envelope: InboundEnvelope) -> bool` defined directly below `_default_not_dm`, returning `False`, with docstring mirroring `_default_not_dm`'s shape and citing F7 L1 + the `optional-plugin-hook-via-getattr-sentinel` convention.
- `the_one/connectors/_discord.py`: new `DiscordPlugin.is_mention(self, envelope: InboundEnvelope) -> bool` method placed immediately after `is_dm` (line ~1617), reading `envelope.raw["discord_message"]` and checking whether `message.guild.me.id` appears in `message.mentions`. Docstring mirrors `is_dm`'s shape and cites the policy gate consult site (L8 forthcoming).
- `the_one/agents.md`:
  - `optional-plugin-hook-via-getattr-sentinel` citation list grows from 4 → 5 (adds `is_mention` site description identical-in-shape to the `is_dm` entry, citing `_acl.py:_default_no_mention` + `_discord.py:DiscordPlugin.is_mention` + the L8-forthcoming consult site).
  - `post-step-dispatcher-message-metadata-binding`:
    - Header sentence rewritten so it references the lifted module (`connectors/post_step_metadata.py`) instead of describing inline mutations.
    - Citation list grows from 2 → 3 (visibility + peer_name + a forward-reference for channel context arriving in L3; mark the latter `pending L3` until L3 lands).
    - The closing "when n=3 is reached, lift the mutators..." sentence is replaced with "Lifted at F7 L1; new mutators are added to `connectors/post_step_metadata.py` and composed via the contract above."
- New tests in `tests/test_connectors_post_step_metadata.py` (renamed from the old visibility-helper file's content + new tests for `bind_peer_name`):
  - All existing `test_connectors_visibility_helper.py` tests are relocated (same test names, same body, import from new module). The old test file is deleted.
  - New tests for `bind_peer_name`: (a) binds peer_name onto the USER message at `pre_step_len`; (b) does NOT touch non-USER messages above `pre_step_len`; (c) accepts `None` peer_name (no-op semantically — leaves the field at its default); (d) raises `AssertionError` when the message at `pre_step_len` is not Role.USER (mirroring the existing inline assertion).
- New tests in `tests/test_connectors_acl.py` (extension): `test_default_no_mention_returns_false` mirroring `test_default_not_dm`.
- New tests in `tests/test_connectors_discord.py` (extension), all six covering the implementation branches:
  - `test_is_mention_returns_true_when_bot_in_mentions` — stub `discord.Message` with `guild.me.id == 42` and `mentions = [User(id=42)]` → True.
  - `test_is_mention_returns_false_when_bot_not_in_mentions` — same shape, bot not in list → False.
  - `test_is_mention_returns_false_on_empty_mentions` — explicit empty list → False.
  - `test_is_mention_returns_false_when_raw_discord_message_missing` — defensive: malformed `raw` dict missing the key → False AND no exception raised (both assertions explicit; pinning that a future refactor to "raise on malformed envelope" doesn't pass silently).
  - `test_is_mention_returns_false_when_guild_missing` — DM-shaped: `raw_msg.guild = None` (the F7 policy gate short-circuits is_dm before consulting is_mention, but the defensive branch is exercised independently) → False.
  - `test_is_mention_returns_false_when_guild_me_missing` — `raw_msg.guild` present, `guild.me = None` (bot not yet synced in this guild) → False.
- Optional small DRY helper: a private `_make_discord_message_stub(*, guild_me_id, mention_ids)` fixture factory used by the six `is_mention` tests, mirroring how other Discord tests in `tests/test_connectors_discord.py` build `discord.Message` stubs.

## Acceptance Criteria

- [ ] `the_one/connectors/post_step_metadata.py` exists and exports both `tag_post_step_visibility` and `bind_peer_name`. Both functions have docstrings naming the Role(s) they touch and the Role(s) they skip.
- [ ] `the_one/connectors/visibility.py` is a deprecation re-export shim. `from the_one.connectors.visibility import tag_post_step_visibility` continues to work.
- [ ] `the_one/connectors/_inbound.py` post-step block (lines ~631–663) replaces the inline peer_name mutation with `bind_peer_name(agent.messages, pre_step_len, working_envelope.peer_name)` and imports both helpers from `post_step_metadata`. The visibility call site uses the same module's symbol.
- [ ] `_default_no_mention(envelope) -> bool` is defined in `the_one/connectors/_acl.py` directly below `_default_not_dm` and returns `False`. Its docstring mirrors `_default_not_dm` and cites F7 L1.
- [ ] `DiscordPlugin.is_mention(self, envelope) -> bool` is defined in `the_one/connectors/_discord.py` directly below `is_dm` and returns True iff the bot's user id appears in `envelope.raw["discord_message"].mentions`, reading the bot id via `message.guild.me.id`. Defensive against `raw` missing `"discord_message"` (returns False) and against missing `guild`/`guild.me` (returns False).
- [ ] `the_one/agents.md`'s `optional-plugin-hook-via-getattr-sentinel` entry lists `is_mention` in its citations (count grows from n=3 → n=4: display_channel, resolve, is_dm, is_mention).
- [ ] `the_one/agents.md`'s `post-step-dispatcher-message-metadata-binding` entry references `connectors/post_step_metadata.py`, lists 3 citations (visibility + peer_name + channel_name/channel_id-pending-L3-within-this-flight), removes the "when n=3 is reached, lift" sentinel sentence (the lift has happened), AND the string `_inbound.py:663` no longer appears anywhere in `agents.md` (the old peer_name citation is *replaced*, not augmented, by the `post_step_metadata.py:bind_peer_name` citation).
- [ ] `_default_no_mention` is added to `the_one/connectors/_acl.py`'s `__all__` list, mirroring `_default_not_dm`'s membership.
- [ ] `tests/test_connectors_post_step_metadata.py` exists, covers both `tag_post_step_visibility` (all the relocated tests) and `bind_peer_name` (the four new tests listed in Outputs). The old `tests/test_connectors_visibility_helper.py` is deleted.
- [ ] `tests/test_connectors_acl.py` has a `test_default_no_mention_returns_false` test.
- [ ] `tests/test_connectors_discord.py` has the six `is_mention` tests listed in Outputs (bot-mentioned True, bot-not-mentioned False, empty-mentions False, missing-discord_message False+no-exception, missing-guild False, missing-guild.me False).
- [ ] `docker exec the-one pytest tests/test_connectors_post_step_metadata.py tests/test_connectors_acl.py tests/test_connectors_discord.py tests/test_connectors_inbound.py -x --timeout 30` passes.
- [ ] Full suite run (`docker exec the-one pytest -x --timeout 30`) at leg-end: no F7-L1-introduced regressions vs. F6-landing baseline.
- [ ] Flight log L1 entry under `## Leg Progress` documents the leg's changes; leg checked off in `flight.md` under `### Legs`.

## Verification Steps

- `python -c "from the_one.connectors.post_step_metadata import tag_post_step_visibility, bind_peer_name; print('OK')"` prints `OK`.
- `python -c "from the_one.connectors.visibility import tag_post_step_visibility; print('OK')"` still prints `OK` (deprecation shim works).
- `grep -n "agent.messages\[pre_step_len\].peer_name = working_envelope.peer_name" the_one/connectors/_inbound.py` returns nothing (inline mutation gone).
- `grep -n "bind_peer_name(agent.messages, pre_step_len" the_one/connectors/_inbound.py` returns exactly one match (the new call site).
- `grep -n "_default_no_mention" the_one/connectors/_acl.py` returns the definition.
- `grep -n "is_mention" the_one/connectors/_discord.py` returns the method definition.
- `grep -n "is_mention" the_one/agents.md` returns at least one citation match.
- `grep -n "post_step_metadata" the_one/agents.md` returns the updated convention reference.
- Targeted test command: `docker exec the-one pytest tests/test_connectors_post_step_metadata.py tests/test_connectors_acl.py tests/test_connectors_discord.py tests/test_connectors_inbound.py -x --timeout 30` — all green.
- Full suite: `docker exec the-one pytest -x --timeout 30` — all green (or only failures attributable to known pre-F7 issues per recon).

## Implementation Guidance

1. **Create `the_one/connectors/post_step_metadata.py`** with module docstring citing F7 L1 + the `post-step-dispatcher-message-metadata-binding` convention. Define `tag_post_step_visibility` (copy verbatim from `visibility.py`, including docstring; update docstring header to note the relocation and to call out Role-touch / Role-skip explicitly in the docstring's first body paragraph). Define `bind_peer_name(messages: list[Message], pre_step_len: int, peer_name: str | None) -> None` with the same assertion + assignment from the current `_inbound.py:660–663` block; docstring should:
   - Cite F6 L3 (origin) + F7 L1 (extraction).
   - State: "Touches `Role.USER` only; skips all other roles" AND frame this as the *composition complement* of `tag_post_step_visibility` (which skips USER and touches all other roles). The non-overlap claim is then visible at docstring read-time without requiring readers to inspect both functions in tandem.
   - Pair the runtime `assert` with the agents.md guidance ("pair with a regular unit test that pins the same invariant so it survives `python -O`").
   - Note that `None` peer_name is allowed (downstream optional field).

2. **Rewrite `the_one/connectors/visibility.py`** as a 5–10 line deprecation re-export shim:
   ```python
   """Deprecated home for ``tag_post_step_visibility``.

   The function lives at :mod:`the_one.connectors.post_step_metadata` as of F7 L1.
   This re-export preserves the import path for any external importers; internal
   callers migrate inline.
   """
   from the_one.connectors.post_step_metadata import tag_post_step_visibility

   __all__ = ["tag_post_step_visibility"]
   ```
   Do NOT delete the file — leave the shim so an external importer (none known at HEAD, but agents.md cites the convention by file path) doesn't break.

3. **Update `the_one/connectors/_inbound.py`:**
   - Replace `from the_one.connectors.visibility import tag_post_step_visibility` (or however it's imported today) with `from the_one.connectors.post_step_metadata import tag_post_step_visibility, bind_peer_name`.
   - In the post-step block (lines ~631–663):
     - Keep the visibility-tagging comment block + call as-is (just the import now resolves through the new module).
     - Replace the peer_name comment block + inline `assert` + assignment with a single `bind_peer_name(agent.messages, pre_step_len, working_envelope.peer_name)` call. Keep the explanatory comment block (M11 F06 L03 + the rationale) above the call — the comment now describes WHY the call happens here; the WHAT lives in the function's docstring.

4. **Update `the_one/connectors/_acl.py`** by adding `_default_no_mention` immediately below `_default_not_dm`, AND extending the module's `__all__` list (currently at `_acl.py:62`) to include `_default_no_mention` alongside `_default_not_dm`. Note: L8's policy gate will `from the_one.connectors._acl import _default_no_mention` — an underscore-prefixed cross-module import is intentional and mirrors the existing F8 precedent for `_default_not_dm` (consumed at `_routing.py:_agent_admits` via the same convention). The leading underscore documents "private to the convention sentinel-fallback set," not "do not import":
   ```python
   def _default_no_mention(envelope: InboundEnvelope) -> bool:
       """Sentinel fallback for the ``is_mention`` plugin hook.

       Returned by ``getattr(plugin, "is_mention", _default_no_mention)`` at
       the F7 policy-gate consult site (L8) for plugins that do not implement
       the optional ``is_mention`` extension. Returning ``False`` preserves
       the gate's silent-by-default branch for plugins without a mention
       concept (webhook-driven future connectors, the test stub).

       Mirrors :func:`_default_not_dm` (named module-level callable
       returning the default outcome — see ``agents.md`` §
       ``optional-plugin-hook-via-getattr-sentinel``).
       """
       return False
   ```

5. **Update `the_one/connectors/_discord.py`** by adding `is_mention` directly after `is_dm`:
   ```python
   def is_mention(self, envelope: InboundEnvelope) -> bool:
       """Return True if the bot is @mentioned in the inbound channel message.

       Reads the raw :class:`discord.Message` from ``envelope.raw["discord_message"]``
       (populated by L4's ``_translate_discord_message_to_envelope``) and checks
       whether the bot's user id (resolved via ``message.guild.me.id`` for guild
       messages — the plugin is stateless, the per-guild Member object carries
       the bot's id) appears in ``message.mentions``.

       Defensive:
       - Missing ``discord_message`` key → False (malformed envelope; should not
         occur in practice but the SDK contract is enforced by the translator,
         not by the type system).
       - Missing ``guild`` or ``guild.me`` → False (DM channels lack a guild;
         the F7 policy gate short-circuits is_dm at decision-tree step 1 before
         consulting ``is_mention``, so this fallback only fires for malformed
         DMs).

       Consumed at the F7 policy-gate consult site
       (:func:`the_one.connectors._inbound.dispatch_inbound`, L8) via the
       ``optional-plugin-hook-via-getattr-sentinel`` convention; the sentinel
       default (:func:`the_one.connectors._acl._default_no_mention`) returns
       ``False`` for plugins without this hook (e.g. the test-only stub).
       """
       raw_msg = envelope.raw.get("discord_message")
       if raw_msg is None:
           return False
       guild = getattr(raw_msg, "guild", None)
       if guild is None:
           return False
       me = getattr(guild, "me", None)
       if me is None:
           return False
       bot_id = me.id
       return any(getattr(user, "id", None) == bot_id for user in raw_msg.mentions)
   ```

6. **Update `the_one/agents.md`:**
   - In the `optional-plugin-hook-via-getattr-sentinel` block (~lines 104–108), append a sentence to the Citations paragraph in the same shape as the `is_dm` citation: "F7 L1's `the_one/connectors/_inbound.py:dispatch_inbound` policy gate (DD §1 step 3) consults `plugin.is_mention` via `getattr(plugin, "is_mention", _default_no_mention)` for the policy gate's mention short-circuit branch (`_default_no_mention` at `the_one/connectors/_acl.py:_default_no_mention` returns False, preserving the silent-by-default behavior for plugins without a mention concept; `DiscordPlugin.is_mention` opts in via `the_one/connectors/_discord.py:DiscordPlugin.is_mention`)." (Note: the consult site itself lands in L8; L1 sets up the hook + default + Discord implementation. The agents.md text may forward-reference L8's consult site for narrative coherence — the line `[pending L8 consult site]` is acceptable as a marker if preferred.)
   - In the `post-step-dispatcher-message-metadata-binding` block (~lines 288–306):
     - The opening sentence is rewritten so it references the module: "The connector dispatcher binds metadata to `Message`s that `agent.step` has appended via shared mutators in `the_one/connectors/post_step_metadata.py`."
     - The Citations block becomes:
       ```
       Citations (n=3):
       - `the_one/connectors/post_step_metadata.py:tag_post_step_visibility` (M10 F4 L4; relocated F7 L1) — visibility tagging on non-USER messages; skips `Role.USER`.
       - `the_one/connectors/post_step_metadata.py:bind_peer_name` (M11 F6 L3; extracted F7 L1) — peer_name binding on the appended USER message; addresses `messages[pre_step_len]` directly.
       - `the_one/connectors/post_step_metadata.py:bind_channel_context` (M11 F7 L3; pending L3 within this flight) — channel_name + channel_id binding on the appended USER message; same addressing pattern as `bind_peer_name`.
       ```
       Critically, the old `the_one/connectors/_inbound.py:663` citation MUST be removed; replacement is by relocation of the citation home, not by adding a third entry alongside the old one. After this edit, `grep -n "_inbound.py:663" the_one/agents.md` returns nothing.
     - Replace the closing "When n=3 is reached, lift the mutators into a shared `connectors/post_step_metadata.py` module" sentence with: "Lifted at F7 L1; the module is the home for all post-step mutators. New mutators land here; the composition contract above governs Role-touch / Role-skip non-overlap."

7. **Relocate + extend tests:**
   - `git mv tests/test_connectors_visibility_helper.py tests/test_connectors_post_step_metadata.py`.
   - Update imports inside the file: `from the_one.connectors.post_step_metadata import tag_post_step_visibility` (was `from the_one.connectors.visibility import tag_post_step_visibility`).
   - Append a new test class or top-level functions for `bind_peer_name` covering the four cases listed in Outputs. Mirror the existing test naming conventions in the file (snake_case function names, docstring sentence, plain `assert` style).
   - In `tests/test_connectors_acl.py`: add `def test_default_no_mention_returns_false() -> None:` calling `_default_no_mention(some_envelope)` and asserting `False`. Build the envelope via the existing test fixtures used by `test_default_not_dm`.
   - In `tests/test_connectors_discord.py`: add the SIX `is_mention` tests (per Outputs — four positive/negative paths + two no-guild defensive paths). Build the stub `discord.Message` either via `unittest.mock.Mock(spec=...)` (preferred — see how other Discord tests in this file mock the SDK) OR via small dataclass-style fakes. The optional `_make_discord_message_stub(*, guild_me_id, mention_ids)` helper factors out the common shape — apply if it tightens; the leg author judges. Verify all six pass. The "raw_discord_message missing" test asserts BOTH the False return AND that no exception was raised (use `pytest.raises` negation idiom or a plain `try/except` wrap that fails the test on any caught exception).

8. **Run targeted tests** then full suite per Verification Steps. Update flight log under `## Leg Progress` with a `### L1 — codifications-and-post-step-module-lift` subsection (status: completed, summary of changes, any anomalies). Check off the leg in `flight.md` under `### Legs`.

## Edge Cases

- **External importers of `visibility.py`**: none known in-repo, but `agents.md` and historical commit messages reference the path. The deprecation re-export shim preserves the import path; no caller breaks.
- **`bind_peer_name` with `peer_name=None`**: the assertion checks `Role.USER`; the assignment writes `None` (the field's default). This is the correct semantic — non-Discord plugins with no peer_name concept emit `working_envelope.peer_name=None` and the field remains at its default. Test (c) under Outputs pins this.
- **`is_mention` on a DM**: DMs lack `message.guild`, so the `getattr(raw_msg, "guild", None) is None` branch returns False. The F7 policy gate at L8 consults `is_dm` FIRST (decision tree step 1), so `is_mention` is never called on a DM in practice — but the defensive `False` return ensures the hook is correctness-safe if called out of order.
- **Bot id not yet resolved at the `is_mention` call**: `guild.me` is set by discord.py once the guild is cached; if the bot has just connected and the guild membership hasn't synced, `guild.me` could conceivably be None — the defensive branch returns False (safe: under-engagement is the F7 bias, per DD §9's "STRONG BIAS TOWARD no").
- **`message.mentions` contains a `discord.User` (DM partner) rather than `Member`**: in practice DMs are filtered upstream; for guild messages the `mention.id` comparison is structurally safe regardless of the concrete class (`User` and `Member` both have `.id`). The `getattr(user, "id", None)` defensive guard tolerates malformed entries.
- **`python -O` strips the `bind_peer_name` assert**: the test that pins `raises AssertionError when message is not USER` exercises the assertion at unit-test time; production behavior with `-O` is "silently writes peer_name to whatever role's message is at pre_step_len," which is a contract violation, not a security gap. The pairing of the runtime `assert` with the unit test matches the codified rule.
- **Tests calling the visibility helper via the deprecation shim**: the relocated tests use the new module path. If any test elsewhere in the repo still imports from `the_one.connectors.visibility`, it continues to work via the shim — no migration needed for unrelated tests.

## Files Affected

- `the_one/connectors/post_step_metadata.py` — NEW (relocated + extracted mutators).
- `the_one/connectors/visibility.py` — REWRITE as deprecation re-export shim.
- `the_one/connectors/_inbound.py` — UPDATE imports + replace inline peer_name mutation with `bind_peer_name` call.
- `the_one/connectors/_acl.py` — ADD `_default_no_mention` below `_default_not_dm`.
- `the_one/connectors/_discord.py` — ADD `DiscordPlugin.is_mention` below `is_dm`.
- `the_one/agents.md` — UPDATE two convention entries per Implementation Guidance step 6.
- `tests/test_connectors_visibility_helper.py` — RENAME to `tests/test_connectors_post_step_metadata.py`.
- `tests/test_connectors_post_step_metadata.py` — UPDATE imports + ADD `bind_peer_name` tests.
- `tests/test_connectors_acl.py` — ADD `test_default_no_mention_returns_false`.
- `tests/test_connectors_discord.py` — ADD four `is_mention` tests.
- `missions/11-discord-connector-depth/flights/07-mentions-aware-response-policy/flight-log.md` — APPEND `## Leg Progress` entry.
- `missions/11-discord-connector-depth/flights/07-mentions-aware-response-policy/flight.md` — CHECK OFF leg under `### Legs`.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing (targeted + full suite)
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `completed` (in this file's header)
- [ ] Check off this leg in flight.md
- [ ] If final leg of flight:
  - [ ] Update flight.md status to `landed`
  - [ ] Check off flight in mission.md
- [ ] Commit all changes together (code + artifacts) — DEFERRED in F7 per `/agentic-workflow` flight-level commit ordering; do NOT commit per leg.

## Citation Audit

All code-location citations in this leg were verified against current code at design time via the F7 L1 reconnaissance pass (flight-log.md Reconnaissance Report + dedicated F7 L1 recon agent run). 8 file-symbol citations verified clean:

- `the_one/connectors/visibility.py:tag_post_step_visibility` — exists.
- `the_one/connectors/_inbound.py:644` — `tag_post_step_visibility` call site (post-step block 631–644).
- `the_one/connectors/_inbound.py:646–663` — inline peer_name mutation (F6 L3); the assertion + assignment lines.
- `the_one/connectors/_inbound.py:590` — `async with session_locks[session_row.id]` lock acquire.
- `the_one/connectors/_inbound.py:620` — `try:` block opening.
- `the_one/connectors/_acl.py:65–78` — `_default_not_dm` definition.
- `the_one/connectors/base.py:289–367` — `ConnectorPlugin` Protocol class block.
- `the_one/connectors/_discord.py:1594–1616` — `DiscordPlugin.is_dm` definition (template for `is_mention`).
- `the_one/connectors/_discord_translate.py:119–134` — envelope construction including `"discord_message": message` raw key.
- `the_one/agents.md:~104–108` — `optional-plugin-hook-via-getattr-sentinel` convention block.
- `the_one/agents.md:~288–306` — `post-step-dispatcher-message-metadata-binding` convention block.

One forward-reference is left as `pending L3`: `the_one/connectors/post_step_metadata.py:bind_channel_context` is named in the updated agents.md citation list but lands in L3. This is intentional (the n=3 lift is a single logical change tracked across L1 + L3) and is annotated in the agents.md text per Implementation Guidance step 6.
