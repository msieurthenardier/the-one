# Backlog

Future ideas not yet promoted to missions. Capturing the thought while it's fresh; not a
commitment, not a current mission. Promote to a `missions/NN-<slug>/mission.md` via `/mission`
when ready.

---

## Privileged-client boundary: close the co-resident local-process hole

**Status:** idea / future mission seed — **NOT** scoped to any current mission. Requires a
deliberate **threat-model expansion**, so the design work comes before the code.
**Captured:** 2026-06-20, during a desktop-app architecture review session.

### The thesis
GleepGlorp exposes privileged capabilities — filesystem read/write, shell + PTY execution, a
Python interpreter, arbitrary HTTP — over a **localhost HTTP/WebSocket server with no auth on
routes by design**. The desktop window (`the-one app`) is a chrome-less webview pointed at that
same server; it has **zero privileged relationship** to the backend. Architecturally, "the app"
and "any browser tab" and "any local process running `curl`" are the **same client class**.

The window should be a **privileged client** — privileged *because the server itself spawned it
and handed it an in-memory secret* — and everything else should be unprivileged by construction.
The operator should make capability choices deliberately and feel confident nothing else on the
machine is quietly piggybacking on GleepGlorp's privileges.

### Why (the evidence — it's in our own code)
The Origin allowlist is a **browser-CSRF mitigation, not authentication**. From
`the_one/interfaces/web/middleware.py` (lines 39-41), missing-`Origin` callers pass:

> *HTTP without an `Origin` header: passes (curl, server-to-server callers; the threat is
> browser-mediated requests, which always include `Origin` ...)*

A native local process isn't a browser — it simply omits `Origin` (or sets it to
`http://localhost`) and is fully authorized. Combined with "no auth on routes by design"
(`SECURITY-MODEL.md`), that means:

> **Any process running as the operator's user can `POST http://127.0.0.1:8484/api/...`, create an
> agent with shell access, and run arbitrary commands — with zero credentials.**

GleepGlorp becomes a **confused deputy**: a no-friction, no-credential API to the filesystem and
shell that anything on the box can drive. The current `SECURITY-MODEL.md` threat model names
"single-user, operator trusted, no multi-user" but does **not** address the case the operator
actually worries about: **another process running as that same user**. This is currently an
*implicit non-goal*; the proposal is to make it an explicit, defended goal.

### The honest ceiling (must be designed in, not oversold)
GleepGlorp's blast radius can never be **smaller** than "what a process running as the operator's
UID can already do." If hostile code is already running as the user, it can read the user's files
directly — it does not *need* GleepGlorp. So the achievable goal is **not** "defend against
same-user malware" (impossible without OS-sandboxing GleepGlorp itself, and moot because such
malware is already game-over). The goal is:

> Stop GleepGlorp from being an **ambient amplifier** — raise the bar from "any process drives it
> with a one-liner" to "a process must either steal a credential protected by OS file permissions,
> or *be* the window the server itself launched."

That is the difference between "a random Electron app's bundled telemetry SDK pokes localhost ports
and finds a shell" (closeable, and worth closing) and "targeted malware running as the user" (not
GleepGlorp's job). The mission must state this boundary explicitly so the new mechanism does not
imply more protection than it delivers.

### Mechanisms (ranked strongest-honest first)
1. **In-memory, per-launch token injected only into the server-spawned window.** The server mints
   a random secret at boot, hands it to the pywebview window it launched (JS bridge /
   `evaluate_js`), **never writes it to disk**, and the middleware requires it on every mutating
   request + WS upgrade. No other process — even same-user — ever sees it (never on the
   filesystem; delivered only to a child the server controls). This is the literal realization of
   "the window is privileged because the server birthed it."
2. **Unix domain socket (POSIX) / named pipe (Windows) instead of TCP loopback.** Removes the
   entire port surface — nothing to scan, no DNS-rebinding, no other-user-on-a-multiuser-box.
   Protected by filesystem perms (0600 socket in a 0700 dir). Add `SO_PEERCRED` (Linux) /
   `GetNamedPipeClientProcessId` (Windows) to reject connections outside the expected UID/PID
   lineage. Does not stop same-user (the ceiling above), but kills everything below it.
3. **Browser mode (`the-one serve`) becomes an explicit, separate opt-in trust mode** with its own
   on-disk-or-printed token the operator pastes — matching "operator makes the choice
   deliberately." Today browser and window are interchangeable; here they become *different trust
   modes*, and the weaker one is something you opt into on purpose.
4. **Keep the Origin allowlist** as defense-in-depth for the webview's own JS. It was never the
   boundary needed for local processes, but it is still correct for browser-mediated requests.

### The bigger confused-deputy this does NOT close (state it explicitly)
Closing the local-API hole does **nothing** for the scarier amplification: the agent fetches an
untrusted web page or reads an untrusted file, and an **indirect prompt injection** makes the
*agent itself* run `rm -rf` or exfiltrate keys. That is a separate axis — handled by
capability-gating, human-in-the-loop confirmation on privileged tool calls, and the bubblewrap
box-by-default already shipped (M14). The token/transport work must not create a false sense that
the whole confused-deputy class is closed.

### Scope notes for when this becomes a mission
- **Design-first.** Write the threat-model delta into `SECURITY-MODEL.md` (new "co-resident local
  process" threat + what is in/out of scope per the honest-ceiling section) **before** any code.
  This is a deliberate expansion of a currently-implicit non-goal.
- **Lead with mechanism #1** (in-memory token injected into the spawned window + middleware
  enforcement + `serve` as an explicit opt-in mode). It restores the native/browser distinction
  cheaply without touching the all-HTTP architecture that the CLI, AIAT, and browser-test harnesses
  all depend on.
- **Sequence the transport (#2) as a follow-up flight**, not the first pass — UDS/named-pipe is a
  larger change and the token alone already closes the ambient-amplifier hole.
- **Do NOT rip out HTTP.** It is load-bearing (tests, CLI, AIAT, the Playwright browser harness all
  ride the HTTP/WS surface). The privileged-client work layers on top of it.
- **Preserve the test harnesses.** The `app_clean` browser fixture binds uvicorn on a random
  OS-allocated port and the middleware allowlist already accepts any localhost port; the new token
  gate must have a test-injectable path so browser/AIAT runs can present a valid credential.
- **Watch the dev-ergonomics footgun separately.** Independent of the security work: `the-one app`
  and `the-one serve` today share a port + `data_dir`, so a stale browser tab and the window can be
  two live writers against one SQLite. Giving the desktop profile a distinct port + `data_dir` is a
  small, today-sized change worth doing regardless of which trust philosophy is chosen.
</content>
</invoke>
