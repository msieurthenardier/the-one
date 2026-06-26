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

---

## Packaging consolidation: evaluate Briefcase + close the cross-platform installer gap

**Status:** idea / future mission seed — **NOT** scoped to any current mission. Starts as a
**spike/evaluation**, not a committed migration.
**Captured:** 2026-06-20, during a packaging review comparing GleepGlorp to the sibling `goldfinch`
project.

### The thesis
GleepGlorp's packaged experience is **Windows-only and built from a two-tool chain** — PyInstaller
(`packaging/windows/the-one.spec`, the one-dir freeze) wrapped by Inno Setup
(`packaging/windows/the-one.iss`, the installer). It is careful, polished work (stable AppId,
close-to-tray Restart Manager handling, an inert-but-ready signing hook), but mac and Linux users
get no installer at all — they fall back to `pip install` plus, on Linux, a **manual
`sudo apt install gir1.2-webkit2-4.1`** for the WebKitGTK backend (the soft spot already noted in
the README's desktop-window section).

Evaluate **[Briefcase](https://briefcase.readthedocs.io/) (BeeWare)** as the Python analog of
`electron-builder`: one tool producing platform installers (MSI, DMG, AppImage, deb/flatpak) from a
single config. The goal is to (a) collapse the PyInstaller + Inno two-tool chain into one contract,
and (b) ship real mac + Linux installers so the *packaged product* is uniform instead of lopsided.

### Why (the evidence — the goldfinch contrast)
`goldfinch` ships Windows (NSIS), mac (dmg+zip), and Linux (AppImage+deb) installers from a **single
`electron-builder` config block**, and its release is a tag-driven affair. GleepGlorp needs two
recipes that must agree, ships only Windows, and carries a display-name/slug split (*GleepGlorp AI*
vs *the-one*) as one more thing to keep straight. The polish gap is real — but a chunk of it is
**stack-inherited**: Electron *is* a packaging-first runtime (it ships its own runtime, so "make an
installer" is one mature command), whereas Python desktop packaging is a retrofit. Briefcase is the
closest thing to closing the *ergonomic* half of that gap without leaving Python (the right call for
an agent runtime — ecosystem gravity, per the earlier stack review).

### The hard constraint: GitHub Actions minutes (shapes the whole design)
**This is a first-class design input, not an afterthought.** The operator is **out of GitHub Actions
minutes**, which is the actual reason the Concourse/GitHub CI split exists on both projects. The
standing pattern is:

> **Do all-the-things on Concourse; use GitHub *only* to cut release installers when `main` is
> tagged with a new release.** Local development continues unabated (the operator is on Windows, which
> is why the Windows installer + local Windows build is the daily path).

So the recommendation is explicitly **NOT** "mirror goldfinch's 3-OS GitHub matrix" — that burns the
very minutes being conserved. The minutes constraint actually **strengthens** the Briefcase case:
cleaner Linux packaging (AppImage/deb) can run on the **self-hosted Concourse Linux workers for
free**, reserving scarce GitHub-hosted runners for only the platforms that genuinely require them
(macOS DMG; optionally Windows MSI if not built locally) and only on a release tag.

### The honest ceiling (don't oversell the migration)
The **frozen-runtime spawn seam** (`platform/env.py` — `clean_subprocess_env`, `resolve_python`,
bundle-dir/`PATH` stripping, `the-one doctor`) is **Python-inherent**: a frozen Python app that must
spawn real `python`/`node`/`uv` children needs it regardless of whether PyInstaller or Briefcase
produces the bundle. Briefcase consolidates the **tool-chain and the cross-platform gap**; it does
**not** eliminate Python's packaging tax. The spike must verify the seam survives Briefcase's bundle
layout (Briefcase uses a different app-dir structure than PyInstaller one-dir — `resolve_python` and
the `sys._MEIPASS`/exe-dir assumptions need re-checking).

### Scope notes for when this becomes a mission
- **Spike first, decide go/no-go.** Stand up a Briefcase build of the existing app on **one** non-
  Windows platform (Linux AppImage is the cheapest to validate on Concourse) and confirm the three
  load-bearing pieces survive: **pywebview** (WebKitGTK on Linux), **native deps** (pywinpty on
  Windows later), and the **frozen-runtime spawn seam** (`the-one doctor` must still PASS inside the
  Briefcase bundle). A negative on the seam is a likely no-go.
- **Kill the manual `apt` step.** The Linux installer should **bundle WebKitGTK** (or declare the
  `.deb` dependency) so a user never runs `apt install gir1.2-webkit2-4.1` by hand — that manual step
  is the most visible "unfinished" tell today.
- **Respect the CI topology.** Linux installer build → **Concourse** (free, self-hosted). The
  GitHub release job stays **tag-triggered only**, used for what Concourse can't host (macOS DMG;
  Windows MSI if not built locally). Do **not** add per-push GitHub matrix builds.
- **Preserve the Windows path.** The operator is on Windows and builds the installer locally today;
  whatever replaces/keeps the PyInstaller+Inno chain must not regress that daily local build. If
  Briefcase's MSI is adopted, retire the `.iss`; if not, keep Inno and only adopt Briefcase for
  mac/Linux (a hybrid is an acceptable outcome of the spike).
- **Fold in the cosmetic cleanup** while touching packaging: the *GleepGlorp AI* / *the-one*
  display-name-vs-slug split, and consolidate the brand-icon regeneration
  (`packaging/windows/regenerate_icon.py`) if Briefcase wants its own icon inputs.
- **Sequencing:** independent of the privileged-client security seed above; either can go first.

---

## Ollama runtime context window (`num_ctx`): make it configurable in the UI

**Status:** idea / future mission seed — **NOT** scoped to any current mission. A runtime fix
already shipped (see "What already shipped" below); this seed is the **UI/UX surface** that the
fix deliberately left out.
**Captured:** 2026-06-25, while diagnosing a chat that "died" at ~4k tokens on an Ollama model.

### The thesis
Ollama allocates a model runner with a fixed **runtime context window** (`num_ctx`) that defaults
to **4096 tokens regardless of the model's advertised architectural window**, and its
OpenAI-compatible `/v1` endpoint **silently ignores** `options.num_ctx`. So a model that advertises
a 262144-token window (e.g. `ministral-3:8b` reports `mistral3.context_length: 262144`) is actually
run at 4096 unless the runner is loaded via the **native `/api/*`** endpoint with an explicit
`num_ctx`. When a conversation's history crosses ~4096 tokens the prompt fills the window, there is
no room left to generate, and the model emits a token or two and stops — the chat appears to "die"
while the UI gauge still reads ~2% (because the gauge was showing the *advertised* 262144, not the
*runtime* 4096). This is a pure mismatch between the window we advertise and the window we run.

### What already shipped (the runtime fix — this seed builds on it)
A targeted fix made the runtime window real and honest, **hardcoded to a sane default**:
- `ollama_api.load_model(..., num_ctx=...)` loads the runner via native `/api/generate` with
  `options.num_ctx`; a later `/v1` chat reuses that runner.
- `ollama_provider.effective_num_ctx(advertised)` = `min(THE_ONE_OLLAMA_NUM_CTX default 32768,
  advertised)`, returning `None` when the window is unknown (leave Ollama's default untouched).
- `OllamaProvider.max_context_tokens` now resolves to the **effective runtime window**, so the
  context gauge and the M16-F08 tool-result **governor** size against reality instead of the
  fictional advertised max.
- The web auto-load (`_ensure_ollama_model_loaded`) loads/reloads the runner at the effective
  `num_ctx` and reloads if it's running at the wrong window.

The only knob today is the **`THE_ONE_OLLAMA_NUM_CTX` environment variable** (global, default
32768). That is invisible to the operator and not per-model or per-agent — which is the gap.

### What this mission adds (the UI surface)
1. **Provider/model-level configuration.** Let the operator set the runtime `num_ctx` for an Ollama
   model from the UI (Administration / provider or model editor), clamped to the model's advertised
   window (surfaced via the existing `get_model_context_length` chip) and to a hardware-aware ceiling.
   The chosen value should drive both the runner load and `max_context_tokens`.
2. **Per-agent override.** Some agents need a big window (long tool-result-heavy flows like the Sonos
   agent); others are fine small. Let an agent override the provider/model default — the natural home
   is `AgentConfig` alongside `max_iterations` / `chat_history_retention_days`. The agent override
   wins; the model default is the fallback; the env var becomes the last-resort global default.
3. **Honest feedback.** Surface the *effective* runtime window (not just the advertised one) in the
   model chip and the chat context gauge so "2% of 262144" can never again mask "100% of 4096".

### Scope notes for when this becomes a mission
- **The plumbing already exists** — `effective_num_ctx` is the single resolution point, `num_ctx`
  threads through `load_model`, AND generation now carries it natively (see "Update" below). The
  mission is mostly **config schema + UI + the resolution precedence** (agent override → model
  setting → env default → leave-Ollama-default), not new transport.
- **VRAM is the real ceiling.** A per-agent 131072 window can fail to load on a small GPU. The UI
  must clamp to advertised AND fail gracefully (the load is already best-effort / fail-open), and
  ideally warn rather than silently fall back.
- **Independent** of the privileged-client and packaging seeds above; can go in any order.

### Update (2026-06-26) — runtime enforcement now lives in the provider
The original runtime fix only set `num_ctx` on the **web auto-load** and left generation on the
OpenAI-compatible `/v1` endpoint — which **ignores** `num_ctx` and reloaded the runner back to 4096
every turn (reload churn + death at the same ~4096 ceiling, now reading "12%" against the 32768
gauge). Fixed properly: real-Ollama providers (`type: "ollama"`, `native_api=True`) now generate via
the **native `/api/chat`** endpoint, which honours `options.num_ctx`. This covers **every entry
point** (web, connectors, CLI) since it lives in `OllamaProvider.stream()`/`complete()` — so the
connector/CLI-parity concern is resolved. `openai-compatible` back-ends (LM Studio, vLLM, llama.cpp)
stay on `/v1`. What remains for this mission is purely the **UI configurability + per-agent override**
described above.
