# Leg: discord-vocabulary-substitution

**Status**: landed
**Flight**: [Discord Connector-Type Registration + Discord-Shaped Creation Form](../flight.md)

## Objective

Introduce a frontend per-connector-type vocabulary map (`App.studio.connectorVocabulary`) and consult it at three display sites in `connector-account-editor.js` so a Discord-type account renders "Users / Channels / Servers / Roles" instead of the substrate's neutral "Peers / Channels / Guilds / Roles" labels — without touching the substrate's persisted vocabulary (Pydantic models, routing scope values, ACL field names, audit-log keys) or any backend code.

## Context

- **Why now**: M11 mission criterion #2 ("no Discord-using operator sees the word 'peer' in the UI on a Discord connector") binds this work to F1. F1 flight spec Design Decision "Vocabulary substitution" commits to a frontend map. L4 landed the typed Discord form; L5 landed the invite section; L6 closes the display-text Discord-shaping half — the last frontend deliverable of F1.
- **Display-only contract**: the substrate code is UNCHANGED — `account.config.allowlist.peers/channels/guilds/roles` field names persist, `_VALID_ROUTING_SCOPES = ['channel', 'thread', 'dm', 'peer']` Literal values persist, `Message.peer_id`/`peer_name` field names persist, `session_metadata["routing"]` audit keys persist. Only the rendered display text varies per connector type. This matches `flight.md` Design Decision §6: "Substrate code (Pydantic models, dispatcher, ACL resolver, routing engine, audit logs) stays neutral — the substitution lives entirely in the rendered display text. **Internal scope values stay generic**."
- **Test-update surface near zero**: the design-review-time grep (recorded in `flight.md` Design Decisions §6) confirmed zero existing test files match the literal display text "Peers" / "Guilds" via `textContent` assertions. `data-testid` selectors are unaffected. The Studio HAT tests carry on byte-identical at the selector level; only any test that explicitly asserts a label string needs updating (none found at design audit; verify at impl time).
- **Three display surfaces** identified by design-audit:
  1. **Allowlist section** (`renderAllowlistSection` at `connector-account-editor.js:1623+`) — four `<label>` rows ("Peers", "Channels", "Guilds", "Roles") at lines 1641, 1649, 1657, 1666; four hint texts at lines 1643-1646, 1651-1654, 1659-1663, 1668-1672 (the "Discord-flavored" qualifiers on Guilds and Roles hints).
  2. **Attached-agents table** (`renderAttachedAgentsList` near line 2247+) — table headers "Peers" / "Channels" at lines 2251-2252.
  3. **Routing-rules editor** (`renderRoutingRulesSection` at line 1855+) — display labels only; internal `_VALID_ROUTING_SCOPES` literal values at `connector-account-editor.js:1585` stay generic (NOT substituted).
- **Hint-tone flag**: per `flight.md` Design Decision §6 trade-off paragraph, the "Discord-flavored; ignored by other platforms" qualifier on the Guilds/Roles hints drops on a Discord connector — it's redundant noise once the labels say "Servers / Roles." The vocabulary-map entry carries a `hintTone: 'native' | 'generic'` flag; Discord = `'native'`; default (no entry) = `'generic'`.

### Design Decisions (L6-internal)

- **Vocabulary map shape**: `App.studio.connectorVocabulary` is a plain object keyed by connector type. Each entry carries:
  ```javascript
  {
    peer: 'user',
    peers: 'users',
    group: 'server',
    groups: 'servers',
    channel: 'channel',
    channels: 'channels',
    role: 'role',
    roles: 'roles',
    hintTone: 'native'  // or 'generic'
  }
  ```
  Singular + plural forms; symmetric across the four axes (peer/group/channel/role). `hintTone` controls whether platform-qualifier hints are emitted. Lower-case strings — call sites do their own capitalization via `App.studio.connectorVocabulary.label(...)` or a local capitalization helper.
- **Lookup function**: expose `App.studio.connectorVocabulary.get(type)` returning the entry or a default (generic) entry — never undefined. Default entry: `{peer: 'peer', peers: 'peers', group: 'guild', groups: 'guilds', channel: 'channel', channels: 'channels', role: 'role', roles: 'roles', hintTone: 'generic'}`. Rationale: a default fallback means the call site never needs to nullcheck; "Peers / Channels / Guilds / Roles" is the existing baseline, so the default entry reproduces it byte-for-byte.
- **Label capitalization**: render sites uppercase the first letter of each word for display (e.g., "Users", "Servers"). Implementation via a tiny helper or `value.charAt(0).toUpperCase() + value.slice(1)` inline.
- **Module shape**: `the_one/interfaces/web/static/js/areas/studio/connector-vocabulary.js` is an IIFE attaching `App.studio.connectorVocabulary`. ES5 style. Loaded BEFORE `connector-account-editor.js` (sibling of `connector-form-registry.js`).
- **Discord entry**: `{peer: 'user', peers: 'users', group: 'server', groups: 'servers', channel: 'channel', channels: 'channels', role: 'role', roles: 'roles', hintTone: 'native'}`. Channels and roles stay textually identical (Discord uses the same words); the labels still flow through the substitution layer so future Discord-language refinements happen in one place.
- **Stub entry**: omit. The generic fallback covers `'stub'`-type (and any future-type-without-entry) so the existing Playwright tests against `'stub'` continue to pass UNMODIFIED at the display-text level (current "Peers / Channels / Guilds / Roles" baseline preserved).
- **Routing-rules editor display**: the editor renders scope labels via the substrate's `_VALID_ROUTING_SCOPES = ['channel', 'thread', 'dm', 'peer']`. The literal values STAY GENERIC at the wire/persistence layer per the flight constraint. The display label for the `peer` scope (e.g., a `<option>`'s textContent) is substituted to "user" on a Discord connector via the vocabulary map. The `<option value="peer">` `value` attribute stays at `peer`. Same posture for any future scope-label substitution.
- **Hint-text drop**: when `vocab.hintTone === 'native'`, the Guilds and Roles hints drop the "Discord-flavored; ignored by other platforms" / "Discord-flavored" qualifier. The hint reads simply "Empty list = no server restriction." / "Empty list = no role restriction." (using the substituted singular/plural).
- **Test-update surface confirmed near-zero at L6 design time**: `grep -rn '"Peers"' tests/ static/tests/ 2>/dev/null | grep -v __pycache__` returns zero hits as of L4 + L5 ship. The same grep on "Guilds" returns one possible hit in test fixtures — verify at implementation time. The dominant pattern in Studio tests is `data-testid` selectors which are unchanged by L6.

## Inputs

Files that must exist:
- `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` (3 display sites; substitution consult sites added at each)
- `the_one/interfaces/web/static/index.html` (new `<script>` tag for `connector-vocabulary.js`)
- L1-L5 all landed; branch flight/01-discord-connector-type-and-creation-form checked out
- 2797 baseline passes

## Outputs

State changes after this leg:
- **NEW FILE** `the_one/interfaces/web/static/js/areas/studio/connector-vocabulary.js` (~50-80 LOC, IIFE ES5): defines `App.studio.connectorVocabulary` with `get(type) → entry` (always returns a populated entry; default for unregistered types is the generic baseline). Discord entry registered at module load.
- **Modified `index.html`**: new `<script src="/static/js/areas/studio/connector-vocabulary.js"></script>` inserted at a position BEFORE `connector-account-editor.js` (and before `connector-form-discord.js` so the form module can use it too if needed in future legs; for L6 the form module does not consult it).
- **Modified `connector-account-editor.js`** at three sites:
  - `renderAllowlistSection` (line 1623+): the four `<label>` strings + four `<small>` hint strings consult `App.studio.connectorVocabulary.get(account.type)`. Labels become `Capitalize(vocab.peers)` / `Capitalize(vocab.channels)` / `Capitalize(vocab.groups)` / `Capitalize(vocab.roles)`. Hints: `"Empty list = no " + vocab.peer + " restriction."` (singular); when `vocab.hintTone === 'native'`, drop the "Discord-flavored" qualifier on the guilds/roles hints.
  - `renderAttachedAgentsList` (near line 2247+): the two `<th>` strings "Peers" / "Channels" consult the map similarly.
  - `renderRoutingRulesSection` (line 1855+): any display labels for routing scopes (e.g., a `<option>` textContent for the `peer` scope) consult the map. The `<option value>` attribute stays at the literal scope value. (Detailed audit at impl time; if the routing editor has no `peer`-scope display label, this substitution may be a no-op at L6 and L6 closes only the Allowlist + Attached-agents surfaces.)
- **NEW or extended tests** (`tests/browser/test_flow_studio_connector_discord_vocabulary.py` OR additions to existing L4 file):
  - Discord-type account renders "Users" instead of "Peers" in the Allowlist labels.
  - Discord-type account renders "Servers" instead of "Guilds" in the Allowlist labels.
  - Discord-type account renders "Users" in the Attached-agents table header.
  - Discord-type account hints drop the "Discord-flavored" qualifier on guilds + roles hints.
  - `'stub'`-type account preserves "Peers / Channels / Guilds / Roles" labels (regression for the generic baseline).
  - Internal persistence: a save round-trip on a Discord account still posts `config.allowlist.peers`/`channels`/`guilds`/`roles` field names — verify by intercepting the network request or by reading the saved account back via GET.

## Acceptance Criteria

- [ ] `connector-vocabulary.js` exists; IIFE-wrapped ES5; attaches `App.studio.connectorVocabulary = { get(type) }` to the global namespace.
- [ ] `get(type)` returns an entry for every input — registered Discord shape OR the generic default. NEVER `undefined`. The default entry contains exactly the generic baseline shape (`{peer: 'peer', peers: 'peers', group: 'guild', groups: 'guilds', channel: 'channel', channels: 'channels', role: 'role', roles: 'roles', hintTone: 'generic'}`).
- [ ] The Discord entry is registered at module load: `{peer: 'user', peers: 'users', group: 'server', groups: 'servers', channel: 'channel', channels: 'channels', role: 'role', roles: 'roles', hintTone: 'native'}`.
- [ ] `connector-vocabulary.js` is loaded by `index.html` BEFORE `connector-account-editor.js`. Ordering (not literal line number) is the contract.
- [ ] `renderAllowlistSection` consults the map; on a Discord-type account, the four `<label>` elements render "Users" / "Channels" / "Servers" / "Roles". On a `'stub'`-type account, they render "Peers" / "Channels" / "Guilds" / "Roles" (existing baseline).
- [ ] `renderAllowlistSection` hint texts use the substituted singular word: "Empty list = no user restriction." (Discord) vs "Empty list = no peer restriction." (generic). The Guilds + Roles hints DROP the "Discord-flavored" qualifier when `vocab.hintTone === 'native'`; the qualifier stays when `hintTone === 'generic'`.
- [ ] `renderAttachedAgentsList` table headers consult the map; on a Discord-type account, headers render "Users" / "Channels". On `'stub'`, they stay at "Peers" / "Channels".
- [ ] **Routing-scope dropdown textContent substituted**: `_renderRoutingScopeOptions` at `connector-account-editor.js:1774-1786` currently builds `<option value={s}>{escapeHtml(s)}</option>` for `s ∈ ['channel','thread','dm','peer']` — so on a Discord connector the dropdown literally shows "peer" as an option label, violating M11 criterion #2. L6 MUST substitute the textContent: extend `_renderRoutingScopeOptions` to accept `vocab` (or `account`/`type` and look up vocab internally); for `s === 'peer'`, render textContent as `vocab.peer` ('user' on Discord); for `s === 'channel'`, render `vocab.channel`; for `'thread'` and `'dm'`, render the literal value (no vocabulary substitution today). The `<option value>` attribute STAYS at the literal scope value `peer`/`channel`/`thread`/`dm` (persistence vocabulary preserved).
- [ ] Capitalization of the routing-scope textContent matches the pre-L6 baseline (lower-case — `escapeHtml(s)` was lower-case). On Discord, the substituted label is lower-case `'user'`/`'channel'`. **Do NOT** capitalize the routing-scope option text — the existing dropdown is lower-case across all four scope values; L6 preserves that styling. ("dm" stays "dm" — out of L6 scope; capitalization is a separate polish task if pursued.)
- [ ] **Substrate code UNCHANGED**: no edits to Pydantic models, no edits to `db/models.py`, no edits to `_VALID_ROUTING_SCOPES` constant in either `connector-account-editor.js:1585` or `db/models.py:113`. `grep -n "'peer'" the_one/db/models.py the_one/connectors/_acl.py the_one/connectors/_inbound.py the_one/connectors/_routing.py the_one/connectors/_outbound.py the_one/tools/connector_send.py` returns the same hits pre-L6 and post-L6.
- [ ] A save round-trip on a Discord account confirms `config.allowlist` posts with field names `{peers, channels, guilds, roles}` (not `{users, channels, servers, roles}`) — substrate vocabulary preserved at the wire layer.
- [ ] Existing browser tests against `'stub'` pass UNMODIFIED (no display-text drift). New Discord-vocabulary tests pass.
- [ ] Full suite at or above L5 baseline (2797 passed). New tests add to the count.

## Implementation Guidance

1. **Create `connector-vocabulary.js`** as IIFE ES5. Mirror `connector-form-registry.js` shape:
   ```javascript
   (function () {
     'use strict';
     window.App = window.App || {};
     window.App.studio = window.App.studio || {};

     var _DEFAULT_VOCAB = {
       peer: 'peer', peers: 'peers',
       group: 'guild', groups: 'guilds',
       channel: 'channel', channels: 'channels',
       role: 'role', roles: 'roles',
       hintTone: 'generic'
     };

     var _ENTRIES = {
       discord: {
         peer: 'user', peers: 'users',
         group: 'server', groups: 'servers',
         channel: 'channel', channels: 'channels',
         role: 'role', roles: 'roles',
         hintTone: 'native'
       }
     };

     function get(type) {
       return _ENTRIES[type] || _DEFAULT_VOCAB;
     }

     window.App.studio.connectorVocabulary = { get: get };
   })();
   ```

2. **Add the script tag** to `index.html` BEFORE `connector-account-editor.js` (and probably before `connector-form-discord.js` too — read existing order and pick a position that keeps the load order sensible). The vocabulary module has no dependencies on the registry or the Discord form module.

3. **Add a tiny capitalize helper** at the top of `connector-account-editor.js`'s IIFE (or use an inline `value.charAt(0).toUpperCase() + value.slice(1)`):
   ```javascript
   function _capitalize(s) {
     return s ? s.charAt(0).toUpperCase() + s.slice(1) : '';
   }
   ```

4. **Refactor `renderAllowlistSection`** (line 1623+):
   - At the head: `var vocab = (window.App && window.App.studio && window.App.studio.connectorVocabulary) ? window.App.studio.connectorVocabulary.get(account.type) : null; vocab = vocab || _DEFAULT_VOCAB_INLINE;` (use a small inline default to triple-guard the case where the vocabulary script failed to load).
   - Replace the four `<label>` literal strings:
     - Line 1641 "Peers" → `_capitalize(vocab.peers)`
     - Line 1649 "Channels" → `_capitalize(vocab.channels)`
     - Line 1657 "Guilds" → `_capitalize(vocab.groups)`
     - Line 1666 "Roles" → `_capitalize(vocab.roles)`
   - Replace the four hint texts:
     - Line 1645 "Empty list = no peer restriction." → `'Empty list = no ' + vocab.peer + ' restriction.'`
     - Line 1653 "Empty list = no channel restriction." → `'Empty list = no ' + vocab.channel + ' restriction.'`
     - Line 1661-1662 "Empty list = no guild restriction. Discord-flavored; ignored by other platforms." → `'Empty list = no ' + vocab.group + ' restriction.' + (vocab.hintTone === 'native' ? '' : ' Discord-flavored; ignored by other platforms.')`
     - Line 1670-1671 "Empty list = no role restriction. Any-of overlap; Discord-flavored." → `'Empty list = no ' + vocab.role + ' restriction. Any-of overlap.' + (vocab.hintTone === 'native' ? '' : ' Discord-flavored.')`

5. **Refactor `renderAttachedAgentsList`** (near line 2247+): the two `<th>` strings at lines 2251-2252 read "Peers" / "Channels". Substitute analogously. The function takes `account` (or has access to the active account via closure — read to confirm; pass `vocab` as a parameter if needed).

6. **Refactor `_renderRoutingScopeOptions`** (line 1774+) — confirmed at design-review-time to render display-text "peer" via `escapeHtml(s)` over `_VALID_ROUTING_SCOPES`:
   - Extend the function's signature to accept `vocab` (or `account` / `type`) so it can look up the substitution.
   - For each scope value `s` in the iteration, compute display text: `s === 'peer' ? vocab.peer : (s === 'channel' ? vocab.channel : s)`. The `'thread'` and `'dm'` scopes have no vocabulary entry today; render their literal values (`'thread'`, `'dm'`) unchanged. (Future legs can extend the vocabulary map with thread/dm if Discord-specific labels emerge.)
   - `<option value="...">` stays at the literal scope value via `escapeAttr(s)`. ONLY the textContent uses the substitution.
   - Pass `vocab` (or `account`) through from `renderRoutingRulesSection` (line 1855+) — read the function's existing signature and thread it consistently.
   - Capitalization: the pre-L6 dropdown text was lower-case (`escapeHtml('peer')` → `'peer'`); L6 preserves that — `vocab.peer === 'user'` is already lower-case. Do NOT capitalize.

7. **Verify substrate preservation**: at the end of impl, run `grep -n "'peer'" the_one/db/models.py the_one/connectors/_acl.py the_one/connectors/_inbound.py the_one/connectors/_routing.py` and compare pre-L6 vs post-L6 — must be identical. Any difference is a bug.

8. **Tests**: new file `tests/browser/test_flow_studio_connector_discord_vocabulary.py` OR extend `test_flow_studio_connector_discord_form.py`. Use `seed_connector_account(type='discord', ...)` for setup. Assertions:
   - Discord account: page text contains "Users" (Allowlist label), "Servers" (Allowlist label), "Users" (Attached-agents header).
   - Discord account: page does NOT contain literal "Discord-flavored; ignored by other platforms." in the visible hints (because `hintTone='native'`).
   - Stub account: page text contains "Peers", "Guilds" (existing baseline).
   - Save round-trip: post a Discord account with modified allowlist, then GET the account, confirm response body has `config.allowlist.peers` / `.channels` / `.guilds` / `.roles` field names (substrate preserved).

9. **Run regression suite**:
   - `docker exec the-one pytest -x --timeout 60 -m browser tests/browser/test_flow_studio_connector_account_editor.py tests/browser/test_flow_studio_connector_account_create_and_test.py tests/browser/test_flow_studio_connector_account_navigation.py tests/browser/test_flow_studio_connector_discord_form.py tests/browser/test_flow_studio_connector_invite_section.py tests/browser/test_connector_form_registry.py tests/browser/test_flow_studio_connector_discord_vocabulary.py`
   - All existing 6 tests pass UNMODIFIED (`'stub'`-type display labels still "Peers / Channels / Guilds / Roles" at the rendered level).
   - New Discord-vocabulary tests pass.
   - Full suite at or above L5's 2797 baseline.

## Edge Cases

- **Vocabulary script fails to load**: every consult site falls back to an inline-default `vocab` object (`{peer: 'peer', peers: 'peers', ...}`) so the labels render the existing baseline. No exceptions thrown.
- **Discord account opened in edit mode mid-render with `App.studio.connectorVocabulary` not yet attached** (early-load race): the `(window.App && window.App.studio && ...)` triple-guard returns null; the inline-default kicks in. No exceptions.
- **A future operator types `peer` as a free-form value in a kv-table** (edge case): the kv-table is generic and does not consult the vocabulary; `peer` shows as `peer`. Not a regression — the kv-table is the escape-hatch surface, not a substitution target.
- **Capitalization edge cases**: empty string → `_capitalize('')` returns ''. Single character → uppercase + empty tail → just the uppercase letter. Unicode → JavaScript `charAt(0).toUpperCase()` handles BMP correctly; for non-BMP (emoji etc.) it would mangle, but the vocabulary entries are ASCII so this is irrelevant.

## Files Affected

- `the_one/interfaces/web/static/js/areas/studio/connector-vocabulary.js` — NEW; ~50-80 LOC.
- `the_one/interfaces/web/static/index.html` — one new script tag.
- `the_one/interfaces/web/static/js/areas/studio/connector-account-editor.js` — ~3 consult-site additions in `renderAllowlistSection`, `renderAttachedAgentsList`, optionally `renderRoutingRulesSection`.
- `tests/browser/test_flow_studio_connector_discord_vocabulary.py` — NEW; ~80-120 LOC.
- Leg/flight-log artifacts.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified
- [ ] Existing browser tests pass UNMODIFIED (Stub-type display labels preserved)
- [ ] New Discord-vocabulary tests pass
- [ ] Full suite at or above L5 baseline (2797)
- [ ] No backend / API / DB / Pydantic / substrate changes; confirm via `grep -n "'peer'" the_one/db/models.py the_one/connectors/*.py` (post-L6 matches pre-L6)
- [ ] Save round-trip on a Discord account confirms persisted field names are still `peers/channels/guilds/roles` (substrate vocabulary preserved)
- [ ] Update flight-log.md with Leg Progress entry
- [ ] Set this leg's status to `landed`
- [ ] Do NOT check off the leg in flight.md (flight-end commit owns that)
- [ ] Do NOT commit

## Citation Audit

Citations verified at leg design time (2026-05-21, post-L5):

- `connector-account-editor.js:renderAllowlistSection` — verified at line 1623+; four `<label>` rows at lines 1641, 1649, 1657, 1666 with literal "Peers" / "Channels" / "Guilds" / "Roles". Hint texts at 1643-1646, 1651-1654, 1659-1663, 1668-1672 with the "Discord-flavored" qualifiers on Guilds and Roles.
- `connector-account-editor.js:renderAttachedAgentsList` — verified near line 2247+; `<th>` headers "Peers" / "Channels" at lines 2251-2252.
- `connector-account-editor.js:renderRoutingRulesSection` — verified at line 1855+; needs runtime audit at impl time for display-text occurrences.
- `connector-account-editor.js:_VALID_ROUTING_SCOPES` — verified at line 1585; literal values `['channel', 'thread', 'dm', 'peer']`; NOT substituted (persistence vocabulary).
- `the_one/db/models.py:VALID_ROUTING_SCOPES` — verified at line 113; same posture (persistence vocabulary).
- `index.html` script order — verified post-L5: `connector-form-registry.js` at line 57, `connector-form-discord.js` at line 58, `connector-account-editor.js` at line 59. New `connector-vocabulary.js` should land before the editor (line 56 or 57 area is acceptable; ordering relative to the editor is the contract).

Six citation clusters verified live. No drift.
