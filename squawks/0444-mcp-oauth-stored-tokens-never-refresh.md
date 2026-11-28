# Squawk 0444: MCP OAuth tokens loaded from storage are never refreshed

**Status**: completed
**Type**: defect
**Severity**: grounding
**Reported**: 2026-11-27
**Completed**: 2026-11-28

## Report

An OAuth MCP source (operator report: Cloudflare MCP, production) needs an interactive sign-in again every time its access token expires, even though a refresh token is stored. In chat the tool call hangs on a sign-in; routines fail with "Needs a sign-in to Cloudflare MCP. Sign in on its page in Library, then run it again." Reset connection plus sign-in in Library clears it until the next expiry. Production log, 2026-11-27: sign-in at about 14:05, Observer routine failures from 16:21, re-auth at about 18:02.

Every new MCP connection builds a fresh `OAuthClientProvider`, and the SDK never learns the stored token's expiry. It treats the expired access token as valid, sends it, gets a 401, and the 401 branch goes straight to full interactive authorization without trying the stored refresh token.

Reproduce: give `OAuthClientProvider` a storage whose `get_tokens` returns `OAuthToken(access_token=..., expires_in=0, refresh_token="rt")` (what `MCPSourceTokenStorage.get_tokens` returns for an expired token) and client info, then `await provider._initialize()`: `context.token_expiry_time` is `None`, `context.is_token_valid()` is `True`, so the proactive refresh does not run.

## Evidence

- `mcp/client/auth/oauth2.py:OAuthClientProvider._initialize` (installed mcp 2.3.0, the latest release; venv-relative) — loads `current_tokens` from storage but never calls `context.update_token_expiry`; `token_expiry_time` is only set after a code exchange or a refresh (`_handle_token_response`, `_handle_refresh_response`).
- `oauth2.py:OAuthContext.is_token_valid` — `not self.token_expiry_time or time.time() <= self.token_expiry_time`: `None` reads as valid.
- `oauth2.py:_auth_flow` — `if not self.context.is_token_valid() and self.context.can_refresh_token():` is the only refresh path; the `status_code == 401` branch runs discovery and `_perform_authorization` directly.
- `the_one/mcp/oauth/provider_factory.py:build_oauth_provider_for_source` — constructs a plain SDK `OAuthClientProvider` per connection (`the_one/mcp/_pool.py:_entry_worker`, `/api/oauth/start`), so every connection starts with no expiry.
- `the_one/mcp/oauth/storage.py:MCPSourceTokenStorage.get_tokens` — already returns a relative `expires_in` (clamped at 0) from `token_expires_at`, so the expiry is available at load time.

Out of scope (a sortie, not this squawk): the chat resume after `/api/oauth/callback` racing the `/api/oauth/start` token save, and routine/connector sessions waiting out the 30 s connect timeout for a sign-in nobody can give.

## Corrective Action

Added `the_one/mcp/oauth/provider.py::TheOneOAuthClientProvider`, an `OAuthClientProvider` subclass whose `_initialize` calls `super()._initialize()` and then, when `context.current_tokens` is set, `context.update_token_expiry(tokens)`. `provider_factory.build_oauth_provider_for_source` (the only construction site under `the_one/`; `/api/oauth/start` and Test connection both go through it) now returns the subclass, so the SDK's existing proactive refresh (`not is_token_valid() and can_refresh_token()`) runs for an expired stored token before the request is sent. `expires_in=None` leaves `token_expiry_time` None (token treated as valid, unchanged). For `expires_in <= 0` the expiry is set to `time.time() - 1.0` rather than `update_token_expiry`'s `now + 0`: `is_token_valid` is `time.time() <= expiry`, so on a coarse clock (Windows desktop) the unclamped value could still read as valid and the fix would silently do nothing. It is not set to 0 because a falsy expiry also reads as valid. The `isinstance(provider, OAuthClientProvider)` check in `mcp_connection_flow.py` still holds. Chosen over patching the SDK (vendored dependency) or pre-refreshing in the pool (would duplicate the SDK refresh and its persistence). Docs: `the_one/agents.md` (after "OAuth-managed secret keys") and the `the_one/mcp/oauth/__init__.py` docstring; `the_one/mcp/README.md` does not describe this behavior.

## Verification

- New `tests/test_mcp_oauth_stored_token_refresh.py` (5 tests, against `OAuthASStub`, in file order):
  - `test_expired_stored_token_is_refreshed_not_sent`: the stub sees a `refresh_token` grant and no `authorization_code`, every MCP request is authorized, the redirect handler is not invoked (the callback raises if called), and the new tokens are persisted to storage.
  - `test_expired_stored_token_is_invalid_right_after_initialize`: with `time.time` frozen, `is_token_valid()` is False immediately after `_initialize` for an `expires_in=0` token (with the `expires_in <= 0` branch disabled, so plain `update_token_expiry` seeding, it fails with `is_token_valid()` True).
  - `test_failed_refresh_falls_through_to_interactive_authorization`: the stub answers the refresh grant 400; the refresh grant is attempted, the redirect handler is invoked and the callback handler is reached.
  - `test_stored_token_without_expiry_is_sent_as_is`: an `expires_in=None` token is sent as-is, no token requests, the expiry stays None.
  - `test_unexpired_stored_token_is_used_without_refresh`: used without a refresh, expiry seeded.
- Falsification (whole fix disabled by editing, then restored): every test failed except `test_stored_token_without_expiry_is_sent_as_is`, which pins unchanged behavior and passed as designed. Falsified: yes for the other four, n/a for that one.
- Related files (`test_oauth_provider_factory`, `test_mcp_agent_build_oauth_refusal`, `test_mcp_test_connection_stale_tokens`, `test_mcp_signin_detection`, `test_mcp_test_connection_negotiation`, `test_oauth_start_endpoint`, new file): 84 passed.
- `ruff check` and `ruff format --check` over `the_one/ tests/ scripts/ evals/`: clean.
- `THE_ONE_TEST_NETNS=1 make test-unit`: 12406 passed, 40 skipped, 0 failed (rerun on the rebuilt Python 3.12 venv; the earlier `test_fake_platforms_seam` failure was the accidental Python 3.13 venv).

## Sign-Off
**Reviewer**: Reviewer agent (Sonnet tier: credential handling), two passes. Pass 1 confirmed with non-blocking nits; one (an `expires_in=0` seed equal to "now" can still read valid on a coarse clock, and production is the Windows desktop app) was fixed in a fix pass. Pass 2 re-reviewed the result.
**Verdict**: confirmed
**Commit**: see PR (single commit on `squawk/0444-mcp-oauth-stored-tokens-never-refresh`)
