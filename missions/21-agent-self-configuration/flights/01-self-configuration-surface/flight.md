# Flight: Self-Configuration Surface

**Status**: completed
**Mission**: [Agent Self-Configuration](../../mission.md)

## Contributing to Criteria

- [x] An agent can retrieve its own configuration through the surface, and no
      response from any part of the surface contains secret material.
- [x] An agent's own configuration is subject to the same secret-handling
      treatment as every other secrets-bearing record in the platform.
- [x] An agent can revise its own description and system prompt; every other
      part is refused by construction rather than by an enumerated denial list.
- [x] A revision states whether it takes effect from the next turn or only from
      the next conversation, and observed behavior matches the choice.
- [x] When the surface is enabled it appears among that agent's configured
      sources, and the operator can withhold individual capabilities from it
      using the same controls that govern every other source.
- [x] The surface is off for every existing and newly created agent until the
      operator enables it.

Criteria 5, 6 and 7 (approval mode, pending queue, revision log and restore)
belong to Flight 2. Criterion 10 (external client access) belongs to Flight 3.

---

## Pre-Flight

### Objective

Stand up a real, loopback-only MCP surface through which an agent can read its
own configuration and revise its own description and system prompt. The surface
presents as an ordinary `streamable-http` MCP source bound to exactly one agent,
so the operator's existing per-source and per-tool controls govern it with no new
gating machinery. Revisions apply directly — operator oversight arrives in Flight
2. The flight opens by bringing agent-configuration secret handling into line
with the rest of the platform, because the read projection is built on top of
that rather than around it.

### Open Questions

- [x] How does the surface present as a source? → **DD1**
- [x] What carries the calling agent's identity? → **DD2**
- [x] How much do the agent's and the external client's paths share? → **DD4**
- [x] How does "from the next turn" reach an open conversation without landing
      mid-turn? → **DD7**
- [x] How is the pre-existing secrets leak closed? → **DD5**
- [x] What is the tool catalog? → **DD6**
- [x] How is propagation observed, given no read path exposes a running agent's
      system prompt? → **DD8**
- [x] Does `describe_my_capabilities` list the self-configuration source itself
      among the agent's sources? Visibility is not writability — the write
      allowlist already excludes it either way — but an agent that cannot see
      the surface it is speaking through may reason poorly about its own limits,
      while one that can see it may probe it. Resolve in Leg 2 against the read
      projection's actual shape.
- [x] What happens to a pending `next_turn` revision if the agent object is
      rebuilt before the turn's iteration loop exits? `_get_or_restore_session`
      always rebuilds (`app.py:1103-1111`), so a rejoin mid-turn discards the
      pending revision silently. Whether that is acceptable (the revision is
      lost, the agent believes it applied) or needs the revision persisted
      before the loop exits is a Leg 3 decision.

### Design Decisions

**DD1 — The surface is a real `streamable-http` MCP source, one row per
enabled agent, pointing at a loopback endpoint the platform serves itself.**

- Rationale: reuses an existing enum value, so **all 14 Python dispatch sites
  and ~26 JavaScript sites stay untouched** — no `MCPSource.type` widening, no
  CHECK-constraint change, no table-rebuild migration. Critically,
  `filter_mcp_tools_by_override` (`mcp/_tool_provider.py:88-93`) receives a type
  it recognizes, so the operator's per-tool controls apply through the existing
  path. The two fall-throughs in that module (`:92-93` and `:181-185`) return
  input **unchanged rather than raising**, so an unrecognized type would have
  silently disabled per-tool control — the criterion would have failed with no
  error anywhere. Choosing an existing type removes that failure mode entirely
  rather than guarding against it.
- Also settles the mission's pre-declared split point: it does not fire. Two of
  its three conditions are unmet — `mcp/_pool.py` contains **zero** `source.type`
  dispatch (it delegates to `mcp/client.py`), and the sandbox layer is
  stdio-only and untouched by an HTTP transport.
- Trade-off: the agent's own tool calls leave the process and re-enter over a
  loopback socket, and pass through `CredentialGateMiddleware` like any other
  caller. The mission's expectation that "the agent's own path needs no
  credential" is **false under this decision** — see DD4.

**DD2 — The calling agent's identity is resolved from the credential, not from
the URL.**

- Rationale: spends Mission 20's first seam exactly as it was designed — the
  gate resolves a caller identity rather than a boolean. One endpoint, no agent
  name in the path, and Flight 3's external clients scope-bind through the
  identical mechanism rather than a parallel one.
- The credential lives in the source row's `secrets`, which
  `MCPSourceRepository` already encrypts at rest (`db/repositories.py:405-417`)
  and `_mcp_source_response` already masks on the way out (`api.py:942-944`).
  This deliberately keeps the credential off `AgentConfig.mcp_overrides`, which
  is the unencrypted, unmasked field this flight's first leg exists to fix.
- Trade-off: no agent name in the URL means loopback traffic is harder to read
  in a log. Accepted — a mismatch between a path and a credential would be a
  second source of truth, and the cross-check for it a second thing to get
  wrong.

**DD3 — Per-agent surface rows are hidden from the MCP Sources admin screen.**

- Rationale: the mission forbids anything from changing whether the surface is
  enabled. These rows are created and destroyed by the enable toggle on the
  agent's own tab; exposing them to the admin list makes deletion and arbitrary
  edits reachable from a screen that knows nothing about the invariant. Filtering
  them out of `list_mcp_sources` (`api.py:1220-1224`) is one change; guarding
  every write path in `mcp-server-editor.js` would be ~22.
- Trade-off: the operator loses a single place to see every MCP source. Mitigated
  by the surface being visible and controllable on the owning agent's MCPs tab,
  which is where it is managed anyway.
- **Constraint this creates**: the agent editor's source fetch must still see
  these rows, or the MCPs tab renders nothing and criterion 8 fails. The filter
  must therefore be scoped to the admin listing, not applied at the repository.

**DD4 — Flight 1 mints one credential per agent, for that agent's own client
only. No operator-facing mint UI.**

- Rationale: DD1 makes a credential unavoidable, so minting moves into this
  flight rather than waiting for Flight 3. Minting self-only keeps the decision
  cluster intact — Flight 3 still owns operator-facing mint, revoke, rotate, and
  the scope-binding semantics that only matter once a second principal exists.
- Trade-off: Flight 3 is meaningfully smaller than the mission anticipated. It
  remains a genuine boundary — it introduces the credential store as a
  secrets-bearing table and settles rotate-everything versus revoke-one, which
  Mission 20 explicitly deferred.
- Per the Mission 20 debrief's "a design decision naming an intended caller is
  not a leg acceptance criterion": Leg 2's criteria must assert that the enable
  toggle actually mints and that the agent's client actually presents it — not
  merely that a mint function exists.

**DD5 — The secrets leak is closed by encrypting the override columns at rest
*and* masking them on read, with preserve-on-PUT resolved server-side.**

- Rationale: brings `AgentConfig.tool_overrides` and `mcp_overrides` in line with
  MCP sources and connector accounts, both of which are already encrypted and
  masked. Masking alone would leave plaintext secrets in a database file that
  issue #169 records as mode 644.
- **Preserve-on-PUT cannot copy the MCP-source pattern verbatim.** That pattern
  relies on the client round-tripping a `__MASKED__` sentinel
  (`api.py:1290-1322`). Studio does not round-trip the agent config — it
  *rebuilds* `mcp_overrides` from the DOM (`studio.js:2064-2132`) while rendering
  no credential fields at all (`mcps-tab.js:21-26`), so any credential override
  set via the API is **already silently wiped by the next Studio save today**.
  Preserve must therefore key off the stored row in `update_agent`
  (`api.py:542-558`), not off a sentinel the frontend never sends.
- **No hard data migration is required.** `_decrypt_secrets_blob`
  (`db/repositories.py:40-59`) already falls back to treating undecryptable input
  as plaintext, so legacy rows decode and re-encrypt on next write. Follow that
  precedent rather than writing a rewrite-every-row migration.
- **No constructor ripple is required.** `SQLiteAgentStore.__init__` takes no
  encryptor today (`db/repositories.py:74`) and is constructed at **7 production
  sites and 30 test sites**. Give the parameter a default that resolves via
  `get_encryptor(settings.data_dir)` — the pattern `_tool_provider.py:242`
  already uses — and all 37 sites stay untouched.
- Note: `Encryptor.rotate_key` (`encryption.py:53`) has **no production caller**,
  so adding an encrypted column does not silently break an existing rotation
  path. Recorded because the absence is easy to mistake for a coupling.

**DD6 — Four intent-shaped tools, with read split from write and one write tool
per writable field.**

```
get_my_configuration()          → secret-free projection of the whole config
describe_my_capabilities()      → tools, sources, connectors held by this agent
                                  (names and descriptions only, no config)
update_my_description(text, apply)
update_my_system_prompt(text, apply)
                                → apply: "next_turn" | "next_session"
```

- Rationale: the write allowlist is expressed **in the catalog's shape** — there
  is no tool that takes a field name, so there is nothing to probe and no
  denial list to maintain. A field added to `AgentConfig` in future is unwritable
  because no tool addresses it, which is the mission's "by construction"
  constraint satisfied structurally rather than by a validator.
- Read is split so an agent can ask what it can *do* without pulling its whole
  configuration, which keeps the common case cheap and narrows what the
  projection has to be careful about.
- Trade-off: no partial or append edit of the system prompt — a revision restates
  the whole thing. Accepted deliberately: append is how a prompt grows without
  bound, and Flight 2's restore is far harder to reason about across partial
  edits.

**DD7 — A `next_turn` revision is applied when the running turn's iteration loop
exits, not when the tool returns.**

- Rationale: `_run_iterations` re-binds `request_messages = self.messages`
  **inside** its `while` loop (`agent/core.py:276-289`), and tool dispatch
  happens at `:588` within that same loop. Mutating `self.messages[0]` in place
  from a tool call would therefore take effect on **the next iteration of the
  same turn** — mid-turn, which the operator explicitly ruled out. `next_turn`
  requires a deliberate deferral, not coordination with the in-flight turn. The
  mission recorded this as open on the assumption that the risk ran the other
  way.
- Applying at loop exit means the revision is live before the next user message
  is appended, and a turn that errors out still applies it on the way out.
- Mechanism: mutate `Agent.system_prompt` and `messages[0]`, the pattern
  `Agent.reset()` already uses (`agent/core.py:635-637`) minus the history wipe.
- `next_session` costs nothing — `_get_or_restore_session` always rebuilds from
  the current agent row (`app.py:1103-1111, 975`), which is how Studio edits take
  effect today.

**DD8 — Propagation is verified behaviorally, not by state inspection.**

- **Act path**: type into the chat UI via the goldfinch browser apparatus.
- **Read path**: the rendered chat transcript, same apparatus.
- Rationale: there is **no read path anywhere that exposes a running agent's
  system prompt**. `session_joined` carries history, title, agent name and
  routing metadata but not the prompt (`app.py:1199-1220`), and
  `GET /api/agents/{name}` returns the stored row, which proves persistence and
  says nothing about whether the live conversation picked it up. Asserting
  propagation therefore requires a revision whose effect is *visible in the
  agent's output* — a sentinel instruction the replies carry.
- Recorded explicitly so no leg reaches for a state endpoint that does not exist
  and then adds a test-only seam reactively.

**DD9 — The surface refuses to serve any agent for which it is not enabled.**

- The credential resolves to exactly one agent; a tool call arriving with a
  credential whose agent has since had the surface disabled is refused rather
  than served. Disabling deletes the source row, so the credential is orphaned by
  construction — but the refusal must be asserted, not assumed to follow.

### Prerequisites

- [x] **Re-entrancy probe — blocking.** *(Verified 2026-08-24 — see flight log
      Session Notes.)* Confirm that the platform's MCP client
      can connect to an HTTP endpoint served by the platform's own process
      without deadlock. `MCPToolProvider` calls `acquire()` + `list_tools()`
      during agent construction (`mcp/_tool_provider.py:311-317`), so agent build
      would issue a loopback request to the app that is building the agent.
      Async-through should let uvicorn serve both sides concurrently, and the
      cache-first path (`:284`) skips the call after the first refresh — but this
      is the assumption the whole of DD1 rests on. **Probe before Leg 2 starts,
      not after it lands.**
- [x] Dev instance runnable on a non-8484 port with a scratch data directory.
      Port 8484 is the operator's production instance and must never be targeted.
- [x] The MCP endpoint mounts on the existing app and port — **no new port is
      introduced**, so no conflict check against other local services is needed.
      Confirmed by the probe: mounted sub-app on the real app, same port.
- [~] goldfinch browser apparatus — **not connected this session; chrome-devtools
      used as the sanctioned fallback** (behavior test still passed 8/8).
- [x] `CredentialGateMiddleware` enforced on the dev instance — the identity
      resolution in DD2 is meaningless with the gate off. Probe ran with the gate
      live; a bare loopback request 401s, a bearer-carrying source passes.
- [x] A test agent with a provider configured, capable of completing a real turn.

### Pre-Flight Checklist

- [x] All open questions resolved or explicitly deferred to a named leg
- [x] Design decisions documented
- [x] Prerequisites verified — **re-entrancy probe passed** (dev instance,
      browser apparatus and test agent are Leg 3 behavior-test prerequisites)
- [x] Validation approach defined
- [x] Legs defined

---

## In-Flight

### Technical Approach

**Secret hardening first.** `tool_overrides` and `mcp_overrides` become
encrypted columns following the `_encrypt_secrets_blob` / `_decrypt_secrets_blob`
envelope, with the existing plaintext fallback carrying legacy rows forward.
`GET /api/agents` and `GET /api/agents/{name}` gain masking; `update_agent`
gains server-side preserve against the stored row. Only then is there a store
worth building a projection over.

**Then the surface.** A loopback MCP endpoint mounts on the existing FastAPI app,
behind the existing gate. Enabling the surface on an agent's new tab mints a
credential, creates a per-agent `streamable-http` source row carrying that
credential in its encrypted `secrets`, and attaches the row to the agent. The
admin source listing filters these rows out; the agent editor's fetch does not.
From there, everything downstream — per-source attach, per-tool checkboxes,
override filtering — is existing machinery.

**Then the writes.** Two write tools, a deferral hook that applies pending
revisions at iteration-loop exit, and a behavior test that watches a real agent
change its own behavior mid-conversation.

### Checkpoints

- [x] Re-entrancy probe returns a clean `list_tools` against the platform's own
      endpoint
- [x] No agent read path returns override secrets in the clear; existing suites
      green
- [x] An enabled agent's MCPs tab shows the surface with per-tool checkboxes that
      actually filter
- [x] An agent reads its own configuration and the response contains no secret
- [x] An agent revises its own prompt; `next_turn` and `next_session` each
      behave as named
- [x] A write to any field other than description or system prompt is
      unreachable — no tool addresses it

### Adaptation Criteria

**Divert if**:
- The re-entrancy probe deadlocks or requires a threading change to the app.
  DD1 collapses; fall back to an in-process pseudo-source and accept that
  `filter_mcp_tools_by_override` needs a third branch — and re-plan Flight 3,
  which was relying on sharing this surface.
- Encrypting the override columns turns out to require the constructor ripple
  DD5 avoids (37 sites), rather than a defaulted parameter. Split Leg 1 rather
  than growing it.
- The gate cannot resolve a credential to an agent without changes to Mission
  20's middleware beyond registering a second credential source. That seam was
  paid for; if it does not fit, the identity decision (DD2) needs re-opening
  before Leg 2 continues.

**Acceptable variations**:
- Exact endpoint path and tool naming
- Whether the enable toggle lives on its own tab or is folded into an existing
  one, provided the surface still appears under MCPs
- Ordering within a leg

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned
> and created one at a time as the flight progresses. This list will evolve
> based on discoveries during implementation.

- [x] `agent-config-secret-hardening` - Encrypt `tool_overrides` and
      `mcp_overrides` at rest, mask them on every agent read path, and resolve
      preserve-on-PUT server-side against the stored row. Closes mission Known
      Issue 1 and mission criterion 2. Lands first because the read projection is
      built on top of it.
- [x] `self-configuration-surface-read` - The loopback MCP endpoint, credential
      minting and identity resolution, the two read tools with their secret-free
      projection, the new agent-configuration tab with its enable toggle and the
      per-agent source row it creates, and the admin-listing filter. Delivers a
      working read-only self-configuration MCP end to end, off by default.
- [x] `self-revision-write-path` - The two write tools, the deferral hook that
      applies `next_turn` revisions at iteration-loop exit, `next_session`
      propagation, and the `agent-self-revision-propagation` behavior test.
      Boundary sits here deliberately: confirm the surface is secret-free before
      enabling self-modification through it.

---

## Post-Flight

### Completion Checklist

- [x] All legs completed
- [x] Code merged
- [x] Tests passing (`make test-unit` is the canonical gate)
- [x] `tests/behavior/agent-self-revision-propagation.md` **executed**, not
      merely authored — the Mission 20 debrief records a behavior test written
      for a flight and never run
- [x] Documentation updated: `SECURITY-MODEL.md` gains the self-configuration
      surface and its indirect-prompt-injection residual risk; the new tab and
      tool catalog are documented for the operator

### Verification

- **Unit**: the write allowlist is unreachable for any field but the two — assert
  by catalog shape, not by attempting denied writes. Masking and encryption
  round-trips on agent read and write paths, including a legacy plaintext row.
  Identity resolution refuses a credential whose agent has the surface disabled.
- **Integration**: an agent build with the surface attached produces exactly the
  tools the operator left enabled, verified through
  `filter_mcp_tools_by_override` rather than around it.
- **Behavior**: `agent-self-revision-propagation` — a real agent revises its own
  prompt mid-conversation and its subsequent replies change accordingly, with
  `next_turn` and `next_session` distinguished by observed behavior.
- **Regression net**: assert that no agent read path emits a known secret value,
  mirroring the `test_list_returns_masked_secrets` pattern
  (`api.py:932-933`) — an assertion on response text, not on a masking function.
