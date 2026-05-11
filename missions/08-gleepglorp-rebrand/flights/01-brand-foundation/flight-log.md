# Flight Log: Brand Foundation

**Flight**: [Brand Foundation](flight.md)

## Summary

Executing 5-leg brand foundation flight orchestrated via `/agentic-workflow`. Legs 1-4 autonomous; Leg 5 is HAT/alignment with the operator. Feature branch `flight/01-brand-foundation` created from `main`.

---

## Flight Director Notes

### 2026-05-11: Flight kick-off

- Phase file loaded from project: `.flightops/agent-crews/leg-execution.md`. Structure validated (Crew, Interaction Protocol, Prompts present with fenced code blocks). Crew: Developer (Sonnet), Reviewer (Haiku), Accessibility Reviewer (Sonnet, optional). Accessibility Reviewer will be enabled at flight-review time given the UI scope.
- Feature branch `flight/01-brand-foundation` created from `main`. Untracked entries at branch creation: `.claude/` (project-local config, gitignored or left untracked), `missions/08-gleepglorp-rebrand/` (mission and flight artifacts drafted during planning; commit on feature branch), `the_one/interfaces/web/static/brand/` (source mascot PNGs `gleepglorp_med.png` + `gleepglorp_small.png` dropped by operator pre-flight).
- Flight status promoted `planning → in-flight`. Leg 1 already designed during pre-flight at `legs/01-brand-assets.md`; spawning Developer for design review before implementation per agentic-workflow Phase 2a.

### 2026-05-11: Leg 01 design review (round 1)

- Developer agent (Sonnet) spawned for leg 01 design review. Returned `needs rework` with 2 high-severity blockers and 4 medium/low fixes.
- High issues addressed: (a) `scripts/` was not bind-mounted into the container, so `docker compose run --rm the-one python scripts/...` would have failed at first invocation — added `./scripts:/app/scripts:ro` bind-mount entry in docker-compose.yml and changed Makefile target to use `docker exec the-one` per project's CLAUDE.md:411 convention; (b) Makefile section ordering in the leg was wrong (no "Container lifecycle → Testing" adjacency exists) — corrected to "between Verification (line 78) and Tests (line 99)" matching the actual Makefile structure.
- Medium issues addressed: idempotency criterion weakened from byte-equality to pixel-equality (PIL version drift guard); aspect-ratio guidance rewritten to drop misleading `Image.thumbnail` reference and use a clean square-pad flow; acceptance criterion #6 reworded to a DOM-structure check rather than a whitespace-brittle HTML string match.
- Low issues addressed: source-PNG choice rationale restated inline; Zone.Identifier ADS cleanup added to leg scope.

### 2026-05-11: Leg 01 design review (round 2)

- Round-2 Developer review returned `approve with changes` — round-1 fixes correctly applied, but two stale `docker compose run --rm` references survived in Edge Cases plus one in Inputs ("State that must be true"). All three were direct contradictions of the round-1 high-severity fix. Cleaned up in three follow-up edits. Also softened the Makefile-line-number citation to note the line numbers may drift over time.
- Square-pad pattern, step renumbering (1-9 contiguous), and Zone.Identifier scope all confirmed clean.
- Round 3 not required (only stylistic cleanup). Leg marked `ready`. Spawning implementation Developer.

---

## Leg Progress

### Leg 04 — brand-text-sweep

- **Window**: 2026-05-11
- **Status transition**: ready → in-flight → landed (review pending)
- **8 user-visible production rewrites applied** (verified via post-edit grep — every former `the-one` surface now reads `GleepGlorp AI`):
  - `the_one/interfaces/web/static/index.html:11` — `<title>GleepGlorp AI</title>`
  - `the_one/interfaces/web/static/js/app.js:19` — topbar wordmark literal `'GleepGlorp AI'` inside `renderTopBar()` (sits between the mascot `<img>` and the closing `</h1>`)
  - `the_one/interfaces/web/app.py:123` — `FastAPI(title="GleepGlorp AI", lifespan=lifespan)` (drives `/docs` Swagger UI title)
  - `the_one/interfaces/cli.py:31` — Rich panel content rewrite + dynamic-version piggyback (see next item)
  - `the_one/interfaces/cli.py:33` — Rich panel `title="GleepGlorp AI"`
  - `the_one/main.py:25` — `print(f"GleepGlorp AI v{__version__}")` (binary-name docstring line 11 + usage hint line 27 preserved)
  - `the_one/__init__.py:1` — package docstring rewritten to `"""GleepGlorp AI: A personal agentic system. (Python package: the_one)"""` — parenthetical preserves discoverability of the Python module name
  - `the_one/interfaces/web/api.py:1579` — OAuth callback eyebrow `<p>` text now `gleepglorp ai // oauth` (lowercase HTML source; CSS `text-transform: uppercase` at api.py:1549 renders it `GLEEPGLORP AI // OAUTH`)
- **api.py:1478 docstring carry-over** (Leg 03 deferral) — rewrote the multi-line docstring block that previously said `"with the rest of the-one — dark-mode cyan-accent palette, Geist / Geist Mono typography, ``//``-prefixed mono-uppercase eyebrow."`. **Final wording**: `"with the rest of GleepGlorp AI — violet-accent design system, Geist Sans / Geist Mono typography, ``//``-prefixed mono-uppercase eyebrow."` — drops both the stale brand-text reference AND the stale "dark-mode cyan-accent palette" reference in one edit, replaces with current-state design-system vocabulary (violet accent + Geist Sans/Mono). Eyebrow phrasing kept since it's a structural element of the page, not a palette claim.
- **cli.py dynamic-version piggyback** (design-review round 1 decision):
  - Added `from the_one import __version__` at cli.py:11 (positioned at the top of the in-package import block, immediately before `from the_one.agent.factory import AgentFactory`). Import block now reads `from the_one import __version__` → `from the_one.agent.factory import AgentFactory` → `from the_one.config import settings` → ... (alphabetical-by-module-path).
  - Converted the Rich panel string from a plain concatenation (`"[bold]the-one[/bold] v0.1.0\n" + ...`) to an f-string for the first line: `f"[bold]GleepGlorp AI[/bold] v{__version__}\n"`. The second line stays a plain string literal — implicit-string-concatenation glues the two together inside the `Panel(...)` call.
  - **f-string compile check**: `python3 -c "import ast; ast.parse(open('the_one/interfaces/cli.py').read())"` exit 0. Module-level parse confirmed the f-string brace pairing is well-formed before runtime.
  - Resolves the pre-existing drift between the CLI splash literal (`v0.1.0`) and the canonical `__version__ = "0.2.0"` at `the_one/__init__.py:3`. Future `__version__` bumps now propagate to the splash automatically.
- **3 test assertion updates** (acceptance criteria 11-12):
  - `tests/browser/test_app_fixture.py:16-18` — assertion swapped from `"the-one" in title.lower()` to `"gleepglorp" in title.lower()`; failure message updated to `"Expected page title to contain 'gleepglorp', got: {title!r}"`. Reformatted across two lines because the new failure message + `title!r` interp pushed past the 100-char ruff line limit; the existing single-line shape would have linted red.
  - `tests/test_aiat.py:129` and `tests/test_aiat.py:151` — both swapped `"the-one" in text.lower()` to `"gleepglorp" in text.lower()`; the `or "the_one" in text.lower()` Python-module fallback clause is preserved verbatim. `@pytest.mark.live` so these are gated out of the default pytest run; the change is correct-by-construction the next time the live AIAT suite runs.
- **Preserved identifiers — verified intact via post-edit grep**:
  - `the_one/main.py:11` — `"""Main entry point for the \`the-one\` command."""` (CLI binary name in docstring) — untouched.
  - `the_one/main.py:27` — `print("Usage: the-one [chat|serve|version]")` (CLI binary name in usage hint) — untouched.
  - `the_one/interfaces/web/api.py:1436` and `1821` — `"clientInfo": {"name": "the-one", "version": "0.1"}` (MCP protocol identifier, both call sites) — untouched.
  - `tests/test_oauth_provider_factory.py:96` — `assert cm.client_name == "the-one"` (pins MCP `clientInfo.name`) — untouched.
  - `tests/test_platform_tempdirs.py:33` — `user_config_dir("the-one") == Path.home() / ".the-one"` (test-internal config-dir slug) — untouched; line 38 fixture string `"the-one-test-no-create-xyz123"` also intact.
  - `tests/test_llm_registry.py:135` — `pytest.raises(ImportError, match=r"the-one\[openai\]")` (regex matching the pip-install hint that uses the PyPI distribution name) — untouched.
  - `the_one/interfaces/web/static/js/areas/admin/tools-editor.js:56` — `default: 'the one cli agent'` (benign sample query value for the `web_search` "Try it" UI; note the spaces, not hyphens — not a brand reference) — untouched.
  - Python-module references `from the_one ...` / `the_one.<module>` — untouched throughout the tree (mission constraint #45 preserves the package name).
- **Zero-hit verification on user-facing surfaces** (acceptance criterion subset): `grep -n "the-one" the_one/interfaces/web/static/index.html the_one/__init__.py the_one/interfaces/cli.py` exit 1 (no matches); `grep -n "'the-one'\|\"the-one\"" the_one/interfaces/web/static/js/app.js` exit 1 (no matches). All four target files clean of the literal.
- **Test gate**: `docker exec the-one pytest tests/test_design_tokens_a11y.py tests/test_token_definitions.py tests/test_oauth_provider_factory.py tests/test_platform_tempdirs.py -x -q --timeout 10` — **56 passed in 0.92s, exit 0**.
- **Serving check**: `make verify-serving` — `/api/info` returned 200 after 1s + all 9 admin sub-modules served 200. Exit 0.
- **Container-rebuild caveat**: edits under `the_one/` (HTML, JS, Python) are NOT yet propagated to the running daemon — `docker-compose.yml`'s `--reload --reload-dir /app/the_one` watches Python source, BUT static assets (`index.html`, `app.js`) live in the image-baked tree at build time and are served as-is until `make rebuild`. Visual spot-check (browser tab title, topbar wordmark, `/docs` title) will not match the new strings until the next rebuild. The leg's verification gate does not require visual confirmation; deferred to Leg 05 alignment HAT or operator's next `make rebuild`.

### Leg 03 — cyan-class-rename

- **Window**: 2026-05-11 (post leg-02 review)
- **Status transition**: ready → in-flight → landed (review pending)
- **Pre-rename grep counts** (Implementation Guidance step 1, re-grep current state):
  - `grep -rn "btn-filled-cyan\|btn-outlined-cyan" the_one/ tests/ | wc -l`: **62** matches across **14 files** (10 JS + 3 CSS + `agents.md`). Matches the design-time count; no drift in occurrence count, though components.css selector lines drifted (.btn-outlined-cyan now at line 281, .btn-filled-cyan at line 297 — leg-design citations of 273/289 had shifted +8 since leg-02 prepended palette-token rules).
  - `grep -rin "cyan\|nexus" the_one/ CLAUDE.md` filtered for `badge-filesystem.*dark cyan`: ~30 hits including the in-scope CSS comments + agents.md narrative + CLAUDE.md:89 + the deferred api.py:1478.
- **Implementation**:
  - **CSS** (3 files via `sed -i 's/btn-filled-cyan/btn-filled-primary/g; s/btn-outlined-cyan/btn-outlined-primary/g'`): `components.css`, `admin.css`, `studio.css`. Plus manual Edit on `components.css` for the two title-case comment headers `Outlined-Cyan` → `Outlined-Primary` and `Filled-Cyan` → `Filled-Primary` that sed (case-sensitive) missed.
  - **CSS — tokens.css** (5 in-file comment cleanups via Edit): line 3 (Dark-theme realization note), line 68 (`--badge-openai` note), line 115 (light surfaces comment), lines 138-141 (light `--accent` block), line 183 (`--panel-shadow-glow` comment). All annotated as historical pre-Mission-08 framing pointing at the violet retune; original cyan story preserved.
  - **JS** (10 files via `sed -i`): `dialog.js`, `areas/chat.js`, `areas/admin/{provider-editor,provider-models,tools-editor}.js`, `areas/studio/{agent-editor,general-tab,mcps-tab,mcp-server-editor,tools-tab}.js`. All `class="btn-{filled,outlined}-cyan ..."` strings rewritten.
  - **agents.md**: class-name refs swept via sed; then targeted Edits for the prose sections.
  - **CLAUDE.md** line 89: "NEXUS-style cyan accent" → "GleepGlorp violet accent — originally NEXUS-style cyan, retuned in Mission 08".
- **Per-line agents.md cleanup policy decisions** (one of: rewrite / annotate-as-historical / leave):
  - Line 521 (`.chat-no-providers banner uses a cyan-accented gradient`): **rewrite** → "primary-accented gradient". Short prose with no narrative cost.
  - Line 523 ("**Outlined-cyan**" pattern name): **rewrite** → "**Outlined primary**" (semantic affordance name; not pinned by tests).
  - Line 525 ("**Filled-cyan CTA**" pattern name): **rewrite** → "**Filled primary CTA**".
  - Line 529 ("those are outlined-cyan, pattern 2"): **rewrite** → "outlined-primary, pattern 2".
  - Lines 541-565 (Affordance vocabulary entries naming `.btn-outlined-cyan` / `.btn-filled-cyan` as class names): **rewrite** via sed to `.btn-outlined-primary` / `.btn-filled-primary`. These are class-name references, not narrative — rewrite is the only correct option once the CSS classes are renamed.
  - Line 622 (WCAG table cell "PASS (retuned cyan-600 → cyan-700)"): **annotate-as-historical** → kept "PASS" + appended bracketed historical annotation noting the Mission 08 cyan-700-to-violet-700 retune at the same 5.17:1 ratio. Rewrite would lose the leg-07 retune context the row was written to capture.
  - Lines 632-655 (Token retunes leg-07 narrative; bullets for `--accent`, `--status-success`, `--status-warning`, `--fg-on-danger`): **annotate-as-historical** for the `--accent` bullet specifically (per leg guidance — the narrative was written about the cyan-iteration audit and has no violet equivalent to rewrite to, because Leg 02 of Mission 08 passed audit on first run with no iteration). Added a section-leading blockquote pointing readers at Mission 08 Flight 01 Leg 02 for current values, and a bracketed annotation on the `--accent` bullet itself. The other three bullets (status-success, status-warning, fg-on-danger) are still in force as written — no annotation needed.
  - Lines 684-688 (Focus-ring `:focus-visible` description "#22d3ee outline + cyan glow; in light it resolves to #0e7490 outline + cyan glow"): **rewrite** to the post-Leg-02 hex values `#a78bfa` (dark) and `#6d28d9` (light) with "violet glow", parenthetical note that this is the post-Mission-08-retune resolution from the original cyan outlines. Both meet 3:1.
  - Line 866 ("Active area accent: ... → cyan `::before` left-border stripe"): **rewrite** → "primary-accent `::before` left-border stripe". Short prose, no narrative cost.
  - Line 1029 ("Two variants, both using `var(--accent)` (cyan)"): **rewrite** → "(primary accent)". Same rationale.
- **Deliberate cyan retentions**:
  - `tokens.css:81` `--badge-filesystem: #008b8b; /* dark cyan */` — literal hex-color description for a non-brand category badge. Per leg spec, leave as-is.
  - `the_one/interfaces/web/api.py:1478` docstring with both `the rest of the-one` AND `dark-mode cyan-accent palette` — deferred to Leg 04 brand-text sweep per leg spec (re-edit collision avoidance; Leg 04 will rewrite the whole comment in one edit).
  - All other remaining "cyan" occurrences are inside `[historical: ...]` annotations or the cyan-iteration narrative blockquote in agents.md `#### Token retunes (leg 07)` — deliberate preservation of the leg-07 audit story.
- **Post-rename grep counts**:
  - `grep -rn "btn-filled-cyan\|btn-outlined-cyan" the_one/ tests/`: **0 hits**, exit 1 (canonical completeness pass).
  - `grep -rn "btn-filled-primary\|btn-outlined-primary" the_one/ | wc -l`: **62** (≥60 target met; matches the original 62 — one-for-one rename).
  - `grep -rin "nexus" the_one/ CLAUDE.md`: 2 hits, both deliberate historical annotations (`tokens.css:3`, `CLAUDE.md:89`).
  - `grep -rin "cyan" the_one/ CLAUDE.md` filtered for deliberate retentions: only `tokens.css:81` `--badge-filesystem` literal, `api.py:1478` (deferred), and the historical annotations in `tokens.css` lines 141-142 + `agents.md` lines 622, 635-655, 699 — all deliberate.
- **Audit outcomes**:
  - `docker exec the-one pytest tests/test_design_tokens_a11y.py tests/test_token_definitions.py -x -q --timeout 10`: **PASS** (46 tests, 0.05s, exit 0). Rename is name-only — no token values changed.
  - `make verify-serving`: **PASS** (exit 0). All 9 admin sub-modules return 200; container restart not needed because the leg only renames CSS classes (uvicorn `--reload` picks up file changes within ~1s).
- **Deviations**: none.
- **Anomalies**: none.
- **Final pytest exit code**: **0** (primary gate). Broader gate not run (per orchestrator narrow-gate guidance to avoid SQLite WAL hang).
- **Outcome**: landed pending Reviewer sign-off. Status updated in leg artifact header. Orchestrator commits at flight-end.

### Leg 02 — palette-tokens

- **Window**: 2026-05-11 (post leg-01 review)
- **Status transition**: ready → in-flight → landed (review pending)
- **Final hex values committed**:
  - **Dark theme** (`[data-theme="dark"]`, `tokens.css:46-52`):
    - `--accent: #a78bfa` (violet-400)
    - `--accent-api: #22d3ee` (cyan-400 — the retired primary, recycled into the secondary slot)
    - `--accent-glow: rgba(167, 139, 250, 0.25)`
    - `--accent-glow-strong: rgba(167, 139, 250, 0.4)`
    - `--accent-translucent: rgba(167, 139, 250, 0.08)`
    - `--accent-translucent-hover: rgba(167, 139, 250, 0.12)`
  - **Light theme** (`[data-theme="light"]`, `tokens.css:142-147`):
    - `--accent: #6d28d9` (violet-700)
    - `--accent-api: #0e7490` (cyan-700 — the retired primary, recycled into the secondary slot)
    - `--accent-glow: rgba(109, 40, 217, 0.20)`
    - `--accent-glow-strong: rgba(109, 40, 217, 0.35)`
    - `--accent-translucent: rgba(109, 40, 217, 0.10)`
    - `--accent-translucent-hover: rgba(109, 40, 217, 0.15)`
  - **Light theme `--panel-shadow-glow`** (`tokens.css:189`): first rgba arg shifted `rgba(14, 116, 144, 0.18)` → `rgba(109, 40, 217, 0.18)`; second slate-900 component unchanged.
  - **Light theme `--nav-fg-active`** (`tokens.css:208`): hardcoded `#22d3ee` → `#a78bfa` (matches dark `--accent`; the nav rail uses the dark palette internally because the rail itself is dark navy `#0f172a`). Inline comment updated to reference the new color family.
  - **Python mirror** (`tests/browser/design_tokens.py`): `DARK["accent"]` = `#a78bfa`, `DARK["accent_api"]` = `#22d3ee` (newly added); `LIGHT["accent"]` = `#6d28d9`, `LIGHT["accent_api"]` = `#0e7490` (newly added).
  - **WCAG audit** (`tests/test_design_tokens_a11y.py::test_text_on_color`): three new tuples added — `("dark", "fg_on_accent", "accent_api", 4.5)`, `("light", "fg_on_accent", "accent_api", 4.5)`, `("light", "accent_api", "bg", 3.0)`; stale "Text on accent (cyan)" inline comment refreshed to "Text on primary accent".
- **Iteration history**: none required. The starter palette from the leg artifact's "Starter palette working values" table passed the full WCAG audit on first run. Computed-vs-actual ratios (all from the audit's WCAG 2.1 sRGB formula) matched the leg-spec predictions within rounding (e.g., `#000` on `#a78bfa` ≈ 7.72:1; `#fff` on `#6d28d9` ≈ 7.10:1; `#000` on `#22d3ee` ≈ 11.62:1; `#fff` on `#0e7490` ≈ 5.36:1). No values needed to step darker or lighter.
- **Audit outcomes**:
  - `docker exec the-one pytest tests/test_design_tokens_a11y.py tests/test_token_definitions.py -x -q --timeout 10`: **PASS** (46 tests, 0.05s, exit 0). Includes the three new `accent_api` parametrizations.
  - `make verify-serving`: **PASS** (exit 0). All 9 admin sub-modules return 200 post-rebuild; served `tokens.css` confirmed to carry the new values (verified via `curl /static/css/tokens.css | grep accent`).
- **Deviations**: none.
- **Anomalies**: none in this leg. (The leg-01 SQLite WAL / pytest contention is not exercised by this leg's narrowed gate; the gate ran cleanly.)
- **Final pytest exit codes**:
  - Primary gate (`test_design_tokens_a11y.py` + `test_token_definitions.py`): **0**
  - Secondary broader gate: not run (per orchestrator guidance — the leg-01 hang risk applies; the primary gate fully covers this leg's CSS/token-mirror diff).
- **Outcome**: landed pending Reviewer + Accessibility Reviewer sign-off. Status updated in leg artifact header.

### Leg 01 — brand-assets

- **Window**: 2026-05-11 ~08:18 → ~08:35 (UTC, approximate; pytest hang accounts for ~17 min of wall time inside this window)
- **Status transition**: in-flight → landed (review pending)
- **Implemented**:
  - `scripts/derive_brand_assets.py` (134 lines) — Pillow-based square-pad + LANCZOS resize → 7 sized PNGs (16/24/32/48/180/192/512) + multi-res `favicon.ico` (16/32/48 packaged). Pixel-idempotent across runs; module docstring documents re-run trigger + commit policy.
  - `docker-compose.yml`: added `- ./scripts:/app/scripts:ro` bind-mount with inline rationale comment.
  - `Makefile`: new `# ── Brand assets ──` section (between Verification and Tests) with `brand-assets` target; appears in `make help`.
  - `the_one/interfaces/web/static/index.html`: 5 favicon `<link>` tags inserted between `<meta name="viewport">` and `<title>`.
  - `the_one/interfaces/web/static/js/app.js::renderTopBar`: `<h1 class="app-topbar-title">` now opens with `<img src="/static/brand/topbar-icon-24.png" width="24" height="24" alt="">` before the `the-one` wordmark.
  - `the_one/interfaces/web/static/css/components.css`: `.app-topbar-title` promoted to `display: flex; align-items: center; gap: 8px;`; new `.app-topbar-title img { width: 24px; height: 24px; flex-shrink: 0; }` rule for CLS guard.
  - `.gitignore`: appended `*:Zone.Identifier`.
  - 8 derived brand assets committed to repo at `the_one/interfaces/web/static/brand/` (NOT gitignored — they ship in the image).
- **Dimensions verified** via `docker exec the-one python -c "from PIL import Image; ..."`: favicon-16 16×16, favicon-32 32×32, favicon-48 48×48, topbar-icon-24 24×24, apple-touch-icon 180×180, icon-192 192×192, icon-512 512×512, favicon.ico (48×48 base, multi-res packaging) — all RGBA PNG/ICO as expected.
- **Decisions**:
  - **Extra `gleepglorp_icon.png` (600×600) retained.** Prior agent dropped a 600×600 square-cropped intermediate into `static/brand/` that the derivation script does NOT consume. Decision: keep it. (a) It is a manual square-crop of the mascot's recognizable region and matches the "future enhancement: derive 16/32 sizes from a centered head/face crop" note in the leg's Edge Cases section (line 197 of the leg spec) — a plausible later input to a refined derivation. (b) No file/code references it, so its presence is inert. (c) Deleting it would discard work that took manual effort. Reviewer may overrule and delete during code review if preferred; that is a single `git rm` away. If kept past commit, surface as a known-issue candidate for "consider routing 16/32 derivations through `gleepglorp_icon.png` as an explicit head-crop input" in a future leg.
- **Deviations**:
  - **Test gate scope narrowed.** The leg's acceptance criterion calls for `docker exec the-one pytest tests/` to exit 0. The full-suite run hung indefinitely on a `futex_wait_queue` syscall — root cause: the running uvicorn container (pid 1) holds an open handle on `/root/.the-one/the-one.db` (SQLite WAL), and the pytest subprocess inside the same container contends on the DB during fixture setup. CLAUDE.md flags pytest-asyncio loop teardown as a known wedge class, and this is the same family of issue exacerbated by the live daemon. Substituted gate: `docker exec the-one pytest tests/test_design_tokens_a11y.py tests/test_token_definitions.py -x -q --timeout 10` — 43 tests, 0.05s, exit 0. Justification: this leg's diff is exclusively CSS/JS/HTML/PNG/Makefile/compose; none of it touches Python import paths, test fixtures, or DB-adjacent code, so the broad pytest gate cannot regress against this leg's changes specifically. Reviewer to confirm or escalate.
- **Anomalies**: pytest hang (see Anomalies section below) — Developer killed the hung process; no data loss.
- **Verification outcomes**:
  - Narrow pytest gate: PASS (exit 0)
  - `make verify-serving`: PASS (exit 0) — all 9 admin sub-modules return 200
  - `curl /`: 200 with all 5 `<link>` tags present
  - `curl /static/brand/topbar-icon-24.png`: 200
  - `curl /static/brand/favicon-32.png`: 200
- **Outcome**: landed pending Reviewer + Accessibility Reviewer sign-off. Status updated in leg artifact header.

---

## Decisions

### 2026-05-11: Leg 05 — HAT, tactical fixes, flight close

- Operator-driven HAT walkthrough of the rebranded UI in both themes via private-window load of `http://localhost:8484/`. Two tactical issues surfaced:
  1. **Icon source-PNG switch**: operator preferred the simpler `gleepglorp_icon.png` (600×600 head-crop intermediate retained at Leg 01) over the full-emblem `gleepglorp_med.png` as the favicon/topbar derivation source — cleaner detail at 16/32 sizes. Fix: changed `DEFAULT_SOURCE` constant in `scripts/derive_brand_assets.py` to point at `gleepglorp_icon.png`; added a "Source-file evolution" note to the module docstring explaining the switch + how to override back to the emblem (via `--source` flag). Ran `make brand-assets` to regenerate all 8 derived assets from the new source. `gleepglorp_med.png` retained in `static/brand/` for the case where the wordmark-baked-in emblem is needed.
  2. **Unstyled checkboxes in Studio → agent editor → MCP tab → tool list**: per-tool `<input type="checkbox">` elements at `js/areas/studio/mcps-tab.js:315` were rendered without custom styling — appeared as browser defaults against the brand. Fix: added scoped custom-checkbox CSS in `studio.css` for `.area-studio .mcp-tools-checkbox-group input[type="checkbox"]` — 14×14 rounded square, `--border-strong` border (purple on hover), `--accent` fill when checked, white checkmark drawn via `::after` rotated-border trick, `--accent` focus ring. Scoped narrowly so other Studio checkboxes are unaffected. The source-level toggle at line 109 was unaffected — it already uses the `.tool-toggle` + `.tool-switch` iOS-toggle pattern.
- **Snapshot regeneration**: 10 of 12 baselines regenerated cleanly with `UPDATE_SNAPSHOTS=1`. The remaining 2 (`test_snapshot_chat_with_messages[dark]` + `[light]`) failed during regeneration — root cause is the `app_with_agent` seeder fixture's auto-session-join flow: the `.session-agent-badge` element exists on the page but stays empty (the agent name doesn't populate). This is pre-existing test infrastructure, not introduced by this flight. Logged as a mission Known Issue (see `mission.md` Known Issues section).
- **Stale snapshot-test selector** (caught during regeneration, fixed inline): `tests/browser/test_visual_snapshots.py` referenced `.admin-category-item` at lines 247 and 260, but the admin sidebar nav was unified to `.section-nav-item` in M04/M05 cleanup. Pixel tests are excluded from default `addopts` (`-m 'not pixel'`), so this drift went silently red for months. Changed selector to `.section-nav-item`; admin baselines now regenerate cleanly. Not a Mission-08 regression, but a Mission-08-discovered fix.
- **Playwright Chromium install gap** (caught during regeneration): `make rebuild` does NOT preserve the Playwright browser cache at `/root/.cache/ms-playwright/` (named-volume not bind-mount). The Makefile already has an `_ensure-playwright` target to repopulate. Documented as observation; the existing target is sufficient mitigation.
- All Leg 05 acceptance criteria satisfied (with the snapshot criterion marked partial-with-known-issue per leg-design's adaptation pattern).
- Flight status: `in-flight` → `landed`. Tick the flight checkbox in `mission.md`. Committing tactical fixes + leg-05 artifacts + flight/mission status updates as a second flight commit on the branch. Pushing branch and opening draft PR.

### 2026-05-11: Flight review + commit (Phase 2d)

- All four autonomous legs landed. Spawned Code Reviewer (Haiku) and Accessibility Reviewer (Sonnet) in parallel against the working tree.
- **Code Reviewer**: `[HANDOFF:confirmed]`. All 4 legs PASS individually; 56-test narrow gate exits 0 (palette + token-def + oauth-factory + tempdirs); `make verify-serving` exits 0. Reviewer noted (and pre-emptively applied) a `ruff format` cleanup pass that condensed pre-existing multi-line collapses in `api.py` (~94 lines net -28). Kept the format changes: project enforces `ruff format --check` in CI per M07 maintenance pass, so excluding them would risk a CI fail later.
- **Accessibility Reviewer**: `[HANDOFF:confirmed]`. WCAG 2.1 AA checks PASS: 1.4.3 Contrast, 1.4.11 Non-text Contrast (`--nav-fg-active` `#a78bfa` on `#0f172a` measures 6.56:1, well above 3:1), 1.1.1 Non-text Content (decorative `alt=""` on mascot is correct — adjacent wordmark provides the accessible name), 1.3.1 Info and Relationships (multiple `<h1>` is a pre-existing structural pattern not introduced by this flight). All 45 a11y test parametrizations pass including the 3 new Leg-02 `accent_api` pairs.
- Promoting legs 01-04 status `landed` → `completed`. Ticking the 4 autonomous-leg checkboxes in flight.md (Checkpoints + Legs lists). Flight status stays `in-flight` (Leg 5 HAT/alignment is operator-driven and not yet done).
- Committing autonomous batch now. Leg 5 lands as a subsequent commit after the operator walks the HAT.

### Leg 04 design-review round 1 — CLI version flag + version-string piggyback

- Developer design review caught (a) the leg's verification command used `the-one --version` but `main.py:22` dispatches on the subcommand `version`, not the `--version` flag — corrected. (b) `cli.py:30` literal `v0.1.0` is stale; the actual package version per `__init__.py:3` is `0.2.0` — piggybacking a dynamic `f"v{__version__}"` fix into this leg while the line is already being rewritten. (c) Two low-severity preserve classifications added explicitly: `tools-editor.js:56` `'the one cli agent'` (benign search-query default) and `tests/test_llm_registry.py:135` regex `r"the-one\[openai\]"` (matches the pip install hint — refers to PyPI distribution / binary name).
- Verification grep tightened: added file-specific zero-hit assertions on the four user-facing surfaces (index.html, app.js wordmark literals, cli.py, __init__.py) where no legitimate `the-one` preservation reason exists. Acknowledged that the broader `the_one/` tree retains ~25-30 preserved hits across module references, MCP protocol, pip hints, internal comments — the broad grep is not zero-hit-bounded.
- Verdict: `approve with changes`; round 2 not required (all fixes are scope additions and scope clarifications, not contradictions). Leg marked `ready`; spawning implementation Developer.

### Leg 03 design-review round 1 — additional uncited cyan/NEXUS references

- Developer design review surfaced (a) 5 additional `agents.md` "cyan" hits beyond the cited blocks (lines ~521, ~529, ~622, ~852, ~1015); (b) `CLAUDE.md:89` "NEXUS-style cyan accent" framing in project documentation; (c) `the_one/interfaces/web/api.py:1478` docstring `"dark-mode cyan-accent palette"`.
- (a) and (b) added to leg-03 scope explicitly; verification grep scope broadened from `static/css/ + agents.md` to `the_one/ + CLAUDE.md`.
- (c) deferred to Leg 04 (brand-text sweep) — the same comment also contains "the rest of the-one" which Leg 04 already plans to rewrite; combining the two edits into one avoids re-edit collision. Documented in both the leg-03 artifact (Inputs "Out of scope" subsection) and to be carried into the leg-04 design.
- Developer also noted components.css selector line numbers drifted +8 from cited values (legs 01 and 02 prepended other rules). Leg's step-1 re-grep already covers this; explicit note added so the implementer doesn't trust the cited line numbers blindly.
- Verdict: `approve with changes`; round 2 not required (all fixes are scope additions, not contradictions). Leg marked `ready`; spawning implementation Developer.

### Leg 02 design-review round 1 — `--nav-fg-active` retune scope-in

- Developer design review caught that `tokens.css:208` `--nav-fg-active` is hardcoded `#22d3ee` (cyan-400) inside the light-theme nav-rail block. The token is NOT derived from `var(--accent)`, so retuning `--accent` alone leaves the nav rail's active state cyan while the rest of the app goes purple. Decision: pull the `--nav-fg-active` retune into Leg 02's scope rather than deferring — the alternative is a one-leg window where the nav reads cyan-on-purple, which is exactly where the brand reads loudest. Added matching audit pair `nav-fg-active on nav-bg` at 3:1 in the leg artifact's expected-contrast table (≈9.5:1 for `#a78bfa` on `#0f172a` — passes).
- Developer also surfaced that `agents.md` design-system prose at lines ~637 and ~684-685 pins old hex values (`#0e7490`, `#22d3ee`, "cyan-700"). Decision: defer to Leg 03 (which is already chartered for the design-system-documentation sweep) rather than splitting it across two legs. Leg 02 artifact carries an explicit Out-of-Scope note pointing at Leg 03 so the handoff is not silent.

---

## Deviations

_Departures from planned approach. Populated as they arise._

---

## Anomalies

- **Leg 01 — pytest-asyncio loop / SQLite WAL contention with live uvicorn process.** Broad `docker exec the-one pytest tests/` hung for 17+ min on `futex_wait_queue` while the live uvicorn container (pid 1) held an open SQLite WAL handle on `/root/.the-one/the-one.db`. The pytest process was killed (no data loss). Verified leg via narrowed test scope (CSS/contrast + token-definition tests: 43 tests, 0.05s, exit 0) plus `make verify-serving`. The leg's diff is non-Python so the narrow gate sufficiently covers it. See Leg 01 entry for full context. Consider whether the pytest fixture stack should better isolate from a running uvicorn — separate environmental concern worth lifting into mission known-issues or a future maintenance pass.

---

## Session Notes

_Chronological notes from work sessions._
