# Mission: Agent Self-Configuration

**Status**: active

## Outcome

An agent can look at itself and revise how it presents — its description and
its system prompt — through a first-class surface the operator controls, rather
than only being edited from the outside by a human in Studio. The same surface
can be opened to an external client scoped to that one agent, so a tool sitting
outside the platform can inspect and tune a single agent without being handed
the platform.

The operator stays in charge throughout. The surface is off until they turn it
on, per agent. They choose per agent whether revisions apply directly or wait
for their approval. They can see every revision an agent made to itself, and
restore any earlier version. And they keep the same per-capability control they
already have over any other source the agent uses.

The boundary is deliberately narrow: an agent can change what it *says* about
itself and how it *behaves within* the capabilities it already holds. It cannot
acquire new capabilities, read anything belonging to another agent, see any
secret, or alter the surface that grants it this access.

## Context

Agent configuration today is human-only: an operator edits an agent in Studio,
and the agent has no view of its own definition and no way to act on it. That
forecloses a class of use the platform is otherwise well shaped for — an agent
that notices its instructions are wrong for the work it keeps being asked to do
and corrects them, or an external tool that tunes one agent's prompt against
observed behavior without being trusted with the whole platform.

Mission 20 built the runway for this and stopped deliberately at its edge. It
refused in-app credential minting on the grounds that nothing consumed a minted
token yet, and it declared per-route scope enforcement out of scope because it
had no consumer. It named *this* surface as the consumer that would settle both,
and paid for three seams up front so the surface would not require rework: the
request gate resolves a caller identity rather than a boolean, a credential
carries an identifier distinct from its secret so it can be revoked by name and
logged without leaking, and credential lookup sits behind a seam a second source
can register against. Those seams are unspent. This mission spends them.

Two properties of the existing codebase shape the design more than anything
else. Per-agent capability gating already runs through the MCP source machinery
— `MCPToolProvider` reads `mcp_source_ids` and `mcp_overrides` at agent-build
time, in-process, for every transport — so a self-configuration surface that
presents as a source inherits the operator's existing per-capability control
without new machinery. And the built-in tool resolver already enforces a
narrowing discipline in which an agent-level override may only ever restrict,
never widen, with widening raising rather than silently applying. That is the
same instinct as this mission's central invariant and worth citing as
precedent — but it is a directional precedent only. The resolver narrows
*values within an already-permitted field*; this mission needs a closed set of
permitted *field names*. Do not attempt to route the write allowlist through it.

The risk this mission carries is not the writes. Two fields, neither
capability-bearing, is a small blast radius. The risk is that the surface is
reachable by an agent whose inputs are attacker-controllable — the indirect
prompt-injection axis that mission 20 explicitly did not close. An injected
agent that can rewrite its own instructions can shed its guardrails while
keeping every tool it already had. That is bounded but real, and it is why the
write allowlist, the self-referential exclusion, and the revision log are
mission-level constraints rather than implementation details.

## Success Criteria

- [ ] An agent can retrieve its own configuration through the surface, and no
      response from any part of the surface contains secret material — including
      when the agent asks about records its configuration references.
- [ ] An agent's own configuration is subject to the same secret-handling
      treatment as every other secrets-bearing record in the platform: no read
      path anywhere returns its secret material in the clear, including the read
      paths that predate this mission.
- [ ] An agent can revise its own description and system prompt. Every other
      part of its configuration is refused, including the settings that govern
      this surface itself, and the refusal is by construction rather than by an
      enumerated denial list.
- [ ] A revision states whether it takes effect from the next turn of the
      current conversation or only from the next conversation, and the agent's
      observed behavior matches the choice made.
- [ ] The operator sets, per agent, whether self-revisions apply directly or
      wait for approval — and an agent cannot change that setting for itself.
- [ ] Where approval is required, a revision has no effect until the operator
      accepts it, and the operator can see what would change before deciding.
- [ ] Every revision is recorded with what changed and when, and the operator can
      restore any earlier description or system prompt.
- [ ] When the surface is enabled for an agent it appears among that agent's
      configured sources, and the operator can withhold individual capabilities
      from it using the same controls that govern every other source.
- [ ] The surface is off for every existing agent and every newly created agent
      until the operator enables it.
- [ ] An external client can be granted access scoped to a single agent; that
      access can be withdrawn and reissued without restarting the platform, and a
      withdrawn credential stops working immediately.

## Stakeholders

- **Operator (device owner)** — the only human. Gains a way to let agents tune
  themselves without giving up oversight, and must never be surprised by a
  change they cannot see or undo.
- **Agents** — gain self-knowledge and a bounded ability to act on it. Their
  interest is in a surface that is useful enough to be worth consulting rather
  than a token gesture.
- **External tooling** — clients outside the platform that want to inspect or
  tune one agent. Their existence is what makes credentials necessary at all;
  without them the agent's own path needs none.
- **Mission 20** — this mission is the consumer that settles the questions that
  mission deferred: whether minting has a consumer, and what rotation means once
  more than one principal exists.

## Constraints

- **The write surface is an allowlist of exactly two fields** — description and
  system prompt. Not a denial list. A field added to agent configuration in
  future must be unwritable by default, without anyone remembering to forbid it.
- **The surface can never modify itself.** Nothing reachable through it may
  change whether it is enabled, which capabilities it exposes, which sources or
  tools the agent has, or whether revisions require approval. This is what keeps
  the write scope from being a bootstrap into a wider one.
- **No secret material is returnable**, by the agent or an external client. This
  is to be achieved structurally — the surface returns purpose-built projections
  rather than stored records — not by masking, which is marker-driven and
  therefore only as complete as its markers. This constraint is load-bearing
  rather than precautionary: an agent's own configuration row can already hold
  plaintext secrets (see Known Issues), so serializing that row is an active
  leak, not a theoretical one. The flight that builds the read path must
  enumerate which configuration fields are unsafe to serialize, as a concrete
  list rather than a general policy.
- **Read scope is the agent itself.** No other agent's configuration, no other
  agent's conversations, no platform-wide inventory.
- **Loopback only.** Mission 20's single-user local posture is retained
  unchanged. No network reachability, no multi-user accounts, no reverse-proxy
  auth. Any external client is a client on this machine.
- **Off by default**, for existing and new agents alike, matching the
  locked-down-by-default semantics the codebase already uses for per-agent tool
  and override fields.
- **Reuse the existing per-agent capability controls** rather than building a
  parallel gating mechanism for this surface.
- **Planning skills do not implement.** Implementation runs through
  `/agentic-workflow`.

## Environment Requirements

- Local toolchain and the existing test lanes: `make test-unit` is the canonical
  gate; browser lanes via `scripts/run-tests.sh --lane …`.
- Mission 20's credential gate is in force, so every lane and every non-browser
  caller already needs a credential. Behavior tests and the live lane inherit
  that plumbing.
- **A live agent turn is required** to verify propagation timing — whether a
  revision applied "from the next turn" is actually observed by the running
  conversation cannot be established by unit tests alone. This criterion is
  behavior-test-backed; the flight that owns it plans the spec.
- The `-m live` lane must never be pointed at the operator's production
  instance on port 8484; use a dedicated dev instance.
- No external accounts, network services, or third-party credentials required.

## Open Questions

- **How does the surface present as a source?** `MCPSource.type` is a closed
  two-value literal, guarded by a table-level check constraint, and roughly
  fourteen production call sites switch on it — transport dispatch, override
  application and tool filtering, and the create/update/test endpoints. Widening
  it buys reuse of the existing override and gating machinery at the cost of
  touching all of those plus a full table-rebuild migration and a new override
  schema. That is not unprecedented: the earlier transport rename was executed
  exactly that way, so the maneuver is known rather than novel. The alternative
  — a synthesized entry with no stored row — sidesteps nearly all of it, and is
  made more attractive by the fact that per-agent tool provision already runs
  in-process for every transport. **Resolve first; it is Flight 1's largest
  decision.**
- **How much do the agent's path and the external client's path share?** The
  agent's own path needs no credential — per-agent tool provision is already
  in-process for every existing source, so binding the surface at agent-build
  time gives identity implicitly. What remains open is how much of the tool
  implementation is shared with Flight 3's external-client path, which does need
  a credential and does cross a socket. The answer decides whether Flight 1
  writes tools against a transport or against a core that two entry paths call.
- **How does "from the next turn" reach an open conversation?** Settled enough
  to plan against, and it is not free. The system prompt is baked into the
  message list once when an agent is constructed, and the step loop never
  re-reads it. Rebuilding on rejoin already exists — it is how operator edits in
  Studio take effect today — so **next-session propagation costs nothing**.
  Next-turn propagation within a conversation that is already open does not
  happen on any current path, and needs a bounded change: mutating the live
  agent's prompt and first message in place, which the existing reset path
  already does minus the history wipe. What is still genuinely open is
  concurrency — the write arrives *as a tool call inside a turn*, so whether the
  mutation must coordinate with that in-flight turn or may simply land after it
  returns needs deciding rather than discovering.
- **What does an agent see when its revision is queued rather than applied?**
  Under approval mode the write does not take effect, and the agent needs a
  truthful result it can reason about without being able to distinguish "queued"
  from "applied" in a way that invites it to retry in a loop.
- **What happens to a pending revision when the prompt changes underneath it?**
  The operator may edit the prompt in Studio, or a revert may land, while a
  proposal is outstanding. Approving a stale diff silently would be a real
  defect.
- **What stops a revision loop?** An agent that rewrites its own prompt every
  turn is not obviously misbehaving, and is also not obviously fine. Whether
  this needs a rate limit, or only needs the revision log to make it visible, is
  unsettled.
- **What is the tool catalog?** Roughly five to eight intent-shaped operations
  rather than a field-level mapping, but the exact set — and whether revision
  history and revert are reachable by the agent or operator-only — is open.
- **What does rotation mean now that more than one principal exists?** Mission
  20 shipped command-line rotation only, expressly because rotate-everything
  versus revoke-one could not be settled before this surface existed. Flight 3
  inherits that decision.

## Known Issues

- [ ] **An agent's configuration row can hold plaintext secrets, and the existing
      agent-read endpoints return them unmasked.** The per-agent override fields
      are stored as unencrypted JSON columns, and the substitutable keys written
      into them include bearer tokens, headers, and environment values. Unlike
      every other secrets-bearing record in the platform, these are neither
      encrypted at rest nor masked on the way out — the agent-read endpoints
      serialize the row wholesale. This predates the mission and is currently
      bounded by the credential gate to operator-authenticated callers, so it is
      not an open breach. It becomes one the moment an agent can read its own
      row. **Disposition: closed as a leg in Flight 1**, ahead of the read path
      that would otherwise be a careful projection built over a leaky store.
      Whether the fix is masking on the way out, encrypting the columns at rest,
      or both is a flight-design decision, not settled here.
- [ ] Mission 20 closed with one success criterion partial: the live/AIAT lane,
      the repository's serving-verification target, the packaged-app smoke check
      in CI, and the `local-api-auth-session-lifecycle` behavior test were
      code-changed but never executed. Flight 3 builds directly on that
      credential substrate. Not a blocker for Flights 1 and 2.

## Flights

> **Note:** These are tentative suggestions, not commitments. Flights are
> planned and created one at a time as work progresses. This list will evolve
> based on discoveries during implementation.

- [x] Flight 1: Self-configuration surface — how it presents as a source, the
      intent-shaped tool catalog, the secret-free read projection, the two-field
      write allowlist with its self-referential exclusion, the propagation
      choice, and the new agent-configuration tab with its enable toggle.
      Revisions apply directly; oversight arrives in Flight 2. **Opens with a
      leg that brings agent-configuration secret handling into line with the
      rest of the platform** (see Known Issues) — the read projection is built
      on top of that, not around it.
- [x] Flight 2: Operator oversight — the revision log, approval mode with its
      pending queue and count badge, and restore. Follows the pending/approve/
      dismiss pattern the connector peer-approval flow already establishes.
- [ ] Flight 3: External client access — the locally-bound surface for clients
      outside the platform, and credentials scoped to a single agent with mint,
      revoke, and rotate. Isolates the credential store, which is a further
      secrets-bearing table and the trigger the mission 19 debrief named for
      extracting a shared secrets-column helper.

**Why three and not one.** Each boundary sits at a decision cluster that needs
its own conversation, not at a layer. Flight 1 turns on a hard-to-reverse
schema-shaped choice about how the surface presents. Flight 2 is governance
semantics — staleness, concurrency, and what the agent is told — which is
independent of how the surface is exposed. Flight 3 introduces a secrets-bearing
store and consumes mission 20's credential seams. Each flight carries its own
schema, backend, UI, and tests.

**Pre-declared split point:** if Flight 1's source-presentation decision turns
out to require widening the transport enum *and* that widening ripples into
transport dispatch, the pool, and the sandbox layer, split the presentation work
from the tool catalog at that boundary. The signal is a survey count, not a
feeling — count the call sites that switch on source type before committing to
the leg breakdown.
