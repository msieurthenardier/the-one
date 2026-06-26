# Flight Log: Human Acceptance Testing — Provider Chat Sweep

**Flight**: [HAT — Provider Chat Sweep](./flight.md)

> Running ledger of HAT findings. One entry per defect/rough-edge observed while
> exercising chat on the installed app. Capture enough to act:
>
> - **Provider / model** (verify the model id is live before relying on it)
> - **Version/commit under test** (installed app build)
> - **Repro** (steps)
> - **Observed vs. expected**
> - **Evidence** (screenshot, log excerpt, WS frame — anonymize paths)
> - **Disposition** (DD4): leg `{NN}-{slug}` here / spun-out flight / mission Known Issue

## Environment Under Test
- App: installed GleepGlorp app (web UI `http://localhost:8484` or desktop `the-one app`)
- Baseline version: 0.2.9 (record actual commit per session)
- Providers in scope: Anthropic, Ollama (native `/api/chat`), OpenRouter

---

## Findings

### F09-01 — `search_tools` silently caps at 8 results; tools beyond the top 8 become invisible

- **Provider / model**: Ollama — `ministral-3:8b` (agent "Sonos Agent", provider config `ec0d0a56cbf0`).
- **Version under test**: 0.2.9 (installed app, `http://localhost:8484`).
- **MCP source**: Sonos (`e7c2e3106487`) — exposes **37 tools**, all enabled (no
  `enabled_tools`/`disabled_tools` restriction on the agent).
- **Repro**: In a Sonos Agent chat, ask it to change a speaker's volume ("turn the
  column on the kitchen down to 20"), then "isnt there a set_volume tool?" / "how many
  sonos tools do you have available?". Session `a15d1d79aa8f`.
- **Observed**: Agent reports exactly **8 tools** (`list_speakers`, `list_groups`,
  `refresh_speakers`, `now_playing`, `play_url`, `play_file`, `pause`, `resume`) and
  states there is **no `set_volume` tool** — then tries pause/resume workarounds.
- **Expected**: `set_volume` exists on the Sonos MCP server (verified via
  `/api/mcp-sources`), along with ~28 others the agent never saw (`mute`, `unmute`,
  `stop`, `next_track`, `previous_track`, `group`, `ungroup`, `partymode`, `say`,
  `dissolve_all_groups`, and the full `playlist_*` family).
- **Root cause**: Lazy tool-discovery protocol — the model is shown only
  `search_tools` + `continue` and must search to load tools
  (`the_one/agent/core.py` `_compute_visible_schemas`). `search_tools` hard-caps
  non-empty queries at **8** (`the_one/tools/_search_tools.py:51`
  `_MAX_SEARCH_RESULTS = 8`, applied at ~`:217`). With 37 candidate tools, ranking is
  token-overlap (`:135-143`) with ties broken by registration order, so a query like
  "volume"/"sonos" returns 8 tools and `set_volume` falls outside the cut and is
  **silently dropped**. The result carries **no truncation signal**, so the model
  concludes the tool does not exist. *(Mechanism is provider-agnostic — any agent on
  an MCP source with >8 tools is exposed — but surfaces hardest on small Ollama models
  that issue one narrow search and give up.)*
- **Evidence**: chrome-devtools snapshot of session `a15d1d79aa8f` (agent claims "8
  tools", no `set_volume`); `/api/mcp-sources` cache showing the 37-tool Sonos catalog
  incl. `set_volume`; code citations above.
- **Disposition (DD4)**: in-flight leg — fix in `the_one/tools/_search_tools.py`
  (+ possibly the `search_tools` result shape and core wiring). Contained to the
  tool-search mechanism; no `LLMProvider`-contract impact. → leg `01-search-tools-truncation`.
- **Status**: fix implemented (leg `01-search-tools-truncation`) — `_filter_candidates`
  returns the pre-cap total; name-token matches are guaranteed and ranked above
  description-only matches; truncated results report the honest "N of M" total + a
  recovery hint. Unit tests green (`tests/test_search_tools.py` 54/54 in `.venv`).
  **Pending live re-verify** — operator tests against the packaged installer, not the
  editable dev install, so this rides into release **0.2.10**: bump + fix committed on
  branch `fix/search-tools-truncation` → PR → merge to `main` → Concourse `the-one`
  pipeline (`ci` → `build-windows-installer`) publishes `the-one-setup-0.2.10.exe` to
  the MinIO `the-one-installers` bucket. Operator installs 0.2.10, then a fresh Sonos
  Agent chat must find & call `set_volume` to close F09-01 / the leg.
