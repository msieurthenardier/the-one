# Flight: Professional README

**Status**: landed
**Mission**: [GleepGlorp AI Rebrand & UX Polish](../../mission.md)

## Contributing to Criteria

- [x] The project's top-level documentation introduces GleepGlorp AI as a product — what it is, what it does, how to run it, how it is structured, and where to read the security model — without requiring the reader to dig through code or per-mission artifacts

---

## Pre-Flight

### Objective

Create a top-level `README.md` that introduces GleepGlorp AI as a product to anyone landing on the repository cold — an external developer, a future self, an LLM. The README opens with the medium mascot above a tagline, a warmly-narrative one-paragraph "what this is", then steps down into a terse install/run quickstart, a per-layer architecture overview (one short paragraph per layer), a link to `SECURITY-MODEL.md`, and a one-sentence pointer to the `missions/` artifact tree and the Mission Control methodology repo. Three dark-theme screenshots (Chat, Studio, Administration) — captured by the operator from a realistically-seeded instance — anchor the document visually. As a small side scope, the `?perf=1`/`localStorage` debugging gate pattern (introduced in F7's `App.perf` module) is promoted to a documented convention in `the_one/agents.md` so future debugging-only modules mirror it deliberately.

### Open Questions

- [ ] Final tagline wording — resolved during L01 design. Working hypothesis: "Your local AI agent — LLM-agnostic, tool-rich, hand-rolled." (Self-modification is intentionally OUT of the tagline since the mission decision excludes Concourse CI / self-mod from README scope — the tagline must not contradict the body.)
- [ ] Screenshot viewport dimensions — resolved during L02 setup (working hypothesis: 1440×900 DPR 1 captured via OS or browser DevTools "full page" screenshot; consistent across the three shots)
- [ ] Seeded-demo agent content for screenshots — resolved at L02 setup (working hypothesis: one agent named "GleepGlorp" with a short chat exchange that exercises the trace UI; one provider configured; one custom tool config visible in Admin)
- [x] Does the README cover Concourse CI and self-modification? → No. Resolved at design time per operator direction: README scope stays on what an external reader installing the app needs; CI / self-mod is operator-internal and lives in deeper docs.
- [x] Screenshot capture strategy → Manual operator capture into `docs/screenshots/`. Resolved at design time.
- [x] Architecture overview depth → Per-layer mini-paragraph (Interfaces, Agent, LLM, Tools, MCP, Persistence). Resolved at design time.
- [x] Six-paragraph slicing vs `agents.md`'s four-layer diagram → Deliberate audience-driven divergence (README addresses external readers; `agents.md`'s four-layer diagram addresses implementers). L01 notes this in copy so a cross-referencing reader isn't confused. Resolved at design review (Architect-flagged).

### Design Decisions

**README as product entry, not reference**: The README is shallow on purpose — a single screen-and-a-half that answers "what is this, how do I run it, where do I go for depth". `CLAUDE.md` and `the_one/agents.md` remain the reference-depth surfaces; the README links into them rather than duplicating their content.
- Rationale: Drift is the worst README failure mode. The closer the README stays to product-level framing, the less it lies as the system evolves.
- Trade-off: A reader who wants implementation depth has to click through. Acceptable — they're the wrong audience for the README anyway.

**Warmly-narrative voice for the opening, terse elsewhere**: The one-paragraph "what this is" reads conversationally; install/architecture/security sections are terse and scannable.
- Rationale: Personal-project READMEs that open warmly are more inviting; once the reader is hooked, dense scannable sections respect their time.
- Trade-off: Tone shift across the document; mitigated by keeping the warm section visually separated (above install).

**Manual operator screenshot capture into `docs/screenshots/`**: Three dark-theme shots — `chat-dark.png`, `studio-dark.png`, `admin-dark.png` — captured by the operator from a manually-seeded instance, committed to `docs/screenshots/`. No Playwright fixture, no checked-in capture script.
- Rationale: Screenshots refresh rarely; an automated fixture is over-engineering for a thrice-a-year regeneration. `docs/screenshots/` is non-gitignored (unlike `tests/browser/__snapshots__/` which is gitignored per `.gitignore:19`).
- Trade-off: Reproducibility depends on operator effort and discipline. Mitigated by an L02 procedure documenting the exact pre-conditions (theme, viewport, seeded state, what to crop) so a future regeneration converges on the same shots.

**Three dark-theme shots, no light-theme parity in README**: README copy mentions light/dark themes; the embedded shots are dark-only.
- Rationale: Halves the capture cost, keeps README weight down, and dark theme is the project's default visual identity. The pixel-snapshot test suite (gitignored) covers light/dark parity automatically as regression infrastructure — README is for product presentation.
- Trade-off: A reader who wants to see light theme has to install and toggle. Acceptable.

**Realistic seeded demo state for screenshots, not empty states**: Chat shows a populated exchange (ideally with the per-response trace expanded so F5's structural change is visible); Studio shows at least one configured agent; Admin shows at least one configured provider and a tool config tile.
- Rationale: The mission's "looks like a serious product rather than a developer prototype" criterion is harder to communicate with empty states. A populated UI is what someone evaluating the project actually needs to see.
- Trade-off: Operator has to set up a representative state before capture; risk of context leak (real agent names, real conversation content) — mitigated by L02 procedure prescribing a clean demo identity.

**Per-layer architecture overview, single short paragraph each**: Six layers (Interfaces, Agent, LLM, Tools, MCP, Persistence), each 2-4 sentences in the README — short enough to be skimmable, long enough to convey what the layer does.
- Rationale: Reader gets a complete shape of the system without 1600 lines of `agents.md`. Each paragraph ends pointing into the reference doc for depth.
- Trade-off: Six paragraphs is more weight than a "short prose only" option, but the project genuinely has six load-bearing modules and the paragraph-per-layer shape stays scannable.

**Mission/flight pointer is one sentence, not a methodology primer**: README states that artifact tree shape ("`missions/`, flights, legs live under `missions/`") and links to the Mission Control repo for the methodology itself.
- Rationale: Most README readers don't need to learn the methodology — they need to know the artifacts exist and where to read about them if curious.
- Trade-off: A contributor inheriting the codebase still has to click through to learn the methodology. Acceptable — the artifacts themselves are self-explanatory if you read one.

**`?perf=1` convention promotion lands as a named convention under `agents.md` `## Project Conventions`**: The F7-debrief action item (promote `App.perf`'s URL+localStorage gate to a documented convention so `App.debug`/`App.trace`/etc. mirror it) lands as a NEW named convention peer of the existing four (`trust-the-runtime`, `canonical-import + convenience-re-export`, `structural-Protocol-satisfaction`, `verbatim-message-equality`) at `the_one/agents.md`'s `## Project Conventions` anchor (line 171). It does NOT duplicate the activation mechanics already documented in the F7 perf-scenarios operational section (`agents.md:1505+`) — it cross-links to that section as the canonical live example.
- Rationale: `agents.md` is already the canonical conventions home, and the existing convention entries are well-shaped peers. The F7 perf-scenarios section already covers operational mechanics — the convention entry is for the pattern itself ("debugging-only modules use a URL + localStorage gate, short-circuit when disabled, never compile-time excluded") with a pointer to `App.perf` as the reference implementation.
- Trade-off: `agents.md` grows another short Convention entry; balanced by keeping it tight (~10-15 lines) and explicit cross-reference to the operational doc to prevent duplication drift.

**Leg boundaries: FD-mechanical work and operator-manual work do not share a leg**: L01 (README content draft + `agents.md` convention addition) is wholly FD-mechanical — content editing, no app boot, no visual judgment. L02 (screenshots) is operator-heavy — boots the app, seeds demo state, captures images, judges crops and content. The convention addition moves into L01 rather than L02 to honor this boundary.
- Rationale: Architect-flagged at design review. The two have different failure modes (typo in content vs. data leak in screenshot), different actors (FD agent vs. operator-with-app-running), and different review gates (cold-read vs. visual). Conflating them muddles the commit boundary.
- Trade-off: L01 grows slightly (README content + ~15 lines of agents.md); L02 simplifies to "screenshots + image wiring in README." Net win on cohesion.

**L01 uses HTML-comment placeholders for screenshots, not `<img>` tags**: Between L01 (READMEcontent lands without screenshots) and L02 (screenshots commit), the README on the branch must render without broken-image icons. L01 uses `<!-- SCREENSHOT: chat-dark.png -->` markers; L02 replaces them with `<img>` references and commits the PNGs in the same commit.
- Rationale: Architect-flagged. A broken-image-icon intermediate state would be embarrassing if the L01 branch is pushed for review before L02 lands.
- Trade-off: L02 must locate-and-replace the placeholders rather than fill in stubs. Mechanically trivial; grep `<!-- SCREENSHOT:` finds all of them.

### Prerequisites

- [x] F7 (UI Performance Audit) is landed and on `main` — README screenshots reflect post-F7 polish and performance state
- [x] Brand assets exist under `the_one/interfaces/web/static/brand/` — verified during Phase 1b recon (`gleepglorp_med.png`, mascot variants, favicons all present)
- [x] `SECURITY-MODEL.md` exists at repo root with current content — verified during recon (141 lines, current)
- [x] `CLAUDE.md` and `the_one/agents.md` are current — verified during recon (443 and 1668 lines, mission-aware)
- [ ] Operator can boot the app via `make rebuild-clean` and seed a demo state for screenshots (Docker + Playwright Chromium baseline) — verified at L02 setup
- [x] No top-level `README.md` exists yet — verified (only `.flightops/README.md` and `.pytest_cache/README.md` repo-wide)

### Pre-Flight Checklist

- [x] All open questions resolved (3 remaining lock at leg-design time per design decisions)
- [x] Design decisions documented
- [x] Prerequisites verified
- [x] Validation approach defined
- [x] Legs defined

---

## In-Flight

### Technical Approach

The flight delivers a single new file at the repo root (`README.md`) plus a new committed directory (`docs/screenshots/`) plus a small surgical edit to `the_one/agents.md`. No source-code changes, no migrations, no test-suite changes — this is a documentation flight.

**L01 (README content + perf-gate convention)** is FD-mechanical content work, wholly written from existing-source-of-truth references with no app boot required.
- (a) Writes `README.md` end-to-end with three HTML-comment placeholders (`<!-- SCREENSHOT: chat-dark.png -->` etc.) where images will go in L02. Content is structured as: hero (centered medium-mascot `<img src="the_one/interfaces/web/static/brand/gleepglorp_med.png">` + tagline below) → one-paragraph "what this is" (warm tone) → install/run quickstart (cribs `pip install -e ".[all-llms,dev]"` and `make rebuild` from `CLAUDE.md` + `pyproject.toml`; this verbatim duplication is acknowledged drift risk — see Design Decision) → per-layer architecture overview (six short paragraphs: Interfaces / Agent / LLM / Tools / MCP / Persistence) with explicit note that this six-paragraph slicing is audience-driven and deliberately diverges from `agents.md`'s four-layer diagram → link to `SECURITY-MODEL.md` → one-sentence pointer to `missions/` + Mission Control repo.
- (b) Adds a new named convention entry under `agents.md`'s `## Project Conventions` section (anchor at line 171), peer of the existing four conventions, naming the URL + localStorage debugging-gate pattern and cross-linking to the F7 perf-scenarios operational doc (`agents.md:1505+`) as the live example. Does NOT duplicate the activation mechanics.

**L02 (screenshots + image wiring)** is operator-heavy work.
- Operator boots a fresh instance via `make rebuild-clean`, seeds a demo state per a procedure documented inline in the leg artifact (one agent named "GleepGlorp" with a short representative chat exchange, one configured provider, one tool config visible in Admin). Captures three dark-theme screenshots: Chat with trace expanded, Studio with agent editor visible, Admin with providers grid populated. Saves as `docs/screenshots/{chat,studio,admin}-dark.png`. The READMe's L01 placeholders are replaced with `<img>` references to those files (single commit alongside the PNGs so the branch never has broken-image icons).
- Explicit data-leak gate: operator visually verifies no personal data, real conversation content, or real-world agent names appear in any committed PNG before commit. The committed PNGs are public-repo artifacts.

**L03 (alignment HAT)** is a non-optional cold-read pass. Either the operator reads the README from a fresh-context perspective, or asks a fresh-context model to do the same, and surfaces anything confusing, inaccurate, or stylistically off. Cold-read MUST explicitly verify the install snippet against current `pyproject.toml` (the one acceptable duplication identified at design time). Fixes apply inline. When the operator is satisfied, the leg closes — and with it, the flight, and the mission.

The flight is content-only — no leg requires `make rebuild` for compiled-code reasons (although L02 uses `make rebuild-clean` to get a clean demo state for screenshots). Test impact is zero new tests, zero regressions expected.

### Checkpoints

- [ ] L01 lands: `README.md` exists at repo root, contains all required sections (hero / one-para "what this is" / install / per-layer architecture / security link / mission pointer), `<!-- SCREENSHOT: ... -->` placeholders are explicit and locatable via grep, `agents.md` `## Project Conventions` section has the new named convention entry referencing `App.perf` as the live example
- [ ] L02 lands: three dark-theme screenshots committed under `docs/screenshots/{chat,studio,admin}-dark.png`, README's L01 placeholders are replaced with `<img>` references, README renders correctly on GitHub's markdown preview, operator-verified no data-leak in committed PNGs (no real conversation content, no personal data, no real-world agent names)
- [ ] L03 lands: alignment HAT completed; install snippet verified against current `pyproject.toml`; README reads cleanly cold

### Adaptation Criteria

**Divert if**:
- L01 content draft surfaces that any "user-facing" surface still reads as "the-one" rather than "GleepGlorp AI" — this would be an F1 brand-foundation regression and gets a Known Issue carry-forward (likely fix as inline opportunistic if trivial, otherwise a follow-up flight)
- L02 screenshots reveal a visual regression introduced by F7 that wasn't caught in the F7 HAT — log to flight log, scope-decide whether to fix inline or carry forward
- L03 cold read surfaces a structural inaccuracy (e.g. an architecture paragraph that describes the layer wrong) — fix inline, no diversion

**Acceptable variations**:
- Tagline wording iterates during L01
- Screenshot viewport dimensions adjust if 1440×900 produces awkward crops
- Demo seeded state adjusts if the initial mock looks too sparse
- Per-layer paragraph wording iterates freely; structure stays as "six short paragraphs"
- `agents.md` `?perf=1` subsection placement (under an existing Conventions section vs. its own new subsection) decided at L02 implementation

### Legs

> **Note:** These are tentative suggestions, not commitments. Legs are planned and created one at a time as the flight progresses. This list will evolve based on discoveries during implementation.

- [x] `readme-content-and-perf-convention` - Write `README.md` with all sections (screenshot placeholders as HTML comments); add the `?perf=1` URL+localStorage gate convention entry under `agents.md`'s `## Project Conventions`. FD-mechanical content work.
- [x] `screenshots-and-image-wiring` - Capture three dark-theme screenshots from a seeded demo, commit them under `docs/screenshots/`, replace L01 placeholders with `<img>` references. Operator-heavy with explicit data-leak gate.
- [x] `alignment-hat` - Cold-read HAT; verify install snippet against current `pyproject.toml`; surface and fix anything confusing or inaccurate. Closes the flight and the mission.

---

### Out of Scope (carried elsewhere)

F7 (UI Performance Audit) debrief action items other than the `?perf=1` convention promotion are intentionally NOT in this flight per operator direction. They remain in F7's debrief action-item list at `missions/08-gleepglorp-rebrand/flights/07-ui-performance-audit/flight-debrief.md` for a future maintenance flight: Playwright `CDPSession` parity recipe, `BYTES_PER_TOKEN`/threshold naming consolidation, `AgentFactory(store=...)` wiring docstring, `BYTES_PER_TOKEN` heuristic accuracy parametrized test, `test_provider_api::test_ollama_models` `AsyncMock` warning investigation, browser test for `session_joined` eager-fetch failure path, "live-read across lazy-resolver boundary" pattern codification, `AnthropicProvider` raw-event iteration refactor.

---

## Post-Flight

### Completion Checklist

- [ ] All legs completed
- [ ] `README.md` at repo root renders correctly on GitHub's markdown preview (operator-verified by pushing branch and viewing on GitHub, or by local markdown preview)
- [ ] `docs/screenshots/` contains the three dark-theme images and they are not gitignored (verify against `.gitignore` after commit — no `docs/` entry should mask them)
- [ ] No real-world data leak in committed screenshots — operator visually confirmed before commit
- [ ] `the_one/agents.md` `## Project Conventions` section contains the new named convention entry referencing `App.perf` as the live example
- [ ] Install snippet (`pip install -e ".[all-llms,dev]"`) cross-verified against current `pyproject.toml` (`[project.optional-dependencies]` section) during L03 cold read
- [ ] Mission criterion "The project's top-level documentation introduces GleepGlorp AI as a product..." checked off
- [ ] Mission `08-gleepglorp-rebrand` ready for `/mission-debrief`

### Verification

How to confirm the flight achieved its objective:
- **README renders correctly**: open the file in a markdown-aware viewer (VS Code preview, GitHub web UI on the branch, or any markdown previewer); all images load, all internal links resolve, no broken syntax
- **README is self-contained for product entry**: a fresh reader can answer "what is this", "how do I run it", "how is it structured", "where is the security model documented", "where do contributors look for project artifacts" without leaving the README
- **Screenshots accurately reflect the polished UI**: each shot shows the GleepGlorp AI brand, dark theme, populated demo state; nothing leaks personal/real data; viewports are consistent
- **`agents.md` perf-gate convention**: subsection exists, references `App.perf` as the reference example, is locatable from the table of contents / structure
- **Mission completion**: the README satisfies the final unchecked mission criterion; running `/mission-debrief` is unblocked
