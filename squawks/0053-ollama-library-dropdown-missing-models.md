# Squawk 0053: Ollama "Pull Model" dropdown lists only 20 cloud models, not the library

**Status**: open
**Type**: defect
**Severity**: routine
**Reported**: 2026-09-15
**Completed**: —

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
*(written at completion)*

## Verification
`GET /api/ollama-library/search` with empty `q` returns ≥ 200 entries
including `llama3.2`; `?q=llama` returns the llama family; the cloud models
from `/api/tags` are still present. `TestOllamaLibrarySearch` updated to the
new fixture and green; `make test-unit` green; `ruff check` /
`ruff format --check` clean.

## Sign-Off
*(written at completion)*
**Reviewer**:
**Verdict**:
**Commit**:
