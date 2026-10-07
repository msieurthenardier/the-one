# Squawk 0133: The README is too complex and out of date

**Status**: completed
**Type**: servicing
**Severity**: routine
**Reported**: 2026-10-07
**Completed**: 2026-10-07

## Report

`README.md` is the project's front page, and several of its claims are now false. It is also hard to read: mission history and implementation internals sit beside the install steps. The operator decided on these changes on 2026-10-07:
- Rewrite it for a **user first**: what the app is, what it can do, how to install it (Windows installer or pip), and how to set up a first provider and agent.
- End with a **short "Developing" section** that points to `CLAUDE.md`, `the_one/agents.md` and `missions/`.
- Move architecture internals and mission history out.
- **Drop the screenshots.** They predate the Mission 25 redesign.

## Evidence

- **No auth:** "Security" says "no auth on routes by design". There has been a local-API credential gate since Mission 20 Flight 1 (`SECURITY-MODEL.md` "Authentication", `the_one/api_credential.py`).
- **Providers:** "Supported LLMs" says "four LLM providers". There are six provider types: `the_one/db/_provider_types.py::PROVIDER_TYPES`, which includes `openai-compatible` and `anthropic-plan` (Claude Pro/Max sign-in, M19). `mock` is dev-only.
- **Screenshots:**
  - The Settings caption says Providers "is now a table". It has been a tile grid again since the Mission 25 Flight 3 checkpoint (`CLAUDE.md` "Settings item pages").
  - All three images (`docs/screenshots/{chat,studio,admin}-dark.png`) predate the M25 rail and list panes.
  - Nothing outside `README.md` uses them, apart from historical mission artifacts.
- **Missing features:** knowledge bases and retrieval (M24) and the self-configuration surface (M21) are absent from "What this is".
- **Too complex:**
  - The Connectors paragraph is one sentence of about 150 words of mission history.
  - The Docker-removal callout (M15/M16) is history, not guidance.
  - "Architecture" restates `CLAUDE.md`/`agents.md` with mission numbers.
  - The tool count ("21 built-in tools") and the Ollama example (`qwen2.5:7b`) are unverified against the current build.

## Corrective Action
Rewrote `README.md` user-first (88 lines, was 139): brand header, What this is, What it can do, Install (Windows installer, pip from source, compressed desktop window), Getting started, Supported LLM providers (six real types, `mock` omitted), Security, Accessibility, and a short Developing section pointing to `CLAUDE.md`, `the_one/agents.md`, `SECURITY-MODEL.md` and `missions/`. Removed the Architecture section, mission-number references, the Docker callout, the Connectors run-on, and the Screenshots section. `git rm`'d `docs/screenshots/{chat,studio,admin}-dark.png`; the directory is gone. No other file or test needed changes.

## Verification
Test and lint results are recorded in the handoff report. Claims checked:
- Single-user, local-only; all routes but `GET /api/live` need the credential; local origins only: `SECURITY-MODEL.md` "Authentication" and the Origin-allowlist section.
- 22 built-in tools: counted by instantiating `BuiltinToolProvider().get_tools()` in `the_one/tools/builtins.py` (22 returned; `search_tools` is separate and not counted).
- Six provider types: `the_one/db/_provider_types.py::PROVIDER_TYPES` minus `mock`; Anthropic plan description from CLAUDE.md.
- Ollama `http://localhost:11434` with `/v1` added automatically: `the_one/llm/ollama_api.py::ensure_v1`. Example model `llama3.2` is a generic Ollama library name; `qwen2.5:7b` was dropped.
- Commands `chat`, `serve`, `app`, `version`, `doctor`, `rotate-api-credential`: `the_one/main.py::cli_entry`. Port 8484: CLAUDE.md. Extras `all-llms`, `gui`, `dev`: `pyproject.toml`.
- Linux packages `python3-gi gir1.2-webkit2-4.1`, close-to-tray, single-instance focus, browser fallback: the previous README and CLAUDE.md "Desktop launcher".
- Settings pages "Providers" and "Encryption": `static/js/settings-pages.js`.
- Connectors Discord and Telegram: `docs/connector-setup.md`. Self-configuration off by default with optional approval: CLAUDE.md.
- All relative links and the logo path resolve (script check). No `screenshots` reference remains in the README; no test reads the README or the images.

Planned checks:
- Every factual claim left in the README is checked against the working tree: provider types, tool count, commands, ports and paths.
- Every relative link resolves.
- No `docs/screenshots/` reference remains, and the three images are removed.
- `ruff check` and `ruff format --check` are unaffected.
- `make test-unit` is green (some unit tests may read the README).

## Sign-Off

**Reviewer**: independent batch Reviewer (Haiku tier: no credential, gate, sandbox or self-configuration-identity surface in the diff); `make test-unit` 5496 passed, 10 skipped; static guards 265 passed; ruff clean
**Verdict**: confirmed (`[HANDOFF:confirmed]`)
**Commit**: `squawk: turnaround 2026-10-07` on branch `squawk/turnaround-2026-10-07`
