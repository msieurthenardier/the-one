# agents.md

Development-facing reference for the-one. This file **codifies decisions, contracts, and invariants** that aren't visible from reading the code. For module layout, exports, and dependency direction, read the code — `ls the_one/`, `grep`, and the package-level READMEs (`the_one/mcp/README.md`, `tests/CONVENTIONS.md`) are the truth.

For usage, commands, and conventions, see `CLAUDE.md`. For the security threat model, see `SECURITY-MODEL.md`.

---

## Architecture Overview

Four layers, bottom-up:

```
Interfaces (cli.py, web/app.py)         — user-facing shells
Agent (core.py, factory.py, ...)        — loop, config, persistence
Tools / LLM / MCP                       — peer subsystems
Config (config.py)                      — pydantic-settings singleton
```

Rules: `config.py` is the leaf (imported by everything, imports nothing). `llm/`, `tools/`, and `mcp/` are peers — none imports the others. `agent/` imports from all three. `interfaces/` only imports `agent/factory.py`. No circular imports.

---

## Desktop launcher (`the-one app` / `the_one/interfaces/app.py`)

M15 F4 added `the-one app`, a windowed launch path implemented in `the_one/interfaces/app.py`. Key architecture points:

**Thread model**: `uvicorn.Server` runs on a **daemon thread**; `pywebview` (via `webview.start()`) runs on the **main thread**. The main thread blocks until the window closes, then `_graceful_shutdown` drives the server to completion.

**`_graceful_shutdown(server, thread, timeout=60.0)`**: sets `server.should_exit = True`, then `thread.join(timeout)` to wait for the lifespan drain. **No-op when `server is None`** — callers pass `(None, None)` when this `the-one app` process is a window-only client (it opened a window onto an already-running server; it owns no local server to drain). Distinct from the `finally:` block being present: the `finally` always calls `_graceful_shutdown`; when `server is None` the function returns immediately.

**`_select_port(host, port, retries=3, delay=0.3) → (port, is_our_instance)`**: uses a **connect-probe** (not a bind-probe with `SO_REUSEADDR`, which gives a false "free" on a `TIME_WAIT` socket). Three cases:

| Case | Condition | Return |
|------|-----------|--------|
| (a) Free | Port not occupied | `(port, False)` — start a new server on the configured port |
| (b) Ours | Occupied, `/api/info` responds 200 with matching `__version__` | `(port, True)` — attach a window to the existing server; do NOT start a second server |
| (c) Foreign | Occupied, but not a matching the-one (or a different the-one version) | `(bind-0 free port, False)` — start a new server on an OS-assigned free port; coexistence with the foreign process |

The startup-retry loop (3 attempts, 0.3s delay) covers a the-one that just bound but hasn't completed lifespan startup yet — without it, a racing `the-one app` could misclassify a starting instance as "foreign" and bind a second port.

**`_webview_available() → bool`**: **typelib-only probe** — does NOT import `Gtk` or `WebKit2`, which would initialize GLib, touch a display connection, and hang on headless machines. On `win32`/`darwin`, returns `True` unconditionally (WebView2 / WKWebView assumed present). On Linux: calls `gi.require_version("WebKit2", ver)` for versions `4.1`, `4.0`, `6.0` — catches `ImportError` (no `gi`) and `ValueError` (typelib absent). Returns `True` on the first version that succeeds.

**`[gui]` extra and lazy import**: `pywebview` is an **optional** dependency declared in `pyproject.toml` as `[gui]`. It is imported **lazily** inside `run()` — `import webview` — NOT at module top-level. This keeps the Linux CI install GTK-free (the default `pip install -e ".[all-llms,dev]"` does not pull in `pywebview`, and therefore does not touch WebKitGTK or GLib). The module-level `import the_one.interfaces.app` is safe in any environment. Installing the extra: `pip install 'the-one[gui]'` (or `-e ".[all-llms,dev,gui]"` for dev).

**M15 F6 desktop-shell additions** (`the_one/interfaces/desktop/`):

- **Close-to-tray / background run**: closing the window (pressing ×) hides it to the system tray rather than exiting the process. The app keeps running in the background; the tray icon stays visible. A first-run balloon notification explains this behaviour (marker file in the data dir suppresses it on subsequent launches).

- **Quit from tray menu is the real exit**: the tray menu has two items: "Show" (brings the window back to focus) and "Quit". **Quit is the only way to fully exit the process** — closing the window does NOT terminate the app.

- **Single-instance focus** (`/api/window/focus`): a second `the-one app` invocation that detects a running our-version instance (case (b) above) does NOT open a new window. Instead it POSTs to `http://{host}:{port}/api/window/focus` on the running server, which calls `focus_window()` → `window.show()` + `window.restore()` to bring the existing window to front, then exits immediately. One server, one window.

- **Window-state persistence** (`window-state.json`): the window's size and position are saved to `{data_dir}/window-state.json` on close (via the `_on_closing` hook) and restored on the next launch via `load_state()` + `clamp_to_bounds()`. `clamp_to_bounds` computes the union of all screens and clamps the saved geometry into visible bounds — negative-origin monitors (common on Windows multi-monitor setups) are handled correctly.

**M15 F7 desktop-shell additions** (`the_one/interfaces/desktop/shell.py`):

- **`DesktopSession` class**: all per-launch window/tray/quit lifecycle state lives in `DesktopSession`. `run()` is the entry point; it starts the server thread, creates the splash, passes `_boot` to `webview.start()`, and drives `_graceful_shutdown` in a `finally`. `run_desktop()` (the CLI entry) instantiates `DesktopSession().run()`.

- **Launch splash**: a small frameless branded window (`frameless=True`, 400×300) is created **before** `webview.start()` and is visible during the uvicorn boot wait. It embeds the brand logo (`gleepglorp_med.png`) as a base64 data URI (falls back to text-only HTML if the asset is unreadable). The splash is destroyed when the main window's `loaded` event fires (idempotent `threading.Event` guard against a double-fire race).

- **Native OS frame** (DD3 divert → DD2-alt): the main window uses `_create_kwargs = {"frameless": False, "resizable": True}` — a standard OS-framed window with native title bar, native min/max/close controls, and native resize. The native X hides the window to the tray via the F6 `_on_closing` handler (`frameless=False` + close-to-tray fully compatible). A frameless custom-chrome approach was attempted (Leg 2) and reverted (Leg 8) — see the footgun note below.

- **Brand `.ico`**: `packaging/windows/regenerate_icon.py` generates `packaging/windows/installer-assets/the-one.ico` (256/128/64/48/32/16 px multi-size) from the 512 px brand master (`icon-512.png`). The `.ico` is embedded in the windowed exe via `EXE(icon=...)` in `the-one.spec` (`exe_gui` only — not the CLI exe), giving the window and taskbar/Alt-Tab the brand icon. Regenerate the `.ico` by running `python packaging/windows/regenerate_icon.py` on any host with Pillow installed.

**pywebview frameless custom-chrome footgun (Windows WebView2 / edgechromium)**

Do **not** attempt frameless custom chrome via pywebview on Windows — it does not work reliably on the `edgechromium` (WebView2) backend:

- `easy_drag` / `.pywebview-drag-region` activate drag only on `platform == 'chromium'` (the Linux/macOS CEF backend). On `edgechromium`, the drag region is silently ignored — the frameless window is not draggable.
- CSS `-webkit-app-region: drag` is Electron-only and has no effect in pywebview's WebView2 host.
- `js_api` button callbacks (min / max / close via `window.pywebview.api.*`) require `pywebviewready` to have fired AND the `js_api` object to be exposed on the correct window. `pywebviewready` can fire before a second window's page listener attaches — a race difficult to close in the two-window (splash + main) model.

The mac/Linux desktop port should use the **native OS frame** (`frameless=False`, DD2-alt) for the same reasons.

**Browser CI**: the `browser` lane (`ci/tasks/browser.yml`) runs the full browser suite on **every push to `main`** via Concourse — no path-filter (the path-filter that rationed the GH Actions browser job to UI-only changes no longer applies; Concourse ephemeral workers make the rationing unnecessary). The GitHub Actions `test.yml` browser job is now `workflow_dispatch`-only break-glass. See `ci/README.md` for the CI topology.

**Maintenance rule**: the Concourse `browser` lane runs all tests under `tests/browser/`. No path-filter configuration to update when adding new UI surfaces or browser test directories. The launcher itself (`the_one/interfaces/app.py`) is covered by the `test` lane (not the `browser` lane), because it has no Playwright-driven tests.

---

## Project Conventions

Named project-wide patterns. Apply across the codebase, not only where they were first introduced. Reviewers flag deviations by name.

### Project-wide

### `trust-the-runtime`

Don't validate at the API layer what the runtime will catch with a clear error. Pre-validation duplicates the check, introduces TOCTOU windows, and bloats the surface translating good-enough runtime errors into hand-written API errors.

Applies whenever the runtime emits a clear, actionable error that can be matched + translated. Does NOT apply when the runtime's error is opaque (a generic `OSError` with no discriminator) — pre-check + named exception is the right call then.

### `canonical-import + convenience-re-export`

Each symbol has ONE canonical import path; lower packages MAY re-export for convenience. Code that touches the symbol's identity (subclassing, isinstance, exception handlers) MUST use the canonical path. Re-export, never re-define.

Example: `SandboxError` is canonical at `the_one.platform.sandbox.errors`; `the_one.platform.sandbox.__init__` re-exports for convenience but the canonical import is `from the_one.platform.sandbox.errors import SandboxError`.

### `structural-Protocol-satisfaction`

Classes structurally satisfy `runtime_checkable` Protocols WITHOUT inheriting from them. `runtime_checkable` already gives `isinstance` semantics; inheritance couples implementers to the Protocol's identity and forces no-op defaults across all implementers when the Protocol grows. Multiple unrelated classes can satisfy the same Protocol with zero retrofit.

### `verbatim-message-equality`

Error messages are tested via verbatim string equality (or substring `in str(exc)` when the message interpolates values), NOT regex. Verbatim equality pins the operator-facing wording, surfaces rephrasings as deliberate test updates, and avoids regex-overkill on string literals. Applies only to operator-facing error strings, not log messages or internal debug text.

### `gated-debug-instrumentation`

Debug-only / measurement-only modules are gated by **both** a URL query-string flag and a `localStorage` key, capture the enabled state at module-load time, and short-circuit to no-ops when disabled. Production pays zero cost; the gate survives SPA navigation. Two activation channels by design: URL is ad-hoc (no operator commitment); localStorage is sticky (survives reloads).

Reference: `App.perf` in `static/js/perf.js` — `?perf=1` or `localStorage.getItem('the-one-perf') === '1'`.

### `host-side-bench-drift-detection`

Targets that detect drift between the host bench and the canonical test environment (the repo `.venv`), surface a clean diagnostic on failure, and are invoked manually (not on every dev iteration). The `make test` / `make lint` chains run host-native against `.venv` and cannot, on their own, see venv drift introduced out-of-band.

Pattern: live under `# ── Drift detection (host-side) ──` in the `Makefile`; use `.venv/bin/python3 -c "..."` (NOT bare `python -c`, which has a PATH foot-gun); exit 0 if clean, non-zero with a clear `ModuleNotFoundError` / `AssertionError` if drift detected. Spec MUST include both a positive probe (clean → exit 0) AND a negative probe (deliberate violation → non-zero) — "clean tree exits 0" alone doesn't prove detection. For `git grep` recursive `**` pathspecs, use the `:(glob)` prefix; git's default mode treats `**` literally.

Reference: `make doctor`, `make audit`, `make audit-bytes`.

### `hat-driven-contract-flip-migration-discipline`

When a HAT iteration flips a previously-shipped contract (semantic, schema, or behavioral default), apply a three-part migration discipline: (i) preserve the original behavior as a backward-compatible read-side coercion path so existing data round-trips through the new shape without operator intervention; (ii) document the flip plus the rationale in the flight log Deviations section so reviewers can audit the contract change post-hoc; (iii) close out the read-side coercion in a follow-up flight with explicit deprecation language (the coercion is migration scaffolding, not a permanent compatibility shim). Distinct from `verbatim-message-equality` — that convention pins operator-facing error strings byte-for-byte; this one governs operational contract changes mid-mission.

Citation: M10 F6 HAT3 — the per-axis tri-state semantic flipped under operator review (legacy `match: str` form coerced in-place to the multi-value `match: list[str]` form on next save; deviation logged; coercion explicitly tagged for follow-up cleanup).

### `live-read-across-lazy-resolver-boundary`

When a provider field is **lazily resolved** on first call (sentinel → real value after a one-time upstream probe), every downstream consumer must read the field **live at the point of use**, not pre-capture it at the entry of a surrounding function. Eager capture sees the pre-resolution sentinel; the resolver fires later inside the provider call, but the captured local is never re-read.

Example: `LLMProvider.max_context_tokens` (Ollama queries `/api/show` once per model and caches on the instance). The contract is pinned by `test_usage_event_reflects_live_max_context_tokens_at_emission`.

Generalises to any field where the upstream value is unknown until a per-model / per-session probe completes. Lazily-resolved fields are owned by the provider and must be read through the provider, never copied across a function boundary.

### `host-test-entrypoints-reach-via-make`

Tests run host-native against the repo `.venv` (the canonical test environment), driven by `scripts/run-tests.sh`. The `make test-*` targets chain required preconditions; a raw `.venv/bin/python -m pytest -m <marker>` invocation bypasses them.

Concrete foot-gun: if `~/.cache/ms-playwright/` is missing, a raw `.venv/bin/python -m pytest -m browser` produces hundreds of "Executable doesn't exist" errors. `make test-browser` chains `_ensure-playwright` (conditional re-install, no-op when present). A raw pytest invocation is a debugging tool — fine for one isolated failure, wrong as the default invocation.

Before adding a NEW mitigation to a recurring foot-gun, audit whether the existing `make` chain already mitigates and the bug is in invocation form, not infrastructure form.

### `landmark-elements-over-aria-roles`

For shell-level navigation surfaces, prefer native HTML5 landmark elements (`<nav>`, `<main>`, `<aside>`, `<header>`, `<footer>`) over `<div role="...">`. Native semantics survive ARIA spec churn and tooling improvements; ARIA roles on generic containers carry the same semantic load but require explicit role-assignment plus dev-mode regression guards.

Canonical shape for active-item nav: `<nav aria-label="..."><ul><li><button [aria-current="page"]>item</button></li>…</ul></nav>`. Active-item toggle uses `setAttribute('aria-current', 'page')` on the new active + `removeAttribute('aria-current')` on the prior — NOT `setAttribute('aria-current', 'false')` (ambiguous to AT). `role="listbox"` is INVALID when descendants are interactive (`<button>` inside `role="option"`); use `<nav>` + `<ul>` + `<button>` with `aria-current` instead.

**Selector-continuity tax**: when a leg restructures DOM (changing the container element, ARIA roles, or class hierarchy), distinguish **class-name preservation** (lexical — the class still exists) from **selector-continuity preservation** (structural — descendant/sibling selectors still resolve). Class names can survive a `<div>` → `<nav>` change while `.parent .child` descendant selectors silently break. Pre-edit, enumerate test selectors touching the restructured surface and mark each as SURVIVES or UPDATES.

### `function-local-import-to-break-load-cycle`

When two modules transitively import each other (e.g. `mcp/_tool.py` ↔ `platform/sandbox/errors.py` via `the_one.mcp.__init__`'s eager import of `_tool`), top-level imports can fail with `ImportError` if the cycle is initiated from one entry but not another. The fix is **function-local imports at the call site**: defer the cycle-crossing import to runtime so module load completes cleanly, regardless of which module the importer reaches first. Apply this pattern when (and only when) the cycle is real and load-order-dependent — at the top-level when no cycle exists, prefer the top-level form. Every function-local import that exists to break a cycle MUST carry an inline comment naming the cycle so future readers can verify the motivation.

Citations:
- `db/repositories.py: MCPSourceRepository.find_by_runtime_package` — `from the_one.mcp.cache_cleanup import extract_runtime_package` inside the function body, with the inline comment "Local import to avoid a circular: cache_cleanup is in the_one.mcp, which transitively imports db modules through other helpers."
- `the_one/mcp/_tool.py: MCPClientTool.execute` — `from the_one.platform.sandbox.errors import SandboxError` inside the function body, with the inline comment "`the_one.mcp.__init__` eagerly imports this module (`_tool`), so a top-level `SandboxError` import re-opens the `mcp/__init__` eager-load cycle. Keep it function-local." The parallel site `the_one/mcp/_tool_provider.py` (Path A fallback branch) carries the identical comment for the same cycle.

Pattern is at the 2-occurrence threshold pending a clearer 3rd documented occurrence. The function-local imports in `mcp/_pool.py` are not load-cycle-breaks (no inline comment documenting the motivation; `mcp/_pool.py` already imports `the_one.db.repositories` at the top level cleanly) and are deliberately excluded from this citation list — naming the pattern matters more than padding the count.

### `optional-plugin-hook-via-getattr-sentinel`

An optional plugin extension that not every plugin needs to provide is accessed via `getattr(plugin, "<hook_name>", None)` with a sensible fallback at the call site. The Protocol stays at its minimal shape; future plugin authors aren't forced to write no-op stubs. The consumer's exception-catching behavior tolerates plugin-raised exceptions and falls back. Distinct from `protocol-widening-for-required-capability` (see below) which applies when ALL plugins in scope must implement the method. The fallback may be `None` (consult site short-circuits — `display_channel`'s shape) OR a named callable that returns the default outcome (when the default outcome is structured — F6's `_default_permit` returns a `Permit()` instance).

Citation: `Agent._governor`-feeding helper in `the_one/agent/core.py` reads `getattr(self.llm, "max_context_tokens", None)` and `getattr(self.llm, "bytes_per_token", 4.0)` — not every `LLMProvider` (or minimal test double) sets these, and the getattr-with-default lets an implementer that doesn't crash tool dispatch instead of raising; the helper itself floors a missing/absurd `max_context_tokens`. (An earlier, richer n=4 citation set lived in the now-removed connector subsystem — a plugin's optional `display_channel` / `resolve` / `is_dm` / `is_mention` hooks, each consulted via `getattr(plugin, "<hook>", <default>)`; re-attach citations here if a comparable multi-hook case recurs.)

### `protocol-widening-for-required-capability`

When a capability moves from "future" (one plugin needs it, others don't) to "required" (every plugin in scope must implement it), widen the `runtime_checkable` Protocol additively rather than reaching for `getattr`-sentinel. The widening is non-breaking for existing `isinstance(...)` checks at the type level — Python's `runtime_checkable` Protocol checks method-name presence at call time, so existing implementers that satisfy the pre-widened shape continue to pass UNLESS they're missing the newly-required method (in which case the isinstance check correctly fails and surfaces the gap). Implementations still MUST NOT inherit from the Protocol — structural satisfaction is the rule (`structural-Protocol-satisfaction` convention).

Citation: `the_one/tools/provider.py:ToolProvider.get_tools` widening (F5 L6) added `tool_configs` / `agent_overrides` / `agent_name` parameters to the existing `ToolProvider` Protocol's single method. Every provider in scope (builtin, per-MCP-source) must accept the widened signature; the docstring notes explicitly that `runtime_checkable` Protocol checks validate method NAMES only, so the widening is non-breaking for existing `isinstance(provider, ToolProvider)` checks. (An earlier citation — a `ConnectorClient.send` widening onto the outbound-send Protocol — lived in the now-removed connector subsystem's base module; outbound had no sensible default there, which is the same "widening is structurally right" reasoning as this citation.)

### `cross-subsystem-pattern-premise-revalidation`

Every "mirror X" rationale invoked in a design must include an explicit paragraph: "the original design rests on premise P; does P hold here?" Pattern-transfer without premise validation ships defects that survive design review. Reviewers must demand the premise-revalidation paragraph before approving any cross-subsystem mirror.

Applies to any cross-subsystem pattern reuse where the precedent's premise is implicit. Does NOT apply to local refactors within a subsystem — a single-subsystem change can mirror its own siblings without re-deriving the premise.

M11 F7 L4: the F6 DD §2 provider audit pinned "no leak" — peer_name (and forthcoming channel_name) cannot reach LLM payloads because all three adapters explicitly project ``{role, content}``. F7 L4 deliberately refines that premise: peer_name and channel_name DO reach the LLM, but ONLY via an inline-prefix mutation at ``_to_api_message``'s user-role return path; never as separate API-payload keys. The audit-into-design-decision shape from F6 produced the structural guarantee that the new projection now relies on (a single, explicit, code-cited mutation site per adapter); the convention's "premise P holds" check is satisfied by L4's premise-revalidation paragraph in the L4 leg artifact.

Source: M10 mission-debrief "Process §2" — codify `cross-subsystem-pattern-premise-revalidation`; also listed in "Action Items → Codify 6 new agents.md Project Conventions."

### `provider-shape-portability`

**Convention**: The canonical `Message` and `ToolResult` dataclasses in `the_one/llm/base.py` ARE the portable shape across LLM providers. Provider-specific encoding lives entirely in each `LLMProvider._to_api_message`; provider-specific decoding lives entirely in the response parser. No provider-specific shape leaks back into the dataclass before persistence.

**Mechanism**:
- `ToolResult.__post_init__` JSON-stringifies non-str content at construction — so every consumer (4 providers, codec, telemetry, CLI) reads `str` uniformly. Removes the need for per-encoder coercion (the F7 12.l hotfix that this convention replaces).
- `Message.__post_init__` asserts content is `str`, OR a `list[ContentBlock]` **only on `Role.USER`** messages (M16 F12 L01/DD2-DD3) — non-str/non-list arrival, or a block-list on a non-USER role, is a provider-parser defect surfaced as `AssertionError` (via explicit `raise`, not a bare `assert`, so the role guard survives `python -O`), not silently coerced. The asymmetry vs `ToolResult` is deliberate: structured tool returns are legitimate (channel-context tools return `list[dict]`); non-str/non-block-list on a `Message` is not. `ContentBlock` (`TextContent | ImageContent`, `the_one/llm/base.py`) is the canonical provider-neutral union — mirrors the `ThinkingBlock` precedent — that each provider's `_to_api_message` maps to its native multimodal wire shape; images/documents are USER-turn inputs only, so SYSTEM/ASSISTANT/TOOL content stays `str`.

**Source**: M11 F8 L2 (dataclass-shape-invariants). Pinned by `tests/test_llm_provider_cross_provider_history.py` (canonical session round-trip across all 4 providers) and `tests/test_llm_provider_tool_result_serialization.py` (construction-time normalization + per-provider pass-through encoders).

**When this matters**:
- Adding a new provider — `_to_api_message` is the ONLY site where shape translation happens; consume `str` content uniformly. No per-encoder coercion is needed; the dataclass invariant already guarantees the shape.
- Adding a new tool — the agent loop wraps tool returns as `ToolResult(content=output)`; `__post_init__` normalizes structured returns automatically. Tool authors return native shapes; the canonical-wire-shape conversion is at the dataclass boundary.
- Refactoring the codec — both encode and decode paths produce/consume str content via the dataclass invariants. Legacy rows whose stored content is non-str (rare; pre-L2 round-trip corner) surface as `AssertionError` at decode-time — an intentional signal of underlying corruption.

**Operator runbook for legacy-row AssertionError**: when a session-replay or codec-decode path surfaces `AssertionError` in `Message.__post_init__` with non-str content, the offending row is a pre-L2 storage artifact. Triage:

1. Identify the chat_sessions row via the traceback's session_id (the dispatcher logs it in the surrounding context). Run `sqlite3 var/the_one.db "SELECT id, agent_name, length(messages) FROM chat_sessions WHERE id = '<id>'"` to confirm the row exists.
2. Decide: delete the row (loses the chat history) OR repair the row (recover the history by manually editing the messages JSON to coerce non-str content to str). For single-user local-tool use, delete is usually fine — the operator can recreate the conversation.
3. If multiple rows trigger the AssertionError, batch via `UPDATE chat_sessions SET messages = '[]' WHERE ...` (loses history) or write a one-off migration script that walks the JSON and stringifies non-str content keys.
4. After cleanup, restart the app — the storage layer is now consistent and the AssertionError stops firing.

This is intentionally manual: the rare and structurally-illegal nature of the AssertionError means we DO NOT add a fallback at the dataclass layer (would silently mask future provider-parser defects).

**Anti-pattern**: post-construction direct field assignment (e.g., `tr.content = some_list`). Bypasses `__post_init__` and reintroduces the shape-loss this convention prevents. The annotation is `str | dict | list[Any]` to permit structured constructor callers; `__post_init__` enforces the str invariant once the dataclass exists. Tests that need a non-str field must construct fresh via `ToolResult(content=non_str)` (which normalizes), or use `dataclasses.replace`. Never reach in via attribute assignment. The F7 12.l Anthropic encoder-level coercion site (now deleted at `the_one/llm/anthropic_provider.py`) was the symptom this convention closes by moving the invariant up to the dataclass boundary.

Source: M11 F8 L2 — replaces the surgical F7 12.l hotfix with a structural shape invariant at the canonical-dataclass boundary; cited by the `cross-subsystem-pattern-premise-revalidation` convention's F7 audit-history paragraph above.

### `single-source-of-truth-for-paired-helpers`

**Convention**: When two helpers form a tightly-coupled pair — one EMITS a pattern and the other RECOGNIZES it (or one CONSTRUCTS state and the other PARSES it back, or one ENCODES and the other DECODES) — both helpers must read from the same constant(s) or generator function. Never hardcode the same literal in both places.

**Mechanism**: extract the shape into module-level constants (e.g., `_MASK_PREFIX = "***"`, `_MASK_TAIL_LEN = 4`). The emitter builds output from the constants. The recognizer (regex / parser / matcher) is also built from the same constants — for regexes, use `re.escape(CONST)` so the pattern adapts when the constant changes.

**Source**: M11 F8 L3 (mask-shape-single-source). Pinned by `tests/test_api_secret_mask_roundtrip.py::TestMaskShapeSingleSourceOfTruth` — tests assert `regex.match(emitter(x))` for representative inputs, so if a maintainer drifts one without the other, the tests fail.

**When this matters**:
- Mask emitters + regex recognizers (the M11 F8 L3 motivating case).
- Encoders + decoders that share a wire format (the canonical Message dataclass invariant from `provider-shape-portability` is a structural variant of this).
- Tokenizers + parsers, prefix-stripping helpers, sentinel emitters + matchers, any helper pair where one PRODUCES what the other RECOGNIZES.

**Anti-pattern**: two functions that build/recognize the same literal pattern with copy-pasted hardcoded strings or regexes. If you find yourself writing the same `"***"` (or `\*\*\*` regex escape) in two adjacent functions, extract the constant.

**Pair with**: `mechanical-fallback-prompt-truth-pairing` (the analogous discipline for prompt-vs-code pairings) and `provider-shape-portability` (the same single-source-of-truth principle applied to dataclass shapes across LLM providers).

### `prompt-discipline-needs-mechanical-fallback`

Any agent behavior the system depends on but the LLM controls requires either empirical HAT validation against the production model OR a mechanical dispatcher-side fallback that enforces the behavior without relying on prompt compliance. Decision-only (prompt-only) paths are not production contracts — LLM directive compliance is not a contract the system can build on.

Applies to any system-level invariant whose enforcement passes through the LLM (outbound channels, tool-call-mandatory flows, content-filter directives). Does NOT apply to UX-only directives that fail soft if ignored (style guidance, persona instructions).

Citation: the worked example — a connector-dispatcher directive telling the model "MUST call the `send_to_platform_channel` tool," which Sonnet 4.7 ignored at HAT, closed by a mechanical auto-relay fallback that delivered the reply regardless of tool-call compliance — lived in `the_one/agent/config.py`'s connector directives and the now-removed connector subsystem's inbound dispatcher, both removed in the Mission 23 connector reset. The nearest live analog is the degraded-model tool-call backstop under "Continue Signal" below (`_run_iterations`' redundant-call backstop is a mechanical fallback for a different LLM-controlled behavior — not relying on prompt compliance to stop redundant tool calls); re-attach a directive-specific citation if a future prompt/dispatcher pairing recurs.

Source: M10 mission-debrief "Process §3" — codify `prompt-discipline-needs-mechanical-fallback`; also "Lessons Learned §11" (LLM directive compliance is not a production contract).

### `mechanical-fallback-prompt-truth-pairing`

When a mechanical fallback ships alongside a system-prompt directive (per `prompt-discipline-needs-mechanical-fallback`), the prompt must accurately describe the actual behavior the dispatcher delivers. Lying in the prompt about what auto-runs (e.g., still saying "MUST call tool X" when the dispatcher now auto-relays anyway) confuses LLMs trained for honesty and produces hedging / over-explanation. The directive and the dispatcher's truth ship in the same diff.

Applies whenever a mechanical fallback exists for a behavior the system-prompt also describes. Does NOT apply when the dispatcher honors the original prompt's contract verbatim (no fallback divergence).

Citation: the worked example — a paired connector directive ("Auto-relay is ON: your plaintext replies in this session ARE automatically delivered to platform peers") that told the model the truth about the auto-relay fallback from `prompt-discipline-needs-mechanical-fallback` above — lived in `the_one/agent/config.py`'s connector directives, removed in the Mission 23 connector reset along with the fallback it paired with. Distinct from `hat-driven-contract-flip-migration-discipline` — that convention governs schema/contract flips at HAT; this one governs prompt/dispatcher pair synchronization. Re-attach a citation if a future mechanical fallback ships alongside a system-prompt directive.

Source: M10 mission-debrief "Documentation §1" — companion to `prompt-discipline-needs-mechanical-fallback`; also "Lessons Learned §4" (Auto-relay default-on with a mechanical fallback is the right shape for bot UX).

### `lifespan-wiring-same-leg-as-installation`

Event-handler installation (registering a handler that depends on application-level state) and the lifespan-time call site that triggers it land in the same leg, OR the leg's acceptance criteria include a runtime end-to-end test exercising the installed handler. Installing a handler without wiring the lifespan that fires it leaves the entire code path unreachable in production — silently, until somebody triggers the handler end-to-end.

Applies to any event-driven handler (gateway listeners, periodic sweeps, background workers, lifespan-startup callbacks) that depends on application-level dependency injection. Does NOT apply to handlers wired into a synchronous import path that runs at module-load. The pattern is connector-agnostic and applies project-wide to any lifespan-driven handler.

Citation: the worked example — a connector gateway listener installed in F8 L4 (`DiscordPlugin.connect`'s `on_message` handler) whose lifespan-time pool-acquire wiring was deferred to L11, leaving the inbound code path end-to-end unreachable in production for seven flights — lived in the connector subsystem, removed in the Mission 23 connector reset. The module-level `set_factory` / `get_factory` accessor pair it relied on (`the_one/agent/factory.py`, consumed by `the_one/interfaces/web/app.py`'s lifespan startup) has a real caller again as of the Mission 23 connector reset (Flight 2): `the_one/connectors/inbound.py::dispatch_inbound` calls `get_factory()` at dispatch time, wired end-to-end alongside the manager's lifespan `start_all`/`drain` hooks in the same leg (`01-contract-core`) — this time honoring `lifespan-wiring-same-leg-as-installation` rather than repeating the F8/L11 split. Re-attach a further citation if a future event-driven handler (Discord, Flight 3) adopts the same accessor.

Source: M10 mission-debrief "Process §6" — add `lifespan-wiring-same-leg-as-installation` to `/leg` and `/flight` design guidance; also "Methodology Feedback §4."

### `atomic-leg-pattern`

When a single contract change touches multiple coordinated sites (Pydantic field + DB migration + repository CRUD + downstream ripple-sites that load or persist the value), all sites land in the same leg. Splitting the contract across legs leaves intermediate commits where one half of the contract exists without the other — the column exists in the schema but the Pydantic model doesn't know to write to it, or the model has the field but the repository drops it on save.

Applies whenever a contract change crosses two or more of {Pydantic schema, DB schema, repository codec, runtime consumer that reads the value}. Does NOT apply to contract-additive changes that are fully optional at every site (e.g., adding a Pydantic field with a default that no existing consumer reads).

Citations (n=2 — pattern is at codification threshold per `function-local-import-to-break-load-cycle` precedent):
- M21 F02 L02: `AgentConfig.self_revision_requires_approval` field landed alongside schema v35 migration (`agents.self_revision_requires_approval INTEGER NOT NULL DEFAULT 0`), `SQLiteAgentStore.set_self_revision_requires_approval` repository method, and the `surface.py:_apply_revision` branch consumer in a single leg.
- Historical: two connector-subsystem citations (`AgentConfig.connector_ids` / v17; `AgentConfig`'s since-removed per-connector allowlist field / v18) demonstrated this pattern before the pre-reset connector subsystem was deleted in Mission 23 Flight 1; re-attach if a comparable case recurs.

Source: M10 mission-debrief "Documentation §1 (Architect addition)" — `atomic-leg-pattern` (Pydantic field + migration + repository + ripple-sites in one leg; F4 L5 + F6 L1c are n=2); also "Methodology Feedback §8."

### `optional-registry-entry-hook`

When a registry entry needs to participate in substrate machinery — dirty tracking, namespace exposure, lifecycle hooks, render-time integrations — add OPTIONAL function fields to the entry's contract, validated as "must be a function IF present" but absent without error. Required entry fields are the render-time contract (the substrate calls them to produce the entry's per-type UI); optional fields are substrate-integration opt-ins (the substrate calls them when its machinery has work to dispatch to the entry, but absence means "this entry doesn't participate at that integration site"). The validator extends linearly: a new optional hook adds one name to an `optionalFns` list, no structural validator change.

Applies when a registry/dispatch primitive owns substrate-touching machinery (event listeners, snapshot serialization, lifecycle callbacks) where some per-type entries opt in and others don't. Does NOT apply to dispatch tables where every entry must implement every method (use Protocol-widening then; see `protocol-widening-for-required-capability`).

Citations: this pattern's n=5 worked example (a per-type registry's `_validateEntry` with an `optionalFns` array of entry-shape hooks — `snapshot`, `wireEvents`, `renderInviteSection`, `renderDirectiveSection`, `renderDiscoverableDropdown`, `renderRuntimeConfigFields`) lived in the connector Studio editor's type registry, removed in the Mission 23 connector reset along with the rest of the connector frontend. The registry-shaped surfaces that remain (`the_one/interfaces/web/static/js/areas/studio/mcp-server-editor.js`, `the_one/interfaces/web/static/js/areas/admin/provider-editor.js`) are per-type editors without a shared dispatch registry of their own today; re-attach citations here if a future per-type registry adopts the optional-hook shape.

Source: M11 F1 flight-debrief "Key Learnings §3" (the F1 added three optional hooks; the additive-extension shape is generalizable) + "Recommendations §2" (operator-confirmed codification at debrief).

### `registry-dispatch-create-mode-AC`

Any registry-mediated typed-render path requires BOTH "create-mode-after-dispatch-key" AND "edit-mode-with-dispatch-key-set" as explicit acceptance criteria. The dispatch key (the value the registry uses to pick a per-type entry — connector type, provider type, plugin type) may be absent at first render in create mode and only populated when the operator picks it; the AC must verify that the post-pick render produces the typed entry's content, not the substrate's fallback. Edit-mode tests alone are insufficient — they exercise the dispatch-key-set path and miss the dispatch-key-absent-then-set transition that operators actually hit.

Applies when a registry/dispatch primitive renders different content based on a dispatch key that may be absent on first render (operator-picked type in a create form; post-fetch resolved key in an async-populated editor). Does NOT apply when the dispatch key is structurally guaranteed at mount (e.g., the key is part of the URL route fragment and a renderer is mounted at all only when the key is present).

Citation (n=1 from M11 F1 L7, codified by methodology-promotion per F1 debrief Recommendations §2 — operator-confirmed): the worked example — a Studio connector editor's create-mode dispatch-key zeroing bug, HAT-caught at F1 L7 — lived entirely in the connector editor (`connector-editor.js`), removed in the Mission 23 connector reset along with its resolution test. The general lesson stands: any registry-dispatch render path needs both create-after-pick and edit-with-key-set as explicit ACs; re-attach a citation when a future registry-dispatch surface demonstrates it.

This is the first codification under the n=1-by-methodology-promotion shape — the F1 debrief elevated this convention on the strength of the methodology lesson (registry-mediated dispatch is a structural pattern that demands symmetric ACs), not on a recurring-pattern threshold. Future occurrences citing this convention re-validate the structural claim; if they don't, the convention is a candidate for retirement at a later mission debrief.

Source: M11 F1 flight-debrief "Recommendations §2" + "Key Learnings §5" (HAT essential signal even at the end of autonomous flights) + F1 L7 leg-progress entry.

### `primitive-rename-test-classification`

When a leg spec touches a primitive's name (rename, split, consolidation), every test file that contains the primitive's name is default-classified as `code-update` — i.e., the leg must read the test to determine whether the rename ripples into functional code. Downgrade to `docstring-sweep` (the rename only changes prose in test docstrings) ONLY after `grep` verifies the name appears solely inside `"""..."""` docstring blocks across the entire file. The cycle-0 default of "docstring-sweep until proven otherwise" inverts the safe direction — it treats a name appearance as docstring noise until refuted, when the truth-table is the opposite (a name appearance is functional usage until refuted).

Applies whenever a leg's scope includes renaming, splitting, or consolidating a named primitive (function, class, dataclass, constant, or method) that is referenced by tests. Does NOT apply to leg-internal symbol renames whose names never appear in test files (grep returns zero hits in `tests/`).

Citations (n=1 trigger, n=3 evidence files from M11 F2 L2 cycle-1 — two of the three, `tests/test_connectors_inbound.py` and `tests/test_connectors_e2e_platform_send.py`, were connector-subsystem tests removed in the Mission 23 connector reset; `tests/test_lifespan.py` survives and still pins the rule via its getattr/setattr sites + assertion):
- `tests/test_lifespan.py` — getattr/setattr sites + assertion (functional, multi-site).

Source: M11 F2 flight-debrief "Recommendations §Important — codify two methodology rules as agents.md project conventions" (convention 1) + "What Could Be Improved §Important — primitive-rename test classification rule."

### `flight-spec-dom-order-audit`

At flight-design time, when a flight or leg artifact's natural-language wording describes adjacency between rendered DOM sections (e.g., "between section X and section Y" in Design Decisions, leg objectives, or implementation guidance), the architect must re-walk the current DOM order in the live source before committing the wording. Memory of a prior DOM walk is unreliable across flight boundaries — sections may have been added, removed, or reordered between the original audit and the current flight-design session.

Applies whenever a flight or leg artifact's natural-language wording describes adjacency between rendered DOM sections (Studio editor sections, Chat UI panels, settings sub-pages). Does NOT apply to logical ordering claims that are not DOM-rendered (file ordering in a directory, leg execution ordering within a flight, mission flight ordering).

Citation (n=1 from M11 F2 L4 cycle-1, codified by methodology-promotion per the same F1-L7-derived precedent as `registry-dispatch-create-mode-AC`): F2 flight.md Design Decisions §3 originally claimed the directive section landed "between Pairing and Test Connection," but a fresh DOM walk at cycle-1 showed Attached Agents between Pairing and Test Connection in the current source, so the correct placement was "between Pairing and Attached Agents." The reviewer caught the divergence; the leg spec was reworded to match the actual DOM; no structural harm done at L4 itself, but the symptom indicates the flight spec was written without a fresh DOM-order audit.

Source: M11 F2 flight-debrief "Recommendations §Important — codify two methodology rules as agents.md project conventions" (convention 2) + "What Could Be Improved §Minor — flight-spec wording drift from DOM order."

### `pool-warming-entrypoints-are-finite-and-named`

Any subsystem with a pool primitive must explicitly enumerate the entrypoints that warm the pool; design-time reasoning may not assume that any operator-triggered action implicitly populates the pool unless the action's handler explicitly calls one of the named entrypoints. `grep` for the entrypoint name in the candidate handler is the mechanical fallback that converts assumed-warming into verified-warming.

Applies whenever a flight or leg artifact's design assumes a pool entry is warm at a given UX-trigger point. Does NOT apply to read-only pool inspection paths or to lifespan-driven warmup (which is structurally-guaranteed at startup, not operator-triggered).

Citation (n=1 from M11 F3 L4 design-time + L7 HAT anomaly #1, codified by methodology-promotion per the same F1-L7-derived precedent as `registry-dispatch-create-mode-AC`): F3 L4's design assumed Test Connection populated the pool via the lifespan-listener-warmup path (a named entrypoint in the now-removed connector subsystem's pool module); the assumption was structurally false — Test Connection's handler (in the now-removed connector routes) called `plugin.doctor()` but never `account_acquire`; HAT step caught the gap at F3 L7 (dropdowns 404 immediately after Test Connection succeeded); the F4 L2 leg is closing the underlying code-side mismatch by wiring `account_acquire` after `doctor()` succeeds. The convention codifies the methodology fallback that prevents recurrence: enumerate-and-grep at design time.

Source: M11 F3 flight-debrief "Recommendations §Critical §3" + "Key Learnings §2" + "What Could Be Improved §Process — recon should default-walk L1 codifications."

### `frozen-snapshot-for-cross-lock-read`

When handler code reads multi-field cache state outside the lock that protects mutation, build a frozen-snapshot dataclass inside the lock and return the snapshot for outside-the-lock consumption. The pattern prevents inconsistent-multi-field-read races without requiring all readers to hold the lock for the entire read window.

Applies whenever a cache or shared mutable state exposes multiple correlated fields that callers may read outside the mutation lock. Does NOT apply to single-field atomic reads or to fully-immutable shared state.

Citation (n=1 from M11 F3 L4 cycle-1, codified by methodology-promotion per the same F1-L7-derived precedent as `registry-dispatch-create-mode-AC`): F3 L4 architect cycle-1 caught that the cache exposes a `(client_id, entities, last_refresh)` triple that handler code reads outside the lock; cycle-1 introduced `_DiscoverableCacheSnapshot` as the frozen-triple dataclass returned from a lock-held read.

Source: M11 F3 flight-debrief "Recommendations §Methodology §12" + "Deviations and Lessons Learned" table (L4 `_DiscoverableCacheSnapshot` row).

### `slot-getter-bridge-for-dropdown-collect-path`

When a new editor shape (e.g., a dropdown chip-list) must integrate with an existing DOM-walking collect path that expects a specific child-element shape (e.g., text nodes), install a function-valued property (a slot getter) on the slot's container element that the collect path can invoke to retrieve the editor's current values. The getter bridges the new editor shape to the existing collect path without rewriting either side.

Applies whenever a new UI editor surface must integrate with a pre-existing DOM-walking collect/serialize path that doesn't natively understand the new editor's DOM shape. Does NOT apply when the collect path can be cleanly rewritten in lockstep with the new editor.

Citations (n=3 from M11 F3 L6a + L6b):
- `_allowlistValues` (L6a allowlist) — installed as a function-valued property on the allowlist slot container so `collectAllowlistFromContainer`'s text-node walk can extract dropdown selections.
- `_routingMatchValues` (L6b routing match-value) — installed as a function-valued property on the routing match-value slot container so the existing routing collect path can extract dropdown selections.
- `_overlayChipValues` (L6b per-agent overlay) — installed as a function-valued property on the per-agent overlay slot container so the existing overlay collect path can extract dropdown selections.

Source: M11 F3 flight-debrief "Recommendations §Methodology §13" + "Deviations and Lessons Learned" table (L6a/L6b row).

### `two-concurrent-callers-reasoning`

At design-review time, when a leg touches code that may be invoked by two or more concurrent callers (handler + background task; refresh-loop + read-loop; lifespan-warmup + operator-triggered acquire), the architect must walk the two-concurrent-callers thought experiment for every shared mutable state the leg touches. Sketch-based reasoning about a single caller is not naturally extended to two concurrent callers; the discipline is to explicitly enumerate the second caller, the interleaving point, and the partial-success / partial-failure shape.

Applies whenever a leg touches code that may be invoked by two or more concurrent callers and the leg modifies or reads shared mutable state (in-process caches, locks, pool entries, refresh loops). Does NOT apply to leg-internal pure functions or to single-caller-by-design paths (e.g., startup-only initialization that the runtime guarantees against re-entry).

Citation (n=3 from M11 F3 L4 cycle-1 within a single leg, codified by methodology-promotion per the same F1-L7-derived precedent as `registry-dispatch-create-mode-AC`): F3 L4 cycle-1 caught three concurrent-caller race-safety issues — (1) `prior_cache` race between refresh-loop and operator-triggered read; (2) `_shutting_down` bail interleaving with re-acquire; (3) identity-check on `client` to detect mid-refresh reconnection. All three would have been cycle-0-discoverable had the architect explicitly walked the two-concurrent-callers thought experiment.

Source: M11 F3 flight-debrief "Recommendations §Methodology §16" + "Key Learnings §4 — cycle-1 race-reasoning has limits."

### `cross-flight-ux-debt-reconciliation`

Every flight's reconnaissance phase MUST include a section walking the prior 2-3 flight debriefs' AND the parent mission-debrief's deferred-UX items, classifying each as "in-scope-for-this-flight" / "out-of-scope-with-reason" / "structurally-blocked-by-X." The discipline arrests the "fold into F8/F10/follow-on-mission" structural source of UX-debt accumulation by forcing each new flight to explicitly cross-check the deferred queue rather than passively inheriting it.

Applies to every flight reconnaissance phase. Does NOT apply to the first flight of a mission (no prior debriefs to cross-check) — though that flight should still cross-check the mission-debrief of any predecessor mission whose work it inherits.

Citation (n=1 from M11 F3 debrief root-cause analysis, codified by methodology-promotion): F3 debrief surfaced an n=1 trigger of the 4-step UX-debt-accumulation pattern (HAT discovers → deferred → subsequent flight touches surface → deferral not folded). The primary codification destination is mission-control's `/flight` skill prompt (out of project scope); this agents.md entry is the project-side binding fallback that holds even if the mission-control skill prompts are out of date. The F4 `flight-log.md`'s Reconnaissance Report (Recon table R1-R11) is the n=1 application of this discipline.

Source: M11 F3 flight-debrief "Recommendations §Critical §1" + "UX-Debt Accumulation §Root cause of the accumulation pattern."

### `touched-surface-ux-debt-folding`

When a flight touches a code surface (file or component), the architect MUST enumerate all open UX-debt items against that surface from prior debriefs and either fold them in or explicitly state why they're left. The discipline prevents the "touched the file but missed the gap" failure mode (F3 L6b touched `connectors-tab.js` but missed A2's raw-id checkbox-mode rendering because the leg's contributing-criteria framing was narrow).

Applies whenever a leg's Files Affected list includes a source file with open UX-debt items in prior debriefs. Does NOT apply to files with no prior-debrief UX-debt entries.

Citation (n=1 from M11 F3 L6b miss, codified by methodology-promotion): F3 L6b touched `connectors-tab.js:_renderAccountTile` for per-agent overlay dispatch but did not fold A2 (checkbox-mode raw-id rendering) into scope; A2 surfaced at F3 L7 HAT and is now closed by F4 L3. The primary codification destination is mission-control's `/flight` skill prompt (out of project scope); this agents.md entry is the project-side binding fallback.

Source: M11 F3 flight-debrief "Recommendations §Critical §2" + "What Could Be Improved §Process — touched-surface UX-debt folding."

### `message-additive-back-compat-via-emit-when-non-none`

When adding an optional field to the `Message` dataclass (or to a nested dataclass it owns), the codec MUST emit the field key only when the value is non-None on encode, AND MUST read `d.get("<field>")` defaulting to None on decode. The pattern preserves byte-identical JSON for legacy rows that predate the field — encoded shape is unchanged when the field is at its default, decoded `Message` instances on pre-addition rows pick up `None`. No DB migration, no backfill script, no storage churn.

Applies to every additive change to a persisted dataclass shape whose history must remain decodable. Does NOT apply to required-field additions (those need a migration) or to non-persisted state (in-memory only).

**Implementation shape** (n=3+):
```python
def message_to_dict(msg: Message) -> dict[str, Any]:
    d: dict[str, Any] = {"role": msg.role.value, "content": msg.content}
    # ... existing emit-when-non-None blocks ...
    if msg.<new_field> is not None:
        d["<new_field>"] = msg.<new_field>
    return d

def message_from_dict(d: dict[str, Any]) -> Message:
    return Message(
        # ... existing required + optional reads ...
        <new_field>=d.get("<new_field>"),  # None on legacy rows
    )
```

Use `is not None` for the emit guard, NOT truthy (`if msg.<new_field>:`). Empty strings, zero counts, and other falsy-but-meaningful values must round-trip; the absence sentinel is `None` and only `None`.

Citations (n=6 — pattern is well past codification threshold):
- `tool_result.metadata` (M08 F7 L05 / F5 L3) — `the_one/db/codec.py:45` (`if tr.metadata is not None`).
- `Message.visibility` (M10 F3 L2) — `the_one/db/codec.py:66, 117` (encode + decode).
- `Message.peer_name` (M11 F6 L1) — `the_one/db/codec.py:72, 119` (encode + decode).
- `Message.channel_id` (M11 F7 L2) — `the_one/db/codec.py:78, 121` (encode + decode).
- `Message.channel_name` (M11 F7 L2) — `the_one/db/codec.py:84, 123` (encode + decode).
- `Message.created_at` (fix: message-timestamp-on-replay) — `the_one/db/codec.py` `message_to_dict`/`message_from_dict` (encode + decode). Unlike the other four citations, the dataclass default (`None`) is NOT what `Message.user`/`Message.assistant` construct with — those two factories default `created_at` to a non-None ISO timestamp (`_utcnow_iso()`) so live and replayed turns can render a "· HH:MM UTC" attribution. The emit-when-non-None guard still applies at the codec boundary; only a bare `Message(...)` (or `Message.system`/`Message.tool`) leaves it at `None`.

Cross-cutting compose test (`tests/test_db_codec.py::TestMessagePeerNameCodec::test_round_trip_with_peer_name_and_visibility`) confirms multiple emit-when-non-None fields compose without interference — each is independently emitted/decoded against its own None default.

Source: M11 F6 flight-debrief "Recommendations §Critical §3" + "Key Learnings §6" + "What Could Be Improved §Technical."

### `message-thinking-field` (M16 F10)

`Message.thinking: list[ThinkingBlock]` carries provider reasoning/thinking as a first-class,
structured field (each block is `{type: "thinking", thinking, signature}` or `{type:
"redacted_thinking", data}`). It is a **structural sibling of `tool_calls`** (a list with
`field(default_factory=list)`), NOT part of the `message-additive-back-compat-via-emit-when-non-none`
convention above: the codec emits it with a **truthy guard** (`if msg.thinking:` at
`the_one/db/codec.py`), so an empty list is not emitted and the byte-identity tripwire
(`test_db_codec.py::test_encode_emits_no_keys_when_all_optional_fields_default`) stays green without
a citation bump. Blocks are stored in the exact Anthropic content-block shape so replay
(`AnthropicProvider._to_api_message`) hands them back verbatim — **signatures must round-trip
unmodified** or the follow-up turn 400s.

Anthropic specifics (M16 F10): enablement is **adaptive-only** — `thinking: {"type": "adaptive",
"display": "summarized"}` (Sonnet 4.6+; the `budget_tokens` wire format 400s on current models).
`display` defaults to `"omitted"` on Sonnet 5 / Opus 4.8/4.7 / Fable 5 (signed-but-empty thinking
text), so `"summarized"` is requested explicitly to surface readable reasoning for the web-UI
disclosure; the `signature` is identical across display modes, so replay is unaffected. Replay is
**gated on the outgoing request's thinking state** (`_to_api_message(..., thinking_active)`):
replay-when-on, strip-when-off (DD8). The field is provider-agnostic — Ollama/OpenAI may populate
it in a later flight with no protocol change.

### `provider-request-param-config-surface` (M16 F11)

Per-request LLM params that not every provider needs, and that don't warrant a change to the
`LLMProvider` ABC's constructor/method signatures, are configured through the free-form
`LLMProviderConfig.config` dict rather than new formal parameters. A4 (M16 F11) added three:
`reasoning_effort`, `response_format`, `stop`. Keeping the ABC signature unchanged avoids a
hand-rolled-test-double cascade — every provider subclass and test double would otherwise need
updating for a signature change three separate providers don't all need. Canonical resolvers live
in `the_one/llm/_request_params.py`: `resolve_reasoning_effort`, `resolve_response_format`,
`resolve_stop`, backed by `_coerce_effort`, `_coerce_response_format`, `_coerce_stop`.

**Precedence** (mirrors the pre-existing `resolve_extended_thinking` (`anthropic_provider.py`) and
`effective_num_ctx` (`ollama_provider.py`) lineage): per-provider `config` key → env
(`THE_ONE_REASONING_EFFORT` / `THE_ONE_RESPONSE_FORMAT` / `THE_ONE_STOP`) → default `None`. Each
provider's `__init__` coerces the raw `config` value via the matching `_coerce_*` helper at
construction time; the resolver itself coerces *only* the env read, at call time. The split keeps
`_coerce_*` independently unit-testable and matches the established precedent exactly.

**Canonical→native mapping is per-provider (DD3)**: the shared module normalizes shape only; each
provider's own request-kwargs assembly maps the canonical value to its native wire shape.
Anthropic (`the_one/llm/anthropic_provider.py:_build_kwargs`) maps to `output_config.effort` /
`output_config.format` (json_schema-only — canonical `json_object` no-ops with a logged warning,
since Anthropic's structured-output surface has no bare-JSON mode) plus top-level
`stop_sequences`. OpenAI, OpenRouter, and Ollama's `/v1` path share the OpenAI-compat shape
(`the_one/llm/openai_provider.py:_a4_request_kwargs`, `the_one/llm/ollama_provider.py:_v1_a4_kwargs`)
— `reasoning_effort`, `stop`, and `response_format` with a `json_schema` wrapper that synthesizes a
required `name`. Ollama's native `/api/chat` path (`the_one/llm/ollama_provider.py:_native_body` /
`:_native_options`) uses body-level `think` / `format` plus `options.stop` instead of the
OpenAI-compat keys. **Subclass caveat**: `OpenRouterProvider` inherits `OpenAIProvider`'s
request-building methods but reads its own config in its own `__init__` via the shared
`the_one/llm/openai_provider.py:_read_a4_config` helper (`OpenRouterProvider.__init__`
deliberately does not call `OpenAIProvider.__init__` — see that file's docstring) — a future A4
key must be threaded through `_read_a4_config` for OpenRouter to pick it up, not assumed to arrive
via `super().__init__()`.

**UI surface**: only `reasoning_effort` gets a provider-config editor field — Admin's
`the_one/interfaces/web/static/js/areas/admin/provider-editor.js` renders a `<select>` bound to
`data-field="config.reasoning_effort"`. `response_format` and `stop` are config/env-only (no UI
field; the file documents this inline as "config/env-only response_format + stop, DD6"). The save
path seeds `payload.config` from the existing provider's config object before overlaying
type-specific fields, so out-of-band keys (`response_format`, `stop`, or anything set via API/DB
rather than through the UI) survive a UI-triggered save instead of being wiped by the backend's
field-level-replace update (`existing.model_copy(update=data)`). This save-path pattern is named
and generalized as its own convention — see `seed-before-overlay for partial-field UI saves` under
`### Mission-specific (M16)` below.

Citations: `the_one/llm/_request_params.py` (resolvers + coercers); `the_one/llm/anthropic_provider.py:_build_kwargs`
(and its `resolve_extended_thinking` precedent in the same file); `the_one/llm/openai_provider.py:_a4_request_kwargs`
/ `:_read_a4_config`; `the_one/llm/openrouter_provider.py:OpenRouterProvider.__init__` (subclass caveat);
`the_one/llm/ollama_provider.py:_v1_a4_kwargs` / `:_native_body` / `:_native_options` (and its `effective_num_ctx`
precedent in the same file); `the_one/interfaces/web/static/js/areas/admin/provider-editor.js` (UI field +
save-path config seeding).

### `risk-tiered-test-seam-gating`

Test-only HTTP seams are gated by mutation risk, not gated uniformly. **Inert-metadata seams** — seed or read in-process state without touching live data or driving the agent loop — gate on `settings.dev_mode` alone. **Live-state-mutating or agent-loop-injecting seams** — real DB writes, real LLM calls, real tool execution — gate on `settings.dev_mode` AND a seam-specific env var (`THE_ONE_<NAME>_TEST_ENDPOINT=1`), so a stray `THE_ONE_DEV_MODE=true` left on in a shared dev environment doesn't also arm every high-risk seam.

Classify a new test-only seam against this tier before choosing its gate — don't default to single-gate for convenience, and don't default to dual-gate when the seam is genuinely inert.

Precedents:
- Single-gate (inert-metadata): `POST /_test/oauth/pending` (`the_one/interfaces/web/api.py`) — registers a pending OAuth flow in `the_one.mcp.oauth._state`; no DB write, no agent loop.
- Dual-gate (state-mutating): `POST /_test/purge-sweep` (`the_one/interfaces/web/api.py`) — fires a real daily-purge DB sweep; `THE_ONE_PURGE_SWEEP_TEST_ENDPOINT=1`.
- Dual-gate (agent-loop-injecting): `POST /_test/stub/inbound` / `GET /_test/stub/outbound` (`the_one/interfaces/web/api.py`, Mission 23 Flight 2, DD-10) — injects free text into a live agent loop with real LLM calls and tool execution; `THE_ONE_STUB_TEST_ENDPOINT=1`. The same dual gate also decides "stub" connector-type creatability (`_creatable_connector_types`) and the lifespan startup hook that registers `StubPlugin`.
- Dual-gate (live-state-mutating): `POST /_test/discord/sever` (`the_one/interfaces/web/api.py`, Mission 23 Flight 3 Leg 3, DD-7) — abruptly kills a real Discord connector's gateway websocket via the optional `sever_for_test` hook; `THE_ONE_DISCORD_TEST_ENDPOINT=1`, its OWN gate name — deliberately not reusing `THE_ONE_STUB_TEST_ENDPOINT`, since arming the stub gate must not also arm a seam that mutates a real platform connection.

Source: Mission 23 Flight 2 debrief, What Could Be Improved / Documentation — the risk-tiering rationale was re-argued from scratch a second flight running before this entry existed.

### `composition-disjoint-post-step-mutators`

When two post-step mutators must both walk the same `messages[pre_step_len:]` slice after `agent.step` returns, design them to touch disjoint subsets of that slice (by `Role`, or another partition) so they compose in either call order without one function growing multiple jobs. Provable non-overlap by construction beats a single mutator that "does everything" for a turn — each concern stays independently testable and reviewable.

Citation: `the_one/connectors/inbound.py::_bind_peer_name` touches only the `Role.USER` message at `messages[pre_step_len]`; `the_one/llm/base.py::tag_post_step_visibility` touches every role EXCEPT `Role.USER`. `dispatch_inbound` calls them back-to-back (`_bind_peer_name(...)` then `tag_post_step_visibility(...)`); the disjoint `Role` partition means the two calls cannot conflict regardless of order.

Applies to any pair of independent post-step concerns over the same message slice. Does NOT apply when the concerns genuinely need to see each other's output — a single ordered pass is the right shape there.

### `probe-must-not-pass-by-download`

A diagnostic probe that loads a bundled asset through a loader capable of falling back to a network fetch (Hugging Face `snapshot_download`, or any similar "local path, else fetch" resolver) must assert the packaged path resolves and exists via `importlib.resources` **before** calling that loader, and must force the process into offline mode in-process before the call — both the environment variable AND any already-bound module constant that reads it once at import time. A probe that can satisfy itself by downloading is not proving the bundle ships the asset; it is proving the test machine has network access.

Applies to any diagnostic or test that loads a package-data asset through a resolver with a network fallback. Does NOT apply to loaders with no fallback path (a bare `open()`/`Path.read_bytes()` either finds the file or raises — there is nothing to guard).

Example: `the_one/embeddings/local.py:resolve_model_dir` (called by `LocalStaticBackend.load()`, which `the_one/diagnostics.py:_probe_embedding_model` constructs fresh — Flight 2 Leg 3 moved the guards out of `diagnostics.py` so production loads carry them too) resolves `importlib.resources.files("the_one.embeddings")/"data"/"potion-retrieval-32M"` and checks `.is_dir()` before ever importing `model2vec`; `force_hf_offline` then sets `os.environ["HF_HUB_OFFLINE"]` AND (if `huggingface_hub.constants` is already in `sys.modules`) its bound `HF_HUB_OFFLINE` constant, since that constant is read once at import and a bare env-var set after import is too late. Precedent this rests on: `_probe_model_catalog`'s docstring records the sibling fail-open — a tree-shaken seed file resolving to an empty, silently-degraded catalog rather than a hard failure.

Source: M24 F01 DD-5; pinned by `tests/test_doctor_embedding_model.py::TestOfflineInvariant`.

### `report-what-you-got`

A probe (or the test that exercises it) asserts on the CONCRETE resolved value inside the emitted detail string — a dtype read off the returned array, a byte size read off the file on disk, a resolved path, a `numkong=yes|no` flag — never on a bare `ok` / "no exception was raised". A capability that silently degrades (an extension that loads but answers nothing, a quantization step that silently no-ops, a dynamic-dispatch fallback masking a missing native library) passes a no-exception check and fails a value check; only the latter is a real regression gate.

Applies to any diagnostic probe or its test. Does NOT apply to advisory-only lines with no pass/fail semantics (e.g. `detect_runtimes`' "not found — here's how to install" lines, which are intentionally always `ok=True`).

Rationale: the M24 Flight 1 debrief names five same-shaped fail-opens found in one flight — the HF download fallback, the numkong dynamic-dispatch fallback, an immutable-`sqlite3.Connection` monkeypatch that a naive test would silently no-op against, a cosine-only correctness check, and a tree-shaken-but-still-imports model directory. Every `_probe_*` in `the_one/diagnostics.py` asserts a concrete value: `_probe_sqlite_vec` checks the KNN query returns the exact stored rowid, not just that `vec0` loaded; `_probe_usearch` checks the search returns the exact stored key; `_probe_embedding_model` checks the vector is 512-wide with a non-zero norm and reports the dtype read off the array itself (never hardcoded as "float16" — a silently-skipped quantization would otherwise mislabel itself).

Source: M24 F01 flight-debrief "Key Learnings"; pinned throughout `tests/test_doctor.py` and `tests/test_doctor_embedding_model.py` (each probe test asserts substrings of `result.detail`, not `result.ok` alone).

### `autouse-fixture + dedicated-real-load-file`

When an UNCONDITIONAL gate (one that must fail the run on every host, not just when frozen) loads something expensive — a multi-hundred-MB-of-import-weight model, a slow native build — give it a function-scoped `autouse` fixture in the shared test file that stubs the probe, and put exactly ONE real, unstubbed load in its own dedicated test file. pytest has no opt-out from an `autouse` fixture (the usual marker-based workaround needs `request.node` to be the test function; at module scope it is the Module object instead), and a module-scoped fixture cannot request the function-scoped `monkeypatch` fixture (`ScopeMismatch`) — so there is no way to write "stub everywhere in this file except test X" from inside the same file.

Applies whenever a gate that must be unconditional (never downgraded to a frozen-only skip) also happens to be expensive to actually exercise. Does NOT apply to frozen-only gates — those already downgrade cheaply via `_vector_probe_outcome` (see the Diagnostics section below) and don't need blanket stubbing to stay fast on a dev host.

Example: `tests/test_doctor.py`'s module-level `_stub_embedding_probe` fixture (`autouse=True`, function-scoped) patches `diagnostics._probe_embedding_model` for all 18 `run_doctor(` call sites in that file, so `make test-unit` never pays for the 62 MiB `potion-retrieval-32M` load. `tests/test_doctor_embedding_model.py::TestRealLoad.test_probe_loads_the_committed_weights` is the one real, unstubbed load — the only host-side proof the bundled asset actually loads — and per `report-what-you-got` above it asserts on the detail string's dimension, dtype, norm, weights byte count, and peak RSS, not merely `ok is True`.

Suite-wide variant (Flight 2 Leg 3): once `create_knowledge_base` started firing `embeddings.warm_up()` as a background task on every call, the expensive load became reachable from ANY test that creates a knowledge base, not just the doctor probe's callers — too broad a surface for a single file's autouse fixture. `tests/conftest.py::_stub_embedding_backend_by_default` (also `autouse=True`, function-scoped) patches `LocalStaticBackend.load` itself for every test module EXCEPT the two that need real control (`tests.test_doctor_embedding_model`, checked by `request.module.__name__`, and `tests.test_embeddings`, which stubs `LocalStaticBackend.load` itself to test the process singleton). The exclusion-by-module-name technique generalizes the file-split idea to "opt two files out of a suite-wide autouse fixture" where a per-file split would otherwise require touching every consuming test file individually.

Source: M24 F01 DD-7; the split is enforced structurally (there is no other place a real-load test could live once the autouse fixture exists) rather than by convention alone.

### `db-writes-hold-the-write-lock`

Every code path that calls `commit()`/`rollback()` on the shared SQLite connection outside `ensure_schema` does so through `the_one/db/_write_lock.py`'s `write_transaction(conn)` async context manager — not only multi-statement writers, but every single-statement self-committing repository method too.

Why: the Architect modelled a narrower design (lock scoped to multi-statement writers only, single-statement committers left bare) and it destroyed a concurrent writer's rows — `aiosqlite` serialises statements on the one shared connection, not transactions, so *any* coroutine's `commit()` commits whatever is currently open on that connection, including another coroutine's partial multi-statement write. A single-statement method's unprotected `commit()` is exactly such a hazard; it is not made safe by being "only one statement." With every committer holding the lock, the model survives (proven by the concurrent-interleave test below).

`ensure_schema`'s migrations in `the_one/db/schema.py` are the one exemption: they run at `init_db()` before any request or background task exists, so there is no concurrent committer on the connection to race — see the corrected comment at that module's v8 migration block for the full argument.

Not re-entrant, and re-entry is detected rather than allowed to deadlock: a second `write_transaction` entered by the same `asyncio` task before the first exits raises `RuntimeError` immediately (checked before acquiring the lock, never after — acquiring first would deadlock the task against itself). Compose a multi-step write as sequential transactions, never as one `write_transaction` nested inside another — this is also why a component that itself acquires the lock (e.g. a vector store, Leg 2+) must be called OUTSIDE any caller's own `write_transaction` block, never wrapped inside it.

Enforcement: `tests/test_db_write_lock.py::test_commit_and_rollback_confined_to_write_lock_and_schema` scans every `.py` file under `the_one/` and asserts `.commit()`/`.rollback()` appear only in `the_one/db/_write_lock.py` and `the_one/db/schema.py` — the guard that keeps the rule true as the codebase grows (the rule decays silently otherwise). The same test file's other cases pin the behavioural contract: single-task failing-write rollback, the realistic concurrent-interleave case (a failing writer vs. a plain single-statement writer, both going through the guard), same-task re-entry detection without deadlock, and two contending tasks both landing.

Source: Flight 2 ("Storage and Embedding Foundation") Leg 1, DD-13. Leg 2 adds the FTS-specific sync rules (chunk insert/delete alongside the FTS `INSERT`/`'delete'` commands, in the same transaction) to this convention.

### Mission-specific (M16)

Patterns that emerged in Mission 16 (LLM provider hardening) whose project-wide generalization has not yet been demonstrated. They live here until a second-mission citation lifts them into `### Project-wide` above, per the same pattern established by `### Mission-specific (M10)` below.

### `rule-of-three OpenAI-compat duplication`

OpenAI, OpenRouter, and Ollama's `/v1` path share the OpenAI-compat wire shape, so the same small mapping logic is currently **duplicated by hand across exactly two call sites** rather than factored into a shared helper:

- Request-kwargs assembly (M16 F11): `the_one/llm/openai_provider.py:_a4_request_kwargs` and `the_one/llm/ollama_provider.py:_v1_a4_kwargs` independently build the `reasoning_effort` / `stop` / `response_format` (`json_schema`-wrapped) OpenAI-compat kwargs — see `provider-request-param-config-surface (M16 F11)` above.
- Content-block projection (M16 F12): `the_one/llm/openai_provider.py:_content_block_to_api` and `the_one/llm/ollama_provider.py:_content_block_to_api` independently map `ContentBlock` to the OpenAI-compat content-part shape (`the_one/llm/anthropic_provider.py:_content_block_to_api` is a third, Anthropic-native implementation and is NOT part of this duplication — it maps to a different wire shape).

**The rule**: two duplicated implementations of the same OpenAI-compat mapping are tolerated as-is — do NOT preemptively extract a shared helper on the second occurrence. Lift the logic into a shared module only when a **genuine third `/v1`-shaped provider** arrives (OpenRouter today inherits `OpenAIProvider`'s methods directly rather than reimplementing them, so it doesn't count as a third independent implementation). Until then, `tests/test_llm_provider_cross_provider_conformance.py` (the cross-provider tool-use round-trip conformance suite, M16 F04 L02) is the drift net: it exercises OpenAI, Ollama, and OpenRouter through the same canonical script, so the two hand-duplicated mappings diverging would surface there before shipping, without paying the abstraction cost of a shared helper for only two call sites.

Source: maintenance report 2026-07-10 finding DOC2 (Mission 18 Flight 4), generalizing the code-comment-only convention already present at both `_a4_request_kwargs` and `_v1_a4_kwargs`.

### `seed-before-overlay for partial-field UI saves`

See `provider-request-param-config-surface (M16 F11)` above for the full write-up (the save path seeds `payload.config` from the existing provider's config object before overlaying type-specific fields, so out-of-band keys set via API/DB rather than through the UI survive a UI-triggered save instead of being wiped by the backend's field-level-replace update). Named here as its own convention because the pattern generalizes beyond provider-config saves: **any UI editor that only exposes a subset of a config object's fields must seed the save payload from the existing persisted object before overlaying the fields the UI actually edited**, or a save silently drops fields the UI never rendered. Citation: `the_one/interfaces/web/static/js/areas/admin/provider-editor.js` (seeding) + `existing.model_copy(update=data)` (the field-level-replace backend update it protects against).

### Mission-specific (M11)

### `column-aware-index-create-for-rewind-paths`

When a migration block must DROP+CREATE an index whose underlying columns have evolved across prior migrations, do NOT use `executescript("CREATE TABLE ...; CREATE INDEX ...")` — the `CREATE INDEX` half references the column names as they exist in the connection's current schema, and a v7-style strip-and-rewind path may execute that block against a schema where the column has since been renamed. The safe shape is: split the block into a `CREATE TABLE` half (executescript-safe) plus a Python-guarded `CREATE INDEX` step that consults `PRAGMA table_info(<table>)` at runtime to choose the correct column name branch (old-name vs new-name).

Citation: F12 L3 introduced the pattern at `the_one/db/schema.py`'s v21 block, where v24 had dropped the old-named `idx_pending_approvals_account_peer_status` index whose v21-block CREATE referenced the post-v23-renamed column. The `test_v7_strips_removed_tool_names` rewind+rerun fixture path surfaced the failure mode (operators don't exercise the rewind path; pytest does).

Source: F12 debrief Recommendation #5; codified at F13 L1.

### `detail-endpoint-attaches-rich-payload`

When a REST endpoint serves both a list-style summary (`list_*`) and a single-resource detail fetch (`get_*`), heavy/rich fields (audit logs, message bodies, routing decisions, embedded blobs) attach ONLY at the detail-endpoint composition site — NOT inside the shared summary helper that the list endpoint also consumes. Adding a rich field to the shared helper bloats every list response with potentially hundreds of nested entries; attaching only at the detail-endpoint composition keeps the list shape cheap while making the rich field available where it's actually consumed (typically a per-resource detail view).

Precedents:
- M11 F13 L5: `_session_summary()` at `the_one/interfaces/web/api.py:3253-3260` stays untouched (5-key summary shape: `id`, `agent_name`, `title`, `created_at`, `updated_at`); `session_metadata` (a dict that can grow to hundreds of entries — audit/telemetry data such as per-turn usage snapshots) attaches only on the `get_chat_session` detail-endpoint return at `:3204`. List endpoints (`list_chat_sessions`, `create_chat_session`, `update_chat_session`) keep their existing summary-only response shape.
- M10 F05 L04: `Session.platform` field added to the in-memory dataclass + populated at restore time — only the operator-attached-session detail consumers read it; the list-of-sessions API didn't take on the field.

Anti-pattern: extending the shared summary helper to include the rich field — every list-row response carries the bloat even when no consumer needs it. F13 architect cycle-1 explicitly corrected the original leg spec from "extend `_session_summary`" to "attach only at the detail-endpoint composition."

Source: F13 L5; codified at F13 debrief.

### `provider-aware-model-dropdown-with-custom-fallback`

LLM model fields in the UI should be **provider-aware dropdowns** populated from `GET /api/providers/{providerId}/models` on provider-change, NOT free-text inputs. The dropdown's empty state is `"— No model —"` when a provider is selected, or `"Select a provider first"` (disabled) when no provider is selected. **Persisted values that aren't in the current API response** (e.g. an Ollama model the operator pulled locally but the provider isn't currently enumerating, or an OpenAI/Anthropic model the provider doesn't enumerate at all) surface as a synthesized `{value} (custom)` option that stays selected — preserving the operator's intent without silently wiping the value.

Race-guard for rapid provider-switching: an `AbortController` cancels in-flight fetches AND an `_activeProviderId` equality check on resolution drops any response that no longer matches the live selection. Without both layers, a slow earlier-provider response can clobber a fresh later-provider response. On fetch error, surface a clear `"Failed to load models"` placeholder while preserving the persisted value as a disabled `{value} (saved)` option so the operator's saved choice stays visible.

The async populate is a side effect — do NOT call `recaptureSnapshot()` from inside the populate (would re-baseline the dirty-tracker against the post-populate state and silently absorb user edits); do NOT call `checkDirty()` either (the general change listener already fires on user-driven provider changes; calling from inside the populate races against concurrent async populates on mount). Clearing the provider via GUI should dispatch a synthetic `change` event so the general change listener picks up the dirty state against the persisted baseline.

Precedent:
- Chat agent-editor: `the_one/interfaces/web/static/js/areas/studio.js:1720+` `fetchModelsForProvider` — the canonical pattern (race-guard via `_modelsFetchController` + `_activeProviderId`; `(custom)` fallback at `:1794+`). (A second precedent, the connector editor's inference Model field, lived in the connector subsystem removed in the Mission 23 connector reset.)

Source: M11 F13 L4-enhancement; codified at F13 debrief.

### `in-memory-snapshot-from-db-restore`

When an in-memory dataclass (e.g. `Session` in `the_one/interfaces/web/app.py:285+`) needs to surface a DB-stored field to consumers (WS payload builders, REST detail-endpoint composers, in-process handlers) WITHOUT re-fetching from the DB on every access, add the field to the dataclass + populate it in `_restore_session` from the loaded DB row. The cached attribute is a snapshot at restore time; the documented staleness escape hatch is a REST "Refresh" button on the consumer surface (operator triggers re-fetch on demand) OR a re-mount of the in-memory entry on lifecycle events that the DB write path emits.

NOT the right shape when:
- The field changes in real-time and the consumer needs push-not-pull semantics (use WS event broadcasts instead).
- The field is large enough that snapshotting in memory is wasteful relative to re-fetching on the rare access (re-fetch with caching is preferable).

When in doubt, the snapshot shape's defensibility comes from a clearly-documented staleness contract: source-of-truth (DB row), rebuild trigger (re-mount on session restore + manual Refresh button), maximum staleness acceptable to the operator (until next Refresh click or session re-mount), and user-action invalidation map (no DB write paths invalidate the in-memory snapshot in the MVP shape — the Refresh button is the only consumer-visible escape).

Precedents:
- M10 F05 L04: `Session.platform` field, populated in `_restore_session` from `ChatSession.platform`, read by the operator-visibility tagging path in `_process_and_broadcast`.
- M11 F13 L5: `Session.session_metadata` field, populated in `_restore_session` from `ChatSession.session_metadata`, read by both `_build_session_joined_ok` + `_build_session_joined_degraded` WS payload builders and surfaced via a Chat UI inspector panel with a Refresh button. (The specific panel this precedent cited — a routing-decision audit view — lived in the connector subsystem removed in the Mission 23 connector reset; the snapshot-from-restore mechanism itself is generic and still governs `session_metadata`'s other consumers, e.g. `last_usage`.)

Source: M10 F05 L04 + M11 F13 L5; codified at F13 debrief.

---

## Subsystem contracts

These sections record decisions and invariants. Module layout, exports, and per-file behaviour live in the code and package-level READMEs (especially `the_one/mcp/README.md`).

### Encryption-rotation invariant (seven corpora)

`POST /api/encryption/rotate` (`interfaces/web/api.py:rotate_encryption_key`) re-encrypts every credential ciphertext in **one atomic transaction**. As of Mission 22 Flight 1 Leg 1 the rotation covers seven corpora:

1. `llm_providers.api_key` (Mission 03)
2. `llm_providers.secrets` (Mission 19 Flight 1 — the anthropic-plan OAuth token set)
3. `mcp_sources.secrets` (Mission 07)
4. `connectors.secrets` (Mission 10 Flight 1; table renamed from `connector_accounts` by M11 F11 L1 v23) — the `Connector` row's own secrets column; this corpus, `ConnectorRepository`, and the `Connector` DB model persist independently of the routing/ACL/approval machinery removed in the Mission 23 connector reset.
5. `agents.tool_overrides` / `agents.mcp_overrides` (Mission 21 Flight 1 Leg 1 — see "Agent override secrets storage" below)
6. `tool_configs.secrets` (Mission 16 Flight 8 Leg 3 — built-in tool API keys, e.g. `web_search`'s keyed-engine credentials)
7. `agent_external_credentials.secret` (Mission 21 Flight 3 — the `ext_` client credential store)

A failure in any of the seven UPDATE loops calls `conn.rollback()`, discards the staged key sidecar (see below), and re-raises, so a partial rotation that handled only a subset is impossible. Migration-residue rows (plaintext `'{}'` carried over from the column default) are tolerated via `InvalidToken`-swallowing decrypt and normalized to proper ciphertext for `{}` as a side-effect across corpora 1–4 and 6; the agents columns use `_decrypt_overrides_column` instead — same tolerant-decrypt shape, but legacy plaintext there is real operator data rather than a `'{}'` default (see "Agent override secrets storage"). Corpus 7 (`agent_external_credentials.secret`) decrypts **strictly** — a decrypt failure there is real corruption, not migration residue, and aborts the rotation before any write.

**Key handoff — two-phase sidecar (flight Design Decision Q1).** The single `await conn.commit()` is the authoritative DB commit point, but the on-disk key file is no longer replaced directly after it. Instead:

1. Before the commit, the new key is staged to `<key_path>.next` via `Encryptor.stage_pending_key` (atomic write, `0o600`, via `_write_key_atomic`). If staging fails, the DB is untouched.
2. If the commit fails, the transaction rolls back and the sidecar is discarded (`Encryptor.discard_pending_key`).
3. Once the commit succeeds, `Encryptor.install_key(new_key)` runs immediately — no `await` in between — so no other coroutine can observe "DB committed under the new key, in-memory encryptor still on the old key."
4. The sidecar is then promoted to the canonical key file via `Encryptor.promote_pending_key` (`os.replace`). If promotion fails (disk full, permission, cross-device), the route returns `{"status": "ok", "key_file": "staged"}` instead of `"promoted"` — the DB and in-memory encryptor are already correct on the new key, and the sidecar stays on disk for the startup reconcile to finish the job.

**`MultiFernet` read mode.** While a pending key is staged, `Encryptor` decrypts with `MultiFernet([Fernet(canonical), Fernet(pending)])` (canonical first) so in-flight reads never fail across the staged-but-not-yet-promoted window; `encrypt()` always uses the canonical key.

**Startup reconcile.** `the_one/db/key_reconcile.py:reconcile_pending_key(conn, encryptor)` runs in both entrypoints (`app.py:lifespan`, `cli.py:_run_cli`) between `get_connection()` and the first encryptor-backed repository construction — repositories hold the encryptor by reference, and the reconcile mutates it in place, so this ordering is what makes that by-reference propagation sufficient. It samples ciphertext across all seven corpora (`sample_ciphertexts`) and either promotes the pending key (at least one sample decrypts under it, or nothing is decidable) or discards it (no sample decrypts under it but at least one decrypts under the canonical key) via `the_one.encryption.resolve_pending_key`.

**CLI-window trade-off.** A CLI process already running during a crashed rotation keeps encrypting new rows under the canonical key until it restarts — the reconcile only runs at process start. Negligible for a single-operator app; documented rather than engineered around. If the reconcile then promotes the pending key while some sampled ciphertext still decrypts only under the canonical key, `resolve_pending_key` names this loss explicitly in its WARNING log line (`the_one/encryption.py`), pointing back at this paragraph.

### `__MASKED__` sentinel (LLM providers)

The provider edit form sends the literal string `__MASKED__` for unchanged `api_key` values. `update_provider` in `interfaces/web/api.py` detects this sentinel and preserves the stored value. Anyone touching the provider edit form needs to know this contract.

The same form-side validator (`_is_safe_provider_url`) must run on the **resolved** `base_url` post-`model_copy(update=data)`, not on the request payload — `__MASKED__` would otherwise fail validation.

### MCP source secrets storage

`mcp_sources` (schema v10) uses **field-segregated encryption with two columns**: `config TEXT` holds plaintext non-sensitive fields (transport-aware: `command`/`args`/`env` for `'stdio'`, `url`/`headers` for `'streamable-http'`); `secrets TEXT` holds a single Fernet-encrypted JSON blob whose decoded value is a dict of operator-marked sensitive field values. Encryption is per-row (one `Fernet.encrypt/decrypt` per row), NOT per-field inside the JSON.

The repository stores the `Encryptor` **as a reference, not a copy**, so post-rotation `install_key()` propagates to live repository instances.

**Per-key `__MASKED__` semantics**: GET returns `{secrets: {key: "***...{tail4}", ...}}` with each VALUE masked individually. On PUT, `secrets[key] == "__MASKED__"` preserves the existing stored value for that key; other keys overwrite.

**OAuth-managed secret keys**: `dcr_credentials`, `access_token`, `refresh_token`, `token_expires_at`. Written exclusively by `MCPSourceTokenStorage`; stripped + preserved on PUT by the API layer's `_OAUTH_MANAGED_SECRET_KEYS` logic.

### Tool config secrets storage (M16 F08 L03)

Built-in **tool configs** (`tool_configs`, `secrets` column added in schema v32) use the **same field-segregated `config`+`secrets` encryption** as `mcp_sources` / `connectors` — parity with MCP and LLM-provider keys. `config TEXT` holds plaintext non-sensitive fields; `secrets TEXT` holds a single Fernet-encrypted JSON blob. `ToolConfigRepository` holds the `Encryptor` by reference (rotation propagates), delegating to the shared `_encrypt_secrets_blob`/`_decrypt_secrets_blob` (InvalidToken-tolerant — the plaintext `'{}'` default decrypts to `{}`).

The split is **generic and marker-driven**: a field is a secret iff its Pydantic `json_schema_extra` carries `secret: true` (`web_search`'s `google_pse_api_key`/`brave_api_key`/`tavily_api_key` are the first consumers; any future built-in tool Config with a `secret`-marked field gets encrypted storage + masking for free). `interfaces/web/api.py:_secret_field_names(config_cls)` reads the marker set.

- **PUT** `/tools/configs/{name}` validates the full body, then **moves** secret-marked keys out of `config` into the encrypted `secrets` store — **a plaintext key never lands in the `config` column**. `_looks_masked` values preserve the existing decrypted secret; a masked value with no stored secret is dropped (cleared), never persisted as the mask string. A real new value replaces it. (Same mask sentinel + `_looks_masked` recognition as the MCP/provider PUT handlers.)
- **GET** `/tools/configs/{name}` returns `config` with secret-marked fields masked via `_mask_secret_value` (decrypt-then-mask, never raw).
- **Resolver / backends see the REAL key**: `ToolConfig.merged_config()` (`{**config, **secrets}`) is the factory feed (`factory.py`), so `build_search_backend` receives the decrypted api_key — NOT the masked admin view. The `/test` connection endpoint uses the same `merged_config()` feed. Two distinct reads: the admin GET masks, the resolver/test path resolves real keys.

### Agent override secrets storage (M21 F01 L01)

`agents.tool_overrides` and `agents.mcp_overrides` (schema v8 / v11, both nullable `TEXT`) are **both Fernet-encrypted at rest** — parity with every other secrets-bearing column, and coverage for a future `Substitute`-marked credential on either override schema without a second migration of habit. Unlike the `config`+`secrets` split used by MCP sources / connectors / tool configs, there is no column split here: each column holds ONE Fernet-encrypted JSON blob of the whole dict (`_encrypt_overrides_column` / `_decrypt_overrides_column` in `db/repositories.py`), because only a minority of `mcp_overrides`' inner keys are secret and the outer dict is keyed dynamically by MCP source name (no fixed non-secret/secret field split like a `ToolConfig` has).

`SQLiteAgentStore` holds the `Encryptor` **by reference, not a copy** (same as `MCPSourceRepository` / `ToolConfigRepository`) — `install_key()` after rotation propagates to the live store. `SQLiteAgentStore.__init__(conn, encryptor: Encryptor | None = None)`: when omitted, the encryptor resolves via `get_encryptor(settings.data_dir)` (the `_tool_provider.py:242` pattern), so all ~37 pre-leg construction sites (`SQLiteAgentStore(conn)`) are unaffected.

**Decode is NOT `_decrypt_secrets_blob`.** That shared helper treats `InvalidToken` as "empty secrets" (`{}`) — correct for a column whose plaintext default is the string `'{}'`, but destructive here: legacy pre-leg rows carry REAL operator data in plaintext JSON (e.g. `{"shell": {"timeout": 30}}`), not an empty-default residue. `_decrypt_overrides_column` instead falls through `InvalidToken` to `json.loads(raw)` — the plaintext IS the value — while still letting `JSONDecodeError` propagate for genuine corruption. The next `save()` on a legacy row rewrites the column as proper ciphertext; there is no eager rewrite migration.

**Masking is marker-derived, not hand-listed.** `MCP_OVERRIDE_CREDENTIAL_KEYS` (`the_one/mcp/_overrides.py`) is computed by scanning `StdioMCPOverride` / `StreamableHttpMCPOverride`'s `model_fields[name].metadata` for the `Substitute` marker (same `m is Substitute` identity check as `the_one/tools/resolver.py` and `api.py:_enrich_schema_with_markers`) — currently `{"env", "headers", "bearer_token"}`. `enabled_tools` / `disabled_tools` carry no marker and are never masked — they round-trip in the clear through Studio's MCPs tab. `tool_overrides` values are never masked: no built-in tool Config has a `Substitute`-marked field today (`WebConfig.default_user_agent` is the only `Substitute` field outside `_overrides.py`, and it is not secret).

`api.py:_agent_response(cfg)` is the single response helper every agent-config HTTP return routes through (`list_agents`, `get_agent`, `create_agent`, `update_agent`, `rename_agent`) — it masks exactly the `MCP_OVERRIDE_CREDENTIAL_KEYS` present inside each `mcp_overrides[<source>]` entry via `_mask_secret_value`, leaving every other key (including all of `tool_overrides`) byte-identical to what is stored.

**Preserve-on-PUT is server-side, not sentinel-based** (`api.py:_merge_preserved_mcp_credentials`, called from `update_agent` and, with `stored=None`, from `create_agent`). Studio does not round-trip the agent config — it rebuilds `mcp_overrides` from the DOM and renders no credential fields at all — so preserve cannot key off a client-sent sentinel the way the MCP-source PUT handler does; it resolves the incoming payload against the stored row instead, per `(source_name, credential_key)`:

- key omitted from the incoming source entry (or the whole source entry, or `mcp_overrides: null`, or the key omitted from the request body entirely — all four collapse to the same "nothing incoming" case since JSON `null` and an absent key are indistinguishable via `dict.get`) → keep the stored value.
- key present and mask-shaped (`_looks_masked`) → keep the stored value.
- key present as an explicit `null` → clear it.
- key present with any other value → overwrite.
- a mask-shaped value for a key with nothing stored is dropped, never persisted as the literal mask string.

For the two dict-valued keys (`headers`, `env`) the same four rules apply per INNER key, so an operator changing one header does not silently wipe the others. An empty merge result (nothing incoming, nothing stored) folds to `None` rather than `{}`, preserving the pre-leg None/`{}` fidelity when nothing was ever set.

### Self-configuration surface contract (M21 F01 L02-L03)

`the_one/self_configuration/` (new package) is a real per-agent `streamable-http` MCP source — DD1 in the flight spec — so all 14 Python and ~26 JavaScript sites that switch on `MCPSource.type` stay untouched and the operator's existing per-source/per-tool controls (`filter_mcp_tools_by_override`) govern it for free. Off by default for every agent; the operator opts an agent in from its own Studio "Self-configuration" tab. As of L03 the surface is no longer read-only: two write tools let an agent revise its own `description` and `system_prompt` — see "Write path and deferral contract" below.

**Module map**:
- `constants.py` — leaf module (no `the_one` imports): `MOUNT_PATH = "/mcp/self-configuration"`, `CONFINED_SOURCE_PATHS` (credential-source name → path prefix the gate confines it to), `AGENT_CREDENTIAL_PREFIX = "agt"`. `the_one/interfaces/web/middleware.py` imports ONLY this module from the package — the gate must not gain a heavy import for a security-sensitive per-request check.
- `credentials.py` — `SelfConfigurationCredentialSource` (the `CredentialSource` Protocol implementer registered against `api_credential.register_source`) plus an in-memory `identifier → (source_id, secret)` registry. The gate's lookup seam (`resolve_caller`) is synchronous and walked per-request, so this is a registry, not a DB read.
- `surface.py` — the module-level `FastMCP("the-one self-configuration", stateless_http=True, streamable_http_path="/")` instance and its four `@mcp.tool()`-decorated tools: two read (`get_my_configuration`, `describe_my_capabilities`) and two write (`update_my_description`, `update_my_system_prompt` — L03). `_calling_agent(ctx)` reads `ctx.request_context.request.scope[CALLER_SCOPE_KEY]` — the FIRST production reader of that scope key (Mission 20 stamped it but nothing consumed it before this leg) — resolves it to a source id via the credential registry, loads the row, and enforces DD9 (refuses if the row is gone or the owner's `mcp_source_ids` no longer contains it). Any failure — that refusal, or an L03 input-bounds `ValueError` — raises a plain exception with a one-line message; FastMCP's low-level server (`mcp.server.lowlevel.server.Server.call_tool`) catches every exception escaping a tool call and converts it to an `isError` result — this module never has to build that envelope itself, and never lets a stack trace reach the transport. ONE error mechanism for both refusal classes, by design (LD5).
- `projection.py` — `build_get_my_configuration` / `build_describe_my_capabilities`, pure `async` functions over repositories. Neither builds an `Agent` — building one from inside that agent's own tool call would recurse into the surface. `describe_my_capabilities`'s built-in-tools projection calls `BuiltinToolProvider().get_tools(...)` directly and applies the SAME two predicates `AgentFactory.create` uses (operator `ToolConfig.enabled`, `AgentConfig.is_tool_enabled`) — introspection, not agent construction.
- `pending.py` (L03, new) — the in-process `next_turn` deferral registry: `record(agent_name, *, system_prompt=None, description=None)` merges into an agent's pending entry, `apply_pending_revision(agent_name, agent) -> bool` pops and applies it onto a live `Agent` object, `clear_for_test()`. Process memory only — see "Write path and deferral contract" below.
- `manage.py` — `enable`/`disable`/`status`/`reconcile_on_startup`/`cascade_rename`/`cascade_delete`/`reject_foreign_surface_attachments`/`reject_surface_credential_overrides`, plus the reserved row-name constant `SURFACE_ROW_NAME = "self-configuration"` (L03/LD7). Every function takes its repositories/store as keyword arguments — this module never opens its own DB connection or encryptor.

**Ownership marker, not a new `AgentConfig` field** (LD1): a surface row carries `config["self_configuration"] = {"agent": "<name>"}`; enabled-ness *is* "a row with this marker exists AND its id is in the owner's `mcp_source_ids`" — nothing the agent can write governs whether its own surface exists, which is the mission's "off by default, operator-controlled" constraint satisfied structurally. `manage.status()` distinguishes a genuinely absent row (`{"enabled": false}`) from a detached-but-present one (`{"enabled": false, "orphaned_row": true}` — a legitimate operator detach via `PUT /api/agents/{name}` dropping the id from `mcp_source_ids`); the next `enable()` reuses that row rather than minting a duplicate credential.

**Gate confinement (LD2) is the highest-risk line in this package.** `CONFINED_SOURCE_PATHS` maps `"self-configuration"` → `MOUNT_PATH`; `CredentialGateMiddleware._handle_http`/`_handle_websocket` look the resolved caller's `source` up in that map and, only when present, refuse any HTTP path outside the prefix (403) and every WebSocket upgrade outright. The map is opt-in per source — `file` and the cookie channel's `session` are absent from it and are admitted exactly as before this leg. A check phrased as "source is not `file`" is wrong and will 403 the session cookie everywhere (caught in this leg's own design review before implementation — see the flight log's Decision D5).

**Startup sequence** (`interfaces/web/app.py:lifespan`): `register_credential_source_once()` (idempotent, guarded — safe to call every lifespan cycle) then `manage.reconcile_on_startup(mcp_repo)`, which rewrites every marked row's `config.url` from the CURRENT `settings.port` (LD3 — never trust a persisted port across a restart) and rebuilds the credential registry from those rows. The FastMCP sub-app is mounted (`app.mount(MOUNT_PATH, surface.mcp.streamable_http_app())`) at MODULE LOAD, before `lifespan` ever runs — `streamable_http_app()` is what lazily creates `mcp.session_manager`, so it must be called before `lifespan` tries to access that property. `lifespan` wraps `session_manager.run()` around its ENTIRE body (not just the yield point) via `_self_configuration_session_scope()`, which additionally guards `.run()` to fire AT MOST ONCE per process — the SDK's `StreamableHTTPSessionManager.run()` raises if called a second time on the same instance, and a real server process only enters `lifespan` once, but the unit-test suite cycles `TestClient(app)` (and therefore `lifespan`) hundreds of times in one pytest process. A test that needs the surface actually serving (`tests/test_self_configuration_surface.py`) does NOT reuse this singleton — it `importlib.reload`s `the_one.self_configuration.surface` to get a fresh, unstarted `FastMCP` instance and mounts that on its own throwaway app, mirroring the re-entrancy probe's mechanism (one process, one event loop, a real `uvicorn.Server` on an OS-allocated port, the platform's own client path dialing back into itself).

**Tool-name length (Anomaly A11) — closed by L03/LD7.** `MCPClientTool` prefixes every tool name as `mcp__{normalized_source_name}__{tool_name}` and drops (with a warning, not an error) any tool whose prefixed name exceeds 64 characters (`the_one/mcp/_tool.py`). Leg 2's row-name template, `self-configuration (<agent name>)`, left as little as ~11 characters of agent name before a tool silently dropped off the catalog — tighter still once L03 added `update_my_system_prompt` (23 chars). L03 closes this by giving EVERY agent's surface row the SAME constant name, `manage.SURFACE_ROW_NAME = "self-configuration"` — `mcp_sources.name` carries no UNIQUE constraint, ownership is the marker (not the name), and `mcp_overrides` is keyed per agent, so sharing one literal name across every agent is safe. With the constant, the four prefixed surface tool names are a FIXED 45-49 characters regardless of agent name length, well under the ceiling. `cascade_rename` no longer touches the row's name — only the ownership marker — since there is nothing left to rename. The literal name is RESERVED: `create_mcp_source`/`update_mcp_source` (`api.py`) 409 any attempt to create or rename a non-surface source to this exact name, because override application is keyed by source *name* (`_tool_provider.py`, mirrored in `mcps-tab.js`) and a same-named ordinary source on the same agent would collide with the platform-managed row. Startup `reconcile_on_startup` renames any surviving legacy-template row and migrates its owner's `mcp_overrides[old_name]` entry to the constant key (skipped, with a log line, if the constant key is already taken) so per-tool checkboxes set under Leg 2 survive the rename.

**`_cache` population (LD6)**: `manage.enable()` calls `surface.list_surface_tools()` — a direct, in-process introspection of `mcp._tool_manager.list_tools()`, no loopback hop — to populate a fresh (or re-enabled) row's `config._cache` in the same shape `/mcp-sources/{id}/test/connect` writes (`tools`, `capabilities`, `server_info`, `instructions`, `meta`, `protocol_version`, `last_updated`), plus `auth_posture: "no_auth"` so the pool never attempts DCR on a 401 for this source. This makes the very first agent build after enable take `MCPToolProvider`'s cache-first path (sub-100ms, no network) instead of the acquire+list_tools fallback. **L03 extends `reconcile_on_startup` to keep `_cache.tools` current for rows enabled BEFORE a catalog change**, not just at enable time: on every startup, for every marked row, `_cache.tools` is unconditionally rewritten from the CURRENT `surface.list_surface_tools()` (not gated on the URL-staleness check alongside it) — so a row enabled under Leg 2 (two tools) picks up L03's two new write tools on the next process start, and the operator's per-tool checkboxes on the MCPs tab show all four. A row is persisted only when something actually changed (URL, tools, or name).

**Write path and deferral contract (M21 F01 L03)**: `update_my_description(text, apply)` / `update_my_system_prompt(text, apply)` — `apply` is `"next_turn"` or `"next_session"`, whole-value replacement (no append/partial edit; a future `AgentConfig` field stays unwritable because no tool addresses it, DD6's "by construction" contract). Both tools follow the same order: resolve caller (`_calling_agent`, DD9) → validate (`_validate_write_input`, LD5: non-empty `str`, ≤ 64 KiB UTF-8-encoded, `apply` one of the two literals — else a plain `ValueError`, the module's one error mechanism) → `SQLiteAgentStore.load → model_copy(update=…) → save` (persist FIRST, always — `LD2`) → if `apply == "next_turn"`, `pending.record(agent_name, **{field: text})` → return a truthful result (`applied_to_store`, `effective`, `field`, `length`, a one-sentence explanation) that never claims the running conversation already changed.

- **Why persist-first matters (LD2/LD3)**: `next_session` needs no further machinery — `_get_or_restore_session` always rebuilds `Agent` from the stored row, so a rebuild picks up the revision whether or not a pending entry exists. If the live session's `Agent` object is rebuilt mid-turn (a rejoin), the pending entry becomes a no-op — moot, because the rebuild already read the fresh row. This resolves the flight's open question about a pending revision surviving a mid-turn rebuild: it doesn't need to, because the store already has it.
- **Why `next_turn` needs a deferral at all (DD7/LD1)**: `Agent._run_iterations` re-binds `request_messages = self.messages` INSIDE its `while` loop, and tool dispatch happens in that same loop — an in-place mutation of `messages[0]` from inside the write tool would land on the NEXT ITERATION OF THE SAME TURN, which the mission explicitly rules out. The write tool therefore only persists and records; nothing about the LIVE `Agent` object changes until an explicit hook fires. Contextvars set around `agent.step` (`current_chat_session_id`, `current_tool_call_id`) are NOT visible to the write tool — it runs inside the loopback request's own task — so the deferral is keyed by AGENT NAME (`the_one/self_configuration/pending.py`'s `_pending: dict[str, dict[str, str]]`), not by session or contextvar.
- **The hook, and EXACTLY where it is wired**: `pending.apply_pending_revision(agent_name, agent)` pops the agent's pending entry (if any) and mutates `agent.system_prompt` plus replaces `agent.messages[0]` with a fresh `Message.system(...)` — the same two-line pattern `Agent.reset()` uses, minus the history wipe (`description` has no live-conversation counterpart to mutate; it is store-only). It is called from EXACTLY two sites in `the_one/interfaces/web/app.py`, both non-paused turn-SETTLE points: inside `_process_and_broadcast`'s `if not paused:` block (before its `done` broadcast) and inside `_resume_paused_session`'s `if not re_paused:` block (before ITS `done` broadcast — NOT the unconditional save/usage tail after it, which also runs when the resume RE-pauses; a re-pause is not a settle). Both call sites pass `session.agent_name or "default"` — the `or "default"` is LOAD-BEARING: `Session.agent_name` is stored as `None` for the default agent while the pending registry and `_calling_agent` key on the literal string `"default"`; a skip-on-`None` guard would silently degrade `next_turn` to `next_session` for single-agent installs.
- **Merge and consumption semantics**: `pending.record()` MERGES into any existing entry for the same agent — two different-field revisions (a description AND a system-prompt revision) made in the same turn both apply at the SAME settle; two same-field revisions in one turn both persist in order, and the LAST one wins everywhere (store and pending entry alike). `apply_pending_revision` POPS the entry — a second settle for the same agent with nothing new pending is a no-op. `pending.py` also logs an INFO line with the agent name, the revised field(s), and a per-agent-per-process revision COUNT at record time — the leg does not rate-limit revisions (Flight 2's revision log is the real mitigation), so this count is the only visibility into a runaway self-revision loop today.
- **Reachable only through the confined surface**: same gate confinement, ownership guards, and per-tool operator controls as the read tools (see above) — nothing new to the security boundary. The residual risk this leg does NOT mitigate — an injected agent using these tools to shed its own guardrails — is recorded in `SECURITY-MODEL.md`'s "Self-configuration surface" section as a LIVE risk as of this leg, not a deferred one.

**Approval mode + revision queue (M21 F02 L02)**: the operator gate on the write path. Each agent carries `AgentConfig.self_revision_requires_approval: bool = False`, persisted in the v35 `agents.self_revision_requires_approval INTEGER NOT NULL DEFAULT 0` column. It is **operator-owned and agent-unreachable by construction**: no write tool addresses it (the catalog shape, DD6), the `get_my_configuration` projection omits it (an explicit allowlist), and it is set ONLY by an immediate-post Studio control via a **targeted** `UPDATE agents SET self_revision_requires_approval=? WHERE name=?` (`SQLiteAgentStore.set_self_revision_requires_approval`) — never a full-row `save`, so the toggle dodges the whole-row last-writer-wins window entirely. **DD2 HIGH:** `update_agent` (`api.py`) preserves the field when a Studio Save omits it (Studio rebuilds its payload from the DOM and never sends it), mirroring the `mcp_overrides` preserve — otherwise every unrelated Save would silently reset approval mode to `False`.
- **The branch (DD3)**: `_apply_revision` (`surface.py`) reads `config.self_revision_requires_approval` after loading config. When **True**, it calls `AgentRevisionRepository.upsert_pending_revision(...)` (enqueue one `pending`/`self` row, dedup one per agent+field) and returns `{applied_to_store: False, effective: "pending_operator_approval", field, length, message}` — a truthful, non-retry-inducing result — WITHOUT `save` or `pending.record`. The store and live conversation are untouched; an approved revision propagates next-session only (the proposing turn's `apply` is moot and never replayed). When **False**, the existing Leg 1 persist+log path runs unchanged.
- **New `AgentRevisionRepository` methods (`repositories.py`)**: `count_pending(agent_name)` (per-agent), `upsert_pending_revision(...)` (dedup, returns `(revision, created)`), `_transition`/`mark_applied`/`mark_dismissed` (idempotent-on-self-target, `ValueError`→409 on any other non-`pending` state, single UPDATE stamping `status`+`resolved_at`), `update_base_value(id, base)` (override re-capture), `supersede_pending(agent_name)` (bulk, DD8). The shape mirrors the connector subsystem's `PendingApprovalRepository` (peer-approval queue), removed in the Mission 23 connector reset. No revision-table migration — Leg 1's v34 already ships all four statuses and the `(agent_name, status)` index.
- **Endpoints (`api.py`, beside the self-config routes)**: `PUT /agents/{name}/self-configuration/approval-mode` (`{requires_approval: bool}` → targeted UPDATE → `{requires_approval}`); `GET .../revisions` (name-scoped, newest-first, full rows — `base_value`/`proposed_value` are plaintext description/system_prompt, safe and needed for the decision); `GET .../revisions/pending-count` (`{count}`); `POST .../revisions/{id}/dismiss`; `POST .../revisions/{id}/approve` (`?override=bool`). Every revision route enforces a **cross-ID 404 guard** (`revision.agent_name != {name}` → 404, never leaking that the id exists under another agent) and maps the repo's `ValueError` to **409**.
- **DD4 fail-closed approve**: on a `pending` row, compare `base_value` (the field's value the agent saw at capture) to the CURRENT stored value. Unchanged → apply (`load → model_copy({field: proposed}) → save`) + `mark_applied`. Drifted and no `override` → **409** returning `{error: "stale", current_value, proposed_value, base_value}`, writing nothing. Drifted with `override=true` → `update_base_value(id, current)` first, then apply + `mark_applied`. Idempotent no-op on an already-`applied` row; 409 on dismissed/superseded. **The override branch is intentionally NOT transactional** (`update_base_value` → `save` → `mark_applied` are three commits); a `save` failure after `update_base_value` leaves a still-`pending`, still-re-approvable row — do NOT reorder so `mark_applied` precedes `save`.
- **DD8 supersede-on-disable**: `manage.disable` takes an optional `revisions_repo` kwarg (threaded from the DELETE endpoint) and calls `supersede_pending(agent_name)` **above** the `row is None` early-return, so a disable ALWAYS clears the queue — a revision proposed under a since-revoked surface becomes `superseded` and can never be approved (a follow-up approve is 409). `manage.status` returns `requires_approval` from the loaded config in EVERY config-loaded branch (enabled / row-None / orphaned) so the Studio tab renders the toggle consistently regardless of surface state.
- **Studio UI** (`self-configuration-tab.js` + `studio.js` + `agent-editor.js`): an immediate-post approval-mode toggle (mirrors the enable toggle — NOT a `collectFormData()` field), a pending-revision queue rendering approve/dismiss cards (each shows base→proposed on the clean path too, one-click clean approve, a 409-staleness panel with current-vs-proposed and an explicit override button), and a per-agent pending count. On any action the tab relies on `_refreshAgentAfterSelfConfigurationChange` (which re-fetches and re-renders via `doSelect`, so the resolved row leaves the pending list) rather than an in-place swap. Every new control carries a `data-testid`.

**Restore (M21 F02 L03)**: operator-direct rollback of a description / system_prompt to any earlier value the field actually held.
- **Endpoint**: `POST /agents/{name}/self-configuration/revisions/{id}/restore`, query `side: Literal["proposed", "base"] = "proposed"` (a `Literal`, so FastAPI auto-422s a bad value — the enum analog of approve's `override` query param). Same cross-ID/unknown-id 404 guard as approve/dismiss. **LD1**: the target must be an `applied` revision (only `applied` rows name a value the field genuinely took — a `pending` was never applied, a `dismissed` was declined, a `superseded` was orphaned); a non-applied target → **409**, store + log untouched. **LD2**: `side` selects the value node — `proposed` reinstates the target row's after-image, `base` its before-image; `side=base` on the earliest applied row reaches the **original** pre-first-revision value (never a `proposed_value`, only the earliest `base_value`), and a mid-timeline `base_value` reaches any out-of-band operator-set value (a direct `PUT /agents/{name}` edit leaves no revision row).
- **DD5 operator-direct**: restore **never consults `self_revision_requires_approval`** and never queues — the operator is the approval authority. It mirrors approve's clean apply arm (`_load_agent_or_404` → `config.model_copy(update={field: reinstated})` → `store.save`), then `append`s a NEW `source='restore'`, `status='applied'` row with `restored_from={id}`, `base_value` = the pre-restore current value, `resolved_at == created_at` — an append-only record, never a pointer rewind. Restore-to-current still logs (an honest record; `base_value == proposed_value` is acceptable). **No new repo method** — reuses `AgentRevisionRepository.append` (already accepts `source`/`status`/`restored_from`) and needs no migration.
- **No agent-facing restore tool** — the write allowlist (tool catalog shape) is unchanged, so the agent cannot restore itself. The mission's "by construction" boundary held: rollback is operator-only.
- **Studio UI**: the Self-configuration tab renders a **revision-history** view (the full `GET .../revisions` list, newest-first, reusing the queue's fetch — the queue is the `status==='pending'` subset, the history the whole list) below the pending queue. Each entry shows field / before→after / timestamp / source (`self`/`restore`) / status. The history renders **one Restore control per distinct value-node** — the dedup of `base_value` + `proposed_value` across all `applied` rows (walked oldest-first so the earliest holder of each value wins) — each restoring via an appropriate `(revision_id, side)`, so every value the field held is restorable with no duplicate buttons. `onRestore(name, id, side)` → `POST .../restore?side=...` → `_refreshAgentAfterSelfConfigurationChange`. New `data-testid`s registered in `docs/ui-testid-registry.md`.

### External-client credential (M21 F03)

Everything above is the agent's OWN `agt` principal reaching its surface over the loopback. Flight 3 adds a SECOND principal on the same surface: an **external client** (a script, a CI job, a separate service) the operator explicitly grants access to tune one agent. The two principals share the `/mcp/self-configuration` mount, the four-tool catalog, and every input/ownership bound; they differ only in credential lifecycle and write provenance.

- **A distinct `ext`-prefixed, per-grant credential (`external_credentials.py`, DD1).** Each operator grant mints its OWN `ext_<id>.<secret>` credential — a different prefix from both `loc` and `agt`, so a token's type is legible at a glance and the other registered credential sources reject it on prefix mismatch, falling through to `ExternalAgentCredentialSource`. Resolution walks the same synchronous seam as `agt`: a process-local `identifier → (source_id, secret)` registry (`external_credentials._ext_registry`), rebuilt at startup from the store and mutated live on mint/revoke/rotate — no per-request DB read. Unlike the single per-agent `agt` credential, an agent can carry MANY external grants at once, each independently revocable.
- **A real store, not a surface-row secret (`agent_external_credentials`, schema v36, DD2/DD8).** The `agt` credential hides inside its surface row's encrypted `secrets["Authorization"]`; the external credentials get their own secrets-bearing table (`identifier` PK, `source_id`, Fernet-encrypted `secret`, `label`, `created_at`), fronted by `AgentExternalCredentialRepository` (encryptor-bearing). The FK keys on the surface ROW — `source_id REFERENCES mcp_sources(id) ON DELETE CASCADE` — not on `agent_name`, so an agent rename (row id stable) is free and **surface-disable / agent-delete auto-revokes every external grant via the FK cascade** (DD9): an external principal never outlives the operator closing the surface. Hard-revoke is a row DELETE (no `revoked_at` tombstone); the audit of "which external principal tuned this agent" lives in the revision log, not here.
- **Secret-free projection; secret returned exactly once at mint (DD2).** `list_for_source` (behind `GET .../external-credentials`) projects `{identifier, label, created_at}` only — never the secret. The `ext_<id>.<secret>` token is returned ONCE, by `mint` (`POST .../external-credentials`) and by `rotate`, in the response's `token` field; no read path returns it again (mirrors the operator credential's mint-once shape, and the Studio UI's copy-once reveal enforces it in the browser).
- **A second confined `CredentialSource` on the SAME mount (`EXTERNAL_SOURCE_NAME = "self-configuration-external"`).** `CONFINED_SOURCE_PATHS` maps this source name to `MOUNT_PATH` alongside the `agt` source, so the external principal inherits Flight 1's confinement UNCHANGED — no new enforcement code, one extra map entry. `CredentialGateMiddleware` refuses any request whose path is outside `/mcp/self-configuration` with **403** and refuses every WebSocket upgrade outright. This is the **governance invariant**: an external principal reaches ONLY the four confined MCP tools; the operator control plane (`/api/...`, admin surfaces, every other mount) answers it with 403, exactly as it does the agent's own `agt` credential.
- **Per-principal revoke / rotate (`api.py`, DD7)** — contrast the operator credential's rotate-EVERYTHING. `revoke` DELETEs one row and evicts one registry entry (the next request bearing that token is 401, no restart); `rotate` DELETEs the old and mints a fresh credential for the SAME label/agent, returning the new token once and 401-ing the old immediately. Both enforce a cross-ID 404 guard (`cred.source_id` must equal `name`'s surface row id) so a grant can never be revoked/rotated through another agent's route, and NEVER touch the agent's `agt` credential or any sibling external grant. `mint`/`rotate` 409 when the surface is not enabled (they issue a live credential); `revoke` works on an orphaned (detached-but-present) surface too, so an operator can always tear a grant down.
- **External-write provenance in the revision log (schema v37, DD3).** The surface routes an external caller by `caller.source == EXTERNAL_SOURCE_NAME`: `_calling_principal` returns `(agent_name, "external", caller.identifier)` vs `(agent_name, "self", None)` for the agent's own write. Every revision the write path appends carries `source` (`agent_revisions.source` CHECK widened to `'self' | 'restore' | 'external'`) plus a nullable `source_principal` = the `ext_` identifier for an external write (NULL for `self`/`restore`) — so the log answers "which external principal wrote this."
- **External writes honor the SAME per-agent approval flag.** The write path checks `config.self_revision_requires_approval` regardless of source, so an external client's proposal is held in the pending queue (never silently applied) exactly like a `self` write when approval mode is on — the operator gate on the mission's central write-risk covers the external principal with no special-casing.
- **Operational trace: log lines, not a tombstone (Flight 01 Leg 2, Q2).** Mint/revoke/rotate each emit one INFO line on `the_one.interfaces.web.api`'s module logger (agent name, `ext_` identifier, label, principal — never the secret); `manage.disable`/`manage.cascade_delete` each emit one INFO line on `the_one.self_configuration.manage`'s logger at the two points a credential row disappears without an explicit revoke (surface disable, agent delete), carrying the evicted identifiers and their count — the row is already gone by then (FK cascade), so the cascade line can't carry a label the way the mint line does. A `revoked_at` tombstone was considered and rejected: the FK cascade would bypass it (recording explicit revokes but not cascades), and a queryable audit trail is properly an events table — a separate initiative from this flight, alongside the Advisory logging sweep, which inherits this log-line field set as its convention.

### Connector subsystem contract (Mission 23 Flight 2)

`the_one/connectors/` bridges external chat platforms to the agent loop.
Mission 23 Flight 1 deleted the pre-reset framework outright (a ~430-line
message-routing layer, per-agent ACLs, manual peer-approval flows, a
slash-command surface, worker-pool machinery, the Discord plugin); Flight 2
rebuilt a small, platform-agnostic core from scratch. **The full contract —
Protocol shapes, manager lifecycle, inbound pipeline stages, pairing, reply
policy, the send/history-tool authorization rule, config schema, test
seams, known limitations — lives in `the_one/connectors/README.md`.** This
entry is the architecture-index pointer other subsystem-contract entries
get; don't duplicate the README's content here.

- **Module map**: `base.py` (Protocols + envelope/target dataclasses),
  `registry.py` (type → plugin dict; `discord` registers unconditionally
  at lifespan startup as of Flight 3, `stub` remains test-only
  registration), `manager.py` (`ConnectorManager`: listener-task
  lifecycle + in-memory pairing store, installed via
  `set_manager`/`get_manager` mirroring `agent.factory`'s accessor pair),
  `inbound.py` (`dispatch_inbound`: admission → `/new` → reply policy →
  session resolution → per-session-locked agent dispatch), `stub.py`
  (`StubPlugin`: in-process test/dev fixture, never registered in
  production), `discord/` (`_gateway.py`/`_rest.py`/`plugin.py`, Flight
  3: the first real `ConnectorPlugin` — full contract in the README's
  "Discord (Flight 3)" section, not duplicated here).
- **Three built-in tools** attached alongside the package:
  `tools/connector_send.py` (`send_to_platform_channel`) and
  `tools/connector_history.py` (`fetch_channel_history`, DD-8, optional per
  plugin via `getattr(client, "history", None)` —
  `optional-plugin-hook-via-getattr-sentinel` above), sharing one
  binding-derived authorization rule (see the README's "Authorization
  rule"); and `tools/connector_lookup.py` (`find_platform_destination`,
  Mission 23 Flight 4 Leg 3, DD-5) — a read-only name-to-id lookup over
  the passively-populated connector directory, CONNECTOR-LEVEL scoped
  (not the send/history pair's per-target rule) and carve-out-seeded
  alongside the send tool (DD-6's generalization of the baseline-
  visibility carve-out below to the connector tool pair). See the
  README's "Lookup tool" section for the full contract.
- **Persisted across the reset, unaffected by the deletion/rebuild**: the
  `Connector` DB model/row, `ConnectorRepository`, and connector-secret
  enrollment in the encryption-rotation invariant above; `Message.visibility`
  and the `ChatSession` session-keying columns (`platform`, `connector_id`,
  `channel_id`, `thread_id`, `peer_id`, `session_metadata`,
  `last_inbound_at`). Flight 1 deleted the dispatcher that populated them;
  Flight 2's `inbound.py` populates them again, on the new contract.
- **Reply visibility** (`tag_post_step_visibility`, `the_one/llm/base.py`)
  is connector-agnostic machinery with a live connector-specific branch
  again: a successful `send_to_platform_channel` tool result is tagged
  peer-visible (`visibility=None`); everything else a turn produces is
  tagged operator-only by default. See
  "`message-additive-back-compat-via-emit-when-non-none`" above for the
  general visibility-field convention this specializes.
- **DD-10 auto-reply mechanical fallback (Flight 3, mid-flight amendment)**:
  `dispatch_inbound` (`the_one/connectors/inbound.py::_auto_deliver_reply`)
  runs immediately after `tag_post_step_visibility` and mechanically
  delivers the turn's FINAL assistant text to the ORIGINATING target —
  `PeerTarget`/`ChannelTarget` resolved straight from the inbound
  `InboundEnvelope`, via `manager.client_for(connector_id).send()` — then
  flips that message's `visibility` back to `None` (peer-visible), so the
  persisted history reflects the real delivery. Skip rule: a turn that
  already contains a successful `send_to_platform_channel` result is left
  alone entirely (the agent spoke to the platform deliberately; no
  double-send). Delivery failure (no live client, `ConnectorClientError`,
  any other exception) is logged and the text is left operator-only — no
  retry, no crash. This only fires for `dispatch_inbound`-originated turns
  (a peer's own inbound message); the WS-storage-edge shim's operator-typed
  path (`interfaces/web/app.py`) never runs through `dispatch_inbound` and
  is untouched — an operator's console note still never reaches the
  platform. Landed because live-gate checkpoint 2 attempt 2 proved the
  prior design had NO mechanism for a plain reply to reach a peer at
  all — `dispatch_inbound` hands the model only raw text, so it cannot
  target the send tool, and plain assistant text was operator-only by
  contract; the project's own `prompt-discipline-needs-mechanical-fallback`
  convention, applied to the reply path rather than left to model
  tool-calling reliability (RQ8's lesson). The send tool remains the
  agent-INITIATED path (speak-first, cross-channel, deliberate re-send) —
  unchanged, no new tool, no change to the tool's own visible schema. See
  `the_one/connectors/README.md`'s "Reply visibility" section and
  `tests/behavior/stub-connector-round-trip.md`'s 2026-09-01 re-author note
  for the end-to-end contract.
- **Discord (Flight 3)** is the first real plugin, registered
  unconditionally (not gated like `stub`); **Flight 4** proves the
  `ConnectorPlugin` contract generalizes to further platforms (Slack,
  Matrix, Signal, email — each a small client, none needing a public
  endpoint per the mission's design). The module-level `set_factory`/
  `get_factory` accessor (`the_one/agent/factory.py`) that a real gateway
  listener resolves the application factory through — see
  `lifespan-wiring-same-leg-as-installation` above — is now driven by a
  REAL (non-test) gateway listener for the first time.
- **DD-5 baseline-visibility carve-out (Flight 3 Leg 2, agent loop)**: the
  mission-amended constraint making `send_to_platform_channel` visible to
  the model without a `search_tools` call first. Implemented by SEEDING
  `Agent._loaded_schemas`/`_loaded_tool_names` (the F10 L1 strict-baseline
  containers) with the send tool's schema at factory-build time — never by
  appending inside `Agent._compute_visible_schemas`, which would bypass
  the search-match dedup and risk a duplicate schema reaching the model.
  `Agent.__init__` copies the seed onto `_seed_schemas`/`_seed_tool_names`
  so `reset()` (which unconditionally clears the live containers) can
  re-extend from the seed — the seed itself has no other memory. One
  deliberate, owner-approved touch to the frozen loop, scoped to a single
  baseline entry and pinned by tests; see `the_one/agent/core.py`'s
  `__init__`/`reset()` and `the_one/agent/factory.py`'s
  `SEND_TO_PLATFORM_CHANNEL_TOOL_NAME` seeding block for the
  implementation. The `discord-live-round-trip` behavior spec proves it
  empirically — `test-agent`'s system prompt there carries no tool-
  discipline nudge, the mechanical-fallback proof `mechanical-fallback-
  prompt-truth-pairing` (above) requires.
- **DD-11 send-tool target defaulting (Flight 3, mid-flight amendment)**:
  `send_to_platform_channel`'s `target` argument is now OPTIONAL — when
  omitted, the tool resolves a default from `current_chat_session_id`
  (`agent/_context.py`) → the session's own `chat_sessions` keying
  columns, mirroring `resolve_session`'s keying (`channel_id` is the
  session's primary key, not `peer_id`): `channel_id`-bearing → a
  `ChannelTarget`; `channel_id`-absent + `peer_id`-present → a
  `PeerTarget`. No active session context, or a session not bound to a
  connector at all, is a clear error, never a guess. The resolved default
  is folded into the exact dict shape an explicit `target` takes, so it
  flows through the SAME binding-derived authorization the explicit-target
  path already uses — no restructuring, and a defaulted target that fails
  authorization errors identically to an explicit one. Landed because
  live-gate checkpoint 5 proved the model can call the DD-5 carved-out
  tool by name but has no way to discover its own session's platform ids
  to fill `target` explicitly. See `the_one/connectors/README.md`'s
  "Send-tool target defaulting (DD-11)" section and
  `tools/connector_send.py`.

### MCP F2 Client Foundation (authoritative for F3+)

1. **Module layout** — `the_one/mcp/` is a peer of `the_one/llm/`, NOT a sub-package of `the_one/tools/`. `MCPClient` is a service abstraction; `MCPToolProvider` wraps individual `MCPTool`s into the project's `Tool` abstraction.

2. **`_PINNED_PROTOCOL_VERSION`** — Defined in `the_one/mcp/__init__.py`. **Read at call time** via `the_one.mcp._PINNED_PROTOCOL_VERSION`, NOT `from the_one.mcp import _PINNED_PROTOCOL_VERSION` — the latter binds at module-load time and breaks `monkeypatch.setattr` in tests. Upgrade procedure: bump SDK pin → re-read `LATEST_PROTOCOL_VERSION` → update the constant → run `test_pinned_protocol_version_matches_sdk`.

3. **Pool-compat invariants** — `MCPClient` exposes `is_alive: bool` (false until `connect()` returns, false from `disconnect()` start) and `last_activity: float` (monotonic, updated per `list_tools`/`call_tool`). `disconnect()` is **idempotent and never raises**. No thread-locals, no module-globals. Naming is aligned with `PtySession` so the pool builds one reaper code path.

4. **`build_stdio_environ`** — `(source, allowlist_env) -> dict[str, str]` performs a 2-layer flat merge: `allowlist_env ∪ (config.env ∪ secrets)`, secrets winning on collision. **Do NOT consume `MCPSource.merged_config()`** for stdio env assembly — that helper produces a flat top-level merge that would inject `command`/`args` as env-var-shaped keys.

5. **Fail-hard version handshake** — `connect()` raises `MCPVersionMismatch` when `protocolVersion != _PINNED_PROTOCOL_VERSION` (exact match required). Narrower than the SDK's `SUPPORTED_PROTOCOL_VERSIONS` whitelist; the SDK's own `RuntimeError` is caught and re-raised as `MCPVersionMismatch` so operators see one error type. Pre-release stance; revisit at 1.0.

For runtime invariants (test-seam pattern, AsyncExitStack composition, `_DEFAULT` sentinel rationale, env-var assembly, sandbox-wrap composition, pool semantics), see `the_one/mcp/README.md`.

### Sandbox seam — platform-wide (M14 F1+F2, authoritative for F4+)

**Scope (M14 F1+F2)**: the sandbox is now a platform-wide seam, not an MCP-only one. Four
spawn paths route through a single `get_sandbox_backend()` factory: built-in `shell` tool,
built-in `python_exec` tool, stdio MCP servers, and PTY `shell_session_*` sessions (wired
in M14 F2).

**Backend selection (`get_sandbox_backend()` in `the_one/platform/sandbox/factory.py`)**:
returns a `BubblewrapSandbox` on Linux when `bwrap` is in `$PATH`, and a
`PassthroughSandbox` otherwise (off-Linux or bwrap missing on Linux). On Linux with a
missing `bwrap`, a one-time WARNING is emitted; no `SandboxError` is raised at construction
time. The factory is the sole selector — spawn sites do NOT construct backends directly.

**`PassthroughSandbox`**: a no-op backend that returns the command/args/env unchanged.
Proves the seam contract without enforcing containment. Used for non-Linux hosts, for
bwrap-absent Linux environments (with logged warning), and for all passthrough-pinned
unit tests (`test_execution_tools.py`). The passthrough is observable (logged) — absence
of enforcement is not silent.

**Built-in-tool profile (host-workspace, M14 F1 L4)**:
`_build_tool_profile(exec_cfg, fs_cfg)` in `the_one/tools/execution.py` derives a
`SandboxProfile` for `shell` and `python_exec`:
- `writable_paths` = `FilesystemConfig.path_allowlist` (operator-configured workspace).
- `readonly_overlay_paths` = `FilesystemConfig.path_denylist` (denylisted entries are
  bound read-only via `--ro-bind-try`; write attempts raise; **read-scoping is satisfied
  for the boxed path** (box has no user FS — canary files are absent by construction);
  **host-workspace read-scoping still deferred** — denylisted secrets are not writable,
  not necessarily unreadable on the host path).
- `home` = real `$HOME` (the host-workspace profile gives the agent a capable assistant
  posture, not a cage; `/tmp` default is for MCP servers where no real workspace applies).
- `network_allowed` = `ExecutionConfig.sandbox_network_allowed` (deny-by-default; False
  unless the operator opts in).

1. **Strict-by-default trust** — Locally-spawned stdio MCP servers run in a bubblewrap jail: read-only filesystem outside an operator-configured `writable_paths` list; network OFF unless `network_allowed=True`. Operator-trust threat model: the sandbox does not defend against operator mistakes (broad `writable_paths`, `network_allowed=True` on untrusted sources), only against MCP-author mistakes / supply-chain compromise within the sandboxed scope.

2. **Profile storage** — `MCPSource.config["sandbox"] = {"writable_paths": list[str], "network_allowed": bool}` lives plaintext alongside `command`/`args`/`env`. Both fields optional; defaults `[]` and `false`. Namespace-flag fields (`pid_unshare`, `ipc_unshare`, `uts_unshare`, bool-defaulting-True) are JSON-edit-only advanced knobs — API validator passes them through unchanged.

3. **`ToolSandbox` Protocol** — `prepare_spawn(profile, command, args, env, cwd=None) -> SpawnSpec`. `SpawnSpec` is `@dataclass(frozen=True)` with `command/args/env/cwd` plus Windows-only `creation_flags: int = 0` and `attribute_list`. Windows fields exist purely so a future backend can populate them without changing the Protocol.

4. **`SandboxError` boundary** — Failures BEFORE bwrap successfully wraps-and-execs raise `SandboxError` (writable_paths entry doesn't exist, `EPERM` on `unshare`, container lacks §10 privilege grants). Failures AFTER (target spawned but exits non-zero, init handshake fails) raise `MCPConnectionError` / `MCPVersionMismatch`. **Bwrap missing** no longer raises `SandboxError` at construction time — the factory routes to `PassthroughSandbox` (one-time WARNING on Linux; no error). The runtime bwrap-stderr→`SandboxError` translation on the MCP stdio path (catalog messages in `the_one/mcp/errors.py`) still raises `SandboxError` on post-exec bwrap failures. `THE_ONE_SANDBOX_DISABLED` is never read in production paths. Catalog messages (operator-facing, verbatim-tested) live in `the_one/mcp/errors.py`.

5. **Privilege model** — Dev container (now retired): `cap_add: [SYS_ADMIN]` AND `security_opt: [seccomp:unconfined]` (BOTH — SYS_ADMIN alone is filtered by docker's default seccomp profile). Host-native dev runs bwrap directly with the host's own privileges, so those container grants no longer apply; the seccomp/SYS_ADMIN semantics are retained here as a record of what bwrap needs when it IS containerized. Browser-test CI: no privilege grants; `THE_ONE_SANDBOX_DISABLED=1` AND `THE_ONE_TEST_MODE=1` (BOTH; set ONLY by `tests/conftest.py::pytest_configure`). Production: no flags — bwrap is mandatory.

   **Operational guardrail**: `THE_ONE_TEST_MODE` MUST NOT appear in any Dockerfile, compose env, entrypoint script, k8s manifest, or CI variable. Presence outside pytest is a deployment defect.

6. **HOME policy** — `BubblewrapSandbox.prepare_spawn` sets `env["HOME"]` from `profile.home` when set, otherwise defaults to `"/tmp"` (MCP safe default — inherited `HOME=/root` would be read-only-but-not-writable under `--ro-bind / /`; subprocess writes to `~/.cache` would EACCES; `/tmp` is writable via `--tmpfs`). The host-workspace profile (`_build_tool_profile`) passes the real `$HOME` so built-in tools get a capable-assistant posture. Operators still cannot override HOME via the kv-table — `SandboxProfile.from_dict` intentionally omits `home` from its parsed-key set.

### the_one/platform/sandbox/

Four-module package implementing the cross-platform sandbox seam (M14 F1+F2):

- **`base.py`** — defines `SandboxProfile` (policy dataclass: `writable_paths`,
  `readonly_overlay_paths`, `network_allowed`, namespace-unshare flags, `home`),
  `SpawnSpec` (frozen dataclass: `command/args/env/cwd` + Windows-only `creation_flags`
  and `attribute_list` for forward-compat), and the `ToolSandbox` `Protocol`
  (`runtime_checkable`; structurally satisfied — no inheritance required).
- **`factory.py`** — `get_sandbox_backend() -> ToolSandbox`: sole backend selector.
  Returns `BubblewrapSandbox` on Linux when `bwrap` is in `$PATH`; falls through to
  `PassthroughSandbox` on non-Linux, bwrap-absent Linux (one-time WARNING), or test
  double-flag bypass (`THE_ONE_SANDBOX_DISABLED=1` + `THE_ONE_TEST_MODE=1`). Re-evaluates
  on every call (not memoized) so test monkeypatching is always visible.
- **`bubblewrap.py`** — `BubblewrapSandbox`: wraps the target command in a bwrap PID
  namespace. `prepare_spawn(profile, command, args, env, cwd) -> SpawnSpec` emits the
  bwrap argv: `--die-with-parent`, `--unshare-user/pid/ipc/uts/net`, `--clearenv`,
  `--setenv` per env key, `--ro-bind / /`, `--tmpfs /tmp`, `--bind` per `writable_paths`,
  `--ro-bind-try` per `readonly_overlay_paths` (after writable mounts so overlays win),
  `--proc /proc`, `--dev /dev`, `[--chdir cwd]`, `--`, then the wrapped command and args.
- **`passthrough.py`** — `PassthroughSandbox`: no-op backend; returns command/args/env/cwd
  unchanged. Forward-compat shim for non-Linux hosts and test environments.

**The `prepare_spawn → SpawnSpec` contract** is the seam's public surface. All four spawn
sites call `get_sandbox_backend().prepare_spawn(profile, command, args, env, cwd)` and
consume the returned `SpawnSpec` — none construct a backend directly. The four sites are:
`ShellTool` (`tools/shell.py`), `PythonExecTool` (`tools/python_exec.py`),
`connect_stdio` in `mcp/transports/stdio.py` (MCP stdio servers), and
`UnixPtySession.start()` in `platform/pty.py` (PTY `shell_session_*` — added M14 F2).

### MCP error translation

`MCPClient.{connect, list_tools, call_tool}` raise one of: `MCPVersionMismatch`, `MCPAuthRequired`, `SandboxError` (stdio only), or `MCPConnectionError` (catchall). `MCPToolProvider.get_tools_for_agent` graceful-skips all four. Adding a fifth typed exception requires updating BOTH the translator AND the consumer's match list.

**Nested `try/except*` in `connect()`** — Python (PEP 654) forbids mixing `except` and `except*` in one block. The OAuth `except*` nests inside an inner `try` so the version-mismatch `except RuntimeError` can stay flat. `list_tools`/`call_tool` use a flat shape because they have no `except` siblings. Don't "tidy up" the asymmetry.

**Three 401 sources in `connect()`** — inner `except* (OAuthFlowError, OAuthTokenError)`, outer `BaseExceptionGroup.subgroup(httpx.HTTPStatusError)` walk, and `except asyncio.CancelledError` (narrowed to non-OAuth/non-401 only). Narrowing is preserved by comments; don't collapse them.

**`MCPAuthRequired` propagation** — `connect()`'s outer `except (MCPClientError, NotImplementedError): … raise` already propagates `MCPAuthRequired` cleanly. `list_tools`/`call_tool` DO need an explicit `except MCPAuthRequired: raise` guard because their outer `except McpError` would re-wrap. Asymmetry by design.

**Synthetic csid pattern** — Three csid shapes pass through `oauth/handlers.py::redirect_handler`: real csids (12-char hex), `f"test:{source_id}"` (Test connection endpoint), `f"agent_build:{source.id}"` (pool entry-worker). Disjoint by character-set construction — hex cannot produce `:`. Synthetic csids no-op the `auth_required` broadcast.

### Tool authorship contract (F4+)

Tools subclass `Tool` and declare:

- `Config: type[BaseModel]` — per-tool config schema (per-category Config classes: `FilesystemConfig`, `ExecutionConfig`/`PythonExecConfig`, `WebConfig`).
- `Requires: tuple[type[BaseModel], ...]` — opts into the shared `cross_configs` view.
- `__init__(config, cross_configs=None, agent_name=None)`.
- `execute(**kwargs) -> str`.
- `truncation_direction: Literal["head", "tail"]` — which end the context-budget governor preserves when it truncates this tool's result. Default `"head"` (prose/pages/files); execution tools that return shell output (`shell`, `python_exec`, `shell_session_send`) override to `"tail"` so the `[exit code: N]` suffix + stderr tail survive. See "Context-budget governor" below.

The two-clause `try/except` envelope (catch `ConstraintError` → `[error] [constraint] {e}`, catch other exceptions → `[error] {e}`) IS the authorship contract. `ConstraintError` lives at `the_one.tools.base` (canonical) for that reason.

**Context-budget governor (M16 F08 L01 / DD1).** `Agent._execute_tool` is the single chokepoint where EVERY `ToolResult.content` — from any tool — is bounded before it enters the conversation, so no one tool result can consume a disproportionate share of the model's context window (the F07 context-poison theme). The pure helper `the_one/agent/_governor.py::govern_tool_content(content, max_context_tokens, *, fraction, floor, ceiling, direction, bytes_per_token)` computes `budget = clamp(int(fraction * max_context_tokens * bytes_per_token), floor, ceiling)` and slices on a byte boundary (`decode(errors="replace")`), appending (head) / prepending (tail) a truncation marker that sits OUTSIDE the budget. It governs the normal `output` and the timeout/generic-except error strings; the MCP `<auth required>` sentinel is NOT governed. `max_context_tokens` ≤0/None/absurd floors to 128k. Defaults — fraction 1/8, floor 8 KB, ceiling 256 KB — are env-overridable (`THE_ONE_TOOL_RESULT_BUDGET_FRACTION` / `_FLOOR` / `_CEILING`; see `.env.example`). This RETIRED the per-tool LLM-facing caps (the web text cap; the model-sized role of `output_cap_bytes`); the transport/OOM safety caps (`response_size_cap_bytes` 1 MB streaming abort, `read_size_cap_bytes` file-size guard, `output_cap_bytes` as a transport ceiling) remain — a different axis (what the process buffers/reads vs. what reaches the model).

**Tool policy resolver** (`the_one/tools/resolver.py`) composes tool-level config with agent-level overrides per per-key marker semantics on the tool's `Config` schema:

- `Annotated[type, Narrow]` — agent override must not widen the value (bool, int/float lower-cap, list/tuple subset). Other types raise `NotImplementedError`.
- `Annotated[type, NarrowPrefix]` — `list[str]` of paths is narrowing iff every agent entry is descendant-of (or equal to) at least one tool entry. Used by `FilesystemConfig.path_allowlist`.
- `Annotated[type, NarrowSuperset]` — `list[T]` is narrowing iff every tool entry is also in the agent value (agent ⊇ tool — agent adds restrictions). Used by `FilesystemConfig.path_denylist`. Membership uses raw `==`; canonicalisation is consumer-side.
- `Annotated[type, Substitute]` — agent override replaces (no comparison).
- Unmarked field — agent override raises `ValueError("... no Narrow/Substitute marker ...")`.

Session-bound freshness: mid-session operator updates apply at the next `AgentFactory.create()`.

**Cross-Config dispatch**: tools declaring `Requires` receive a per-`get_tools()`-call shared `cross_configs: dict[type[BaseModel], BaseModel]` view. Configs are `frozen=True` so one tool cannot mutate the view to corrupt another's read. Both `BuiltinToolProvider` and tests inject via the same dict (e.g. fake `SearchBackend` for tests).

### Constraint surface

Active constraint types after F5:

| Type | Config field(s) | Marker(s) | Applies to |
|------|-----------------|-----------|------------|
| Path scope | `FilesystemConfig.path_allowlist`, `path_denylist` | `NarrowPrefix` + `NarrowSuperset` | 9 filesystem tools + cwd validation in 6 execution tools (cross-Config) + `download_file` destination |
| Read-size cap | `FilesystemConfig.read_size_cap_bytes`, `allow_binary_files` | `Narrow` × 2 | `read_file`, `grep`, indirect via `edit_file` pre-read |
| Output cap (transport ceiling) | `ExecutionConfig.output_cap_bytes` | `Narrow` | 6 execution tools (combined stdout+stderr, tail-preserving). M16 F08 L01: reclassified from a model-sized LLM cap to a transport/safety ceiling — the context-budget governor now applies the model-derived LLM bound on top (tail-preserving for shell). |
| Timeout caps | `ExecutionConfig.timeout_seconds_default`, `timeout_seconds_max` | `Narrow` × 2 + `default <= max` model_validator | 6 execution tools |
| Command denylist | `ExecutionConfig.command_denylist` | `NarrowSuperset` | `shell`, `python_exec`, `shell_session_send` (per-call re-check). Substring match with trailing-space convention to avoid the `sudoku` false-positive class. |
| Sandbox network | `ExecutionConfig.sandbox_network_allowed` | `Narrow` | `shell`, `python_exec` (deny-by-default; `True` opts the built-in tool into network access inside the bwrap jail) |
| URL/host scope + SSRF | `WebConfig.*` (see below) | mixed | 3 web tools (`http_request`, `fetch_url`, `download_file`) |
| Search-engine selection | `WebSearchConfig.*` (see below) | none (operator-only) | `web_search` |

**`WebConfig.redirect_cap`** is `Field`-only — NO `Annotated` marker. Tool-level only; agent override raises `ValueError`.

**`web_search` engine registry (M16 F08 L02 — DD3 refinement).** `web_search` migrated off the shared `WebConfig` onto its own `WebSearchConfig` (it never read `WebConfig`'s SSRF/transport fields — it consumes only the injected `SearchBackend`). `WebSearchConfig` carries the engine selector + per-engine connection fields, all operator-only (NO resolver marker — agents cannot pick the search engine or set keys):

| Field | Purpose |
|-------|---------|
| `search_backend` | Active engine: `duckduckgo` (keyless default) / `searxng` / `google_pse` / `brave` / `tavily`. Dropdown (`ui_hint:"dropdown"`). |
| `searxng_base_url` | SearXNG instance base URL (JSON format must be enabled on the instance). |
| `google_pse_api_key` *(secret)* | Google Programmable Search Engine API key. |
| `google_pse_cse_id` | Google PSE engine id (the `cx` param). |
| `brave_api_key` *(secret)* | Brave Search API subscription token. |
| `tavily_api_key` *(secret)* | Tavily API key. |

The factory `build_search_backend(config, *, extra_allowed_hosts)` (`_search_backends.py`) maps `search_backend` to one of five `SearchBackend`-conformant classes (`DDGSearchBackend` / `SearxngSearchBackend` / `GooglePSESearchBackend` / `BraveSearchBackend` / `TavilySearchBackend`). Each owns a **per-call** `httpx.AsyncClient(transport=SSRFGuardedTransport(extra_allowed_hosts=…))` — even DDG respects the SSRF policy (read off the resolved shared `WebConfig`). Default DDG for unset/unknown names; a **selected-but-unconfigured keyed engine still constructs and raises `SearchUnavailableError` at call time** (no silent DDG fallback — that would hide misconfig).

**Honest-empty contract (M16 F08 L02 — HIGH-3).** Backends raise typed errors (`SearchError` base → `SearchBlockedError` / `SearchUnavailableError`) on blocked/throttled/parse-failure/misconfig, and return `[]` ONLY for a genuinely-empty result. `WebSearchTool.execute` surfaces the raised error honestly as `[error] web_search ({backend}) blocked/throttled|unavailable: …` and keeps `[]` → "No results found." — so the model stops mistaking a broken search for "the web has nothing" and guessing URLs. DDG's genuine-empty is detected via its positive `no-results` HTML marker (Option B); a 200 with neither `result__a` nor `no-results` is treated as blocked. Backends NEVER log secret values.

> **Secret-at-rest (M16 F08 L03 — landed)**: the secret fields are MARKED (`json_schema_extra={"ui_hint":"password","secret":true}`) on `WebSearchConfig`; the encrypted-at-rest `config`+`secrets` split now lands them in the `tool_configs.secrets` column (schema v32) — see "Tool config secrets storage" above. The flight batch-commits at the end (no intermediate release), so plaintext keys never ship.

**Admin config UI (M16 F08 L04 — landed).** Administration → Tools → `web_search` renders the engine registry schema-driven. The operator picks an engine from the `search_backend` **dropdown** (`ui_hint:"dropdown"` on a string `Literal` — `renderField` in `tools-form-helpers.js` grew a string-enum `<select>` branch alongside the pre-existing integer-dropdown branch so the picker renders as a real `<select>` rather than a free-text box) and sees **only that engine's** connection fields. Per-engine visibility is driven by a generic `show_if` mechanism: each per-engine field carries `json_schema_extra={"show_if":{"search_backend":"<engine>"}}`, and `tools-editor.js` `applyShowIf(container, properties)` hides any field whose controller value ≠ the `show_if` value (`is-hidden` + `aria-hidden="true"`), re-running on the controller's `change`. **Hidden rows stay in the DOM** (so `getFormSnapshot` still submits them — an entered key survives an engine switch; the leg-3 preserve-on-masked contract handles the masked round-trip). DuckDuckGo shows no per-engine fields. The three secret keys (`google_pse_api_key` / `brave_api_key` / `tavily_api_key`) render as **masked password inputs** with an `.api-key-eye` reveal toggle (ported from the provider editor; toggles `type` password↔text + swaps `aria-label`). On reload, GET returns the leg-3 mask (`***...{tail4}`); leaving it untouched preserves the stored key. The `show_if` mechanism is generic (reads the schema, not hardcoded to `search_backend`) — any field controlled by any sibling participates. No Studio change: all `WebSearchConfig` fields are markerless `str` and so never render in agent mode (`renderField` early-returns `''` for non-boolean markerless fields in agent mode).

**SSRF "no full-disable" mission invariant**: `WebConfig` has no `disable_ssrf` / `ssrf_disabled` / `disable_ssrf_protection` field. SSRF protection is always-on; operators reaching internal hosts list them in `extra_allowed_hosts` (host-by-host opt-in), not a global kill-switch. The invariant is encoded by the field's ABSENCE — no enforcement code needed. Sweep: `grep -rn 'disable_ssrf\|ssrf_disabled' the_one/` must return zero source hits (only docs allowed).

**Two-layer SSRF enforcement**: (1) `_url_check(url, cfg)` at the tool boundary refuses non-`http(s)` schemes, enforces host allowlist/denylist. (2) `SSRFGuardedTransport` resolves DNS once and pins the connect target to the resolved IP, refusing loopback / link-local / RFC1918 / cloud-metadata / IPv6 ULA + ULL by default. **IP-literal hosts** are also gated by `_is_ssrf_blocked(host)` in the transport's IP-literal short-circuit branch (gated BEFORE `super().handle_async_request`). `extra_allowed_hosts` is the operator override for both paths. DNS-rebind protection: the resolve-then-pin strategy means the second-call rebind to a private IP never reaches the connect layer.

### Subprocess environment invariant

The hardcoded 8-key allowlist is defined as `_ENV_ALLOWLIST` in `the_one/platform/env.py`
and materialized by `_build_subprocess_env()`:

```
PATH, HOME, USER, LOGNAME, LANG, LC_ALL, TERM, TZ
```

Call sites (M14 F1+F2 update):
- `the_one/tools/shell.py` (ShellTool) — calls `_build_subprocess_env()` and passes the
  filtered env to `run_shell()` / the sandbox seam.
- `the_one/tools/python_exec.py` (PythonExecTool) — same pattern.
- `the_one/platform/pty.py::UnixPtySession` — calls `_build_subprocess_env()` in the
  parent (before `pty.fork()`) and passes the filtered env through
  `get_sandbox_backend().prepare_spawn(...)` — now wired through the sandbox seam (M14 F2),
  identical in structure to the one-shot built-in tools.

The platform layer (`run_shell`, `run_python`) receives the already-filtered env from the
tool layer — it does NOT re-build the allowlist internally.

**Fork-safety convention (PTY spawn path)** — `pty.fork()` is a raw POSIX fork. Between
`fork()` and the subsequent `execvp()` (the OS-level exec that replaces the child image),
only **async-signal-safe** operations are permitted in the child process. In practice:
no Python-level memory allocation, no logging, no lock acquisition, no `import`, and no
calls into the asyncio event loop. Python's allocator, the GIL, and any library mutexes
are in an undefined state in the child immediately after fork — calling them before exec
can deadlock or corrupt state silently. Footgun: if the parent process is **multi-threaded**
at `fork()` time (e.g. asyncio + a thread-pool executor), the child inherits only the
forking thread's stack while all other threads' locks remain held, making even basic
C-library calls unsafe before exec. The PTY spawn path is safe today because exec follows
the fork immediately; any future change that adds work between `fork()` and `exec()` in
`UnixPtySession._start()` must audit for async-signal-safety.

**NOT operator-configurable** — part of the F4 trust contract: the agent has no path to read or carry through host secrets via subprocess inheritance.

### Threat model — trip-wire, not fence

The `command_denylist` is a **trip-wire** catching obvious-stupid (agent typos, prompt-injection telegraphs in plaintext, operator-specific dangerous patterns). It is **NOT a fence** against adversarial agents — `bash -c "$(echo c3VkbyB3aG9hbWk= | base64 -d)"` is not in the denylist. The trip-wire produces a clean small-model-readable error rather than a destructive side-effect; bypasses are accepted because the operator-trust threat model assumes the agent is not actively adversarial. Operators wanting fence-grade isolation run the agent in a sandbox (container, VM, namespace).

False-positive surface is also accepted: `echo "do not run sudo"` is refused; workaround documented in `shell_session_send`'s tool description.

### PTY session lifecycle

- **Addressing** (Decision 4): per-explicit-handle. `shell_session_start` returns a `pty-{12hex}` token; the agent passes it back into `_send`/`_close`. Four discrete tools (`_start`, `_send`, `_close`, `_list`), not an action-enum.
- **Per-agent isolation**: registry keyed on `(agent_name, session_id)`. Cross-agent `_send`/`_close` returns the SAME error shape as a non-existent session ("not owned by this agent or does not exist") — agents cannot probe for other agents' session ids.
- **Idle reap**: single lazy asyncio reaper; wakes every 30s; closes sessions where `monotonic() - last_activity > pty_session_idle_ttl_seconds` (default 5min, `Narrow`). Registered with FastAPI lifespan for clean drain on shutdown.
- **Max concurrent**: `count_for_agent < max_concurrent_sessions` (default 5, `Narrow`). The L6 spec accepts a documented race on concurrent `_start` calls; the registry's internal lock has so far serialised correctly under single-process asyncio.
- **Idle-mark prompt detection**: `_read_until_idle` blocks until the master_fd has been silent for 100ms (2s hard cap). Robust against inconsistent shell prompts (zsh themes, sudo prompts).
- **Per-call denylist re-check** (Decision 11): every `_send` runs `_command_check(input, exec_cfg)` BEFORE forwarding. Agents cannot pre-stage a denylisted command behind an open session.

### Singleton aiosqlite connection model

`the_one/db/connection.py` holds a single module-level `aiosqlite.Connection` (`_connection`). The connection is lazy — created on the first `get_connection()` call — with WAL journal mode and foreign-key enforcement applied immediately after open. All repositories and schema helpers obtain the connection via `get_connection()`; there is no connection-pool layer. The lifespan handler calls `close_connection()` on shutdown, which closes and nulls the module-level reference. Tests that need a clean state re-call `init_db()` on an isolated `tmp_path` data dir.

### Knowledge storage (Flight 2, Legs 1-4)

`kb_chunks` (v40) holds one row per extracted text chunk (`item_id`, `kb_id`, `seq`, `text`, `char_start`, `char_end`; `AUTOINCREMENT` ids, never recycled; `UNIQUE(item_id, seq)`). `kb_chunks_fts` is an external-content FTS5 index over it (`content='kb_chunks', content_rowid='id', tokenize='porter unicode61'`) — external-content means the FTS shadow table stores no text of its own and must be kept in sync by hand; SQLite's FK cascade reaches `kb_chunks` on a `kb_items`/`knowledge_bases` delete but does **not** reach `kb_chunks_fts`.

- **The repository is the only writer of `kb_chunks_fts`.** `KBChunkRepository` (`the_one/db/repositories.py`) owns every FTS write — insert, delete, rebuild, integrity-check — through the module-level `_fts_delete_rows(conn, rows)` helper (the sole site issuing the `INSERT INTO kb_chunks_fts(kb_chunks_fts, rowid, text) VALUES ('delete', ?, ?)` command) and `replace_item_chunks`'s own `INSERT INTO kb_chunks_fts(rowid, text) VALUES (?, ?)`. A raw `DELETE FROM kb_items` or `DELETE FROM knowledge_bases` issued anywhere outside `KnowledgeBaseRepository.delete` / `KBItemRepository.delete` is a defect — it desyncs the index (`check_fts()` starts returning `False`) because FK cascade silently removes the `kb_chunks` rows without their matching FTS deletes.
- **FTS delete needs the original text**: external-content FTS5 deletion requires the text that was indexed, not just the rowid, so every deleting path does `SELECT id, text FROM kb_chunks WHERE ...` **before** the matching `DELETE FROM kb_chunks` — never after. `KnowledgeBaseRepository.delete` and `KBItemRepository.delete` each do this select-then-FTS-delete step themselves, inside their own existing `write_transaction`, immediately before the row delete that FK-cascades the `kb_chunks` rows away.
- **No nesting**: `KnowledgeBaseRepository.delete` / `KBItemRepository.delete` never call into `KBChunkRepository`'s methods — each of those opens its own `write_transaction`, and `write_transaction` is not re-entrant (same-task re-entry raises `RuntimeError`, per `db-writes-hold-the-write-lock` above). They call the module-level `_fts_delete_rows` helper directly instead, composing the FTS sync into their own transaction rather than nesting one guard inside another.
- **`check_fts()` must use the two-argument integrity-check form** — `INSERT INTO kb_chunks_fts(kb_chunks_fts, rank) VALUES ('integrity-check', 1)` — which, for an external-content table, verifies the index against the content table. The one-argument form (`VALUES ('integrity-check')`) checks only the index's own internal structure and reports clean on an external-content desync; three bypass scenarios were verified against it during Leg 2's design review before this was corrected.
- **`bm25(kb_chunks_fts)` and `WHERE kb_chunks_fts MATCH ?` name the UNALIASED table**, even when the `FROM` clause aliases it (`kb_chunks_fts f`) — `bm25(f)` / `f MATCH ...` raise `no such column: f`. `search_keyword`'s KB-scoping is therefore a `JOIN kb_chunks c ON c.id = f.rowid ... AND c.kb_id = ?`, not a predicate on the FTS table itself, because the FTS table carries no `kb_id` column.
- **`bm25()` is lower-is-better (negative)** — `search_keyword(kb_id, query, k) -> list[tuple[int, float]]` returns the raw score as-is, ordered ascending (best first); callers (the Leg 4 benchmark, the later fusion flight) must not assume higher-is-better.
- **Query quoting**: `search_keyword` splits its query on whitespace and quotes each term individually (`'"' + term.replace('"', '""') + '"'`), joined by spaces (FTS5 implicit AND) — this neutralises FTS5 operator characters (`"`, `*`, `(`, `-`, `OR`, `NEAR`) so a query containing them is matched as plain terms rather than raising or being misparsed as a query-language expression. An empty/whitespace-only query returns `[]` without touching the DB.
- **`ChunkRecord`** (`the_one/db/_kb_types.py`, frozen dataclass: `seq`, `text`, `char_start`, `char_end`) is the shape crossing from the chunker (Leg 3) into `KBChunkRepository.replace_item_chunks(item_id, kb_id, chunks)` — deliberately a plain dataclass, not Pydantic, since it validates nothing itself (`UNIQUE(item_id, seq)` and `NOT NULL` enforce at insert time).
- **`the-one doctor`'s `fts5` gate** (`_probe_fts5`, unconditional per DD-11 — see "Diagnostics" above) proves FTS5 support end-to-end (in-memory `CREATE VIRTUAL TABLE ... USING fts5`, insert, `MATCH`) independently of the `kb_chunks_fts` schema — it is a platform/SQLite-build capability check, not a check of this repository's sync logic (that is `tests/test_kb_chunks.py`'s job).

**The vector-store seam** (Leg 4, DD-3/DD-4/DD-10/DD-13; `usearch`-only since Leg 6, DD-9): `the_one/vectors/_store.py` holds a `runtime_checkable` Protocol (`VectorStore`: `open`/`upsert`/`delete`/`delete_kb`/`query`/`count`/`flush`/`close`, plus `backend`/`dtype`/`dim`; structural satisfaction — no inheritance) and `quantize_int8(vectors) -> np.ndarray` (`np.clip(np.rint(v * 127), -127, 127).astype(np.int8)` — the cast is load-bearing: `usearch.Index.add` silently re-scales an un-cast float array a second time instead of raising, corrupting the stored vector). Every id crossing the seam is a `kb_chunks.id` value (Leg 1's `AUTOINCREMENT`, never recycled); no chunk text or metadata ever crosses. A candidate second backend (loadable-SQLite-extension-backed, `sqlite-vec`) was benchmarked in Legs 4-5 and removed from the closure in Leg 6 after the operator's DD-9 decision — the seam (Protocol, dispatcher shape, settings shape) is kept generic for a future second backend, but only `UsearchStore` exists today.

- **`upsert` means delete-then-insert.** `usearch.Index.add` raises on a duplicate key (no native upsert).
- **Write ordering (DD-3)**: chunks + FTS commit first (Leg 2's repository), vectors land after via this seam; an item reaches `indexed` only once the vectors have **flushed** — see the flush rule below. `UsearchStore` cannot save its HNSW index on every `upsert` at scale (a save is O(N)), so `upsert` only mutates the in-memory index and marks it dirty — `flush(kb_id)` is what calls the atomic save (below) and is what "vectors landed" means. An `upsert` observed through a FRESH `UsearchStore` instance without an intervening `flush` does not see the new vectors — documented behaviour, not a bug (empirically measured per-`flush` save cost at Leg 4's test sizes, dim 512: ~3 ms at 50 vectors, ~7.5 ms at 1,000, ~6 ms at 5,000 — sidecar bytes scale linearly, ~1.17 KB/vector at f16; Leg 5's benchmark measures the corpus-ceiling number).
- **The store acquires `the_one/db/_write_lock.py`'s write lock itself, for every one of its own writes — a caller must never wrap a store call inside its own `write_transaction`** (not re-entrant; raises `RuntimeError` on same-task re-entry, per `db-writes-hold-the-write-lock`). This is why the write ordering above is always two transactions, never one. `UsearchStore.upsert`/`.delete` enter-and-exit an empty `write_transaction` block purely to enforce this no-nesting contract (the actual mutation is in-memory only, under the store's own per-KB `asyncio.Lock`) — a deliberate departure from Leg 4's literal per-method guidance, needed to satisfy the acceptance criterion that EVERY store method (not only the SQL-writing ones) refuses nesting.
- **`UsearchStore`** (`the_one/vectors/usearch_store.py`) is a per-KB sidecar: one HNSW index file at `{data_dir}/vectors/{kb_id}.usearch` (`data_dir` resolved inside `open()`, never at construction — a `settings.data_dir` monkeypatch applied after construction but before `open()` is honoured), with a registry table `kb_vector_index(kb_id, path, count, generation, dtype, dim, updated_at)`. The registry table was store-owned (created inside `open()`) through Legs 4-5 while the backend choice was open; Leg 6 moved its DDL into the v41 migration block (DD-9 won it), and `open()` issues no DDL at all today. Per-KB state (`_KbIndex`: the loaded `Index | None`, an `asyncio.Lock`, `dirty`/`stale` flags) is get-or-created SYNCHRONOUSLY via `dict.setdefault` — no `await` between the membership check and the insert — before anything ever awaits the per-KB lock; the lock cannot guard its own creation, so the synchronous `setdefault` is what makes two concurrent first-touches of the same `kb_id` land on the same lock instead of racing to create two independent ones.
- **Staleness** (Leg 4, hardened Leg 6): on load, a registry row whose sidecar file is missing, unreadable (`_ensure_loaded` catches the base `Exception` around `Index.restore` — a corrupt sidecar raises `ValueError` on garbage/empty bytes or `RuntimeError` on a truncated file, three different types for one condition), whose restored index length disagrees with the row's `count`, or whose `dtype`/`dim` disagree with the store's configuration marks the KB stale and raises `VectorStoreStaleError` (chained `from` the original exception when applicable) on every subsequent read/write except `rebuild_from` and `delete_kb`; `rebuild_from(kb_id, ids_and_vectors)` builds a fresh index from scratch, saves it, and clears the staleness.
- **Atomic sidecar save (Leg 6)**: `flush`/`rebuild_from` route through `_save_atomically` — save to a same-directory `.usearch.tmp` path, then `os.replace(tmp, path)` (atomic on POSIX and Windows; `Index.restore` never memory-maps, so nothing keeps the destination open), only THEN upsert the registry row. A failure before the replace leaves the previous sidecar untouched, best-effort-removes the temp file, and leaves `entry.dirty` `True` so the next `flush`/`close()` retries. The sidecar-write and registry-write remain two separate steps (pre-existing caveat): a crash between them leaves the sidecar one generation ahead of the registry, which the staleness check above reports as stale — a fail-safe window, recoverable by `rebuild_from`, not a defect.
- **`delete_kb` is guard-first (Leg 6)**: the `write_transaction` that deletes the registry row runs BEFORE any in-memory or filesystem mutation — a caller who nests this call inside their own `write_transaction` gets the re-entry `RuntimeError` before anything has changed, not after the sidecar was already unlinked (the pre-Leg-6 ordering).
- **Dispatcher** (`the_one/vectors/__init__.py`): `get_vector_store()` is **async** (a documented departure from `create_pty_session`'s sync dispatch shape, since the backend choice is a DB record) and double-checks under an `asyncio.Lock` — the `get_embedding_backend()` shape widened to async. It reads `knowledge.vector_store` (absent → `usearch`/`f16` default, DD-9), calls the named `_build_store(settings, conn)` seam (one branch today; lazy-imports the backend module; the site AC-11's tests monkeypatch to inject a recording stub), `open()`s the store, and caches it — callers never call `open()` themselves. `_reset_for_test()` clears the cache.
- **`VectorStoreSettings`** (`the_one/knowledge/settings.py`): `backend: Literal["usearch"]`, `dtype: str` (validated against `("f16", "i8")` — `f16` is the DD-9 default), `dim`, `model_id`; stored under `knowledge.vector_store` (`VECTOR_STORE_KEY`). **Store-written, not operator-configurable** — `update_knowledge_settings`'s existing generic top-level-key guard already 422s a `vector_store` key in a `PUT` body (no dedicated message was added). Unlike `load_knowledge_settings`, `load_vector_store_settings` RAISES (never falls back) on an invalid stored record — a corrupt vector-store record is the one setting that must not silently default, because the wrong backend would read the wrong on-disk data with no error. `GET /api/knowledge-settings` surfaces it read-only under `"vector_store"`, alongside the pre-existing `notes` list.
- **Delete-route wiring**: `delete_knowledge_base` and `delete_kb_item` (`the_one/interfaces/web/api.py`) call `store.delete_kb(kb_id)` / `store.delete(kb_id, ids)` AFTER the repository transaction has committed, never inside it (the store acquires the write lock itself — nesting would raise). A store failure is logged (`logger.exception`) and swallowed; the route still returns 200 — the DB row is truth, and a stale vector row for a never-recycled id is harmless.
- **No native SQLite extension is loaded anywhere in the app** (Leg 6; see `SECURITY-MODEL.md`). `usearch` is an ordinary imported Python extension module, not a SQLite extension, and never touches the app's SQLite connection. The Leg 4 `sqlite-vec` backend, which did load a native SQLite extension (`enable_load_extension`), was removed in Leg 6.
- **An inert `kb_vectors` table can remain in a dev database** that opened the removed `sqlite-vec` backend between Leg 4 and Leg 6 (its `vec0` virtual table cannot be dropped without the extension loaded — `DROP TABLE` raises `OperationalError: no such module: vec0`). No release ever shipped this table; the v41 migration deliberately never touches it, and every other statement (including migrations) works fine with the table present and the extension absent.

**The embedding seam** (Leg 3, DD-1): `the_one/embeddings/` now holds a `runtime_checkable` Protocol (`EmbeddingBackend` in `_backend.py`: `model_id`, `dim`, `embed(texts) -> EmbedResult`, structural satisfaction — no inheritance), the production backend (`LocalStaticBackend` in `local.py`, wrapping the bundled `potion-retrieval-32M` model and carrying the two DD-5 offline-load guards `resolve_model_dir()`/`force_hf_offline()` that used to live only in the doctor probe), and a process-wide singleton (`get_embedding_backend()` / `warm_up()` / `_reset_for_test()` in `__init__.py`, double-checked-locked so two concurrent first callers still load once). The test-only second implementation, `StubEmbeddingBackend` (`tests/_embedding_stub.py`, hash-seeded deterministic unit vectors), is what every seam-consumer's unit test runs against — real loads stay confined to `tests/test_doctor_embedding_model.py::TestRealLoad` (two per run) and `tests/test_embeddings.py`'s own singleton tests (which stub `LocalStaticBackend.load`, never touching model2vec for real). A global `tests/conftest.py` autouse fixture (`_stub_embedding_backend_by_default`) patches `LocalStaticBackend.load` to a stub for every OTHER test module, since `create_knowledge_base` now fires `warm_up()` as a background task on every call.

**Knowledge settings** (Leg 3, DD-6): two `app_metadata` JSON records — `knowledge.embedding` and `knowledge.chunking` (`the_one/knowledge/settings.py`'s `EMBEDDING_KEY`/`CHUNKING_KEY`) — read with defaults applied (`load_knowledge_settings`) and written as two independent transactions (`save_knowledge_settings`). `EmbeddingSettings` uses plain `str`/`int` fields with `field_validator`s (not `Literal`s — a `Literal` mismatch can't carry the DD-2 amendment message into the 422 response) rejecting anything but the one bundled `(backend, model_id, dim)` combination. `ChunkingSettings` bounds `size_chars` (200–2000) and `overlap_chars` (`<= size_chars // 2`). Routes: `GET`/`PUT /api/knowledge-settings` in `api.py`, merge-then-revalidate on `PUT` (the `update_knowledge_base` precedent), 422 on an unknown top-level key or a failed validator.

**The chunker** (Leg 3, DD-7): `the_one/knowledge/chunking.py::chunk_text(text, *, size_chars=1000, overlap_chars=150) -> list[ChunkRecord]` is pure and deterministic, offsets into the original text (never a normalized copy — CRLF is handled via `\r?\n` regexes, not by rewriting `\r\n` to `\n`). One combined, sorted set of candidate break positions (paragraph/line/sentence) drives both window-end selection (latest boundary at or before the size cap) and the next window's overlap start (earliest boundary at or after `end - overlap_chars`) — see the module docstring's "Overlap direction note" for why the leg spec's literal "latest boundary at or before" phrasing for the overlap step does not itself bound overlap above by `overlap_chars` (verified with concrete numbers) and was corrected during implementation.

### Web-session idle reaper

The `_sessions: dict[str, Session]` in `the_one/interfaces/web/app.py` is the warm in-memory cache for active UI chat sessions. Each entry pins a live `Agent` (LLM HTTP client, full message history). A background idle reaper (F05 L01, Mission 12 Flight 05) bounds memory growth in long-lived processes.

- **Reaper**: `_web_session_reap_loop()` / `_reap_web_sessions_once()` in `app.py`. Wakes every `max(30, TTL // 10)` seconds. Evicts sessions where `not subscribers_for(sid)` AND `not is_session_processing(sid)` AND `(monotonic() - last_activity) > TTL`.
- **Safety invariant**: sessions with ≥1 live WS subscriber (open chat tab) are NEVER reaped, regardless of idle age. Sessions mid-processing (tool calls up to 120s) are protected by the `is_session_processing` guard.
- **Teardown**: eviction calls `await agent.aclose()` outside the `_sessions_lock` (two-phase pattern — snapshot+pop under lock, close after release). `Agent.aclose()` delegates to `LLMProvider.aclose()`; Anthropic/OpenAI providers release their persistent `httpx` client; Ollama (per-request client) is a no-op.
- **Rehydration**: evicted sessions rehydrate losslessly from `chat_sessions` DB on next join (the DB is the durable backing store; the in-memory dict is a warm cache).
- **TTL**: `THE_ONE_WEB_SESSION_IDLE_TTL_SECONDS` env var, read at call time via `os.environ.get`, int-parse with fallback to 1800 (30 min). See `.env.example`.
- **Lifespan**: reaper started just after `start_periodic_sweep()` on startup; `_web_session_reaper_shutdown_drain()` called on shutdown after in-flight task drains, before PTY registry drain.

### Windows PTY backend (M15 F3)

`WindowsPtySession` (`the_one/platform/pty_windows.py`) is the Windows concrete
implementation of `PtySession`. It spawns `cmd.exe` via `pywinpty`'s `PtyProcess`
(ConPTY-backed, Windows 10 1809+ / Server 2019+). The platform dependency is
`pywinpty>=2.0; sys_platform == "win32"` — installed only on Windows via the env
marker in `pyproject.toml`.

**Split-module structure.** The PTY subsystem is split across three files:
- `platform/pty.py` — platform-neutral ABC (`PtySession`) + `create_pty_session()`
  factory dispatcher. No POSIX-only stdlib at module scope; imports on every OS.
- `platform/pty_unix.py` — `UnixPtySession` (POSIX concrete backend). Never imported
  on Windows.
- `platform/pty_windows.py` — `WindowsPtySession` (Windows/ConPTY concrete backend).
  Never imported on Linux or macOS (the factory's `os.name == "nt"` guard keeps it out
  of the Linux import cascade). The top-level `import winpty` is therefore safe.

**Socket-timeout idle-read mechanism (ConPTY-specific).** The obvious approach
(`proc.read()` or setting `read_blocking=False`) does NOT work for idle detection.
`PtyProcess.read()` performs a blocking `fileobj.recv()` fed by an internal daemon
thread; the `read_blocking`/`PYWINPTY_BLOCK` flag is captured by that thread's closure
at construction time — changing it after spawn is a **no-op**.

**WARNING:** do NOT call `proc.read_blocking = False` (or `proc.read_blocking = True`)
after `PtyProcess.spawn` — the thread has already captured the flag and will not observe
the change. A future maintainer who sees `read_blocking` in the pywinpty API and tries
to use it for idle detection will introduce a silent regression.

The correct approach (used by `_read_until_idle_blocking`): call
`proc.fileobj.settimeout(idle_window)` then `proc.fileobj.recv(_READ_CHUNK)` directly
(raw bytes, bypassing `proc.read()`). Catch `socket.timeout` as the "no data this
window" signal; catch empty `recv` or `EOFError` as EOF.

**`_WINDOWS_ENV_ALLOWLIST` in `platform/env.py`.** In addition to the POSIX 8-key
`_ENV_ALLOWLIST` (`PATH`, `HOME`, `USER`, etc.), `_build_subprocess_env` unions in
`_WINDOWS_ENV_ALLOWLIST` on `os.name == "nt"`:
`SystemRoot`, `PATHEXT`, `COMSPEC`, `TEMP`, `TMP`, `USERPROFILE`, `USERNAME`.
These are non-secret OS essentials that `cmd.exe` requires to function correctly.
`_ENV_ALLOWLIST` is NOT modified — `test_execution_helpers.py:273` pins it to the exact
8-key POSIX tuple and that pin must stay green.

**Curated Windows CI lane (DD7 revised — 2026-06-13).** The `windows-tests` lane
(`ci/tasks/windows-tests.yml`) runs a curated file list (~427 tests) on the Concourse
`platform: windows` worker rather than the full suite. The full suite remains the
source of truth on Linux; the Windows lane covers only the platform-divergent OS surface
(`test_platform_*`, `test_pty*`, `test_filesystem*`, `test_config*`,
`test_execution*`, `test_encryption`, `test_sandbox_factory/contract`,
`test_logging_config`). (Formerly the `windows` job in `.github/workflows/test.yml`,
now `workflow_dispatch`-only break-glass — see `ci/README.md`.)

**THE RULE:** if you add a new test file that exercises platform-divergent behavior
(PTY/shell, env allowlist, filesystem paths, encryption, execution, sandbox factory),
you MUST add it to the curated file list in `ci/tasks/windows-tests.yml` — or it will
NOT run on Windows. The maintenance comment in that task file states this rule inline.
Platform-agnostic test files (DB layer, provider/LLM/MCP-protocol) are
legitimately absent from the curated list.

**`_wrapped` is always `False` on Windows.** `UnixPtySession._wrapped` is set at
`start()` time from `spec.command == "bwrap"` and controls SIGKILL-fast vs
SIGTERM-grace teardown. On Windows, `PassthroughSandbox` never produces a `bwrap`
command, so `self._wrapped` is structurally `False` and the bwrap teardown branch is
never taken.

**Windows is unsandboxed (DD9).** The sandbox factory returns `PassthroughSandbox`
on non-Linux; `warn_if_isolation_unenforced` still fires for boxed profiles (the seam
contract is preserved). See `SECURITY-MODEL.md` "Windows: interactive tools run
unsandboxed" for the full model, including the Job Object lifecycle semantics.

### Origin allowlist

`OriginAllowlistMiddleware` gates state-mutating HTTP (POST/PUT/PATCH/DELETE) and WS upgrades by `Origin`/`Referer` against `THE_ONE_ORIGIN_ALLOWLIST`. Default: `http://127.0.0.1:*` and `http://localhost:*` — port-wildcard with strict-digits enforcement to reject `http://127.0.0.1.evil.com`-class confusion attacks. Missing-Origin requests pass through (server-to-server clients are NOT browser-originating). WS upgrades close at the ASGI layer (`{"type": "websocket.close", "code": 1008}`) BEFORE the route handler can `accept()` — `Depends()` runs post-`accept()` and cannot do this. Policy: `SECURITY-MODEL.md`.

### Continue Signal

A virtual tool (`CONTINUE_SCHEMA`, defined inline in `core.py`) that the LLM calls to indicate it needs another iteration. Not a real tool — the agent loop intercepts it and loops.

**Capability gate**: `Agent.step()` consults `LLMProvider.supports_tools()` once per turn. When tools are unsupported (e.g. Ollama Gemma — `/api/show` capabilities lack `"tools"`), the wire `tools=` array stays empty (Ollama 400s if a tools array is offered to a non-tool model). M16 F03 L08C (#105): the degraded path is **chat-only** — the system prompt is replaced with a tool-free `CHAT_ONLY_PROMPT` (no catalog, no `tool_code` format spec, no continue-tool semantics) on an ephemeral request copy (self.messages is NOT mutated). Recovery is also gated OFF at the provider level: `OllamaProvider.complete()` and `.stream()` gate `_recover_into_tool_calls` on `supports_tools()`, so a spontaneously-emitted `tool_code` fence from a non-tool model passes through verbatim as assistant text instead of being parsed/stripped/dispatched. The model converses naturally; it never runs a tool. Studio surfaces the degraded model via the red `no tools` chip on the model selector. (Prior approach — direct tool protocol injection via `degraded_tools.build_degraded_tool_prompt` — was trialled as 08A and found unreliable for 4B models; retired with `the_one/agent/degraded_tools.py` in 08C.)

**Degraded redundant-call backstop**: M16 F03 L09 (#105): a degraded model (e.g. gemma3:4b) can get *stuck* — re-emitting a tool call whose result it already has, then terminating with an empty message (no closing answer). `_run_iterations` keeps a turn-local executed-map keyed on `(name, canonical-json(raw args)) → (result content, is_error)`, populated only after a successful, non-paused dispatch. On the degraded path each response's `tool_calls` are partitioned into new vs already-executed; **only new calls dispatch** (the redundant re-emission is dropped). When *all* calls are redundant: if the response has no text, the empty terminal assistant message is **replaced in-place** (not appended) with a synthesized closing surfacing the prior result(s) — so persisted history carries no empty message with orphaned `tool_calls`; if the response *does* have text, that text is the answer and its leftover undispatched `tool_calls` are cleared. The backstop is **gated on `not supports_tools`** — the capable path is byte-identical to before (a capable model may legitimately re-poll changing state, e.g. `shell("date")`). The auth-pause/`_deferred_tool_calls` flow is untouched (the map records only after a non-paused dispatch, so a paused call is never treated as redundant on resume).

### Model capability surface

`LLMProvider.supports_tools()` is async, default `True` for cloud providers (OpenAI, Anthropic, mock). `OllamaProvider` overrides via `ollama_api.get_model_capabilities(base_url, model)`:

- Fetches `/api/show`, reads the `capabilities` array.
- Caches per `(base_url, model)` with 5-minute TTL.
- Returns `frozenset[str] | None`. `None` means "couldn't determine" — the agent treats that as `True` (trust the provider; surface errors via the 400-body diagnostic).

`GET /api/providers/{id}/models` async-gathers per-model capabilities for Ollama providers. Failures are non-fatal: a single capability fetch failing degrades to `null`, the rest of the list still renders.

The Pull Model dropdown is **deliberately NOT enriched** — `/api/tags` doesn't carry capabilities, so per-option chips would mean N×`/api/show` round-trips per dropdown open.

### Dev iteration

The app runs host-native at `localhost:8484` via `the-one serve` (started by `make up`). `serve` has no `--reload`, so source edits under `./the_one/` take effect on `make restart`. Tests run host-native against the repo `.venv` — `.venv/bin/python -m pytest ...` (or the `make test-*` chains) always see the latest test code.

### Diagnostics (`the-one doctor` / `the_one/diagnostics.py`)

`run_doctor(out=None) -> int` (`the_one/diagnostics.py`) is the frozen-runtime spawn diagnostic (M15 F5, extended by M24 F01 with vector-store/embedding probes, and by Flight 2 Leg 2 with `fts5`; the vector-store side narrowed from two probes to one in Leg 6, DD-9). It builds the real child-spawn env via `_build_subprocess_env()`, runs a fixed list of probes, and prints one `  {name}: {status} — {detail}` line per probe (`status` is `OK`/`FAIL`), followed by an advisory `runtimes:` block from `detect_runtimes()`, then a `RESULT: PASS`/`RESULT: FAIL` line. Returns `0` only when every gate's `ok` is `True`; `1` otherwise. `out` defaults to `sys.stdout`; tests pass an `io.StringIO()`.

**Consumers of the exit code + stdout** — the report format is a contract, not incidental logging:
- `the_one/main.py`'s `cli_entry()` `doctor` branch: `sys.exit(run_doctor())`.
- `tests/test_doctor.py`: asserts `code == 0`/`!= 0` and greps specific `"{name}: OK"`/`"{name}: FAIL"` substrings out of the captured stream.
- `.github/workflows/windows-installer.yml` and `ci/tasks/windows-installer-build.yml`: both run the frozen `the-one.exe doctor`, capture stdout to a file, and `grep -q`/PowerShell-match the exact same per-gate `"{name}: OK"` strings (`child spawn`, `desktop shell`, `usearch`, `fts5`, `embedding model`) plus `RESULT: PASS`. Renaming a probe's `name` breaks these greps silently — they are not exercised by `make test-unit`.

**The eight gates**, in the order `run_doctor` runs and prints them:

| Probe | Function | Frozen-only? |
|---|---|---|
| `child spawn` | `_probe_child_spawn` | No — unconditional |
| `python interpreter` | `_probe_interpreter` | No — unconditional |
| `desktop shell` | `_probe_desktop_shell` | Yes |
| `llm providers` | `_probe_llm_providers` | Yes |
| `model catalog` | `_probe_model_catalog` | Yes |
| `usearch` | `_probe_usearch` | Yes |
| `fts5` | `_probe_fts5` | No — unconditional |
| `embedding model` | `_probe_embedding_model` (via `LocalStaticBackend`) | No — unconditional |

Frozen-only gates downgrade a failure to an informational `ok=True` line when `is_frozen()` is False (a dev host may legitimately lack an optional extra, or native extension import/load behaviour may vary by build); they still fail the build when frozen. The skip detail's shape varies by probe: `_vector_probe_outcome` (used by `_probe_usearch`) uses an em-dash form, `f"skipped — {reason}"`; `_probe_desktop_shell`, `_probe_llm_providers`, and `_probe_model_catalog` instead use a parenthesized form — `"skipped (gui extra not installed)"`, `f"skipped (extras not installed in dev): {detail}"`, and `f"skipped (seed did not resolve {model} on this host)"` respectively. `child spawn`, `python interpreter`, `fts5`, and `embedding model` gate unconditionally — a failure fails `run_doctor` on every host, dev included (`fts5` per DD-11: FTS5 is a mission constraint in every build, not an optional extra like the vector-store gate). Runtime-detection lines (`detect_runtimes`) are separate from the eight gates and never fail the run — missing `node`/`uv`/etc. is advisory, not a gate.

**Probe contract**: every `_probe_*` function returns a `ProbeResult(name, ok, detail)` dataclass. Six of the eight wrap their body in a broad `except Exception` and report `ok=False` with the exception folded into `detail`, so they never raise (an escaping exception would take down `doctor` and both CI gates for reasons unrelated to the thing under test): `_probe_desktop_shell`, `_probe_llm_providers`, `_probe_model_catalog`, `_probe_usearch`, `_probe_fts5`, `_probe_embedding_model`. The other two catch narrowly and CAN propagate an unexpected exception out of `run_doctor`: `_probe_child_spawn` catches only `(OSError, subprocess.SubprocessError)`, and `_probe_interpreter` catches only `FrozenInterpreterError`. Per the `report-what-you-got` convention (see "Project Conventions" above), every probe must still assert a CONCRETE resolved value — a returned rowid, a returned index key, a vector's dimension and norm — never merely "no exception was raised"; a capability that silently degrades (an extension that loads but answers nothing) is exactly the failure class a bare try/except would miss.

**Frozen-only gating idiom — `_vector_probe_outcome(name, reason)`**: the shared helper the vector-store probe (`_probe_usearch`) routes every failure through (a second backend's probe, removed in Leg 6, used to share it too — the helper keeps its shape for a future second one). Frozen → `ProbeResult(name, False, reason)` (hard `FAIL`); not frozen → `ProbeResult(name, True, f"skipped — {reason}")`. The probe still always ATTEMPTS the real load-and-query round-trip regardless of frozen state — only the *failure* is downgraded, never the attempt — so a passing dev host is real signal, not a rubber stamp. It exists because native extension import/load behaviour genuinely varies across builds (e.g. numkong linkage — see `_numkong_extension_state()` below), so a dev-host failure there is not evidence of a packaging defect. **`_probe_embedding_model` deliberately does NOT use this helper** — `model2vec` is a base dependency and the bundled weights are package data present in every checkout, so an unfrozen failure IS a real defect (most usefully a missing package-data glob in a non-editable wheel install, which a frozen-only gate would never catch). `tests/test_doctor.py::TestEmbeddingProbeGating::test_does_not_use_the_frozen_only_helper` enforces this by `inspect.getsource`-scanning the probe function body for the string `_vector_probe_outcome` — a source-level regression guard, not a behavioral one.

**Offline invariant (embedding probe)**: as of Flight 2 Leg 3, the two DD-5 guards live in `the_one.embeddings.local.resolve_model_dir()` (called by `LocalStaticBackend.load()`), not in `diagnostics.py` — `_probe_embedding_model` constructs a FRESH `LocalStaticBackend` (never the process singleton `get_embedding_backend()`, so the offline test that monkeypatches `the_one.embeddings.local.EMBEDDING_MODEL_DIRNAME` can't race the singleton) and calls through the seam rather than around it. `resolve_model_dir()` resolves `importlib.resources.files("the_one.embeddings").joinpath("data", "potion-retrieval-32M")` and asserts `.is_dir()` (and that `model.safetensors` exists inside it) BEFORE ever importing `model2vec` — a missing packaged directory raises `EmbeddingModelMissingError` instead of falling through to `model2vec`'s `_resolve_folder` → `snapshot_download()` network fetch. `force_hf_offline()` then sets BOTH `os.environ["HF_HUB_OFFLINE"] = "1"` AND, if `huggingface_hub.constants` is already present in `sys.modules`, its bound `HF_HUB_OFFLINE` attribute directly — the constant is read once at `huggingface_hub` import time, so setting only the env var is too late for a process (like the pytest suite) where the package may already be imported. See the `probe-must-not-pass-by-download` convention. The probe's detail line now reads `f"{dim}-dim {native_dtype} model -> float32 seam, norm {norm:.4f}, truncated={n} (...)"` (ASCII `->`, not U+2192 — AC-15/build 606620 found the frozen Windows CI lane's piped stdout is cp1252, which can't encode the arrow character) — the model's native dtype AND the float32 seam it's upcast through, plus the DD-1 truncation count for the probe text; the norm check is `abs(norm - 1.0) > NORM_TOLERANCE` (1e-3) rather than a bare nonzero check, which also subsumes the old all-zeros failure mode.

**`numkong=` / `_numkong_extension_state()`**: `_usearch_acceleration()` reports `numkong=yes|no, simd=<kernel>` by reading `usearch.compiled.USES_NUMKONG` and calling `hardware_acceleration()`. When `numkong=no`, it appends `_numkong_extension_state()`'s own diagnosis, because `numkong=no` alone cannot distinguish two very different causes: (a) the `numkong._numkong` extension is present but fails to import HERE (e.g. a Windows `.pyd` whose dependent DLL can't resolve — `usearch/__init__.py` swallows exactly that with a bare `except ImportError: pass`, a real packaging defect), vs (b) the extension loads fine and this `usearch.compiled` binary simply was never linked against it (an upstream wheel property, unfixable by packaging). `numkong=no, simd=serial` on every published Windows `usearch` wheel (verified 2.16.0 through 2.26.2 — zero `nk_*` symbol references, no `_numkong*.pyd` import table entry, empty delay-import directory) is case (b): an upstream wheel property, not a packaging defect. `packaging/windows/the-one.spec`'s long "numkong / SIMD on Windows" comment block records the verification in full so a future maintainer doesn't re-run the search.

**`_peak_rss_bytes() -> tuple[int | None, str | None]`**: best-effort peak (not current) resident-set-size of this process, threaded into the embedding probe's detail line (DD-4 read path — no CI task measures memory, so the probe self-reporting is the only observability). POSIX: `resource.getrusage(resource.RUSAGE_SELF).ru_maxrss` — **KiB on Linux, bytes on macOS/BSD** (`sys.platform == "darwin"` branches the multiply-by-1024). Windows: `ctypes`-drives `K32GetProcessMemoryInfo` (falling back to `psapi.GetProcessMemoryInfo` if the kernel32 export is absent) into a hand-declared `_ProcessMemoryCounters` structure. **The HANDLE lesson**: `kernel32.GetCurrentProcess.restype` and `.argtypes` MUST be declared explicitly before the call — without an explicit `restype`, `GetCurrentProcess()`'s `-1` pseudo-handle is truncated by ctypes' default `c_int` return type and re-widened incorrectly on a 64-bit process, so the subsequent memory call receives an invalid handle and fails with `ERROR_INVALID_HANDLE` (verified on windows-worker). Returns `(None, reason)` on any failure — the reason is threaded into the probe's detail line so a Windows API failure is diagnosable from `doctor` stdout, never a bare "unavailable". Never raises.

**Packaging notes for a maintainer** (`packaging/windows/the-one.spec`):
- A Flight 1 native-loadable-extension collection lesson, from a vector-store candidate removed from the closure in Leg 6: `collect_data_files` unconditionally excludes every `importlib.machinery.all_suffixes()` pattern (`.so`/`.abi3.so`/`.cpython-311-*.so`, never `.dll`/`.dylib`), so it silently drops a native library that is data to the module graph (nothing imports it; it's opened by path at runtime) — an entry would appear to work on Windows/macOS while shipping nothing on Linux. Such a library needs `collect_dynamic_libs` with explicit `search_patterns` instead, routed into `binaries=` (not `datas=`) so both binary-dependency scanning and `upx_exclude` (consulted only for `EXTENSION`/`BINARY` typecodes, a dead no-op against `datas`) see it. No current spec entry needs this mechanism — `usearch.compiled`/`numkong._numkong` are ordinary importable extension modules PyInstaller's module graph collects unaided.
- The `potion-retrieval-32M` model directory IS correctly collected via `collect_data_files("the_one", includes=["embeddings/data/**/*"])` — the native-loadable-extension lesson above does NOT apply here, because every file in that directory is `.json`/`.safetensors`/`.md`, none of which are in `all_suffixes()`.
- `the_one.embeddings` needs an explicit `hiddenimports` entry even though `embedding_datas` ships its data correctly: nothing `import`s the package — it is reached only by NAME, as the string argument to `importlib.resources.files("the_one.embeddings")` in `_probe_embedding_model`, which PyInstaller's static analysis cannot see. Without the entry the package is tree-shaken out of the PYZ (`files()` raises `ModuleNotFoundError`) while its 62 MiB of weights sit in the bundle unreachable.
- `upx_exclude` carries usearch's/numkong's native artifacts plus the embedding closure's native payloads (four entries): `"compiled*"` (usearch), `"_numkong*"`, `"tokenizers*"`, `"_safetensors_rust*"` — UPX-packing a native/Rust extension is a known load-failure source; these entries are insurance against a future UPX install (no current CI toolchain provides UPX, so `upx=True` is a no-op today). `"vec0*"` (a removed vector-store candidate) and `"_hf_xet*"` (excluded from the closure entirely, squawk 0049) were dropped in Leg 6.
- `excludes = ["hf_xet"]` (added in the AC-15 build-606657 fix, M24 F02 L06): excluding `hf-xet` from the *dependency closure* (`[tool.uv] exclude-dependencies`) is not sufficient on its own — `huggingface_hub` still carries a guarded `import hf_xet`, so PyInstaller bundles the module whenever it happens to be importable in the BUILD environment, closure notwithstanding. The persistent-worker lesson: Concourse's Windows worker runs tasks uncontainerised, so `C:\Python311`'s site-packages survive across builds, and build 606657 shipped a stale `hf_xet` left over from before the closure change — the doctor gate (which never imports `hf_xet`) still passed, masking it. `ci/tasks/windows-installer-build.yml` now installs into a fresh per-build `venv` for the same reason: a persistent build env can equally hide a MISSING dependency, not just a stray extra one — proven out by AC-15 build 606698, where the now-fresh venv exposed a real `pip install -r <uv export>` failure (huggingface-hub's own wheel metadata still declares `hf-xet`, so pip's hash-checking mode refuses the whole install rather than skipping just that package) that the persistent env at build 606657 had been silently absorbing by leaving its own stale `hf_xet` copy in place; the fix there is `--no-deps` on that install step (`uv export` is already a complete closure — pip has nothing left to resolve) plus a `$LASTEXITCODE` check after it, since neither the venv nor `excludes` alone would have caught a wholesale install failure. `PyInstaller.excludes` is the belt to the closure's suspenders — it makes the bundle correct regardless of what else is sitting in the interpreter that runs the freeze.

**Test conventions** (see also the `autouse-fixture + dedicated-real-load-file` convention above): `tests/test_doctor.py` has a function-scoped `_stub_embedding_probe` fixture (`@pytest.fixture(autouse=True)`) that patches `diagnostics._probe_embedding_model` for every one of that file's 19 `run_doctor(` call sites, so `make test-unit` never pays for the 62 MiB load. The dedicated real load lives in `tests/test_doctor_embedding_model.py::TestRealLoad` and must never be skipped or mocked — it is the only host-side proof the bundled asset actually loads. Tests throughout both files assert on the emitted `detail` string (dimension, dtype, norm, byte size, `numkong=`), not bare `ok`, per `report-what-you-got` — a monkeypatch a probe's broad `except` would otherwise swallow silently would leave a test asserting nothing but `ok is True`. Because `sqlite3.Connection` is an immutable C type (its methods can't be monkeypatched away), `test_frozen_fail_when_enable_load_extension_is_absent` instead swaps the whole `diagnostics.sqlite3` MODULE reference for a `types.SimpleNamespace(Connection=type("Connection", (), {}))` stand-in. The Windows-branch pattern (`tests/test_doctor_embedding_model.py::TestPeakRssWindowsBranch`): monkeypatch `os.name = "nt"`, stub `ctypes.WinDLL` with `raising=False` (it doesn't exist on non-Windows `ctypes`) to return a fake `kernel32` object whose `GetCurrentProcess`/`K32GetProcessMemoryInfo` are recording callables, then assert `restype`/`argtypes` were declared on those callables BEFORE they're invoked — proving the production code fixes the HANDLE-truncation bug rather than merely returning a plausible number.

---

## Provider type extension checklist

Six layers must coordinate. Missing any one causes either silent rejection (validation) or runtime errors.

### Provider URL validation

`_is_safe_provider_url` (`interfaces/web/api.py`) enforces `https://` for non-localhost hosts on LLM provider `base_url`. Called at endpoint time from `create_provider`, `update_provider`, and `test_provider` — NOT a Pydantic validator (must run on the resolved `base_url` post-`model_copy`, after `__MASKED__` substitution). Two skip layers: (a) `_URL_VALIDATION_SKIPPED_TYPES = frozenset({"mock", "ollama"})` bypass entirely; (b) for the rest, `http://` is allowed only when host is `localhost`, `127.0.0.1`, `::1`, or `*.localdomain`. RFC1918 / link-local / `0.0.0.0` require `https://`.

### Checklist

1. **Pydantic `Literal`** — `db/models.py` `LLMProviderConfig.type`. Add the new value to the `Literal[...]` tuple, or `model_validate` rejects.
2. **`PROVIDER_TYPE_MAP`** — `llm/registry.py` (lifted from `agent/factory.py` in M19 F01 L02; consumed by the factory and the provider API branches). Add `"<type>": "<registry-name>"`, or the module-load assert (keys must equal `PROVIDER_TYPES`) fails at import.
3. **Registry `loaders`** — `llm/registry.py:_try_load_builtin`. Add the lazy-loader lambda, or `get_provider("<type>")` raises a misleading `ImportError("requires extra dependencies")`.
4. **SQLite `CHECK` constraint** — `db/schema.py` (table definition AND migration). The `llm_providers.CHECK (type IN (...))` clause hard-codes allowed values. Adding a new type requires a schema migration (see v6 for the pattern: `PRAGMA foreign_keys=OFF` + table rebuild). Without this, `INSERT` fails with `IntegrityError`.
5. **API gating / branches** — `interfaces/web/api.py`: type-specific gating in `create_provider`/`update_provider` (e.g. dev-mode gate for `mock`); branch in `test_provider`; branch in `list_provider_models`; inclusion/exclusion in `GET /api/providers/types`.
6. **Frontend** — `interfaces/web/static/js/areas/admin.js`: add `TYPE_DEFAULTS["<type>"]` (unconditional — needed for editing existing providers even if hidden from creation); add `<type>` to `KNOWN_BADGE_TYPES`; add `--badge-<type>` token in `tokens.css` + matching `.admin-provider-badge--<type>` rule in `admin.css`.
7. **`_init_provider_state(self, kwargs)`** (optional hook on `LLMProvider`) — when the new provider needs to capture configuration outside the base field set (e.g. OpenRouter's `app_url`/`app_name` analytics headers; Ollama's lazy `max_context_tokens` state).

---

> **Connector subsystem rebuilt (Mission 23 Flight 2).** This file previously
> carried a "Connector type extension checklist" and a "Connector subsystem"
> section (Mission 10 Flight 1 and its follow-on flights) documenting the
> pre-reset package's message-routing layer, ACL axes, manual peer-approval
> flows, slash commands, and worker-pool machinery — deleted wholesale in
> Mission 23 Flight 1. Flight 2 defined a new, minimal connector contract;
> see "Connector subsystem contract (Mission 23 Flight 2)" under "Subsystem
> contracts" above for the architecture index, and
> `the_one/connectors/README.md` for the full contract. No provider-type-style
> extension checklist applies here — adding a platform means implementing
> the `ConnectorPlugin`/`ConnectorClient` Protocols (see the README), not
> touching a fixed multi-file checklist the way an LLM provider type does.

## Streaming protocol

Provider-agnostic at the agent layer; per-provider native streaming sits behind `LLMProvider.stream(...)`. The base class supplies a default implementation that calls `complete()` and yields exactly one `StreamChunk(is_final=True, ...)`. Subclasses MAY override.

### `StreamChunk` contract

```python
@dataclass
class StreamChunk:
    content: str = ""               # NEW tokens since last chunk; delta semantics
    is_final: bool = False
    tool_calls: list[ToolCall] = []  # populated on final chunk
    usage: TokenUsage | None = None  # populated on final chunk where exposed
    message: Message | None = None   # synthesised assistant Message; final chunk
```

**Delta semantics**: `content` is NEW tokens, NOT cumulative. The agent accumulates by string concatenation. The final chunk MAY carry a delta (some providers emit stop-event trailing text); the accumulator checks `chunk.content` regardless of `is_final`.

**Final-chunk contract**: providers populate `message` so `Agent.step` can prefer it. When `message` is None, the agent rebuilds from accumulated `content` + `tool_calls` + `usage`.

### Per-provider notes

- **Anthropic**: native via `client.messages.stream(...)`. Catches `BadRequestError` mentioning "temperature", strips the kwarg, retries once. Gated by `yielded_any` so the retry is only safe BEFORE any chunk has emitted (Anthropic raises pre-stream in practice).
- **OpenAI**: native via `chat.completions.create(stream=True, stream_options={"include_usage": True}, ...)`. The `include_usage` flag is **required** — without it the trailing metadata chunk has no `usage` and end-of-stream telemetry breaks. Tool-call deltas accumulate by `index`.
- **Ollama**: native via `ollama_api.chat_stream`. True SSE (`data: {...}` + `data: [DONE]` terminator), distinct from `pull_model`'s JSONL. Reuses the OpenAI-shape tool-call accumulation.
- **Mock**: honours `config["stream_chunks"]: list[str]`. When unset, falls back to default-impl **inline** (NOT `super().stream(...)` delegation) for clarity.

### `_StreamAccumulator` — shared streaming helper

`the_one/llm/_streaming.py` — M12 F6 L1 consolidation of the near-identical per-provider streaming internals.

**Responsibility**: encapsulates the two cross-provider concerns that previously lived as duplicated blocks in `openai_provider.py` and `ollama_provider.py` (tool-call delta accumulation) and `anthropic_provider.py` (byte→interim-usage emitter):

1. **Tool-call delta accumulation** (`feed_tool_call_delta`, `finalize_tool_calls`) — keyed by `index` (OpenAI / Ollama streaming convention). Providers normalise SDK objects to `str` at the edge before calling `feed_tool_call_delta`; the accumulator is str-append-only. Ollama must `json.dumps(args)` when `arguments` arrives as a dict before handing the increment here.
2. **Byte→interim-usage emission** (`maybe_emit_interim`) — returns a `StreamChunk(usage=…)` when the cumulative byte count since last emission crosses `threshold` (shared 200-byte default). Providers call this AFTER yielding the content chunk, then yield the returned interim chunk (if not None). Preserves the exact per-provider emit ordering.

**Per-provider bytes-per-token** (M16 F08 L01): a SINGLE public `bytes_per_token` accessor lives on the `LLMProvider` base (default 4.0); OpenAI/OpenRouter 4.0, Ollama 3.5, Anthropic 3.7 override the class attribute. Both consumers — the `_StreamAccumulator` (passed `self.bytes_per_token` at stream-open) and the context-budget governor (`_execute_tool` → `govern_tool_content`) — read this one value, so they cannot drift. (Replaced the prior subclass-only `_bytes_per_token_for_interim()`.)

**Anthropic adopts only the byte-emitter half** — its tool calls arrive whole via `get_final_message`, not as streaming deltas.

**Import discipline**: `_streaming.py` imports ONLY from `the_one.llm.base` (acyclic: `base` is the leaf; `_streaming` depends only on `base`; providers depend on both).

### WS event vocabulary

| Event | When | Notes |
|------|-----|-------|
| `assistant_chunk` | Per-content-delta during streaming | |
| `assistant` | Direct-action shortcut path only | Suppressed when chunks fire |
| `tool_call` | Tool-call emitted by the model | Carries `parent_message_id` + `tool_call_id` |
| `tool_result` | Tool execution result | Carries the same pair |
| `usage` | Per-iteration final-chunk usage | |
| `done` | End of agent step | |

The streaming WS contract is **chunks-only-no-final-assistant**: when the chunk path fires, the legacy `assistant` event is suppressed server-side. The client has the accumulated text via chunks. The legacy event survives for the direct-action shortcut path (early-return in `Agent.step` before any LLM call).

**`parent_message_id` namespace convention**: live sessions use `{session.id}-msg-N`; replayed sessions use `replay-msg-N`. The frontend treats these as opaque grouping keys — different namespace prefixes between live and replay are not collisions.

### `chunks_seen` invariant

The server distinguishes streaming from direct-action via a per-iteration `chunks_seen` flag captured in the agent-step closure. The flag is set inside `_broadcast_chunk` and reset **unconditionally at the end of each Role.ASSISTANT block** in the `async for msg in agent.step(...)` loop. Unconditional matters for multi-iteration loops: a tool-call-only iteration (empty content, non-empty `tool_calls`) must still reset the flag for iteration N+1.

### Persistence contract

The synthesised final assistant `Message` is **NOT broadcast** as `{"type": "assistant"}` over the WS during streaming (the client already has the text). It IS:

- Appended to `session.history` via `session.add_event` so rejoin/refresh re-renders from server-side history.
- Appended to `result_messages` so the HTTP API caller receives the full message list.

This split — stream-deltas-over-WS, persist-full-message-server-side — is the F4 leg-04 contract. Enforced end-to-end by `test_streaming_message_persists_to_history`.

---

## Markdown rendering

Hand-rolled CommonMark-subset library at `static/js/markdown.js`. Public API: `App.markdown.parse(text) → AST`, `App.markdown.render(text) → DocumentFragment`, `App.markdown.NodeType`.

### Supported subset (v1) — contract for callers

paragraphs, ATX headers (`#`..`######`), fenced code blocks with language tag, blockquotes (single level), unordered + ordered lists (one nesting level), horizontal rules (`---`/`***`), emphasis (`*` or `_`), strong (`**` or `__`), inline code, links (including balanced-paren URLs), soft breaks (single `\n`), hard breaks (trailing TWO spaces + `\n`).

**Out of subset (v1 non-goals)**: tables, footnotes, definition lists, autolinks, reference-style links, HTML passthrough, recursive nested emphasis. The test corpus locks v1 in; expanding requires a new flight with test-case expansion.

### Nested-emphasis v1 contract

`***word***` renders as `<em><strong>word</strong></em>` (outer-em-first). Recursive nested emphasis is v2 scope. `**bold *with em***` renders as `<strong>bold *with em*</strong>` — the inner `*with em*` is literal. Mechanism: `inEmphasisRun` suppression flag once an emphasis run opens.

### XSS guarantee

Renderer constructs DOM via `document.createElement` + `textContent` exclusively. The library NEVER uses `innerHTML` — `grep -n innerHTML markdown.js` returns zero hits (including comments). SVG icon injection on the copy button uses `DOMParser().parseFromString(svg, 'image/svg+xml').documentElement` to keep the invariant. Link `href` values pass through a scheme allow-list (`http`, `https`, `mailto`, `tel`, `/`, `#`); other schemes (`javascript:`, `data:`, `vbscript:`, `file:`) are stripped to `#`. "No innerHTML anywhere in the markdown pipeline" is a structural property — future contributors cannot accidentally introduce XSS via crafted markdown.

### Robustness for streaming

`parse(null)`, `parse(undefined)`, `parse('')` all return `{type: 'document', children: []}` — no exception. Streaming callers can pass partial buffers without try/catch ceremony.

### Mid-stream rendering NOT supported

Partial markdown syntax has no canonical semantics (`**bold` mid-token has no end). The streaming path uses `textContent` accumulation followed by a single swap on `done`. Chat integration: `App.chat.renderMessage(cls, text)` markdown-renders assistant messages by default; user/tool/system stay `textContent`. Detection uses a first-token whitespace split (`cls.split(' ')[0] === 'assistant'`) so `'assistant-error'` would NOT trigger markdown.

### Extension contract

Adding a new construct: (1) `NodeType` constant, (2) tokeniser/parser case, (3) renderer branch, (4) ≥3 parametrised test cases. All four in the same leg. PRs missing test cases fail review.

---

## Design system

**Design Language v3 — "quiet instrument panel"** (Mission 17 Flight 2). Neutral surface ladders, hairline borders, one restrained violet accent, exactly two shadows, no decorative effects. The v2 alien-console vocabulary (glows, glass/backdrop-filter, bezels, chamfer clip-paths, shell chrome, btn-v3 gradients, `//` section markers) is retired and ENFORCED-gone: `tests/test_ui_guards.py::test_no_retired_design_vocabulary_in_css` fails on any reintroduction in `static/css` (comments included). Flight 3 closed the last deferred remnant: the selected-tab L-bracket `clip-path: polygon` in `components.css` is gone (rebuilt as a 2px accent bottom-border), and its count-1 `CLIP_PATH_POLYGON_ALLOWANCE` entry was deleted with it — the guard now expects zero retired-vocabulary matches.

### Token roles and ladder semantics

Defined in `static/css/tokens.css` (single source; hex values live there, not here):

- **Surfaces** — a three-step ladder `--bg` → `--surface` → `--surface-elevated` (dark: lifted charcoal; light: white/near-white). Elevation reads as the next ladder step, NOT as a bigger shadow — especially in dark. `--surface-tool` and `--code-block-bg` are role variants on the same ladder (the code well sits one step *below* bg in dark).
- **Borders** — hairlines one step above their surface: `--border` → `--border-hover` → `--border-strong`. Separation between panels is carried by 1px hairlines, never by fills, shadows, or chrome.
- **Text ladder** — `--fg` → `--fg-secondary` → `--fg-tertiary` → `--fg-muted` → `--fg-faint`, plus on-color inks (`--fg-on-accent`, `--fg-on-danger`). Every tier clears body AA on all three surfaces EXCEPT `--fg-faint` (deliberate band exception, below).
- **Accent** — violet (`--accent`), with `--accent-translucent(-hover)` washes. `--accent-api` is badge-tier (chat user-vs-API differentiation), NOT an interactive accent.
- **Status** — `--status-success/warning/danger` + soft `-bg-soft`/`-border` washes. Status text gates at body AA on bg/surface in BOTH themes. LEDs/dots are flat; labels carry the meaning.
- **Badges** — provider + tool-category brand colors, theme-stable. Per-badge ink tokens (`--badge-ink-*`, Flight 3) give each fill a luminance-matched text color; every badge×ink pair clears **body AA in both themes** and is GATED in `tests/test_design_tokens_a11y.py` (`test_badge_ink_passes_body_aa`).
- **Geometry/motion** — spacing/radius/shadow scales (below), `--sidebar-w`/`--topbar-h` density tokens, `--motion-*` durations (collapse to 0 under `prefers-reduced-motion`). The `--panel-radius*` compat aliases were retired in Flight 3: all 35 consumer refs were migrated onto the `--radius-*`/`--space-*` scales and the 4 alias definitions deleted from `tokens.css`.

### Accent restraint rule

Accent appears on **interactive and selected states only** — active nav item, selected tab, focus rings, primary buttons, links. Never as ambient decoration, never on static chrome, never as a glow. The palette carries two accents' worth of identity (violet + badge colors); restraint is what keeps the panel quiet.

### Both-themes-designed contract

Dark and light are each designed on their own merits — neither is a value-flip of the other (dark: charcoal ladder + 400-family statuses; light: zinc ladder + 600/700-family statuses). Any change to one theme block must be designed (and AA-verified) in the other in the same change; a leg never lands with one theme unfinished. The nav rail is ladder-native in both themes (the light theme's dark-navy palette island was retired in v3).

### Color contrast (WCAG AA regression contract)

Token contrast pairs are audited by `tests/test_design_tokens_a11y.py` against:
- **4.5:1** for body text (WCAG 1.4.3)
- **3.0:1** for large text, UI components, non-text contrast (WCAG 1.4.11)

The test file hardcodes token values to mirror `tokens.css`; canonical mirror lives in `tests/browser/design_tokens.py` (`DARK` / `LIGHT` dicts). **Before changing a color token, re-run `pytest tests/test_design_tokens_a11y.py`.** If CSS values change, update `design_tokens.py` in lockstep — the lockstep is ENFORCED by `tests/test_ui_guards.py::test_design_token_mirror_in_sync` (mirror-driven value-sync against the top-level theme blocks of `tokens.css`, hex-normalized). Coverage (v3, gates accreted M17 F2–F6): the full fg ladder × bg/surface/surface-elevated/surface-tool at body AA; accent/accent-api/status-danger-muted at UI AA on the ladder surfaces; on-color pairs (accent/danger fills, code well); status colors at body AA on bg/surface; **per-badge ink × fill** (F3); and the **composited-a11y** family — text/marks on rgba washes reconstructed with `_alpha_composite` over a known base surface (danger/warning soft-fills, the tinted user bubble + translucent assistant/table-zebra surfaces, the indeterminate tool-switch thumb, the resting telemetry ghost) — all in both themes.

**SC2 completeness net** (F7): `test_design_tokens_a11y.py::test_sc2_every_fg_role_token_is_gated_or_exempt` enumerates the fg-role families (`--fg*/--accent*/--status*/--code-block*`) **from `tokens.css` itself** (via `parse_tokens_css_theme_blocks`, NOT from the mirror) and asserts every token is either GATED (literal-hex, mirrored, and referenced by a contrast assertion) or EXEMPT (rgba wash / structural, documented in `_CONTRAST_EXEMPT` with rationale). This closes the one hole the mirror-sync guard cannot: that guard is strictly mirror→CSS, so a literal-hex fg token added to `tokens.css` but NOT the mirror would slip both nets — the completeness net drives off the CSS source of truth and fails loudly naming any such token.

`tests/test_token_definitions.py` parses every `var(--x)` reference across `static/css/*.css` and asserts each token has a definition. Catches typos like `var(--accnet)` that CSS silently treats as `unset`.

### Deliberate AA exceptions

`--fg-faint` (dark `#6b6d78`, light `#898993`) is intentionally below body AA but pinned to the **3.0 ≤ ratio < 4.5 band** on bg, surface, AND surface-elevated in both themes (v3 re-derivation, M17 F2: a faint tier at ≥4.5 stops being faint and collides with muted). Used for de-emphasized annotation labels (`.msg-attribution`, telemetry "in:"/"out:"/"ctx:" eyebrows) — NEVER body prose, NEVER an interactive UI affordance. The exception carries a `# DELIBERATE EXCEPTION` comment in the test file; the band assertions trip if a future retune drifts the value out of "faint" territory in either direction.

**Exception policy**: a sub-AA pair exists only as a *band-pinned, consumer-scoped, test-annotated* exception — the suite asserts both its floor AND its ceiling, the allowed consumer roles are named, and the `# DELIBERATE EXCEPTION` comment marks it. An exception the suite doesn't pin is a bug, not an exception.

### Focus visibility convention

Pinned form (v3): `outline: 2px solid var(--accent); outline-offset: 2px;` — **no halo, no box-shadow**. Three sanctioned variants (M17 F2 L2a):
- **Inset rings** keep negative outline-offsets where an outset ring would clip against a scroll container (`.list-item`, `.entity-tile`, `.section-nav-item`, `.tab`, `.chat-welcome-item`).
- **`.btn-stop-turn`** keeps a danger-colored outline (its accent IS danger).
- **`:focus-within` container treatments** degrade to a border-color change (e.g. `.chip-list-editor`), not a ring.

Both themes meet the 3:1 non-text contrast threshold against adjacent surfaces.

### Two-shadow elevation system

Exactly two shadows exist: `--shadow-popover` (dropdowns, toasts, transient floats) and `--shadow-modal` (modal dialogs). Everything else expresses elevation via the surface ladder + hairlines. Do not introduce a third shadow; if a component seems to need one, it is either a popover, a modal, or not elevated.

### Spacing and radius scales

`--space-1..8` (4/8/12/16/24/32/48/64 px) and `--radius-sm/md/lg` (6/8/12 px), theme-agnostic in `:root`. Declarations being rewritten adopt the scales; wholesale migration of untouched declarations is deferred work (Flight 3+), not license for ad-hoc pixel values in new CSS.

### Type discipline

Geist, sizes per `fonts.css` (13px UI chrome / 14–15px content). Weights: **400 body, 500–600 emphasis — no 700 in chrome**. Tabular numerals for tables/telemetry. No uppercase-shouting in chrome: labels and section titles are sentence-case.

### Component vocabulary (M17 F3 — one vocabulary, used identically everywhere)

The shared component set lives in `static/css/components.css`; the `#admin/design-language` gallery is its **living reference** (each section module showcases the current vocabulary and is the acceptance surface for "one vocabulary"). All components consume `--space-*`/`--radius-*`/`--motion-*` — no ad-hoc pixels.

- **Buttons** — four variants, class names retained from v2: PRIMARY `.btn-filled-primary` (flat accent fill), SECONDARY `.btn-outlined-primary` (quiet surface + hairline, `--fg` ink), GHOST `.btn-ghost` (borderless, surface shift on hover), DANGER `.btn-muted-destructive` (soft danger fill + danger border). All **32px** tall / `--radius-sm` / flat fills (no gradients) / pinned focus (2px accent, +2px offset). Height modifiers: `.btn-sm` 24 / `.btn-lg` 36 / `.btn-xl` 40. Icon svgs inside these render at 16px. **One primary per region** — at most one `.btn-filled-primary` in any visual region; every other affordance is outlined/ghost (e.g. the unified header create CTA is `.btn-outlined-primary`, so an empty state showing header + canvas CTA never has two primaries).
- **Fields** — label-above stacked `.field-group` is the vocabulary primitive (the legacy label-left `.field-row` 100px gutter is per-area layout that migrates in the F4-6 re-skins, not the vocabulary). The group's label row is the shared `.field-group-label` (Flight 6) — a flex header carrying the `<label>` plus any trailing affordance (info icon, inline action) on one baseline above the control; `renderField` and the studio/admin editors all mount their labels through it, so the label/control gap and alignment are one recipe, not per-editor. **Inline validation** = `.is-invalid` on the group + a `.field-error` message (color **and** text, never color alone); `.field-hint` for help. Pinned focus form. `.field-select` is self-sufficient (full quiet-surface + hairline + pinned-focus treatment on its own class) — it IS the vocabulary dropdown for static single-select.
- **Tiles / cards** — surface + hairline + `--radius-md`; elevation reads as the surface-elevated ladder step, **no shadows at rest**; hover = `--border-hover` + surface-elevated; accent reserved for the selected state.
- **Tables / lists** — 40–44px rows (`.list-item` min-height 40px), hairline separators only, hover = surface shift.
- **Tabs** — selected = 2px accent **bottom-border** keyed off `aria-selected` (no chamfer/clip-path); unselected reserves the 2px with a transparent border so selection never jumps layout. Arrow keys move focus (inset ring), Enter commits selection + panel swap.
- **Modals** — the existing `dialog.js` overlay (`.modal-dialog`) restyled, NOT a native `<dialog>` migration: it already carries `role=dialog`/`aria-modal`/focus-trap/Escape/restore-focus; the vocabulary gives it `--radius-lg` + surface + hairline + `--shadow-modal`.
- **Toasts** — `.app-flash`: `--surface` + `1px --border` hairline + `--fg` ink + `--shadow-popover`; the `.error` variant swaps to `--status-danger` ink + danger hairline on the same surface (both inks gated body-AA on `--surface`).
- **Empty states** — one-line statement + exactly one primary action (`.empty-canvas-cta`, an outlined-primary instance sharing the grid's create handler); the inviting canvas copy carries the invitation.
- **Badges** — per-badge ink, body-AA gated both themes (see Token roles → Badges).

### Section titles — quiet treatment

`.section-title` is a quiet label: sans, `--font-size-body-sm`, weight 500, `--fg-secondary`. No `//` eyebrow pseudo-elements, no mono-uppercase-letterspaced treatment — in CSS *or* in JS-supplied text (hardcoded ALL-CAPS strings are the same violation).

**One class, two roles (element-scoped size).** The class is worn by BOTH real section HEADINGS (`<h2 class="section-title">` — studio/admin editors) AND a non-heading quiet label (`<label class="section-title" for="chat-agent-select">` in the chat sidebar). Real headings get an **element-scoped** bump — `h2.section-title { font-size: var(--font-size-h3) }` (Flight 3) — while the label stays at `--font-size-body-sm`. A bare `.section-title { font-size }` rule would inflate the label too; the `h2` element scope is load-bearing. **Renaming the class was considered and deferred** (churn without payoff — the element-scoped bump gives headings their emphasis without a mass rename); the admin `-pf-models-title`/`-pf-section-label` eyebrows were also quieted to this recipe in the same flight.

### Label-association guard pattern — static + runtime (Flight 5/6 methodology asset)

`<label for="X">` associations are enforced by a TWO-LAYER guard because neither layer alone is sound:

- **Static** (`tests/test_ui_guards.py::test_field_group_label_for_resolves_to_control`, F5) scans the JS sources and asserts every literal `<label for="X">` has a matching control id somewhere in source (WCAG 1.3.1 / 4.1.2). Cheap, no browser — but it reads SOURCE, so it is blind to associations that break only at mount time.
- **Runtime** (`tests/browser/test_flow_chiplist_label_resolver.py`, F6) mounts the chip-list-bearing editors in a real browser and resolves each `label[for]` through the DOM's own `HTMLLabelElement.control` (which returns `null` for a missing OR non-labelable target), asserting it lands on the real `.chip-list-input`.

The runtime layer exists because the shared `renderChipListEditor` mounts via `outerHTML=` (`mountChipListEditors`), which STRIPS the placeholder `<div id="X">`'s id — so a label that looks correctly wired in source dangles at runtime, and the static scan provably cannot catch it. The general lesson: **any label whose control is (re)mounted by an `innerHTML`/`outerHTML` write needs the runtime resolver guard, not just the source scan.** Both guards are load-bearing mission-introduced invariants — keep both green.

### Theme switching contract

Tri-state preference (`'dark'` | `'light'` | `'auto'`) persisted in `localStorage` under `theme-preference`. `<html data-theme="dark|light">` is applied synchronously by `static/js/theme.js` BEFORE any stylesheet load — the `<script>` is in `<head>` ahead of `<link rel="stylesheet">` to avoid FOUC.

API on `App.theme`:
- `get()` → preference or `'auto'` if unset
- `resolved()` → currently-applied theme (reads `data-theme`)
- `set(pref)` — throws on values other than `'dark'`/`'light'`/`'auto'`. `'auto'` REMOVES the localStorage key (page falls back to OS).

Auto-mode resolution: `darkMedia.matches` → dark, else `lightMedia.matches` → light, else **dark** (canonical default — the design language is dark-first). Reads/writes are try/catch-wrapped so private-browsing degrades to in-memory non-persistent.

**Cross-tab sync (M17 F2 L3)**: theme.js listens for `window` `storage` events on the `theme-preference` key, so a preference set in one tab applies live in every other open tab — including key REMOVAL (`newValue === null` → auto) and garbage values (degrade to auto via `resolve`). The listener reads the event's `newValue` (never re-reads localStorage — a re-read races a subsequent write) and re-dispatches `theme-preference-changed` so a mounted toggle in the receiving tab re-checks. `storage` events never fire in the originating tab, so there is no echo loop. Regression: `tests/browser/test_theme_cross_tab_sync.py` (two pages, SAME BrowserContext — storage events don't cross contexts).

Test environment: Playwright pins `color_scheme="no-preference"` so tests don't inherit host OS preference. Measured ground truth (M17 F2 L3): Chromium under that emulation MATCHES `(prefers-color-scheme: light)` — the no-preference media state was dropped from the spec — so **auto resolves light in the harness** (the "neither matches → dark" default is unreachable there). To capture a specific theme: `page.evaluate("App.theme.set('light')")` + wait for `App.theme.resolved() === 'light'`.

### Typography & icons

Sizes / weights / families / icons are defined in `static/css/fonts.css` and `static/js/icons.js` — read the source rather than mirror the catalog here. Icons pinned to `lucide@v0.265.0`; the pin matters for snapshot-test stability. Add icons by appending to `Icons` in `icons.js` (preserve Lucide's `width="24" height="24" viewBox="0 0 24 24" stroke="currentColor"`).

### App shell — invariants

- The `<a class="skip-link" href="#main-content">` is the FIRST element in `<body>` (before topbar). Activating it sets `location.hash = '#main-content'`; the `hashchange` listener bails because `main-content` is not a registered area. `<main tabindex="-1">` receives programmatic focus.
- App-picker (hamburger) wiring lives INSIDE `renderTopBar()` so `closePicker` is in shared closure scope — no separate `wirePicker` function (that pattern introduced a closure-scope hazard in F3 design review).
- `App.registerArea({sidebarLabel})` — after each `switchTo`, `<aside id="app-sidebar">` receives `aria-label` = `descriptor.sidebarLabel` OR `descriptor.label + ' sidebar'`.

### Hash routing

URL format: `#area[/sub]`. `area` ∈ `{chat, studio, admin}` (defaults to `chat`); `sub` is area-specific (`sessions/<uuid>`, `agents/<name>`, bare admin-category id).

**Critical history invariant**: cross-area navigation uses `location.hash =` (pushes history); area-internal sub-change uses `history.replaceState` (replaces). `replaceState` does NOT fire `hashchange`. If this invariant is broken by using `location.hash =` for sub-navigation, a recursion loop results: `switchTo` → `replaceSub` → `hashchange` → `switchTo` → ...

Net effect: browser back exits the area entirely (or returns to the previous area) — it does NOT walk back through sub-page history within an area.

**Lifecycle**: cold entry runs `init() → activate() → hydrateState(sub)`; same-area sub-change runs `hydrateState(sub)` only. `hydrateState` runs synchronously after `activate` returns, but `activate` may have kicked off async work — `hydrateState` MUST stash a pending target and resolve it when async work completes; it MUST NOT assume data is ready synchronously.

### Keyboard operability patterns

**Listbox/option** — used where a parent row is clickable AND contains a child action affordance (the nested-button rule prohibits `<button>` inside `<button>`). Parent stays `<div role="listbox">`; rows are `<div role="option" tabindex="0" aria-selected="...">`. Keydown fires the activation handler on Enter or Space (preventDefault on Space). All options use `tabindex="0"` (no roving) — WCAG-compliant for 5-20 items.

**Deliberate accepted deviation**: `role="option"` technically should not contain interactive children. In practice NVDA and VoiceOver handle this correctly (announce the option, then the inner button separately).

**Button reset for `<span>` → `<button>` conversions**: add `background: transparent; border: none; cursor: pointer; padding: 0;`.

**SVG-resilient click dispatch**: use `e.target.closest('.chip-remove')` (not `e.target.classList.contains`). Clicking on a child SVG yields `e.target = <svg>` and the `classList` check fails silently.

**`:focus-within` reveal**: hover-only delete affordances (hidden by `display: none`) reveal via the parent's `:focus-within` selector when the user Tabs into the child button.

---

## Testing patterns

### Pytest markers

| Marker | Tests | Default `pytest` | CI |
|---|---|---|---|
| (none) | unit | runs | runs |
| `live` | real LLM APIs (paid) | skipped | skipped |
| `browser` | Playwright functional | skipped (`-m browser`) | runs `-m browser` |
| `pixel` | Playwright visual snapshot | skipped (`-m pixel`) | **never runs** |
| `requires_bwrap` | bwrap integration | skipped | skipped |

Default `addopts` deselects `live`, `browser`, `pixel`, and `requires_bwrap`.

### Test fixtures and conventions

Tests monkeypatch built-in tool registration via `the_one.tools.builtins._TOOL_CLASSES` (module-level dict) — the supported seam; do NOT reach into `BuiltinToolProvider` internals.

The four established test patterns (asyncio_mode auto; `monkeypatch.setenv` HOME for tilde-expansion tests; httpx `MockTransport` `_install_mock` recursion avoidance; kill+reap timeout-budget assertions) live in `tests/CONVENTIONS.md`.

Tests inject a fake `SearchBackend` (and other Protocol-keyed services) by overriding `cross_configs[SearchBackend]` on the per-call view — no monkeypatching of module internals. This IS the supported test seam.

**`_TOOL_CLASSES` ordering is policy — cross-Config source note (M14 F4 L7)**: the
`get_tools` cross-config resolution loop walks `_TOOL_CLASSES` in declared order and maps
each distinct `cls.Config` to the **first** tool name that carries it. `FilesystemConfig`
is shared by all 9 filesystem tools (`read_file`, `write_file`, `edit_file`, …), but the
first one in declaration order is `read_file` (not `shell`, whose Config is
`ExecutionConfig`). This means tool-config tests that need to set filesystem-policy fields
(e.g. `path_allowlist`) must key them under `"read_file"`, not `"shell"` or any other
filesystem tool. Reordering `_TOOL_CLASSES` silently changes which tool name resolves
`FilesystemConfig` — a policy consequence, not cosmetic. A module-level `assert` in
`tools/builtins.py` guards this invariant and fires immediately on any reorder.

### Sandbox testing footguns

Three patterns that cause confusing false-passes or false-failures in `@requires_bwrap` and sandbox-adjacent tests:

1. **Spec-level teardown dispatch** — `self._wrapped = spec.command == "bwrap"` is the single ground truth used by `UnixPtySession.close()` to pick SIGKILL-fast vs SIGTERM→grace teardown. Tests that want to assert teardown behavior must not mock the backend after `start()` returns — the dispatch bit is set during `start()`. Check `_wrapped` directly or rely on the test's observable (e.g. timing) rather than inspecting backend state.

2. **PTY-echo sentinel** — the PTY echoes the command line back on the master fd before the shell runs the command. If a test asserts `"connected"` is in the send output, it will **always pass** (the echo contains "connected" before the shell runs). Use the `"con"+"nected"` string-concat trick to keep the target literal out of the source text sent to the shell. Assert on the OUTPUT portion (after the echo) when the shell output and echo are interleaved. See `test_pty_sandbox.py:test_pty_network_denied_by_default_allowed_when_enabled` for the canonical example.

3. **`@requires_bwrap` workspace must be under `$HOME`, not `/tmp`** — bwrap always mounts a fresh `tmpfs` at `/tmp` (via `--tmpfs /tmp`). Any workspace or file under `/tmp` is invisible inside the sandbox. Always use `home_workspace()` from `tests/_sandbox_fixtures.py` (creates `~/.the-one-test-{suffix}`) for bwrap test workspaces; never use `tmp_path` or `/tmp`-rooted paths. The same applies to denylist secrets: create them under `$HOME` via `make_denylist_secret(workspace)` before bwrap starts, because `--ro-bind-try` silently skips absent paths (see `--ro-bind-try` silent-skip caveat in `SECURITY-MODEL.md`).

### Browser test isolation

Each browser test gets its own app subprocess on a random port (`socket.bind(('', 0))`) with isolated `tmp_path` data_dir. Teardown sends SIGTERM, escalates to SIGKILL after 10s. Browser navigates to `http://127.0.0.1:{port}` (not `localhost`) to avoid IPv6 first-attempt delay on WSL2.

Playwright fixtures (`playwright_instance`, `browser`) are **module-scoped**, NOT session-scoped — session scope kept the asyncio loop alive across modules and broke standalone smoke tests. Module scope still amortises Chromium within a module.

Tests rely on `data-testid` attributes on load-bearing UI elements rather than CSS classes, so they survive UI redesigns.

### Browser apparatus doctrine (goldfinch) — live visual verification

goldfinch (MCP-driven browser) is the **canonical apparatus** for live visual verification against a running dev instance (`make up`); Playwright covers scripted regression, goldfinch covers exploratory/evidence work. Hard-won rules (sources: M17 F1 run log; M17 F2 L1/L2a/L2b flight-log anomalies):

- **printToPDF + computed-style probes are the default evidence path, not a fallback.** `captureScreenshot` wedged (timeouts) in three consecutive F2 legs; `captureWindow` is admin-only. printToPDF is provenance-certain pixels, BUT print emulation mutes background fills — computed-style probes are the primary color evidence, and active/selected states are judged via a11y checked-state (`readAxTree`), not print pixels.
- **The `captureScreenshot` wedge is progressive, and reload WORSENS it — escalate to UnknownVizError, don't retry.** The timeout is not transient: once `captureScreenshot` starts wedging on a tab it degrades further on `reload`/`navigate` (the doomed capture pipeline compounds), so the reflex "reload and retry" makes it worse, not better. Treat a wedged `captureScreenshot` as an **UnknownVizError** — an apparatus fault, NOT a product signal — and escalate to a different evidence path (printToPDF for pixels, computed-style probes for color, `readAxTree` for state, or a CDP page — below) rather than burning retries on the same broken primitive. Never let an apparatus wedge masquerade as "the UI didn't render."
- **PDF fill-palette cross-check — recover theme evidence under print-CSS muting.** Because print emulation flattens background fills, a printToPDF of a dark-theme view can look nearly identical to the light one, which defeats "prove the theme applied." Cross-check technique: render the SAME view to PDF in both themes and compare the surviving, non-muted signals — text ink color, hairline border colors, and the accent on selected/interactive elements (accent strokes survive muting better than large fills). If the fill-palette reads identical across the two PDFs on the signals that SHOULD differ, the theme did not actually switch (or you captured the wrong tab); matching computed-style probes are the tiebreaker. printToPDF proves structure/geometry; the fill-palette cross-check + computed styles prove theme.
- **goldfinch cannot observe `:focus` / `:focus-visible` — `document.hasFocus()` is always false there; use a CDP-driven `chrome-devtools` page for focus evidence.** A goldfinch-driven tab never holds real window focus, so `document.hasFocus()` returns false and `:focus-visible` never matches — focus-ring and keyboard-operability evidence gathered through goldfinch is a **false negative**, not a product bug. For any focus/keyboard acceptance (focus rings, Tab traversal, focus-trap, `:focus-visible`), drive a **CDP-connected `chrome-devtools` page** instead: it holds real focus (`document.hasFocus() === true`), `:focus-visible` matches, and its `take_screenshot` writes full-color pixels (sidestepping print-emulation muting). This is the sanctioned apparatus for the "Focus visibility convention" acceptance surface.
- **Multi-tab provenance discipline: unattributed frames are non-evidence.** Every capture/probe must be attributed to a specific tab (wcId + URL) you opened or verified. Close your own tabs when done; never assume a foreground tab is the one you drove.
- **a11y rendered/notRendered discrimination**: use the accessibility tree (`readAxTree`) to distinguish "element exists but hidden" from "rendered and exposed" — DOM presence alone over-claims.
- **Foreground the tab before trusting computed styles after a theme flip.** A backgrounded tab's rendering is throttled: rules with `transition: background-color` freeze at their FROM state, so probes read the OLD theme's colors while `var()` on the same element already resolves NEW values. Foregrounding (or a printToPDF, which foregrounds first) unfreezes it instantly.
- **Never-painted tab freezes transitions at FROM — `getAnimations().finish()` before probing (when you can't foreground).** A stronger form of the throttle above (F2 L2 anomaly, seen again L3): a tab that has NEVER been foregrounded produces **zero rendering frames**, so a transition on a freshly-set attribute/class (e.g. `aria-current` toggling a `transition: background-color` wash) sits at `currentTime 0` / `startTime null` indefinitely — `getComputedStyle` reports the FROM value forever even though the rule verifiably matches. This is an apparatus artifact, NOT a product bug: a synthetic element inserted with the attribute pre-set (no transition to play) styles correctly, and the transition lands in any painting tab. When you can't foreground the probe tab, call `el.getAnimations().forEach(a => a.finish())` to jump every running transition to its end state **before** reading computed styles.
- **Hard-reload after `make restart`.** The SPA links assets with versioned URLs (`?v=X.Y.Z`); the browser serves cached versioned responses even after the server restarts with new CSS/JS. Recovery: `fetch(href, {cache:'reload'})` over `document.styleSheets`/`document.scripts`, then `location.reload()`.
- **Port-ownership pitfall (the squatter class).** A foreign process squatting the app port serves ITS build while `make up`'s fresh server dies with "address already in use" — every 200 and every rendered frame then comes from the WRONG build. `make verify-serving` asserts the pid listening on `$THE_ONE_PORT` matches the port-suffixed pidfile (`.the-one.<port>.pid`) and fails loudly on mismatch or unresolvable pid. Before trusting visual evidence, confirm the served instance is yours (verify-serving, or served-source grep + pid-owns-port).
- **Record and restore operator state.** Theme preference (`theme-preference` localStorage key, per visited origin) is recorded before toggling and restored after; the dev instance is left as found.

### Visual snapshots — local-only

Baselines under `tests/browser/__snapshots__/` are **gitignored** — local regression artifacts, not shared source. First run: `pytest -m pixel --snapshot-update`. Subsequent runs compare; >2% diff fails and writes `<name>-actual.png` + `<name>-diff.png`. CI never runs `-m pixel`. Pixel diffs are a developer's local feedback loop, not a regression gate.

### UI schema metadata

Pydantic Config schemas may declare UI-presentation hints via `Field(json_schema_extra={"ui_hint": "...", "ui_choices": [...]})`. `ui_hint` is the rendering strategy (`"dropdown"`, future: `"slider"`, `"toggle"`); `ui_choices` is a list of `{"value": ..., "label": ...}` dicts. The F6 admin form generator (`App.adminFormHelpers.renderField`) renders finite-set fields as dropdowns rather than free-form inputs. Server-side `_enrich_schema_with_markers` injects `x_marker` per property so the renderer can dispatch on marker class — admin and Studio share the same renderer with mode-specific widget shapes.

---

## Performance instrumentation

`App.perf` (`static/js/perf.js`) is the canonical surface for ad-hoc UI performance measurement. Gated per `gated-debug-instrumentation` convention (URL `?perf=1` OR `localStorage.getItem('the-one-perf') === '1'`). The `enabled` flag is captured at module-load time — toggling localStorage mid-session requires a reload.

**Browser support**: `performance.memory` is Chromium-only and only exposed in same-origin-isolated contexts; values are throttled to 100KB precision. `App.perf.captureHeap()` returns `null` when unavailable; callers must handle null.

Public surface: `mark`, `measure`, `captureHeap`, `dump`, `summary`, `reset`. Every method short-circuits when disabled. Measurement procedures and budgets for specific scenarios (area-switch cycles, long-chat rendering, large session-history list, many-agents-in-studio) live in flight design documents, not this file.

### Missing Playwright Chromium breaks raw `-m browser`

If `~/.cache/ms-playwright/` is missing — raw `.venv/bin/python -m pytest -m browser` errors with hundreds of "Executable doesn't exist" failures. Recovery: `make _ensure-playwright` (idempotent re-install, ~30-60s). The `make test-browser` chain already chains this; only the raw invocation hits the foot-gun. See `host-test-entrypoints-reach-via-make` convention.

> **Two connector-specific patterns removed here (Mission 23 connector reset)**: `connector-live-status-via-poll` (a DOM-connected-guard polling loop for reflecting live gateway connection state) and `save-reconnects-the-gateway` (evict-and-rewarm-in-background on connection-relevant config saves). Both lived entirely in the deleted connector editor and pool; the general "poll anchored to `element.isConnected`, stop on unmount" and "evict/re-acquire warm pool entries only on connection-relevant field changes" shapes are still sound and worth re-citing if a future UI surface or pooled resource needs them.
