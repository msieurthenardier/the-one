# Leg: security-model-and-docs

**Status**: landed
**Flight**: [Authenticated Local API End-to-End](../flight.md)

## Objective

Revise the documented security posture so it no longer asserts the API is
unauthenticated by design, states what the new posture does and does not protect
against, and corrects the documentation that describes now-stale unauthenticated
probes.

## Context

This is a mission success criterion in its own right, not a chore appended to
code work: *"the documented security model no longer describes the API as
unauthenticated and states what the posture does and does not protect against."*
GitHub issue #165 framed the whole mission as revisiting **F3 Decision 10**, and
until that revision lands the flight has changed the system's behaviour while
leaving its documented rationale contradicting it.

### What `SECURITY-MODEL.md` currently says, and why each part must change

- **Line ~14, F3 Decision 10** — *"operator-trusted setup, NOT malicious
  filesystem actor... the canonical citation for any future 'should we add
  auth?' question."* This is the load-bearing sentence. It is cited elsewhere in
  the file and it is the thing this mission revisits. It must not simply be
  deleted: the decision was *reconsidered*, and the document should say so and
  say why, because the next person asking "should we add X?" will cite whatever
  replaces it.
- **The `## Authentication` section, line ~19** — *"No auth on HTTP/WebSocket
  routes by design. Every endpoint... is unauthenticated. Adding auth would
  violate the single-user posture documented above."* Now false in every clause.
- **The same section's Origin-allowlist paragraph** — still accurate, but its
  framing ("closing the drive-by-LAN attack surface **without adding auth**")
  needs rewriting now that auth exists and the gate sits *outside* it (DD4).
  Its closing note that "`GET` requests and missing-`Origin` callers pass
  through" is exactly the gap the credential gate now covers, and saying so
  makes the layering legible.
- **Line ~310, Future Work** — *"Multi-user form factor: would require auth +
  per-user tool isolation + per-user encryption keys — a substantial change that
  inverts F3 Decision 10."* Half of this just happened. The entry should be
  rewritten to reflect what remains (per-user isolation and keys), not deleted.
- **`packaging/windows/README.md`, line ~202** — *"frozen `serve` answers
  `http://127.0.0.1:8484/api/info` with HTTP 200"*. `/api/info` is credentialed
  now; this describes a probe that will 401.

## What the posture section must actually say

The mission is explicit that the honest boundary be documented, not just the
capability. The revision must state:

**What it now protects against**: other local OS accounts reading or driving the
API; lower-privilege processes on the same machine; and browser-vectored access
— a hostile page can no longer reach the loopback API, including via `GET`,
which the Origin allowlist deliberately never gated.

**What it does not protect against**: a process running *as the operator* can
read the credential file and therefore has full access. This is not a
deficiency to apologise for; it is the boundary the mission chose, and stating it
plainly is what stops a future reader assuming more protection than exists.

It must also record the layering and the two-credential design, because both are
non-obvious and both have already caused confusion inside this flight:

- The gate is registered outermost, so a missing credential yields **401**
  before origin logic runs, and a valid credential from a disallowed origin
  yields **403** (DD4).
- Exactly **one** exemption exists — the liveness endpoint — and it returns
  liveness and nothing else. Record *why* `/api/info` was rejected as the
  exemption: it returns `base_prompt`, so exempting it would publish the agent's
  system prompt to every local process (DD5).
- There are **two** credentials with different lifetimes: a long-lived persisted
  one, and a single-use, short-lived browser-handoff one. The flight spec names
  conflating them as the likeliest implementation error; the document should
  make the distinction hard to miss.
- The session cookie is `SameSite=Strict`, and **why** — `Lax` would attach it
  to cross-site top-level `GET` navigations, which is precisely the ungated
  method (LD5). This is the single most reversible-by-accident decision in the
  flight and deserves a sentence naming the consequence.
- Rotation is the revocation mechanism and drops every session at once (DD9,
  LD3).

## Acceptance Criteria

- [x] F3 Decision 10 is **revised, not deleted** — the document records that the
      decision was reconsidered by this mission and what replaced it, so future
      "should we add X?" questions cite something current.
- [x] The `## Authentication` section no longer claims the API is unauthenticated
      by design, and describes the credential, the gate, the channels, and the
      exemption.
- [x] The posture section states what the new posture protects against **and**
      what it does not — specifically that a process running as the operator can
      read the credential file.
- [x] The Origin-allowlist paragraph is reframed to show the layering rather than
      presenting itself as the alternative to auth.
- [x] The Future Work "multi-user form factor" entry reflects what remains.
- [x] `SameSite=Strict`, the two-credential distinction, the single exemption and
      why `/api/info` was rejected, and rotation-as-revocation are all recorded.
- [x] `packaging/windows/README.md`'s `/api/info` probe description is corrected.
- [x] `docs/windows-install.md` checked for the same staleness and corrected if
      present (no staleness found; left unmodified).
- [x] `CLAUDE.md`'s testing-lane guidance mentions the credential where a
      contributor would otherwise be confused by a 401.
- [x] No operator username or absolute home path appears in any added text —
      this is a public repository.
- [x] Every code reference added is verified against the tree at writing time.

## Verification Steps

- Read the revised `SECURITY-MODEL.md` against the actual implementation —
  every claim it makes must be true of the code as landed, not of the design as
  planned. This leg runs last precisely so the earlier legs' deviations are
  already known.
- `grep -rn "unauthenticated"` across docs to catch stragglers.
- `make test-unit` (no code changes expected, but cheap insurance).

## Edge Cases

- **Claims that were true when written and are now false elsewhere in the file**
  — the two `grep` hits are the known ones, but the file cross-references F3
  Decision 10 from several places. Follow the citations.
- **Over-claiming.** The temptation is to describe the posture as stronger than
  it is. The mission's own outcome statement is the calibration: what is removed
  is other local accounts, lower-privilege processes, and browser-vectored
  rebinding — not a process running as the operator.
- **`.env.example`** — check whether it needs a credential-related entry or a
  comment; it already carries the `THE_ONE_ORIGIN_ALLOWLIST` example.

## Files Affected

- `SECURITY-MODEL.md` — the substantive revision.
- `packaging/windows/README.md`, `docs/windows-install.md` — stale probe
  descriptions.
- `CLAUDE.md` — testing-lane guidance.

---

## Post-Completion Checklist

- [x] All acceptance criteria verified
- [x] Update flight-log.md with leg progress entry
- [x] Set this leg's status to `landed`
- [ ] Check off this leg in flight.md — left to the Flight Director / flight-end
      review gate, consistent with Leg 6's precedent (commit and cross-artifact
      bookkeeping deferred to the end-of-flight review).

> Commit is deferred to the flight-end review gate. Do **not** commit and do
> **not** signal `[COMPLETE:leg]`.
