# Sortie: Agent tool overrides

**Status**: ready

## Charter

### Outcome
An agent's Built-in tools tab refuses, on the field, a value that goes outside the app-wide setting and says where to change that setting; it stores only the values the operator actually changes and shows which values are the agent's own; an override overtaken by a later app-wide tightening is clipped to fit and the agent carries a notice; and the path fields say plainly how Shell and Python are (or aren't) limited.

### Why Now
The operator hit it on the Windows build (2026-10-27): an agent whose file tools were allowed only a folder under `\\wsl.localhost\<distro>\…` could not start a chat ("Cannot start chat: agent override widens FilesystemConfig.path_allowlist; '…' not within any tool entry"). The message named only a config shared by nine tools and pointed nowhere. The app-wide Allowed paths was `~`, so the WSL folder really was outside it; but the agent tab had accepted it on Save. Discovery also showed that with `~` alone the agent still reached the WSL folder, through `shell`: an agent's own paths never apply to Shell or Python on any platform, and on Windows nothing limits them at all (SECURITY-MODEL.md, M15 F3 DD9). Nothing in the tab says so. Separately, opening a tool's panel and saving copies the inherited app-wide values into the agent's override (the panel pre-fills them), so a later app-wide change can break agents nobody touched. Squawk 0257 (overrides stored without validation) is the API half of the same defect.

### Success Criteria
- [ ] Saving an agent with an override that goes outside the app-wide value is refused, in the editor and through the API: a plain sentence on that field names the tool and says where to change the app-wide setting, and nothing is saved. (Closes squawk 0257.)
- [ ] Opening a tool's panel on an agent and saving without changing a field stores no override for that field (confirmed by API read-back); each field shows whether it is inherited or the agent's own, with a one-step reset to inherited.
- [ ] When the app-wide value is tightened after an agent saved a narrower one, the agent keeps working at the intersection of the two (paths: what both allow; numbers: the lower; switches: off wins; denied paths: both lists joined), and a chat never fails because an override went stale. Settings › Built-in tools lists the agents a save would narrow before it saves. The agent carries a notice naming the tool, the field and what was dropped, shown in the chat's agent drawer, as an indicator on the agent editor's Built-in tools tab and on the agent's Agents list row, and on the field itself, with a one-step fix (accept the narrowed value, or reset to inherited). A notice cannot be dismissed; it clears when its cause is fixed.
- [ ] When an agent has Shell or Python enabled, its Allowed paths and Denied paths fields say how those tools are limited on this computer (in the Linux sandbox: by the app-wide paths, not the agent's; elsewhere: not at all) and that turning them off keeps the agent to its paths. (Widened from "On Windows" by operator decision, 2026-10-27, after recon found agent paths never reach Shell or Python on any platform.)
- [ ] A web tool that follows a redirect refuses a host the effective Allowed hosts or Denied hosts forbid, exactly as it refuses that host as the first URL. (Added by operator decision, 2026-10-27, after Architect review 1 found redirects skip both lists.)

### Constraints
- An agent override can still only narrow the app-wide setting; the security model does not change. Clipping never widens past either value, and never disables a tool: an allow list clipped to nothing means "allowed nowhere", never "inherit".
- Notices are derived by the server from current state, never stored, and cannot be dismissed. Their shape is general (a kind per notice); this sortie adds one kind.
- The app-wide Settings › Built-in tools editor gains only the before-save warning about affected agents.
- Windows default paths (Windows- and WSL-form denied paths, WSL access by default) are a separate item, not this sortie. So is making an agent's own paths fence Shell and Python in the Linux sandbox.
- Paths in the sortie's documents are de-identified: no operator username or home path.
- Execution waits until Mission 31 has completed and shipped (operator, 2026-10-27).

---

## Pre-Flight

### Objective
Make agent tool overrides honest in both directions. On the way in, the server checks each new or changed override against the current app-wide value and refuses a widening or invalid one with a 422 the agent tab shows on the field. While stored, an override holds only what the operator changed: the tab stops copying inherited values, denied lists hold only the agent's additions, and a one-time cleanup removes the copies earlier saves made. After the operator tightens an app-wide value, the agent is built with its override clipped to the intersection instead of failing. The server derives a notice that the chat drawer, the editor's Built-in tools tab, the Agents list row and the field all show, with a one-step fix; Settings › Built-in tools previews which agents a save would narrow. Finally, the path fields tell the truth about Shell, Python and downloads.

### Open Questions
- [x] Following vs pinning? → **own once changed** (operator, 2026-10-27; DD9). A field is inherited until edited; once edited it is stored, even if equal to the app-wide value, until Reset.
- [x] Overrides already copied in by the pre-fill defect? → **one-time cleanup** at first start (operator, 2026-10-27; DD13).
- [x] One folder for all nine file tools in one step? → **out of scope** (Flight Director recommendation, not contested). Each file tool keeps its own app-wide row and its own agent override (`builtins.py:195-200` resolves per tool name).
- [x] HAT leg? → **yes, on Linux**, a scratch dev instance (operator, 2026-10-27; leg 5).
- [x] Agent paths never limit Shell/Python on any platform: scope? → **tell everywhere**; fencing Shell with the agent's paths in the Linux sandbox is a separate item (operator, 2026-10-27; DD10).
- [x] Stale-override policy? → **clip and tell, never disable** (operator, 2026-10-27; DD2, DD6).
- [x] An empty path intersection: offer "Use narrowed value"? → **no** (Architect review 1). An own empty list cannot survive the Save walk, which treats empty as inherit. Offering it would quietly widen the agent back to the app-wide list. The field offers Reset and says the tool can be turned off for the agent (DD9).
- [x] Notices for tools disabled for the agent or app-wide, or for fields the tab hides? → **no** (Architect review 1; DD6). They cannot be fixed on the tab, and notices cannot be dismissed. Their clips are logged.
- [x] Redirects bypass `host_allowlist` and `host_denylist` (Architect review 1, pre-existing): `_url_check` runs only on the first URL (`web.py:176,274,404`); the transport re-checks only the SSRF block list on each hop (`_web_config.py:483-530`). → **fold in** (operator, 2026-10-27; DD15, criterion 5)

### Design Decisions

**DD1. One rule set, two entry points: strict `resolve`, new `clip_override`.** `resolver.resolve` keeps raising on a widening or invalid override, and the save path uses it (DD5). MCP's Substitute-only path (`mcp/_tool_provider.py:158,169`) is untouched. A new pure function `clip_override(schema, tool_config, agent_override) -> ClipResult` (in `the_one/tools/resolver.py`) returns the override narrowed to fit, plus a list of changes (field, kind `narrowed` | `invalid` | `coupled`, dropped values, effective value). The build path (DD7), notices (DD6), the Settings impact preview (DD8) and the cleanup (DD13) all call it, so there is one definition of "what fits". `clip_override` is **total**: it never raises for any JSON value in an override. That covers strings for ints, fractional floats, non-list paths, non-string entries, `~nosuchuser` paths, symlink loops and NUL bytes. Canonicalisation failures are caught as `RuntimeError`, `OSError` and `ValueError`: the type differs by Python version and platform (a symlink loop is `RuntimeError` on 3.12 and `OSError` on 3.13; `ntpath.realpath` re-raises some `OSError`s for UNC paths). `ClipResult.override` never gains a key the input lacked; `coupled` changes are report-only (DD2). Property tests over arbitrary JSON pin three things: `clip_override` never raises; `resolve(clip_override(...).override)` never raises; the effective value is never wider than the app-wide value, nor wider than the agent's value wherever that value is interpretable (an uninterpretable value never applied, because `resolve` raised on it, so only the app-wide bound is meaningful for it).
- Rationale: keeping `resolve` strict leaves every existing caller, and the guarantee that overrides only narrow, intact. The clip is a separate, testable step in front of it.
- Trade-off: two functions to keep in step. The property tests and the shared per-marker helpers mitigate it.

**DD2. Clip rules, per marker.** The rules apply to keys present in the override; an omitted key inherits, as today.

| Marker / field | Fits when | Clip to |
|---|---|---|
| `Narrow` bool | agent ≤ app-wide (`False` < `True`) | `False` (off wins) |
| `Narrow` int/float | agent ≤ app-wide | the app-wide value (the lower) |
| `Narrow` list (subset): `extra_allowed_hosts` | agent ⊆ app-wide | agent ∩ app-wide (empty is a valid "no extras") |
| `NarrowAnyWhenEmpty` list: `host_allowlist` (DD4) | empty means "any host" on **both** sides; a list containing `NO_HOSTS` means "no hosts" and always fits. Otherwise fits when the app-wide list is empty, or the agent list is non-empty and ⊆ app-wide | agent `[]` against a non-empty app-wide list: the app-wide list (any ∩ app-wide). Otherwise agent ∩ app-wide; if that is empty, the reserved `NO_HOSTS` entry (DD4) |
| `NarrowPrefix` paths: `path_allowlist` | each agent entry within some app-wide entry | the prefix-set intersection. For each pair (agent `a`, app-wide `o`), keep `a` if `a` is within `o`, and keep `o` if `o` is within `a`; de-duplicate. Empty means "allowed nowhere": an empty allow list refuses every path (`filesystem.py:251-255`) |
| `NarrowSuperset` denied lists | always (DD3) | resolved as a union; for `path_denylist`, an entry that cannot be canonicalised is dropped (kind `invalid`): no canonical path can fall under it, so dropping it widens nothing, and `FilesystemConfig.model_post_init` (`filesystem.py:160`) would otherwise raise at build |
| `Substitute` | always | no clip |
| no marker / several markers (e.g. `redirect_cap`, `WebSearchConfig` fields) | never agent-settable | key dropped (kind `invalid`; it never applied, because `resolve` raised on it) |
| a value the marker cannot interpret, or one outside the schema's bounds | never | **lists:** bad entries are dropped one at a time (non-strings, and paths that cannot be canonicalised, in allow and deny lists alike); an allow list emptied that way becomes `[]` (paths) or `[NO_HOSTS]` (hosts), never inherit. **A non-list value on a list field:** an allow list clips to its strictest value (`[]` for `path_allowlist` and `extra_allowed_hosts`, `[NO_HOSTS]` for `host_allowlist`); a deny list drops the key (the union with the app-wide list still holds). **Numbers:** clamped into the schema's bounds; a non-number drops the key, so it inherits the app-wide value (it never applied). All kind `invalid` |

**Default follows a lower maximum.** `resolve` applies this to the merged dict before `model_validate`: when the merged `timeout_seconds_max` (`execution.py:312`, `_web_config.py:278`) is below a `timeout_seconds_default` the agent did not set, the effective default is lowered to the max. `clip_override` reports it as kind `coupled` (report-only, not a notice) and never writes it into the override. Legacy data with both own and default > max clips the default to the max (kind `invalid`). An agent that sets only `timeout_seconds_max: 10` while inheriting a default of 30 is a valid narrowing. An agent that sets both, with default > max, is a 422 on `timeout_seconds_default`. When the app-wide max is tightened below an agent's own default, the clip lowers it (kind `narrowed`, a notice). Before this sortie the pre-fill copied the default too, which hid this case.
- Rationale: each rule moves only toward the stricter of the two values, so a clip can never grant what either the operator or the agent withheld. The path intersection keeps a tightened subfolder when the agent had its parent (agent `~`, app-wide tightened to `~/work` gives `~/work`), which a filter would wrongly empty. The prefix intersection equals the set intersection of subtrees under `is_within` (Architect review 1).
- Trade-off: the agent's value is reinterpreted rather than kept; the notice (DD6) is how the operator learns of it.

**DD3. Denied lists store only the agent's additions; resolve joins them with the app-wide list.** `NarrowSuperset` fields (`path_denylist`, `command_denylist`, `host_denylist`) resolve to app-wide ∪ agent, and `_check_narrow_superset` no longer raises. The tab still shows the app-wide entries as locked chips, but saves only the agent's own entries: `readValue` keeps returning the union, and the Save walk subtracts the locked chips (DD9).
- Rationale: "store only what you change" (criterion 2) is impossible while the check demands that the agent list contain every app-wide entry (`resolver.py:172-192`; the tab saves the full union, `tool-config-fields.js:423-456`). A union is the "join" clip by construction: a new app-wide denied entry reaches every agent with no notice. A union can never hold fewer denied entries than the app-wide list (Architect review 1). Stored full unions from before stay valid, because a union is idempotent; the cleanup strips them anyway (DD13).
- Trade-off: a denied-list override can no longer be "widening", so the tests that pin a raise on a dropped default entry change to pin the union (Verification).

**DD4. `host_allowlist`: empty means "any host", and "no hosts" is enforced in code.** A new marker `NarrowAnyWhenEmpty` replaces `Narrow` on `host_allowlist` only. It goes in the resolver, the `x_marker` map (`api.py:519-537`) and the client's `allowed()` (`tool-config-fields.js:81-86`). Without that last change the field is flagged dead and dropped on Save (`tools-tab.js:164-176`). Its rules are in DD2's table.

"No hosts" is a single constant, `NO_HOSTS = "none.invalid"`, defined in `the_one/tools/resolver.py` beside `NarrowAnyWhenEmpty` and imported by `_web_config.py` (the reverse would be a circular import: `_web_config.py:53` and `execution.py:44` import the markers from the resolver). `_url_check` refuses **every** host when the allowlist contains it. A unit test pins that refusal **without** DNS, so the guarantee never rests on `.invalid` failing to resolve: search domains, NXDOMAIN hijacking and hosts files can all make it resolve (Architect review 1). The field and the notice show it as "no hosts", never as an editable chip.
- Rationale: an agent `[]` against a non-empty app-wide list resolves to "any host" today (`_check_narrow` treats `[]` as a subset of anything, `resolver.py:139-146`). That hole is live through the API, with no test. Conversely, any agent list against the default empty app-wide list is refused as widening, though it is narrower. And an empty `host_allowlist` means any host (`_web_config.py:350`), so "nothing allowed" needs its own enforced value.
- **Leg ordering:** the client's `allowed()` change ships in the same leg as the marker (leg 1), or the browser lanes break between legs.
- Trade-off: a reserved value inside a user-visible list.

**DD5. Save validation: new or changed fields only, a 422 on the field.** `create_agent` and `update_agent` (`api.py:1008`, `:1059`) run strict `resolve` after `AgentConfig.model_validate`. They check every tool field in `tool_overrides` that is new, or that differs from the stored agent's value; on create, that is every field.
- **"Changed"** is decided per field by JSON-canonical comparison with the stored value (`json.dumps(..., sort_keys=True)`, so `True` ≠ `1` and `5` ≠ `5.0`). A list edited while it still holds a stale entry counts as changed as a whole, so the stale entry is refused. No unchanged field can widen the effective value, because the build always clips (DD7).
- **The check uses the current stored app-wide config, per field, over the whole new override.** For each changed field, the field's own marker rule is checked on its own (so every failing field is reported, not just the first), and then the whole merged config is validated so cross-field rules apply. A cross-field failure (default > max, whose pydantic `loc` is `()`) is attributed to whichever of `timeout_seconds_default` / `timeout_seconds_max` changed, `timeout_seconds_default` if both did. Path entries are canonicalised one at a time in the check, so a canonicalisation error is attributed to its field. Catch order matters: pydantic's `ValidationError` subclasses `ValueError`, so it is caught first, then `OverrideWidensError`, then `ValueError`, `RuntimeError`, `OSError` and `NotImplementedError`.
- **Every failure** maps to `detail = [{"type": "tool_override", "loc": ["tool_overrides", <tool>, <field>], "msg": <sentence>}]`, one entry per failing field. That covers:
  - the new structured `OverrideWidensError(ValueError)` (tool, field, marker, offending value; its `str` keeps today's text, so message-pinning tests and logs are unchanged);
  - pydantic `ValidationError` (bounds or type: squawk 0257's negative timeout), using its `loc`;
  - `NotImplementedError` (a type mismatch, `resolver.py:147-150`);
  - the "no marker" `ValueError` (`resolver.py:244-248`);
  - `RuntimeError` / `OSError` / `ValueError` from path canonicalisation (`~nosuchuser`, a symlink loop, a NUL byte; `paths.py:40`, `filesystem.py:160`).

  Each has a test.
- **An unknown tool name** in a new or changed tool entry is a 422 on `["tool_overrides", <tool>]`. Unchanged stored entries naming a tool removed since are carried, as the tab carries them (`agent-form-data.js:237-241`). Unknown field keys stay ignored (`extra="ignore"`, as today).
- **Unchanged stored entries are not re-checked.** If they no longer fit, they are clipped at build (DD7) and noticed (DD6), so a stale override never blocks saving an unrelated field.
- **Sentences** name the tool as Settings shows it and the field by its schema `title`. For example: "`\\server\share\proj` is outside read_file's app-wide Allowed paths. Add it in Settings › Built-in tools › read_file first." Or: "Maximum timeout can be at most 120 for shell, the app-wide value."
- Rationale: the save check mirrors sortie 06's "check what was sent" rule for legacy data, and the structured error keeps one source of truth.
- Trade-off: a stale stored entry survives a save untouched. This is deliberate: it is clipped and flagged instead.

**DD6. Notices: derived per response, never stored.** Each of the five `_agent_response` callers (`list_agents`, `get_agent`, create, update, rename; `api.py:925,936,1055,1135,1204`) passes in `notices: [...]`.
- **How they are computed:** `clip_override` runs over the agent's overrides against one `ToolConfigRepository.list()` per request, in `asyncio.to_thread` (path canonicalisation is blocking), memoised in a bounded (LRU) cache on a fingerprint of (override, tool-config row). The scope filter below (enabled tools, rendered fields) is applied outside the cached part. The clip also depends on disk state (`is_within` resolves symlinks), so a symlink change can leave a cached notice stale until either input changes; that is accepted and documented. This departs from the `kb_tool_names` precedent, which skips list reads (`_agent_response`, `api.py:205`). The list response needs notices because the drawer, the Agents list and Jump to all read the list-shaped `agents` store. The thread plus memo keeps that read off the event loop and cheap when nothing changed. That matters on the operator's Windows setup, where resolving `\\wsl.localhost\…` can start the distro.
- **Shape:** `{"kind": "tool_override_narrowed", "tool", "field", "field_title", "dropped": [...], "effective": <value>, "message": <sentence>}`. Path entries in `effective` are in canonical form, so the notice shows what was actually checked. Example sentence: "read_file's Allowed paths was narrowed by the app-wide setting: `\\server\share\proj` no longer applies."
- **What raises a notice:** only a `narrowed` or `invalid` change, on a field the agent tab renders (overridable, not hidden by the tool's `config_fields`), for a tool enabled both for the agent and app-wide. Clips on hidden fields or disabled tools still apply at build and are logged, but raise no notice: a notice that cannot be fixed on the tab could never clear.
- **No dismiss route exists.** `kind` is the general hook for later notices; this sortie adds only this one.
- **A stored `host_allowlist: []` clipped to the app-wide list** has nothing literal to report as dropped, so its notice gets its own sentence: "read_file's Allowed hosts was any host; the app-wide setting now limits it to its own list."
- Rationale: derived state cannot drift from its cause, and clears itself when the operator fixes either side, or turns the tool off for the agent.
- Trade-off: a memo to invalidate correctly. The fingerprint includes both inputs, so a change on either side recomputes.

**DD7. The build path clips; failure paths stop failing silently.**
- **Clipping at build:** `BuiltinToolProvider.get_tools` (`builtins.py:195-200`) passes each override through `clip_override` before `resolve`. So `AgentFactory.create`, `describe_my_capabilities` (`projection.py:88`), the context-window route (`api.py:939-940`) and connector chats no longer raise on a stale override; DD1's totality means no override can make a build fail at all.
- **Logging:** a clip that changes anything logs one warning naming agent, tool, field and what was dropped. It is rate-limited per (agent, tool, field, dropped), since every join and every connector message rebuilds.
- **Hardening for the other build failures** (provider errors and the like):
  - `_restore_session` (`app.py:1597-1678`, which today catches only the provider and agent-not-found errors) returns a degraded `RestoredSession` with a new status `build_failed`, which `RestoredSession.is_degraded` (`app.py:1514-1518`) includes (otherwise `join` falls through to the not-found branch). The WebSocket `join` then sends `_build_session_joined_degraded` (`app.py:1903`): the history shows, with the reason. This replaces today's unhandled exception, which drops the socket (`app.py:3146`; the loop catches only `WebSocketDisconnect`, `:3461`). It also leaves the client state machine on a frame it understands (`session-state.js:182,242`), and covers the same restore in `POST /api/chat` (`app.py:3069`, which returns `{"error": "session_<status>"}` for a degraded restore).
  - **The client half:** the degraded frame gains a `reason` sentence (`_build_session_joined_degraded` sends none today, `app.py:1903-1925`). `chat.js`'s `setSessionHealth` (`:465-472` since M31 F6 split the chat area, today a banner and disabled input only for `agent_deleted` and `provider_missing`) and `session-state.js`'s `DEGRADED_REASONS` (`:55-58`; unknown statuses fall back to "This chat cannot start.", `:219`) gain `build_failed`: a banner with the reason, set with `textContent`, and input disabled. A `chats`-lane test pins it.
  - Connector inbound (`connectors/inbound.py:480-483`) catches any build exception, not only the three factory errors, and logs it with the agent name. There is no reply to the peer: that is out of scope.
- Rationale: criterion 3, "a chat never fails because an override went stale", plus the two paths where any build failure is worst today (a dead socket, a silent drop).

**DD8. Settings impact preview and refresh.**
- **A new read-only route,** `POST /api/tools/configs/{name}/impact`, sits behind the credential gate like every other route.
  - Its body is the proposed config in the PUT's shape. It goes through the same computation as the PUT (a helper extracted from the PUT's `api.py:742-756`: `_merge_hidden_fields` (`:570`) plus the hidden-value fallback), so the preview equals what the PUT would store. An invalid body gets the PUT's 422.
  - The response is `{"agents": [{"agent", "fields": [{"field", "field_title", "dropped"}]}]}`. It lists agents whose notice set for that tool would gain or change a narrowing under the proposed config compared with the current one, using DD6's notice rules.
- **The Settings editor's `save()`** (`areas/admin/tools-editor.js:404-435`) calls the route first. A non-empty answer opens `App.confirmDialog` ("Saving narrows 2 agents", with the list; Save anyway / Cancel). Cancel leaves the form dirty.
- **After a successful save, and after the tile's on/off switch** (an `enabled`-only PUT, which changes which notices exist under DD6's scope), the host invalidates `App.store` `agents` (nothing in `areas/admin/` does today), so the drawer, the list and the editor's notices refresh.
- Rationale: the warning arrives while the operator can still act. No dry-run endpoint exists today, and a separate read-only route keeps the PUT's contract unchanged.
- Trade-off: one extra request per save, and only tightenings are listed.

**DD9. The agent tab: inherited vs own.**
- **Field state:** a field is **own** when its key is in the stored override, **inherited** otherwise.
  - Inherited fields show the app-wide value with an "Inherited from Settings" line.
  - Editing a field makes it own, even if the value equals the app-wide one (the operator's pinning decision).
  - An own field shows "This agent's own" and a **Reset** button that returns it to inherited. The state shows in text, not only in style.
- **The Save walk** (`agent-form-data.js:211-257`) stores own fields only, replacing today's "every non-empty field". Denied lists store only the agent's added chips (DD3: the union minus the locked chips). Clearing an own list returns it to inherited, as today (`agent-form-data.js:225-227`), so "allowed nowhere" and "no hosts" are never typed by the operator, only produced by a clip.
- **A clipped field** (from `agent.notices`) shows a warning line: "Narrowed by the app-wide setting: … no longer applies."
  - It offers **Use narrowed value**, which makes the canonical effective value the field's own, and **Reset to inherited**.
  - When the effective value is empty or `NO_HOSTS`, it offers only Reset, and adds "or turn this tool off for this agent". An own empty value cannot survive the walk, so "Use narrowed value" would quietly inherit the app-wide list (Architect review 1). A tool turned off for the agent raises no notices (DD6), so its notice clears.
- **A save-time 422** on `loc ["tool_overrides", tool, field]` selects the Built-in tools tab, opens that tool's panel and sets the field's error. The agent editor's error mapping (`agent-editor-controller.js:89`, today `['name']` only) gains this three-segment `loc`, because `App.api.fieldErrors` matches single segments only (`api.js:105-109`).
- **An unchanged own number is exempt from the browser's range check.** In agent mode a Narrow integer gets `max = operatorValue` (`tool-config-fields.js:386-387`), checked by `invalidMessage` (`:212-217`) and enforced by `blockingError()` (`agent-form-data.js:334-349`). Left as is, an own value the app-wide max has since undercut would block every Save of the agent, against DD5. The check applies only to a value the operator changed; the clipped-field line covers the unchanged one.
- **Dead keys** (stored, not overridable) are dropped on Save, as today (`data-tool-override-dead`). Hidden-field keys are carried, as today (M31 F4 L05c).
- Rationale: criterion 2. Field state comes from key presence, so no schema change is needed.

**DD10. A note on Shell, Python and download paths (all platforms).**
- **The server half:** `GET /api/config` (`api.py:599`) gains `execution_sandbox: "bubblewrap" | "passthrough"`. It comes from `platform/sandbox/factory.py::describe_selection()`, warmed once in the lifespan via `asyncio.to_thread`: the first call runs a blocking `bwrap` probe of up to 5 s (`factory.py:117-127`), and only the probe is cached after that. `GET /api/config` reads the warmed value, and calls through `asyncio.to_thread` if a request arrives before the warm-up finishes, so it never blocks the loop. The test bypass reports passthrough. The unit test monkeypatches the selection for both values (it depends on `sys.platform`, `bwrap` on PATH, the userns knob and the bypass env vars, `factory.py:145-163`), never the host's own.
- **When the note shows:** when the agent's enabled set includes `shell`, `python_exec`, `shell_session_start` or `download_file` and that tool is also enabled app-wide (`tools-tab.js::enabledSetFor`, `:93-107`, ignores the app-wide switch, so the check adds it). Every Allowed paths and Denied paths field on the tab then carries a note:
  - bubblewrap: "Shell, Python and downloads don't use this agent's paths. Without host access, Shell and Python run in an empty sandbox; with host access, and for downloads, read_file's app-wide paths apply. Turn them off for this agent to keep it to these paths."
  - passthrough: "On this computer, Shell and Python aren't limited by any paths, and downloads use read_file's app-wide paths. Turn them off for this agent to keep it to these paths."
- Rationale: both statements describe what the code does. The cross-config view is resolved from the first FilesystemConfig tool, `read_file`, with no agent override (`builtins.py:153-168`, order asserted at `:96`). `host_access` uses that view (`shell.py:94,113-117`), and so does `DownloadFileTool` (`web.py:394`). Non-Linux hosts get `PassthroughSandbox`. The posture is a server fact, so the browser's OS is never consulted.
- Trade-off: the sandbox backend name is exposed to the client, which is credential-gated and single-user. The wording still needs the operator's eye at the HAT.

**DD11. Indicators in the control library.**
- **`App.ui.tabs`** gains a per-item `indicator` option and a `setIndicator(id, label | null)` method. They render a dot inside the tab button plus visually hidden text, so the tab's accessible name reads "Built-in tools, 1 notice".
- **`App.ui.listPane` rows:** M31 F6 L10b added `item.activity` (`'working' | 'new'`, `rowStyle 'chats'` only): an aria-hidden fixed slot beside the time plus a separate visually hidden text run after `nameSuffix` (", New reply"), patched in place by `setItems`. The agent row's notice extends that pattern (for example a `notice` value or a third activity state, rendered in the default row style) rather than inventing a second one; `badges`/`nameSuffix` remain the fallback.
- **Colour is never the only cue.**
- **Library requirements:** each new option gets its catalogue row update in `docs/ui-control-inventory.md` (owned classes) and contract tests in Chromium and WebKit (`test_ui_tabs_contract.py`, `test_ui_library_contract.py`).
- **Consumers:**
  - the agent editor sets the Built-in tools tab indicator from `agent.notices`;
  - the Agents list (`agents-list.js:76-93`) marks the row from the list response;
  - the tools tab flags the tool's panel header.

**DD12. The drawer's notices group.** `areas/chat/agent-drawer.js` renders a "Needs attention" group (testid `chat-drawer-notices`) between the facts and "What it can use", only when `agent.notices` is non-empty. It shows one sentence per notice and a link to `#agents/{name}/tools`. It is read-only, like the Rules and Notes groups. It refreshes through the drawer's existing `agents` store subscription (the drawer reads the list-shaped agent, `agent-drawer.js:258-260`), which DD6 and DD8 keep current.

**DD13. One-time cleanup of copied values.** A startup step after the name repair (`app.py`, beside `repair_unsafe_names`) runs **once ever**. It is recorded in `app_metadata` under `tool_override_cleanup_v1` in a `finally` once the agent loop has started, **including when individual agents failed or the step itself failed partway**. Re-running it would undo pins made since (DD9). A failed agent is logged by name and keeps its copies, which are valid values that just act as pins.
- **For each agent and each tool entry:**
  - drop a field whose value equals the effective app-wide value (the stored row merged over schema defaults; scalars by JSON-canonical equality, lists as sets of strings);
  - strip app-wide entries from denied lists (no change in effect, DD3);
  - drop dead keys (no marker; they never applied);
  - drop emptied tool entries.
- **Saving** goes through `SQLiteAgentStore`, so encrypted fields round-trip.
- **Never raises:** each per-agent step and the step as a whole are guarded, and one injected-failure test per call site pins that (sortie 06 recommendation 3). A test also pins that the marker is written after a partial failure, and that a second start changes nothing.
- **Known limitation, named in the release notes:** a copy of an app-wide value the operator has since changed no longer matches, so it stays as a pin.
- **Test databases:** the step also runs on fresh test instances, so leg 3 checks that no existing test relies on overrides equal to the defaults surviving startup (`copy_template` pre-seeds).
- Rationale: the operator chose a cleanup. Copies cannot be told apart from deliberate equal values, and following is the safe default for them.
- Trade-off: a deliberate pin equal to today's app-wide value reverts to following.

**DD15. Every hop is checked against the host lists.** The host part of `_url_check` (allow list with `NO_HOSTS`, deny list) is factored into `_host_policy_check(host, cfg)`. `SSRFGuardedTransport` gains optional `host_allowlist` / `host_denylist` arguments, and `handle_async_request` runs that check on **every** request before its SSRF logic, so a redirect hop (httpx sends each one through the transport, streaming included, `_client.py:1679-1730`) is refused exactly like a first URL.
- **Pin on a copy.** Today the transport pins by rewriting the caller's request in place (`request.url = request.url.copy_with(host=ip)`, `_web_config.py:518-526`), and httpx builds the next hop from that same object, resolving a relative `Location` against it (`response.request = request`; `_redirect_url`). So a `Location: /next` hop would arrive with the IP as its host and be refused by a non-empty allow list (Architect review 2 reproduced it). The transport instead builds a new `httpx.Request` for the IP URL, with `sni_hostname` and `Host`, and passes that to `super()`, leaving the caller's `request.url` as the hostname. This also stops `sni_hostname` leaking into later hops through the copied `extensions`. The check must never treat an IP hop as its carried `sni_hostname`: an absolute redirect to any IP would inherit the allowed name.
- **One host normalisation.** `_url_check` reads `urlparse(...).hostname` (which keeps an `xn--` form as given) and httpx decodes `request.url.host` to Unicode, so both checks compare through one helper: lowercase IDNA ASCII, applied to the host and to the list entries. Each web tool's `_build_transport(cfg)` (`http_request` `web.py:152`, `fetch_url` `:262`, `download_file` `:385`; called at `:177,275,406`) passes the resolved, effective `WebConfig` lists. Tool tests that monkeypatch `_build_transport` with an `httpx.MockTransport` bypass the transport by design, so the hop tests use the real transport under a real `httpx.AsyncClient(follow_redirects=True)`. A test against a local server needs `127.0.0.1` in `extra_allowed_hosts`, and that branch skips the pin (`_web_config.py:507-508`), so the pin path is tested with the existing seams `_patch_getaddrinfo` and `_patch_super_dispatch` (`tests/test_web_helpers.py:285-317`) and a relative `Location`. The search backends (`_search_backends.py:238,303`) pass none and keep today's behaviour: they call fixed engine hosts and have no host lists. A refused hop returns the tools' existing `[error] [constraint] …` shape, naming the redirect target.
- Rationale: criterion 5; an agent narrowed to `docs.example.com` must not reach another public host through a 3xx. The check sits in the transport because that is the one place every hop passes, as the SSRF check already does.
- Trade-off: a site that redirects to a CDN host outside the allow list now fails; the operator adds the host. Release notes say so.

**DD14. Docs.**
- **`the_one/agents.md`:**
  - the tool authorship contract (`:1203-1225`);
  - the constraint surface (`:1229-1244`);
  - the Built-in tools tab paragraph (`:2242`), which says the PUT does not validate and that min and max are never checked in the browser (already stale, Architect review 2);
  - the squawk 0223 rule (`:2231`);
  - a new "Agent override validation and clipping" block.
- **`SECURITY-MODEL.md`:**
  - the Tool Execution Boundary (`:605-640`);
  - the Windows section (`:827-854`) gains that an agent's own paths never reach Shell, Python or downloads (they use read_file's app-wide row), and that web_search's SSRF policy uses the app-wide `extra_allowed_hosts` (`builtins.py:189-192`); the Tool Execution Boundary gains that the host lists apply to every redirect hop (DD15).
- **`CLAUDE.md`:** the agent-PUT watch-out (`:81`).
- **`docs/ui-control-inventory.md`:** DD11.
- **The next release notes:** the save refusal, clipping and notices, the cleanup with its limitation, and redirects now checked against the host lists (DD15).

### Citation Audit

Verified against the working tree at `142dbee` by the Flight Director (2026-10-27) and re-checked by Architect review 1 unless marked; re-checked against `c236622` after the rebase (2026-10-28). Of the cited files, only `api.py`, `app.py`, `connectors/inbound.py`, `agent-editor-controller.js`, `ui/list-pane.js`, `agent-drawer.js`, `chat.js`, `tools-editor.js`, `tools-page.js`, `agents.md` and `CLAUDE.md` changed; their rows carry the new lines, and every cited mechanism still holds.

| Citation | Status |
|---|---|
| `the_one/tools/resolver.py::_check_narrow_prefix` — raises `ValueError` "agent override widens …; '…' not within any tool entry" when an agent entry is within no tool entry (DD1, DD5) | verified |
| `the_one/tools/resolver.py::_check_narrow_superset` — raises when a tool entry is missing from the agent list; plain `==` membership (DD3) | verified |
| `the_one/tools/resolver.py::_check_narrow` list branch (`:139-146`) — subset check; `[]` passes against anything (DD4) | verified (Architect) |
| `the_one/platform/paths.py::is_within` — canonicalises both (`expanduser().resolve()`) then `relative_to`; `expanduser` raises `RuntimeError` on `~nosuchuser` (DD2, DD5) | verified |
| `the_one/tools/filesystem.py::_filesystem_check` — `in_allowlist = any(...)` over the canonical allowlist; an empty list refuses every path (DD2) | verified |
| `the_one/tools/builtins.py::BuiltinToolProvider.get_tools` — cross-config view resolved per Config from the first tool name with a `None` override (`:153-168`); per-tool `resolve(cls.Config, tool_configs.get(name), agent_overrides.get(name))` (`:195-200`) (DD7, DD10) | verified |
| `the_one/tools/shell.py::ShellTool.execute` — reads `self._cross_configs[FilesystemConfig]`; `host_access` uses it for `_cwd_check` and `_build_tool_profile` (DD10) | verified |
| `the_one/tools/web.py:394` — `DownloadFileTool` writes through `self._cross_configs[FilesystemConfig]` (DD10) | verified (Architect) |
| `static/js/areas/shared/tool-config-fields.js::seedValue` — agent value, else `''` (Substitute), a copy of the operator list (NarrowSuperset), the operator value otherwise (DD9) | verified |
| `static/js/areas/studio/agent-form-data.js` walk `:211-257` — stores every non-empty rendered field; skips `null`/`[]`/`''`; carries unopened tools (DD9) | verified |
| `the_one/interfaces/web/api.py::update_agent` — preserve-on-omit `tool_overrides`, then `AgentConfig.model_validate`, guards, `store.save`; no override validation (DD5) | verified |
| `the_one/interfaces/web/api.py` `_agent_response` (`:205`) callers — exactly five (`:925,936,1055,1135,1204`); no self-configuration route returns an agent (DD6) | verified at `c236622` |
| `the_one/interfaces/web/api.py::get_config` (`:599`) — returns `dev_mode`, `version` and two context thresholds (DD10) | verified |
| `the_one/platform/sandbox/factory.py::describe_selection` — `(name, reason)` via `_select`, no logging; non-Linux gives passthrough; the userns probe is a blocking `subprocess.run(..., timeout=5)`, cached only after its first call (DD10) | verified (corrected by Architect review 1) |
| `the_one/tools/_web_config.py` `:350` — `if cfg.host_allowlist and host not in cfg.host_allowlist` (empty = any host) (DD4) | verified |
| `the_one/tools/_web_config.py` `SSRFGuardedTransport.handle_async_request` (`:483-530`) — re-checks the SSRF block list per request, but not `host_allowlist`/`host_denylist`; `_url_check` runs only on the first URL (`web.py:176,274,404`) (Open Questions) | verified |
| `the_one/tools/web.py` `_build_transport` (`:152,262,385`) — each returns `SSRFGuardedTransport(extra_allowed_hosts=cfg.extra_allowed_hosts)`; called at `:177,275,406`; tests monkeypatch it (DD15) | verified |
| `the_one/tools/execution.py:312`, `the_one/tools/_web_config.py:278` — `model_validator(mode="after")` default ≤ max (DD2) | verified |
| `the_one/interfaces/web/app.py:3146` — `join` awaits `_get_or_restore_session(session_id)`; the loop catches only `WebSocketDisconnect` (`:3461`); `_restore_session` (`:1597-1678`) catches only the provider and agent-not-found errors; `RestoredSession.is_degraded` (`:1514-1518`); `_build_session_joined_degraded` (`:1903`) sends no reason (DD7) | verified at `c236622` |
| `static/js/areas/chat.js:465-472` `setSessionHealth`, `session-state.js:55-58,219` `DEGRADED_REASONS` — a banner only for `agent_deleted`/`provider_missing`; unknown statuses fall back to "This chat cannot start." (DD7) | verified at `c236622` |
| `the_one/tools/_web_config.py:518-526` — the transport pins by mutating `request.url` in place; httpx resolves a relative `Location` against that request (DD15) | verified (Architect review 2, with a mock-transport repro) |
| `the_one/tools/filesystem.py:160` — `model_post_init` canonicalises `path_denylist`; `~nosuchuser` raises `RuntimeError` there (DD2) | verified (Architect review 2) |
| `static/js/areas/shared/tool-config-fields.js:386-387,212-217`, `agent-form-data.js:334-349` — agent-mode Narrow int `max = operatorValue`, enforced by `blockingError()` (DD9) | verified (Architect review 2) |
| `static/js/areas/chat/session-state.js:182,242` — `joining` ends only on `session_joined` / `join_failed` (DD7) | verified (Architect) |
| `the_one/connectors/inbound.py:480-483` — catches only `AgentNotFoundError, ProviderNotFoundError, ProviderNotConfiguredError` (DD7) | verified |
| `the_one/naming.py::name_rule_detail` — pydantic-shaped `[{"type","loc":[loc],"msg"}]` (DD5 shape precedent) | verified |
| `static/js/api.js::fieldErrors` — strips a leading `body`; the first `loc` segment found in `names` wins (DD9) | verified |
| `static/js/ui/tabs.js` — no indicator, badge or dot option (DD11) | verified (grep) |
| `the_one/interfaces/web/api.py:519-537` — `x_marker` map names `NarrowPrefix`, `NarrowSuperset` (DD4) | verified |
| `areas/chat/agent-drawer.js:258-260` — the drawer reads the agent from `App.store.peek('agents')` (DD12) | verified (Architect) |
| `areas/admin/tools-editor.js:404-435` `save()`; nothing in `areas/admin/` invalidates `agents` (DD8) | verified (Architect) |
| `the_one/self_configuration/projection.py:86-94` — `describe_my_capabilities` calls `get_tools` with the agent's overrides (DD7) | verified (Architect) |

### Prerequisites
- [x] Mission 31 completed and shipped (operator, 2026-10-28; `main` at `c236622`, after v0.12.3).
- [x] Branch `sortie/07-agent-tool-overrides` rebased onto `main` at execution start (2026-10-28, onto `c236622`; Citation Audit re-checked). The worktree is `.claude/worktrees/sortie-tool-overrides`, created 2026-10-27 from `main` at `142dbee`. After the rebase, re-check the Citation Audit against the new base: M31 F6 touches `chat.js`, the drawer's neighbourhood and the chat session state. Each leg's design also re-checks the rows it touches, in case other work lands on `main` between legs.
- [ ] The worktree's own `.venv` built and **every gated lane baselined** before leg 1, in that venv: the unit tier plus the `--parallel 3` browser lanes (sortie 06 debrief, recommendation 2; squawk 0241's fresh-install failures are expected).

### Pre-Flight Checklist
- [x] All open questions resolved
- [x] Design decisions documented
- [x] Citation Audit complete — every code-asserting design decision verified
- [ ] Prerequisites verified (at execution start)
- [x] Validation approach defined
- [x] Legs defined

---

## In-Flight

### Technical Approach
The server goes first, so every later leg builds on a single rule set.
- **Leg 1** adds the total clip function, the union and any-when-empty semantics with the enforced `NO_HOSTS` (and the client's `allowed()` change for the new marker), the default-follows-max coupling, structured save errors on every failure type, derived notices (threaded and memoised), the build-path clip and the two failure-path fixes with the `build_failed` client half. It closes squawk 0257.
- **Leg 2** checks the host lists on every redirect hop, with the pin-on-a-copy fix and its transport tests (DD15). It is a separate leg because it changes the SSRF transport, a different risk from the override rules, and gets its own review.
- **Leg 3** rebuilds the agent tab's field states and Save walk on those contracts, adds the Shell/Python note (with its `/api/config` field), and runs the one-time cleanup. "Stop copying" and "remove the copies" are one success criterion.
- **Leg 4** adds the library indicators and wires the notice surfaces, the impact route (both halves) and the Settings warning.
- **Leg 5** is the HAT.

### Checkpoints
- [ ] Leg 1: no override can make a build fail (property tests); a widening or invalid one is a 422 on its field (API); `NO_HOSTS` refuses with no DNS; a broken chat rejoins degraded with its reason.
- [ ] Leg 2: a redirect hop obeys the host lists, and a relative redirect on a pinned host still works.
- [ ] Leg 3: open-and-save stores nothing; inherited/own/Reset work; the note shows by sandbox posture; the cleanup runs once and never raises.
- [ ] Leg 4: tightening in Settings warns, and the notice appears in the drawer, tab, list row and field.
- [ ] Leg 5: HAT signed off.

### Adaptation Criteria

**Divert if**:
- Notices on list reads stay measurably slow even when threaded and memoised (for example, a cold `\\wsl.localhost\…` resolve on Windows). Fall back to notices on the detail route plus a lightweight `has_notices` on the list. That is a design change, so it goes back to the operator.
- The impact preview cannot be made exact for some marker without duplicating clip logic outside `clip_override`.
- A property test finds a clip that widens past either value.

**Acceptable variations**:
- Notice and note wording, within one plain sentence each.
- The indicator's visual form (dot, small count), as long as the accessible name stays "{tab}, {n} notice(s)".
- Where the "Inherited from Settings" text sits on a field.
- The list-row indicator riding existing `badges`/`nameSuffix` rather than a new option (DD11).

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses. This list will evolve based on discoveries during implementation.

- [ ] `override-rules` - Server: total `clip_override` and its table, default-follows-max (DD1, DD2), denied-list union (DD3), `NarrowAnyWhenEmpty` with code-enforced `NO_HOSTS` (DD4), save-time 422 on changed fields for every failure type (DD5), derived, threaded, memoised `notices` with their scope rules (DD6), build-path clip plus the `build_failed` restore (server and client, with a `chats`-lane test) and connector hardening (DD7), and the client's `allowed()` accepting the new marker; unit and property tests; closes squawk 0257.
- [ ] `redirect-hosts` - Host lists checked on every request in `SSRFGuardedTransport`, pinning on a copy of the request, one host normalisation (DD15); transport tests through the real pin path with a relative `Location`, plus allow, deny and `NO_HOSTS` hops; release-notes line.
- [ ] `agent-tab` - Inherited/own/Reset field states and the own-only Save walk with locked-chip subtraction (DD9), the clipped-field line and its fixes, three-segment 422 mapping, `execution_sandbox` in `/api/config` warmed in the lifespan, and the Shell/Python/download note (DD10); the once-ever startup cleanup with injected-failure tests (DD13); `agent-tabs` lane tests updated, with the posture pinned by stubbing `App.config.execution_sandbox`.
- [ ] `notice-surfaces` - The `App.ui.tabs` indicator and the list-row indicator, with catalogue rows and two-engine contract tests (DD11); the editor tab, Agents row and tool-panel flags; the drawer's notices group (DD12); the impact route sharing the PUT's config computation, the Settings before-save warning and the `agents` invalidation (DD8); docs and release notes (DD14).
- [ ] `hat` *(optional)* - A guided HAT on a Linux scratch dev instance: a refused widening; open-and-save stores nothing; own vs inherited and Reset; a Settings tightening with its warning; the notice in the drawer, tab, list row and field; both fixes, including the empty-intersection case; the paths note (first confirm `GET /api/config` or `the-one doctor`'s `sandbox:` line reads bubblewrap, then the bubblewrap wording live; passthrough wording checked on the served text); a redirect to a host outside an agent's Allowed hosts is refused.

---

## Post-Flight

### Completion Checklist
- [ ] All legs completed
- [ ] Code merged
- [ ] Tests passing
- [ ] Documentation updated
- [ ] Squawk 0257 completed

### Verification
- **Unit** (`make test-unit`):
  - **Clip rules:** the clip table per marker; the property tests (DD1: total over arbitrary JSON, `resolve(clip(...))` never raises, never wider than either input, with empty `host_allowlist` modelled as the universe); the denied-list union; `host_allowlist` any-when-empty in both directions; `NO_HOSTS` refusing with no DNS lookup; default-follows-max.
  - **Save 422:** shape and `loc` for every failure type, on changed fields only; an unchanged stale entry still saves.
  - **Notices:** on all five response routes; their scope rules (hidden fields, disabled tools); the memo invalidates when either input changes.
  - **Impact route:** it equals the PUT's computation.
  - **`/api/config`:** includes `execution_sandbox`, and the lifespan warm-up runs off the loop.
  - **Redirects (DD15):** through the real pin path (`_patch_getaddrinfo`, `_patch_super_dispatch`) under a real `httpx.AsyncClient(follow_redirects=True)`: a relative `Location` on an allowed, pinned host succeeds; a hop to a host outside the allow list, inside the deny list, or with `NO_HOSTS` set is refused; an absolute redirect to an IP never inherits the allowed name; a punycode and a Unicode spelling of one host match; the search backends are unchanged.
  - **Failure paths:** the `build_failed` restore over WebSocket `join` and `POST /api/chat`; the connector catch-all.
  - **Cleanup:** runs once; the marker is written after a partial failure; a second start changes nothing; injected failures at every call site.
  - **Existing tests that change** (Architect review 1 and recon):
    - `test_resolver.py:422-437`;
    - `test_filesystem_config.py:81-137`;
    - `test_execution_config.py:210-352`;
    - `test_web_config.py:160-236`;
    - `test_agent_tool_overrides_round_trip.py`;
    - `test_api_tool_configs.py:124` and `test_enrich_schema_with_markers.py:21-24` (`x_marker` on `host_allowlist`);
    - the marker references in `tests/browser/seeders.py`.
- **Browser:**
  - **`agent-tabs`:**
    - open-and-save stores nothing (API read-back);
    - an unchanged own number above a since-lowered app-wide max does not block Save;
    - inherited/own/Reset;
    - a widening 422 on the field;
    - the clipped line and both fixes;
    - the empty intersection, which offers no "Use narrowed value" (stored value asserted after each fix);
    - the paths note under both postures, pinned client-side;
    - `test_flow_studio_tool_overrides_preserved.py:135-149` and `test_flow_studio_tools_fields.py:97-101` re-pinned to additions-only.
  - **`settings-tools`:** the before-save warning lists agents; Cancel keeps the form dirty.
  - **`chats`:** the drawer's notices group appears and clears; a chat whose agent cannot be built rejoins degraded, with the reason in the banner and input disabled (leg 1).
  - **`agents`:** the list-row indicator.
  - **`contracts-controls`:** the new library options, in Chromium and WebKit (`THE_ONE_REQUIRE_WEBKIT=1`).
- **No behavior test.** Every criterion is observable through the API and the browser lanes on a scratch instance, and the HAT covers alignment. There is no out-of-process actor whose state the lanes cannot read.
- **HAT** (leg 5) on Linux, as above.
