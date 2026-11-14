# Leg: readme-content-and-perf-convention

**Status**: completed
**Flight**: [Professional README](../flight.md)

## Objective

Create the top-level `README.md` (warmly-narrative product-entry doc with screenshot placeholders) and add a new named convention entry under `the_one/agents.md`'s `## Project Conventions` section promoting the `?perf=1` / localStorage debugging-gate pattern.

## Context

Final flight of Mission 08 (GleepGlorp Rebrand & UX Polish). The mission's last unchecked criterion is "The project's top-level documentation introduces GleepGlorp AI as a product — what it is, what it does, how to run it, how it is structured, and where to read the security model — without requiring the reader to dig through code or per-mission artifacts."

L01 is FD-mechanical content work — no app boot required, no operator-manual screenshot capture. Two surfaces are created/modified:
- **NEW**: `/README.md` at repo root (none currently exists; only `.flightops/README.md` which is gitignored and `.pytest_cache/README.md` which is auto-generated)
- **MODIFY**: `the_one/agents.md` — add one new named convention entry under `## Project Conventions` (line 171), as a peer of the existing four (`trust-the-runtime`, `canonical-import + convenience-re-export`, `structural-Protocol-satisfaction`, `verbatim-message-equality`), naming the URL + localStorage debugging-gate pattern and cross-linking to the existing operational doc at `## Performance Measurement (F7)` (line 1503+) as the live example.

Key design decisions from the flight artifact:
- **README-as-product-entry, not reference**: README is shallow; link to `CLAUDE.md` and `the_one/agents.md` for depth. Drift is the worst README failure mode.
- **Warmly-narrative opening, terse elsewhere**: One-paragraph "what this is" reads conversationally; install/architecture/security sections are terse and scannable.
- **HTML-comment placeholders for screenshots, not `<img>` tags**: Between L01 and L02 commits, the README on the branch must render without broken-image icons. L01 uses `<!-- SCREENSHOT: chat-dark.png -->` markers; L02 replaces them with `<img>` references.
- **Six-paragraph architecture vs `agents.md`'s four-layer diagram**: Deliberate audience-driven divergence (README addresses external readers; `agents.md`'s four-layer diagram addresses implementers). L01 notes this in copy so a cross-referencing reader isn't confused.
- **Convention promotion lands as a NEW named entry peer of the existing four, NOT a duplicate of the operational doc**: The operational mechanics (URL query string `?perf=1`, `localStorage.setItem('the-one-perf', '1')`, enabled flag captured at module-load time) are already documented at `the_one/agents.md:1507-1511`. The new convention entry covers the **pattern itself** ("debugging-only modules use a URL + localStorage activation gate, short-circuit when disabled, never compile-time excluded") with a cross-link to the operational section as the live example.
- **No Concourse CI / self-modification coverage in README** — operator-internal, lives in deeper docs.

## Inputs

**State before this leg runs**:
- F7 (UI Performance Audit) is landed on `main`; mission criteria 1-11 all met or unchecked-but-not-this-leg
- Brand assets exist under `the_one/interfaces/web/static/brand/` — verified: `gleepglorp_med.png` (mascot), `gleepglorp_small.png`, `gleepglorp_icon.png`, `gleepglorp_banner.png`, `apple-touch-icon.png`, full favicon set
- `SECURITY-MODEL.md` exists at repo root (141 lines, current)
- `CLAUDE.md` exists at repo root (443 lines, mission-aware)
- `the_one/agents.md` exists (1668 lines, mission-aware); `## Project Conventions` section anchor at line 171 with four existing named conventions; `## Performance Measurement (F7)` section anchor at line 1503
- `the_one/interfaces/web/static/js/perf.js` exists with `App.perf` public surface (verified — module head comment block at lines 1-16 documents the gate and public surface)
- No top-level `README.md` exists yet
- No `docs/screenshots/` directory exists yet (created in L02; L01 does not create it)

**Files that must exist** (read-only inputs for this leg):
- `pyproject.toml` — install instructions reference `[project.optional-dependencies]` (lines 27-36)
- `Makefile` — Docker workflow targets (`up`, `down`, `rebuild`, `rebuild-clean`, lines 13-33)
- `.env.example` — sample env config (16 lines, mentions defaults for `THE_ONE_*`)
- `CLAUDE.md` — architecture reference (especially lines 60-91)
- `the_one/agents.md` — architecture reference (especially line 11-27 four-layer diagram)
- `SECURITY-MODEL.md` — security model overview
- `the_one/interfaces/web/static/brand/gleepglorp_med.png` — hero mascot

## Outputs

**Files created**:
- `/README.md` (repo root) — new file, ~120-160 lines, with structured sections per "Implementation Guidance" below

**Files modified**:
- `the_one/agents.md` — one new `### {name}` block inserted under `## Project Conventions`, between the existing `### verbatim-message-equality` block (ends ~line 217) and the section-closing `---` separator (line 219). Net diff: ~15-25 lines added; no other content changed.

**State changes**:
- The mission's criterion-12 (top-level documentation) precondition is now partially satisfied — content exists, screenshots pending (L02).

## Acceptance Criteria

- [x] `/README.md` exists at repo root and contains, in order: (a) hero image of `gleepglorp_med.png` (centered), (b) tagline below the image, (c) one-paragraph "what this is" in warmly-narrative tone, (d) install/run quickstart with both pip-editable and Docker paths, (e) per-layer architecture overview with six short paragraphs (Interfaces, Agent, LLM, Tools, MCP, Persistence) and an explicit one-line note about audience-driven divergence from `agents.md`'s four-layer diagram, (f) link to `SECURITY-MODEL.md`, (g) one-sentence pointer to the `missions/` artifact tree + a link to the Mission Control methodology repo (`https://github.com/msieurthenardier/mission-control`)
- [x] Three `<!-- SCREENSHOT: {area}-dark.png -->` HTML-comment placeholders are present in `/README.md`, one each for Chat / Studio / Administration, locatable via `grep -n "<!-- SCREENSHOT:" README.md`
- [x] `/README.md` contains NO `<img>` tags for screenshots (those are L02's responsibility); the hero mascot `<img>` IS present
- [x] `/README.md` contains NO references to Concourse CI or self-modification (operator-explicit out-of-scope decision)
- [x] `the_one/agents.md` contains a new `### {convention-name}` block under `## Project Conventions`, structured similarly to the four existing peers (intro paragraph + Live example + Counter-example), naming the URL + localStorage debugging-gate pattern, and cross-linking to the `## Performance Measurement (F7)` section
- [x] The new convention entry does NOT duplicate activation-gate operational mechanics (URL pattern, localStorage key, module-load-time capture) already documented at `the_one/agents.md:1507-1511`; it references that section as the live example
- [x] Markdown renders cleanly: no syntax errors, no broken inline links, all relative-path references resolve from the repo root
- [x] `ruff format` reports no diffs on the changed file paths (no Python files changed, but verify the working tree is clean otherwise)

## Verification Steps

- **README presence**: `test -f ~/projects/the-one/README.md && wc -l ~/projects/the-one/README.md` — file exists, line count in 100-200 range
- **Required sections present**: `grep -n "^## " ~/projects/the-one/README.md` should show at minimum: install, architecture, security, contributing/methodology
- **Hero asset reference**: `grep -n "gleepglorp_med.png" ~/projects/the-one/README.md` — should return at least one line in the top ~15 lines
- **Screenshot placeholders**: `grep -n "<!-- SCREENSHOT:" ~/projects/the-one/README.md` — exactly 3 matches: chat-dark.png, studio-dark.png, admin-dark.png
- **No premature `<img>` for screenshots**: `grep -n "<img.*chat-dark\|<img.*studio-dark\|<img.*admin-dark" ~/projects/the-one/README.md` — zero matches
- **No Concourse/self-mod**: `grep -in "concourse\|self-modif" ~/projects/the-one/README.md` — zero matches
- **Security link present**: `grep -n "SECURITY-MODEL.md" ~/projects/the-one/README.md` — at least one match
- **Mission Control link present**: `grep -n "mission-control" ~/projects/the-one/README.md` — at least one match
- **Convention entry added**: `awk '/^## Project Conventions/{found=1} found && /^## Dependency Graph/{exit} found && /^### /{print NR": "$0}' ~/projects/the-one/the_one/agents.md` — should now print five `### {name}` lines (the existing four plus the new one) within the `## Project Conventions` → `## Dependency Graph` range; the new entry's name should be self-describing and not collide semantically with the existing four. (Note: the obvious-looking `grep -n "^### " ... | sed -n '1,/Dependency Graph/p'` pattern does NOT work — `Dependency Graph` is an H2, never present in the H3-only grep output, so the sed range would stream indefinitely.)
- **Convention cross-link**: the new entry's body should reference `Performance Measurement (F7)` or `App.perf` or both; verify via `awk` or `grep -A 30 "### {convention-name}"`
- **No drift to other agents.md sections**: `git diff the_one/agents.md` should show ADDITIONS only between the existing `### verbatim-message-equality` content and the `---` separator at line 219; no other modifications
- **Markdown sanity (optional)**: open in VS Code preview or run a markdown linter — no syntax errors

## Implementation Guidance

### Step 1: Draft `/README.md`

Create the file at `~/projects/the-one/README.md`. The structure (top to bottom):

1. **Hero**
   - Centered `<img>` of `the_one/interfaces/web/static/brand/gleepglorp_med.png` (use `<p align="center">` wrapper since GitHub markdown respects it; img `alt="GleepGlorp AI"`, width around 240-320px — readable but not overwhelming)
   - Below the image, the H1 title (`# GleepGlorp AI`) OR if the hero image already includes the wordmark visually, a smaller H2 or no title (decide at draft time — inspect the asset; the working hypothesis is the image is mascot-only, so include the H1)
   - Tagline immediately below: working text "Your local AI agent — LLM-agnostic, tool-rich, hand-rolled." Italicized, centered. Refine wording while drafting if a better phrasing surfaces; KEEP "self-modifying" OUT (the mission excluded it from README scope).

2. **What this is** (one paragraph, warm-narrative tone)
   - Conversational opening, talks to a fresh reader. Names that GleepGlorp AI is a personal AI agent the user runs locally; mentions the three functional areas (Chat for talking to agents, Studio for configuring them, Administration for system settings); references the agentic loop (tool use, multi-step problem solving) without going technical. Length: 4-7 sentences. Tone should feel personal but not gimmicky.
   - Draft seed (refine to taste): "GleepGlorp AI is your local AI agent — the kind that lives on your laptop, talks to whichever LLM you point it at, and reaches into your filesystem, your shell, and the open web through a rich set of built-in tools. You give it a goal in plain English; it figures out which tools to use, calls them, reads the results, and keeps going until the work is done. Configure agents in Studio (system prompts, which tools they can touch, which model powers them), talk to them in Chat (per-session, with the full execution trace one click away), and manage providers and built-in-tool defaults in Administration. Built without agent frameworks — every layer, from the agent loop to the LLM abstraction to the tool registry, is hand-rolled in plain Python."

3. **Screenshots** (placeholders only)
   - One H2 section titled `## Screenshots` (or merge into "What this is" — decide at draft time)
   - Three placeholders, in chat/studio/admin order:
     ```
     <!-- SCREENSHOT: chat-dark.png -->
     <!-- SCREENSHOT: studio-dark.png -->
     <!-- SCREENSHOT: admin-dark.png -->
     ```
   - One sentence below the placeholders mentioning that the app ships with a light theme too (so the dark-only shots in the README aren't misleading): "(Light theme is the default — Admin → General → Appearance has the toggle.)"

4. **Quickstart** (terse)
   - Two paths side by side or as alternative tabs:
     - **Local Python** (the simpler one for tinkering):
       ```bash
       pip install -e ".[all-llms,dev]"
       cp .env.example .env  # tweak THE_ONE_LLM_* defaults for your setup
       the-one chat          # CLI
       the-one serve         # web UI at http://localhost:8484
       ```
     - **Docker** (the production-shaped path):
       ```bash
       cp .env.example .env
       make rebuild          # build image + start container at localhost:8484
       make logs             # follow container logs
       make down             # stop
       ```
   - Brief one-line clarification that ollama is the default provider (so the user doesn't need an API key to start), and that adding `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` to `.env` enables those providers.
   - Reference: install command verified against `pyproject.toml:35` (`all-llms` extra) and `pyproject.toml:36` (`dev` extra). Port 8484 verified against `.env.example:13`. Default ollama provider verified against `.env.example:3` (`THE_ONE_LLM_PROVIDER=ollama`).

5. **Architecture overview** (six short paragraphs)
   - Open with a one-line note: "(For implementation depth, see `CLAUDE.md` and `the_one/agents.md`. The four-layer diagram there is the canonical implementation view; the six paragraphs below are the product-shaped view for orientation.)"
   - One paragraph per layer (2-4 sentences each):
     - **Interfaces** (`the_one/interfaces/`) — CLI (Rich + prompt-toolkit) and Web (FastAPI + WebSocket); both use `AgentFactory.create()` to spin up agents and call `agent.step()` to drive them. Web UI is vanilla JS + hand-rolled CSS, no frameworks.
     - **Agent** (`the_one/agent/`) — The agent loop. User input → LLM call → tool execution → repeat, capped at 20 iterations per step as a safety limit. `AgentConfig` (Pydantic) defines provider, model, system prompt, tool selection, behavior; `AgentFactory` resolves config from DB into a ready-to-use `Agent`.
     - **LLM** (`the_one/llm/`) — Abstract `LLMProvider` base with `complete()` and `stream()`. Lazy-loaded registry of three implementations (Ollama for local models, OpenAI, Anthropic). Adding a fourth means adding a `*_provider.py`, registering it, and writing one wire-shape adapter — patterns established in M03.
     - **Tools** (`the_one/tools/`) — 19 built-in tools: filesystem (read/write/edit/glob/grep), execution (shell + PTY sessions), Python interpreter, web (fetch/download/search), and an HTTP-request escape hatch. Each tool is a `Tool` subclass with a Pydantic `Config` for operator-set defaults; per-agent overrides narrow or substitute fields via the M05 resolver.
     - **MCP** (`the_one/mcp/`) — Model Context Protocol client (M07). Talks to external MCP servers over stdio or streamable-HTTP; sandboxed with bubblewrap by default (M07 F3); OAuth pause-and-replay for servers requiring user authorization (M07 F5).
     - **Persistence** (`the_one/db/`) — SQLite via aiosqlite. Agents, providers, MCP sources, chat sessions, and a Knowledge Base index live here. API keys and MCP secrets are encrypted at rest via Fernet symmetric encryption (M02); key rotation is exposed via `POST /api/encryption/rotate`.
   - Sources for paragraph content: cribbed from `CLAUDE.md:60-91` and `the_one/agents.md:9-30` (the four-layer diagram). Keep each paragraph to 2-4 sentences; resist the urge to include every detail.

6. **Security** (one-line section)
   - "GleepGlorp AI is a single-user local tool — no auth on routes by design. See [SECURITY-MODEL.md](SECURITY-MODEL.md) for the threat model, the Origin-allowlist middleware, the tool execution boundary, and what the model deliberately excludes."

7. **Project organization & methodology** (one sentence)
   - "The codebase is organized using [Mission Control](https://github.com/msieurthenardier/mission-control), an aviation-themed AI-first development methodology — missions, flights, and legs live under [`missions/`](missions/), and the per-mission artifacts there capture the design and execution history of every change."

8. **License / contributing** (optional, brief)
   - If a license file doesn't exist, skip — don't make claims about licensing in the README that aren't backed by a `LICENSE` file. (Verify with `ls ~/projects/the-one/LICENSE` before deciding.)
   - One-line "Contributions welcome — read a flight under `missions/` first to get oriented" is acceptable but optional.

### Step 2: Add the new convention entry to `the_one/agents.md`

Read the existing four-convention block at `the_one/agents.md:171-217` to match the structural shape (intro paragraph + Live example + Counter-example + optional clarifying paragraph). Insert the new block AFTER the `### verbatim-message-equality` block (which ends around line 217) and BEFORE the section-closing `---` separator at line 219.

**Working name suggestion**: `gated-debug-instrumentation` or `dual-channel-debug-gate` or `url-and-localstorage-activation-gate`. Pick at draft time. The name should describe the pattern, not the specific module.

**Content shape** (mirror the existing four for structural consistency):

```markdown
### {convention-name}

Debugging-only and measurement-only modules are gated by **both** a URL query-string flag and a `localStorage` key, capture the enabled state at module-load time, and short-circuit to no-ops when disabled. Production paths pay zero cost; the gate survives SPA navigation; activation is achievable both ad-hoc (URL) and persistently (localStorage).

**Live example**: `App.perf` (`the_one/interfaces/web/static/js/perf.js`) — gated by `?perf=1` in the URL query string OR `localStorage.getItem('the-one-perf') === '1'`. The `enabled` flag is captured at module-load time (the file's `isEnabled()` IIFE), and every public method (`mark`, `measure`, `captureHeap`, `dump`, `summary`) short-circuits when disabled. See **Performance Measurement (F7)** below (this section) for full operational mechanics including the activation procedure, browser-support caveats, and the four canonical measurement scenarios that consume the surface.

**Counter-example (what NOT to do)**: compile-time-excluding debug instrumentation via a build flag would break the project's "no build step for vanilla JS" architecture, AND would prevent operators from activating instrumentation on an already-deployed instance for ad-hoc diagnosis. Pre-compiling debug paths out of production also forecloses the "turn it on in production for one incident, turn it off after" workflow that the localStorage gate enables.

The pattern applies whenever a frontend module exists primarily to support diagnosis (perf measurement, debug logging, trace capture, etc.) and is not part of the user-facing feature surface. Future modules following this convention should mirror `App.perf`'s shape: a module-load-time `isEnabled()` gate, public methods that short-circuit when disabled, and one-line activation via either URL or localStorage. The two activation channels are intentional — URL is ad-hoc (no operator commitment), localStorage is sticky (survives reloads, useful for measurement campaigns).
```

Verify the entry uses the verbatim-message-equality block's structural template (intro + Live example + Counter-example + closing paragraph) so it visually slots into the existing four.

### Step 3: Verify markdown renders correctly

- Open `~/projects/the-one/README.md` in VS Code's markdown preview, or push the branch and view on GitHub
- Inspect: hero image loads, internal links (`SECURITY-MODEL.md`, `missions/`, Mission Control repo URL) resolve, the three screenshot placeholders are visible as HTML comments (so they don't render as broken images), code blocks for install/Docker have correct syntax highlighting
- For `agents.md`: inspect that the new convention entry visually slots between `### verbatim-message-equality` and the `## Dependency Graph` section break

## Edge Cases

- **Tagline wording reveals a problem**: If "Your local AI agent — LLM-agnostic, tool-rich, hand-rolled." reads awkwardly when seen below the mascot, iterate freely. Constraints: stay under ~80 characters, don't mention self-modification, don't claim features that don't exist (e.g. avoid "multi-agent" — the system is single-agent-per-session).
- **Hero image is too wide or includes the wordmark already**: Decide at draft time whether to keep the H1 title below the image or drop it. If the image dominates without wordmark, H1 stays. If the wordmark is baked in, drop H1 and go straight to the tagline. Inspect `the_one/interfaces/web/static/brand/gleepglorp_med.png` and decide.
- **Convention name collides**: If any of the suggested names (`gated-debug-instrumentation`, etc.) overlaps in spirit with an existing convention, pick a different one. Cross-check by reading the four existing entries' names at `agents.md:175,185,195,205`.
- **`pyproject.toml` install snippet drift**: If `pyproject.toml`'s `[project.optional-dependencies]` has changed between flight design and leg execution (e.g. the `all-llms` extra was renamed), update the README snippet AND flag in the flight log. The exact installable extras must match `pyproject.toml` verbatim.
- **`SECURITY-MODEL.md` link case sensitivity**: GitHub is case-sensitive for relative-path links on Linux backends. Use the exact filename casing: `SECURITY-MODEL.md` (uppercase, hyphen, `.md`).
- **No `LICENSE` file**: don't add license claims to the README; either skip the license section or use a placeholder pointing to "(license TBD)" — operator-explicit decision at draft time.
- **Mission Control repo URL**: Working hypothesis is `https://github.com/msieurthenardier/mission-control` (per `projects.md` for mission-control's remote). Verify by checking `projects.md` in mission-control's working tree, or default to the working hypothesis and let L03 alignment HAT catch drift.
- **`agents.md` line numbers drift during leg execution**: If another flight has shifted the `## Project Conventions` section's anchor line between flight design and leg start, use the symbol-based citation (`agents.md:## Project Conventions`) and locate via `grep -n "^## Project Conventions" the_one/agents.md` to find the correct insertion point.

## Files Affected

- `~/projects/the-one/README.md` — NEW; ~120-160 lines of markdown with hero + 6 sections
- `~/projects/the-one/the_one/agents.md` — MODIFY; one new `### {convention-name}` block (~15-25 lines) inserted under `## Project Conventions`, between the existing `### verbatim-message-equality` block and the section-closing `---` separator

No other files modified. No source code changed. No tests added or modified. No build artifacts produced.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [x] All acceptance criteria verified (run the Verification Steps grep commands; confirm each returns the expected matches)
- [x] Tests passing — N/A for this leg (no code touched). Verify the working tree's broad-pytest baseline is preserved by running `python -m pytest tests/ --tb=short -q --co` (collect-only) — collection error count should be zero
- [x] Update `flight-log.md` with a Leg Progress entry: changes made (`README.md` created; `agents.md` convention entry added), notes on any deviations from this leg artifact (tagline wording finalized, screenshot placeholder format, etc.)
- [x] Set this leg's status to `landed` (in this file's header) — NOT `completed`; Reviewer pass + commit happen next
- [x] Check off this leg in `flight.md` (the `readme-content-and-perf-convention` line under `## Legs`)
- [x] NOT the final leg — do NOT update flight.md status to `landed`; L02 and L03 remain
- [ ] Commit `README.md` + `the_one/agents.md` + artifacts (leg + flight log) together in a single commit; suggested message shape: `docs: add top-level README and gated-debug-instrumentation convention (F8 L01)` — DEFERRED to Phase 2d (Reviewer pass runs first per agentic-workflow protocol)

## Citation Audit

11 code-location citations verified against current code at leg design time:

| Citation | Classification | Notes |
|---|---|---|
| `the_one/agents.md:171` — `## Project Conventions` section anchor | OK | Verified via `grep -n "^## " the_one/agents.md`; line 171 matches |
| `the_one/agents.md:1503` — `## Performance Measurement (F7)` section anchor | OK | Verified same grep; line 1503 matches |
| `the_one/agents.md:1507-1511` — activation gate operational mechanics | OK | Read inline at design time; URL `?perf=1` + `localStorage.setItem('the-one-perf', '1')` documented |
| `the_one/agents.md:175,185,195,205` — existing four convention `### {name}` anchors | OK | Verified via Read offset=171 limit=60; `trust-the-runtime`, `canonical-import + convenience-re-export`, `structural-Protocol-satisfaction`, `verbatim-message-equality` at expected lines |
| `the_one/agents.md:217` — end of `verbatim-message-equality` block | OK | Verified via Read; content ends at "log messages" / "internal debug strings" paragraph |
| `the_one/agents.md:219` — `---` separator before `## Dependency Graph` | OK | Verified |
| `the_one/agents.md:11-27` — four-layer architecture diagram | OK | Verified via Read offset=1 limit=120 in prior /flight pass |
| `the_one/interfaces/web/static/js/perf.js:1-16` — `App.perf` public surface comment block (precedes IIFE at line 17) | OK | Verified via Read; public surface methods (`enabled`, `mark`, `measure`, `captureHeap`, `dump`, `summary`, `reset`) documented at lines 6-13; continuation comments lines 14-16 |
| `the_one/interfaces/web/static/brand/gleepglorp_med.png` — hero mascot asset | OK | Verified via `find` in flight design |
| `the_one/interfaces/web/app.py:129` — `app = FastAPI(title="GleepGlorp AI", lifespan=lifespan)` | OK | Verified via grep at flight design; rebrand surface confirmed |
| `pyproject.toml:36` `dev` extra / `pyproject.toml:35` `all-llms` extra | OK | Verified via Read offset=1 limit=50; lines 35-36 are the extras definitions in `[project.optional-dependencies]` |
| `Makefile:21-25` `rebuild` target (`.PHONY` line at 21, recipe header at 22, body lines 23-25) | OK | Verified via Read offset=1 limit=60; full target declaration spans lines 21-25 |
| `.env.example:3` `THE_ONE_LLM_PROVIDER=ollama` / `.env.example:13` `THE_ONE_PORT=8484` | OK | Verified inline at flight design |
| `CLAUDE.md:60-91` architecture reference | OK | Verified via Read; layers and feature areas documented |

All citations verified clean at leg design time. No drift, no `gone` items, no `unverifiable` citations.
