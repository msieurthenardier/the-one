# Squawk 0053: Ollama "Pull Model" dropdown lists only 20 cloud models, not the library

**Status**: completed
**Type**: defect
**Severity**: routine
**Reported**: 2026-09-15
**Completed**: 2026-10-07

## Report

The Pull Model dropdown on an Ollama provider's models panel (Administration
→ provider → Models) offers only 20 models, every one of them a large
cloud-hosted build (`kimi-k3`, `deepseek-v4-pro:0813`, `qwen3.5:397b`,
`mistral-large-3:675b`, `nemotron-3-ultra`, `glm-5.x`, `minimax-m3`,
`gpt-oss:20b`/`120b`, `gemma4:31b`, …). Everyday pullable models —
`llama3.2`, `llama3.1`, `qwen3`, `gemma3`, `phi4`, `mistral`, `deepseek-r1`,
`nomic-embed-text`, `bge-m3` — are absent, so they cannot be pulled from the
UI at all (the dropdown is a native `<select>` with no free-text entry).

The *installed* model list is unaffected: `ollama list` and
`GET /api/providers/{id}/models` agree (two models, with capabilities). Only
the pull catalog is short.

Reproduce: `GET /api/ollama-library/search` with empty `q` → 20 entries.
Or open the Ollama provider panel in the packaged Windows app and inspect the
Pull Model select.

Root cause: the catalog is sourced from `https://ollama.com/api/tags`, and
that upstream endpoint now returns only the 20 cloud models (verified with
curl on 2026-09-15; sizes up to 1.5 TB). The app mirrors it faithfully — the
same 20 names, byte for byte. The full library is only published as HTML at
`https://ollama.com/library` (240 entries on 2026-09-15); no JSON endpoint
exposes it.

Fix direction: populate the cache from the `/library` page instead — each
`<li>` carries `<a href="/library/{name}">`, size-tag spans
(`text-blue-600`: `1b`, `3b`, `70b`, …) and capability spans
(`text-indigo-600`: `tools`, `vision`, `thinking`, `embedding`). A prototype
regex over the page parsed all 240 entries cleanly. Keep `/api/tags` as a
supplementary source (it is the only place the cloud models and byte sizes
come from), keep the 300 s cache and stale-cache fallback, and keep the
`{name, size}` response shape. HTML-sourced entries have no byte size, which
the dropdown already tolerates (`size > 0` guard). Whether to emit one entry
per name or one per `name:size` variant is the implementer's call; bare
names pull `:latest`. A free-text pull field alongside the dropdown would be
a nice belt-and-braces, but that is new behavior — not this squawk.

## Evidence

- `the_one/interfaces/web/api.py:search_ollama_library` — `resp = await client.get("https://ollama.com/api/tags")`; the comment "The library is ~100 models and renders into a native `<select>`" records the endpoint's earlier behaviour
- `curl -s https://ollama.com/api/tags | python3 -c 'import sys,json; print(len(json.load(sys.stdin)["models"]))'` → `20` (2026-09-15)
- `curl -sL https://ollama.com/library | grep -o 'href="/library/[^"]*"' | sort -u | wc -l` → `240` (2026-09-15)
- `GET /api/ollama-library/search` on the running packaged app → the same 20 names as upstream, `diff` empty
- `tests/test_provider_api.py:TestOllamaLibrarySearch._mock_httpx` — `mock_resp.json.return_value = {"models": models}`: the fixture fakes the JSON shape and will need an HTML fixture alongside it
- `the_one/interfaces/web/static/js/areas/admin/provider-models.js:loadLibraryOptions` — `fetch('/api/ollama-library/search')`; size suffix rendered only when `Number(models[i].size) > 0`

## Corrective Action
`search_ollama_library` now builds its cache through a new `_fetch_library_models()` that merges two sources by name: the `https://ollama.com/library` HTML page (parsed by the new pure helper `ollama_api.parse_library_html`, one entry per bare name, size `"0"`) and `/api/tags` (cloud models and byte sizes; a byte size overrides the HTML placeholder). Each source is fetched in its own try block, so one failing never wipes the other; a page that parses to zero entries contributes nothing (a failed source, not an empty library). If both yield nothing the stale cache is kept (or `[]` when empty). The 300 s TTL, `{name, size}` shape, alphabetical sort and no-cap behavior are unchanged. Chosen over a single-source swap because `/api/tags` is the only source of cloud models and sizes, and over per-variant entries because bare names pull `:latest` and keep the dropdown short. The regex tolerates attribute order, quote style, absolute URLs, query strings and fragments.

## Verification
Implementation run (Developer):
- Added `tests/fixtures/ollama_library_excerpt.html` (4 real entries trimmed from the live page) and updated `TestOllamaLibrarySearch` (`_mock_httpx` now routes per URL: HTML for `/library`, JSON for `/api/tags`); new tests cover merge/no-dupes/sort, `q` filtering, each source failing alone, zero-entry parse, both-empty, both-fail stale-cache fallback; new `TestParseLibraryHtml` (4 tests).
- `PYTHON=.venv/bin/python bash scripts/run-tests.sh tests/test_provider_api.py -x --timeout 30` -> 190 passed.
- `make test-unit` -> 5452 passed, 10 skipped, 0 failed.
- `ruff check` and `ruff format --check` clean.
- Live check (new `_fetch_library_models()` against real upstream, 2026-10-07): 251 entries (245 library names + cloud-only tags); `llama3.2`, `qwen3`, `nomic-embed-text` present; 14 entries carry byte sizes from `/api/tags`.

Original acceptance:
`GET /api/ollama-library/search` with empty `q` returns ≥ 200 entries
including `llama3.2`; `?q=llama` returns the llama family; the cloud models
from `/api/tags` are still present. `TestOllamaLibrarySearch` updated to the
new fixture and green; `make test-unit` green; `ruff check` /
`ruff format --check` clean.

## Sign-Off

**Reviewer**: independent batch Reviewer (Haiku tier: no credential, gate, sandbox or self-configuration-identity surface in the diff); `make test-unit` 5496 passed, 10 skipped; static guards 265 passed; ruff clean
**Verdict**: confirmed (`[HANDOFF:confirmed]`)
**Commit**: `squawk: turnaround 2026-10-07` on branch `squawk/turnaround-2026-10-07`
