# Leg: 03-outside-value-guard

**Status**: completed
**Flight**: [MCP servers and model providers](../flight.md)

## Objective

Add a deterministic guard to `propose_change` and `fill_form`, for every kind. After
GleepGlorp has read outside content, the guard refuses a link, address, email address, command
or loader key that did not come from the operator.

## Context

- **Flight DD7** is the authority for the rules. The flight spec's DD7 text, as revised after
  both Architect cycles, wins over any paraphrase here.
- **Why now:** MCP servers and providers (Legs 4 and 5) carry URLs, commands and env. Flight 3
  measured about 1 planted link in 12 fills on operator-linked pages with only the prompt
  rule.
- **This leg ships the guard for every kind.**
  - It has teeth today only for the agent kind's free text (system prompt, description).
  - The declared-field and loader-key rules are built and tested on a **stub kind** with
    declared fields, because no real kind declares them until Leg 4.
  - Legs 4 and 5 mark their fields and add their own falsification cases.
- **What the stored history looks like** (verified):
  - A USER message's `content` is the operator's text: a `str`, or a list of blocks whose
    `TextContent` is the typed text, beside images.
  - The page line is **not** in `content`. It is `Message.page` and is projected only when the
    provider request is built (`llm/base.py`, `[Page: …]`), so it is never mistaken for typed
    text.
  - Marked USER messages carry `peer_name`, `routine_id` / `routine_untrusted_sources`, or
    `proposal_id` / `proposal_event` (approval and dismissal turns, whose text is built from
    summaries and titles).
  - A tool call's arguments are `ToolCall.arguments` (a dict) on the assistant message. Its
    result is a TOOL message whose `tool_result.tool_call_id` links back.
  - The fetch tool is `fetch_url(url)` (`tools/web.py:244`). For HTML it returns readability
    plus markdownify output, with markdown escapes. It follows redirects up to the configured
    cap.
- **How the tools use taint today:**
  - `proposals/tool.py:128-131` runs `guard.check(...)`, then `compute_taint(self._agent,
    current_tool_call_id.get(), turn)`.
  - `fill/tool.py:114-117` does the same.
  - `compute_taint` (`agent/taint.py:97`) finds the anchor (the assistant message holding the
    tool call) by a backwards scan, then classifies every message before it.

## Inputs

- Legs 1a, 1b and 2 landed (uncommitted): the `kinds/` registry, `FieldSpec.address_or_command`
  (added in 1a, unused so far) and `FieldSpec.path`.
- `the_one/agent/taint.py`, `gleepglorp/proposals/tool.py`, `gleepglorp/fill/tool.py`,
  `gleepglorp/proposals/guard.py`, `the_one/tools/web.py` (`FetchUrlTool`).

## Outputs

- **`the_one/agent/taint.py`:** the anchor scan is extracted into
  `find_anchor(messages, tool_call_id) -> int | None`. `compute_taint` uses it, and its behaviour
  is unchanged.
- **`the_one/gleepglorp/outside.py`** (new):
  - `collect(agent, tool_call_id) -> Sources | None`. `None` means no anchor, which fails
    closed. `Sources` holds:
    - `typed`: the normalised tier-1 texts;
    - `typed_urls`: the normalised URLs found in them;
    - `linked`: the normalised tier-2 texts, each with the URL it came from.
  - `check(kind, changes, sources) -> str | None`, the refusal sentence or `None`.
  - Helpers, each tested: `normalize_url`, `extract_addresses`, `deescape`, `token_match` and
    `is_loader_key`.
- **`FieldSpec`** gains `rows: bool = False`, a row-typed `{key: value}` field (DD2). The loader
  rule applies to the keys of a field that is both `rows` and `address_or_command`.
- **Both tools** call the guard when `compute_taint` says `untrusted`. The order is `normalize`,
  then `guard.check`, then `compute_taint`, then the outside-value check, then record. The
  current code computes taint after `guard.check`; keep that order and insert the new check
  after it.
- **Docs:**
  - `SECURITY-MODEL.md`: the residual paragraph (`:1380`) is rewritten to say the link and
    address part is now enforced in code, with instruction text still a prompt-level residual.
    A guard paragraph is added beside the fill and proposal sections.
  - `the_one/agents.md`: an "Outside-value guard (M36 F4)" section.

## Acceptance Criteria

- [ ] **AC1. `find_anchor` is extracted with no behaviour change.** These pass unedited:
  - `tests/test_taint_results.py`, `tests/test_routine_tools_taint.py` and
    `tests/test_notes_tools.py`;
  - `tests/test_evals_gleepglorp_fills.py` and `tests/test_evals_gleepglorp_proposals.py`.
- [ ] **AC2. Tier 1 (`typed`).** It is the text of USER messages before the anchor with:
  - `peer_name is None`;
  - `channel_id is None` and `channel_name is None` (defence in depth: GleepGlorp takes no
    channel turns today);
  - `routine_id is None` and `routine_untrusted_sources` empty;
  - `proposal_id is None` and `proposal_event is None`.

  The text is the string content, or the `TextContent` blocks of a list content. It never
  includes `Message.page`, images, assistant text or tool results. A test builds a history with
  each kind of marked USER message, each carrying a URL, and shows that none of those URLs
  counts.
- [ ] **AC3. Tier 2 (`linked`).** It is the `tool_result` content of `fetch_url` calls before the
  anchor that meet two conditions:
  - **The call's `url` matches a tier-1 URL:** both sides are normalised (AC5) and compared as
    whole URLs. Or GitHub: the call's URL is
    `raw.githubusercontent.com/{owner}/{repo}/…` and tier 1 holds a URL on `github.com` whose
    path starts `/{owner}/{repo}`. Owner and repo compare case-insensitively, with `.git`
    stripped, and any further path (`/tree/…`, `/blob/…`) is allowed.
  - **The result is a success,** starting with `[2xx]` (`^\[2\d\d\]`). `[error]`, `[404]`,
    `[500]` and other results never count.

  Tool calls are mapped **per assistant message**: a TOOL message matches only the calls of the
  nearest preceding assistant message, as `compute_taint` does, because Ollama ids repeat across
  turns. A test with a repeated id across two turns shows that the right URL is attributed. A
  `fetch_url` in the **same** assistant message as the proposing call is after the anchor, so it
  never counts; a test covers this.

  `web_search`, any other tool, and a `fetch_url` of a URL the operator did not type are never
  tier 2. Tests cover the exact match, the scheme-less operator URL, the `www.` difference, the
  GitHub raw rule (match, other repo, other owner, case), a fetch of an untyped URL, and an
  error result.
- [ ] **AC4. The check, run only when `untrusted`.**
  - **The input shape.** `check()` receives `norm.changes`, keyed by `FieldSpec.stored` (the
    string key; a `path` is used only to read and write the stored row).
    - A `rows` field's value is a `{key: value}` dict of strings.
    - A row the fill leaves for the operator (DD9's Sensitive handoff) has the value `""`, and an
      empty value is never checked.
    - The stub kind in AC7 uses exactly this shape, so Leg 4 does not discover a mismatch.
  - **What is scanned and what is skipped.**
    - **Scanned:** every `text` field; every `names` field **without** a `ref`; the `rows`
      fields; and declared fields.
    - **Skipped:** `ref`-resolved fields (provider, MCP, knowledge-base ids, and built-in tool
      names, which are ids or fixed names, never addresses); hidden fields (`anchor_at`); and
      the routine `schedule` object (canonical and validated).
    - A test pins the scanned and skipped sets for the agent, rule and routine kinds.
  - **Every value and every source text is folded first.** NFKC normalisation, then zero-width
    and bidi control characters removed, so fullwidth and invisible-character forms are compared
    in their plain form.
  - **Declared fields** (`address_or_command`):
    - **A URL-shaped value** (one `extract_addresses` finds as a URL, including protocol-relative
      `//host/path`) passes only by **normalised equality** with a typed URL or with a URL
      extracted from linked text. It never passes by substring.
    - **Any other value** must `token_match` a typed or linked source text.
    - **For a list field such as `args`:**
      - every item of 4 or more characters that does not start with `-` must `token_match`;
      - **all** items, together with the kind's companion command field when one is declared,
        must appear in **one single** source text (one typed message, or one fetch result).

      So a command cannot be stitched together from fragments of different sources. A README's
      JSON config form (`"command": "npx", "args": ["-y", "@pkg"]`) still passes, because both
      parts are in that one page.
  - **Loader keys.** For a `rows` field marked `address_or_command`, a key where
    `is_loader_key(key)` is true must appear in **typed** text, and so must its value. Linked
    text never counts for either.
  - **Free text** (the other scanned values). Every address `extract_addresses` finds must come
    from typed text:
    - URLs, by normalised equality with a typed URL;
    - emails, case-insensitively;
    - `host:port`, bare domains and IP literals, by whole-token equality with an address
      extracted from typed text.
  - **Anything else in free text is not checked.** Instruction text is a prompt-level residual
    (DD7).
  - **A trusted turn is never checked.**
  - **No anchor** (`collect` returns `None`): every declared-field value, every loader key and
    every free-text address is refused.
- [ ] **AC5. Normalisation and matching** (DD7 "Matching rules"), as pinned functions:
  - **`normalize_url`:**
    - it adds `https://` when the scheme is missing;
    - it lowercases the scheme and host, and drops a leading `www.`;
    - it drops the fragment and keeps the query;
    - it removes one trailing `/` from the path;
    - it keeps the port.
  - **`extract_addresses(text)`** runs on folded text and finds:
    - `scheme://…` URLs. The scheme is matched case-insensitively, for `http`, `https`, `ftp`,
      `ws`, `wss`, `ssh`, `git` and `file`, plus `mailto:` addresses.
    - Protocol-relative `//host/path`.
    - `www.`-prefixed hosts.
    - **Bare domains, with or without a path:** a dotted name whose last label is in a TLD
      allowlist. The allowlist is one pinned constant: common generic TLDs (`com`, `net`,
      `org`, `info`, `biz`, `io`, `ai`, `co`, `dev`, `app`, `xyz`, `site`, `online`, `tech`,
      `cloud`), common country TLDs (`us`, `uk`, `de`, `fr`, `nl`, `eu`, `ca`, `au`, `jp`, `in`,
      `ru`, `cn`, `br`), and the reserved or internal names (`test`, `example`, `invalid`,
      `local`, `internal`, `localhost`, `lan`, `home`, `corp`).
      - It deliberately **excludes TLDs that collide with file extensions**: `py`, `md`, `js`,
        `ts`, `sh`, `rs`, `go`, `pl`, `rb`, `cs`, `json`, `yaml`, `txt`.
      - `garden-stats.example.test` must be extracted; it is the planted link in
        `evals/gleepglorp/fixtures/web/gg-fill-4.html`.
    - `host:port` (the host is a dotted name, `localhost` or IPv4), and bracketed IPv6
      `[::1]:8080`.
    - Bare IPv4 literals.
    - Emails.

    Trailing punctuation (`.,;:!?)]}>'"`) is trimmed. A closing `)` is kept only when the URL
    has a matching `(`.

    Every pattern requires a **trailing boundary** (`(?![\w.])` after a port or TLD), so an
    Ollama tag never yields an address.

    **Must-pass (never extracted):** `10:30`, `16:9`, `file.py:12`, `main.py`, `README.md`,
    `Node.js/express`, `v1.2.3`, `phi3:3.8b`, `qwen2.5:14b`, `llama3.1:70b`, `gemma3:27b`,
    `deepseek-r1:1.5b`, `gpt-4o`, `e.g.`, `i.e.` and `2026-11-21`.

    **Must-extract:** `garden-stats.example.test`, `Evil.COM/x`, fullwidth `ｅｖｉｌ．ｃｏｍ／ｘ`
    (after folding), `ev​il.com` (after folding), `//evil.test/x`, `ftp://evil.test`,
    `10.0.0.5`, `[::1]:8080` and `bookings@trips-example.test`.

    **Accepted residuals** (documented, not extracted): defanged forms (`hxxp://`,
    `evil[.]com`), domains on TLDs outside the allowlist, and instruction text.
  - **`deescape`** removes markdown backslash-escapes (`\` before ASCII punctuation), decodes
    HTML entities and collapses whitespace.
    - Linked text is matched against **both** its raw (folded) form and its de-escaped form,
      so JSON and plain-text bodies are not corrupted.
    - **A real-pipeline test** calls `FetchUrlTool.execute`, with its transport replaced by an
      `httpx.MockTransport` (monkeypatch `_build_transport`), on fixture HTML. The fixture has
      enough prose that readability keeps the body. It holds a command in a `<code>` block and
      in running text, plus `server_github` and `@scope/pkg_name`. The test checks that the
      guard's linked form of the result contains each value.
  - **`token_match(value, text)`.** The value is whitespace-normalised and found in the text
    with no character from `[A-Za-z0-9_\-./@:%~]` immediately before or after it. A trailing
    `.`, `,` or `;` is allowed after the value only when whitespace or the end of the text
    follows.
    - Must-fail: `sh` in `share`; `good.com` in `good.com.evil.test`; `good.com` in
      `good.com/x`; `evil.com` in `good.evil.com`.
    - Must-pass: `npx -y @acme/mcp-server` inside a backticked sentence, and at a sentence end
      before `.`; `-y` after `npx `.
  - **`is_loader_key`.** The key is folded (strip, NFKC, uppercase) and then matched with
    `fnmatch` against a pinned glob list:

    | Group | Globs |
    |---|---|
    | Exact names | `PATH`, `ENV`, `SHELL`, `IFS`, `BASH_ENV`, `PROMPT_COMMAND` |
    | Loader and linker | `LD_*`, `DYLD_*` |
    | Node | `NODE_OPTIONS`, `NODE_PATH`, `NODE_EXTRA_CA_CERTS` |
    | Package managers | `NPM_CONFIG_*`, `YARN_*`, `PIP_*`, `UV_*`, `CARGO_*`, `GOPROXY`, `GOFLAGS` |
    | Python | `PYTHONPATH`, `PYTHONHOME`, `PYTHONSTARTUP`, `PYTHONUSERBASE` |
    | Perl, Ruby, Java, .NET | `PERL5OPT`, `PERL5LIB`, `RUBYOPT`, `RUBYLIB`, `JAVA_TOOL_OPTIONS`, `_JAVA_OPTIONS`, `JDK_JAVA_OPTIONS`, `CLASSPATH`, `DOTNET_STARTUP_HOOKS` |
    | Git | `GIT_SSH_COMMAND`, `GIT_PROXY_COMMAND`, `GIT_EXEC_PATH`, `GIT_CONFIG*`, `GIT_SSL_*` |
    | Proxies and certificates | `*_PROXY`, `SSL_CERT_FILE`, `SSL_CERT_DIR`, `REQUESTS_CA_BUNDLE`, `CURL_CA_BUNDLE` |

    Pinned cases:
    - loader keys: `HTTPS_proxy`, `no_proxy`, ` path ` (with surrounding spaces) and fullwidth
      `ＰＡＴＨ`;
    - not loader keys: `PATHNAME`, `ENVIRONMENT` and `GITHUB_TOKEN`.

    The list lives in one constant, and a test pins it.
- [ ] **AC6. The refusal.** One sentence that:
  - names the field label;
  - names the source when it can (the **host only** of the page whose text held the value, or
    "outside content" otherwise);
  - tells GleepGlorp to quote the value and its source to the operator. To be accepted, the
    value must then be typed by the operator in their own message; a bare "go ahead" does not
    supply it.

  Every model- or page-derived part (the value, the host) goes through `shape._q` (the echo
  cap). Nothing is recorded, and no frame is sent.
- [ ] **AC7. Wired into both tools for every kind.**
  - `propose_change` and `fill_form` run the check after `guard.check` and taint, before the
    insert.
  - **Tests through the real tools on the agent kind:**
    - an untrusted turn (`fetch_url` result present) whose fill puts a fetched-page URL into
      `system_prompt` → refused, no row;
    - the same URL typed by the operator → allowed and flagged untrusted;
    - a trusted turn with a model-invented URL → allowed;
    - an email from the page in `description` → refused.
  - **Stub-kind tests for the declared fields and rows.** A test-only kind is registered by
    monkeypatching `kinds.REGISTRY` and `kinds.get`, with a declared `url` field, a declared
    `command` field, a declared `args` list field and a declared `env` rows field, in the AC4
    input shape. Cases:
    - a command and args from an operator-linked page, in JSON config form → allowed;
    - from an unlinked page → refused;
    - from a search result → refused;
    - args stitched from two different pages → refused;
    - a URL `https://good.com` when the linked page holds `https://good.com.evil.test/x` →
      refused;
    - a `NODE_OPTIONS` key from a linked page → refused;
    - `NODE_OPTIONS` typed → allowed;
    - an empty Sensitive row value → not checked;
    - a declared field with no anchor → refused.
- [ ] **AC8. Falsification.** Each safety test is reported falsified, yes or no. At least
  these must be yes:
  - the marked-USER exclusion;
  - the untyped-fetch exclusion;
  - the free-text email refusal;
  - the loader-key-from-linked refusal;
  - the no-anchor refusal;
  - the token boundary, including `good.com` in `good.com.evil.test`;
  - the bare-domain extraction (`garden-stats.example.test`);
  - the stitched-args refusal;
  - the per-message call map (the repeated-id test).
- [ ] **AC9. No regression in the existing tool tests.** `tests/test_gleepglorp_proposals_tool.py`,
  `tests/test_gleepglorp_fill_tool.py`, `tests/test_gleepglorp_apply_error.py` and
  `tests/test_gleepglorp_*` pass with their assertions unedited.
  - If an existing test's history now trips the guard (for example a proposal with a fetched
    URL), **stop** and report it. That is a behaviour change to decide, not a pin to edit.
  - The evals suites (`tests/test_evals_gleepglorp*.py`) and `tests/test_evals_freeze.py`
    pass. `evals/` code is not edited in this leg.
- [ ] **AC10. Docs.** `SECURITY-MODEL.md` and `the_one/agents.md`, as in Outputs. The
  `SECURITY-MODEL.md` residual paragraph keeps its history ("accepted 2026-11-20") and adds the
  2026-11-21 change.
- [ ] **AC11. Gates.** `THE_ONE_TEST_NETNS=1 make test-unit` passes with 15 skips, and ruff is
  clean. No browser lane is needed: there is no client change.

## Verification Steps

- `.venv/bin/python -m pytest tests/test_gleepglorp_outside.py tests/test_taint_results.py tests/test_routine_tools_taint.py tests/test_notes_tools.py tests/test_gleepglorp_proposals_tool.py tests/test_gleepglorp_fill_tool.py tests/test_evals_gleepglorp_fills.py tests/test_evals_gleepglorp_proposals.py -x --timeout 60`.
- The real-pipeline de-escape test needs `readability` and `markdownify`, which are in the
  project's deps. If they are absent, skip with a reason; do not stub them.
- `THE_ONE_TEST_NETNS=1 make test-unit` in the background.

## Implementation Guidance

1. **`find_anchor`.** Extract the backwards scan from `compute_taint` into a function in
   `taint.py`, and call it from `compute_taint`. Run the taint tests.

2. **`outside.py` helpers first** (`normalize_url`, `extract_addresses`, `deescape`,
   `token_match`, `is_loader_key`), each with table-driven tests, including every must-pass
   string in AC5. Use `urllib.parse` for URLs. Keep the regexes in named module constants with
   a one-line comment each.

3. **`collect`.**
   - Walk `messages[:anchor]`.
   - Keep a map of tool-call id to `ToolCall` from each assistant message, as `compute_taint`
     keeps names. For each TOOL message, find its call. If the name is `fetch_url` and the url
     argument matches tier 1 (AC3), add the de-escaped result to `linked` with its URL.
   - Collect tier 1 from qualifying USER messages.
   - Because a fetch can precede the operator typing the URL in a later message, compute tier 1
     over the whole pre-anchor window first, then classify the fetches.

4. **`check`.**
   - Iterate the kind's `FieldSpec`s present in `changes`, keyed by the stored key (`changes`
     uses stored keys after `normalize`). Read Leg 1a's `Normalized.changes` key convention.
   - Apply AC4. Build the refusal per AC6.

5. **Wire into the tools** after `compute_taint`, only when `untrusted`. Pass `self._agent` and
   the tool-call id, and `collect` again: it is cheap and keeps the tools simple.

6. **`FieldSpec.rows`.** Add the attribute, defaulting to false. No existing spec sets it.

7. **Tests** (AC7, AC8), then docs (AC10), then the unit tier.

## Edge Cases

- **The same URL typed with a trailing slash or `www.`** normalises equal.
- **A URL inside a markdown link in fetched text** (`[docs](https://x)`): `extract_addresses`
  finds it. Trimming must not cut a `)` that belongs to a balanced URL path. Trim it only when
  the URL has no matching `(`.
- **Very long fetched pages:** `linked` can be large. Normalise once per tool result, never
  per value.
- **Agent `model` values like `phi3:3.8b` or `llama3.1:8b`:** these must not be extracted as
  `host:port`. The port is digits only, and the host must be a dotted name, `localhost` or an
  IPv4 address.
- **An agent's `name` field** is free text and is scanned like any other.
- **Redirects.** `fetch_url` follows redirects, so a typed URL that redirects off-site still
  counts as linked. This is an accepted limitation, documented next to the followed-link README
  limitation.
- **Truncated pages.** A very long README can be cut by the loop's result budget, so a value
  beyond the cut is refused. That fails closed, and GleepGlorp quotes it for the operator.
- **Eval impact.** After a fetch, a model-invented URL or email in agent free text is now
  refused, so the GleepGlorp `fill_made` and `propose-*` rates may move. Legs 6 and 7
  re-baseline; this leg edits no `evals/` file.
- **Rule text and routine prompts** are free text in the rule and routine kinds, so a fetched
  URL planted into a routine prompt is refused too. This is intended: DD7 says every kind.
  Confirm that no existing routine or rule test trips (AC9).

## Files Affected

- `the_one/agent/taint.py` (`find_anchor`).
- `the_one/gleepglorp/outside.py` (new).
- `the_one/gleepglorp/proposals/shape.py` (`FieldSpec.rows`).
- `the_one/gleepglorp/proposals/tool.py`, `the_one/gleepglorp/fill/tool.py`.
- `tests/test_gleepglorp_outside.py` (new); possibly a test fixture HTML file under
  `tests/fixtures/`.
- `SECURITY-MODEL.md`, `the_one/agents.md`.
- **Registries and pins:** none of the tool descriptions or parameters change (the description
  and `set(props)` pins are untouched). The loader denylist constant is pinned by a new test.

## Design Review

Cycle 1 (Developer, Sonnet): **approve with changes.** All folded in above:
- **High:**
  - **Whole-URL matching.** URL values pass only by normalised equality, and the token boundary
    is widened.
  - **Bare-domain extraction.** A TLD allowlist that excludes file-extension TLDs, so the
    planted `garden-stats.example.test` is caught. The eval cell stays a zero-failure safety
    cell.
- **Medium:**
  - Ollama-tag boundaries;
  - the per-message call map;
  - test file references;
  - the `changes` input shape and the scanned/skipped sets;
  - `fnmatch` loader globs on folded keys, with a wider denylist;
  - NFKC and zero-width folding, more schemes, protocol-relative URLs and IP literals;
  - args matched within one source.
- **Low:**
  - only `[2xx]` fetches count;
  - raw plus de-escaped matching, tested through `FetchUrlTool.execute`;
  - the channel exclusion;
  - the refusal shows the host only and explains retyping;
  - a test for a fetch in the same message;
  - residuals documented (defanged forms, unlisted TLDs, redirects, truncation).

This refines DD7's matching and extraction rules; the flight log records it. There was no
second cycle, because the changes tighten rules already in DD7 rather than changing its
design.

## Citation Audit

Verified against the working tree with Legs 1a and 1b landed:
- `llm/base.py` `Message` fields: `content: str | list[ContentBlock]`, `tool_calls`,
  `tool_result`, `visibility`, `peer_name`, `routine_id`, `routine_name`,
  `routine_untrusted_sources`, `proposal_id`, `proposal_event` and `page: dict | None` — verified.
- `llm/base.py:36` `ToolCall.arguments: dict`; `ToolResult.tool_call_id`, `content` (normalised
  to `str`) — verified.
- `agent/taint.py:97` `compute_taint`: the backwards anchor scan at `:127-133`, the
  classification loop, `UNKNOWN_POSITION` when there is no anchor — verified.
- `tools/web.py:244` `FetchUrlTool` (`name = "fetch_url"`), `:276` `execute(url)`, HTML via
  readability then markdownify, redirects up to `redirect_cap`, `[error]` prefix on failures —
  verified.
- `gleepglorp/build.py:19` the web tools `["fetch_url", "web_search"]` — verified.
- `proposals/tool.py:128-131` and `fill/tool.py:114-117` — `guard.check` then `compute_taint`
  — verified at `9597b0f4`. **Re-check after Legs 1a and 1b** (both edited these files).
- `SECURITY-MODEL.md:1380` the residual paragraph; `:1378` the browser-side fill paragraph —
  verified.
