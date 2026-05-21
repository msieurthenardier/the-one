# Flight: Discord Connector-Type Registration + Discord-Shaped Creation Form

**Status**: landed
**Mission**: [Discord Connector Depth & Robustness](../../mission.md)

## Contributing to Criteria

- [x] The existing `'discord'` connector-type registration (M10 F8) grows a Discord-shaped UI surface on top of the substrate's connector-type contract: Discord-shaped creation form (typed BOT_TOKEN, intents selector with safe defaults, optional guild scoping, invite-URL helper); non-secret typed fields land in `account.config` rather than `account.secrets`; the substrate's connector-type checklist (Pydantic Literal, registry, schema CHECK constraint, API gating, frontend badges/tokens, default-config layer) is the contract this work satisfies.
- [x] Every Discord-touching user-facing surface speaks Discord vocabulary (username, server, channel, role) where the substrate uses generic vocabulary (peer, group); the generic vocabulary remains in code for connector-agnostic plumbing, but no Discord-using operator sees the word "peer" in the UI on a Discord connector.

---

## Pre-Flight

### Objective

F1 closes M11's "the operator sees Discord shape, not substrate shape" promise at the **creation and detail surfaces**. Today, an operator selecting Discord in the connector-account creation flow lands in a generic key-value config table with a free-form `BOT_TOKEN` secret row; the connector type's intents are hardcoded in the plugin (`_discord.py:619-622`), the only way to scope to specific guilds is to type the key `guilds` into the kv-table by hand, and the operator has to leave Studio for the Discord developer portal's OAuth-URL generator to find the invite URL. F1 replaces that with a Discord-shaped form (typed bot-token field with masked-edit, three-intent selector with safe defaults, optional guilds list, presence dict, advanced kv-table behind a disclosure), an always-visible Invite section on the detail page (computed from the probe's `application_id` + selected intents), and a frontend vocabulary substitution that swaps the substrate's generic terms ("peer", "group") for Discord vocabulary ("username", "server") on every Discord-facing UI surface. The substrate's connector-type six-layer checklist (Pydantic Literal, registry, schema CHECK, API gating, frontend badges/tokens, default-config) closes for Discord at the API-gating and default-config layers (the other four landed in M10 F8 L2). The substrate's per-type form abstraction is introduced as a frontend `connector-form-registry` so the second connector lands as a registry entry, not as new branching. F1 also folds in M11's Known Issue #1 — codify the six `agents.md` conventions inherited from M10's debrief — as its first leg, since M11 binds those conventions and they must be readable before legs 2+ run.

### Open Questions

*All planning-time open questions resolved at design review (2026-05-21). Resolutions promoted to Design Decisions below.*

### Design Decisions

**Per-type config validation layer — API-layer per-type dispatch** *(resolved at design review)*:
- Add `_validate_connector_account_config(account: ConnectorAccount) -> None` to `interfaces/web/api.py` mirroring `_validate_mcp_source_config` at `api.py:730`. Discord branch validates `config['intents']` shape (3-key dict of bools), optional `config['guilds']` (list of digit-only strings), optional `config['presence']` shape (lifting the existing inline checks at `_discord.py:_build_activity` and `_sync_per_guild_commands` to the API layer).
- Call sites: `create_connector_account` (api.py:2148+, between `model_validate` and `repo.create`) and `update_connector_account` (api.py:2169+, same insertion point). Contract delivery is the existing FastAPI `HTTPException(status_code=422, detail=...)` pattern.
- Pydantic model stays type-neutral; per-type knowledge lives at the API boundary.
- **Rationale**: Three convergent reasons per architect's review — (1) precedent fit is exact (MCP `_validate_mcp_source_config` is the only per-type config validator in the API today, and `api.py:2160-2163` comment explicitly invites this extension); (2) M11 substrate-neutrality constraint is honored (Pydantic-model option would couple substrate to per-connector knowledge); (3) `agents.md:315` already documents "API gating / branches" as layer 5 of the connector-type checklist — the spec ships the convention already documented.
- **Trade-off**: validation does NOT fire on the DB read path (only on API write). If a future operator manually edits the DB, the read path won't catch invalid shapes. Acceptable: the same trade-off applies to MCP today; the single-user local-tool security posture and the API-only-write discipline make this acceptable.

**`_init_*` state hook on `DiscordPlugin` — skip** *(resolved at design review)*:
- The Discord plugin reads `account.config` at `connect()` time (`_discord.py:240` for `guilds`, `_discord.py:624` for `presence`, post-F1 also for `intents` per L2). No state outside the base `ConnectorAccount` fields is needed; the per-account state is just the live `discord.Client` carried by the pool's worker.
- `agents.md:317` already documents "Not needed for Flight 1's stub or any Flight-8/9 design currently on the table; revisit per real plugin" — F1 confirms the prediction held. Document as N/A in flight-log; no source change.

**Form abstraction — substrate-level per-type form registry (frontend)**: Introduce `the_one/interfaces/web/static/js/areas/studio/connector-form-registry.js` exposing `App.studio.connectorFormRegistry.{register, get}`. Each registered entry carries `{ type, renderConnectionFields, renderCredentialsFields, collect, reservedConfigKeys }` for the Discord-specific replacements of the generic kv-table sections. `connector-account-editor.js:renderConnectionFields` and `renderSecretsKvTable` consult the registry; when no entry is found for `account.type`, they fall back to the existing generic kv-tables (preserving the `'stub'` test-only path and unblocking future types added without UI work).
- The registry's per-type `collect` hook returns `{config: {...}, secrets: {...}}` and the substrate's `collectFormData` stitches the result alongside any allowlist / routing / pairing data. This is the cleaner of the two integration options surfaced at design review (the alternative — emit the same DOM selectors as the generic tables so existing scanning works unchanged — couples the registry entry's DOM to the substrate's selector strings, which is a worse separation).
- The registry's per-type `reservedConfigKeys` declares which keys the typed form owns and that the Advanced kv-table must hide. The substrate's `RESERVED_CONFIG_KEYS = { pairing, allowlist, routing }` stays as the connector-agnostic generic baseline; the Discord registry entry adds `{ intents, guilds, presence }` to its own per-type set. `collectConfigRows` consults the registry to compose the effective reserved set for the active account's type.
- This abstraction is consciously richer than the `static/js/areas/admin.js:177-189` `TYPE_DEFAULTS` precedent — `TYPE_DEFAULTS` is a flat-map-of-defaults, while `connector-form-registry` is a render-time dispatch registry. The acknowledged divergence is appropriate: the connector form needs typed fields per type, not just default values.
- **Rationale**: M11 constraint forbids closing design space for the second connector. A pluggable registry is the substrate-level abstraction the mission explicitly invites (Tertiary stakeholder section: "the Discord-shaped UX patterns introduced here become the reference shape for the second connector"). Hardcoded `if (type === 'discord')` would force a refactor at F9-equivalent landing.
- **Trade-off**: ~150-250 LOC of registry plumbing (loader, fallback path, dirty-tracking integration) in F1 we wouldn't otherwise need until a second connector type lands. Accepted because the alternative — hardcode now, refactor later — repeats the M10 F1 pool-keying pattern that the M10 debrief flagged as a methodology failure (mirror M07's MCP-keyed pool without premise re-validation surfaced as a structural defect at F8 HAT, 7 flights later). The premise here ("a second Discord-shaped connector form will be needed at M12 or later") is M11 mission text itself.

**Intents shape — three checkboxes, all-defaulted-on, plugin reads config**:
- `account.config["intents"]` shape: `{message_content: bool, members: bool, guilds: bool}`. All three default to `true` for new accounts.
- Discord plugin at `_discord.py:619-622` replaces hardcoded `intents.message_content = True; intents.members = True; intents.guilds = True` with `intents_cfg = account.config.get("intents", {}); intents.message_content = intents_cfg.get("message_content", True); ...` so existing accounts (which lack `config["intents"]`) round-trip with byte-identical behavior.
- Plugin emits a WARNING-level log line at `connect()` if `message_content` is unticked but the bot is expected to receive channel content (currently this is the only mode the plugin supports — there is no "read-only listener with just members + guilds" mode in F8's design, so the warning is "you've disabled message_content; the bot will silently receive no channel messages until you re-enable it").
- The doctor probe's intents check (M10 F8 L7) already cross-checks the developer-portal-side enabled intents against what the gateway IDENTIFY actually requests; this composes with F1's config-driven intents without further change.
- Form renders three checkboxes with a small help-text per intent; an "Advanced" disclosure mirrors the kv-table escape hatch but is rendered closed by default.
- **Rationale**: Operator visibility is the M11 outcome. Hardcoded intents in the plugin is the F8 footgun the mission's first criterion calls out. Defaulting all on preserves M10 F8 behavior; the warning catches the only operationally meaningful misconfiguration.
- **Trade-off**: Adds a Pydantic-validator constraint to `config["intents"]` if validation lands at layer (c). The chosen API-layer path (recommended) avoids the coupling.

**Invite URL — always-visible Invite section on detail page**: On the General tab of an **edit-mode** Discord connector (not visible in create mode — pre-probe state is only meaningful after the account is persisted), a persistent "Invite" section is always mounted below the Test Connection section. The section's content varies by probe state: post-probe it renders the computed invite URL (from `application_id` returned by the doctor probe's `application` check at `_discord.py:1089,1124,1301` + selected intents + constant permission integer + `scope=bot+applications.commands`) with a Copy button and a "Recompute" button; pre-probe (account just created, probe never run) it renders the hint "Run Test Connection first to fetch your application ID." The URL recomputes on intents-checkbox change with no debounce — recompute is pure-function and rapid toggling is operationally fine.
- **Rationale**: Repeated invites to multiple servers is a daily-driver reality (per M11 mission text). A persistent section beats a one-time post-create banner. M11 mission criterion #1 explicitly calls out "invite-URL helpers."
- **Trade-off**: Requires the probe to have run at least once (the application_id is not available without it). Acceptable: the Create & Test flow runs the probe automatically; the operator only sees the empty hint if they create an account without running the probe.
- **Required permissions integer**: derived from selected intents. M10 F8 only requires `Send Messages` (2048), `Read Message History` (65536), `View Channels` (1024), `Use Application Commands` (2147483648) — the operator's intent toggles do not affect the required-permissions integer (intents and permissions are orthogonal Discord concepts). Permission integer is therefore a constant in F1 (`(1 << 11) | (1 << 16) | (1 << 10) | (1 << 31)` or equivalent). Document this in the flight-log so a future flight extending bot capabilities updates the integer alongside.

**Vocabulary substitution — frontend vocabulary map by connector type**: Add `the_one/interfaces/web/static/js/areas/studio/connector-vocabulary.js` exposing `App.studio.connectorVocabulary[connectorType] = {peer, peers, group, groups, ...}`. Allowlist (`renderAllowlistSection`), Routing-rules editor, and Connector-detail surfaces consult the map when rendering labels and copy.
- Discord entry: `{peer: 'user', peers: 'users', group: 'server', groups: 'servers', channel: 'channel', channels: 'channels', role: 'role', roles: 'roles'}`. Allowlist labels become "Users / Channels / Servers / Roles" on a Discord connector; routing-rules editor uses Discord vocabulary for scope copy.
- Stub entry: omit; the generic vocabulary remains the fallback ("Peers / Channels / Guilds / Roles" — current shipped state).
- Substrate code (Pydantic models, dispatcher, ACL resolver, routing engine, audit logs) stays neutral — the substitution lives entirely in the rendered display text. **Internal scope values stay generic**: the routing-rules editor's `_VALID_ROUTING_SCOPES = ['channel', 'thread', 'dm', 'peer']` (`connector-account-editor.js:1585`) and `db/models.py:113`'s `VALID_ROUTING_SCOPES` are persisted values and MUST NOT be substituted — only the display labels rendered next to them switch vocabulary.
- `data-testid` attributes stay stable so existing Studio HAT tests continue to resolve. Verified at design review: zero test files in `tests/` and `static/tests/` grep-match on display-text "Peers" or "Guilds"; the test-update surface is small to zero.
- Per-axis hint copy also substitutes: the existing Allowlist hint "Discord-flavored; ignored by other platforms" (at the Guilds/Roles axes) drops the "Discord-flavored" qualifier when rendered on a Discord connector — it's redundant noise once the labels say "Servers / Roles." The vocabulary entry can carry a `hintTone: 'native' | 'generic'` flag that hint-rendering consults.
- **Rationale**: Operator never sees "peer" on a Discord connector — M11 mission criterion #2 explicit. Substrate stays neutral per M11 constraint. Smallest surface in F1 (per-type map is ~30 lines, plus the call-site substitution in 3 sections).
- **Trade-off**: Test selectors that match on display text (`textContent === 'Peers'`) need updating to the Discord vocabulary. Selectors that match on `data-testid` are unaffected (the dominant pattern in the existing Studio tests; design-review grep confirmed near-zero impact).

**Advanced kv-table behind disclosure**: The generic kv-table is preserved as an "Advanced" collapsed disclosure within the Discord-shaped form. Keys covered by typed fields (intents, guilds, presence) hide from the kv-table per the `RESERVED_CONFIG_KEYS` pattern (already at `connector-account-editor.js:553`); add `intents`, `guilds`, `presence` to the reserved set. Anything else operator-set (e.g. `ready_timeout_seconds`, future undocumented plugin keys) remains accessible via the disclosure.
- **Rationale**: Preserves forward compatibility for plugin keys the typed form hasn't surfaced; matches the operator's mental model that nothing was taken away.
- **Trade-off**: Operators who edit `intents` via the disclosure would conflict with the typed form. Mitigate via reserved-key hiding (the kv-table physically doesn't show `intents`) so the conflict is structurally prevented.

**UAT-and-alignment leg — Create + Test + Invite + Attach round-trip on real Discord**: The optional final leg drives the new flow against a real Discord application: operator opens Studio → New Connector → selects Discord → types bot token → toggles intents → clicks Create & Test → sees probe report → sees invite URL → invites bot to test guild (out-of-band) → attaches to an agent. Verifies F1's end-to-end UX is operator-comfortable. Reuses M10 F8's bot identity (gleepglorp) or a fresh test bot at operator discretion. Browser-MCP-drivable per M11 mission's environment requirements but operator can also run it manually.

**M10 conventions codification folded as L1**: M11 Known Issue #1 binds F1 to six `agents.md` conventions from M10's debrief. None of them appear in `the_one/agents.md` today. L1 codifies them as a doc-only change before any code lands; subsequent legs can reference the convention names by their committed text. Operator decision (per Phase-3 interview): fold into F1, defer routine-maintenance separately.

### Prerequisites

- [x] M10 F8 substrate is landed and unchanged (confirmed: `connectors/_discord.py`, `connectors/registry.py`, `db/_connector_types.py`, `db/models.py` all on `main` per F8 debrief 2026-05-20).
- [x] M11 mission planning complete and `mission.md` carries the F1 scope (confirmed: `missions/11-discord-connector-depth/mission.md`).
- [ ] Discord developer application available for the UAT leg (operator has gleepglorp from M10 F8 HAT; can be reused or rotated).
- [ ] Discord test guild + at least one channel reachable by the bot for UAT (operator already has this from M10 F8 HAT).
- [ ] The `chrome-devtools` MCP is registered if the UAT leg uses browser-driven flow (operator confirmed; M11 environment requirements section).
- [ ] Routine-maintenance scheduled to run AFTER M11 lands (operator decision: M11 first, maintenance and any structural cleanup as a separate post-M11 pass).

### Pre-Flight Checklist

- [x] All open questions resolved (validation-layer choice; `_init_*` hook necessity)
- [x] Design decisions documented (above; refined at design-review per architect's feedback)
- [x] Prerequisites verified (M10 F8 substrate, M11 mission, Discord dev application, MCP availability)
- [x] Validation approach defined (per-leg ACs in leg specs; UAT leg covers integration)
- [x] Legs defined (below; planned one-at-a-time per Flight Control convention but tentatively scoped here)

---

## In-Flight

### Technical Approach

**Layer-by-layer satisfaction of the connector-type six-layer checklist for Discord.** F1 closes the two layers the M10 F8 L2 leg did not: API gating (layer 5 — per-type config validation) and default-config / frontend Discord-shaped form (layer 6's second half). Layers 1-4 are unchanged from F8 L2; layer 7 is documented as N/A; layer 8 is unchanged from F4.

**The substrate-level per-type form registry is the load-bearing piece.** It is the first piece M11 builds; once it exists, the Discord-shaped form is a registry entry plus the typed-field components. The fallback path (no registry entry → generic kv-table) is the test-seam that keeps the `'stub'` flow working and ensures unrelated connector types added in the future don't break Studio.

**Discord plugin changes are minimal and bounded.** The only `_discord.py` edit is replacing the hardcoded intents block at lines 619-622 with `config["intents"]` reads (atomic; one diff). Everything else lands in `interfaces/web/static/js/areas/studio/` (frontend) and `interfaces/web/api.py` (validation), per the M11 constraint that the agent loop and substrate stay frozen.

**Vocabulary substitution is display-only.** The substrate's neutral vocabulary persists in code paths, Protocols, storage, and tests. The substitution table is consulted at render time at three surfaces (Allowlist, Routing-rules, Connector-detail). Future surfaces opt in by consulting the same table.

**Invite-URL helper is a computed-derived-value.** `application_id` flows from the probe's `application` check; intents from the form; permission integer from a constant. Composition is pure (no I/O); rendering is reactive (recompute on intents change). Pre-probe state shows a hint.

**Codification leg lands first** so legs 2-6 can reference the convention names in their guidance.

### Checkpoints

- [x] L1 — Six M10 conventions live in `the_one/agents.md` with definitions, exemplar lines, and back-references to M10 debrief
- [x] L2 — `config["intents"]`, `config["guilds"]`, and `config["presence"]` shape contracts are validated at the API layer via per-type dispatch; the Discord plugin's existing inline checks at `_build_activity` and `_sync_per_guild_commands` are lifted to the API-layer dispatcher; Discord plugin reads `config["intents"]` with fallback to existing-behavior defaults; consistency tests pin the shapes
- [x] L3 — Frontend `connector-form-registry` exists, Discord entry is registered, generic kv-table fallback continues to render for `'stub'` and unregistered types
- [x] L4 — Discord-shaped form renders in create + edit modes: typed BOT_TOKEN, three intent checkboxes (all on by default), guilds list editor, presence editor, Advanced kv-table disclosure; reserved-key hiding extended to `intents` / `guilds` / `presence`
- [x] L5 — Always-visible Invite section on Discord connector detail page renders the computed invite URL with Copy button; updates reactively on intents toggle and Recompute; pre-probe hint state covered
- [x] L6 — Frontend vocabulary map lives at `connector-vocabulary.js`, Discord entry substitutes labels on Allowlist + Routing-rules + Connector-detail surfaces; substrate code unchanged; `data-testid` attributes stable
- [ ] L7 (optional) — UAT: Create + Test + Invite + Attach round-trip on a real Discord application is operator-comfortable and produces a working bot reachable from the test guild; any HAT-time fixes shipped + documented

### Adaptation Criteria

**Divert if**:
- Architect's resolution of the validation-layer open question requires a substrate-shape change (e.g. extending `ConnectorPlugin` Protocol). Pause F1, escalate to mission-level Known Issue, decide whether the substrate change lands here or in a substrate-touching flight.
- The vocabulary substitution at the Routing-rules editor surface exposes a coupling between the routing engine's scope vocabulary (`Literal["channel","thread","dm","peer"]` at `db/models.py:113`) and the display. The constraint says generic vocabulary stays in code; if a substrate-shape change is needed for vocabulary to substitute cleanly, escalate.
- An existing Studio HAT test depends on the literal display text "Peer" / "Peers" rather than a `data-testid` selector. Mitigate by updating selectors; if more than 3-4 tests need touching, treat as a flight-design signal and consider scoping the substitution narrower.

**Acceptable variations**:
- L3 and L4 may merge if the registry plumbing turns out to be small enough that the Discord entry's typed fields fit in the same leg.
- L5 (Invite section) can ship before L4 (Discord form) if the architect prefers — they're independent surfaces.
- Default permission integer (for invite URL) may be tuned at L5 if Discord's required-permissions semantics are different than M10 F8 assumes; document any change in the flight log.
- Reserved-key hiding may be deferred to a follow-up if the operator wants to see `intents` / `guilds` / `presence` in the Advanced kv-table during F1 for debugging. Default ON; toggle to OFF at L4 if HAT surfaces operator confusion.

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses. This list will evolve based on discoveries during implementation.
>
> **Dependency ordering**: L1 lands before all subsequent legs (L2-L6 reference convention names codified in L1). L2 lands before L4 (the form writes shapes the API validator gates; reversing this would let the form land sending payloads the server rejects). L3 lands before L4 (L4 is the first registry consumer). L5 and L6 are independent of each other and of L3-L4 ordering once L1+L2 are landed. L7 is optional and lands last.

- [x] `codify-m10-conventions` — Codify the six M10-debrief conventions in `the_one/agents.md` Project Conventions section: `encryptor-parameter-receive-but-not-consume`, `cross-subsystem-pattern-premise-revalidation`, `prompt-discipline-needs-mechanical-fallback`, `mechanical-fallback-prompt-truth-pairing`, `lifespan-wiring-same-leg-as-installation`, `atomic-leg-pattern`. Each gets a definition, an exemplar code-line citation from M10 F8, and a back-reference to the M10 debrief recommendation. Distinguish "project conventions" (cross-mission, e.g. `cross-subsystem-pattern-premise-revalidation`) from "mission-specific conventions" (M10-emerged, e.g. `encryptor-parameter-receive-but-not-consume`) per M10 debrief recommendation #8. Doc-only change; no source modifications. **Methodological note**: codifying conventions as a leg vs. as a pre-flight artifact is the looser of two valid readings of M11 Known Issue #1; operator preference (Phase-3 interview, 2026-05-21) chose the leg framing to keep all M11 work under flight-log discipline.

- [x] `discord-config-schema-and-validation` — Add API-layer per-type config validation for Discord and lift the existing plugin-side inline checks. New `_validate_connector_account_config(account)` in `interfaces/web/api.py` mirrors `_validate_mcp_source_config:730`; Discord branch validates `config['intents']` (3-key dict of bools), optional `config['guilds']` (list of digit-only strings), optional `config['presence']` (the dict shape already enforced at `_discord.py:_build_activity`). Discord plugin replaces hardcoded intents at `_discord.py:619-622` with `config["intents"]` reads (fallback `{message_content: True, members: True, guilds: True}` so existing F8-shipped accounts round-trip with byte-identical behavior). `_build_activity` and `_sync_per_guild_commands` keep their defensive runtime checks but the API-layer validator catches malformed shapes at the boundary. Per `atomic-leg-pattern` (M10 convention, codified L1): all sites of the contract — validator + plugin + consistency-test — land in this single leg.

- [x] `connector-form-registry-substrate` — Introduce `the_one/interfaces/web/static/js/areas/studio/connector-form-registry.js` exposing `App.studio.connectorFormRegistry.{register, get}`. Each registered entry carries `{ type, renderConnectionFields, renderCredentialsFields, collect, reservedConfigKeys }`. `connector-account-editor.js:renderConnectionFields` and `renderSecretsKvTable` consult the registry; fallback to generic kv-tables when no entry. `collectConfigRows` and `collectFormData` consult `registry.get(type).reservedConfigKeys` to compose the effective reserved set for the active type (generic baseline `{pairing, allowlist, routing}` from `RESERVED_CONFIG_KEYS` + registry-declared per-type extension). Per-type `collect` returns `{config: {...}, secrets: {...}}` and the substrate stitches alongside allowlist / routing / pairing payloads. Pin with a unit test that an unregistered type (e.g. `'stub'`) still renders the generic kv-table; the registry's fallback path is the test seam.

- [x] `discord-shaped-form` — Register Discord entry in the form registry with typed fields: `BOT_TOKEN` (single secret field with masked-edit + show/hide eye), intents (three checkboxes all defaulted on, with help-text per intent), guilds (list editor — typed input, validates digit-only entries), presence (small dict editor — name + type with `_build_activity`'s known type values as a select), and an Advanced disclosure wrapping the generic kv-table. The Discord registry entry declares `reservedConfigKeys: ['intents', 'guilds', 'presence']` so the Advanced kv-table cannot double-write keys the typed form owns. Dirty-tracking integrates with `getFormSnapshot` / `collectFormData` via the registry's `collect` hook (no DOM-selector coupling between registry entry and substrate scanning logic).

- [x] `invite-url-section` — Add an always-mounted Invite section on the Discord connector detail page (General tab, between Test Connection and Danger Zone — edit-mode only; pre-probe state is only meaningful after the account is persisted). Renders the computed invite URL (probe-derived `application_id` from `_discord.py:1089,1124,1301` + selected intents + constant permission integer + scopes `bot+applications.commands`) with a Copy button and a Recompute button. Pre-probe content: hint "Run Test Connection first to fetch your application ID." Post-probe content: the URL. Reactive to intents-checkbox change with no debounce — recompute is pure-function and rapid toggling is operationally fine. Document the permission integer as a constant for now (`(1 << 11) | (1 << 16) | (1 << 10) | (1 << 31)` or equivalent — Send Messages + Read Message History + View Channels + Use Application Commands); future flights extending bot capabilities update it alongside.

- [x] `discord-vocabulary-substitution` — Add `the_one/interfaces/web/static/js/areas/studio/connector-vocabulary.js` with the Discord entry. Wire substitution at Allowlist section (`renderAllowlistSection`), Routing-rules editor (rule scope/match copy — display labels only; internal `_VALID_ROUTING_SCOPES` Literal values at `connector-account-editor.js:1585` stay generic), and Connector-detail page (section titles, hints). Per-axis hint copy substitutes too: the existing "Discord-flavored; ignored by other platforms" qualifier on the Guilds/Roles axes drops on a Discord connector. Stub entry omitted; generic vocab is the fallback. Update Studio HAT tests' display-text matchers to the Discord vocabulary; `data-testid` matchers stay stable. Verified at design review: zero existing tests grep-match on the literal "Peers" / "Guilds" display text; test-update surface is near-zero.

- [ ] `uat-and-alignment` *(optional)* — Operator-driven Create + Test + Invite + Attach round-trip on a real Discord application, via browser-MCP-driven flow (chrome-devtools MCP registered per M11 environment requirements). Existing gleepglorp bot or a fresh test bot. Walks the new flow end-to-end; verifies invite URL produces a working bot reachable from the test guild; surfaces any HAT-time fixes. HAT-discovered fixes land in the flight-log under the relevant leg's Anomalies section. Any HAT-time fix that reverses a substrate contract (per M10 F8 L11 Fix #4 precedent and the `prompt-discipline-needs-mechanical-fallback` convention codified L1) pauses the flight and triggers fresh design review per the Adaptation Criteria above.

---

## Post-Flight

### Completion Checklist

- [ ] All required legs (L1-L6) completed
- [ ] L7 UAT completed or explicitly waived (operator decision)
- [ ] Code merged on `main`
- [ ] Tests passing (unit + Studio HAT browser tests, with display-text matchers updated to Discord vocabulary)
- [ ] `the_one/agents.md` updated with the six codified conventions
- [ ] Discord plugin no longer hardcodes intents at `_discord.py:619-622`
- [ ] Connector-form-registry shipped; generic kv-table fallback path verified for `'stub'`
- [ ] Discord-shaped form renders in create + edit modes
- [ ] Invite section ships with copyable URL
- [ ] Vocabulary substitution active on Discord connector surfaces

### Verification

**Mechanical verification** (CI / scripted):
- `pytest tests/test_connector_types_consistency.py` — pins Literal vs CONNECTOR_TYPES vs registry vs CHECK
- `pytest tests/test_db_models.py::TestConnectorAccount` — pins `config["intents"]` validator (if validation lands at Pydantic — depends on architect's resolution of the open question)
- `pytest tests/connectors/test_discord.py::TestConnect::test_intents_from_config` — pins plugin reads `config["intents"]` with documented defaults
- `pytest tests/interfaces/test_api_connector_accounts.py::TestCreate::test_discord_config_validation` — pins API rejects invalid `config["intents"]` shape
- Studio browser tests with display-text matchers updated to Discord vocabulary; `data-testid` matchers unaffected
- New unit test `tests/web/test_connector_form_registry.js` (or equivalent) — pins registry fallback for unregistered types

**Operational verification** (UAT leg):
- A fresh Discord connector account can be created end-to-end from Studio without consulting documentation or source
- The probe surfaces `application_id` and the Invite section renders a working invite URL
- The bot, once invited, is reachable and the agent receives a peer's message
- The intents toggle's effect on the invite URL's permission integer is consistent with Discord's required permissions for the operations the bot performs (channel send / read history / view / app commands)

**Methodology verification**:
- L1's codified conventions are referenceable by name in subsequent flights' design decisions (per M10 debrief recommendation #1)
- The connector-form-registry's fallback path is the empirical evidence that the substrate is genuinely additive for the second connector (per M10 mission criterion #2 deferred to M11 / future)
