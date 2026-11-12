# Behavior Test: Widget Escape — a live widget in a real chat cannot reach out of its frame

**Slug**: `widget-escape`
**Status**: active
**Created**: 2026-11-09
**Last Run**: 2026-11-10-02-35-43 (pass, 9/9; [run log](widget-escape/runs/2026-11-10-02-35-43.md))

## Intent

Verify Mission 35 Flight 2's boundary claim end to end, in a real browser with real input, against a real chat:
an assistant reply that carries a `widget` block draws a managed, sandboxed card, the widget's own
code runs, and **nothing it tries leaves the card**.

The claim has seven observables:
- no request, datagram or connection reaches a listener the widget aims at (the sink is empty);
- the page's URL, route, history length and `popstate` count are unchanged by the widget;
- the widget cannot take focus away from the composer while the operator types;
- the DOM outside the card is unchanged (no new `<link>`, `<meta>`, dialog or window);
- no new page or dialog opens;
- the operator's data (`GET /api/agents`) is unchanged;
- the operator's own Back still works (one step, no entries the widget pushed).

This is a behavior test, not a flow test, because:
- the verdict comes from outside the browser: a separate process counts what arrives on three channels
  (HTTP, UDP for WebRTC STUN, TCP for a preconnect);
- the input must be real (a CDP mouse and keyboard, never a synthetic event), because the focus gate
  and the link gate depend on genuine user activation.

The in-frame battery is `tests/fixtures/widgets/escape.html` (the same file the contract tests use). It
draws its own pass/fail grid inside the frame (`window.__grid`: `refused`, `attempted` or `open` per
attempt; `open` is a breach).

## Preconditions

- **Instance under test.** A dedicated dev instance on a non-default port AND a fresh scratch data
  directory, started from a scratch working directory (CLAUDE.md "Behavior-test credential
  convention"; never 8484, never 8485, never the default data directory):

  ```
  mkdir -p $HOME/the-one-behavior-test-scratch/widget-escape/{cwd,data}
  cd $HOME/the-one-behavior-test-scratch/widget-escape/cwd
  THE_ONE_DATA_DIR=$HOME/the-one-behavior-test-scratch/widget-escape/data <repo>/.venv/bin/the-one rotate-api-credential
  THE_ONE_PORT=8491 THE_ONE_DATA_DIR=$HOME/the-one-behavior-test-scratch/widget-escape/data THE_ONE_DEV_MODE=true \
    <repo>/.venv/bin/the-one serve >serve.log 2>&1 &
  echo $! > serve.pid
  ```

  `{base}` is `http://127.0.0.1:8491`. Find the real server PID with `ss -ltnp | grep 8491` and stop
  the instance by that PID (a recorded PID, never by name or pattern).
- **The sink.** In another background process from the same scratch directory:

  ```
  <repo>/.venv/bin/python <repo>/scripts/widget_sink.py >sink.out 2>sink.err &
  echo $! > sink.pid
  ```

  The first line of `sink.out` is JSON `{"http": P, "udp": P, "tcp": P, "pid": N}`: the three loopback
  ports (and the sink's PID). `GET http://127.0.0.1:{http}/__sink/counts` returns
  `{"http": n, "http_requests": [...], "udp": n, "tcp": n}`; `/__sink/fixture` and
  `/__sink/fixture-focus` return the battery with the ports filled in (the main mode and the
  focus-stealing mode). Control requests are never counted. The sink refuses a non-loopback
  `--host` and stops on SIGTERM (stop it by `sink.pid`).
- **The reply.** A mock provider whose `config.response.content` is the escape-battery reply (a
  non-streamed reply), built from the sink's own fixtures:

  ```
  curl -s {sink}/__sink/fixture       > main.html
  curl -s {sink}/__sink/fixture-focus > focus.html
  python3 - <<'EOF'   # writes provider.json
  import json
  main, focus = open("main.html").read(), open("focus.html").read()
  text = "Escape battery:\n\n```widget\n" + main + "\n```\n\nFocus thief:\n\n```widget\n" + focus + "\n```\n"
  json.dump({"name": "we-mock", "type": "mock", "base_url": "", "config": {"response": {"content": text}}}, open("provider.json", "w"))
  EOF
  ```

  With the credential (`Authorization: Bearer $(cat <data>/api-credential)`): `POST {base}/api/providers`
  with `provider.json` (201); then `POST {base}/api/agents`
  `{"name":"we-agent","provider_config_id":"{provId}","llm_model":"mock-default","system_prompt":"mock","description":"widget escape"}`
  (201).
- **Probes.** `GET {base}/api/live` returns 200; `GET {sink}/__sink/counts` returns all zeros.
- **Browser apparatus.** Headless Chromium driven over CDP with **real input** (Playwright's
  `page.mouse` and `page.keyboard`, or CDP `Input.dispatch*`), never `dispatchEvent` or an
  `element.click()` from an eval. One fresh browser context, viewport 1440x900, authenticated by one
  handoff mint (`POST {base}/api/session/handoff` with the credential, then navigate to the returned
  URL). Attach **before** the first page load: an init script that counts `popstate`
  (`window.__pop = 0; addEventListener('popstate', () => window.__pop++)`), a `page.on('dialog')`
  counter, and `context.on('page')` / `context.pages` for new pages. On a WSL host with mirrored
  networking, run the instance, the sink and the browser inside one loopback-only namespace
  (`unshare -rn`, `ip link set lo up`) so Chromium does not abort with `ERR_NETWORK_CHANGED`.
  A practical shape: one namespace holder process, with every command entered through
  `nsenter --preserve-credentials -U -n -t <holder pid>`. Hand that prefix and the sink's HTTP port
  to the Validator with the step 2 report, so its read-only curls reach the same loopback. Drive the
  browser from one long-lived driver process for the whole run. If a context has to be replaced
  (for example after a driver bug), the replacement needs its own handoff mint, and only the
  replacement is judged.
- **Evidence notes.** In-frame state is read with Playwright's `frame.evaluate` on the widget's
  iframe (`[data-testid="chat-widget-frame"]`, its `content_frame()`), which does not grant user
  activation. The frame's origin is the string `"null"`. Focus is `document.activeElement` identity
  (tag and `data-testid`) through an eval on the main page. "The DOM outside the card" means:
  `document.head.innerHTML`, `document.documentElement.attributes`, `#app-rail`'s `outerHTML`, the
  count of `dialog[open]`, and the count of `iframe` elements outside `figure.ui-widget` (must be 0).
  The sink is read with curl, never the browser.
- **Baselines are taken after the chat exists.** `H0`, `P0` and `D0` are recorded in step 4, once the
  reply has rendered, not at the pending route. Creating the chat moves the route from
  `#chats/~new/we-agent` to `#chats/{id}`, and the app's router sets `document.title` from the route
  (`router.js`), so a baseline taken before that would differ in `<title>` for reasons that have
  nothing to do with the widget.
- **Rendered evidence per card.** For the `[a11y]` rows, take an element screenshot of each card,
  not only a viewport screenshot (the second card sits below the fold at 1440x900).
- **Back.** Alt+Left does nothing in headless Chromium. Step 9 goes back with CDP
  `Page.getNavigationHistory` and `Page.navigateToHistoryEntry` (current index − 1), and records the
  entry list before and after.

## Observables Required

- browser: DOM, `location.href`, `location.hash`, `history.length`, `window.__pop`,
  `document.activeElement`, the context's page list, dialog events, in-frame `window.__grid` and
  `window.__done`
- http: the sink's counts (curl), `GET {base}/api/agents`, the seed calls
- shell: the two background processes (PIDs, `sink.out`), the teardown

## Steps

| # | Actions | Expected Results |
|---|---------|------------------|
| 1 | **Setup (no judgment).** Start the instance and the sink as in Preconditions, seed the provider and the `we-agent` agent. Save `GET {base}/api/agents` as `agents0.json`. | (setup row, no judgment) |
| 2 | **Baseline.** Read `GET {sink}/__sink/counts`, wait 3 seconds, read it again. | Both reads are exactly `{"http": 0, "http_requests": [], "udp": 0, "tcp": 0}`. A control request is not counted, so reading twice changed nothing. |
| 3 | Open a fresh context (init script, dialog and page listeners attached), mint and use one handoff, navigate to `{base}/#chats`. Click **New chat** (`chats-new-btn`), type `we-agent`, press Enter. Record `location.hash`, `history.length`, `window.__pop`, the number of pages in the context and the number of `iframe` elements. | The hash is `#chats/~new/we-agent`; the header reads "New chat" with "with we-agent"; `chat-input` is enabled. One page in the context, no dialog seen, no `iframe` anywhere. The sink is still all zeros. |
| 4 | Type `go` into the message box (`chat-input`) with the real keyboard and press Enter. Wait for the reply. Then record the baselines: `history.length` (`H0`), `window.__pop` (`P0`) and the "DOM outside the card" set (`D0`). Take an element screenshot of each card. | The mock reply is rendered as two cards (`figure[data-testid="chat-widget"]`), each with the header "Widget by we-agent", in one assistant bubble. Each card has a frame (`chat-widget-frame`). The send button is enabled again. The hash is now `#chats/{session id}`. `H0` equals the `history.length` from step 3 and `P0` equals its `window.__pop` (creating the chat replaces the route, it does not push). [a11y] |
| 5 | Wait until the main battery has finished: `frame.evaluate(() => window.__done)` is true in the first card's frame (poll up to 10 s). Then read `window.__grid` from that frame. | `__done` is true. The grid has no entry whose status is `open` (no breach), and every key named below is present (a missing key is a failure). Every in-frame refusal entry is `refused` (only `refused` is allowed for these): `parent-dom`, `top-dom`, `top-location-read`, `top-navigation`, `cookie`, `local-storage`, `session-storage`, `window-open`, `alert`, `nested-realm`, `webrtc-undefined`, `exec-command`, `neutered-hold`. The network entries (`fetch`, `xhr`, `image`, `beacon`, `websocket`, `form-post`, `link-prefetch`, `css-url`, `css-import`, `data-worker`, `blob-worker`, `eventsource`, `dynamic-import`, `preconnect-script`, `dns-prefetch`, `webrtc-stun`, `history`, `flood`) are `attempted` or `refused`: `attempted` only means the code ran, and step 6's sink read is what proves nothing arrived. (`webrtc-stun` is normally `refused` with a TypeError, because `RTCPeerConnection` is neutered.) The frame's `location.origin` is `"null"`. |
| 6 | Wait 3 more seconds (the battery has delayed attempts at 300 ms and WebRTC gathering). Read the sink. | **The sink is empty**: `http` 0 with `http_requests` `[]`, `udp` 0, `tcp` 0. |
| 7 | With the real mouse: click in the middle of the first card's frame; then scroll the card's **View source** summary (`chat-widget-source-details`) into view with the real wheel if needed and click it; click **Pause**, then **Resume** (read the button's label before each click); then click the frame again. Record whether the first card's source disclosure is open, the page list, dialog count, `location.href`, `history.length`, `window.__pop`, the "DOM outside the card" set (`D1`) and the sink. | The first card's source disclosure is open (the click reached the card's own control). The button read Pause before the first click and Resume before the second. The URL is the same as in step 4 (`#chats/{session id}`), `history.length` equals `H0`, and `window.__pop` equals `P0`. The context still holds **one page**; no dialog event fired and `dialog[open]` is 0. `D1` equals `D0` in `document.head.innerHTML`, `<html>` attributes and `#app-rail` (apart from the route's own `aria-current` link state, which is unchanged for Chats), and no `iframe` exists outside a `figure.ui-widget`. The sink is still all zeros. [a11y] |
| 8 | Scroll the log with the real mouse wheel until the second card (the focus thief) is in view and its frame is loaded (`frame.evaluate(() => !!document.getElementById('steal'))` is true); stop scrolling once the log can scroll no further. Record the thief's liveness: its card's position in the viewport and its Pause/Resume button label. Click into the composer (`chat-input`) with the real mouse. Type `hello typed text` with the real keyboard, key by key, over about 2 seconds, while the thief's loop runs, sampling the main page's `document.activeElement` (with a timestamp) before the first key, every ~300 ms during the typing, and after the last key, all from one driver command. | The thief is live: its card is in the viewport, its button reads Pause (not Resume), and `#steal` exists. `document.activeElement` is the composer textarea (`data-testid="chat-input"`) at the start, in **every** sample during the typing (at least 5 samples while keys are being pressed) and after the typing. The composer's value is exactly `hello typed text`. The frame's `document.activeElement` is not the page's. The sink is still all zeros. [a11y] |
| 9 | Clear the composer. Record the navigation history (`Page.getNavigationHistory`: every entry's URL and the current index). Go back one entry with CDP `Page.navigateToHistoryEntry` (current index − 1). Record `location.hash`, `window.__pop`, `history.length`, the navigation history again, and the page list. | Exactly one step back: the current index dropped by 1, `window.__pop` is `P0 + 1`, and `history.length` is unchanged. The entry Back landed on is an app route from before the widget ran. If that entry was a bare `#chats`, the app may rewrite it in place to the last chat (`#chats/{id}`, the same entry, through the router's replace-only sync), which is not a failure. **No history entry and no hash contains `widget-push` or `widget-replace`** (the widget's `history.pushState` / `replaceState` attempts left no entry). The context still holds one page, no dialog fired. |
| 10 | Read the sink one last time and `GET {base}/api/agents`. | The sink is all zeros. The agents response equals `agents0.json` exactly. |
| 11 | **Teardown (no judgment).** Close the context. Stop the sink by `sink.pid`, then the instance by the PID `ss -ltnp` showed for port 8491 (confirm the port is free). Remove `$HOME/the-one-behavior-test-scratch/widget-escape`. | (setup row, no judgment) |

## Out of Scope

- **The widget's rendering, controls, pause and lifecycle, and the hang guard:** the contract lanes
  `contracts-widget` and `contracts-widget-lifecycle`, and the chats-widgets flow tests.
- **WebKit and Windows engines:** the engine-matrix measurements in the flight log and the desktop
  leg's real-shell passes (this test drives Chromium).
- **The page's response headers** (`frame-src 'none'`): `tests/test_app_frame_policy.py` and the
  chats-widgets flow test.
- **Link-route and navigation modes of the battery** (`nav-*`, `link-*`): the contract tests, which run
  one attempt per load.

## Variants

None. The theme does not affect the boundary.
