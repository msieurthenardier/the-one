# Mission: Anthropic Individual Plan Provider

**Status**: active

## Outcome

Agents can run on prepaid Anthropic subscription plans (Claude Pro/Max) through a new provider type that authenticates by signing in with an Anthropic account, alongside the existing API-key-based Anthropic provider. Operators who already pay for an individual plan can put that capacity to work for their agents without provisioning API keys or incurring per-token API billing.

## Context

Anthropic previously disallowed third-party applications from using individual (Pro/Max) plans; that policy has changed, and subscription-based OAuth access is now a supported authentication path (bearer tokens on `Authorization` with the OAuth beta header, rather than `x-api-key`). the-one already has an Anthropic API-key provider (`anthropic` type) and reusable OAuth *periphery* from the MCP integration work (mission 07): the loopback callback route, pending-flow state registry, popup-based consent UX, and encrypted secrets-blob storage. The MCP OAuth *core* (the MCP SDK's `OAuthClientProvider`, discovery, dynamic client registration) is MCP-coupled and will **not** be reused — Anthropic's consumer OAuth uses a fixed well-known public client, so the flow itself is a small hand-rolled PKCE implementation against fixed endpoints. This mission extends the provider system with a subscription-authenticated variant so agents can draw on prepaid plan capacity.

Multiple accounts are supported the same way any provider supports multiple configurations — create additional provider configs of the same type.

## Success Criteria

- [ ] An operator can create an Anthropic individual-plan provider in Administration and complete authentication by signing in with their Anthropic account in a browser — no API key is ever entered. *(behavior-test-backed)*
- [ ] An agent bound to a plan provider completes chat turns — including streaming, tool use, and extended thinking — with parity to the existing Anthropic API-key provider. *(behavior-test-backed)*
- [ ] Plan credentials survive application restarts and are stored encrypted at rest, never appearing unmasked in API responses or logs.
- [ ] Expired short-lived credentials are renewed automatically during normal operation, with no operator intervention.
- [ ] When renewal is no longer possible (long-lived credential expired or revoked), the operator sees a clear re-authenticate affordance in Administration, and agents using the provider fail with an actionable error rather than silently.
- [ ] Multiple plan providers (distinct Anthropic accounts) can coexist and be independently bound to different agents.
- [ ] The provider's connection test and model listing work in Administration, consistent with other provider types.

## Stakeholders

- **Operator (device owner)** — wants agents to use plan capacity they already pay for, without API billing or key management.
- **Agents** — need an LLM provider indistinguishable in capability from the API-key Anthropic provider.

## Constraints

- **Simplest solution wins.** Where the auth-flow design offers a choice (self-contained OAuth flow reusing the MCP machinery vs. delegating to an external credential source), prefer the simplest approach that satisfies the criteria — this is the Architect's call to recommend.
- Follow existing provider-system conventions: type registered across the established sites (type tuple, model literal, schema constraint, factory map, API branches, frontend defaults/badges), secrets encrypted with the existing Fernet infrastructure, masked-secret API contract preserved.
- No changes to the existing `anthropic` API-key provider's behavior.
- Provider type identifier fixed at mission level as **`anthropic-plan`** so the registration sites (type tuple, model literal, schema constraint, factory map, API branches, frontend) can be planned verbatim.
- Subscription capacity limits (plan usage windows, rate limits) are out of scope — no fallback or quota-visibility features.

## Environment Requirements

- Local development environment with the-one runnable (`make restart` workflow), SQLite + Fernet key on disk.
- A real Anthropic individual plan (Pro/Max) account for end-to-end verification — OAuth consent requires a browser.
- Network access to Anthropic auth and API endpoints.

## Open Questions

- [x] Auth-flow ownership → **Resolved (Architect, 2026-07-28)**: self-contained flow in the-one with a hand-rolled PKCE implementation against Anthropic's fixed public client, reusing only the generic OAuth periphery (callback route, state registry, popup UX, encrypted storage). Delegating to the `ant` CLI was rejected: it adds an external runtime dependency, moves sign-in and re-auth out of Administration (failing criteria 1 and 5), and cannot cleanly support multiple accounts (criterion 6).
- [x] Credential storage → **Resolved (Architect)**: add an encrypted `secrets` column to `llm_providers` via the established table-rebuild migration, mirroring the `mcp_sources`/`tool_configs` precedent, and extend the masked-secret API contract (strip-and-preserve) to the token keys.
- [x] Refresh write-back → **Resolved (Architect, shape only)**: a process-wide, per-provider-config single-flight credential source injected by the factory and shared across provider instances — prevents concurrent-refresh races that can invalidate a rotated refresh token. Detailed design belongs to the flight.
- [ ] Redirect-URI acceptance: does Anthropic's fixed OAuth client accept an arbitrary-port `http://127.0.0.1:{port}/api/oauth/callback` loopback, or only a code-paste (console callback) variant? **Must be spiked first in Flight 1** — it decides how much callback machinery is reused; the code-paste variant is a first-class fallback and is actually less code.
- [ ] Model listing under plan tokens: live `/v1/models` listing like the API-key provider, or a static catalog fallback if the endpoint behaves differently for subscription tokens. Flight-level decision; the criterion only requires that listing works.

## Known Issues

- [ ] **Third-party plan usage bills to Anthropic "extra usage", not the plan's included window** — discovered in Flight 1 (HAT), affects the mission premise. Plan OAuth sign-in works end-to-end, but Anthropic's current policy routes third-party app inference to the account's extra-usage balance ($200 promo credit for eligible accounts); without that entitlement, Sonnet/Opus requests hard-429 (bare `'Error'`, no retry-after) while Haiku works. Not addressable in the-one's code; remediation is account-side (enable extra usage / claim credit at claude.ai/settings/usage). Ref: anthropics/claude-code#45326.

## Flights

> **Note:** These are tentative suggestions, not commitments. Flights are planned and created one at a time as work progresses. This list will evolve based on discoveries during implementation.

- [x] Flight 1: Anthropic plan provider end-to-end — redirect-URI spike first, then credential acquisition and storage, provider implementation with automatic renewal, provider-type registration, Administration UI, and acceptance behavior tests. Pre-declared split point if leg design exceeds budget: credential acquisition/storage vs. provider + UI + parity tests.
