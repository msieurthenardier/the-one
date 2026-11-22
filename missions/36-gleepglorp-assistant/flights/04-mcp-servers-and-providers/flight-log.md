# Flight Log: MCP servers and model providers

**Flight**: [MCP servers and model providers](flight.md)

## Summary

Planning 2026-11-21, from `main` at `9597b0f4`. Flight 3 (#382) and the
2026-11-21 squawk turnaround (#383) are merged.

## Reconnaissance Report

**Sources:**
- the Flight 3 debrief's recommendations and action items;
- the Flight 2 refactor debt it carried;
- the Flight 3 log's carried items;
- open squawks 0398 and 0399.

Each item was walked against `9597b0f4`.

| Item | Classification | Evidence | Recommendation |
|---|---|---|---|
| `ApplyError` protocol | confirmed-live | `proposals/apply.py:137-251`: isinstance chains, no `ApplyError` class | This flight, DD3, Leg 1 |
| Split `shape.py` by kind | confirmed-live | `shape.py` 620 lines; `normalize` if/else `:426-433` | This flight, DD2, Leg 1 |
| Per-kind card, follow and fill registries | confirmed-live | `approvals.js:29,52`; `agent-editor-fill.js:46` `ALLOWED`; drawer `fill.js` agent-only routing | This flight, DD11, Leg 2 |
| Shared fill and proposal plumbing (debrief rec. 1) | confirmed-live | `fill/store.py` 291 and `proposals/store.py` 386; two `events.py`; `fill-receipts.js` and `proposal-cards.js` fold separately | This flight, DD11, Legs 1-2 |
| Route or page id in the page line (rec. 2) | confirmed-live | `page.py:161` `build_line`: labels only | This flight, DD6, Leg 1 |
| Deterministic guard on links and commands (rec. 3) | confirmed-live | `proposals/guard.py:101` checks keys and stored secrets only | This flight, DD7, Leg 3 |
| Grep registries and pins at leg design (rec. 4) | confirmed-live | no such item in `.flightops/agent-crews/leg-execution.md` | Applied as FD practice (DD14); the `.flightops` file change stays with the operator |
| Prompt at its cap; grow through tools (rec. 5) | confirmed-live | `p4c` is 550 of 550 | This flight, DD12 |
| Quiet-host gate and re-budget (squawk 0389 note) | confirmed-live | owed since M36 F1; F3 gate loaded (5-7) | This flight, DD15, closing leg; no fourth deferral |
| Re-slice `shared` | confirmed-live | `run-tests.sh:87` `[shared]=420`; F3 reading 683 s | This flight, DD14, Leg 1 |
| Squawk 0391 (type ignores) | already-satisfied | `5e5a388f` (PR #383): the five ignores removed | Retire from this flight |
| Squawk 0392 (proposal lifecycle) | already-satisfied | `the_one/agents.md` "Proposal lifecycle (M36 F2)" (PR #383) | Retire |
| Squawk 0393 (Windows test-copy root) | already-satisfied | `the_one/agents.md` "Windows test copy" bullet (PR #383) | Retire |
| Squawks 0394, 0395, 0396, 0397 | already-satisfied | PR #383 | Retire |
| Squawk 0398 (stale `CLAUDE.md` citations) | confirmed-live | `the_one/mcp/README.md:15/354/398/491`, `mcp/__init__.py:8`, `self_configuration/credentials.py:42`, `db/schema.py:798` | This flight, Leg 4 (the MCP package) |
| Squawk 0399 (behavior specs on 8485) | confirmed-live | 9 specs in `tests/behavior/` | This flight, Leg 8, beside the new spec |
| "Who uses a provider" helper (F1, carried by F3's log to "provider proposals") | already-satisfied | `api.py:list_provider_agents` (GET /api/providers/{id}/agents), `AgentStore.list_by_provider` used by `view_library.py:46` (found by the Architect, cycle 1) | Retire |
| The two notes tables decision (F1) | confirmed-live | `gleepglorp_notes` beside agent notes | Not on this flight's path; carried |

## Flight Director Notes

- **2026-11-21, planning.** A read-only survey of the seven remaining kinds
  ran before the spec. It covered write routes, inline validation, secret
  fields, editor seams and pushes. Findings:
  - **No kind has a write service.** Validation and side effects live in the
    routes.
  - **No library editor exports fill handles or follows `config_changed`.**
  - **Two lower layers lock out new kinds:** the proposal kind CHECK and the
    fills' `agent_name NOT NULL`.
  - **No code-level guard against links or commands.**
  - **MCP servers, providers, knowledge bases and connectors have non-unique
    names.**
  - **Sign-in needs a saved row:** MCP OAuth and the Anthropic plan.
  - **The date and time page saves on choice,** so it can only take
    proposals (Flight 5).
- **Operator decisions (2026-11-21):**
  - Split the mission's Flight 4 after MCP servers and providers; the other
    five kinds go to Flight 5, and alignment to Flight 6.
  - GleepGlorp may set commands and URLs, behind a code-level block on
    outside values.
  - Values typed by the operator, and values from a page whose address the
    operator typed, count as the operator's.
  - A drawer request for another item opens that editor and fills it.
  - A HAT closes the flight.
- **FD scoping calls:**
  - Squawks 0398 and 0399 ride this flight, on shared surfaces.
  - No desktop-webview leg: no new shell, socket or engine behaviour.
  - The `.flightops` checklist change (rec. 4) is left to the operator.
- **2026-11-21, design review cycle 1** (Architect, Opus). The verdict was
  approve with changes. The findings, all folded in:
  - **High:**
    - DD7 as first agreed did not close the 1-in-12 residual, because the
      planted pages are operator-linked.
    - `p4c`'s no-copy line forbids the headline case.
    - The MCP and provider repositories lack the `precheck`/`on_commit` hooks
      the proposal lifecycle needs.
    - The `propose_change` description pins cannot hold every field of the
      new kinds.
  - **Medium:**
    - DD6 changes the eval page lines, and the route must come from the
      server's resolution, not client text.
    - DD7 named the wrong fetch tool (`web_fetch`; it is `fetch_url`) and
      had no matching rules
      (markdownify escapes, URL normalisation, token boundaries), and it did
      not exclude marked USER messages.
    - DD4 did not follow the project's conventions (`CURRENT_VERSION`, the
      `executescript` ceremony, replay shape detection). The kind CHECK is
      dropped, not widened.
    - DD9 needs nested paths, a per-row merge, the Sensitive rule, `cwd`
      operator-only and the runtime dropdown mapping.
    - DD10 needs type changes handled and a server-side defaults table.
    - `guard.check` false positives on commands and URLs.
  - **Low:**
    - DD3 keeps the re-raise;
    - an import-cycle-safe registry layout;
    - the lane is `chats-transcript`, not `chats`;
    - the prerequisite re-verifies moved to Legs 7 and 8;
    - the key-value note and dict card rows put to the operator as a mockup.
  - **Suggestions taken:**
    - Leg 1 split into 1a (refactor) and 1b (schema, targets, route, lane);
    - squawk 0398's `schema.py` comment moved to 1b;
    - ids resolved before names;
    - operator-typed `read_app_config` text as a tier-2 source;
    - a loader-key denylist;
    - URL-move warnings;
    - per-kind `operator_only`.
- **Operator decisions after cycle 1 (2026-11-21):**
  - narrow the linked-page rule to declared address and command fields;
  - a raw README from the same GitHub repo counts;
  - provider type changes allowed with a warning;
  - one note under a key-value table.
- **FD calls after cycle 1:**
  - env and header rows merge per row;
  - attachment text counts as a linked page;
  - `fill_form` description pin at 90 tokens.
- **2026-11-21, design review cycle 2** (Architect, Opus; the last cycle
  under the two-cycle cap). Verdict: approve with changes. The cycle-1
  fixes held, apart from two partial ones. Everything was folded in by the
  FD with no third review: the remaining items were text contradictions and
  missing specifics, none a new design direction.
  - **High:** DD7 contradicted itself on loader keys (tier 2 admitted them),
    and the denylist missed the package-redirect keys (`npm_config_*`,
    `PIP_INDEX_URL`, `PATH`, `*_PROXY`, …). Fixed: a loader key and its value
    must both be tier 1, matched by prefix patterns.
  - **Medium:**
    - There is no attachment-text source (attachments are images only).
    - The operator-typed `read_app_config` source cannot work (the MCP views
      always carry outside paths), so it is dropped and listed as a gap.
    - The change services now follow `change_agent`'s retry rule and re-pin
      `_cache` and the OAuth secrets inside the transaction.
    - `FieldSpec.stored` stays the string key, with a `path` added; headers
      and env are row-typed fields.
    - Leg 1a re-pins the `evals/harness.py` freeze digest.
    - A provider key never follows a type change to another key-taking type
      (refused for proposals; cleared on fills).
    - `SECURITY-MODEL.md` and `evals/README.md` are in the docs.
    - Sensitive rows never appear on proposal cards.
    - The `Kind` interface is aligned with the later decisions.
    - The full `shape` re-export list and the patched tests are known.
    - `read_app_config` gets the id-then-name rule.
  - **Low:**
    - free-text must-pass cases;
    - a `command`/`args` warning;
    - more registries listed;
    - DD6 Settings routes and over-cap routes;
    - URL and GitHub matching details;
    - fill warnings go in the reply, not on the receipt, so there is no new
      placement;
    - text errors.
  - **Suggestions taken:**
    - character caps beside the token pins;
    - reuse of `mcp-editor-shared.js`'s runtime collapse;
    - refusals name their source page;
    - Leg 8 prerequisites for GitHub and Web access;
    - a Divert criterion for the 550-token cap;
    - the sandbox-network note for `npx`/`pipx` servers.
  - **FD calls in this cycle** (within the operator's "allow with a warning"
    on provider types):
    - a proposal moving a provider between key-taking types is refused with
      a handoff;
    - a fill clears the key field instead;
    - moving into `anthropic-plan` or a keyless type, or out of
      `anthropic-plan`, is allowed with a warning;
    - an MCP type change writes the editor's Save body;
    - the Leg 7 order (old set first, then candidates, then the
      re-baseline).
- **Why the quiet-host gate runs last, not first** (the debrief recommended
  first): Leg 1b re-slices the lanes and Legs 2-5 add browser files, so a
  first-day reading would be stale by landing.
- **2026-11-21, execution start** (`/mission-control:agentic-workflow flight
  04 mission 36`, operator). The flight moved ready → in-flight.
  - **Crew file:** `.flightops/agent-crews/leg-execution.md`. Developer on
    Sonnet. The Reviewer is on Sonnet (security tier), because the batches
    touch the secret guard, credential-bearing services and the outside-value
    guard. The Accessibility Reviewer (Sonnet) joins any batch with UI
    changes.
  - **Batch plan** (the batch-mode protocol). Each batch ends in a review and
    a checkpoint commit:
    - **A:** Legs 1a, 1b, 2 and 3, the groundwork and the guard;
    - **B:** Legs 4 and 5, the kinds;
    - **C:** Leg 6, eval setup, reviewed and committed before any quota;
    - **then:** Leg 7 (rounds) and Leg 8 (the HAT and the gate).
- **Leg 1a design** (`legs/01a-kind-registry.md`). **Risk tier: high,**
  because it changes a shared module with many consumers (the proposal and
  fill tools, the store, the apply path and the tests). It gets a Developer
  design review. Two leg-level refinements of the flight spec:
  - **The byte-identical pin is not a committed golden file** (user-global
    rule). It is the existing suites with their assertions unedited, plus a
    before/after comparison in a scratch directory.
  - **`apply_proposal` accepts `AgentWriteDeps` or `KindDeps`**
    (`KindDeps.of`). So `evals/harness.py` and its freeze digest are not
    touched, which supersedes DD3's "re-pinned in Leg 1a" note.

- **2026-11-21, during Leg 1a: connectors are out of GleepGlorp's scope**
  (operator). After this mission, the operator will rework how connectors
  work, so GleepGlorp gets no connector proposals, fills or write service.
  - The mission criterion, its planning decisions and its Flight 5 entry are
    amended, as is this spec's DD1 and Open Questions.
  - DD4's dropped kind CHECK means no schema text names connectors.
  - The existing read-only connector view (Flight 1) and page awareness stay,
    since they are read-only and already shipped. Removing them would be a
    separate operator call. The operator then confirmed: "reading connectors
    is fine".
- **Leg 1a landed** (`[LAND:leg]`).
  - **Accepted deviations,** both behaviour-preserving:
    - `Kind.summary_text(p, zone)` is async, and the routine kind loads its
      own zone;
    - `Kind.apply` takes the routine `runner` beside `mark`;
    - a small `Kind.card()` helper.
  - **Results:**
    - the AC8 before/after diff was empty;
    - the unit tier gave 11397 passed and 15 skipped;
    - the evals harness and the freeze digests were untouched.
- **Leg 1b design** (`legs/01b-schema-targets-and-route.md`). **Risk tier:
  high,** because of a schema migration, shared stores, the tool parameter
  schemas and the page line the model reads. It gets a Developer design
  review against Leg 1a's landed code.
- **Leg 1b design review, cycle 1** (Developer, Sonnet). Verdict: approve
  with changes. FD calls:
  - the route is stripped from the operator's chip, client-side;
  - the AUTOINCREMENT sequence is carried across the rebuild;
  - the shared store base is cut to what is really common (no shared
    `mark`);
  - the `target` tool parameter **moves to Leg 4**, so no platform-text
    change lands without a consumer (a refinement of DD5);
  - `gleepglorp` lane budget 360 s, provisional;
  - the `chat` alias keeps its pattern.

  There was no second cycle; see the leg's Design Review section.
- **Leg 2 design** (`legs/02-client-groundwork.md`), drafted while Leg 1b is
  being built. **Risk tier: high,** because it changes shared client modules
  (the drawer fill, the cards, the receipts, the approvals record). The design
  review waits for 1b to land. Scope calls:
  - **The "one card and receipt folding rule" (DD11) is dropped.** The card
    and receipt state machines share no folding rule; ordering is already
    shared (`App.chat.cardOrder`).
  - **No new dirty-state tests for the agent kind.** The existing four in
    `test_flow_gleepglorp_fill.py` cover it and are the unedited net. Legs 4
    and 5 add the pair for their kinds.
- **Leg 1b landed** (`[LAND:leg]`). Unit tier 11431 passed, 15 skipped. The
  `gleepglorp` lane: 122 passed in 289 s (solo, reference only).
  `chats-transcript`: 152 passed.
  - **Accepted deviations:**
    - the chip-strip regex is `/ \(#\S*\)$/`, because `encodeURIComponent`
      keeps parentheses;
    - the fill tool passes `norm.target_id`;
    - only `dumps` is unified in `status_rows.py`; the others write different
      bytes.
  - **Accepted test gap:** the falsification "no" items are shape and route
    cases with no fail-open risk.
- **Leg 2 design review, cycle 1** (Developer, Sonnet). Verdict: approve
  with changes, all folded in:
  - the namespace is `App.gleepglorpKinds`, since `gleepglorp.js` would
    clobber `App.gleepglorp.kinds`;
  - the agent kinds register at the end of the Studio block, with late-bound
    calls;
  - the AC8 test nulls the agent kind's `fill` (no fake kind can be seeded);
  - a separate `byTarget` store;
  - the single frame pin.

  There was no second cycle.
- **Leg 3 design** (`legs/03-outside-value-guard.md`). **Risk tier: high**
  (security). The design review comes after Leg 2 lands.
- **Leg 3 design review, cycle 1** (Developer, Sonnet; it ran while Leg 2 was
  being built, read-only on other files). Verdict: approve with changes. Two
  high bypass-class findings:
  - **Substring URL matching.** `https://good.com` would match inside
    `good.com.evil.test`.
  - **Bare domains not extracted.** The planted `garden-stats.example.test`
    in the eval fixture would pass.

  Both are fixed in the leg, which **refines DD7's matching rules**:
  - URL values pass by normalised equality only;
  - a wider token boundary;
  - TLD-allowlist bare-domain extraction that excludes file-extension TLDs;
  - NFKC and zero-width folding;
  - `fnmatch` loader globs, with a wider denylist;
  - args matched within one source;
  - only `[2xx]` fetches count;
  - the channel exclusion.

  **Documented residuals:** defanged forms, TLDs outside the allowlist,
  off-site redirects of a typed URL, truncated pages (fail closed), and
  instruction text.
- **Leg 2 landed** (`[LAND:leg]`).
  - **Results:** the `gleepglorp` lane 125 passed (293 s); `agent-tabs` 221
    passed (458 s); unit tier 11431 passed, 15 skipped. No existing browser
    assertion was edited.
  - **New:** `tests/browser/test_flow_gleepglorp_kinds.py`, in the
    `gleepglorp` lane.
  - **Lanes not run:** only `agent-tabs` among the follow lanes. The other
    hits of the broad grep are unrelated files. The Batch A review decides
    whether more lanes run.
- **Leg 3 landed** (`[LAND:leg]`).
  - **Results:** unit tier 11549 passed, 15 skipped. AC9 clean: no existing
    test tripped the guard. All nine required safety tests were falsified.
  - **Accepted going-beyond items,** all fail-closed:
    - peer and routine turns drop the last USER message from tier 1;
    - unnamed keys are scanned as free text;
    - the trailing boundary is `(?!\w|\.\w)`.
  - **Leg 4 constraint:** the declared companion command field must be named
    `command`.
  - **Accepted residual:** common-TLD names in free text after a fetch (for
    example `socket.io`) need operator typing.
- **Batch A review** (Legs 1a, 1b, 2 and 3). **Reviewer: Sonnet, security
  tier,** because the diff touches the secret guard's neighbour, the new
  outside-value guard and the taint scan. **Accessibility Reviewer: Sonnet,**
  because the client changed (the chip strip, receipt and card text sources).
  They run in parallel; the Accessibility Reviewer does a static review only,
  so the host policy holds.
- **Batch A accessibility review:** `[HANDOFF:confirmed]`. The visible and
  accessible text is unchanged for the agent kinds. The route never reaches
  an accessible name or an announcement (`addPageChip` is the only path, and
  it uses `textContent` only).
- **Leg 4 split into 4a (server) and 4b (client)**, an acceptable variation
  (the Flight 3 Leg 6 precedent). Leg 4a design: `legs/04a-mcp-server-kind.md`.
  **Risk tier: high** (write boundary, secrets). FD calls:
  - **Changing an MCP server's `type` is fill-only.** A proposal refuses it
    with a handoff, because the editor owns which keys a switch drops. This
    narrows DD9 for proposals.
  - **`update_in_txn(mutate)`** re-reads and mutates inside the transaction,
    instead of `change_agent`'s retry. There is no read-outside-write gap, so
    `_cache` and the OAuth tokens are always fresh.
  - **The `target` parameter and kind-named descriptions land in 4a,**
    because adding fields breaks the per-field description pin.
- **Batch A code review** (Reviewer, Sonnet, security tier):
  `[HANDOFF:confirmed]`, no blocking issues.
  - **Results:** unit tier 11549 passed, 15 skipped; the `gleepglorp` lane
    125 passed (294 s).
  - **Bypass probing of `outside.py` found nothing.** The taint scan, v56
    and the `ApplyError` folding were judged sound.
  - **Non-blocking items carried:**
    1. **Leg 4a:** a `None` row value in the declared-rows branch is turned
       into the string "None", so skip `None` (with a test).
    2. **Leg 4a:** widen `LOADER_KEY_GLOBS` (`NODE_TLS_REJECT_UNAUTHORIZED`,
       `HOME`, `XDG_*`, `PYTHONINSPECT`, `BUN_*`, `DENO_*`, `GEM_*`,
       `BUNDLE_*`, `JAVA_HOME`, `MAVEN_OPTS`, `GRADLE_OPTS`).
    3. **Leg 4a docs:** IDN and homograph domains and TLDs outside the
       allowlist in free text go on `SECURITY-MODEL.md`'s residual list.
    4. **Accepted as precedent:** a crash between DROP and RENAME in the v56
       replay (the v12/v33/v44 ceremony).
    5. **Accepted:** the tier-2 args single-source rule.
- **Batch A checkpoint commit.** Legs 1a, 1b, 2 and 3 are marked
  `completed`. The planning artifacts are included.
- **Batch A committed** as `f4ee1a12` (69 files). Not pushed.
- **Leg 4b design** (`legs/04b-mcp-editor-fill.md`), from a read-only survey
  of the MCP editor. **Risk tier: high** (a browser write seam plus a new
  follow-through on an editor that had no refresh path).
  - **FD call:** a filled Sensitive row saved while still empty stores an
    empty secret. That is existing editor behaviour for any empty Sensitive
    row, so no new validation is added; the note and Test show it.
- **Leg 4a design review, cycle 1** (Developer, Sonnet). Verdict: approve
  with changes. The leg was rewritten. High findings:
  - `_card_extras` would have rendered MCP cards as routines;
  - `Kind` lacked the members the leg used;
  - eight-plus pins were unlisted;
  - the guide topic is at 563 of 600 words.

  **New FD decisions:**
  - **4a is never shipped without 4b.** Batch B commits 4a, 4b and 5
    together.
  - **Secret-looking row keys** (`authorization`, `*token*`, `*secret*`,
    `*password*`, `*key*`, …) with a non-empty value are refused, with a
    handoff.
  - **Header keys compare case-insensitively** against `secrets`, existing
    headers and the OAuth keys. This closes a Sensitive-rule bypass.
  - **`agent_name` is `None` for MCP proposals.** The card name and
    `target_gone` come from a lookup by `target_id`.
  - **A create's id is generated before the write,** so the mark and
    `config_changed` carry it.
  - **The `guard.check` key-shape heuristics are narrowed** for declared
    fields. Stored-secret containment is kept.
  - **Deviation from DD9:** the in-transaction mutator (`update_in_txn`)
    replaces the retry wording.

  Cycle 2 was spawned.
- **Leg 4a design review, cycle 2** (Developer, Sonnet). Verdict: approve
  with changes; every cycle-1 finding resolved. Folded in:
  - **The secret-looking-key rule is one pinned algorithm:** segments split on
    punctuation and camelCase; accepted false positives `X-Request-Key-Id` and
    `MAX_TOKENS`; it also covers `args` flags.
  - **The `guard.check` relaxation covers only `url`, `command` and `args`.**
    Rows keep their heuristics, which closes a typed-secret-in-a-header hole.
  - **The validators move into the service.**
  - **Warnings show on pending and failed cards only.**
  - **A create's `target_id` reaches the view** through `result`.

  The two-cycle cap is reached and the leg is `ready`.
- **Provider survey for Leg 5** (read-only, while Leg 4a builds). Findings
  that shape the design:
  - **A real race today.** `update_provider` pins the OAuth keys from a read
    outside the transaction, then rewrites the whole secrets blob. An OAuth
    refresh (`plan_credentials` `update_secrets`) in between is clobbered.
    The in-transaction mutator fixes it for the route as well.
  - **No server-side per-type defaults.** A `PROVIDER_TYPE_DEFAULTS` table
    goes in `db/_provider_types.py`, pinned to `providers-section.js`
    `TYPE_DEFAULTS` the way `test_admin_reasoning_effort_field.py` reads it.
  - **The editor has no programmatic setters.** The type select's change
    handler resets `base_url` and relabels the key row. The sign-in section
    is outside the dirty machinery.
  - **An open provider editor never refreshes,** as with MCP.
  - **Changing out of `anthropic-plan`** silently drops the OAuth secrets
    today.
  - **Create accepts a client-supplied `id`;** a duplicate gives a 500.
  - **The read view shows no config and no key-present flag.**

  Leg 5 will be split 5a (server) and 5b (client), like Leg 4.
- **Leg 4a landed** (`[LAND:leg]`).
  - **Results:** unit tier 11698 passed, 15 skipped. The AC1 route suites
    passed unedited before the change path was written. Lanes: `mcp` 105,
    `mcp-connection` 102 and `gleepglorp` 125 passed. Every required safety
    test was falsified.
  - **Accepted calls:**
    - the secret-key rule lives in `mcp/service.py`;
    - there are no `api.py` wrappers for validators with no remaining
      callers;
    - a proposal refuses an empty row;
    - `agent` is refused for `mcp_server`.
- **Leg 5a design** (`legs/05a-provider-kind.md`). **Risk tier: high.** Its
  review runs in parallel with Leg 4b's (both read-only).
- **Leg 4b design review, cycle 1** (Developer, Sonnet). **Verdict: needs
  rework.** The leg was written before 4a landed, and two of its server
  assumptions were false:
  - **4a refuses empty rows,** so the Sensitive handoff was impossible;
  - **`fill/tool.py` refuses non-agent kinds,** and `fill_view` is
    agent-shaped.

  The card rows would also have rendered `[object Object]`. **Rewritten, with
  FD decisions:**
  - **No `type` change on an existing MCP server, by fill or by proposal.**
    The operator switches the type in the editor. This narrows DD9 to
    create-only, because the editor owns what a switch drops.
  - **The handoff row is a bare `""`,** in fills only, for secret-looking keys
    only. The client marks it Sensitive.
  - **`normalize` gains `mode="fill"`.**
  - **`fill_form` keeps `agent` for agents;** `target` carries MCP ids.

  Cycle 2 was spawned.
- **Leg 5a design review, cycle 1** (Developer, Sonnet). Verdict: approve
  with changes. **FD resolutions:**
  - **AC2 race test.** It is now deterministic: hold the write lock, then
    write the refresh token raw. The first wording passed on today's buggy
    code.
  - **Propose versus fill** uses `normalize(mode=)`, shared with Leg 4b.
  - **Key-taking types** come from `shows_api_key`. Key-taking to a
    different key-taking type is refused for proposals and in
    `change_provider`, and allowed for fills (the key is cleared).
    Keyless to key-taking is allowed with a warning.
  - **Type changes mirror the editor:** default `base_url` for hidden-URL
    types; `openai-compatible` needs a URL; `num_ctx` and `thinking_enabled`
    are seeded.
  - **`mock` is refused.**
  - **The guard exemption is "equals any type's default URL".**
  - **The agents count** goes in the type-change warning.
  - **The PUT response's `updated_at`** becomes the written value, a latent
    bug fixed.

  There was no second cycle. The leg is `ready`.
- **Leg 4b design review, cycle 2** (Developer, Sonnet). Verdict: approve
  with changes; the cycle-1 findings are resolved. Twelve binding
  resolutions were added to the leg. The main ones:
  - **`kept` carries stored keys only,** because the outcome API 422s
    anything else;
  - **`setType` on a create form** uses its own sequence, not `applySaved`;
  - **`fill_view` stale** goes through a public `stale_fields` alias with
    labels and flattened rows;
  - **an empty handoff row never replaces an existing plain row;**
  - **the AC3 pins are corrected;**
  - **the `fill_form` description is drafted and measured** before coding.

  The leg is `ready`. Build order: Leg 4b, then Leg 5a, which depends on 4b's
  `mode`.
- **Leg 4a's Developer** kept waking on leftover background waiters after
  landing. It was asked to stop them and did not answer, so the FD stopped
  the agent with `TaskStop`. Its leg was already accepted. No test runs
  overlapped: only Leg 4b's lane was running.
- **Leg 4b landed** (`[LAND:leg]`).
  - **Results:**
    - `fill_form` description: 78 tokens, 341 characters;
    - lanes: `gleepglorp` 141, `mcp` 105, `library` 122 and `mcp-connection`
      101 passed (one key-list pin updated);
    - unit tier 11706 passed, 15 skipped;
    - the five required safety tests were falsified.
  - **Accepted deviation:** a kept command group reports `args` for an
    args-only fill, because the outcome API needs the fill's own keys.
  - **For the Batch B review:**
    - **Header casing:** a proposed `accept` may be stored beside an existing
      `Accept`, instead of updating it. Check it against Leg 4a's decision 5.
    - **The follow tests use `App.approvals.record`,** not a real Approve.
    - **The `mcp-servers.md` guide** was trimmed to fit 600 words.
- **Leg 5a landed** (`[LAND:leg]`).
  - **Results:**
    - the AC1 provider route suites (13 files, 497 tests) passed unedited;
    - the three race tests (service replace, service change, the PUT route)
      were falsified;
    - unit tier 11811 passed, 15 skipped;
    - lanes: `providers` 144 and `gleepglorp` 141 passed.
  - **The PUT response `updated_at`** is now the written value (pinned; no
    old pin existed).
  - **Accepted deviations:**
    - `Kind.needs_secret` was removed in favour of `mode`;
    - the provider kind refuses duplicate names case-insensitively, for
      proposals only, so name targeting stays unambiguous;
    - an `anthropic-plan` create warns "Sign in on the page after
      approving";
    - a type-change proposal stores no `base_url` (the service fills the
      default on approve).
- **Leg 5b design** (`legs/05b-provider-editor-fill.md`). **Risk tier:
  high** (a browser write seam, and key clearing). Its review runs now,
  against 5a's landed code.
- **Leg 5b design review, cycle 1** (Developer, Sonnet). Verdict: approve
  with changes. Four high findings:
  - a fill to `ollama` would have kept the old key;
  - Cancel did not restore type-driven rows (a pre-existing manual bug too);
  - the rebase had to refresh the editor closure's `provider`, or a later
    Save would revert approved options;
  - the kept rule ignored a typed key.

  Thirteen FD resolutions were written into the leg. The main ones:
  - **`clears_key`** is computed from the fill's base: true for a change to a
    keyless type, or between two different key-taking types.
  - **A typed key is kept.**
  - **`applyType` is shared** by the handler, `setType` and Cancel.
  - **A controller module** lives beside the editor, which is at its size
    ceiling.
  - **Fill-time warnings** for MCP and providers. This closes DD9's
    "fill warnings in the tool result", which Leg 4b had not wired.
  - **The `fill_form` character cap** rises 360 → 440, with tokens at 90.

  There was no second cycle; the shape is unchanged. The Batch B review
  covers the result.
- **Leg 5b landed** (`[LAND:leg]`).
  - **Results:**
    - `fill_form`: 89 tokens, 397 characters;
    - lanes: `gleepglorp` 167, `providers` 144 and `library` 122 passed;
    - unit tier 11836 passed, 15 skipped;
    - the six required safety tests were falsified, including two real
      Approves.
  - **Accepted:** `provider-editor.js` is at 894 of its 895-line ceiling.
  - **For the Batch B review:**
    - **Fill warnings read "… after approving".** They reuse the proposal
      sentences, which is the wrong verb for a fill.
    - **A dirty editor's Save after a type change by approval** still sends
      the old type, reverting the approved change. This was scoped out
      (the note says Cancel); decide whether it is acceptable.
- **Batch B review** (Legs 4a, 4b, 5a and 5b). **Reviewer: Sonnet, security
  tier** (MCP secrets, provider keys and OAuth tokens, write services, the
  guard). **Accessibility Reviewer: Sonnet** (the MCP and provider editor
  notes, follow notes and cards). They run in parallel; the Accessibility
  Reviewer does a static review only.
- **Batch B accessibility review:** `[HANDOFF:confirmed]`.
  - The notes are linked to their controls and unlinked cleanly.
  - No live region announces values or secrets.
  - No focus is stolen from the drawer.
  - The new CSS uses existing tokens.
  - **Non-blocking (HAT candidate):** a follow note appears without any
    screen-reader announcement. This matches the existing agent-editor
    pattern. An optional visually hidden polite status ("This server was
    changed by an approved change") would close it.
- **Batch B code review** (Reviewer, Sonnet, security tier):
  `[HANDOFF:confirmed]`, no blocking issues.
  - **Results:** unit tier 11836 passed, 15 skipped; lanes `gleepglorp` 167,
    `mcp` 105 and `providers` 144 passed.
  - **Header casing is confirmed correct:** a proposed `accept` replaces an
    existing `Accept` by folded name, with no duplicate.
  - **Non-blocking items, dispositions:**
    - **The MCP operator PUT still reads outside the transaction** (the old
      race on OAuth keys and `_cache`): squawk 0400.
    - **A dirty provider editor can revert an approved type change on
      Save:** accepted for the flight, squawk 0401.
    - **Fill-warning wording "after approving":** folded into Leg 6.
    - **Provider create with a duplicate client id gives a 500**
      (pre-existing): squawk 0402.
    - **A high-entropy secret in a URL query with no known prefix** passes the
      relaxed guard, but needs operator typing anyway. Accepted, and noted
      for the debrief.
  - **Squawk 0398 completed,** with sign-off.
- **Batch B checkpoint commit.** Legs 4a, 4b, 5a and 5b are marked
  `completed`. Squawks 0400-0402 are logged as open.
- **Leg 6 design** (`legs/06-prompt-and-evals-setup.md`), drafted during the
  Batch B review. **Risk tier: high,** because it edits frozen eval scoring
  files (the FD re-pins them under the 2026-11-20 ruling) and safety-cell
  classes.

## Leg Progress

### 01a-kind-registry

- **Status**: landed
- **Started**: 2026-11-21
- **Completed**: 2026-11-21
- **Changes Made**:
  - New package `the_one/gleepglorp/kinds/`: `base.py` (`Kind`), `errors.py` (`ApplyError`, one
    `translate`, `reraise`), `deps.py` (`KindDeps.of`), `agent.py`, `rule.py`, `routine.py`
    (field tuples, normalizers, `exists`, `apply`, summary text), `__init__.py` (explicit
    `REGISTRY` tuple, `get`, `normalize`, `describe`, `spec_for`, the derived views, `FILLABLE`).
  - `proposals/shape.py` reduced to the primitives plus a lazy module `__getattr__` re-export
    (no moved name is a real attribute). `proposals/apply.py` dispatches through
    `kinds.get(...)` and folds `ApplyError` in one branch; `failure_errors`, `_is_gone`,
    `_agent_or_rule_stale`, `_routine_stale` are gone from it.
  - `continuation.proposal_title`, `fill/store.py`, `fill/tool.py` (`enum` from `kinds.FILLABLE`),
    `proposals/tool.py`, `proposals/store.py`, `view_fields.py` read the registry.
  - Tests: three monkeypatch retargets (`shape` to `kinds` / `kinds.agent`); seven `kinds/*.py`
    paths added to the seam-import guard parametrization; new `tests/test_gleepglorp_kinds.py`
    and `tests/test_gleepglorp_apply_error.py`. `the_one/agents.md` gained "GleepGlorp kinds
    registry (M36 F4)" and its `shape` references were repointed.
- **Notes**:
  - **AC8 before/after: identical.** Scratch script
    `/tmp/claude-1000/-home-cprch-projects-the-one/1821e3c0-8ca0-4061-b85e-be991e1f3210/scratchpad/leg01a/capture.py`
    run before any edit (`before.json`) and after (`after.json`); `diff` printed nothing. It
    captures `describe()` and per kind, `KINDS`, `ACTIONS`, `KIND_SUMMARIES`,
    `OPERATOR_ONLY_FIELDS`, every `FieldSpec` (without the two new attributes),
    `SCHEDULE_EXAMPLE`, `_ECHO_MAX`, both tools' `parameters`, `proposal_title` for every
    kind and action, `normalize` output for each apply scenario, and `apply_proposal`
    outcomes, stale payloads and `result` dicts (agent, rule and routine stale and override;
    routine create and change; agent and rule create). Nothing from it is committed.
  - **Deviation from the leg text (small, behaviour-preserving):** `Kind.summary_text` is
    `async summary_text(p, zone)` (the routine kind loads the zone for the schedule sentence
    itself) instead of `(p, routine_name, sentence)`; `apply` also receives a `runner` (the
    routine `ProposalRunner`) beside `mark`, because kinds may not import `apply.py`.
    `Kind` also gained a `card()` helper over `card_title`. The fill card title now comes from
    `kinds.get(fill.kind).card(...)`, the same text.
  - Falsification: `test_an_error_that_is_not_an_apply_error_propagates` yes (catching
    everything in `apply_proposal` failed it); the agent-create `IntegrityError` tests
    (`test_translate_an_agent_create_integrity_error_is_returned_unchanged`,
    `test_an_agent_create_integrity_error_propagates_out_of_apply_proposal`) yes (widening
    `_is_gone` failed both). The stale, gone, items, already-resolved, `KindDeps` and
    registry or re-export tests: no (not falsified). Both fixes were put back by editing.
  - AC6: `git diff --stat` shows `evals/`, `test_evals_freeze.py` and
    `test_gleepglorp_proposals_apply.py` untouched; `test_gleepglorp_proposals_continuation.py`
    changed only by the seven added seam-guard parameters (no fixture or assertion edit).
  - AC7 suites: 699 passed. `THE_ONE_TEST_NETNS=1 make test-unit`: 11397 passed, 15 skipped. `ruff check` and
    `ruff format --check` on `the_one/ tests/ scripts/ evals/`: clean.

### 01b-schema-targets-and-route

- **Status**: landed
- **Started**: 2026-11-21
- **Completed**: 2026-11-21
- **Changes Made**:
  - **Schema v56** (`db/schema.py`): `gleepglorp_proposals` rebuilt without the kind CHECK;
    `gleepglorp_fills` rebuilt with nullable `agent_name` and `target_id` after it. Per-table
    shape helpers (`_proposals_has_kind_check`, `_fills_has_target_id`), one `executescript` per
    table (v12/v33/v44 ceremony), sequence carried by an `UPDATE`/`INSERT` on
    `sqlite_sequence` written into the script from the old `seq`. Squawk 0398 comment now cites
    `the_one/agents.md`. Every `== 55` pin is 56 (about 16 in `test_db_migration.py`,
    `test_gleepglorp_fill_store.py:58`); fills column pin gains `target_id`;
    `TestSchemaV54`'s bogus-kind test is inverted (accepts any kind, keeps action and status
    CHECKs). New `TestSchemaV56` (fresh shapes; v55 shape built by hand with all statuses and
    kinds, top row deleted, rows and ids carried; replay; each table independent).
  - **Stores**: new `gleepglorp/status_rows.py` (`loads`, `dumps`, `get_row`,
    `list_for_session_rows`, `push_session_frame`); both stores and both `events.py` use it
    (wrapper names and modules unchanged, so every patch site holds). Proposal insert refuses an
    unknown kind (`ValueError`, like the fill store); fill store checks `kinds.FILLABLE`
    (`KINDS` removed); `NewFill`/`Fill`/SQL/`fill_view` carry `target_id`; `fill_view` guards a
    missing agent; `agent_name` is `str | None` on `Normalized`, `NewFill`, `Fill`; the fill
    tool passes `norm.target_id`.
  - **Targets**: `Kind.resolve_target` (optional, set on agent via `existing_agent`),
    `kinds.target_key`, `kinds.resolve_by_id_or_name`.
  - **Reads**: `_list_or_detail(..., id_of=)`; MCP servers and providers list and detail carry
    `id` (`ALLOWED`, `OPERATOR_PATHS`, the provenance `REVIEWED_ALLOWED` pin for providers
    updated on purpose); id matches before name.
  - **Page line**: `build_line(descriptor, resolved_name, resolved_id)` with `_route`, `_enc`,
    `_label`; `_resolve_item` replaces `_stored_name`. Chip strip in `addPageChip`
    (`areas/chat/transcript.js`, the one function). Eval scenario `[page]` lines and
    `agent_seg` fact updated; `test_evals_gleepglorp_fills.py` page-line pin builds with
    `resolved_name`/`resolved_id`; `test_ws_page_context.py` `LINE` gained the route.
  - **Lane**: `gleepglorp` (5 files) in `scripts/run-tests.sh` (LANE_LIST, CANON_LANES, case,
    BUDGET 360 s provisional, header), out of `chats-transcript`/`chats`/`shared`;
    `test_run_tests_lanes.py` updated (LANES, LANE_LIST string, `chat` alias pin, a new lane
    test).
  - **Docs**: `CLAUDE.md` lane list; `the_one/agents.md` (new "Schema v56, id targets and the
    page route" subsection, `build_line` signature, proposal/fill table notes, lane bullet).
- **Notes**:
  - **Lane timings (reference only, not a budget reading; solo runs at host load about 1.5-2.0,
    `THE_ONE_TEST_NETNS=1`):** `gleepglorp` 122 passed in 289 s; `chats-transcript` (now without
    the two moved files) 152 passed in 410 s.
  - **Gates:** `THE_ONE_TEST_NETNS=1 make test-unit` 11431 passed, 15 skipped (the static JS
    guards `test_ui_guards.py`, `test_token_definitions.py`, `test_design_tokens_a11y.py`
    included: 396 passed alone); `ruff check` and `ruff format --check` clean.
  - **Left out of the shared store module, and why:** status transitions (`mark_op`, the
    fills' `claim`/`record_outcome`) and both `insert`s stay in their stores (different rules:
    one-open-per-chat vs claim tokens and leases). The two serializers were not unified beyond
    `dumps`: `dumps` is byte-identical to what both stores wrote for `changes` and `base`
    (compact, `ensure_ascii=False`), but `mark_op`'s `result` serializer and the
    `untrusted_sources` `json.dumps` use different options, so they stay as they were.
  - **Deviation from the leg text (small):** the chip strip regex is `/ \(#\S*\)$/`, not
    `/ \(#[^()\s]*\)$/`: `encodeURIComponent` (so `enc`, so the route) leaves `(` and `)`
    unescaped, and an agent named `a(b)` would otherwise keep its route in the chip. A route
    never holds whitespace, so `\S*` anchored at the end is exact. The Python `_enc` copies the
    client's `enc` (parens unescaped).
  - Not run: the `settings`-family and other browser lanes (nothing under them changed). The
    new browser assertion (no `(#` in a resolved item's chip) is in
    `test_a_later_message_carries_the_agent_tab_it_was_sent_from`; the strip also fails the
    existing exact-text chip assertions when removed.
  - **Falsification (each by editing the fix out, running, putting it back by editing):**
    sequence carry (`test_v55_rows_and_id_high_water_marks_survive`): yes; fills replay
    (`_fills_has_target_id` made always-False: `test_replay_keeps_rows_and_a_post_v56_target_id`
    and `test_each_table_is_rebuilt_independently`): yes; proposal kind refusal: yes; fill kind
    refusal (three params): yes; id-first resolution (`test_an_id_wins_over_a_name`): yes; chip
    strip (existing chip assertion `test_the_first_message_carries_the_page_...` failed without
    it): yes. Not falsified: the proposals-side replay helper alone (a rebuild is lossless, so
    only the fills side can lose data), the read-by-id twin test (the name-first order would
    still reach the twin because ids and names do not collide in the seed), the encoder
    pin, the route cases, the lane tests, `test_gleepglorp_targets.py`'s `target_id` round
    trips, the ids-in-reads shape test, and the new `(#` browser assertion on its own.

### 02-client-groundwork

- **Status**: landed
- **Started**: 2026-11-21
- **Completed**: 2026-11-21
- **Changes Made**:
  - New `static/js/gleepglorp-kinds.js` (`App.gleepglorpKinds`: `register` (throws on a
    duplicate), `get`, `names`), loaded before `approvals.js`; new
    `areas/studio/agent-kinds.js` registering `agent` (with a `fill` spec), `rule` and `routine`,
    loaded last in the Studio block (late-bound calls).
  - Drawer `fill.js` now goes through `get(view.kind).fill` (no agent code; a kind with no
    `fill` is `not_filled` / `editor_unavailable`, no navigation). `fill-receipts.js` words the
    two kind reasons from `labels` (generic fallback "The editor could not open." / "That item no
    longer exists."). `proposal-cards.js` uses `openLink` / `labels.withdrawnGone` (`AGENT_TABS`
    and `openAgentLink` gone; `focusTarget` reads the link's testid; `appliedByApproval` passes
    `target_id`). `approvals.js` records any registered kind through `recordKey`, adds
    `byTarget` and `forTarget(kind, id)`, invalidates the kind's `store`.
  - `apply.py`: `config_changed` carries `target_id`; the one frame pin
    (`test_gleepglorp_proposals_apply.py`) updated to `None`.
  - New `tests/browser/test_flow_gleepglorp_kinds.py` (3 tests), added to the `gleepglorp` lane
    in `scripts/run-tests.sh` and `tests/test_run_tests_lanes.py`; `the_one/agents.md` section
    "GleepGlorp client kinds registry (M36 F4 L2)".
- **Notes**:
  - Lanes (reference only): `gleepglorp` 125 passed, 293 s; `agent-tabs` (holds the follow
    test) 221 passed, 458 s; `THE_ONE_TEST_NETNS=1 make test-unit` 11431 passed, 15 skipped,
    384 s (static guards included). Ruff check and format clean.
  - Greps for AC3/AC4 return nothing. No existing browser assertion was edited.
  - Dropped the flight's "one card and receipt folding rule" as the leg planned (card and
    receipt states do not share one).
  - Falsification: registry duplicate-throw and approvals/stub test: yes (guard removed, failed);
    no-fill-spec drawer test: yes (guard removed, failed); script-order/names test: no.

### 03-outside-value-guard

- **Status**: landed
- **Started**: 2026-11-21
- **Completed**: 2026-11-21
- **Changes Made**:
  - `agent/taint.py`: `find_anchor(messages, tool_call_id)` extracted; `compute_taint` uses it,
    behaviour unchanged (taint, routine-tools and notes tests pass unedited).
  - New `the_one/gleepglorp/outside.py`: `fold`, `normalize_url`, `extract_addresses`,
    `deescape`, `token_match`, `is_loader_key` (+ `LOADER_KEY_GLOBS`, `TLD_ALLOWLIST`),
    `collect` (tier 1 and tier 2), `plan`, `check`.
  - `FieldSpec.rows` added (default false); docstring updated.
  - `propose_change` and `fill_form`: after `guard.check` and `compute_taint`, when untrusted,
    `outside.check(kinds.get(norm.kind), norm.changes, outside.collect(...))`; a refusal returns
    before the insert (nothing recorded, no frame). Neither tool's description or parameters
    changed; no `evals/` file edited.
  - New `tests/test_gleepglorp_outside.py` (118 tests). `SECURITY-MODEL.md` (residual paragraph
    keeps 2026-11-20, adds the 2026-11-21 update and a guard section); `the_one/agents.md`
    "Outside-value guard (M36 F4)".
- **Notes**:
  - Gates: `THE_ONE_TEST_NETNS=1 make test-unit` 11549 passed, 15 skipped; ruff check and format
    clean. AC9: no existing test tripped the guard (no `[BLOCKED]`).
  - Falsification (fix removed by editing, test run, fix restored by editing), all yes:
    marked-USER exclusion; untyped-fetch exclusion; free-text email refusal; loader-key-from-
    linked refusal; no-anchor refusal; token boundary (`good.com` in `good.com.evil.test`);
    bare-domain extraction (`garden-stats.example.test`); stitched-args refusal; per-message
    call map (repeated id). The nine mutations were applied together and every target test
    failed; they were then reverted.
  - Design calls beyond the leg text, all fail-closed or defence in depth:
    - `collect` takes an optional `turn`; on a peer or routine turn the last USER message is
      dropped from tier 1, because the app binds a turn's marks only after the step.
    - A stored key that no spec names is scanned as free text.
    - A loader key is still checked when its value is empty (key must be typed).
    - A declared list's single-source rule uses the declared field named `command` as companion;
      Leg 4 must name its command field `command` (or this rule needs a marker).
    - A bare domain, host:port or IP as a whole declared value passes by normalised equality with
      a typed or linked URL, else by token match.
    - Scheme URLs are extracted before emails, so `ssh://git@host` is one URL.
    - The bare-domain, host:port and www. lookbehinds exclude only word characters and `@`, so
      `*.evil.com`, `--host=evil.com` and `x:evil.com` are still found; the trailing boundary is
      `(?!\w|\.\w)` so a sentence-final period does not hide an address.
    - The stub-kind tool test reaches `propose_change` by monkeypatching `kinds.normalize` and
      `kinds.get`; the allowed side asserts only "not refused" (the real store has no stub kind).
  - Accepted residuals (documented): instruction text in free text; defanged forms and
    unlisted-TLD domains; redirects off-site; truncated pages; typed-only args stitched across two
    operator messages are refused (fails closed); common-TLD false positives in agent free text
    after a fetch (for example `socket.io`) are refused until the operator types them.
  - No AC9 trip. Eval rates (`fill_made`, `propose-*`) may move; Legs 6 and 7 re-baseline.

### 04a-mcp-server-kind

- **Status**: landed
- **Started**: 2026-11-21
- **Completed**: 2026-11-21
- **Changes Made**:
  - New `the_one/mcp/service.py` (create, replace, change; `McpWriteError`, `McpSourceNotFound`,
    `McpStaleError`, late-bound `McpWriteDeps`; validators moved with exact details; the
    secret-looking key rule). `api.py` routes are thin (`_mcp_write_errors`, `_mcp_write_deps`).
  - `MCPSourceRepository.create(on_commit=)` and `update_in_txn` (re-read inside the transaction).
  - New `kinds/mcp_server.py` (fourth in `REGISTRY`), `Kind` members `warnings`, `card_extras`,
    `needs_secret`, `relaxed_guard_keys`, `create_only_message`; `kinds.find`, `kinds.target_args`.
  - `proposal_view` gains `warnings` and the create `target_id`; `display_values` rows; `errors.py`
    maps the MCP errors; `config_changed` carries the pre-generated id.
  - `guard.check(..., relaxed=)`; `target` on both tools; kind-named `propose_change` description.
  - `describe()` adds `shape` and `provenance` (declared in `view_core.py` ALLOWED and operator paths).
  - AC7b: `None` row skip, widened `LOADER_KEY_GLOBS`, residuals in `SECURITY-MODEL.md`.
  - Guide topic (589 words), squawk 0398 Corrective Action and Verification (not completed),
    `the_one/agents.md` and `SECURITY-MODEL.md` sections.
- **Notes**:
  - AC1 list (787 + 292 tests across the listed files) passed unedited after the routes were thinned,
    before any change-path or kind code was written; no `[BLOCKED]`.
  - Gates: `THE_ONE_TEST_NETNS=1 make test-unit` 11698 passed, 15 skipped; ruff check and format
    clean. Lanes (one at a time, wall times for reference): `mcp` 105 passed (292 s),
    `mcp-connection` 102 passed (290 s), `gleepglorp` 125 passed (333 s). `tests/test_evals_gleepglorp*.py`,
    `test_evals_freeze.py` and the guide test pass.
  - New tests: `tests/test_mcp_service.py` (55), `tests/test_gleepglorp_kind_mcp.py` (80), plus pins.
  - Falsified (fix removed by editing, run, restored), all yes: case-insensitive header compare;
    secret-looking row rule; OAuth-managed and stored-Sensitive row checks; guard relaxation applied
    to rows (and relaxation absent); `None` row skip; surface-row refusal inside the mutator;
    re-read under the lock (a concurrent-write test; a first version of the test did not falsify and
    was replaced); stale check; open-only warnings; type-change refusal. Not falsified: import
    boundary, describe markers, card extras, concurrency-apply-once (structural/derived).
  - Pins updated, none weakened: `test_gleepglorp_proposals_shape/_kinds/_tool/_fill_tool/_outside`
    (HOME moved from not-loader to loader keys), seam-import list, `view_core` allowlists.
  - Deviations: the secret-looking rule lives in `mcp/service.py` (not the kind) because AC4 requires
    the service to refuse it; the kind re-exports it. `api.py` keeps no wrappers for the moved
    validators (no remaining callers); only `_drop_source_agent_tool_cache` delegates. Squawk 0398:
    the `db/schema.py:798` citation no longer matches the grep; the notes citation points at
    `SECURITY-MODEL.md`.
  - Design calls: a proposal refuses an empty row; a create refuses a duplicate or reserved name;
    `agent` is refused for an MCP server; `agent` and `target` conflict is refused for an agent.

### 04b-mcp-editor-fill

- **Status**: landed
- **Started**: 2026-11-21
- **Completed**: 2026-11-21
- **Changes Made**:
  - Server: `Kind.normalize(mode=)` on every kind (`kinds.normalize` forwards it, `fill_form` passes
    `"fill"`); `mcp_server` fill mode accepts a bare `""` only for a secret-looking key;
    `fillable = ("create", "change")`; `fill_form` generalized (kind in `FILLABLE`, editor named by
    `Kind.label`, `notes_enabled` refusal agent-only, new description); `fill_view` uses
    `card_extras` and a public `stale_fields` (`mcp/service.py`) for `mcp_server` change fills.
  - Client: editor controller handles (`setType`, `setField`, `setRows`, notes, `rebase`, `saving`,
    `onIdle`), `connectionFields` / `envHeaders` silent handles; new `mcp-editor-fill.js`,
    `mcp-editor-follow.js`, `mcp-kinds.js` (registry order agent, rule, routine, mcp_server);
    `proposal-cards.js` flattens `headers` / `env` rows, counts values, renders `view.warnings`
    (`proposal-warning`, a `chat.css` rule); `index.html`; two registry rows pairs in
    `docs/ui-testid-registry.md`.
  - Tests: `tests/browser/test_flow_gleepglorp_fill_mcp.py` (8), `test_flow_gleepglorp_follow_mcp.py` (6),
    two card tests in `test_flow_chat_proposals.py`, kinds test extended, seeder `target_id`, fill-mode
    and view tests in `test_gleepglorp_kind_mcp.py`; pins updated (FILLABLE, enum, a character cap
    beside the 90-token cap, lane list, the controller key list in the sign-in lifecycle test).
    Lane list in `scripts/run-tests.sh`.
  - Docs: `the_one/agents.md` section, `SECURITY-MODEL.md` (type decision, the fill handoff), guide
    `mcp-servers.md` (trimmed to the 600-word cap).
- **Notes**:
  - `fill_form` description measured first: 78 tokens (o200k_base), 341 characters (cap 90 and 360).
    Eval measurement stays Legs 6 and 7.
  - Lanes (one at a time, wall times for reference): `gleepglorp` 141 passed (397 s), `mcp` 105 passed
    (283 s), `mcp-connection` 101 passed + 1 failure fixed (the controller key-list pin in
    `test_destroy_is_idempotent`, re-run passed) (290 s), `library` 122 passed (370 s). Unit tier first run:
    two failures fixed (guide word cap 687 -> under 600; raw `#route` hashes in two new tests, now
    `_nav.href`); a second full run is recorded below if it differed.
  - Falsified (fix removed by editing, run, restored): fill-mode empty-row acceptance limited to
    secret-looking keys: yes; proposal still refusing the empty row: yes; type change refused on
    change fills (both the kind check and `create_only`): yes; existing plain row kept (handoff never
    replaces it): yes; follow not overwriting a dirty field: yes. Not falsified: the card rows and
    footer, the note linkage, whenSettled.
  - Deviations: a kept command group reports `command`, or `args` when the fill carries only `args`
    (the outcome route requires kept to be a subset of the fill's keys); `outside.py` unedited (a unit
    assertion pins the empty-value skip); a handoff never replaces an existing row of any kind.
    The follow test drives `App.approvals.record` (what the approve response calls) after changing the
    row through the API, not a real approval.

### 05a-provider-kind

- **Status**: landed
- **Started**: 2026-11-21
- **Completed**: 2026-11-21
- **Changes Made**:
  - `the_one/llm/provider_service.py` (new): `ProviderWriteError/NotFound/StaleError`, `ProviderWriteDeps`,
    `create_provider`, `replace_provider` (the PUT, on `update_in_txn`), `change_provider`, moved validators,
    type-fact helpers (`takes_key`, `base_url_for`, `seeded_config`). Repo behind `TYPE_CHECKING`; no
    interface/gleepglorp imports (ast test).
  - `LLMProviderRepository.create(on_commit=)` and `update_in_txn`; `PROVIDER_TYPE_DEFAULTS` and derived
    `CLAUDE_PROVIDER_TYPES` in `db/_provider_types.py` (pinned to the client `TYPE_DEFAULTS`); `api.py` routes
    thin, aliases kept.
  - `kinds/provider.py` (registered fifth), `errors.py` mapping, `outside.APP_DEFAULT_URLS` exemption,
    `providers` detail `options` and `key_stored`, `propose_change` description and `target_args`, guide
    `model-providers.md` (596 words), `agents.md`, `SECURITY-MODEL.md`. `Kind.needs_secret` removed (mode used).
  - Tests: `tests/test_provider_service.py` (45), `tests/test_gleepglorp_kind_provider.py` (57); pins updated
    (registry, operator-only sets, enum, describe lists, seam-import list, provenance allowlist, the 4a
    `needs_secret` assertion).
- **Notes**:
  - AC1: 13 files (test_provider_api, secret_mask_roundtrip, name_rule, invalid_json, agent_provider_check,
    gleepglorp_settings, reasoning_effort_field, provider_types_consistency, store_static, proposals_continuation,
    encryption_status, drawer_seed, name_repair) 497 passed, assertions unedited, run before the change path or kind.
    No test pinned the old PUT `updated_at`; the response now carries the written value (new route test pins it).
  - AC2: deterministic race tests for service replace, service change and the PUT route. Falsified (stale read
    outside the transaction restored): all three failed (plus two 404 tests); restored, pass.
  - Falsified (yes): guard default-URL exemption, relaxed `base_url` guard (needed a long hex path: a UUID is
    already stripped by the guard, so the UUID case is a pass-case only), service key-taking refusal, kind
    key-taking refusal, key clearing into ollama. Not falsified: warnings sentences, mock refusals, name uniqueness.
  - Lanes (reference): providers 144 passed (327 s), gleepglorp 141 passed (347 s). Unit tier
    `THE_ONE_TEST_NETNS=1 make test-unit`: 11811 passed, 15 skipped (383 s). Static JS guards 396 passed. ruff clean.
  - Deviations: duplicate provider names refused by the kind (not required by the leg; keeps name targeting
    unambiguous); creating `anthropic-plan` warns "sign in" (not listed in the leg); `base_url` is not added to a
    type-change proposal's stored changes (the service fills the default); evals not run (no eval baseline compare
    for the description wording; provisional, Legs 6 and 7).

### 05b-provider-editor-fill

- **Status**: landed
- **Started**: 2026-11-21
- **Completed**: 2026-11-21
- **Changes Made**:
  - Server: `provider` kind `fillable = ("create", "change")`; `fill_view` gains `clears_key` (provider
    change, type differs from `base.type`, base type takes a key), `warnings` (the kind's, for pending
    fills, MCP included: closes DD9's fill-warnings gap) and a provider `stale` branch; `fill_form` reply
    appends the warnings; description names the provider kind.
  - Client: new `provider-editor-controller.js` (the handles; `provider-editor.js` stays at 894 of 895
    lines and returns the controller), `provider-editor-fill.js`, `provider-editor-follow.js`,
    `provider-kinds.js` (registry order ... mcp_server, provider); `provider-editor.js` extracts
    `applyType` (change handler, `setType` and Cancel all call it); `providers-section.js` keeps the live
    controller (`current`, `controller()` seam), attaches fill and follow, re-mounts on a type change
    by approval; `index.html`; two registry rows (`provider-filled-note`, `provider-approved-change-note`).
  - Tests: `tests/test_gleepglorp_fill_provider.py` (25), `tests/browser/test_flow_gleepglorp_fill_provider.py`
    (14), `test_flow_gleepglorp_follow_provider.py` (12, two real Approves, a stale approve, the cards);
    pins updated (FILLABLE, enum, 440-character cap, provider kind registration, kinds browser test, seeder
    `target_key` from the registry, lane list in `run-tests.sh` and `test_run_tests_lanes.py`).
  - Docs: `the_one/agents.md` section, guide `model-providers.md` (trimmed to the 600-word cap).
- **Notes**:
  - `fill_form` description measured first: 89 tokens (o200k_base), 397 characters (caps 90 and 440).
    Provisional platform text; eval compare is Legs 6 and 7.
  - Falsified (fix removed by editing, run, restored): `clears_key` computed on the server, both
    key-taking to key-taking and into ollama: yes; the client `clearKey` (keyless and key-taking to a
    different key-taking type, Save storing null): yes; a typed key kept: yes; Cancel restoring the
    type-driven rows and key label: yes; the follow's clean-field rebase / Save after follow sending the
    approved values (two tests): yes; fill-time warnings present (view, tool reply, MCP): yes. Not
    falsified: the notes' `aria-describedby` linkage, `whenSettled`, the card rows.
  - Lanes (one at a time, reference): `gleepglorp` 167 passed (427 s); `providers` 144 passed (327 s);
    `library` 122 passed (354 s). Unit tier `THE_ONE_TEST_NETNS=1 make test-unit`: 11836 passed, 15 skipped
    (396 s). Static JS guards, `test_area_module_size.py`, `test_store_static.py` pass; ruff check and
    format clean.
  - Deviations: the key note for the token type reads "Enter the token from claude setup-token." (no
    backticks); a Save from a dirty editor after a type change by approval still sends the old type (the
    leg scopes it out; the note says Cancel); fill warnings reuse the proposal sentences ("... after
    approving") unchanged.

## Decisions

## Deviations

## Anomalies

## Session Notes
