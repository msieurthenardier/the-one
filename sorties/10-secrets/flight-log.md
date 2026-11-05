# Flight Log: Secrets

**Flight**: [Secrets](flight.md)

## Summary
Sortie planned 2026-11-04 from an operator request: let agents use locally stored secrets (a vault key passed to a tool, a website password, PII) without the values landing in transcripts. Today they sit in plain text in agent prompts.

---

## Planning Notes

### Qualification (2026-11-04)
- One outcome, one cluster of decisions (how a stored value reaches a tool without the model seeing it), no new subsystem (reuses Fernet encryption, the Library list and the attach-toggle pattern; the agent-loop change is one choke point, `_execute_tool`).
- Leg budget flagged: about 3 legs plus HAT (storage/API/grant; substitution/masking/prompt layer; Library editor and the Tools-tab section). The prompt-migration helper was cut to a manual step to stay near the limit. Re-check at the gate.
- No active mission overlaps; sortie 09 is completed.

### Charter and surfaces (operator, 2026-11-04)
- Charter agreed; migration manual.
- Applying sortie 09's lesson, the existing surfaces were settled before drawing: Library editor like the provider editor (DD1), grants as a Secrets section in the Tools tab (DD2), allowed tools required (DD3).

### Rendered mockup, round 1 (2026-11-04)
- Built in the real app (scratch dev instance on port 8492, data dir `~/the-one-s10-mockup/data`, PID recorded from `ss -ltnp`, not `$!`), with the new surfaces added through the app's own `App.ui` factories (`editorShell`, `field`, `secretInput`, `toggle`, `chipList`, `section`, `dangerZone`, `groupTile`, `toolRow`). The chat transcript is a real render of a seeded history with placeholders and masked results, so the existing trace needs no change.
- Screens (Flight Director scratchpad, `s10-mockup/`): Library › Secrets edit, create with the DD3 refusal, Tools tab option A (a "Secrets" group tile with tool rows) and option B (Knowledge-tab switch rows), and the chat transcript with a Secrets group in the agent drawer.
- Round 1 shown in the app through a scratch copy of the package (PYTHONPATH, never the repo) that loads `s10-mockup.js`, with a one-time handoff link for the operator.

### Mockup round 1 review (operator, 2026-11-04)
- Tools tab: option B (switch rows), but each row shows only the secret's name, its description and its allowed-tool count; the operator does not need the keys or the tool names there.
- Placement: the Secrets section goes at the **top** of the Tools tab.
- Allowed tools: chips **with search-ahead** (there are many tools).
- "Hide in tool results" removed: values are always masked.
- **Model change:** a secret has a friendly name and a list of key/value pairs (an address has several). The first key is generated from the name; "+ Add pair" adds more, on the MCP headers/env table. Agents reference each key as `{{secret:key}}`.

### Rendered mockup, round 2 (2026-11-04)
- Library rows show the friendly name and "N values · N agents"; the editor has Name, Description, a Values table (`App.ui.keyValueTable`, Key + secret Value, stored masks, "+ Add pair"; the first key follows the name until edited), Allowed tools (chip list with a search-ahead popover over built-in and MCP tool names), Used by, Delete.
- Tools tab: Secrets first, Knowledge-style switch rows with "description · N tools".

### Mockup round 2 approved (operator, 2026-11-04)
- Approved as shown ("like it"), including the recommendation that keys are unique across all secrets (a duplicate is refused on Save, on its row) rather than scoped (`{{secret:secret.key}}`).
- Mockup files: Flight Director scratchpad `s10-mockup/app/the_one/interfaces/web/static/js/s10-mockup.js` (round 2) and screenshots `r2-*.png`; scratch instance port 8492, data dir `~/the-one-s10-mockup/data`.

### Crew interview, part 1 (operator, 2026-11-04)
- HAT leg: yes.
- Behavior test: yes (a scripted mock provider calls a tool with `{{secret:key}}`; the tool receives the value, while the stored chat, WebSocket frames and provider request carry only placeholders and masked results).
- Agent discovery: a prompt layer ("Secrets you can use": keys, descriptions, allowed tools), **shown on Settings › Prompts** like the rules and notes examples. Platform prompt text, so it lands with an eval run against the baseline.

### Crew interview, part 2 (operator, 2026-11-04)
- Delete: allowed; the secret is removed from every agent's grants.
- Mask scope: every stored secret, granted or not (criterion 2 widened to match).
- Legs: 3 plus HAT, accepted above the soft limit (one decision cluster; per-leg review and commit).

### Code-mapping recon (2026-11-04)
An Explore agent mapped the encryption corpora, the schema, `_execute_tool` and the persistence paths, the factory and prompt layers, the Library and router wiring, the tool-name sources, the naming rule, self-configuration and reusable masking. Key findings are folded into DD4-DD9 and the Citation Audit (the "recon" rows).

### Design review 1 (Architect, Opus): approve with changes
All recon citations it sampled were accurate. It confirmed that every tool call goes through `_execute_tool`, that `resume_after_auth` re-substitutes, and that `continue` never reaches it. Changes taken:
- Tools that store or publish their input (notes, routines, self-configuration, `send_to_platform_channel`, loop virtual tools) are refused in `allowed_tools` and at runtime (DD3, DD7). Without this, a substituted value could become stored plaintext and later reach the provider.
- The mask needles add the `repr` body and both JSON `ensure_ascii` forms (DD7).
- No pydantic body parameters on the secrets routes, so no default 422 echoes a value; a test pins it (DD5).
- An MCP server rename carries `allowed_tools` (DD3).
- Behavior steps 7-8 reuse the writer's session, so a wrongly cached resolver can't hide; `max_iterations` 1; `read_file` output "contains" (DD9, spec).
- Eval scoped as a no-leak regression check (`measure-prompt`; `compare` only on a change); wording validated in the HAT (DD8, option b; Flight Director call). `the_one/db/_secrets.py` joins CLAUDE.md's platform prompt list.
- The approved mockup and screenshots were copied into `sorties/10-secrets/mockup/`, and the approved copy was written into DD1/DD2.
- Low items folded in:
  - the resolver keys on the session's current agent name (rename-safe); `default` has no grants;
  - the prompt layer is fixed at build and goes in `tool_capable` only;
  - PUT is partial at the top level, and pairs are delete-and-reinsert;
  - placeholder lookup ignores case;
  - the unknown-`secret_ids` 422 applies on POST as well, checking only new ids;
  - `/api/tool-names` parses the per-agent cache blob;
  - a shared-connection note;
  - the log sweep adds `httpx2`/`httpcore2`/`mcp`;
  - HAT external prerequisites are re-verified at leg 4.
- Suggestions taken: behavior run 1 moved to the end of leg 2; leg 3 is designed as parts A/B; SECURITY-MODEL residual risks widened; Jump to and the `#library/secrets` alias; the `Corpora` field is named `secret_values`.
- Answers to its questions: the lookup ignores case; none of the persisting tools is a legitimate `allowed_tools` choice; a refusal names only the requested key.

### Design review 2 (Architect, Opus): approve with changes (final cycle)
It verified the refused-set names, `_read_json`/`_validation_detail`, `max_iterations` 1 (one call, one dispatch) and the single `Agent(` construction site. It went through all 23 built-ins and found no other tool that stores its input. Changes taken:
- **[high] Correction to review 1's behavior-test change.** REST `POST /api/chat` with a `session_id` rebuilds the Agent on every call (`_restore_session`, `app.py:1956-1966`). So steps 7-8 prove the live store, the PUT and the rotation end to end, **not** that an Agent built before a change picks it up. The note under review 1 above ("so a wrongly cached resolver can't hide") is superseded.
  - Flight Director call, option (a): correct the claim in DD9 and the spec. The same-Agent property rests on leg 2's same-Agent unit tests (change and rotation) and the HAT's open-tab step over a live WebSocket chat.
- The resolver keys on `current_turn.session_id or current_chat_session_id`; REST sets only the former (DD7).
- The MCP-rename carry is a separate loop over all secrets beside `carry_mcp_rename`, through both callers (DD3).
- The factory injects a resolver into **every** Agent, with or without grants; the encryptor is fetched through `get_encryptor()` per read (DD7).
- Stale text fixed: the eval wording in Acceptable Variations, the spec's Out of Scope, `max_iterations`, and when the prompt layer reaches an open chat (DD8).
- Suggestions taken: the `evals/tokens.py::_layers` prerequisite for any later secrets eval; tests that `pending.py` puts the layer in `tool_capable` only; a test that the loopback credential is refused on `/api/secrets` and `/api/tool-names`; the refused set matches on `SURFACE_TOOL_PREFIX`.
- Two review cycles used; nothing left unresolved for the operator beyond plan approval.

### Plan approved (operator, 2026-11-04)
The operator approved the plan, including the Flight Director calls (refusing `send_to_platform_channel`, free-text allowed tools, HAT-validated prompt wording, no self-configuration projection change). Status `ready`. The mockup instance on 8492 was stopped by its verified PID.

---

## Flight Director Notes

### Execution start (2026-11-04)
- `/mission-control:agentic-workflow sortie 10`. Phase file `.flightops/agent-crews/leg-execution.md` loaded and validated (Crew, Interaction Protocol, Prompts present). Developer model: Sonnet. Reviewer: Sonnet (security-sensitive diff: key material, the credential gate's loopback scoping, self-configuration identity). Accessibility Reviewer (Sonnet) for leg 3.
- Branch `sortie/10-secrets` created from `origin/main` at `481546e0` (sortie 09's merge; local `main` was behind). The planning artifacts were untracked and carried over.
- Status `ready` -> `in-flight`.
- **Review cadence: per leg, not once per flight.** Each autonomous leg is reviewed and committed before the next starts, as in sortie 09 (its debrief: per-leg review caught real defects in every leg and gave fallback checkpoints) and as this flight's plan records. Leg 3 also gets a checkpoint commit between parts A and B.
- Risk tiers: legs 1-3 are all **high** (schema migration and encrypted corpus; agent loop and platform prompt; shared control-library factory and the agent write path), so each gets a Developer design review.

### Leg 1 `secrets-store`: design (2026-11-04)
- Risk tier **high**: schema migration v51, a new encrypted corpus, a write-only value path.
- Developer design review (Sonnet): **approve with changes**, all taken:
  - Secret names unique ignoring case (`COLLATE NOCASE`), with `IntegrityError` mapped to 409 and `NAME_CONFLICT_SECRET` in `naming.py`.
  - The `secret_ids` existence check ordered after `model_validate` and before `store.save`.
  - The MCP-rename carry made global (all sources), with its own `try` at the `api.py` call site, a prefix-match rule and de-duplication.
  - Tool-name sources corrected: `config["_cache"]["tools"]`, `is_surface_row`, and a new all-rows read on the agent tool cache.
  - The corpus count wording made precise: eight corpora, nine (table, column) pairs.
  - The router follows `routines_api.py` exactly.
  - Ids are `uuid4().hex`.
  - The delete scrub is a read-modify-write that doesn't bump `updated_at`.
  - A `caplog` check for log lines.
- Flight Director calls:
  - **Package renamed `the_one/secret_store/`.** Seven modules do a bare `import secrets` of the stdlib (checked), so a `the_one/secrets/` package invites shadowing. The flight's DD7 path is updated.
  - **`refused.py` imports `the_one.agent.tool_names` lazily.** `the_one/agent/__init__.py` imports `core`, and `core` will import `secret_store` in leg 2. A fresh-interpreter import test pins it.
- No second design pass: the changes adopt facts the reviewer verified in code, with no new design. Status `ready`.

### Leg 1 `secrets-store`: implementation (2026-11-04)
- Landed AC1-AC16: schema v51, `SecretRepository`, `secrets_api.py` routes, `GET /api/tool-names`, the eighth corpus (five places), grants (`secret_ids`), `secret_store/refused.py`, the MCP-rename carry (api.py PUT in its own `try`, and `name_repair`), docs (agents.md, SECURITY-MODEL.md, CLAUDE.md).
- Notes: `count_items_with_secrets` needs the owning secret, so `gather_corpora` fills `Corpora.secret_value_owners` through a separate helper (the guard's regex sees only `SELECT id, value FROM secret_values`). `SecretNameConflict`/`SecretInvalid` carry `# noqa: N818`. Loopback pins (AC14) were added as parametrized cases to `test_credential_gate.py`; no middleware change.
- Gate: `THE_ONE_TEST_NETNS=1 make test-unit`: 9064 passed, 15 skipped; one failure (`test_api_app_guard`: the rotation test built its own app) fixed to use `shared_app()` and re-run green. ruff check/format clean.
- Falsified (shown to fail with the protection removed, then restored by editing): value echoed in a 422 (no-leak test): yes; value in a log line (caplog test): yes; unknown-id grant refusal: yes; rotation loop removed (rotation test and corpora guard): yes; confined-source scoping disabled (AC14 pins): yes; top-level agent import in refused.py (fresh-interpreter test): yes.

### Leg 1 `secrets-store`: review and commit (2026-11-04)
- Reviewer (Sonnet, security tier): **[HANDOFF:confirmed]**, no blocking issues. It ran 475 targeted tests (pass) and ruff (clean). Non-blocking observations:
  1. `is_refused_tool` is case-sensitive, which is correct while tool lookup is exact. **Carried into leg 2's design:** the runtime check uses `tool_call.name` exactly as `ToolRegistry.get` matches it.
  2. `SecretRepository.delete` `json.loads` on a hand-corrupted `secret_ids` would 500. Theoretical (`NOT NULL DEFAULT '[]'`); accepted.
  3. Pre-existing, all corpora: `rotate_encryption_key` gathers corpora before its write transaction, so a secret written in that window keeps old-key ciphertext. Not introduced by this leg; noted for the debrief.
- Flight Director re-ran the unit gate after the Developer's late `shared_app()` fix: `THE_ONE_TEST_NETNS=1 make test-unit` gave **9065 passed, 15 skipped** (the expected netns count) in 246 s.
- Leg status `completed`; committed.

### Leg 2 `secrets-at-runtime`: design (2026-11-04)
- Risk tier **high**: the agent loop (the frozen `core.py`), substitution and masking of key material, and platform prompt text.
- **Frozen-loop touch.** By convention `core.py` changes only with owner approval. The operator approved DD7, which places the hook in `_execute_tool`, and was told at leg design that this counts as the approved touch, scoped minimal: a `secrets=None` kwarg, one call before execution and one after, plus masking of the two error strings. agents.md records it beside the `send_to_platform_channel` precedent.
- Developer design review (Sonnet): **approve with changes**, all taken:
  - `prepared = None` is set before the `try`, and `prepare` sits inside the inner `try` after `bind_positional_args`. A mask failure on any path withholds the output.
  - Only `content` and the error strings are masked (`metadata` is fixed).
  - A concrete type rule: str, dict (keys too), list and tuple are masked; other types pass unchanged; `bytes` already errors (pinned).
  - No resolver cache now, and a fixed number of queries per `prepare`.
  - Entry-point context coverage recorded, plus a session-row-missing fallback test.
  - Connector, routine and MCP `echo` test seams named.
  - The `pending.py` fallback passes `secrets=""` when the load fails, and never raises.
  - The existing exact-output prompt tests are the byte-identity guard.
  - The `measure-prompt` check is honestly framed: identical by construction; the output path must be outside the repo.
- No second pass (changes adopt verified code facts). Status `ready`.

### Leg 2 `secrets-at-runtime`: implementation (2026-11-04)
- Landed AC1-AC20 (status `landed`, uncommitted). New: `secret_store/runtime.py` (resolver, token pattern, one-pass masker, `Prepared`, `SecretMaskError`), `db/_secrets.py`, `tests/_secret_env.py`, `test_secret_runtime.py`, `test_secret_loop.py`, `test_secret_prompt_layer.py`. Changed: `agent/core.py` (the approved touch: `secrets=None` kwarg, `prepare` after `bind_positional_args`, `safe_mask` before `_govern`, mask of the timeout and generic error strings, a `SecretMaskError` branch), `agent/factory.py` (resolver on every Agent), `agent/config.py` (`secrets=""`), `agent/prompt_layers.py` (`load_secrets_block`, tool-capable only, omitted with a WARNING if the load fails), `self_configuration/pending.py` (main path via `build_system_prompts`; fallback retries the load, `""` if it raises), `/api/info` (`secrets_prompt_example`), `logging_config.py`, plus `test_factory.py` (resolver test, `load_secrets_block` stub in the shared fixture), `test_inbound_session_updated.py` and `test_routines_runner.py` (entry-point tests). Docs: agents.md, SECURITY-MODEL.md, CLAUDE.md.
- AC18: `measure-prompt` before and after are identical (same JSON; fingerprint `df5f2249...`). Totals (platform tokens): bare 420, all-on 773, tool-free 54, bare-connector 872, all-on-connector 1225, routines-on 1670. Files in `$HOME/the-one-s10-eval/`.
- AC14 log sweep: grep of `the_one/mcp/*.py` and `agent/core.py` for logging of arguments/bodies found nothing in the app. **Finding:** the `mcp` SDK logs whole JSON-RPC messages at DEBUG (`mcp/client/streamable_http.py:635` "Sending client message", `:191` SSE message, `sse.py:111,135`), which carry substituted tool arguments. `logging_config._QUIETED_THIRD_PARTY_LOGGERS` now also holds `httpx2`, `httpcore2`, `mcp` (WARNING). httpx2 logs only the URL line at INFO and httpcore2 only connection events, but they are quieted too.
- **Surprise (pre-existing, not changed):** `_govern` takes a `str`, so a tool returning a dict or list already becomes an `[error] ... 'dict' object has no attribute 'encode'` result in the loop. AC9's dict/list cases therefore assert the value is absent from that error; the container walk (keys included) is pinned in the masker unit tests. Noted in agents.md and SECURITY-MODEL.md.
- AC13: connector and routine entry points each reach the hook (placeholder from an agent with no grant is refused in the stored chat, using `current_time`). A routine/connector substitution case was not added (a refusal proves the hook; substitution is proven in the loop tests).
- AC6: `resume_after_auth` -> `_dispatch_tool_calls` -> `_execute_tool`, pinned by a source-level test (no MCP auth machinery).
- Design note: with no secret stored at all, `prepare` is a pass-through (AC4), so a token stays literal; the refusal tests store a secret first.
- Falsified (fix removed by editing, test shown to fail, fix restored): AC2 no-mutation yes; AC3 single pass (sequential `str.replace`) yes; AC4 fail-closed load yes, mask failure yes; AC5 mask-before-govern yes; AC7 every-agent resolver yes; AC8 provider-request/placeholder-only (core assigns `tool_call.arguments`) yes; AC9 repr needle yes, ungranted-value masking yes; AC10 refused-set runtime check yes; AC11 same-Agent freshness (added a cache) yes; AC14 log check (mcp/httpx2/httpcore2 quieting removed) yes. The real-MCP-stdio echo test proves masking of an MCP result but cannot produce HTTP request logs, so the log guarantee rests on the quieting test.
- Gate: `THE_ONE_TEST_NETNS=1 make test-unit` after the last code change: 9126 passed, 15 skipped (expected netns count), 252 s. ruff check and format clean.

### Leg 2 `secrets-at-runtime`: review fix (2026-11-04)
- AC2 vs AC4 inconsistency fixed in `secret_store/runtime.py::prepare`: tokens are collected first (`_collect`, a cheap walk), and the fast path (args unchanged, identity mask) applies only with NO tokens and NO stored values. Any token always goes through the lookup, so with an empty Library `{{secret:x}}` is refused "Secret `x` is not granted to this agent." and the tool is not called. A load failure still refuses (fail closed).
- Tests: `test_empty_library_with_a_token_is_refused` (test_secret_runtime.py) and `test_empty_library_token_refused_and_tool_not_called` (test_secret_loop.py) added; the old `test_no_secrets_stored_is_identity_and_one_query` that pinned the pass-through became `test_no_secrets_and_no_tokens_is_identity`. Falsified (condition reverted by editing, both new tests failed, restored): yes.
- Leg AC4 fast-path sentence amended ("with no tokens and no stored secrets"); agents.md Secrets runtime paragraph updated, and now notes that once any secret exists every tool call decrypts all values (uncached by design) and a DB fault refuses every tool call.

### Leg 2 `secrets-at-runtime`: review and commit (2026-11-04)
- Reviewer (Sonnet, security tier): **[HANDOFF:confirmed]**. It confirmed the `core.py` change is exactly the approved minimal hook, the substituted copy never aliases `tool_call.arguments`, masking is single-pass, longest-first and runs before `_govern` and on both error strings, fail-closed holds, and the prompt layer is `tool_capable`-only and byte-identical when empty.
- It ruled on the AC2/AC4 inconsistency (the Flight Director's spec slip): with an empty Library a token passed through as literal text. Non-blocking per the Reviewer; fixed anyway, since DD7 requires the refusal. The fast path now applies only with no tokens and no stored values. Two new tests, both falsified. Unit gate after the fix: **9128 passed, 15 skipped**.
- Non-blocking, accepted:
  - every tool call decrypts all values once any secret exists (uncached by design);
  - a DB fault refuses every tool call (fail-closed);
  - case-colliding keys are prevented by leg 1's validation.

  The first two are recorded in agents.md.
- **Log-sweep finding (fixed in leg):** the `mcp` SDK logs whole JSON-RPC messages at DEBUG (`streamable_http.py:635`, `sse.py:111,135`), which would carry substituted arguments; `httpx2`, `httpcore2` and `mcp` are now quieted to WARNING.
- Pre-existing, noted: `_govern` accepts only `str`, so a dict or list tool result already becomes an error result; masking covers that error string.
- AC18: `measure-prompt` before and after identical (bare 420, all-on 773, tool-free 54 platform tokens).
- Leg status `completed`; committed. Next: behavior test `secrets-round-trip`, run 1.

### Behavior test `secrets-round-trip`, run 1 (2026-11-05)
- **10/10 PASS** on build `c0d75b27` (after leg 2), live mode, Sonnet Executor and Validator. Run log: `tests/behavior/secrets-round-trip/runs/2026-11-05-00-43-42.md`.
- Setup: the seed was dry-run on a throwaway instance (8494, all 201) and then applied to the test instance (8493). Both PIDs were taken from `ss -ltnp`, verified through `/proc/<pid>/environ` and stopped by PID. Scratch under `$HOME/the-one-behavior-test-scratch/`.
- Charter evidence:
  - **criterion 1:** the file on disk held the real values while the stored tool call, the `/api/chat` body and the stored session held only placeholders;
  - **criterion 2:** `read_file` returned `[secret:bt_token] … [secret:bt_pin]`;
  - **criterion 3:** the exact "not granted" and "can't be used with the tool `list_dir`" refusals, naming only the key;
  - **criterion 4:** a Library change and a key rotation applied on the next call; `__MASKED__` only in every API body.
  
  The server log and all SQLite files (main, `-wal`, `-shm`) had 0 plaintext matches. Deleting the secret scrubbed the grant and the next call was refused.
- Not covered here, by design (DD9): an Agent built before a change picking it up (leg 2 unit tests; HAT open-tab step).
- Spec updated after the run: steps 5 and 6 pin the exact refusal wording (Validator suggestion); status `active`.
- Validator notes for the debrief: a replaced pair gets a new id (re-read ids from the PUT response); the zero-count step proves absence, not encryption, which is adequate alongside the decrypting steps.
