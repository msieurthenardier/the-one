# Leg: 04-brand-text-sweep

**Status**: completed
**Flight**: [Brand Foundation](../flight.md)

## Objective

Rewrite every user-visible "the-one" string to "GleepGlorp AI" across the browser tab title, topbar wordmark, FastAPI auto-docs title, CLI Rich welcome panel, version print, package docstring, and OAuth callback page; rewrite one carried-over docstring comment that mixed brand-text and cyan-palette references; update the three test assertions that pin the old brand text; preserve every protocol-level / binary-name / Python-module identifier as `the-one` / `the_one`.

## Context

- Leg 4 of 5 in Flight 1 (Brand Foundation). Legs 01-03 landed uncommitted on `flight/01-brand-foundation`: mascot favicon + topbar icon ship; `--accent` palette retuned cyan→violet; CSS class names + cyan-vocabulary docs sweep complete. The running app already renders purple with the mascot, but every user-visible *text* surface still says "the-one".
- This leg finalizes the rebrand by walking the per-surface decision table from the flight spec. The table is explicit; this leg is mostly mechanical.
- One carried-over scope item from Leg 03: `the_one/interfaces/web/api.py:1478` docstring contains BOTH "the rest of the-one" (brand-text) AND "dark-mode cyan-accent palette" (cyan vocabulary). Leg 03 deferred this to Leg 04 so the whole comment gets rewritten in one edit rather than split across two legs.
- Tests pin "the-one" in three places (verified at design time):
  - `tests/browser/test_app_fixture.py:16` — `assert "the-one" in title.lower()` — page title check; WILL break after rebrand and needs updating
  - `tests/test_aiat.py:129, 151` — `@pytest.mark.live` assertions checking agent introspection responses for "the-one" OR "the_one"; the agent's self-description responses will say "GleepGlorp AI" after this leg, so these need updating to accept the new brand-text
  - `tests/test_oauth_provider_factory.py:96` — `assert cm.client_name == "the-one"` — pins the MCP `clientInfo.name`; this is the protocol-level identifier that the flight spec explicitly preserves as `"the-one"`, so this test STAYS unchanged
- Wordmark form: `GleepGlorp AI` (with space and capital `AI`) — confirmed in flight Open Questions, adopted as the working assumption.
- The Python package name `the_one` and CLI binary name `the-one` are EXPLICITLY out of scope per mission constraint. The package docstring rebrands the human-readable name but adds a parenthetical noting the Python package is still `the_one`.
- Line-number anchors in the per-surface decision table have drifted slightly since flight design (legs 01 added favicon `<link>` tags pushing `<title>` from line 6 to line 11; leg 01 added `<img>` to topbar pushing wordmark from `app.js:17` to `app.js:19`). Implementation should re-grep, not trust the flight spec's line numbers.

## Inputs

Files that must exist (verified at design time):

**Production source — user-visible text** (rebrand to "GleepGlorp AI"):
- `the_one/interfaces/web/static/index.html:11 — "<title>the-one</title>"` — browser tab title
- `the_one/interfaces/web/static/js/app.js:19 — "'the-one' +"` — topbar wordmark text inside the `<h1 class="app-topbar-title">` (sits after the `<img>` mascot prepended by Leg 01)
- `the_one/interfaces/web/app.py:123 — "app = FastAPI(title=\"the-one\", lifespan=lifespan)"` — surfaces as the title on the auto-generated `/docs` Swagger UI
- `the_one/interfaces/cli.py:30 — "\"[bold]the-one[/bold] v0.1.0\\n\""` — content line in the CLI Rich welcome panel
- `the_one/interfaces/cli.py:32 — "title=\"the-one\","` — title attribute on the same Rich panel
- `the_one/main.py:25 — "print(f\"the-one v{__version__}\")"` — output of `the-one --version`
- `the_one/__init__.py:1 — "\"\"\"the-one: A personal agentic system.\"\"\""` — package docstring exposed via `help()` and import-time introspection
- `the_one/interfaces/web/api.py:1579 — "<p class=\"oauth-callback-eyebrow\">the-one // oauth</p>"` — eyebrow text on the rendered OAuth completion page

**Production source — carried over from Leg 03**:
- `the_one/interfaces/web/api.py:1478 — "with the rest of the-one — dark-mode cyan-accent palette, Geist /"` — docstring comment with mixed brand + cyan references; rewrite both at once

**Production source — preserve as-is** (protocol / binary / module identifiers):
- `the_one/interfaces/web/api.py:1436, 1821 — "\"clientInfo\": {\"name\": \"the-one\", \"version\": \"0.1\"}"` — MCP protocol identifier; NOT user-visible
- `the_one/main.py:11 — "\"\"\"Main entry point for the \`the-one\` command.\"\"\""` — refers to CLI binary name in docstring
- `the_one/main.py:27 — "print(\"Usage: the-one [chat|serve|version]\")"` — refers to actual CLI binary name in usage hint
- Python imports / module references `from the_one ...`, `import the_one`, `the_one.<module>` — module name preserved per mission constraint

**Tests — update to match new brand text**:
- `tests/browser/test_app_fixture.py:16 — "assert \"the-one\" in title.lower()"` — change the assertion to check for `"gleepglorp"` instead (lowercased); update the failure message accordingly
- `tests/test_aiat.py:129 — "assert \"the-one\" in text.lower() or \"the_one\" in text.lower()"` — broaden to accept either `"gleepglorp"` OR `"the_one"` (the agent's self-introspection may still mention the Python package internally; the broader assertion is the historical-and-current pattern)
- `tests/test_aiat.py:151` — same change as above

**Tests — preserve as-is** (protocol / fixture identifiers):
- `tests/test_oauth_provider_factory.py:96 — "assert cm.client_name == \"the-one\""` — pins the MCP `clientInfo.name` protocol identifier; preserved per flight spec
- `tests/test_platform_tempdirs.py:33 — "user_config_dir(\"the-one\") == Path.home() / \".the-one\""` — test-internal slug literal for config-dir helper; not a brand reference
- `tests/browser/conftest.py` — `tmp_path / "the-one-data"` style fixture identifiers; documented in Leg 01 completion checklist as expected-remaining hits
- `tests/test_llm_registry.py:135` — regex `r"the-one\[openai\]"` matches the pip install hint in `llm/registry.py:40`; refers to the PyPI distribution name (same as CLI binary name); preserved per mission constraint
- `the_one/interfaces/web/static/js/areas/admin/tools-editor.js:56 — "default: 'the one cli agent'"` — sample search query value used as a placeholder in the admin "Try it" UI for the `web_search` tool; benign test-fixture default, NOT a brand surface; preserved as-is

State that must be true:
- Legs 01-03 landed (uncommitted on `flight/01-brand-foundation`)
- Container is running (`make up` if not)

## Outputs

Files modified:
- **8 production source files** — user-visible brand text updated to "GleepGlorp AI"
- **`api.py:1478`** — docstring comment rewritten to drop both stale "the-one" brand reference and "cyan-accent palette" reference (Leg 03 carry-over)
- **3 test files** — assertions updated to accept the new brand text without losing the historical coverage:
  - `tests/browser/test_app_fixture.py` — assertion + failure message
  - `tests/test_aiat.py` — two assertions

Files NOT modified:
- Any reference to the CLI binary name `the-one` (preserved per mission constraint)
- Any reference to the Python module `the_one` (preserved per mission constraint)
- MCP protocol identifier `clientInfo.name` (preserved per Leg 02 design decision)
- Test-internal identifiers (`tmp_path / "the-one-data"`, etc.)

State changes:
- Running app's browser tab title reads "GleepGlorp AI"
- Topbar wordmark reads "GleepGlorp AI" beside the mascot icon
- CLI splash reads "GleepGlorp AI v0.1.0"
- `the-one --version` prints `GleepGlorp AI v{version}`
- Auto-generated `/docs` Swagger UI title reads "GleepGlorp AI"
- OAuth callback page eyebrow reads "gleepglorp ai // oauth"
- Test suite no longer fails on the rebrand-affected assertions

## Acceptance Criteria

- [ ] `the_one/interfaces/web/static/index.html` `<title>` reads exactly `GleepGlorp AI`
- [ ] `the_one/interfaces/web/static/js/app.js` topbar wordmark text inside `.app-topbar-title` `<h1>` reads exactly `GleepGlorp AI`
- [ ] `the_one/interfaces/web/app.py` `FastAPI(title=...)` argument reads exactly `"GleepGlorp AI"`
- [ ] `the_one/interfaces/cli.py` Rich panel content and `title=` argument both read `GleepGlorp AI`; the stale literal version string `v0.1.0` is replaced with a dynamic `v{__version__}` interpolation sourced from `the_one/__init__.py` (resolves a pre-existing drift where the panel pinned `0.1.0` while `__init__.py` carries `0.2.0`)
- [ ] `the_one/main.py:25` version print reads `GleepGlorp AI v{__version__}` (literal "GleepGlorp AI" before the v; binary name in adjacent usage hint at line 27 stays `the-one`)
- [ ] `the_one/__init__.py:1` package docstring reads `GleepGlorp AI: A personal agentic system. (Python package: the_one)` — the parenthetical clarifies the package name is intentionally preserved
- [ ] `the_one/interfaces/web/api.py:1579` OAuth callback eyebrow `<p>` text reads `gleepglorp ai // oauth` (lowercase to match the existing eyebrow stylistic; the surrounding HTML rule scoping the eyebrow uses small-caps/uppercase styling if needed)
- [ ] `the_one/interfaces/web/api.py:1478` docstring comment line rewritten to drop both the "the rest of the-one" brand reference AND the "dark-mode cyan-accent palette" stale palette reference; new wording describes the design system in current terms (e.g., "with the GleepGlorp AI design system — violet accent, Geist Sans / Mono fonts")
- [ ] `the_one/interfaces/web/api.py:1436, 1821` `clientInfo` `name` values STILL read `"the-one"` (protocol identifier preserved)
- [ ] `the_one/main.py:11, 27` references to the CLI binary `the-one` are PRESERVED (docstring at line 11 says "the `the-one` command"; usage hint at line 27 says "Usage: the-one [...]")
- [ ] `tests/browser/test_app_fixture.py` page-title assertion updated to check `"gleepglorp"` lowercased (the test fixture already lowercases via `title.lower()`) with an updated failure message
- [ ] `tests/test_aiat.py` lines 129 and 151 assertions updated to accept `"gleepglorp" in text.lower() or "the_one" in text.lower()` (preserving the Python-module fallback, swapping the brand check)
- [ ] `tests/test_oauth_provider_factory.py:96` `assert cm.client_name == "the-one"` is UNCHANGED (protocol identifier)
- [ ] Final verification grep: `grep -rIn 'the-one' the_one/` returns ~25-30 expected hits classified as preserved-by-design — module references, CLI binary in `main.py:11, 27`, MCP `clientInfo.name` at `api.py:1436, 1821`, pip install hints in `llm/registry.py:40` and `llm/openrouter_provider.py:26-32`, internal code comments in `config.py`, `tools/filesystem.py`, `tools/_web_config.py`, `mcp/*` modules, etc. No NEW user-visible "the-one" strings remain.
- [ ] Targeted zero-hit checks on the user-facing surfaces (no legitimate preservation reason exists in these files):
  - `grep -n 'the-one' the_one/interfaces/web/static/index.html` returns zero hits
  - `grep -n "'the-one'\|\"the-one\"" the_one/interfaces/web/static/js/app.js` returns zero hits (any remaining `the-one` substring should be inside a comment or unrelated identifier, not a wordmark literal)
  - `grep -n "the-one" the_one/interfaces/cli.py` returns zero hits (CLI splash is the only `the-one` reference in this file pre-leg)
  - `grep -n "the-one" the_one/__init__.py` returns zero hits
- [ ] `docker exec the-one pytest tests/test_design_tokens_a11y.py tests/test_token_definitions.py tests/test_oauth_provider_factory.py tests/test_platform_tempdirs.py -x -q --timeout 10` exits 0 — narrow gate covering: (a) palette regression net, (b) MCP `clientInfo.name` test that pins the preserved protocol identifier, (c) test_platform_tempdirs.py to confirm the test-internal slug literal still works
- [ ] `make verify-serving` exits 0
- [ ] Visual sanity (manual after `make rebuild`): load `http://localhost:8484/`, confirm browser tab reads `GleepGlorp AI`, topbar reads `GleepGlorp AI` next to the mascot, `/docs` Swagger UI shows `GleepGlorp AI`. CLI: `docker exec the-one the-one --version` prints `GleepGlorp AI v{version}` (or whatever the version is).

## Verification Steps

- **Production source rewrites**:
  ```
  grep -n "GleepGlorp AI" the_one/interfaces/web/static/index.html the_one/interfaces/web/static/js/app.js the_one/interfaces/web/app.py the_one/interfaces/cli.py the_one/main.py the_one/__init__.py the_one/interfaces/web/api.py
  # Expect: 7-9 hits across the listed files (each user-visible surface)
  ```
- **OAuth callback eyebrow**:
  ```
  grep -n "gleepglorp ai // oauth" the_one/interfaces/web/api.py
  # Expect: one hit at the line that used to say "the-one // oauth"
  ```
- **Protocol identifier preserved**:
  ```
  grep -n '"clientInfo"' the_one/interfaces/web/api.py
  # Expect: both lines still say "name": "the-one"
  ```
- **CLI binary preserved**:
  ```
  grep -n "the-one" the_one/main.py
  # Expect: docstring line 11, usage-print line 27, both unchanged
  ```
- **Test assertions updated**:
  ```
  grep -n "gleepglorp" tests/browser/test_app_fixture.py tests/test_aiat.py
  # Expect: hits at fixture line 16, aiat lines 129 + 151
  grep -n '"the-one"' tests/test_oauth_provider_factory.py
  # Expect: line 96 unchanged
  ```
- **Test gate**:
  ```
  docker exec the-one pytest tests/test_design_tokens_a11y.py tests/test_token_definitions.py tests/test_oauth_provider_factory.py tests/test_platform_tempdirs.py -x -q --timeout 10
  # Expect: exit 0
  ```
- **Serving check**: `make verify-serving` → exit 0
- **Visual spot-check (manual after `make rebuild`)**:
  - Load `http://localhost:8484/` in private window; tab title reads `GleepGlorp AI`
  - Topbar shows mascot icon + `GleepGlorp AI` wordmark
  - Visit `http://localhost:8484/docs`; page title reads `GleepGlorp AI`
  - CLI: `docker exec the-one the-one version` prints `GleepGlorp AI v0.2.0` (the actual `__version__` from `__init__.py`; subcommand is `version`, NOT `--version` flag)
  - (OAuth callback eyebrow is visible only after a real MCP OAuth flow completes — direct preview optional; the alignment HAT in Leg 05 covers this differently. The eyebrow rule applies `text-transform: uppercase` at `api.py:1549`, so the lowercase HTML source `gleepglorp ai // oauth` renders as `GLEEPGLORP AI // OAUTH`.)

## Implementation Guidance

1. **Re-grep current state** (line numbers may have drifted since flight design — `<title>` shifted from line 6 → 11 due to leg 01 favicon links; topbar wordmark shifted from `app.js:17` → `app.js:19` due to leg 01 `<img>` insertion):
   ```
   grep -rIn "the-one" the_one/interfaces/web/static/index.html the_one/interfaces/web/static/js/app.js the_one/interfaces/web/app.py the_one/interfaces/cli.py the_one/main.py the_one/__init__.py the_one/interfaces/web/api.py
   ```
   Record the count and exact line locations in the flight log.

2. **Rewrite user-visible production text** (8 surfaces):
   - `static/index.html` `<title>the-one</title>` → `<title>GleepGlorp AI</title>`
   - `static/js/app.js` topbar wordmark — find the string literal `'the-one'` inside the `renderTopBar()` HTML-concat, change to `'GleepGlorp AI'`
   - `interfaces/web/app.py` `FastAPI(title="the-one", lifespan=lifespan)` → `FastAPI(title="GleepGlorp AI", lifespan=lifespan)`
   - `interfaces/cli.py` line ~30 `"[bold]the-one[/bold] v0.1.0\n"` → `f"[bold]GleepGlorp AI[/bold] v{__version__}\n"` — rebrand AND fix the stale literal version. Add `from the_one import __version__` at the top of the file if not already imported (the version string lives in `the_one/__init__.py:3` and is the canonical source). This also requires the surrounding `Panel.fit(...)` call to use an f-string container; if the line currently sits inside a plain string concatenation, restructure accordingly.
   - `interfaces/cli.py` line ~32 `title="the-one"` → `title="GleepGlorp AI"`
   - `main.py` line ~25 `print(f"the-one v{__version__}")` → `print(f"GleepGlorp AI v{__version__}")`
   - `__init__.py` line 1 `"""the-one: A personal agentic system."""` → `"""GleepGlorp AI: A personal agentic system. (Python package: the_one)"""` — the parenthetical preserves the discoverability of the actual Python package name
   - `interfaces/web/api.py` line ~1579 `<p class="oauth-callback-eyebrow">the-one // oauth</p>` → `<p class="oauth-callback-eyebrow">gleepglorp ai // oauth</p>` (lowercase per existing eyebrow stylistic — the CSS for the eyebrow handles casing; preserve the `//` separator)

3. **Rewrite the carry-over `api.py:1478` docstring comment** (Leg 03 deferral):
   The current comment line reads: `with the rest of the-one — dark-mode cyan-accent palette, Geist /`
   New wording: `with the rest of GleepGlorp AI — violet accent, Geist Sans / Mono fonts` (or similar; preserve the surrounding context — this is inside a multi-line docstring describing the OAuth callback page renderer's design rationale).

4. **Update the three test assertions**:
   - `tests/browser/test_app_fixture.py:16` — change `assert "the-one" in title.lower()` to `assert "gleepglorp" in title.lower()`; update the failure message to reference the new expected substring
   - `tests/test_aiat.py:129` — change `assert "the-one" in text.lower() or "the_one" in text.lower()` to `assert "gleepglorp" in text.lower() or "the_one" in text.lower()` — keep the `the_one` Python-module fallback because the agent's self-introspection may still surface the package name from imports; the brand-substring swap is the targeted change
   - `tests/test_aiat.py:151` — same change as line 129

5. **Confirm preservation of identifiers** (no change needed; just verify with grep):
   - `main.py:11, 27` — still say "the-one" (CLI binary name)
   - `api.py:1436, 1821` — `"clientInfo": {"name": "the-one", ...}` still says "the-one" (protocol identifier)
   - `tests/test_oauth_provider_factory.py:96` — unchanged

6. **Run the test gate** and **`make verify-serving`**

7. **Rebuild and visual spot-check** (optional but recommended):
   - `make rebuild`
   - Load `http://localhost:8484/` — tab title + topbar wordmark
   - Load `http://localhost:8484/docs` — Swagger UI title
   - `docker exec the-one the-one --version` — version print

## Edge Cases

- **`the-one` substring inside markdown / docstrings**: false-positive risk on broad `sed -i 's/the-one/GleepGlorp AI/g'` invocations. DO NOT use a blanket sed pass; use per-line surgical Edits because the same string is used in two semantic contexts (user-visible brand vs CLI binary name) and the leg explicitly preserves the binary references at `main.py:11, 27`.
- **Test-internal `tmp_path / "the-one-data"` fixtures**: documented as expected-remaining hits in Leg 01 completion checklist; this leg does NOT touch them. The final verification grep allows for them.
- **`the_one.` Python-module references**: dot-suffix means these are module-path imports (`from the_one.foo import bar`, `the_one.config.settings`, etc.). The grep filter `| grep -v "the_one\."` excludes them. Preserved per mission constraint.
- **`tests/browser/test_app_fixture.py` lowercase check**: the test already calls `.lower()` on the page title before substring-matching, so the new assertion `"gleepglorp" in title.lower()` works regardless of how the title is cased in `index.html` (which uses title-cased "GleepGlorp AI"). No casing pitfall.
- **`tests/test_aiat.py` is `@pytest.mark.live`**: excluded from default runs. The assertion change doesn't affect anything until someone runs the live AIAT suite. But updating it as part of this leg is correct — leaving the assertion stale would fail the moment someone next runs the live suite, with no obvious "what changed" pointer.
- **OAuth callback page direct preview**: the eyebrow change is hard to visually verify without triggering an actual OAuth flow. Leg 05 alignment HAT may cover this via a query-param-seeded direct render, or it may defer to Flight 3 (Studio Polish) where MCP OAuth sources are exercised. This leg does not need to manually verify the OAuth surface — the source-code change is the deliverable.

## Files Affected

- `the_one/interfaces/web/static/index.html` — `<title>` line
- `the_one/interfaces/web/static/js/app.js` — topbar wordmark string literal in `renderTopBar()`
- `the_one/interfaces/web/app.py` — `FastAPI(title=...)` argument at line 123
- `the_one/interfaces/cli.py` — Rich panel content and title at lines ~30, 32
- `the_one/main.py` — version print at line ~25 (NOT lines 11 or 27 — those are preserved)
- `the_one/__init__.py` — package docstring at line 1
- `the_one/interfaces/web/api.py` — OAuth eyebrow at line ~1579, docstring comment at line ~1478
- `tests/browser/test_app_fixture.py` — page-title assertion at line ~16
- `tests/test_aiat.py` — two assertions at lines ~129 and ~151

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified
- [ ] Narrow test gate (palette + token-def + oauth-factory + tempdirs) exits 0
- [ ] `make verify-serving` exits 0
- [ ] Flight log entry under `## Leg Progress` records: per-surface rewrites applied, the api.py:1478 carry-over wording chosen, the three test assertion changes, and a confirmation that protocol/binary/module identifiers stayed put
- [ ] Set leg status to `landed` in this file's header
- [ ] Signal `[HANDOFF:review-needed]` — orchestrator commits at flight-end; do NOT commit or signal `[COMPLETE:leg]`

---

## Citation Audit

12 citations verified against current code at leg design time:

| Citation | Verified |
|---|---|
| `the_one/interfaces/web/static/index.html:11 — "<title>the-one</title>"` | OK (shifted from line 6 → 11 by Leg 01 favicon links) |
| `the_one/interfaces/web/static/js/app.js:19 — wordmark string literal 'the-one'` | OK (shifted from line 17 → 19 by Leg 01 `<img>` prepend) |
| `the_one/interfaces/web/app.py:123 — "FastAPI(title=\"the-one\", lifespan=lifespan)"` | OK |
| `the_one/interfaces/cli.py:30 — Rich panel content` | OK |
| `the_one/interfaces/cli.py:32 — Rich panel title argument` | OK |
| `the_one/main.py:11, 25, 27 — CLI binary docstring (preserve), version print (rebrand), usage print (preserve)` | OK |
| `the_one/__init__.py:1 — package docstring` | OK |
| `the_one/interfaces/web/api.py:1436, 1478, 1579, 1821 — four hits with distinct dispositions` | OK |
| `tests/browser/test_app_fixture.py:16 — page title assertion (rebrand)` | OK |
| `tests/test_aiat.py:129, 151 — live agent introspection assertions (rebrand)` | OK |
| `tests/test_oauth_provider_factory.py:96 — MCP clientInfo.name assertion (preserve)` | OK |
| `tests/test_platform_tempdirs.py:33 — config-dir slug literal (preserve, test-internal)` | OK |
| `tests/test_llm_registry.py:135 — pip install hint regex r"the-one\[openai\]"` | OK (preserved per binary/PyPI-name decision; Developer found at design review round 1) |
| `tools-editor.js:56 — sample search query 'the one cli agent' (preserve, benign default)` | OK (Developer found at design review round 1) |
| `cli.py — Rich panel literal `v0.1.0` vs actual `__version__ = "0.2.0"` in __init__.py` | OK (drift confirmed; piggyback dynamic-version fix into this leg per Developer suggestion) |
| `api.py:1549 — .oauth-callback-eyebrow text-transform: uppercase` | OK (Developer verified; lowercase HTML source renders uppercase) |
| `main.py:22 — CLI dispatch uses subcommand "version", NOT --version flag` | OK (Developer found; verification commands corrected) |

Design-review revisions applied (Developer review, round 1):
- High: corrected CLI version-print verification command from `the-one --version` to `the-one version` (main.py dispatches on subcommand, not flag).
- Medium: piggybacked the stale `v0.1.0` → `f"v{__version__}"` fix into the `cli.py:30` rewrite — resolves a pre-existing drift while we're already touching the line.
- Low: explicitly classified `tools-editor.js:56` `'the one cli agent'` and `tests/test_llm_registry.py:135` regex as preserve-as-is in the Inputs section.
- Suggestion: strengthened the verification grep with file-specific zero-hit checks on user-facing surfaces (index.html, app.js wordmark literals, cli.py, __init__.py) where no legitimate `the-one` preservation reason exists. Acknowledged that ~25-30 preserved hits remain in the broader `the_one/` tree (internal comments, pip hints, MCP protocol, etc.).
