# Leg: 03-security-and-docs-sweep

**Status**: completed
**Flight**: [Integrity Gate Restoration](../flight.md)

## Objective

Land a tight bundle of small fixes: close the OAuth callback same-origin script-injection path; validate the npx package name argument in cache cleanup; adopt `pip-audit` for local CVE awareness on the M07-expanded dep surface (local-only — CI step dropped with Concourse removal in Leg 4); carry forward three documentation items from the M08 mission-debrief (`agents.md` `_init_provider_state`; `agents.md` "live-read across lazy-resolver boundary"; `.env.example` `THE_ONE_DEV_MODE`); add one `SECURITY-MODEL.md` Future Work note (MCP `streamable-http` URL gating asymmetry — Concourse rotation cadence note dropped, Concourse going away); and update OpenRouter's `_APP_URL` / `_APP_NAME` to GleepGlorp AI identity.

> **Scope pivot 2026-05-15**: Concourse + self-improvement framing being removed in Leg 4. Two items dropped from Leg 3 as a result: (a) pip-audit CI step (kept as a `make audit` local target instead); (b) the SECURITY-MODEL Concourse rotation cadence note (the threat surface goes away with the infrastructure).

## Context

Each item in this leg is one-liner to a few-line scope. They cluster in this leg because they share a "small change + tight verification" character — running this leg in isolation makes the maintenance mission's outputs easier to review.

The single Action Required security finding here is the OAuth callback's same-origin XSS: the page renders `json.dumps(post_message)` directly inside a `<script>` body without escaping `</`, so a malicious-or-compromised third-party OAuth Authorization Server can inject same-origin script via `error_description=...</script><script>fetch('/api/encryption/rotate',...)</script>`. The injected payload runs as same-origin script and bypasses the Origin allowlist (it loads from `127.0.0.1` so the Origin header matches). The Architect escalated this from the Security Reviewer's "medium under operator-trusted" to Action Required because `SECURITY-MODEL.md` "Future Work" names the MCP trust-boundary gap as a *gap to close*, not a license to ship exploitable code that lives in that gap.

`pip-audit` adoption is a second-pass-running re-flag: the prior maintenance report (2026-05-04 §3.3) recommended it; M06 didn't adopt it; the M07 dep surface expansion (`mcp==1.27.0` + transitive auth deps) is exactly the case that motivates it. The Architect's framing: "Don't punt a third time."

The OpenRouter rebrand strings are bundled here per the flight's design decision: one-line change in `openrouter_provider.py:38-39`, low user-impact (visible to OpenRouter analytics only), but the kind of item that rots if not bundled opportunistically.

## Inputs

- `the_one/interfaces/web/api.py` — `post_message_script` template (around line 1683-1690 post-Leg-1-format; locate by symbol `post_message_script = (`) and the THREE `post_message=` flow sites (around lines 1838, 1861, 1913 post-Leg-1-format; locate via `grep -n "post_message=" api.py | head -10`). Line numbers below are pre-Leg-1-format and have shifted by ~2 lines — locate by symbol.
- `the_one/mcp/cache_cleanup.py` — `async def _clean_npx(pkg: str)` (around line 213 post-format; locate by `^async def _clean_npx`); the unsanitized `pkg` flows into `slot_dir / "node_modules" / pkg / "package.json"` (around line 246). Add the allowlist at the function entry, not at the path-join site.
- `pyproject.toml` `[project.optional-dependencies].dev`
- `ci/pipeline.yml:22-24` (test task command chain)
- `the_one/agents.md` `## Provider type extension checklist` heading (around line 1485 — locate by heading, line numbers drift)
- `the_one/agents.md` `## Project Conventions` heading (around line 171 — locate by heading; Architect spot-check confirmed prior leg's L219 reference was stale)
- `.env.example`
- `SECURITY-MODEL.md` (Future Work section)
- `the_one/llm/openrouter_provider.py:38-39` (`_APP_URL` and `_APP_NAME`)
- M08 mission-debrief context on the live-read pattern (F6.5 L4 + F7 L05) for codifying the convention text

## Outputs

- OAuth callback's `postMessage` JSON output escaped (no `</` or `<!--` can reach the browser as raw HTML)
- `_clean_npx` validates `pkg` against `[A-Za-z0-9._@/-]` allowlist before using it in path operations
- `pyproject.toml` declares `pip-audit` in dev extras
- `ci/pipeline.yml` test task gains a non-blocking `pip-audit --skip-editable || echo 'pip-audit non-blocking'` step
- `agents.md` `## Provider type extension checklist` includes `_init_provider_state` entry
- `agents.md` `## Project Conventions` includes a "live-read across lazy-resolver boundary" entry
- `.env.example` documents `THE_ONE_DEV_MODE`
- `SECURITY-MODEL.md` Future Work section names: the MCP `streamable-http` URL gating asymmetry with the LLM provider path. (Concourse team-password rotation cadence note dropped — Concourse removed in Leg 4.)
- `openrouter_provider.py:38-39` `_APP_URL` and `_APP_NAME` updated to GleepGlorp AI strings

## Acceptance Criteria

- [ ] In `api.py`, the OAuth callback's `post_message_script` no longer renders raw `json.dumps(...)` output; instead the JSON is HTML-escaped against `</script>` injection (either `.replace("</", "<\\/")...` chain or `<script type="application/json">` + separate parser)
- [ ] An end-to-end OAuth happy-path test still passes (existing tests in `tests/test_oauth_callback_route.py` cover the heading text; they do NOT assert on the script body or `post_message` JSON, so the escape change is non-breaking — verified by reviewer)
- [ ] **All THREE `post_message=` flow sites** in `oauth_callback` (failed / expired / success at api.py:1838, 1861, 1913 area) route their dict through `_safe_script_json`. Verification: `grep -n "json.dumps(post_message)" the_one/interfaces/web/api.py` returns empty after the fix (no raw `json.dumps(post_message)` reaches the rendered template anywhere).
- [ ] `_clean_npx` raises a `ValueError` when given inputs that fall outside the **npm package-name spec** `^(?:@[a-z0-9][a-z0-9._-]*\/)?[a-z0-9][a-z0-9._-]*$`. **NOTE**: the original allowlist `[A-Za-z0-9._@/-]` does NOT block `../etc/passwd` (all those chars are allowed individually) — the npm-spec regex tightens to only allow `/` after a scope prefix and forbids leading dots. Verified inputs: `lodash` ✓, `@types/node` ✓, `@scope/pkg` ✓ pass; `../etc/passwd` ✗, `a/b/c` ✗, `.hidden` ✗, empty ✗ reject.
- [ ] `pip-audit` listed in `pyproject.toml` dev extras
- [ ] `make audit` (host-side, parallel to `make doctor` from Leg 2) runs `.venv/bin/pip-audit --skip-editable` non-blocking via `|| true`. Exit 0 even when pip-audit finds advisories.
- [ ] `make doctor` probe list updated to include `import pip_audit` (underscore — module name; `pip-audit` is the package name with dash, `pip_audit` is the importable module)
- [ ] `grep -n "_init_provider_state" the_one/agents.md` matches inside `## Provider type extension checklist`
- [ ] `grep -n "lazy-resolver\|live-read" the_one/agents.md` matches inside `## Project Conventions`
- [ ] `grep -n "THE_ONE_DEV_MODE" .env.example` matches
- [ ] `grep -nE "streamable-http|streamable_http" SECURITY-MODEL.md` matches in Future Work section
- [ ] ~~`grep -ni "rotation" SECURITY-MODEL.md` matches in a relevant context~~ DROPPED — the Concourse rotation cadence content was dropped per pivot; the remaining "rotation" matches (encryption key rotation, etc.) are pre-existing and not Leg 3 work.
- [ ] `grep -n "_APP_URL\|_APP_NAME" the_one/llm/openrouter_provider.py` shows GleepGlorp identity (no longer literal "the-one")
- [ ] `ruff check the_one/ tests/ && ruff format --check the_one/ tests/` both exit 0 (Leg 1 baseline preserved)
- [ ] Broad pytest still exits 0 (Leg 2 baseline preserved)

## Verification Steps

- `cd ~/projects/the-one && grep -n '</script>' the_one/interfaces/web/api.py` → no raw `</script>` strings emitted from json.dumps path
- Inspect the OAuth callback page in a controlled local test: trigger an OAuth flow with a mocked error response whose `error_description` contains `</script><script>alert(1)</script>`; confirm the browser does NOT execute the alert (the payload should render as literal text inside the JSON, not as DOM)
- `cd ~/projects/the-one && python -c "import asyncio; from the_one.mcp.cache_cleanup import _clean_npx; asyncio.run(_clean_npx('../etc/passwd'))"` — signature is `async def _clean_npx(pkg: str) -> None` (single positional arg; verified at `cache_cleanup.py:215`); raises clear `ValueError` from the allowlist check before reaching the path-join site at `:248`
- `cd ~/projects/the-one && pip-audit --skip-editable --strict 2>&1 | head -30` — runs cleanly
- `cd ~/projects/the-one && grep -A2 "_init_provider_state\|live-read\|lazy-resolver" the_one/agents.md`
- `cd ~/projects/the-one && grep "THE_ONE_DEV_MODE" .env.example`
- `cd ~/projects/the-one && grep -i "rotation cadence\|streamable.http" SECURITY-MODEL.md`
- `cd ~/projects/the-one && python -c "from the_one.llm.openrouter_provider import _APP_URL, _APP_NAME; print(_APP_URL, _APP_NAME)"` — prints GleepGlorp strings
- `cd ~/projects/the-one && ruff check the_one/ tests/ && ruff format --check the_one/ tests/ && pytest --tb=no -q` → all exit 0

## Implementation Guidance

1. **OAuth callback JSON escape** (the security-meaningful change) — fix ALL THREE `post_message=` flow sites
   - Locate `post_message_script = (` in `api.py` (around L1683-1690 post-Leg-1-format; locate by symbol)
   - Locate the THREE `post_message=` flow sites: failed (~L1838), expired (~L1861), success (~L1913). Use `grep -n "post_message=" the_one/interfaces/web/api.py | head -10` to confirm current positions.
   - **Define `_safe_script_json` as a module-level private helper in `api.py`**, placed immediately above the function containing `post_message_script` (around L1670 area). Leading underscore signals private. No new module — single consumer; if future endpoints need JSON-in-script, promote later.
   - The current shape is approximately `f"<script>window.opener.postMessage({json.dumps(post_message)}, ...)</script>"` or similar
   - Replace `json.dumps(post_message)` with an HTML-safe-in-script wrapper. Two equally good options:
     - **Option A (chained replacements)**: write a small helper that wraps `json.dumps` and chains the escapes. **IMPORTANT**: the U+2028 (LINE SEPARATOR) and U+2029 (PARAGRAPH SEPARATOR) characters terminate JavaScript statements when literal in source; they must be written as Python escape sequences (`"\u2028"` / `"\u2029"` — NOT as raw characters that look like spaces in source). Approximate shape:
       ```python
       def _safe_script_json(payload: dict) -> str:
           return (
               json.dumps(payload)
               .replace("</", "<\\/")
               .replace("<!--", "<\\!--")
               .replace("\u2028", "\\u2028")  # LINE SEPARATOR
               .replace("\u2029", "\\u2029")  # PARAGRAPH SEPARATOR
           )
       safe_json = _safe_script_json(post_message)
       ```
       Then embed `safe_json` where `json.dumps(post_message)` is currently used.
     - **Option B (cleaner separation)**: render `<script type="application/json" id="oauth-result">{json.dumps(post_message)}</script>` (this is safe because `<script type="application/json">` content is not parsed as JS) plus a separate `<script>document.getElementById('oauth-result').textContent ...</script>` that reads + parses + posts
   - Pick Option A for minimal blast radius (one line change vs restructuring the page); leave a one-line comment explaining the escape rationale ("escape `</` to prevent <script> termination injection from IdP-supplied error_description")
   - Verify both `error_description` and any other Auth-Server-controlled field flowing into `post_message` are routed through `safe_json`, not just one of them

2. **`_clean_npx` package-name allowlist** — use the npm package-name spec, NOT the leg's original `[A-Za-z0-9._@/-]` (which permits `../etc/passwd`)
   - Locate `async def _clean_npx(pkg: str)` in `mcp/cache_cleanup.py` (around L213; grep `^async def _clean_npx`)
   - Add a module-level constant: `_VALID_NPX_PKG_RE = re.compile(r'^(?:@[a-z0-9][a-z0-9._-]*/)?[a-z0-9][a-z0-9._-]*$')` — npm's actual package-name spec: only allows `/` after a `@scope/` prefix; forbids leading dots; matches lowercase + digits + `._-`. **Critical**: the original allowlist `[A-Za-z0-9._@/-]` was broken — it permitted `../etc/passwd` because every character in that string was individually allowed.
   - At the start of `_clean_npx`, validate: `if not _VALID_NPX_PKG_RE.match(pkg): raise ValueError(f"unsafe npx package name: {pkg!r}")`
   - Or, if `_clean_npx` is wrapped by `extract_runtime_package`, add the validation there so all call paths are gated at decode-time
   - Add a test in `tests/test_mcp_cache_cleanup.py` (verify file exists; if not, create) covering:
     - VALID: `lodash` ✓, `@types/node` ✓, `@scope/pkg` ✓, `pkg-with-dashes` ✓, `pkg_with_underscores` ✓
     - INVALID: `../etc/passwd` ✗, `a/b/c` ✗ (deep path), `.hidden` ✗ (leading dot), `Foo` ✗ (uppercase — npm spec is lowercase-only), `pkg;name` ✗, empty string ✗

3. **OAuth XSS regression test** (paired with step 1)
   - Destination file: `tests/test_oauth_callback_route.py` (existing file with OAuth callback coverage). Add a new function at the file bottom or wrap in a `class TestSafeScriptJSON:` for grouping.
   - Reviewer pre-confirmed: existing tests in that file assert only on heading text (`"Login successful. You may close this tab."`, `"Login failed"`, etc.); they do NOT assert on the script body or `post_message` JSON, so the escape change is non-breaking for those. No updates needed.
   - Add tests exercising the helper directly:
     ```python
     from the_one.interfaces.web.api import _safe_script_json

     def test_safe_script_json_escapes_script_termination():
         payload = {"error": "code", "description": "</script><script>alert(1)</script>"}
         out = _safe_script_json(payload)
         assert "</script>" not in out  # no raw script-termination reaches output
         assert "<\\/script>" in out    # escape is applied
         assert "alert(1)" in out        # benign content still present

     def test_safe_script_json_escapes_line_separators():
         payload = {"description": "line1 line2 line3"}
         out = _safe_script_json(payload)
         assert " " not in out       # no raw LSEP reaches output
         assert " " not in out       # no raw PSEP reaches output
         assert "\\u2028" in out          # escape applied
         assert "\\u2029" in out          # escape applied
     ```
   - The LSEP/PSEP test guards against a future refactor silently dropping the U+2028/U+2029 escape (a partial regression that only `</` testing wouldn't catch).

4. **`pip-audit` adoption** (scope-revised — local-only; CI step dropped with Concourse removal)
   - Edit `pyproject.toml`'s `[project.optional-dependencies].dev` to add `"pip-audit>=2.7"` (or whatever the current minor)
   - Install in HOST venv: `.venv/bin/pip install pip-audit` (or re-run `.venv/bin/pip install -e .[dev]`)
   - **Update `make doctor` target** (from Leg 2): the `python -c` probe currently runs `import asgi_lifespan, pytest_asyncio, ...`. Append `, pip_audit` to that comma-separated import list. **Important**: the package name is `pip-audit` (dash), the importable module is `pip_audit` (underscore) — common gotcha.
   - **Add `make audit` target** under the same `# ── Drift detection (host-side) ──` section header as `doctor`. Shape (host-side, non-blocking):
     ```make
     .PHONY: audit
     audit:  ## Run pip-audit against host venv (non-blocking; surfaces advisories)
     	@.venv/bin/pip-audit --skip-editable || true
     ```
     The `|| true` makes findings non-blocking — `make audit` exits 0 even on advisories. Findings still print to stdout for operator awareness.
   - ~~CI step in `ci/pipeline.yml`~~ DROPPED — Concourse removed in Leg 4
   - Run `make audit` locally; note any findings in `flight-log.md` for awareness even if not actionable this leg.
   - **Divert-if**: if `pip-audit` surfaces a HIGH or CRITICAL CVE on any package in `pyproject.toml`'s base `dependencies` list OR a transitive-runtime dep in the install closure of those (NOT dev-extras-only), pause this leg, surface in flight log, and consult before continuing. Common runtime deps: `mcp`, `fastapi`, `anthropic`, `openai`, `httpx`, `pydantic-settings`, `python-multipart`, `sse-starlette`, `aiosqlite`, `cryptography`, `websockets`. Dev-extras CVEs (`pytest`, `ruff`, `playwright`, `pillow`, etc.) are advisory-only and don't trigger the divert.

5. **`agents.md` `_init_provider_state` doc**
   - Read `the_one/agents.md` around line 1485 to confirm `## Provider type extension checklist` heading exists and find the last item (current: 6 items)
   - Add a 7th item documenting `_init_provider_state`:
     ```
     7. **`_init_provider_state(self, kwargs: dict) -> None`** (optional hook) — Called from `LLMProvider.__init__` after standard fields are set. Implement when the provider needs to capture configuration that's not part of the base fields (e.g., OpenRouter captures `app_url` and `app_name` from kwargs to populate OpenRouter HTTP headers). Reference implementation: see `_init_provider_state` in `openrouter_provider.py` (locate by symbol — line numbers drift).
     ```
   - The exact wording can shift to match the existing checklist's voice; the key is the hook is named, signature documented, and a reference site cited

6. **`agents.md` "live-read across lazy-resolver boundary" pattern**
   - Read `the_one/agents.md` around line 219 to confirm `## Project Conventions` heading and find peer entries (e.g., the existing `### gated-debug-instrumentation`)
   - Add a new entry, e.g.:
     ```
     ### live-read-across-lazy-resolver-boundary

     When a value is lazily resolved on first call (e.g., `max_context_tokens` resolved at first `complete()`/`stream()`), readers downstream of the resolver must read the value LIVE, not pre-capture it at function entry. Eager capture at a caller's entry point will see the pre-resolution sentinel or default.

     **Why**: F6.5 introduced the lazy-resolver pattern (Ollama `/api/show` per-model context-window query); F6.5 L4 found a bug in `_process_and_broadcast` that captured `max_context_tokens` BEFORE the resolver had fired. F7 L05 pins the contract with a regression test (`test_max_context_tokens_live_read_across_resolver`).

     **Pattern**: read `provider.max_context_tokens` at the point of use, not at the start of the surrounding function. If a function's loop reads it, read it inside the loop, not before it.
     ```
   - Match the existing voice and structure of peer entries

7. **`.env.example` `THE_ONE_DEV_MODE`**
   - Read `.env.example`; find a logical place (probably near other `THE_ONE_*` entries)
   - Add a line: `# THE_ONE_DEV_MODE=true  # Enables dev-only routes and gates (e.g., /admin design-language page); default false in production`
   - Verify by re-running the prior `grep` test

8. **`SECURITY-MODEL.md` additions** — ONE new bullet (Concourse rotation cadence dropped per pivot)
   - Add a new bullet under `## Future Work (NOT in scope today)` at L116, alongside the existing "MCP server trust boundaries" bullet at ~L120-122:
     - MCP `streamable-http` source URLs are not gated by `_is_safe_provider_url` (the LLM-provider equivalent gate exists for provider create/update/test endpoints). This is currently safe under the operator-trusted posture (operator configures their own MCP source URL) but is asymmetric with the LLM-provider path. A future "import MCP server from registry" feature would widen this gap. Suggested resolution: apply `_is_safe_provider_url`-equivalent to `MCPSource.config.url` at create/update time.
   - Match the file's existing voice (terse, declarative). No Concourse-related additions — that surface is gone in Leg 4.

9. **OpenRouter `_APP_URL` / `_APP_NAME`**
   - Read `the_one/llm/openrouter_provider.py:38-39` to confirm current values (`"https://github.com/msieurthenardier/the-one"` and `"the-one"`)
   - Update to GleepGlorp AI identity:
     ```python
     _APP_URL = "https://github.com/msieurthenardier/the-one"  # GleepGlorp AI — repo name preserved per Mission 08 constraint
     _APP_NAME = "GleepGlorp AI"
     ```
   - Note: the GitHub URL stays as `the-one` because Mission 08's constraint explicitly preserves the repo name; only the display name changes. Add a brief inline comment so future readers understand the asymmetry

10. **Verify Leg 1 and Leg 2 baselines preserved**
   - `ruff check the_one/ tests/ && ruff format --check the_one/ tests/` — both exit 0
   - `pytest --tb=no -q` — exits 0
   - If any new violations or test failures surface, address them before commit

11. **Commit — two commits, not one, so per-class revert stays clean** (per Architect design review)
    - **Commit A — security + CI**: OAuth callback escape, OAuth XSS regression test, `_clean_npx` allowlist + its test, `pip-audit` in pyproject.toml, `pip-audit` step + updated doctor probe in ci/pipeline.yml, Makefile doctor target updated to include `pip_audit`.
      - `git add the_one/interfaces/web/api.py the_one/mcp/cache_cleanup.py tests/<oauth_test_file> tests/<cache_cleanup_test_file> pyproject.toml ci/pipeline.yml Makefile`
      - Commit message: `fix(security/ci): OAuth callback XSS escape; npx pkg allowlist; pip-audit adoption`
    - **Commit B — docs**: agents.md two additions, .env.example line, SECURITY-MODEL.md two additions, OpenRouter `_APP_*` rebrand strings.
      - `git add the_one/agents.md .env.example SECURITY-MODEL.md the_one/llm/openrouter_provider.py`
      - Commit message: `docs: agents.md hook + lazy-resolver pattern; .env.example DEV_MODE; SECURITY-MODEL MCP/Concourse notes; OpenRouter rebrand strings`
    - Inspect each: `git diff --cached --stat` between stages
    - Why two commits: per Architect, the flight technical approach promises per-leg `git revert` is clean rollback. Bundling 8 unrelated files in one commit means a revert-for-one-regression pulls back everything. Splitting on the natural security-vs-docs axis keeps revert blast radius proportional to the change class.

## Edge Cases

- **Existing OAuth tests assert string content of the callback page**: the JSON-escape change will alter the rendered string. Update any string-equality assertions to match the new shape; assertions about behavior (parses cleanly, doesn't execute injected script) should still pass.
- **`_clean_npx` is called with a legitimate `@scope/pkg` name** (contains `@` and `/`): both characters must be in the allowlist. Verify the regex includes them.
- **`pip-audit` floods the leg with findings**: bracket the leg's success on "pip-audit invokable and CI step non-blocking", NOT on "zero vulnerabilities reported". Findings are a M10 deliverable.
- **`SECURITY-MODEL.md` already has a "Future Work" section but it's not exhaustively structured**: add a clearly demarcated subsection (e.g., `### MCP source URL gating`) rather than free-floating text, so the next maintenance pass can find it grep-ably.
- **The `_APP_NAME` change appears in HTTP request headers sent to OpenRouter**: this is analytics-side, not user-visible; the change should not break any test that asserts request behavior unless a test specifically string-matches the old name. If such a test exists, update it.

## Files Affected

- `the_one/interfaces/web/api.py` — OAuth callback JSON escape (lines around 1681-1688 and 1830-1845)
- `the_one/mcp/cache_cleanup.py` — `_clean_npx` allowlist (around line 248)
- `pyproject.toml` — `pip-audit` in dev extras
- `ci/pipeline.yml` — `pip-audit` non-blocking step in test task
- `the_one/agents.md` — `_init_provider_state` entry + live-read pattern entry
- `.env.example` — `THE_ONE_DEV_MODE` line
- `SECURITY-MODEL.md` — Future Work addition (MCP URL gating asymmetry only; Concourse rotation cadence dropped)
- `the_one/llm/openrouter_provider.py` — `_APP_URL` and `_APP_NAME` lines (38-39)
- Possibly `tests/test_mcp_cache_cleanup.py` (or equivalent) — new test for `_clean_npx` allowlist
- Possibly `tests/test_oauth_callback.py` (or similar) — assertion updates for the escape change
- `flight-log.md` — Leg Progress entry on completion

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing — broad pytest exits 0
- [ ] OAuth XSS fix manually verified (mock IdP response with `</script>` payload; browser does not execute)
- [ ] `pip-audit` runs cleanly; findings (if any) noted in flight log for M10 context
- [ ] All carry-forward items closed in the maintenance report's Known Debt section (update `maintenance/2026-05-15.md` checkboxes if applicable)
- [ ] Update `flight-log.md` with leg progress entry
- [ ] Set this leg's status to `completed`
- [ ] Check off this leg in `flight.md`
- [ ] If this is the final leg of the flight:
  - [ ] Update `flight.md` status to `landed`
  - [ ] Check off this flight in `mission.md`
- [ ] Commit all changes together (code + docs + flight artifacts)
