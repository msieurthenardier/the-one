# Behavior Test: Vision round-trip — image-grounded replies, image-only send, rejoin

**Slug**: `vision-round-trip`
**Status**: active
**Created**: 2026-07-10
**Last Run**: 2026-07-10-20-09-44 (pass, 7/7; Step 4 required an apparatus-fix rerun — see run log)

## Intent

Verify the live, real-model vision path end-to-end in the chat UI: an operator attaches an image
and gets back a reply that is actually grounded in the image's content (not a generic non-answer),
that an image-only send (no text) works without a client- or server-side 400, and that rejoining
the session afterward doesn't crash the WS or corrupt the rendered history. This needs a
**behavior test** rather than a unit/browser test because the core claim — "the model's reply
describes what is actually in the image" — can only be judged against a real vision-capable
provider's real output; the hermetic `tests/browser/test_flow_chat_image_attach.py` suite
(Flight 12 L08) covers the mechanical DOM/attach/payload contract against the deterministic mock
provider, but the mock's canned reply ("Mock response from the mock provider.") cannot exercise or
falsify actual vision grounding. Source material: the Flight 12 L08 HAT steps
(`missions/16-llm-provider-hardening/flights/12-message-content-multimodal/legs/08-ingestion-and-vision-hat.md`),
adapted here into re-runnable spec form.

## Preconditions

- the-one is running host-native and reachable on `http://localhost:8485` (the mission dev
  instance), with `THE_ONE_DEV_MODE=true`.
- A **live Anthropic API key** is configured on a vision-capable model (the default,
  `claude-sonnet-4-6` or later — vision is implicit, no feature flag). Verify with an **active
  probe** (decay-prone precondition: credentials expire/rotate): `POST
  /api/providers/{anthropic_provider_id}/test` returns a success result. If it fails, the test
  cannot proceed — this is a live-model test, not something a mock provider can substitute for.
- An agent exists (or is created via the Admin UI / API) using that Anthropic provider, with
  default tool/thinking settings — no special configuration needed for vision.
- A test image fixture is available locally with an unambiguous, describable subject (e.g. a
  photo of a red bicycle, or any image whose content a human reviewer can independently confirm
  before the run — write down the expected subject in the run log so the Validator has a ground
  truth to check the reply against). Do not use an abstract/ambiguous image — the Validator needs
  an unambiguous pass/fail bar for "grounded".
- A **chrome-devtools** browser apparatus is attached to 8485. **Never touch 8484.**

## Observables Required

- browser (rendered chat UI: the composer's staged-image chicklet, the user bubble's `[image]`
  indicator, the assistant reply text, post-rejoin history — measured via chrome-devtools;
  a11y-tree + screenshot as primary rendered-state evidence).
- http (the provider live-test probe in Preconditions — measured via curl/Bash; used only for the
  precondition check, not for step verdicts).

## Steps

| # | Actions | Expected Results |
|---|---------|------------------|
| 1 | (Setup, no judgment) Confirm the live-Anthropic precondition probe passed. Open a fresh chrome-devtools page at `http://localhost:8485`, hard-reload with `ignoreCache`. Select the vision-capable agent's chat welcome item. | The chat view opens for that agent; the session agent badge shows the agent's name. |
| 2 | Attach the test image fixture via the hidden file input (the composer's attach control). | [a11y] A chicklet appears in the `chat-attachments` row above the composer, showing a rendered thumbnail of the attached image (not a broken image icon). |
| 3 | Type "what is in this image?" into the message box and send. | The user bubble renders the typed text followed by the `[image]` indicator (not `[object Object]`, not a crash). The staged chicklet clears from the composer. |
| 4 | Wait for the assistant's reply. | Within a reasonable timeout (~30s), the assistant bubble renders a reply, AND the reply text is **grounded in the actual content of the attached image** — it describes the subject noted in Preconditions (e.g. mentions the red bicycle), not a generic "I can't see images" refusal or an unrelated answer. This is the core live-vision proof. |
| 5 | Attach a second instance of the test image fixture (or a different describable image); leave the message box **empty**; send via the send button. | The request completes with **no client-side block and no 400 from the provider** (the empty-text-block guard is exercised — image-only sends must omit the synthesized empty text block). The user bubble renders just the `[image]` indicator (no leading empty text). |
| 6 | Wait for the assistant's reply to the image-only turn. | Within a reasonable timeout, the assistant bubble renders a reply that is still grounded in the image's content — proving the image-only path reached the model correctly, not just that the request didn't error. |
| 7 | Reload the page (full browser reload, not an SPA navigation) and rejoin the same chat session. | The session loads **without a WS crash or an error banner**. Both prior turns render correctly from replay: the user turns show text + `[image]` (or just `[image]` for the image-only turn), and both assistant replies are present and match what was rendered live in Steps 4 and 6. |
| 8 | (Teardown, no judgment) Note in the run log whether the session should be cleaned up (deleted) or left as a fixture; if deleted, confirm via the UI or API that it no longer appears in the session list. | (empty) |

**Row conventions:** one row = one logical checkpoint. `[a11y]`-marked expectations are the
assistive-tech / rendered-state surface for the optional Accessibility Validator. Step 4 and Step
6's "grounded in the image" judgment requires the Validator to compare the rendered reply text
against the ground-truth subject recorded in Preconditions — record that subject explicitly in
the run log before Step 1 so the judgment isn't retroactively rationalized.

**Locators (apparatus-agnostic — the Executor maps to its MCP):** message composer
`data-testid="chat-input"`; attach control `data-testid="chat-attach-btn"` / hidden file input
`data-testid="chat-image-input"`; staged-image row `data-testid="chat-attachments"` with chicklets
`data-testid="chat-attachment"`; send button `data-testid="chat-send-btn"`; rendered turns
`data-testid="message"` with `.user` / `.assistant` role classes (`the_one/interfaces/web/static/js/areas/chat.js`).

## Out of Scope

- The mechanical attach/stage/multi-image/remove/cap/oversized-file DOM contract against the
  deterministic mock provider — fully covered by
  `tests/browser/test_flow_chat_image_attach.py` (hermetic, runs in `make test-browser`); this
  spec does not re-verify chicklet mechanics, only the live-model grounding claim mechanics can't
  reach.
- Non-Anthropic vision providers (OpenAI/Ollama vision support) — Anthropic is the only
  vision-wired provider as of Mission 16; add a variant when a second provider gains vision
  wiring.
- Own-image thumbnail rendering fidelity/design — a deferred follow-up per the Flight 12 L08 leg,
  not a correctness claim this test makes.
- Documents/PDF attachments — out of scope of the underlying capability (image-only today).
- Attach-while-a-turn-is-running behavior — explicitly out of scope of the underlying L08 leg
  (disable/ignore attach while busy); not exercised here.

## Variants

None today — a single live run against the default Anthropic vision-capable model is sufficient.
A future variant could re-run against a second image subject to reduce false-pass risk from a
lucky single-sample grounded reply.
