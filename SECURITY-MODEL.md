# Security Model

This project is a single-user local development tool. The threat model and
security posture below are deliberate design choices, not gaps to fix.

## Threat Model

- **Audience**: solo developer/operator running the agent on their own
  machine. No multi-user scenarios. No internet exposure. No untrusted
  LLM-supplied tool inputs from external clients.
- **Trust boundary**: the operator is trusted. Tool inputs from agents are
  constrained by per-tool config (resolver-narrowed) but are NOT treated as
  hostile.
- **F3 Decision 10 — REVISED by Mission 20** (`missions/20-local-api-
  authentication/`, GitHub issue #165): originally "operator-trusted setup,
  NOT malicious filesystem actor," used to justify a fully unauthenticated
  local API. Mission 20 reconsidered that: on a loopback API with no
  credential at all, "trust the operator" collapsed in practice into "trust
  every local process, no matter who or what started it" — any other OS
  account, any lower-privilege process, or any page open in the operator's
  own browser could reach the API with nothing presented. The
  filesystem-actor premise itself is unchanged and is still inherited by F4
  / F5 / F6 (the operator still owns the local environment; the tool
  denylists are defense-in-depth against agent mistakes, not an attacker
  already on the machine — see "What This Model Excludes" below) — what
  changed is that the premise no longer, by itself, justifies an
  unauthenticated API. **What replaced it**: the credential gate under
  "Authentication" below. This is now the canonical citation for "should we
  add auth to the local API?" (already done — see Authentication); for
  other "should we add auth/sandboxing/...?" questions, the calibration
  above — narrow what "operator-trusted" is asked to cover, don't discard
  the premise — is the citable precedent.

## Authentication

Mission 20 (`missions/20-local-api-authentication/`) closed the gap recorded
above under F3 Decision 10: every HTTP request, `/static/*` asset, and
WebSocket upgrade now requires an identified caller, enforced by
`CredentialGateMiddleware` (`the_one/interfaces/web/middleware.py`) sitting
in front of the whole application.

**What this now protects against**: other local OS accounts reading or
driving the API; lower-privilege processes on the same machine; and
browser-vectored access — a hostile page open in the operator's browser can
no longer reach the loopback API at all, including via a plain `GET`, which
the Origin-allowlist layer below never gated on its own.

**What this does not protect against**: a process running *as the operator*
can read the credential file (`<data_dir>/api-credential`, mode `0600`) and
therefore has exactly the same access the operator has. This is not a
deficiency to caveat away — it is the boundary this mission deliberately
chose. The credential file rests on the same trust boundary as every other
operator secret this project stores (the encryption key, provider API keys):
OS file permissions, not a second factor. A future flight adding real
multi-user isolation would need to revisit this (see "Future Work" below).

- **Exactly two exemptions**: `GET /api/live`, a minimal liveness probe that
  returns `{"status": "ok"}` and nothing else — no version, no build info, no
  prompt text. `/api/info` was considered and rejected as the exemption
  instead: it returns `platform_sections` (the platform prompt text), and
  exempting it would have published that to every local process regardless
  of credential. `/api/info` is therefore credentialed like every other
  route; only the liveness probe and the OAuth callback below are reachable
  with nothing presented. The liveness exemption is what lets a pure "did
  the server come up yet" readiness wait — the desktop launcher's own
  just-started-server poll
  (`the_one/interfaces/desktop/shell.py::_wait_until_serving`) and the
  browser-test harness's equivalent (`tests/browser/conftest.py`) — succeed
  before either process holds or needs a credential. Callers asking a
  *different* question ("is that other instance out there mine?") still use
  the credentialed `/api/info`, deliberately: the desktop launcher's
  `_select_port` port classifier, `make verify-serving`, and CI
  packaged-smoke all send the credential and treat the response as proof of
  ownership, not just liveness.

  The second exemption, `GET /api/oauth/callback` (Mission 22 / Flight 01 /
  Leg 03, Design Decision Q3): the external IdP's redirect back to this
  path is a cross-site top-level navigation, on which the `SameSite=Strict`
  session cookie is withheld by spec, so the route cannot pass through the
  gate the normal way — without the exemption the redirect 401s before the
  handler runs and the pending OAuth flow times out. It is safe
  unauthenticated because its own single-use, SDK-generated, unguessable
  `state` token *is* the credential for this one path: the handler 401s on
  a missing/unknown `state`, mints no credential, sets no cookie, reads or
  writes no DB row, and consumes `state` on first use, so a caller cannot
  do anything with this route beyond resolving a pending flow whose `state`
  they already hold.

  **Bar for any future exemption**: both routes above were held to a
  four-part inertness checklist first — (a) no database read or write;
  (b) mints no credential and sets no cookie; (c) any accepted token is
  single-use and consumed on first use, so a replay is refused; (d) the
  route is registered GET-only, so any other method 405s at routing. A
  proposed exemption must document all four in the `EXEMPT_PATHS`
  comment block (`the_one/interfaces/web/middleware.py`) and be pinned
  by the route-methods test in `tests/test_credential_gate.py`.
- **Two credentials, two lifetimes — do not conflate them:**
  - A **long-lived, persisted credential** (`the_one/api_credential.py`),
    stored at `<data_dir>/api-credential` (mode `0600`, written with no
    world-readable window between creation and the permission landing).
    Presented as `Authorization: Bearer loc_<identifier>.<secret>` by every
    non-browser caller — CLI tooling, tests, `curl`, MCP-style automation.
    Created on first use; replaced via `the-one rotate-api-credential`.
  - A **single-use, short-lived browser-handoff credential**
    (`the_one/interfaces/web/handoff_store.py`), minted either in-process
    (the desktop launcher, which shares a process with the server) or via
    `POST /api/session/handoff` for a caller that already holds the
    long-lived credential but runs in a separate process (the browser-test
    harness, a behavior-test Executor) — that route's dependency checks the
    resolved caller's source is explicitly `file`, not just that some
    caller resolved, since Mission 21 added other resolvable sources. It
    travels only as a query
    parameter on a `GET /` document request — never anywhere else, and the
    long-lived credential is never accepted from a query parameter — because
    a URL is the one channel that reliably leaks (shell history, server
    logs, browser history, referrers), so only a value that is worthless
    after one use may travel there. It is consumed on its first successful
    use, expires a few minutes after minting if unused, and can never be
    replayed.
  - Consuming a handoff credential sets an `HttpOnly` session cookie
    (`the_one_session`) and redirects back to `/`; the cookie authenticates
    the browser from then on. The cookie is **stateless** — there is no
    session store. Its value is `<nonce>.<HMAC-SHA256(key=current
    long-lived secret, msg=nonce)>`, verified on every request by
    recomputing the HMAC against whatever the long-lived credential
    currently is. That is why a session survives a server restart (a fresh
    process reads the same file and recomputes the same HMAC) and why
    **rotating the long-lived credential drops every outstanding session at
    once** — rotation *is* the revocation mechanism; there is deliberately
    no separate revoke-a-session endpoint.
  - The cookie is `SameSite=Strict`, **not** the `Lax` default — this is
    load-bearing, not a style choice. `SameSite=Lax` still attaches a
    cookie to a cross-site *top-level navigation* using a safe method (an
    ordinary link click is enough). The Origin-allowlist layer below
    deliberately never gates `GET` — so `Lax` would leave exactly the gap
    this mission exists to close: a hostile page could top-level-navigate
    the operator's browser to a loopback `GET` path, arrive carrying a
    valid session cookie, and no origin check would run either. `Strict`
    closes that path entirely. Do not "simplify" this back to `Lax` without
    re-deriving this paragraph first.
- **Layering: the credential gate is outermost, the Origin allowlist is
  inside it.** A request with a missing or invalid credential is refused
  with **401** before the Origin-allowlist logic ever runs. A request that
  presents a *valid* credential from a disallowed origin reaches the
  Origin-allowlist layer and is refused there with **403**. The two checks
  are independent and run in series, not alternatives to each other.
- **The Origin-allowlist middleware is a layer beneath the credential gate,
  not an alternative to it.** (M06 F1 L5;
  `the_one/interfaces/web/middleware.py::OriginAllowlistMiddleware`.) It
  enforces same-origin requests on state-mutating methods
  (POST/PUT/PATCH/DELETE) and on WebSocket upgrade handshakes. Allowed
  origins default to `scheme://host:port` derived from
  `settings.host`/`settings.port`; operators behind a reverse proxy extend
  via `THE_ONE_ORIGIN_ALLOWLIST` (`.env.example` carries a commented
  example). `GET` requests and missing-`Origin` callers (curl,
  server-to-server) pass through this layer by design — that used to be a
  known, accepted gap; it is now exactly the gap the credential gate above
  closes for every route except its two exemptions. `/api/live` and
  `GET /api/oauth/callback` are the only requests that can reach this layer
  without the credential gate having already checked them: the former
  returns nothing sensitive by construction, and the latter is guarded by
  its own single-use `state` token instead (see "Exactly two exemptions"
  above) — so passing through unauthenticated here costs nothing for
  either.
- Provider URL validation (M06 F1 L5) refuses non-`https://` `base_url`
  values for non-localhost hosts at all three create/update/test endpoints
  (HTTP 422). `mock` and `ollama` provider types are skipped.

### Time-zone routes (M28 F1 L1)

`GET`/`PUT /api/time-settings` and `GET /api/time-zones` sit behind the same local-API credential gate as every other route. The zone string in a PUT is validated against the fixed name set read from the tzdata package (`the_one/time_zones.py::is_known_zone`) and is never used as a filesystem path or passed to a loader unvalidated, so `localtime`, `posixrules` and `../` forms are refused with a 422 whose detail echoes at most 64 characters of the offending value.

### Desktop window routes (M32 F2 L03)

`GET /api/window/state` and `POST /api/window/quit` are credential-gated and Origin-allowlisted like `POST /api/window/focus`, with no exemption, so the window routes (the destructive `POST /api/window/quit` included) share the existing posture: a page on another localhost origin that the Origin allowlist admits (default `http://127.0.0.1:*` / `http://localhost:*`) and that holds a valid session cookie can call them, exactly as it can every other route. `quit` only stops a desktop session that a credentialed caller could already control, so it grants nothing new. `POST /api/window/quit` answers `{quit, pid, state}` (`state` is `window`, `booting`, `browser` or null for a bare `serve`), so a credentialed caller learns this process's pid, which it could already learn from `GET /api/window/state`. `the-one quit` is the CLI client: it reads the credential with the read-only lookup (never creating one), sends it only to `settings.host:settings.port`, and prints one distinct line for a 401/403 (another program, or a different credential, holds the port) rather than retrying or falling back. `POST /api/window/focus` also accepts an optional `activation_token` (the launching desktop's `XDG_ACTIVATION_TOKEN` or `DESKTOP_STARTUP_ID`, at most 256 characters, printable ASCII without whitespace): it is opaque, used only to raise our own window through GTK's startup-id, never stored, and never logged in full (a short prefix at most). A newer launch that finds an older instance sharing our credential asks it to quit through the same credentialed route and waits for the reported pid to exit; it never signals a process, and starts no second server on the data directory if the old one does not go.

### Self-configuration surface (M21 F01 L02)

An agent may be given a loopback MCP source through which it can read its
own configuration (`the_one/self_configuration/`). This is **off by
default for every agent** — the operator opts an agent in from that
agent's own Self-configuration tab in Studio.

- **A second, distinct credential source.** The surface mints one
  `agt`-prefixed credential per enabled agent (shape mirrors the long-lived
  `loc`-prefixed operator credential above, but a different prefix so a
  token's type is legible at a glance). It lives ONLY inside that agent's
  surface row's encrypted `secrets["Authorization"]` — never on
  `AgentConfig`, never returned by the enable endpoint, and masked like
  every other MCP-source secret in every API response. Resolution goes
  through an in-memory registry (`identifier → (source_id, secret)`),
  rebuilt at process startup from every marked row and mutated in-process
  by enable/disable — there is no per-request DB read on this path.
- **Confined to its own mount path — this is the load-bearing property.**
  `CredentialGateMiddleware` resolves an `agt` credential to an identified
  caller exactly like any other registered source, but a caller whose
  `source` appears in `the_one/self_configuration/constants.py:
  CONFINED_SOURCE_PATHS` is admitted ONLY to HTTP requests under that
  source's mapped path prefix (`/mcp/self-configuration`) — every other
  path, and every WebSocket upgrade, is refused with 403. Without this, an
  `agt` credential would be a full operator credential under a different
  prefix: Mission 20's gate resolves any registered source to an
  identified caller and admits it everywhere by default, and that
  mission's debrief named exactly this hazard as the reason per-route
  scope enforcement was deferred ("harmless today; live the moment a
  second `CredentialSource` exists" — it has). `file` and the browser
  session cookie's `session` source are absent from the map and are
  admitted exactly as before this surface existed.
- **The tool catalog IS the write allowlist, by construction.** The surface
  exposes four tools: `get_my_configuration` and `describe_my_capabilities`
  (read-only — neither builds an `Agent`, which would recurse into the
  surface from inside the agent's own tool call, and neither returns a
  source config, URL, header, or secret; `get_my_configuration`'s
  projection is an explicit field list that never touches
  `tool_overrides`, `mcp_overrides`, `provider_config_id`, `kb_ids`, or
  `mcp_source_ids`), and `update_my_description` /
  `update_my_system_prompt` (M21 F01 L03 — the write path). No tool takes
  a field name; the allowlist is the catalog's shape, so a future
  `AgentConfig` field is unwritable because nothing addresses it.
- **The write path (M21 F01 L03): whole-value replacement, persist-first,
  deferred-apply.** Each write tool takes only `text` and `apply` —
  `apply` is `"next_turn"` (the running conversation adopts the revision
  when its current turn ends — never mid-turn, since the agent loop
  re-binds its request messages inside the same turn's iteration loop) or
  `"next_session"` (the running conversation is untouched; the revision
  is visible the next time the agent is rebuilt, e.g. a rejoin). Either
  way the revision is written to the stored `AgentConfig` row
  immediately, before any deferral — a `next_turn` entry in the
  in-process pending registry (`the_one/self_configuration/pending.py`,
  keyed by agent name) is therefore always redundant with what the store
  already holds, not the source of truth. Input is bounded, not
  content-policed: `text` must be a non-empty string of at most 64 KiB,
  `apply` one of the two literals — anything else is refused with no
  partial write. As of Flight 2 the write path is backed by a revision log
  (F02 L01) and an operator approval gate (F02 L02 — see the next bullet).
- **Approval mode is the operator gate on the mission's central write-risk
  (M21 F02 L02).** Each agent carries an operator-owned
  `self_revision_requires_approval` flag (a v35 `agents` column, default
  off; set only from the agent's Self-configuration tab, never reachable by
  the agent — no write tool addresses it and the read projection omits it).
  When it is **on**, a self-revision the agent proposes is NOT applied: it
  is held in the `agent_revisions` queue as a `pending` row (one per
  agent+field) and the tool returns a truthful, non-retry-inducing result
  that does not claim the change took effect. The operator sees a per-agent
  pending count and reviews each proposal (base→proposed) in the tab, then
  **approves** or **dismisses** it. Approve is **fail-closed**: the pending
  row records the field's value at capture (`base_value`); on approve the
  endpoint compares it to the current stored value and, if the field has
  drifted since the agent proposed, returns **409** with the current and
  proposed values (and the stale base) and writes nothing — the operator
  must explicitly override to overwrite the drifted value. An approved
  revision propagates next-session (the proposing turn's `apply` is moot
  and never replayed). Disabling the surface marks the agent's outstanding
  pending rows `superseded`, so a revision proposed under a since-revoked
  surface can never be approved afterward.
- **Restore is operator-direct and has no agent-facing tool (M21 F02 L03).**
  The operator can restore a description or system prompt to any earlier
  value the field actually held via `POST
  /api/agents/{name}/self-configuration/revisions/{id}/restore` (query
  `side=proposed|base`). Restore applies **immediately regardless of
  approval mode** — the operator is the approval authority, so a restore is
  never routed through the queue (DD5) — and is logged as a new
  `applied`/`restore` row with provenance (`restored_from`, and `base_value`
  = the pre-restore current value), never a pointer rewind. Its target must
  be an `applied` revision (a value the field genuinely took); a
  non-applied target is refused with 409. Crucially there is **no restore
  MCP tool** — the write allowlist (the tool catalog's shape) is unchanged,
  so an agent cannot restore itself, prompt-injected or otherwise. Restore
  is reachable only from the operator's Self-configuration tab, and holds
  the mission's "by construction" boundary: the agent's reach over its own
  configuration is exactly the four surface tools; rollback is
  operator-only.
- **Ownership is enforced server-side**, not merely by convention:
  `create_agent`/`update_agent` reject (422) any `mcp_source_ids` entry
  that is another agent's surface row, and reject (422) any
  `mcp_overrides` entry targeting a surface row that carries a credential
  key (`env`/`headers`/`bearer_token`) — an agent can never be handed a
  foreign or attacker-supplied credential through the override path. The
  admin MCP Sources screen hides these rows by default (`GET
  /api/mcp-sources` — pass `?include_agent_surfaces=1` to include them,
  which only the owning agent's own Studio tabs do); a direct `PUT` on a
  marked row is refused with 409, and `DELETE` performs the full disable
  rather than an ordinary row delete.
- **Indirect prompt injection is the surface's live residual risk**,
  recorded here rather than treated as closed. Any content an agent's
  *other* tools feed into its context (web fetch, MCP servers) can now,
  as of M21 F01 L03, instruct the agent to call
  `update_my_system_prompt` or `update_my_description` — nothing gates
  the write tools beyond the existing per-source/per-tool checkboxes an
  operator uses for every MCP tool. A prompt-injected agent that decides
  to revise its own guardrails does so with the SAME confinement,
  ownership, and input-bounds enforcement as a legitimate self-revision;
  none of those mechanisms distinguish agent intent from injected intent
  — they were never designed to. This is the mission's central,
  explicitly named risk. **As of M21 F02 L02, approval mode is the operator
  gate that closes it when armed:** with approval mode **on** for an agent,
  a prompt-injected write is held in the pending queue and cannot take
  effect until the operator approves it — the fail-closed staleness check
  further ensures an approval can never silently overwrite a value that
  drifted since the agent proposed. With approval mode **off**, the residual
  risk remains live and unmitigated by this gate; the standing mitigations
  are then the same ones that govern any other MCP tool — the operator can
  withhold `update_my_description` / `update_my_system_prompt` from a
  specific agent via the per-tool checkboxes on that agent's MCPs tab, or
  disable the surface entirely from its Self-configuration tab. Approval
  mode is therefore the recommended posture for any agent whose context can
  carry attacker-influenced content.

### Agent notes (M27 F2)

An agent may be given three tools, `save_note`, `update_note` and `forget_note`,
that write a short list of saved notes (`agent_notes`). The notes are shown to
the agent at the start of every later conversation. This is **off by default
for every agent**; the operator turns it on per agent (`notes_enabled`, an
operator-owned `agents` column that no agent tool and no
`get_my_configuration` projection can reach).

- **The threat: ungated, persistent writes.** There is **no approval gate by
  design**. A note an agent writes takes effect at once and persists. Notes are
  **shared agent-wide**, so a note written in one conversation (a web chat, a
  connector DM, a channel) is shown to the agent in **every later conversation,
  including other peers' and other DMs'**. Content that reaches the agent in
  one conversation (a fetched page, an MCP result, a connector peer's message)
  can therefore try to plant an instruction that the agent later reads as its
  own memory in a conversation with someone else.
- **Mitigations.**
  - *Off by default*, and re-checked inside the write transaction, so an
    already-built agent stops writing the moment the operator turns it off.
  - *Provenance.* Every note records its origin (`web`, `connector`, `other`;
    the session, platform and peer) and an **"unverified" flag**. The flag is
    set when content not from the operator was in the conversation the model had
    seen: any tool result outside a small trusted set (the notes tools,
    `search_tools`, `continue`; every other tool, including future ones, is
    untrusted), any connector-peer message, or a turn started by a connector
    peer. The scan runs over the agent's whole message list before the call, so
    it covers earlier turns and a restored history, finds the call by id
    **backwards** (Ollama ids repeat across turns), and attributes results by
    position. It fails closed ("unknown position", "unknown tool", "unknown
    context") whenever it cannot place the call. An agent update never clears
    the flag; it ORs in the new taint and merges the sources. An **operator
    edit that changes the text clears the flag and its sources** (the operator
    reviewed and rewrote the note; `updated_by` becomes `operator`); an
    identical-text save is a no-op and keeps the flag. A later agent update in
    a tainted conversation flags it again.
  - *The prompt block is bounded and delimited.* Notes are rendered inside
    `<saved_notes>` with a heading that says they are reference material, not
    instructions; flagged notes read `(unverified)`. Every note is collapsed to
    one line at write (so it cannot forge a `[n]` line) and the block's
    delimiters are neutralised inside a note.
  - *Limits.* 400 characters a note, 4,000 in total, 5 writes per turn (a
    duplicate does not count); refusals are tool errors, so they show as errors
    in the tool stream.
  - *Rules outrank notes.* The prompt states that the operator's rules take
    precedence over any note. No agent path writes rules or the switch.
- **Residual risks (accepted, recorded).**
  - **Flags do not propagate through notes.** A note read into a conversation
    is not itself counted as outside content, so a note written later from an
    unflagged conversation that merely repeats a flagged note comes out
    unflagged.
  - **Every connector-conversation note is flagged**, so the flag is a weaker
    signal there.
  - **Outside text that bypasses the scan:** MCP tool names and descriptions
    (in `tools=` and in `search_tools` output) and KB tool names reach the
    model outside the message list, so they are not counted.
  - **A flagged note can still be followed.** The model may act on a planted
    note's content even though it is marked unverified. The control is the
    operator's review of the notes list (the "Check this" badge), not the flag.
  - A turn resumed after an authentication pause gets a fresh write budget.
- The deterministic contract is `tests/test_notes_tools.py`
  (`test_planted_instruction_never_yields_an_unflagged_note`).

### External-client access to the self-configuration surface (M21 F03)

Everything above concerns the agent's OWN `agt`-prefixed principal reaching
its surface over the loopback. Mission 21 Flight 3 adds a **second principal
on the same surface**: an external client (a script, a CI job, a separate
service) that the operator explicitly grants access to tune one agent. This
is **off until the operator grants it** — grants are minted from the agent's
own Self-configuration tab and only while the surface is enabled — and it
reuses the surface's existing confinement, tool catalog, and input/ownership
bounds wholesale, differing only in credential lifecycle and write
provenance.

- **A distinct, per-grant `ext`-prefixed credential.** Each grant mints its
  own `ext_<id>.<secret>` credential — a different prefix from both the
  `loc` operator credential and the `agt` self-configuration credential, so a
  token's type is legible at a glance and every other registered credential
  source rejects it on prefix mismatch. It resolves to exactly one agent's
  surface row but is a SEPARATE identity from that agent's `agt` credential,
  so it can be revoked or rotated on its own. An agent can hold many external
  grants at once, each independently revocable — unlike the single `agt`
  credential per agent.
- **A secrets-bearing store, Fernet-encrypted at rest.** The `agt` credential
  lives inside its surface row's encrypted `secrets["Authorization"]`;
  external credentials get their own table, `agent_external_credentials`
  (schema v36), whose `secret` column is Fernet-encrypted with the same key
  as every other secret surface. The operator-facing list projection is
  **secret-free** (`{identifier, label, created_at}` only — the public
  `ext_` identifier, never the token), and the `ext_<id>.<secret>` token is
  returned **exactly once**, at mint (and again only on rotate); no read path
  returns it again. Resolution goes through an in-memory
  `identifier → (source_id, secret)` registry rebuilt at startup and mutated
  live on mint/revoke/rotate — the same no-per-request-DB-read shape the
  `agt` path uses.
- **The SAME confinement, via a second confined `CredentialSource`.** The
  external source (`self-configuration-external`) shares the
  `/mcp/self-configuration` mount and is a second entry in
  `CONFINED_SOURCE_PATHS` pointing at that same prefix, so it inherits Flight
  1's confinement UNCHANGED — no new enforcement code. A caller bearing an
  `ext` credential is admitted ONLY to requests under `/mcp/self-configuration`
  and refused (403) everywhere else, and every WebSocket upgrade from it is
  refused outright. **Governance invariant:** an external principal reaches
  ONLY the four confined MCP tools (`get_my_configuration`,
  `describe_my_capabilities`, `update_my_description`,
  `update_my_system_prompt`); the operator control plane — every `/api/...`
  route and admin surface — answers it with **403**, exactly as it does the
  agent's own `agt` credential.
- **Per-principal revoke and rotate**, in contrast to the operator
  credential's rotate-everything. Revoke hard-deletes one grant's row and
  evicts its registry entry, so the next request bearing that token is 401
  with no restart; rotate revokes the old credential and mints a fresh one
  for the same label/agent, returning the new token once and invalidating the
  old immediately. A cross-ID guard ensures a grant can only be revoked or
  rotated through its OWN agent's route, and neither operation ever touches
  the agent's `agt` credential or a sibling external grant.
- **FK-cascade auto-revoke on surface-disable / agent-delete (DD9).** The
  credential rows FK on the surface ROW (`source_id REFERENCES
  mcp_sources(id) ON DELETE CASCADE`), not on the agent name. Disabling the
  surface or deleting the agent deletes that row, so the FK cascade
  auto-revokes every external grant for that agent — an external principal
  can never outlive the operator closing the surface. (An agent rename keeps
  the row id stable, so grants survive a rename untouched.)
- **External writes are provenance-tagged and honor the approval gate.** A
  write from an external principal is recorded in the F02 revision log with
  `source='external'` and `source_principal` = the `ext_` identifier (the
  agent's own writes are `source='self'`, `source_principal` NULL), so the
  log answers "which external principal tuned this agent." External writes
  pass through the SAME per-agent `self_revision_requires_approval` gate as
  self-writes: with approval mode on, an external client's proposal is held
  in the pending queue and cannot take effect until the operator approves it
  — the residual prompt-injection risk and its approval-mode mitigation
  described above apply identically whether the write originates from the
  agent itself or from an external client.
- **Operational trace: mint/revoke/rotate and cascade-revoke are all
  operator-readable INFO log lines, not a durable tombstone (Flight 01 Leg
  2, Q2).** The route layer logs one INFO line per mint / revoke / rotate
  (agent name, `ext_` identifier, label, and the identified caller — never
  the secret); `manage.disable` and `manage.cascade_delete` each log one
  INFO line at the two points a credential row disappears WITHOUT an
  explicit revoke (surface disable, agent delete), naming the evicted
  identifiers and their count, since the FK cascade has already removed the
  store rows by the time either function runs. A `revoked_at` tombstone
  column was considered and rejected: `agent_external_credentials.source_id`
  is `ON DELETE CASCADE`, so a tombstone would record operator revokes but
  not cascades — a half-record unless the FK itself changed. A queryable
  audit trail is an events table, a separate initiative from this flight. **This
  log-line field set (agent, identifier, label, principal; identifiers +
  count at cascade points) is the convention future credential-lifecycle
  logging follows.**

## Connector Channel Contract (Mission 23 Flight 2)

The connector subsystem (`the_one/connectors/`) bridges external chat
platforms (Discord lands Flight 3; the stub plugin under
`the_one/connectors/stub.py` is a dev/test-only fixture, never registered in
production) to the agent loop. It introduces a new class of caller — a
platform peer, who is by construction untrusted relative to the operator —
so admission and authorization are separate concerns from the operator-vs-API
model above.

**Admission (DD-2/DD-3)**: a flat, per-connector allowlist —
`Connector.config["allowlist"]` holds `peers` and `channels` lists.
`the_one/connectors/inbound.py::is_admitted` checks membership before
anything else runs; an unadmitted sender's message is silently dropped —
nothing is persisted, no chat session is created, no agent turn runs. The
one exception is a correctly-typed pairing code: `POST
/api/connectors/{id}/pairing-code` (operator-only, behind the credential
gate) mints a short hex code with a 10-minute TTL
(`ConnectorManager.PAIRING_TTL_SECONDS`), held in-memory keyed by connector
id. An unadmitted DM whose body matches the live code consumes it
atomically (no `await` between check and consume, so concurrent submissions
resolve first-caller-wins) and appends the sender to `allowlist.peers` —
the *only* side effect an unadmitted sender can trigger. A second
submission of an already-consumed (or expired, or wrong) code is a silent
no-op, same as any other unadmitted message.

**Reply policy (DD-6)** is a separate, non-security gate layered on top of
admission: an admitted sender still only gets a reply when the message is a
DM, `@mention`s the bot, or targets a channel on `config["always_listen"]`.
This bounds agent-loop invocations (and therefore LLM spend), not access —
an admitted-but-not-replied-to message still passed the allowlist check
above.

**Send-tool authorization (DD-4)** — `the_one/tools/connector_send.py`'s
`SendToPlatformChannelTool.execute()` re-checks the live `Connector` row at
call time (not cached at agent-construction time), and the rule is a union
across the two target shapes:

- **Channel target**: sendable by the agent named in `channel_map[channel_id]`
  if that channel has a mapping, else by `default_agent` — i.e. the same
  agent that would have *received* an inbound message on that channel is the
  only one authorized to send on it.
- **DM target**: sendable *only* by `default_agent` — `channel_map` never
  applies to DMs (DD-4) — and only to a peer already on
  `allowlist.peers`. An agent cannot DM an unpaired peer even if it is
  `default_agent`.

Any other calling agent, or any DM target not on the allowlist, gets a
`[error] [constraint] ...` string back (never an exception) — the same
binding-derived check the doctor probe's warnings surface proactively
(`_connector_doctor_warnings` in `the_one/interfaces/web/api.py`: a missing
`default_agent`, or a `default_agent` that exists but lacks the send tool
enabled, both render as operator-visible warnings rather than failing
silently at send time). `the_one/tools/connector_history.py`'s
`fetch_channel_history` (DD-8, optional per-plugin) is authorized
identically.

**Dual-gated test seams**: `POST /api/_test/stub/inbound` and
`GET /api/_test/stub/outbound` require **both** `settings.dev_mode` and
`THE_ONE_STUB_TEST_ENDPOINT=1` — mirroring the purge-sweep test seam's risk
profile, because these seams
inject free text into a live agent loop with real LLM calls and tool
execution. `THE_ONE_STUB_TEST_ENDPOINT=1` also gates `"stub"`'s entry in
`GET /api/connectors/types` (so it cannot be created outside a dev/test
instance) and the lifespan-startup hook that registers `StubPlugin`
(`the_one/interfaces/web/app.py`). All three gates share one env var by
design — there is no way to open one without the others. The retired
pre-reset name `THE_ONE_REGISTER_STUB_CONNECTOR` is fully gone, not
resurrected. `POST /api/_test/oauth/pending` is likewise dual-gated, with its own flag `THE_ONE_OAUTH_TEST_ENDPOINT=1` (squawk 0146).

**Credentials, masking, and rotation**: `Connector.secrets` (the platform
token/credential) is Fernet-encrypted at rest, masked on every response via
the same `_mask_secrets`/`_looks_masked` helpers the MCP-source and provider
PUT handlers use (per-key `__MASKED__` round-trip; a masked sentinel on
*create* is rejected with 422 — there is no stored secret yet to preserve).
`POST /api/connectors` and `PUT /api/connectors/{id}` both restart the
connector's listener from the just-persisted row — a `PUT` unconditionally
stops the old listener and starts a fresh one, so no listener ever survives
on stale credentials (the "save reconnects the gateway" convention).
`POST /api/encryption/rotate` re-encrypts every connector row's `secrets`
blob as one of the rotation's corpora, then stops and restarts every
currently-tracked listener from a freshly re-fetched (post-rotation) row —
see `the_one/agents.md` "Encryption-rotation invariant" for the full
seven-corpora contract and `ConnectorManager._run`'s per-reconnect
fresh-row re-fetch (the DD-Q3 fix that keeps a long-lived listener from
reconnecting on secrets decrypted before a rotation).

## Network Bind

- Default `host=127.0.0.1` (localhost only). Host-native (`the-one serve` /
  `make up`) binds this default, so the dev server is reachable only on the
  loopback unless the operator overrides `THE_ONE_HOST`. Exposing the app on a
  routable interface is the operator's choice and the operator owns host
  firewalling.
- A future production form factor (e.g., desktop app) reverts to
  localhost-only. Any deployment exposing the app over a network is
  responsible for fronting it with a reverse proxy that adds auth — that
  configuration is out of scope for this project.

## MCP client transport: trust store, redirects and issuers (Mission 29)

The MCP client runs on the `mcp` 2.x SDK, which is built on `httpx2` (a separate
package from the `httpx` the rest of the app uses). Three security-relevant
consequences, all deliberate:

- **TLS trust store.** `httpx2` verifies TLS against the **operating system's
  trust store** (through `truststore`), where `httpx` (web fetch, LLM SDKs, the
  rest of the app) uses the bundled `certifi` roots. A root the OS trusts but
  `certifi` does not (an enterprise CA, a locally installed development root)
  therefore works for MCP servers and not for the rest of the app, and the
  reverse. Setting `SSL_CERT_FILE` or `SSL_CERT_DIR` overrides the choice for
  `httpx2` (it then uses that file or directory), the same variables operators
  already use for other Python HTTP clients. Tests that touch TLS or trust
  settings clear both variables explicitly. Accepted by the operator
  (2026-10-12).
- **Redirects.** The MCP path follows only same-origin, method-preserving
  redirects (a POST follows 307/308 to the same scheme, host and port; the GET
  stream follows any status to the same origin). A cross-origin redirect is not
  followed and the request fails with a plain error naming the location, so a
  server cannot bounce the client's credentials (the `Authorization` header, the
  OAuth token) to a third origin by redirecting. The client's
  `follow_redirects` setting is not consulted; the former `follow_redirects:
  True` was dropped as inert.
- **Authorization-server issuer binding (RFC 8414, RFC 9207).** Sign-in checks
  that the authorization server's metadata names the issuer it was discovered
  at, drops stored client credentials that were registered for a *different*
  issuer (so another server is never handed this server's registration), and,
  when the server advertises `authorization_response_iss_parameter_supported`,
  requires the redirect's `iss` to equal the metadata issuer by simple string
  comparison. `GET /api/oauth/callback` therefore forwards an optional `iss`
  query parameter to the pending flow; it is validated by the SDK and never
  used as an identifier or a path. A mismatch, or a missing `iss` when
  advertised, fails the sign-in with the existing plain sign-in-required error.
  Registrations stored by earlier versions record no issuer and are treated as
  unbound.

The one-megabyte cap on a single server-sent event (a tool result or listing
larger than that fails with a plain error naming the limit) also bounds how much
a hostile server can make the client buffer per event.

## Routines (Mission 33)

A routine is an operator-defined scheduled prompt (`the_one/routines/`). What it adds to the threat model:

- **Unattended turns run with the agent's full tool access.** A scheduled run is an ordinary agent turn started by the scheduler instead of a person, so it can use every tool the agent has (including the shell and file tools under the agent's configured containment) with no human watching. The operator who creates a routine is authorizing that.
- **A connector routine posts with no human present.** Its reply goes to the connector chat's own platform target. Only the agent's final reply is posted, never the routine's prompt.
- **The authorized-agent rule.** Before a connector run starts, the target connector must exist, be connected and have the routine's agent as the answering agent for that channel; otherwise the run fails with a recorded reason and no chat is created.
- **Every outcome is recorded.** Each run, including missed, skipped, interrupted and failed ones, has a row in `agent_routine_runs` with a plain reason; nothing is silently dropped, except the accepted one-occurrence loss in a crash between a routine's advance write and its spawn (`agents.md` "Routines (M33)").
- **Routines are operator-written by default.** An agent can write its own only while the operator turns on its Routines item (below).

### Agent self-scheduling (Flight 2)

**The threat is persistence of injected instructions.** A routine is a prompt that runs later, unattended, with the agent's full tool access. If outside text (a web page, a connector message, a tool result) talks an agent into scheduling one, the instruction outlives the conversation it came in through. The controls below make that visible and bounded; they do not make it impossible.

- **The switch.** Each agent has an operator-owned Routines item, off by default and unreachable by the agent. With it off, the four tools (`list_my_routines`, `schedule_routine`, `change_routine`, `cancel_routine`) are not registered, and the `default` agent never has them. Every write also re-reads the switch at call time (`agent_change`), so a cached agent built while it was on refuses once it is off. Turning it on reaches an already-open web chat only after the agent is rebuilt.
- **Approval, on by default.** With approval on, an agent's change is not applied: it becomes a `pending` proposal in `agent_routine_proposals` that the operator approves or dismisses. Approval re-validates against the routine as it is now (a stale check; a delete is checked too), re-runs the caps, and is fail-closed. With approval off, the change applies at once and is recorded as `applied`.
- **The proposals record is kept for the agent's retention window.** It is the audit trail of every agent routine change (applied, pending, dismissed, superseded, with the agent's untrusted flag and the chat it came from). The retention sweep and Purge now delete only resolved rows (the sweep those older than the agent's cutoff, Purge now all of them); pending rows are never deleted, and there is no count-based pruning (M33 F3, DD4).
- **The "Check this" flag.** A routine or proposal written by an agent is flagged `untrusted` (with its sources) when the model had seen content not from the operator. Untrusted means: any tool result from a tool not in `TRUSTED_TOOL_NAMES` (the notes tools, the four routine tools, `current_time`, `search_tools`, `continue`), a connector peer message (`peer:{name}`; in a connector chat every agent routine write is flagged, including the operator's own DM, which fails closed), an unknown position or context, and routine text that was itself flagged. Routine content taints the whole conversation, not only the turn: when a routine runs, the flag it had at that moment is **snapshotted onto the run's user message** (`routine_untrusted_sources`; `[]` when unflagged), so every later turn in that chat, a restart or a rebuilt connector agent still reads it; clearing the routine's flag or deleting the routine later does not un-taint text already in a chat. A pre-existing marker with no snapshot counts as unflagged. `list_my_routines` is trusted only while nothing it returned was flagged: when anything listed is flagged its first line is a fixed sentinel, stored in the message, and a result containing it is untrusted (`routine:listed`) in every later turn. Planted text can only add the sentinel (flag more), never remove it. The write tools echo only the routine id and the text the agent itself passed, never a stored name or prompt, and never a chat title or channel name, so a trusted tool's result cannot carry planted text. An agent write to an operator-made routine ORs the flag into the whole routine.
- **Clearing the flag** is the operator's act: saving a routine with its prompt through the REST `PUT` (the Routines tab form always sends the prompt for a flagged routine). Toggling, Run now and approving a proposal do not clear it.
- **Caps** (`routines/limits.py`, every write, operator or agent, raise-only so a larger set can always be edited down): 50 active routines (enabled and not Done) and 200 routines that are not Done, checked in the repository's write transaction, at proposal time and again at approval (a pending create past a cap is refused 422 and stays pending); Done routines count toward neither. There is deliberately no runs-a-day cap (M33 F3, DD3): a worst-case total is bounded by the 50 active routines and the one-minute floor of the calendar recurrence, and an operator who wants fewer runs lowers the count. Agent writes also carry 5 routine changes per turn (a counter on the turn context; a write with no chat turn is refused), a one-off at least a minute ahead and within a year, and 20 pending proposals.

**Residual risks.** An approved routine, or one applied with approval off, runs with the agent's full tool access: approval is only as good as the operator's reading of it. A flagged routine's run is only flagged, never blocked, and the flag marks what it writes afterwards rather than preventing it. A routine whose run schedules more routines is bounded by the active and per-turn caps, not prevented. Turning the item on reaches an open web chat only after a rebuild. The operator's own connector DM is flagged like any peer (an allowlisted-peer exemption is a recorded option, not built).

## Ollama library and registry fetches

The Pull Model control makes outbound requests from the server to three URL shapes: `https://ollama.com/library` and `https://ollama.com/api/tags` (the catalog of pullable models; fixed URLs, redirects are followed, and the response is only parsed, never acted on: every name and tag it yields is validated before any manifest URL is built) and `https://registry.ollama.ai/v2/library/{name}/manifests/{tag}` (each entry's exact download size; fixed host, no redirects). The hosts are module constants; no part of any host or path is user-controlled. The model `name` and `tag` that reach a manifest URL, whether parsed from the library page or supplied to `GET /api/ollama-library/size?model=`, must first pass an anchored allowlist (`re.fullmatch`, the operator-supplied-identifier rule above: names `[a-z0-9][a-z0-9._-]{0,127}`, tags `[A-Za-z0-9][A-Za-z0-9._-]{0,127}`, a single path segment); a failing entry is dropped and logged, and the size route answers 422. Manifest requests do not follow redirects (a 3xx is treated as "size unknown"); the listing fetches do. Nothing is sent about the operator or their Ollama server, and the pull itself (`POST /api/providers/{id}/models/pull`) is unchanged. Sizes and the listing are cached on disk in `{data_dir}/ollama-sizes.json` (public catalog data, no secrets). See `the_one/agents.md` "Ollama pull catalog".

## Tool Execution Boundary

The per-category Pydantic Configs (`FilesystemConfig`, `ExecutionConfig`,
`PythonExecConfig`, `WebConfig`) and the resolver semantics
(`Narrow`/`NarrowPrefix`/`NarrowSuperset`/`Substitute`) are documented in
detail in [CLAUDE.md](CLAUDE.md) under "Tool Configuration Layer (M05
Flight 2)". The security-relevant invariants are:

- **Filesystem (M05 F3)**: per-tool path allowlist + denylist (default
  19-entry curated denylist covering system secrets, browser/app data,
  agent internals), read-size cap, binary-file refusal. See
  [CLAUDE.md](CLAUDE.md) "Filesystem constraint surface (F3)".
- **Execution (M05 F4)**: timeout/output caps, command denylist
  (trip-wire, not fence — see CLAUDE.md), per-agent PTY session isolation
  keyed on `(agent_name, session_id)`, per-call denylist re-check on
  `shell_session_send` so agents cannot pre-stage a denylisted command
  behind an open session.
- **Subprocess environment**: hardcoded 8-key allowlist (`PATH`, `HOME`,
  `USER`, `LOGNAME`, `LANG`, `LC_ALL`, `TERM`, `TZ`) lives at
  `the_one/platform/env.py` and is **NOT operator-configurable** by
  design. The allowlist is enforced at the tool layer: `ShellTool`
  (`the_one/tools/shell.py`) and `PythonExecTool`
  (`the_one/tools/python_exec.py`) each call `_build_subprocess_env()`
  and pass the filtered env through the sandbox seam; `pty.py::UnixPtySession`
  builds `_build_subprocess_env()` in the parent and passes it through
  `get_sandbox_backend().prepare_spawn(...)` identically (M14 F2) — all
  four spawn paths are now covered.
- **OS-level execution fence (M14 F1+F2)**: all four spawn paths — `shell`,
  `python_exec`, MCP stdio servers, and PTY `shell_session_*` — route
  through a `get_sandbox_backend()` factory seam. On Linux with `bwrap`
  present, each invocation runs inside a bubblewrap jail using the
  host-workspace profile: write access limited to the `FilesystemConfig`
  allowlist, denylisted paths bound read-only via `--ro-bind-try` (not
  writable; read-scoping is satisfied for the boxed path — see below;
  host-workspace read-scoping still deferred), real `$HOME`, network
  deny-by-default (`ExecutionConfig.sandbox_network_allowed` opt-in).
  **`--ro-bind-try` silent-skip caveat**: `--ro-bind-try` (used for
  denylist paths) silently skips a path that does not exist on the host
  — the overlay is a no-op for absent paths. A denylist entry therefore
  only protects a path that already exists at sandbox launch time; a
  missing path is neither mounted nor protected. Tests that rely on
  denylist enforcement must ensure the target directory pre-exists before
  starting the sandbox (see `tests/_sandbox_fixtures.py:make_denylist_secret`).
  On
  non-Linux or bwrap-missing Linux, the seam falls through to
  `PassthroughSandbox` (observable via a one-time WARNING log). **PTY
  teardown**: a single-pid SIGKILL on the bwrap PID reaps the entire bwrap
  PID namespace via `--die-with-parent`, so `setsid`'d grandchildren are
  collected by kernel PID-namespace teardown without needing `killpg`.
  **`--new-session` omission**: the seam deliberately omits `--new-session`
  for PTY spawns to preserve the controlling tty required for interactive
  shell use; the accepted tradeoff is that the `TIOCSTI` input-injection
  surface remains open (recorded design decision).
- **Web (M05 F5)**: two-layer SSRF enforcement — `_url_check` at the tool
  boundary plus `SSRFGuardedTransport` resolving DNS once and pinning the
  connect target to that IP, refusing loopback / RFC1918 / link-local /
  cloud-metadata / IPv6 ULA + ULL by default. IP-literal hosts are gated
  on the same default-block list. See [CLAUDE.md](CLAUDE.md) lines
  142-144 for the canonical mechanism description and the **mission
  invariant** that `WebConfig` deliberately has no `disable_ssrf` field
  — SSRF protection is always-on; operators reaching specific internal
  hosts list them in `extra_allowed_hosts`.
- **Operator-supplied identifier allowlists**: any operator-config-derived
  string that flows into `Path()` joins, `subprocess.run()` argv elements,
  or filesystem operations MUST be validated against a spec-grounded
  allowlist regex, NOT a permissive character class. The character class
  `[A-Za-z0-9._@/-]` is NOT an allowlist for paths — every character is
  permitted individually, so `../etc/passwd` passes. The spec-grounded
  form is anchored, structure-aware, and rejects path-traversal patterns
  by construction.

  Exemplar regex (npm package-name spec — covers `lodash`, `@scope/pkg`,
  `pkg-with-dashes`, `pkg_with_underscores`; rejects `../etc/passwd`,
  `a/b/c`, `.hidden`, uppercase, shell metacharacters):

  ```python
  _VALID_NPX_PKG_RE = re.compile(r'^(?:@[a-z0-9][a-z0-9._-]*/)?[a-z0-9][a-z0-9._-]*$')
  ```

  Implementation: `the_one/mcp/cache_cleanup.py:71-83` defines
  `_VALID_NPX_PKG_RE` module-level, validates at function entry of
  `_clean_npx`, raises `ValueError` before any path operation.
  Established in F1 M09 Leg 3 after a design-review catch (the original
  draft used the broken char-class allowlist).
- **No native SQLite extension is loaded anywhere in the app (M24 F2 L06,
  DD-10)**: the vector-store seam's only backend (`the_one/vectors/usearch_store.py`,
  DD-9) is `usearch` — an ordinary imported Python extension module, not a
  SQLite extension, and it never touches the app's SQLite connection at
  all (its HNSW index lives in a separate sidecar file, per DD-3). The app
  never calls `sqlite3.Connection.enable_load_extension` anywhere. A
  candidate backend that loaded a native SQLite extension (`sqlite-vec`'s
  `vec0`, via `enable_load_extension`) was benchmarked in Flight 2 Legs
  4-5 and removed from the closure in Leg 6 after the operator's DD-9
  decision; this paragraph is retired along with it.
- **Knowledge-base indexing (M24 F3)**: registering a folder or file as a
  knowledge-base source is operator-only through the API — no agent-facing
  route creates `kb_items` (Flight 5's tools are read-only search). Once
  registered, the app reads a folder's contents with its own process
  privileges and no allowlist applies: the operator is choosing what their
  agents may read, the same trust boundary as everything else under the
  single-user, local-only model. The walk (`the_one/knowledge/walk.py`)
  skips dot-prefixed entries and the `SKIPPED_DIRS` set by construction —
  not a security boundary, a scope-of-indexing default. Extracted chunk
  text is stored in plaintext in the SQLite database, like every other
  record under this model. Registration refuses (422) a folder that
  equals, contains, or lies inside the application data directory (M24
  F4) — the app's own database, WAL and vector sidecar live there, so
  this keeps the app's own files out of the index and keeps indexing
  writes from feeding a change-monitoring watcher back into itself. That
  same watcher (`the_one/knowledge/watcher.py`) registers operating-system
  change notifications on the operator-chosen folder trees and reads them
  with the app's own process privileges — the same trust boundary as the
  walk above, no new one introduced.
- **Agent-facing retrieval is attachment-scoped (M24 F5)**: an agent reaches
  exactly the knowledge bases the operator attached to it
  (`AgentConfig.kb_ids`) — one `kb__{slug}__search` tool is built per
  attachment, and the tool instance carries its `kb_id` as a constructor
  argument, never a value the model supplies as a tool-call argument, so it
  is not forgeable through the LLM's tool-call interface (`ToolRegistry`
  gates on tool *name*, and the registry only ever contains tools for
  knowledge bases actually in `kb_ids`). There is no agent-facing route that
  creates or attaches a knowledge base — attachment is operator-only through
  the API, the same boundary as registering a folder above — so the set of
  knowledge bases an agent can search is entirely operator-determined.
- **Operator-facing search route (M24 F6, DD-6)**: `GET
  /api/knowledge-bases/{kb_id}/search` — the route Studio's Knowledge
  inventory uses to preview `retrieval.search` for a human operator — sits
  behind the same credential gate as every other route (see
  "Authentication" above). That means any caller holding the long-lived
  local-API credential, including an agent that obtained it (e.g. through
  the `shell` tool reading `<data_dir>/api-credential`, or a self-configuration
  MCP tool acting under its own scoped credential), can reach it. This is
  the existing single-user trust model applied to one more route, not a new
  hole introduced by this route — worth stating explicitly rather than
  leaving implicit, because the route is read-only and returns chunk text
  the operator may not have expected to be reachable this way.

## Boxed Execution Mode (M14 F4)

The `shell` and `python_exec` tools support an agent-selectable **boxed** isolation
mode layered on top of the host-workspace fence described above.

### Isolation model

- **Box-by-default**: both tools default to boxed mode; the agent must explicitly set
  `host_access=true` to escalate out of the box and reach the host workspace. This is a
  least-privilege default — the agent must consciously decide it needs the user's real
  files or network.
- **True isolation via minimal rootfs**: a boxed spawn uses
  `SandboxProfile(minimal_rootfs=True, …)` — bubblewrap mounts a minimal read-only
  system rootfs (`/usr`, `/bin`, `/lib`, `/etc`, `/proc`, `/dev`, `/tmp`) rather than
  binding the host filesystem. The user's home directory, project files, credentials, and
  any host data are completely absent. There is no host FS overlay and no denylist to
  enumerate.
- **Only writable location is the box's scratch directory**: the scratch dir (`$HOME`
  inside the box) is the sole writable path. Nothing the agent writes inside the box can
  escape to the host filesystem except through that directory.
- **Network unconditionally off**: the boxed profile DOES NOT read
  `ExecutionConfig.sandbox_network_allowed` — network is always denied inside a box,
  regardless of operator configuration. (The host-workspace profile reads the config flag;
  the boxed profile ignores it — `_build_boxed_profile` in `the_one/tools/execution.py`
  hardcodes `network_allowed=False`.)

### Scratch directory lifecycle

Two scratch patterns, both rooted at `settings.data_dir / "boxes"`:

- **Per-call-ephemeral** (`boxes/<uuid>`): used by `shell` and `python_exec` one-shot
  tools. Created by `_ephemeral_box_scratch()` context manager; removed by its `finally`
  block on both clean return and exception (including `asyncio.TimeoutError`). Each tool
  call gets a fresh scratch and leaves nothing behind on normal exit.
- **Per-session-persistent** (`boxes/{agent_name}-{session_id}-{uuid}`): used by
  `shell_session_start` / `shell_session_send`. Created at session start; cleaned up by
  `_SessionBoxedScratch` on `session.close()`. The scratch persists across sends within a
  session so the agent can accumulate files between PTY commands.

### Startup prune of orphaned scratch dirs

On ungraceful process exit (SIGKILL, OOM, kernel crash), per-call and per-session cleanup
may not run, leaving orphaned `boxes/<…>` directories. `prune_box_scratch()` in
`the_one/tools/execution.py` removes all children of `settings.data_dir / "boxes"` at
process startup — before any sessions start, so every box present is an orphan from a
prior run.

Called once from the FastAPI lifespan startup and from the CLI `_run_cli` startup.
**Single-process-at-a-time assumption**: concurrent web + CLI processes sharing the same
`data_dir` are unsupported — a startup prune in one would remove the other's live boxes.
The prune is NOT in `settings.ensure_dirs()` (called per `AgentFactory.create()`) because
that would delete a live session's scratch mid-operation.

### Read-scoping status

- **Boxed path**: read-scoping is **satisfied** — the box has no user FS at all (minimal
  rootfs mount), so the agent cannot read outside its scratch directory by construction.
  No denylist is needed; the host is simply absent.
- **Host-workspace path**: read-scoping is still **deferred** — denylisted paths are
  bound read-only via `--ro-bind-try` (not writable) but are potentially readable. A
  future flight will add read enforcement on the host-workspace path.

### Merged-usr portability caveat

The boxed `minimal_rootfs` branch in `the_one/platform/sandbox/bubblewrap.py` recreates
the system runtime inside the box using `--ro-bind /usr /usr` plus four `--symlink`
entries (`usr/bin → /bin`, `usr/sbin → /sbin`, `usr/lib → /lib`, `usr/lib64 → /lib64`).
This mount set **assumes a merged-usr layout** — i.e. the host's `/bin`, `/sbin`, `/lib`,
and `/lib64` are already symlinks into `/usr` (Debian bookworm, Ubuntu 22.04+, the
`python:3.11-slim` image base). On a **non-merged-usr host** (older Debian/Red Hat with
real split directories at `/bin` and `/lib`), the `--symlink` entries shadow those real
directories with dangling symlinks pointing to `usr/bin` and `usr/lib` inside the
box — resulting in a broken dynamic linker or missing tools. Non-merged-usr deployments
must either add explicit `--ro-bind /bin /bin` (etc.) bind entries to the boxed profile,
or verify the host layout before running boxed spawns. The deployment target for this
project is merged-usr only (bookworm/Ubuntu 22.04+); this is a portability note, not a
current operational gap.

### Passthrough degradation

On non-Linux or bwrap-missing Linux, both boxed and host-workspace spawns fall through to
`PassthroughSandbox`. Passthrough runs the command unisolated; this is logged at WARNING
level and is observable (never silent). The isolation properties above (no user FS,
network off) are NOT enforced under passthrough.

### Windows: interactive tools run unsandboxed (M15 F3 — DD9)

On Windows, the sandbox factory (`get_sandbox_backend()`) returns `PassthroughSandbox`
— there is no AppContainer or equivalent backend. All four spawn paths (including
`shell_session_*` PTY sessions) run **unisolated** on Windows. This is a documented,
accepted gap (DD9), not a regression — the Linux bubblewrap enforcement path is the
production containment boundary; Windows ships at PTY feature parity without sandbox
enforcement. WSL2 users inherit the full Linux sandbox path.

**Win32 Job Object is lifecycle teardown, NOT containment.** The
`WindowsPtySession` backend (`the_one/platform/pty_windows.py`) assigns the spawned
`cmd.exe` process to a Win32 Job Object configured with
`JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` immediately after spawn. This Job Object serves
one purpose: *lifecycle reaping*. When `close()` calls `CloseHandle` on the job, the OS
kills every surviving process in the tree (including backgrounded grandchildren). If the
Python process dies without calling `close()`, the OS automatically closes the job handle
and fires the same reap — this is the parent-crash guarantee (analogous to bwrap's
`--die-with-parent` on Unix). The Job Object does **not** restrict what the session can
read, write, or access over the network. It is not a containment boundary.

**Known gap — `run_shell` (non-PTY) Windows tree-kill.** The one-shot shell-execution
tool (`run_shell` / `ShellTool`) fires its timeout and returns the correct error, but
killing the spawned `cmd.exe` does **not** promptly reap its child tree on Windows (no
process-group or tree kill). A backgrounded child process will run to completion. This
is a robustness gap, tracked in the Mission 15 Known Issues; a `taskkill /F /T` or
Job Object fix for the `run_shell` Windows path is planned as a Flight-5 follow-up.
It does not affect the PTY backend (which has Job Object teardown) and is consistent
with the unsandboxed Windows posture.

## Secrets

- **LLM provider API keys**: encrypted at rest via `Encryptor` (Fernet
  symmetric encryption). The encryption key file (`encryption.key` in the
  project data dir) is created with mode `0o600`. See
  [CLAUDE.md](CLAUDE.md) line 74 for the `Encryptor` integration with
  `LLMProviderRepository`. Key rotation is exposed via
  `POST /api/encryption/rotate` — like every route, it requires the
  credential gate's identified caller (see "Authentication" above) and,
  behind that, the Origin-allowlist middleware. Rotation hands the new key
  off to disk via a transient `encryption.key.next` sidecar (mode `0o600`)
  staged *before* the DB commit and promoted *after*: this makes every
  crash point — including a hard kill between the commit and the on-disk
  key-file replace — self-healing on next process start via a startup
  reconcile, rather than leaving any credential stranded on a key the
  process does not hold. See `the_one/agents.md` "Encryption-rotation
  invariant (seven corpora)" for the full handoff contract.
  `GET /api/encryption/status` (read-only, behind the same credential gate) returns
  the time of the last rotation, a count of items that hold a stored secret and a
  flag for a staged-but-unpromoted key file: counts and a timestamp, no secret
  material (the count is computed by decrypting in-process; nothing decrypted is
  returned or logged).
- **SQLite database and data directory** (squawk 0011 / GH #169): the data
  directory is created and tightened to mode `0o700`; `<data_dir>/the-one.db`
  and its `-wal`/`-shm` sidecars (when present) are created and tightened to
  mode `0o600` before first write, with no world-readable window. On Windows,
  `os.chmod` is a no-op against ACLs — protection there comes from
  `%LOCALAPPDATA%` user-profile ACL inheritance, the same posture the
  `api-credential` and `encryption.key` files above already rely on.
- **MCP source, connector, and built-in tool-config secrets**: same
  Fernet field-segregated `config`+`secrets` encryption-at-rest as the
  provider keys. (The pre-reset `connectors` table's routing/ACL/approval
  machinery was removed in the Mission 23 connector reset; the row and
  its secret encryption persisted independently throughout, and the
  reset connector contract — Flight 2 — has a real masking/rotation
  surface again: see "Connector Channel Contract" above and
  `the_one/agents.md` "Encryption-rotation invariant (seven corpora)".)
  Built-in tool secrets (schema v32 `tool_configs.secrets`) are
  marker-driven — any tool Config field tagged `secret: true` is stored
  encrypted and masked over the API. `web_search`'s keyed-engine API keys
  (Brave/Google PSE/Tavily) are the first consumers. See
  `the_one/agents.md` "Tool config secrets storage".
- **Claude Plan (Token) provider token** (sortie 03): a `claude setup-token`
  token is a long-lived (about a year) subscription bearer credential, the
  same class of credential as the `anthropic-plan` OAuth access token. It is
  stored Fernet-encrypted in `llm_providers.api_key`, masked on every
  response (the `***...{tail4}` shape, preserved by the `__MASKED__`
  sentinel), covered by encryption-key rotation with the other provider
  keys, and never returned unmasked; the API refuses an Anthropic API key
  (`sk-ant-api…`) for the type without echoing the submitted value. The
  token authenticates as the operator's subscription, so revoke it from the
  Claude account when the provider is deleted or the token is no longer
  wanted. The server-stamped `token_set_at` in `secrets` is not a secret and
  is exposed read-only as `token_set_at`/`token_expires_around`.
- **`__MASKED__` sentinel**: provider edit form preserves stored API keys
  when the operator hasn't touched the field. The same mask-shape +
  preserve-on-masked semantics apply to MCP, tool-config, and (again, as
  of the Mission 23 Flight 2 reset — see "Connector Channel Contract"
  above) connector secret fields. See [CLAUDE.md](CLAUDE.md)
  "`__MASKED__` sentinel for API key updates".
- **Per-agent MCP override credentials**: `agents.tool_overrides` and
  `agents.mcp_overrides` are both Fernet-encrypted at rest. Of the two,
  only `mcp_overrides` carries credential material — the three
  `Substitute`-marked inner keys `env`, `headers`, and `bearer_token` are
  masked on every agent-config GET/POST/PUT response; `enabled_tools` /
  `disabled_tools` and every `tool_overrides` value stay in the clear.
  Preserve-on-PUT is resolved server-side against the stored row (Studio
  renders no credential fields at all, so it cannot round-trip a
  sentinel) — an omitted or masked credential key keeps the stored
  value, an explicit `null` clears it, any other value overwrites. Join
  in `POST /api/encryption/rotate`'s single rotation transaction as the
  fifth surface. See `the_one/agents.md` "Agent override secrets
  storage".
- **Per-agent self-configuration credentials** (M21 F01 L02): each
  enabled agent's `agt`-prefixed credential lives only inside its surface
  row's `secrets["Authorization"]` — the same Fernet-encrypted,
  API-masked `MCPSource.secrets` column every other MCP source uses, no
  new storage surface. Never returned by the enable endpoint; never
  written to `AgentConfig`. See "Authentication" → "Self-configuration
  surface" above for the credential's scope.
- **Per-grant external-client credentials** (M21 F03 L01): each operator
  grant mints a distinct `ext`-prefixed credential in its own table,
  `agent_external_credentials`, whose `secret` column is Fernet-encrypted at
  rest like every other secret surface. The operator-facing projection is
  secret-free (`{identifier, label, created_at}`); the token is returned once
  at mint (and on rotate) and by no read path after. The rows FK-cascade on
  the surface row, so surface-disable and agent-delete auto-revoke every
  grant. See "Authentication" → "External-client access to the
  self-configuration surface" above for the credential's scope and the
  governance invariant.
- `.env` is gitignored.
- No secrets land in any committed file (e.g. `.env.example`, which carries
  placeholders only).

## What This Model Excludes

The following are explicitly out of scope. A future flight extending into
any of these would need to revisit (and likely revise) the threat model
above before implementation:

- Multi-user / multi-tenant deployments
- Public internet exposure (without a reverse proxy adding auth)
- Hostile LLM provider scenarios — the LLM provider's responses are
  trusted (the project does NOT defend against an adversarial provider
  that returns malicious tool-call payloads)
- Hostile filesystem actor scenarios — the operator owns the local
  environment; the filesystem denylist is defense-in-depth against
  agent-side mistakes, not against an attacker on the same machine

## Future Work (NOT in scope today)

- **Secrets manager**: would replace local-only `.env`-style secret
  storage and unify with the existing API-key encryption surface
- **MCP server trust boundaries**: each MCP server is a separate trust
  domain; connecting to a third-party MCP server widens the trust
  boundary in ways the current model does not address
- **MCP `streamable-http` source URL gating asymmetry**: the LLM
  provider create / update / test endpoints route `base_url` through
  `_is_safe_provider_url` (scheme = `https` for non-localhost hosts;
  see `the_one/interfaces/web/api.py`). The MCP source create / update
  path does NOT apply an equivalent gate to `MCPSource.config.url`
  for `transport_type == "streamable_http"`. Today this is safe under
  the operator-trusted posture (the operator configures the URL by
  hand), but the asymmetry would widen meaningfully if a future
  "import MCP server from registry" or "share MCP source" feature
  lands. Suggested resolution: apply an `_is_safe_provider_url`-shaped
  validator to `MCPSource.config.url` at create / update time, with
  the same `localhost` exemption and the same `https` floor.
- **Multi-user form factor**: Mission 20 added per-request authentication
  for the single-user case (see "Authentication" above), but every
  authenticated caller today is indistinguishable from "the operator" —
  there is one shared long-lived credential, not one per user. A genuine
  multi-user form factor still needs what auth alone didn't provide:
  per-user identity (multiple long-lived credentials, not one), per-user
  tool isolation, and per-user encryption keys. Substantial, but narrower
  than before this mission landed.
  - **Concurrency consequence (M21 debrief).** Relaxing *either* loopback
    *or* single-user also expires the agent-write concurrency posture that
    depends on it: `SQLiteAgentStore.save` is a whole-row last-writer-wins
    upsert with four write consumers (Studio edit, approve, restore, and the
    field-scoped-CAS-guarded direct write), and only the direct write is
    guarded. A multi-user or non-loopback form factor MUST, in the same work:
    (1) put a row-version/etag on `save`; (2) route all four consumers through
    it; (3) make the self-revision pending-dedup a schema invariant
    (`agent_revisions (agent_name, field) WHERE status='pending'`); and
    (4) re-audit the indirect-prompt-injection residual (see the self-
    configuration surface notes above) for a non-operator principal on the
    write path. Tracked as a Known Issue in Mission 21's mission artifact.
- **CORS / OPTIONS preflight**: `OriginAllowlistMiddleware` does not
  gate `OPTIONS` requests (see code comment above `GATED_METHODS` in
  `the_one/interfaces/web/middleware.py`). The project has no CORS
  need today (single-origin local-only). If a CORS need arises, gate
  `OPTIONS` AND emit explicit `Access-Control-Allow-Origin` headers
  from a dedicated CORS middleware. Do NOT enable wildcard CORS —
  preserve the same-origin posture.
- **X-Forwarded-Host / trusted proxy**: the middleware reads the raw
  `Origin` request header. The reverse-proxy guidance at L30 above
  assumes the proxy preserves `Origin` end-to-end (most modern
  proxies do). If the proxy strips or rewrites `Origin`, the
  operator must either (a) configure the proxy to forward it, or
  (b) replace the middleware with one that consults `X-Forwarded-Host`
  after explicitly validating the proxy's trustworthiness (e.g. via
  IP allowlist on the proxy's source). The current single-user
  local-only deployment has no proxy and does not need this.
