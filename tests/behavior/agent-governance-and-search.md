# Behavior Test: Agent-loop governance — search config, context-budget governor, fullness overlay

**Slug**: `agent-governance-and-search`
**Status**: active
**Created**: 2026-06-25
**Last Run**: 2026-06-25-19-37-47 (9/9 PASS — see `runs/2026-06-25-19-37-47.md`)

## Intent
Verifies the operator-facing guarantees added by Flight 08, end-to-end, in a live
instance: (1) the `web_search` tool is **configurable** in the admin form — an engine
dropdown reveals only the selected engine's fields, API-key fields render **masked with an
eye-toggle**, and selections persist; (2) a chat turn that fetches a **large valid page**
**completes with a bounded tool result** (the context-budget governor) instead of hanging
or poisoning context; (3) the telemetry overlay signals context **fullness** both by color
**and** by a non-color, screen-reader-perceivable label; (4) `web_search` surfaces results
or an **honest error**, never a silent "No results found" that drives the model to guess
URLs. These span the admin UI, the tool layer, the hand-rolled agent loop, the WebSocket
protocol, and the Chat UI — only observable by driving a live instance, which is why the
Witnessed paradigm fits.

## Preconditions
- A dev instance of the-one serves on `http://localhost:8485` with the Flight-08 working
  tree applied (`THE_ONE_DEV_MODE=true`).
- To make the overlay threshold reliably observable in a short session, the instance runs
  with a LOW warn threshold, e.g. `THE_ONE_CONTEXT_WARN_PCT=5` (and a crit above it, e.g.
  `THE_ONE_CONTEXT_CRIT_PCT=20`). Default 70/90 is fine too but harder to reach live.
- A chat agent exists with the web tools enabled (`http_request`/`fetch_url`/`web_search`)
  on a **tool-capable model** — preferably a Sonnet agent using `ANTHROPIC_API_KEY` (mirrors
  the F07 `sonnet-loop-test` precedent) for reliable tool use; a local `qwen2.5:7b` web-tool
  agent is an acceptable fallback. Provider key valid; outbound network reachable.
  **Use a SERVED model id** (e.g. `claude-sonnet-4-6`) — verify against the provider's live
  model list, not the bundled catalog (stale ids 404). NOTE: changing an agent's model does
  NOT retro-apply to an existing chat session — start a NEW conversation to bind it.
- **Threshold math depends on the model's context window.** The low warn/crit precondition
  must be set relative to the model in use: a 1M-window model at warn=5% needs ~50k context
  tokens to cross warn. A single bounded ~256 KB tool result ≈ ~64k tokens, enough for warn.
- web_search engine left at the **DuckDuckGo** default for the search step (no key needed).
- **Credential**: this instance is gated (Mission 20 Flight 1). Follow CLAUDE.md's
  "Behavior-test credential convention" to reach it — read the long-lived credential from
  the instance's data directory, then mint a handoff URL (`POST /api/session/handoff`)
  before the Step-1 browser navigation. A handoff credential is single-use; a fresh
  navigation to the app root needs a fresh mint.

## Observables Required
- browser (admin Tools form: engine `<select>`, per-engine field rows shown/hidden, password
  input `type` + eye-toggle, masked value on reload; Chat UI: streamed assistant text, the
  thinking/stop control, the telemetry overlay's `.context-bar`/`.t-ctx-pct` classes and the
  container `aria-label`) — measured via chrome-devtools.
- http (optional cross-check of `/api/config` thresholds and `/api/tools/configs/web_search`
  masked response) — measured via shell `curl`.

## Steps

| # | Actions | Expected Results |
|---|---------|------------------|
| 1 | Open browser to `http://localhost:8485`. Navigate to Administration → Tools and open the `web_search` tool config. | The web_search config form renders with an engine selector (`search_backend`) as a **dropdown** (`<select>`), defaulting to DuckDuckGo. No API-key fields are visible for DuckDuckGo. |
| 2 | In the engine dropdown, select **Brave**. | Exactly Brave's field appears — a `brave_api_key` input rendered as a **password** field (`type="password"`) with an **eye-toggle** button; SearXNG / Google PSE / Tavily fields stay hidden. `[a11y]` the eye button has an `aria-label` ("Show password"). |
| 3 | Click the eye-toggle on the Brave key field. | The input flips to `type="text"` (value visible) and the button's `aria-label` switches to "Hide password". Clicking again flips it back. |
| 4 | Select **Google PSE** in the dropdown. | Brave's field hides; Google PSE's **two** fields appear (`google_pse_api_key` masked + `google_pse_cse_id` plain). Switching engines reveals exactly the selected engine's fields. |
| 5 | (REQUIRED masked round-trip, hardened from the 2026-06-25 run.) Select **Brave**, enter a dummy key (e.g. `test-brave-key-12345`), Save. Hard-reload, reopen, reselect Brave and read the key field's value. Then select **DuckDuckGo**, Save, hard-reload, reopen. | The Brave key reloads **MASKED** (`***…2345`, rendered as bullets) — NOT the plaintext, NOT empty (leg-3 encrypted-secret + masking contract; cross-check `/api/tools/configs/web_search` returns the masked form). Final state: engine is DuckDuckGo, all per-engine fields hidden, save succeeded. |
| 6 | (Setup) Start a new chat with the web-tool agent (tool-capable model). | Chat UI loads; agent selected; input enabled. |
| 7 | Send: "Use the fetch_url tool to GET `https://jsonplaceholder.typicode.com/photos?_limit=2500` and tell me roughly how many bytes the tool returned, and quote verbatim any truncation notice at the end of the tool output." (Pinned to a deterministic **256 KB–1 MiB** body, hardened from the 2026-06-25 run: a body OVER the 256 KB governor ceiling but UNDER the 1 MiB transport safety cap, so the **governor** truncation — not the transport hard-abort or a tool timeout — is reliably exercised. The gutenberg book timed out at the tool layer; `/photos` unlimited (~1 MiB) trips the transport cap *before* the governor.) | Within 150s the turn **completes** (thinking clears; final message renders) — no hang. **PASS criterion is the tool-result-level observable** (from the activity trace), NOT the assistant's prose: the `fetch_url` result returned to the model is bounded to **262,144 bytes** (the 256 KB governor ceiling) and ends with the verbatim governor marker `[... governor truncated N bytes; showing first 262144 bytes to fit the model context budget ...]`. The conversation stays coherent. |
| 8 | (Wait/observe) Inspect the chat telemetry overlay after the large-fetch turn (and send one or two more short messages if needed to cross the warn threshold). | The overlay's context bar / pct reaches the **warn** state (`.context-bar.warn` / `.t-ctx-pct.warn`, orange) and, if crit is crossed, `.crit` (red). `[a11y]` the overlay container `aria-label` reads "Token usage: N% of context, approaching limit" (warn) / "…, context nearly full" (crit) — the fullness is conveyed **without relying on color**. |
| 9 | Send: "Search the web for `obscure nonexistent gibberish term zzzqqx9988` and tell me verbatim what the search tool returned." | The agent's report is **honest**: either real results, OR an explicit tool error surfaced as `[error] …` (blocked/unavailable/empty). It is **not** a silent "No results found" that the model then "works around" by inventing/guessing URLs. The turn completes. |

**Row conventions:** rows 1 and 6 are setup; the judged checkpoints are 2 (show_if + masked + eye a11y), 3 (eye-toggle reveal/aria), 4 (engine-switch reveals only selected), 5 (persist + reload-masked), 7 (governor bound + no-hang), 8 (overlay color + non-color a11y), 9 (honest search surfacing).

## Out of Scope
- Exact governor byte bound / fraction math (asserted in `tests/test_governor.py` unit tests,
  not re-measured live).
- Encryption-at-rest of keys on disk (asserted in `tests/test_db_repositories.py` /
  `tests/test_api_config.py`; here only the masked round-trip is observed).
- SearXNG / Brave / Tavily live result quality (needs operator keys / a running SearXNG) —
  the search step uses the keyless DuckDuckGo default and judges **honesty**, not counts.
- Interrupt / queued-send / no-hang-on-stream (covered by `chat-loop-hang-and-cancel`).

## Variants (optional)
- Re-run steps 6-9 against a local `qwen2.5:7b` web-tool agent to confirm the governor +
  honest-search guarantees are provider-agnostic (tool-use reliability permitting).
