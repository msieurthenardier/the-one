# Leg: 00-bootstrap

**Status**: landed
**Flight**: [Lazy OAuth 2.1 + PKCE](../flight.md)

## Objective

Two unrelated bootstrap tasks: (1) add `procps` to the dev container Dockerfile (carry-forward from F4 debrief R4 / HAT Finding #3); (2) scaffold the `the_one/mcp/oauth/` package with an empty `__init__.py` and an `errors.py` defining the 4 OAuth-side exception classes that subsequent legs (L2, L4) will raise. No code consumes these classes yet — they're forward-references for the leg sequence.

## Context

### Flight design decisions

- **§11 Module placement** — `the_one/mcp/oauth/` package contains `__init__.py`, `_state.py`, `storage.py`, `handlers.py`, `manual_metadata.py`, `errors.py`. L0 lands `__init__.py` (empty stub) + `errors.py` (4 classes). L2 lands the rest.
- **`procps` Dockerfile roll-in** — F4 debrief R4 / HAT Finding #3. Trivial.

### Carries forward

- F4 debrief R4 (Important): `procps` to dev container Dockerfile. F4 HAT had to install it mid-run via `apt-get install procps` because the playwright base image lacks it. Adding to Dockerfile prevents this for F5 HAT (and any future HAT requiring `pgrep`/`ps`).

### Why this leg lands first

L1+ all touch existing code; L0 adds NEW files only (errors.py + __init__.py) and ONE additive Dockerfile line. Lowest risk. No prior tests are affected. Dockerfile change requires container rebuild (`docker compose build the-one` or `make rebuild`) which the user runs once before subsequent legs benefit.

## Inputs

What exists before this leg runs:

- `Dockerfile` exists at repo root with apt install line `bubblewrap, ca-certificates, curl, git`. No `procps`.
- `the_one/mcp/` package exists with `__init__.py`, `client.py`, `errors.py`, `types.py`, `transports/`, `_pool.py` (per F4-end). **NO `oauth/` subdirectory.**
- `the_one/mcp/errors.py` defines 8 existing classes: `MCPClientError`, `MCPVersionMismatch`, `MCPCapabilityMissing`, `MCPConnectionError`, `MCPSandboxError`, `MCPToolNotFoundError`, `MCPArgumentError`, `MCPCallError`. **NO OAuth error classes yet.**
- Citation-audit verified at L0 design (per `leg/SKILL.md` Phase 2 item 7): `grep -rn "MCPOAuthError\|MCPOAuthDiscoveryError\|MCPOAuthRegistrationError\|MCPOAuthRefreshFailed" tests/ the_one/` returns 0 matches. The 4 new classes have no pre-existing callers; introduction is unambiguous.
- Test counts at L0-start (post-F4): 148 collected (`{59, 14, 13, 9, 17, 14, 22}`); 147 passed + 1 skipped (Test #6c EPERM in dev container).

## Outputs

What exists after this leg completes:

- **`Dockerfile`** apt install line gains `procps` (alongside `bubblewrap`, `ca-certificates`, `curl`, `git`). One-word addition.
- **`the_one/mcp/oauth/__init__.py`** (new, ~5 lines): module docstring + empty `__all__ = []` (subsequent legs append). Mirrors `the_one/mcp/__init__.py`'s structure but stub-only.
- **`the_one/mcp/oauth/errors.py`** (new, ~50 lines): 4 exception classes:
  - `MCPOAuthError(MCPClientError)` — base for all OAuth-side errors. NOT instantiated directly.
  - `MCPOAuthDiscoveryError(MCPOAuthError)` — RFC 9728 PRM or RFC 8414 AS metadata discovery failed (404, malformed JSON, missing required fields). Raised by L2 + L4.
  - `MCPOAuthRegistrationError(MCPOAuthError)` — RFC 7591 DCR call failed (AS rejects, network error, malformed response). Raised by L2.
  - `MCPOAuthRefreshFailed(MCPOAuthError)` — refresh-token exchange failed (401 from `token_endpoint`, invalid_grant, expired refresh token). Raised by L4. Triggers re-auth in the agent loop.
  - All inherit `MCPClientError` → `Exception`. `__init__` matches F2's pattern: takes a single message string; no nested causes; no clever exception types (per mission constraint "small-model friendly").
- **`tests/test_mcp_oauth_errors.py`** (new, ~30 lines): 1 smoke test verifying all 4 classes import, form a coherent hierarchy, and produce clean `__str__` output for small-model consumption.
- F4 prior tests pass UNMODIFIED. Cumulative test count: 148 → 149 (+1 smoke test).

## Acceptance Criteria

- [ ] `Dockerfile` line for apt install includes `procps` (verify via `grep -A 6 'apt-get install' Dockerfile | grep procps`).
- [ ] `the_one/mcp/oauth/__init__.py` exists with module docstring + `__all__ = []`. Importable: `python -c "from the_one.mcp import oauth"` succeeds.
- [ ] `the_one/mcp/oauth/errors.py` exists with the 4 classes per §Outputs. All inherit (transitively) from `MCPClientError`. Each subclass's `__str__` returns the message verbatim (no class-name prefix or rich rendering).
- [ ] `tests/test_mcp_oauth_errors.py` exists with a smoke test that:
  - Imports all 4 classes from `the_one.mcp.oauth.errors`
  - Asserts `issubclass(MCPOAuthDiscoveryError, MCPOAuthError)` (and same for the other two subclasses)
  - Asserts `issubclass(MCPOAuthError, MCPClientError)`
  - Asserts `str(MCPOAuthDiscoveryError("test"))` returns `"test"` exactly (verbatim-message-equality per F4 debrief named convention)
- [ ] All 148 prior tests across the F4 surface pass UNMODIFIED. Cumulative `pytest -q --timeout=30` returns 149 collected, 148 passed + 1 skipped.
- [ ] `ruff check the_one/mcp/oauth/ tests/test_mcp_oauth_errors.py` clean.
- [ ] Container rebuild verification: `docker compose build the-one` succeeds; `docker compose exec the-one which pgrep` returns a path (procps installed).
- [ ] Flight log Leg Progress entry added.

## Verification Steps

1. **Dockerfile change**: `grep -A 6 'apt-get install' Dockerfile | grep -c procps` returns 1.
2. **Package importable**: `docker compose exec the-one python -c "from the_one.mcp import oauth"` succeeds.
3. **Errors module importable + classes correct**: `docker compose exec the-one python -c "from the_one.mcp.oauth.errors import MCPOAuthError, MCPOAuthDiscoveryError, MCPOAuthRegistrationError, MCPOAuthRefreshFailed; from the_one.mcp.errors import MCPClientError; assert issubclass(MCPOAuthError, MCPClientError); assert issubclass(MCPOAuthDiscoveryError, MCPOAuthError); print('OK')"` prints `OK`.
4. **Smoke test green**: `docker compose exec the-one pytest tests/test_mcp_oauth_errors.py -v --timeout=30` returns 1 passed.
5. **Cumulative regression**: `docker compose exec the-one pytest -q --timeout=30` (full suite) returns 0 exit; collected count is `(prior + 1)`; passed and skipped counts unchanged from baseline + 1.
6. **Container rebuild + procps**: `docker compose build the-one && docker compose exec the-one which pgrep` returns `/usr/bin/pgrep` (or similar absolute path; non-empty stdout).
7. **Lint clean**: `docker compose exec the-one ruff check the_one/mcp/oauth/ tests/test_mcp_oauth_errors.py` returns 0 exit.
8. **Flight log updated**: Leg Progress entry exists with status `landed`, timestamps, lines-changed count, test-count delta.

## Implementation Guidance

1. **Capture L0-start commit SHA**: `git rev-parse HEAD` → note value.

2. **Update `Dockerfile`**: edit the apt install line. Insert `procps` alphabetically between `git` and the existing list (or anywhere in the alphabetical run; bubblewrap comes first alphabetically). Result:
   ```dockerfile
   RUN apt-get update && apt-get install -y --no-install-recommends \
           bubblewrap \
           ca-certificates \
           curl \
           git \
           procps \
       && rm -rf /var/lib/apt/lists/*
   ```

3. **Create `the_one/mcp/oauth/__init__.py`**:
   ```python
   """OAuth 2.1 + PKCE for remote MCP servers (F5).

   Lazy/discovery-driven: operator configures MCP source by URL only;
   on first 401 the chat surface renders a Login-required button; modal
   opens IDP consent in a new browser tab; loopback redirect resolves
   at /api/oauth/callback; tokens persist encrypted; agent loop resumes
   the original tool call.

   Consumes mcp.client.auth.OAuthClientProvider from the SDK for PKCE,
   discovery, DCR, audience binding, and refresh. This package provides
   the the-one-side adapter layer:

     - errors: MCPOAuthError hierarchy (this leg, L0)
     - storage: TokenStorage Protocol impl backed by MCPSourceRepository (L2)
     - handlers: redirect_handler + callback_handler (L2)
     - _state: pending-flow registry (L2)
     - manual_metadata: ManualOAuthClientProvider for non-DCR providers (L2)

   See the_one/mcp/README.md (post-L5) for runtime invariants.
   """

   __all__: list[str] = []  # subsequent legs append
   ```

4. **Create `the_one/mcp/oauth/errors.py`**:
   ```python
   """OAuth-side error hierarchy.

   Mirrors the_one/mcp/errors.py's pattern: single base class with narrow
   subclasses; each subclass formats a clean single-sentence __str__ for
   small-model consumption (mission constraint #75); no nested causes,
   no rich tracebacks visible in tool-result strings.
   """

   from the_one.mcp.errors import MCPClientError


   class MCPOAuthError(MCPClientError):
       """Base for all OAuth-side errors. NOT instantiated directly.

       Subclasses cover three failure modes:
         - MCPOAuthDiscoveryError: RFC 9728 PRM or RFC 8414 AS metadata fetch/parse failed
         - MCPOAuthRegistrationError: RFC 7591 DCR call failed
         - MCPOAuthRefreshFailed: token refresh failed; triggers re-auth
       """


   class MCPOAuthDiscoveryError(MCPOAuthError):
       """OAuth discovery failed.

       Raised when the AS metadata document at /.well-known/oauth-authorization-server
       (RFC 8414) or /.well-known/openid-configuration (OIDC) returns 404 or malformed
       JSON, OR when the RFC 9728 PRM document is missing required fields. Operator
       sees: 'OAuth discovery failed: <reason>. The MCP server may not be spec-compliant.'
       """


   class MCPOAuthRegistrationError(MCPOAuthError):
       """RFC 7591 Dynamic Client Registration failed.

       Raised when the DCR endpoint returns an error response, network failure
       interrupts the call, or the response is malformed. Operator sees:
       'OAuth client registration failed: <reason>. Try the manual-entry path
       to register a client at the IDP yourself.'
       """


   class MCPOAuthRefreshFailed(MCPOAuthError):
       """OAuth refresh-token exchange failed.

       Raised when the AS rejects the refresh-token grant (401, invalid_grant,
       expired refresh token). Triggers re-auth in the agent loop: the next tool
       call surfaces a fresh auth_required event so the operator can re-consent.
       Operator sees: 'OAuth token refresh failed: <reason>. Please re-authenticate.'
       """
   ```

5. **Create `tests/test_mcp_oauth_errors.py`**:
   ```python
   """Smoke tests for the_one/mcp/oauth/errors.py.

   Validates the 4-class hierarchy + verbatim-message-equality contract per
   F4 debrief named convention (project-wide pattern in agents.md).
   """

   from the_one.mcp.errors import MCPClientError
   from the_one.mcp.oauth.errors import (
       MCPOAuthDiscoveryError,
       MCPOAuthError,
       MCPOAuthRefreshFailed,
       MCPOAuthRegistrationError,
   )


   def test_oauth_error_hierarchy_and_verbatim_messages() -> None:
       """4-class hierarchy + verbatim-message-equality smoke test."""
       # Hierarchy: each subclass → MCPOAuthError → MCPClientError
       assert issubclass(MCPOAuthError, MCPClientError)
       assert issubclass(MCPOAuthDiscoveryError, MCPOAuthError)
       assert issubclass(MCPOAuthRegistrationError, MCPOAuthError)
       assert issubclass(MCPOAuthRefreshFailed, MCPOAuthError)

       # Verbatim-message-equality (per agents.md Project Conventions):
       # str(exc) returns the constructor argument exactly, no class-name
       # prefix or rich rendering.
       assert str(MCPOAuthDiscoveryError("test")) == "test"
       assert str(MCPOAuthRegistrationError("client registration failed")) == "client registration failed"
       assert str(MCPOAuthRefreshFailed("token expired")) == "token expired"
   ```

6. **Run lint**:
   ```bash
   docker compose exec the-one ruff check the_one/mcp/oauth/ tests/test_mcp_oauth_errors.py
   ```

7. **Rebuild container** (so subsequent legs have `procps`):
   ```bash
   docker compose build the-one
   docker compose exec the-one which pgrep
   ```

8. **Run regression suite**:
   ```bash
   docker compose exec the-one pytest -q --timeout=30
   ```
   Expect: 149 collected (148 prior + 1 new), 148 passed + 1 skipped (the F4 EPERM #6c).

9. **Update flight log**: append Leg Progress entry with status `landed`, ISO 8601 UTC timestamps, lines-changed count, test-count delta.

## Edge Cases

- **`procps` apt install size**: ~280KB compressed. Negligible image size impact.
- **`MCPOAuthError` instantiable**: technically the base class CAN be instantiated (`MCPOAuthError("foo")` works in Python). The docstring says "NOT instantiated directly" but Python doesn't enforce abstract semantics. F5 code never instantiates the base — only subclasses. No need to make it `ABC`-shaped; that would add complexity for marginal value.
- **`__all__ = []` in `__init__.py`**: explicit empty list. Subsequent legs append. Alternative would be no `__all__` (allows `from oauth import *` to do default thing); explicit empty is clearer about "this is intentional, not forgotten".
- **Citation audit was vacuous** (no prior callers of new symbols): documented for transparency. Future legs that introduce new public symbols MUST run the same grep gate per `leg/SKILL.md` Phase 2 item 7.

## Files Affected

- `Dockerfile` — one-word addition (`procps`) to apt install line.
- `the_one/mcp/oauth/__init__.py` (new) — ~25-line module docstring + `__all__ = []`.
- `the_one/mcp/oauth/errors.py` (new) — ~50 lines: 4 exception classes + module docstring.
- `tests/test_mcp_oauth_errors.py` (new) — ~30 lines: 1 smoke test.
- `missions/07-mcp-integration/flights/05-oauth-pkce-remote-mcp/flight-log.md` — append Leg Progress entry.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`. Do NOT commit.**

- [ ] All acceptance criteria verified
- [ ] `pytest -q --timeout=30` green; collected = prior + 1; new test in `test_mcp_oauth_errors.py` passes
- [ ] `ruff check the_one/mcp/oauth/ tests/test_mcp_oauth_errors.py` clean
- [ ] Container rebuilt (`docker compose build the-one`); `pgrep` available inside container
- [ ] Flight log Leg Progress entry added (status `landed`, timestamps, lines-changed, test count)
- [ ] Set this leg's status to `landed`
- [ ] Check off this leg in flight.md
- [ ] Do NOT commit. Do NOT signal `[COMPLETE:leg]`. Signal `[HANDOFF:review-needed]` and stop.

---

## Citation Audit

3 citations verified against current code at leg design time (2026-05-07).

- `Dockerfile` (apt install line, repo root) — verified at design 2026-05-07; lacks `procps`. **Will be modified in this leg.**
- `the_one/mcp/errors.py` (8 existing classes; no OAuth errors) — verified via grep. New OAuth error classes will subclass `MCPClientError` from this file.
- **New-symbol audit (per `leg/SKILL.md` Phase 2 item 7)**: `grep -rn "MCPOAuthError\|MCPOAuthDiscoveryError\|MCPOAuthRegistrationError\|MCPOAuthRefreshFailed" tests/ the_one/` at L0 design returned 0 matches. The 4 new classes have no pre-existing callers; introduction is unambiguous.
