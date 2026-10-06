# Behavior Test: Chat Round-Trip (Mock Provider)

**Slug**: `chat-roundtrip`
**Status**: active
**Created**: 2026-07-04
**Last Run**: 2026-10-06-06-01-26 — pass (9/9; Light steps 1–6 + Dark steps 3–6; M25 F4 close gate, chats start as a pending chat)
**Updated**: 2026-10-05 (M25 F4 leg 8: step 3 starts through New chat and the agent picker, as a pending chat; steps 4 and 6 name the session the first send creates; the Dark variant runs in its own fresh context)

## Intent

Verify the chat *interaction* on the redesigned v3 chat surface end-to-end against the running instance, driven by the deterministic `mock` provider: a sent message appears as a right-aligned tinted user turn, the assistant reply streams in with the composer's Stop affordance visible during streaming, the finished reply renders markdown (bold + inline code) as real markup (not literal characters), and the whole round-trip survives a cold reload from the server. This is the SC7 down-payment for Mission 17 (a chat behavior gate on the redesigned surface) and complements `shell-navigation-smoke` (which verifies navigation but explicitly defers chat round-trips/streaming to this spec). A behavior test — not a Playwright test — because it exercises the *operator's live instance* through a real browser apparatus with rendered-state evidence (streaming, rendered markdown, session persistence) on exactly the surface the redesign changes; the mock provider makes the LLM reply deterministic so the assertions are stable with no live key.

## Preconditions

- The **instance under test** is running and serving (probe: HTTP 200 on `/` immediately before the run). Default `http://127.0.0.1:8485` for the M17 mission dev instance (the operator's packaged app owns 8484 — never target it). The orchestrator states the actual base URL at run time and it applies to every step below.
- **The instance was launched with `THE_ONE_DEV_MODE=true`** — required for the `mock` provider type to be creatable (the API rejects mock-typed creates with HTTP 400 when dev mode is off, and the provider-type dropdown filters `mock` out). This is a decay-prone precondition (a plain relaunch drops it), so Step 1 actively probes it. **Relaunch note**: if the probe fails, stop and relaunch the instance with `THE_ONE_DEV_MODE=true` (the M17 8485 instance sets it in its `.env`; a fresh instance needs it exported), then re-probe.
- A browser apparatus (goldfinch MCP) is attached and can open tabs to that origin. Per the apparatus doctrine (`the_one/agents.md`): if a viewport screenshot wedges (occluded/backgrounded window), the `printToPDF` fallback is sanctioned rendered-state evidence; the a11y tree is second-strongest evidence; a CDP page may be used for focus-state checks.
- The mock provider + mock agent this test needs are **seeded by the test itself** (Step 2) via the real HTTP API — no pre-existing chat data is assumed. Seeded entities should be cleaned up after the run (or left on the disposable dev instance).
- **Credential**: this instance is gated (Mission 20 Flight 1). Follow CLAUDE.md's
  "Behavior-test credential convention" — read the long-lived credential from the
  instance's data directory, mint a handoff URL for the Step-3 browser navigation
  (single-use; re-mint if navigating again), and attach `Authorization: Bearer
  <credential>` to the Step-1/2 HTTP calls.

## Observables Required

- browser (rendered page state, streaming DOM/a11y state, screenshots/printToPDF — measured via goldfinch MCP)
- http (provider-type probe + seeding POSTs — measured via `curl`/Bash or the browser's fetch)

## Steps

| # | Actions | Expected Results |
|---|---------|------------------|
| 1 | **Precondition-check (dev mode).** Probe the provider types the instance offers: `GET {base}/api/providers/types` (or open the provider-create form's type dropdown). | The response/dropdown includes a `mock` provider type (e.g. `{"value":"mock",...}`). If `mock` is absent the instance is NOT in dev mode — HALT and relaunch with `THE_ONE_DEV_MODE=true` per Preconditions, then re-run from here. |
| 2 | **Seed the mock provider + agent.** POST `{base}/api/providers` with `{"name":"chat-roundtrip-mock","type":"mock","base_url":"","config":{"models":["mock-default"],"delay_ms":1200,"stream_chunks":["Hello ","**world**"," and an ","`inline code`"," span."],"response":{"content":"Hello **world** and an `inline code` span."}}}` (expect HTTP 201; keep the returned `id`). Then POST `{base}/api/agents` with `{"name":"chat-roundtrip-agent","provider_config_id":"<id>","llm_model":"mock-default","system_prompt":"mock"}` (expect HTTP 201). *(`stream_chunks` is a LIST of strings — the streamed reply is their concatenation, which is what renders; `delay_ms` paces the stream so the Stop affordance in Step 4 is observable. Equivalently, seed both via the Studio UI.)* | (setup row, no judgment) |
| 3 | Open a fresh browser tab to the instance under test (base URL per Preconditions). Click the rail's **Chats** link (`#chats`). Click the Chats list's **New chat** (`chats-new-btn`), type `chat-roundtrip-agent` in the agent picker's search (`agent-picker-search`), and press **Enter**. | A **pending** new chat with the agent: the hash is `#chats/~new/chat-roundtrip-agent`; the chat header (`chat-header`) reads "New chat" with "with chat-roundtrip-agent" (`chat-agent-line`); the new-chat state (`chat-new-state`) names `chat-roundtrip-agent`; the composer's message box (`chat-input`, placeholder "Message chat-roundtrip-agent…") is enabled, with Send (`chat-send-btn`); the message log is empty. Nothing is created yet: the first Send creates the session. No error banners, no unstyled regions. |
| 4 | Type `hello` into the composer and Send it. **Immediately** (while the assistant reply is still streaming) observe the user turn and the composer's stop affordance. Capture evidence promptly — if the stream finishes before capture, raise `delay_ms` in Step 2 and repeat. | This first Send creates the session: the hash becomes `#chats/{id}` and the new-chat state gives way to the conversation. The sent message appears as a **right-aligned, tinted** user turn (a quiet accent-translucent wash, NOT a loud saturated fill). During streaming, a **Stop** affordance (accessible name "Stop") is **visibly rendered** in the composer (rendered state, not merely present-and-hidden in the DOM), and the assistant turn is progressively filling in. No error banners. |
| 5 | (Wait point, no actions — wait for streaming to complete.) | Within ~15s the assistant turn completes and its content renders as **real markup**: the `**world**` segment shows as actual **bold** text and the `` `inline code` `` segment shows as an actual inline code span — NOT the literal characters `*` or backtick shown as text [a11y]. Once done, the Stop affordance is no longer shown and a Send affordance is available again. |
| 6 | **Hard-reload** the page (defeat client-side cache — fresh load, not an in-app re-render) at the current session's URL (`#chats/{id}` from Step 4). | After the cold reload the same session rehydrates from the server: both the `hello` user turn and the assistant reply are present, and the assistant markdown is **still rendered as real markup** (bold + inline code, not literal characters). The round-trip persisted server-side. No error banners. |

## Out of Scope

- Markdown security hardening (safeHref scheme allowlist, mXSS/script-as-text inertness, streaming-boundary safety) — covered by the unit no-HTML-string invariant guard (`tests/test_ui_guards.py`) and the browser XSS regression suite (`tests/browser/test_markdown.py`).
- Code-fence / copy-button rendering depth and dual-theme pixel fidelity — covered by the local-only pixel snapshots (`tests/browser/test_visual_snapshots.py`) and the flight's dual-theme visual pass.
- Tool-activity traces and thinking disclosures — covered by `extended-thinking-tool-turn` and `gemma-tool-use-recovery`.
- Navigation / hash routing / theme-switch persistence — covered by `shell-navigation-smoke`.
- Real (non-mock) LLM providers, multi-turn conversations, tool-calling round-trips, and scroll-position ("jump to latest") behavior.

## Variants

- **Dark theme.** Re-run Steps 3–6 in Dark, in a **fresh browser context** (a new handoff mint): before Step 3, inside that context, set Dark through Settings › Appearance's theme control (or `App.theme.set('dark')`) and confirm `data-theme="dark"`. The theme choice lives in the context's `localStorage`, so Step 3's fresh tab must open in that same context. Record the theme option in effect before the variant and **restore it after** (if the original was "Auto", restore Auto — not the resolved mode); closing the context does that. Expected results are identical, additionally confirming the tinted user turn keeps primary-foreground text (legible over the dark accent-translucent wash) and the assistant prose + rendered markdown hold in dark. Overall verdict passes only if BOTH the light and dark runs pass.
