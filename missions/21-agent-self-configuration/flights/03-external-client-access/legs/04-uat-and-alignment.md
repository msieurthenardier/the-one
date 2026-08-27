# Leg: uat-and-alignment (HAT)

**Status**: completed
**Flight**: [External Client Access](../flight.md)

## Objective

A guided human acceptance test of Flight 3's external-client access: the operator
grants a credential from the Studio **External access** panel, a real loopback MCP
client (standing in for an external tool) reads and writes the agent's configuration,
the operator sees the write logged as `external` with the principal's identity and
honoring the approval flag, then revokes and rotates — watching access cut off and
reissue immediately, with no restart.

## Nature

Interactive HAT — **not** autonomously executed. The Flight Director stands up an
isolated scratch instance and guides the operator through each step; the operator
drives the Studio UI in their browser, and the Flight Director drives the loopback
MCP client (the "external tool" is a program, not a browser action) and confirms the
server-side revision log. Look-and-feel issues are fixed inline; new behavior is
promoted to a scoped design review per the fix-vs-feature gate.

## Preconditions (operator-confirmed before starting)

- **Isolated instance only.** A scratch instance on **port 8485** (never 8484 — the
  operator's production instance) with a **scratch data dir** under
  `/tmp/the-one-hat/…` (never the operator's real data dir). Dev mode on so a mock
  LLM provider is available (no real API key needed).
- The Flight Director seeds the scratch data dir before launch: a test agent
  (`hat-agent`) with a known description/system_prompt, the self-configuration surface
  **enabled**, and approval mode togglable.
- The operator launches the scratch app themselves (so the credential-gate handoff
  authenticates their browser automatically) and reports readiness.

## Acceptance Criteria (verification steps)

Each is an operator-observed or FD-observed check; confirmed before advancing.

- [x] AC1 — On `hat-agent`'s Self-configuration tab, the **External access** section
      is shown (surface enabled). Entering a label and activating **Grant** reveals an
      `ext_…` token **once** with the surface URL and a "shown once" warning; the grant
      appears in the active list (label + created time), with no secret in the list.
- [x] AC2 — A loopback MCP client bearing that `ext_` token (FD-driven) reads the
      agent's configuration (`get_my_configuration`) — the projection returns the
      description/system_prompt and no secret, no approval-mode field.
- [x] AC3 — With approval mode **off**, the external client writes a new description;
      the operator sees it applied and the revision log shows one `external` entry with
      the principal's identifier (before→after, timestamp).
- [x] AC4 — With approval mode **on**, an external write does **not** apply; it appears
      in the operator's pending queue tagged as an external proposal; the operator
      approves it and it takes effect, still recorded as `external`.
- [x] AC5 — Confinement/governance: the external client is refused (403) on an
      operator route (e.g. attempting the approval-mode endpoint) — it can only reach
      the four surface tools.
- [x] AC6 — **Revoke** from the Studio panel: the operator revokes the grant; the
      external client's next call is refused immediately (401), with no restart. The
      grant leaves the list.
- [x] AC7 — **Rotate**: the operator rotates a (fresh) grant; the panel reveals a new
      token once; the old token is refused and the new one works — no restart.
- [x] AC8 — The operator is satisfied with the look-and-feel of the External access
      panel; any inline fixes made during the session are recorded in the flight log
      (and, if code changed, committed as a follow-up commit on the flight branch — no
      amend).

## Notes

- Open question surfaced at Leg 3: **Rotate is single-click (no confirm)**, unlike
  Revoke's two-step confirm. If the operator wants a rotate confirm, that is a
  look-and-feel fix (inline); anything larger is promoted per the fix-vs-feature gate.
- Teardown: stop the scratch instance and remove the scratch data dir at the end.

---

## Post-Completion Checklist

- [x] All AC steps walked and confirmed (or issues fixed inline + re-confirmed)
- [x] Flight log updated with the HAT session outcome and any inline fixes
- [x] Scratch instance stopped, scratch data dir removed
- [x] Set this leg's status to `completed``; check it off in flight.md
- [ ] If code changed during the HAT: a follow-up commit on the flight branch
