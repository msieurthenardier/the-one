# Behavior Test: Claude Plan (Token) Provider Chat

**Slug**: `anthropic-plan-token-chat`
**Status**: draft
**Updated**: 2026-10-12 (sortie 03 Architect cycle 1: `mask_ok` instead of the mask, a longer step-6 reply, a new chat in step 7)
**Created**: 2026-10-12 (sortie 03)

## Intent

Verify that a Claude Plan (Token) provider, created with a real token from `claude setup-token`, connects, lists models and runs a streamed chat turn on the operator's subscription, and that the token never comes back unmasked. This needs a behavior test because it exercises live inference against Anthropic with a real subscription credential, which unit and browser tests replace with stubs.

## Preconditions

- A dev instance of this branch is running on **port 8487 with a scratch data directory outside the repo** (e.g. `THE_ONE_PORT=8487 THE_ONE_DATA_DIR=/tmp/the-one-sortie03-scratch make up`). Never the operator's default `:8484` instance or default data directory (see CLAUDE.md's "Behavior-test credential convention" safety rule).
- The operator has placed a real `setup-token` token in a file outside the repo and named its path for this run (`TOKEN_FILE`). **The token is never typed, printed, quoted or written by any agent.** It enters the app only through the step-1 shell command, which reads the file itself.
- **Credential**: shell steps send `Authorization: Bearer <credential>` read from `<data_dir>/api-credential`; the browser session is reached through a handoff mint (`POST /api/session/handoff`), one mint per fresh navigation, per CLAUDE.md's convention.
- The operator names a model the plan allows (recorded in the run log); default `claude-haiku-4-5`.

## Observables Required

- shell (HTTP requests against the dev instance — Bash with `curl` and `python3`; `jq` is not installed on this host)
- browser (rendered Library and Chats UI — goldfinch MCP)

## Steps

| # | Actions | Expected Results |
|---|---------|------------------|
| 1 | Shell: create the provider without echoing the token. A short `python3` script reads `TOKEN_FILE` itself, strips whitespace, POSTs `{"name": "Plan token (HAT)", "type": "anthropic-plan-token", "base_url": "https://api.anthropic.com", "api_key": <token>}` to `http://127.0.0.1:8487/api/providers` with `Authorization: Bearer <credential>`, and prints only the status code, the response's `id`, `type`, `token_set_at`, `token_expires_around` and `oauth_active`, and a computed `mask_ok` boolean (the `api_key` value starts with `***` and is not the token). It never prints `api_key` itself, whose mask tail is the token's last four characters. | HTTP 201: `type` is `anthropic-plan-token`; `mask_ok` is true; `token_set_at` is today (UTC) and `token_expires_around` is about 365 days later; `oauth_active` is false. |
| 2 | Shell: `GET /api/providers` and `GET /api/providers/{id}`; check both bodies for the token (a `python3` one-liner that reads `TOKEN_FILE` and prints only whether the token string occurs in each body). | The token occurs in neither body; each body's `api_key` passes the `mask_ok` check and the two `api_key` values are equal (booleans only, never the values); `token_set_at` and `token_expires_around` match step 1. |
| 3 | Browser: open Library › Model providers, open "Plan token (HAT)", press Test. | The editor shows the Token field (masked), no sign-in section, and `provider-token-expiry` reading "Token added {today} · expires around {date ~1 year on}" with no warning style. Test reports success; no error text. |
| 4 | Browser: on the Agents destination, create (or open) an agent bound to "Plan token (HAT)", open the model picker, choose the operator's named model, save. | The model picker lists Claude models; the save completes with no error. |
| 5 | Browser: on Chats, start a new chat with that agent (New chat, then pick it) and send "Reply with exactly the word PONG." | A reply containing "PONG" appears; no error banner or toast. |
| 6 | Browser: send "Write about 600 words on why the sky is blue, in five paragraphs." Capture the transcript at least twice while the reply is being produced, then once after it completes. | Successive in-flight captures show strictly growing reply text (streaming), and the final reply is complete; no error. |
| 7 | Browser: on the agent editor, switch the agent's model to `claude-sonnet-4-6` and save. On Chats, start a **new** chat with the agent (New chat, then pick it): an open chat keeps the agent it was built with at join, so the old chat would still use the step-4 model. Send "Reply with exactly the word PONG." and wait up to 30 s (the SDK retries a 429 twice before giving up). Then switch the model back to the step-4 model and save. | The chat shows the plan-refusal message, beginning "Your Claude plan didn't allow this request to claude-sonnet-4-6" (exact wording after that is an acceptable variation), not a bare "Error" or a raw 429. (If the plan does allow Sonnet at run time and a reply arrives, record that in the run log and mark the step inconclusive, not failed.) |

## Out of Scope

- The OAuth type's sign-in and refresh — covered by `anthropic-plan-signin` and `anthropic-plan-chat-parity`.
- The expiry line's warning and past states — covered by browser tests with a patched provider row (a live token cannot be aged).
- A rejected or revoked token's error text — covered by unit tests with a stubbed 401; the operator may optionally check it after revoking the token at sortie completion.
- Plan usage limits and per-model availability.
