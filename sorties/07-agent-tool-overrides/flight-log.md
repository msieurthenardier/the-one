# Flight Log: Agent tool overrides

**Flight**: [Agent tool overrides](flight.md)

## Summary
Sortie planned 2026-10-27 from an operator report on the Windows build: an agent whose file tools were allowed only a WSL folder could not start a chat, with a message naming only `FilesystemConfig`. Charter agreed with the operator the same day, after discovery in conversation (recorded below). Execution waits until Mission 31 has completed and shipped.

---

## Planning Notes

### Discovery (2026-10-27, with the operator)
- **The refusal was the narrowing rule working as designed.** Each agent Allowed paths entry must lie within some app-wide entry (`resolver.py::_check_narrow_prefix`). The app-wide list was `~` (the Windows home); a `\\wsl.localhost\<distro>\…` folder is not inside it. With both `~` and the WSL folder in the agent's list, the WSL entry still fails on its own.
- **With `~` alone the agent still reached the WSL folder — through `shell`.** The file tools enforce the allowlist at call time (`filesystem.py::_filesystem_check`), so a `read_file` there would be refused; but on Windows `shell` and `python_exec` run under `PassthroughSandbox` (SECURITY-MODEL.md "Windows: interactive tools run unsandboxed"), limited only in their starting directory. Operator confirmed the access was via `shell`.
- **The pre-fill defect is separate and real.** `seedValue` in `areas/shared/tool-config-fields.js` fills an agent field with the app-wide value; the Save walk in `areas/studio/agent-form-data.js` stores every non-empty field. Opening a panel and saving copies inherited values into the override.
- **A WSL entry in the app-wide default was considered and rejected for this sortie.** It would widen every agent without execution tools to the whole Linux home, the default denied paths (`~/.ssh` etc.) expand to the Windows home and would not protect it, a bare `\\wsl.localhost` root contains nothing (each distro is its own UNC drive), and `\\wsl$\…` and `\\wsl.localhost\…` are unrelated strings to the containment check. Folded into the separate Windows default paths item.
- **Stale overrides: clip and tell, never disable** (operator, 2026-10-27). Compared with refusing the chat (agents broken until hand-fixed, connector agents silently) and with disabling the tool (adding one app-wide denied path would strip file tools from most agents). The earlier objection to clipping (it would silently drop a folder the operator had just added) no longer applies once Save refuses widening: a stale override can then only come from the operator tightening the app-wide value later.
- **Where the "tell" shows** (operator, 2026-10-27): the chat's agent drawer, an indicator on the agent editor's Built-in tools tab and on the Agents list row, and the field itself. Notices are not dismissible. One sortie, at about three legs plus a possible HAT (operator accepted the overrun of the two-leg soft limit).

### Flight design (2026-10-27)
- **Code reconnaissance** (Explore agent, read-only, at `142dbee`). Findings that shaped the design:
  - An agent's own paths never reach Shell or Python on any platform. Their cross-config view is resolved with no agent override (`builtins.py:153-168`), and `host_access` uses it (`shell.py:94`). This widened criterion 4 from "On Windows" to every platform (operator, below).
  - Denied lists are stored as the full union of app-wide and agent entries, and the check requires it. That made DD3 (store additions, resolve as a union) a precondition of criterion 2.
  - An empty `host_allowlist` means "any host" (`_web_config.py:350`), but the resolver treats any agent list as widening it. Clipping it without a sentinel would widen an agent to every host (DD4).
  - Lowering a maximum timeout can trip the `default <= max` validators (DD2).
  - The failure paths that are worst today: the WebSocket `join` of an existing chat drops the socket on a build error, and connector inbound drops the message silently (DD7).
  - A Settings tool save doesn't invalidate the `agents` store (DD8). Neither `App.ui.tabs` nor `App.ui.listPane` has an indicator option (DD11).
- **Operator decisions:**
  - Shell paths: tell on every platform. Fencing Shell with the agent's paths in the Linux sandbox is a separate item.
  - Pinning: own once changed.
  - Copied values: one-time cleanup.
  - HAT: yes, on Linux.
  - One folder for all nine file tools: out of scope (Flight Director recommendation, not contested).
- **Legs: 4 plus an optional HAT** in the first draft, over the sortie soft limit of 2 plus HAT. The operator had accepted about 3 legs plus a HAT, and the cleanup was a leg of its own because it rewrites stored data.
- **Architect review 1 (Opus): approve with changes, all adopted.**
  - **High, all three adopted:**
    - An agent `host_allowlist: []` against a non-empty app-wide list resolves to "any host" (live today through the API). Empty now means "any host" on both sides (DD2, DD4).
    - "Use narrowed value" could quietly widen an agent, because an own empty list doesn't survive the Save walk. It isn't offered when the effective value is empty or "no hosts" (DD9).
    - The `none.invalid` sentinel relied on DNS. It is now a constant that `_url_check` enforces in code, with a test that needs no DNS (DD4).
  - **Medium:**
    - Save 422 covers every failure type: pydantic bounds, type mismatch, no-marker keys, path canonicalisation errors (DD5).
    - Default follows a lower maximum (DD2).
    - `clip_override` is total over arbitrary JSON, with property tests (DD1).
    - The `join` fix uses a degraded `build_failed` restore (`_build_session_joined_degraded`), not a `system` frame the client ignores while joining (DD7).
    - `download_file` joins the Shell/Python note, which now names read_file's app-wide row (DD10).
    - The sandbox probe is warmed off the loop in the lifespan, and browser tests pin the posture client-side (DD10).
    - Notices skip hidden fields and disabled tools (DD6).
    - Notices are computed in a thread and memoised, decided now rather than left as a divert (DD6).
    - The cleanup marker is written after a partial failure, and the stale-copy limitation is named in the release notes (DD13).
  - **Low:**
    - There are exactly five `_agent_response` callers; no self-configuration route returns an agent (DD6).
    - "Changed" means JSON-canonical per field (DD5).
    - The impact route shares the PUT's config computation (DD8).
    - The list of tests that change was completed (Verification).
  - **Legs re-cut to 3 plus HAT,** matching what the operator accepted:
    - the cleanup joins the agent-tab leg, since "stop copying" and "remove the copies" are one criterion;
    - the `execution_sandbox` server half moves to that leg too;
    - the impact route (both halves) moves to the notice-surfaces leg.
  - **New, pre-existing finding:** redirects bypass `host_allowlist`/`host_denylist`. `_url_check` checks only the first URL, and the transport re-checks only the SSRF block list.
- **Operator, 2026-10-27: fold the redirect fix in.** It lands in leg 1 as DD15, and the charter gains criterion 5. That is over the four-criteria guideline, but the operator chose it explicitly, and it is the same outcome: the limits an agent shows actually hold.
- **Architect review 2 (Opus, final cycle): approve with changes, all adopted.**
  - **High:** DD15 as written would have refused every relative redirect on a pinned host whenever an allow list is set. The transport pins by mutating `request.url` to the IP, and httpx resolves `Location: /next` against that same request; the reviewer reproduced it with a mock transport. Fix: pin on a copy of the request, never treat an IP hop as its `sni_hostname`, and test the real pin path with a relative `Location`.
  - **Medium:**
    - A list holding `NO_HOSTS` always fits, or the clip's own output would fail strict `resolve`.
    - `NO_HOSTS` and the new marker live in `resolver.py`, avoiding a circular import.
    - Uncanonicalisable denied paths are dropped per entry, since `model_post_init` would raise at build.
    - Bad list entries are dropped one at a time, and a non-list allow value clips to its strictest form, never to inherit.
    - DD5 checks per field over the whole override: cross-field errors are attributed to a field, and the catch order is fixed (`ValidationError` subclasses `ValueError`).
    - The `build_failed` restore gained its client half (banner, reason, disabled input) in leg 1.
    - An unchanged own number is exempt from the browser range check, so a stale value never blocks Save.
  - **Low:**
    - The client `allowed()` change ships with the marker in leg 1.
    - The coupled default is report-only and never written.
    - `OSError` is caught too: exception types differ by Python version and platform.
    - One IDNA host normalisation is used for both checks.
    - The `execution_sandbox` tests pin the selection rather than reading the host's.
    - The notice cache is bounded, with the scope filter outside it.
    - The tile on/off switch invalidates `agents`.
    - The unknown-tool 422 applies only to new or changed entries.
    - The cleanup marker is written in a `finally`.
    - A citation range was corrected (`app.py:1645-1676`).
  - **Suggestions adopted:**
    - the Shell/Python note shows only when those tools are on app-wide too;
    - `/api/config` never blocks on the probe;
    - a per-leg citation re-check;
    - an "any host" notice sentence.
  - **Legs: 4 plus HAT.** The reviewer asked whether DD15 should be its own leg or checkpoint. It is now leg 2, `redirect-hosts`, because it changes the SSRF transport, a different risk with its own review. That is over the operator's "about 3", so it goes back to the operator (sortie skill, step 5).
- **Design review cycles: 2 of 2 used.** No further Architect cycle.

---

## Leg Progress
*(execution not started)*
- **Operator, 2026-10-27:** keep 4 legs plus HAT, with the redirect fix as its own leg (sortie gate step 5: still one decision cluster, so no escalation). Sortie marked **ready**. Execution waits until Mission 31 has completed and shipped. At execution start: rebase onto `main`, re-check the Citation Audit, build the worktree venv and baseline every gated lane, then `/mission-control:agentic-workflow sortie 07`.
- **2026-10-28: rebased.** Mission 31 completed and shipped (v0.12.3). The branch moved from `142dbee` to `main` at `c236622` (a fast-forward: the sortie files are still uncommitted). Citation Audit re-checked against the new base. Eleven cited files changed: `api.py`, `app.py`, `connectors/inbound.py`, `agent-editor-controller.js`, `ui/list-pane.js`, `agent-drawer.js`, `chat.js` (split into modules by M31 F6), `tools-editor.js`, `tools-page.js`, `agents.md` and `CLAUDE.md`. Every cited mechanism still holds, and the rows carry the new line numbers. One design note added: M31 F6 L10b gave `App.ui.listPane` an `activity` slot (an aria-hidden mark plus a visually hidden text run, `chats` rows only), so DD11's Agents-row notice extends that pattern instead of inventing a second one.
- **2026-10-28: on hold** (operator). Status stays `ready`; execution has not started. Nothing was built or run: no venv, no baseline. When it resumes, rebase onto `main` again and re-check the Citation Audit before the venv and baseline steps.
