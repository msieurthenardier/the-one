# Behavior Test: Anthropic Plan Provider Sign-In

**Slug**: `anthropic-plan-signin`
**Status**: active
**Created**: 2026-07-28
**Last Run**: 2026-07-30-03-16-41 (PASS 6/6 — see `anthropic-plan-signin/runs/2026-07-30-03-16-41.md`)

## Intent

Verify that an operator can create an Anthropic individual-plan provider in Settings › LLM Providers and complete authentication end-to-end by signing in with a real Anthropic Pro/Max account — no API key entered at any point — and that the resulting connection state is visible in the UI and the stored credentials never leak through the API. This needs a behavior test because the flow spans the real browser (Settings UI + Anthropic's hosted consent page), a human sign-in only the operator can perform, and the live token exchange against Anthropic's OAuth endpoints — none of which a unit test can observe. Cache is the default cold mode; step 5's hard reload is additionally a deliberate mutation-boundary cache defeat (do not remove it).

## Preconditions

- the-one dev instance is running on a **non-default port with a scratch data
  directory** and the web UI loads in a browser (operator confirms the Settings
  destination renders) — never the operator's default `:8484` instance (see CLAUDE.md's
  "Behavior-test credential convention" safety rule).
- The operator has a Claude Pro/Max account and can sign in to it in a browser (active probe: operator confirms they can reach claude.ai logged in, immediately before the run).
- No existing `anthropic-plan` provider named "Plan Test" exists (delete leftovers from prior runs).
- **Credential**: this instance is gated (Mission 20 Flight 1). Reach it per CLAUDE.md's
  "Behavior-test credential convention" — a handoff-authenticated navigation for the
  browser session (single-use; re-mint per navigation) and `Authorization: Bearer
  <credential>` for the step-5 `curl` call.

## Observables Required

- browser (rendered Settings UI, Anthropic consent page — measured via chrome-devtools or goldfinch MCP)
- http (provider API responses — measured via curl)

## Steps

| # | Actions | Expected Results |
|---|---------|------------------|
| 1 | Click the rail's "Settings" link, then "LLM Providers" in "Settings sections" (`#settings/providers`). Create a new provider: choose the Anthropic individual-plan type and name it "Plan Test". Do NOT save manually. | The editor shows the plan-provider form: a sign-in affordance is visible and enabled in create mode (no prior save required), and no API-key input is presented for this type. |
| 2 | Click the sign-in affordance. | The provider auto-saves without error (the editor transitions to the saved/edit view for "Plan Test"), and the editor enters a waiting-for-code state: a code-paste field is visible, and the Anthropic authorization URL is available (consent popup opened and/or the URL shown as copyable text). Navigating to that URL in a browser tab reaches an Anthropic authorization page. |
| 3 | Operator signs in / consents on the Anthropic page and copies the displayed code. Paste the code into the provider editor and confirm. (Operator performs the consent; Executor performs the paste if the operator hands over the code.) | The editor shows "Plan Test" as connected: the sign-in affordance is replaced by a connected indicator plus a reset/re-authenticate control. No error banner appears, and no unsaved-changes warning is pending. |
| 4 | Hard-reload the Settings page and reopen "Plan Test". | The connected state persists after reload — the editor still shows the provider as connected. |
| 5 | Fetch the provider via the HTTP API (`GET /api/providers/{id}` for "Plan Test"). | Response is 200; it reports the connection as active (e.g. an `oauth_active`-style flag) and contains **no** access token, refresh token, or other credential material in any field. `[mixed-frame]` — the no-token-leak criterion is only observable at the API surface, not in the rendered UI. |
| 6 | Click the provider's connection-test control in the editor. | The UI reports a successful connection test. |

## Out of Scope

- Chat parity (streaming, tools, thinking) — covered by `anthropic-plan-chat-parity` and the plan-provider variant of `extended-thinking-tool-turn`.
- Token refresh and re-auth-required states — covered by unit tests (mocked endpoints) and the seeded revoked-token browser test.
- Multiple simultaneous plan accounts — covered by the two-config independence integration test.
- General provider CRUD regressions — covered by `tests/browser/test_flow_provider_editor.py`, `system-provider-config`, and `save-preserves-config`.
