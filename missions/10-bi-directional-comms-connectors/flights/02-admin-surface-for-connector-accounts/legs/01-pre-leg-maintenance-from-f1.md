# Leg: pre-leg-maintenance-from-f1

**Status**: completed
**Flight**: [Admin Surface for Connector Accounts](../flight.md)

## Objective

Bundle the five Flight 1 debrief carry-forward items that touch surfaces Flight 2 will edit anyway: lift the Fernet envelope helpers to module-level free functions in `db/repositories.py`; codify the `function-local-import-to-break-load-cycle` project convention in `agents.md`; correct the connector-type extension checklist for the v14 → v15 → v16 schema-version sequencing AND for the Studio-not-Admin frontend placement; insert a "Skeleton for a real plugin" code block in `connectors/README.md` §3; and patch the stale F1 flight.md leg-6 bullet that still claims lifespan wiring was deferred to F2.

## Context

### Why this is leg 1 of Flight 2

Per the flight's Design Decision "Bundle the Flight 1 carry-forward maintenance into leg 0" (and the corresponding leg listing under § Legs), these five debt items are bundled into a single leg ahead of the persistence + REST + UI work so the rest of the flight builds on clean shared surfaces. Each item is small, behavior-preserving (or pure-documentation), and verifiable by grep / existing tests / inline diff:

1. **Fernet helper lift** — `_secrets_to_ciphertext` and `_ciphertext_to_secrets` are byte-identical between `MCPSourceRepository` and `ConnectorAccountRepository` (F1 debrief carry-forward item, classified `confirmed-live` in the flight log's Reconnaissance Report). Both repositories will receive new code in Flight 2 (legs 2 and beyond), so paying the lift down now is cheaper than threading two parallel envelopes through the rest of the flight.
2. **`function-local-import-to-break-load-cycle` convention** — the pattern has reached 3 occurrences across the codebase (`mcp/_pool.py`, `db/repositories.py`, `connectors/_pool.py`) and is stable; the F1 debrief flagged it for promotion to `agents.md` Project Conventions. Future flights (3, 4, 5, 8, 9) will keep encountering load cycles as the connector subsystem grows, so the convention deserves the same flag-by-name treatment as the others under "Project Conventions" (e.g. `trust-the-runtime`).
3. **`agents.md` connector-type checklist item 4 + item 6 corrections** — item 4 currently reads "v14 is already claimed by leg 02's `name` column on `connector_accounts`" and "Flight 8's v15 migration adds the CHECK." Leg 2 of THIS flight (`idle-ttl-field`) will land v15 (`idle_timeout_seconds` column), which renumbers Flight 8's CHECK to v16. Item 6 currently directs Connector frontend code to `interfaces/web/static/js/areas/admin.js`, but Flight 2's Design Decision "Studio placement, not Admin" places the connector grid + editor under `static/js/areas/studio/`. Both items need updates so the checklist stays load-bearing during Flight 8 + 9 planning.
4. **`connectors/README.md` §3 skeleton plugin block** — §3 ("Protocol decomposition") currently describes the 4-method `ConnectorPlugin` Protocol abstractly. Flight 8 (Discord) and Flight 9 (second connector) authors will benefit from a concrete ~30-line skeleton that shows the Protocol shape against a hypothetical platform SDK — without prescribing Discord or Slack specifics. The block lands in §3.
5. **F1 flight.md leg-6 bullet patch** — F1's `flight.md:175` reads "The lifespan integration is documented in code but **wired into `app.py` only in Flight 2** (when there's something to drain in production)." This is now stale — F1 leg 6 in fact wired `shutdown_drain` into `interfaces/web/app.py:lifespan` (referenced in `the_one/connectors/README.md:57-61`). The bullet needs to be patched so anyone reading F1's spec doesn't plan duplicate work.

Item 5 from the original F1 debrief carry-forward (rotation `_evict_all_for_account` wiring) is OUT OF SCOPE for this leg — per the flight's leg breakdown, that wiring lives in leg 4 (`rest-doctor-and-rotation-eviction`) because it pairs naturally with the rotation-while-pool-warm test that leg adds.

### Relevant design decisions from the flight

- **Studio placement, not Admin** — drives the item-6 wording change in `agents.md` (item 6 should point to `static/js/areas/studio/connector-accounts-grid.js` + `connector-account-editor.js` + `studio.js`, NOT `admin.js`).
- **Schema version v15 for `idle_timeout_seconds`; Flight 8's CHECK migration renumbers from v15 to v16** — drives the item-4 wording change in `agents.md` AND mirrors the Flight 1 leg-2 v14 renumber precedent.
- **Bundle the Flight 1 carry-forward maintenance into leg 0** — establishes the bundling rationale and notes that item 5 (rotation eviction) is deferred to leg 4 of THIS flight.

### Key learnings from prior flights

- **F1 leg-2 schema-version renumber precedent**: when F1 leg 2 added the `name` column at v14, it bumped `CURRENT_VERSION`, updated every `tests/test_db_migration.py` site that hardcoded the head version, and updated `_connector_types.py`'s docstring. This leg replicates the same mechanical pattern for the next renumber (v14 → v15 → v16).
- **F1 debrief lesson on "behaviour-preserving refactors":** the Fernet helper lift is behaviour-preserving by design; the existing test suites for `MCPSourceRepository` and `ConnectorAccountRepository` are the regression net.

## Inputs

What exists before this leg runs:

- `the_one/db/repositories.py` — contains TWO definitions of `_secrets_to_ciphertext` (MCP at L301, Connector at L456) and `_ciphertext_to_secrets` (MCP at L304, Connector at L459); byte-identical bodies modulo their docstrings.
- `the_one/agents.md` — "Project Conventions" section spans roughly L24-L85 (8 named conventions: `trust-the-runtime`, `canonical-import + convenience-re-export`, `structural-Protocol-satisfaction`, `verbatim-message-equality`, `gated-debug-instrumentation`, `host-side-bench-drift-detection`, `live-read-across-lazy-resolver-boundary`, `container-test-entrypoints-reach-via-make`, `landmark-elements-over-aria-roles`). The "Connector type extension checklist" section spans L271-L283.
- `the_one/connectors/README.md` — §3 ("Protocol decomposition") begins at L69; only fenced code in the file is the package-layout tree in §1.
- `missions/10-bi-directional-comms-connectors/flights/01-connector-plugin-contract-and-lifecycle-foundation/flight.md` — the leg-6 bullet at L175 still says "**wired into `app.py` only in Flight 2**".
- The existing repository test suite (`tests/test_repositories.py`, `tests/test_mcp_sources_repository.py`, `tests/test_connectors.py`, `tests/test_connectors_e2e.py`) is green on `main`; this is the regression net for the Fernet helper lift.

## Outputs

What exists after this leg completes:

- `the_one/db/repositories.py` — exposes two module-level free functions, `_encrypt_secrets_blob(encryptor, secrets) -> str` and `_decrypt_secrets_blob(encryptor, ciphertext) -> dict[str, Any]`, located somewhere in the module-level region (e.g. just above the `MCPSourceRepository` class definition). Both `MCPSourceRepository` and `ConnectorAccountRepository` retain their methods `_secrets_to_ciphertext` and `_ciphertext_to_secrets` BUT each method's body is reduced to a one-line delegating call to the shared helper, e.g. `return _encrypt_secrets_blob(self.encryptor, secrets)`. Preserving the method-on-repository surface keeps any test that mocks `repo._secrets_to_ciphertext` working unchanged. The `__MASKED__`-sentinel API-edge comment at L446 stays as-is (it documents the boundary, not the envelope).
- `the_one/agents.md` — under "Project Conventions" (after the existing entries, before the `---` separator at L86), a new `### function-local-import-to-break-load-cycle` subsection appears with a 3-4 sentence explanation and three citation points (one inline reference per file): `mcp/_pool.py`, `db/repositories.py`, `connectors/_pool.py`. Each citation includes the file path + symbol or surrounding context so the reader can confirm it (avoid bare line numbers, per the `/leg` skill's "Citing Code Locations" guideline).
- `the_one/agents.md` — under "Connector type extension checklist":
  - Item 4 (around L280) is updated. The current parenthetical "v14 is already claimed by leg 02's `name` column on `connector_accounts`" becomes "v14 is claimed by leg 02's `name` column on `connector_accounts` (F1 L2); v15 by leg 02 of Flight 2 — `idle_timeout_seconds`." The "Flight 8's v15 migration adds the CHECK" wording becomes "Flight 8's **v16** migration adds the CHECK via the table-rename ceremony established by v6/v12."
  - Item 6 (around L282) — the literal reference to `interfaces/web/static/js/areas/admin.js` is rewritten to "`interfaces/web/static/js/areas/studio/connector-accounts-grid.js` + `studio/connector-account-editor.js` + integration in `static/js/areas/studio.js`; Flight 8 supplies the Discord-specific badge styles. Admin only if a future surface needs it."
- `the_one/connectors/README.md` — §3 ("Protocol decomposition") gains a "Skeleton for a real plugin" fenced code block (~30 lines) showing how a future plugin satisfies the 4-method `ConnectorPlugin` Protocol against a hypothetical platform SDK. The block sits AFTER the existing prose in §3 and BEFORE §4 ("Test seams"). Imports use forward-typed Protocol references (`ConnectorClient`, `InboundEnvelope`, `OutboundTarget`, `SessionKey`, `DoctorReport`) and the example returns a `DoctorReport(status='ok', details={...})` instance from `doctor()`. The platform is unnamed (e.g. `HypotheticalPlatform`) so neither Discord nor Slack ergonomics are baked into the skeleton.
- `missions/10-bi-directional-comms-connectors/flights/01-connector-plugin-contract-and-lifecycle-foundation/flight.md` — the leg-6 bullet at L175 is updated. The phrase "**wired into `app.py` only in Flight 2** (when there's something to drain in production)" becomes "**wired into `app.py` in this flight's leg 6** (lifespan integration completed; `shutdown_drain` runs at FastAPI lifespan shutdown after the MCP pool drain and before the OAuth periodic-sweep stop)."

## Acceptance Criteria

- [ ] `_encrypt_secrets_blob(encryptor, secrets)` and `_decrypt_secrets_blob(encryptor, ciphertext)` exist as module-level free functions in `the_one/db/repositories.py`, with the migration-residue `InvalidToken → {}` and `JSONDecodeError propagates` semantics preserved verbatim.
- [ ] `MCPSourceRepository._secrets_to_ciphertext` and `_ciphertext_to_secrets` delegate to the shared helpers (single-line implementations).
- [ ] `ConnectorAccountRepository._secrets_to_ciphertext` and `_ciphertext_to_secrets` delegate to the shared helpers (single-line implementations).
- [ ] Existing repository test suites pass byte-identically (no test modification required for the lift): `tests/test_db_repositories.py`, `tests/test_connectors.py`, `tests/test_connectors_pool.py`, `tests/test_connectors_e2e.py`. The full `make test` clean.
- [ ] `agents.md` Project Conventions section contains a new `### function-local-import-to-break-load-cycle` subsection with a 3-4 sentence explanation and three durable citations (file + symbol or file + snippet, NOT bare line numbers).
- [ ] `agents.md` Connector type extension checklist item 4 reflects v14 → v15 → v16 ordering with the F1 L2 + F2 L2 + F8 references; the original "Flight 8's v15" wording is gone.
- [ ] `agents.md` Connector type extension checklist item 6 references `static/js/areas/studio/connector-accounts-grid.js` + `studio/connector-account-editor.js` + `studio.js`; the original literal reference to `admin.js` is gone.
- [ ] `the_one/connectors/README.md` §3 contains a "Skeleton for a real plugin" fenced code block of approximately 30 lines (±10), showing a hypothetical-platform plugin class that satisfies all 4 `ConnectorPlugin` methods, returns a `DoctorReport` from `doctor()`, and uses canonical-import paths.
- [ ] `missions/10-bi-directional-comms-connectors/flights/01-connector-plugin-contract-and-lifecycle-foundation/flight.md` leg-6 bullet at L175 no longer contains the phrase "wired into `app.py` only in Flight 2"; it instead reflects that lifespan wiring shipped in F1 leg 6.
- [ ] `make lint` clean — no new lint findings introduced by the helper lift or documentation edits.

## Verification Steps

How to confirm each criterion:

- `grep -n "_encrypt_secrets_blob\|_decrypt_secrets_blob" the_one/db/repositories.py` — should show the function definitions once each, plus four call sites (two in `MCPSourceRepository`, two in `ConnectorAccountRepository`).
- `grep -n "def _secrets_to_ciphertext\|def _ciphertext_to_secrets" the_one/db/repositories.py` — should still show four method definitions (one pair per repository), each now a one-line delegating call.
- `docker exec the-one pytest -x --timeout 30 tests/test_db_repositories.py tests/test_connectors.py tests/test_connectors_pool.py tests/test_connectors_e2e.py` — all green.
- `make test` — full suite clean.
- `grep -n "function-local-import-to-break-load-cycle" the_one/agents.md` — should show one heading match.
- `grep -n "v15.*idle_timeout_seconds\|v16 migration\|admin.js" the_one/agents.md | grep -i connector` — connector-checklist item 4 mentions v15 + v16; no remaining `admin.js` reference in the connector checklist.
- `grep -n "Skeleton for a real plugin" the_one/connectors/README.md` — should show one heading match inside §3.
- `grep -n "wired into.*app.py only in Flight 2" missions/10-bi-directional-comms-connectors/flights/01-*/flight.md` — should return nothing (the phrase is gone).
- `make lint` — clean.

## Implementation Guidance

0. **Pre-lift consumer audit** — before changing `repositories.py`, run `grep -rn "_secrets_to_ciphertext\|_ciphertext_to_secrets" the_one/ tests/ interfaces/ 2>/dev/null` and skim every hit. The known landscape on the current branch:
   - `the_one/db/repositories.py` — the four method definitions plus their four internal call sites (the lift's actual edit surface).
   - `interfaces/web/api.py:2784` — **comment-only** reference inside the rotation transaction; no behaviour change needed, but flag it in your edit summary so future grep audits know the comment is doc-only.
   - `tests/test_provider_api.py:950` — same shape (comment-only reference).
   - No test mocks or monkey-patches the methods (verified at design time). Preserving the methods as one-line delegators is belt-and-suspenders. If the grep surfaces a NEW consumer not on this list, surface it as a deviation before proceeding.

1. **Lift the Fernet helpers** (`the_one/db/repositories.py`)
   - Add two module-level free functions near the top of the module (after the imports, before the first repository class). Names: `_encrypt_secrets_blob(encryptor: Encryptor, secrets: dict[str, Any]) -> str` and `_decrypt_secrets_blob(encryptor: Encryptor, ciphertext: str | None) -> dict[str, Any]`.
   - Body of `_encrypt_secrets_blob`: `return encryptor.encrypt(json.dumps(secrets))` (verbatim from the current method bodies).
   - Body of `_decrypt_secrets_blob`: the existing decrypt path — empty/None ciphertext → `{}`; `try/except InvalidToken` → `{}` (migration residue); `json.loads(plaintext)` (JSONDecodeError propagates). Docstring documents both swallow-conditions explicitly, mirroring the canonical wording in the current methods.
   - In `MCPSourceRepository._secrets_to_ciphertext`: replace the body with `return _encrypt_secrets_blob(self.encryptor, secrets)`. Same shape for `_ciphertext_to_secrets`: `return _decrypt_secrets_blob(self.encryptor, ciphertext)`. The method's own docstring may stay or be slimmed to "Delegates to `_decrypt_secrets_blob`."
   - Same shape for `ConnectorAccountRepository`.
   - Do NOT move the `__MASKED__`-sentinel API-edge comment at L446 — that comment documents the boundary, not the envelope.
   - Run `docker exec the-one pytest -x --timeout 30 tests/test_repositories.py tests/test_connectors.py tests/test_connectors_e2e.py` to confirm regression net.

2. **Add the project convention to `agents.md`**
   - Append a new `### function-local-import-to-break-load-cycle` subsection inside the "Project Conventions" section (after `### landmark-elements-over-aria-roles`, before the `---` separator).
   - Explanation (3-4 sentences): when two modules transitively import each other (e.g. `connectors/_pool.py` ↔ `db/repositories.py` via `the_one.mcp.__init__`), the top-level import order can fail with `ImportError` if the cycle is initiated from one entry but not the other. Function-local imports break the cycle at the call site without forcing global discipline, and the project applies this pattern when it surfaces.
   - Three citations (use durable forms — symbol + brief snippet, NOT bare line numbers):
     - `db/repositories.py: find_by_runtime_package — "from the_one.mcp.cache_cleanup import extract_runtime_package"` (the "Local import to avoid a circular" comment is the verifier).
     - `connectors/_pool.py: _load_account — "from the_one.db.connection import get_connection / from the_one.db.repositories import ConnectorAccountRepository"` (the function-local import block with the load-cycle explanation in the docstring).
     - **`mcp/_pool.py` 3rd-citation outcome — confirmed at design review**: neither of the function-local imports in `mcp/_pool.py` (L195 `agent._context` symbols, L196 `oauth.build_oauth_provider_for_source`) has a comment documenting a load-cycle motivation, and `mcp/_pool.py` top-level imports `the_one.db.repositories` cleanly. The honest answer is **drop to two citations** and add a one-line note: "Pattern is at the 2-occurrence threshold pending a clearer 3rd documented occurrence." This is the recommended path; do NOT invent motivation that isn't there. (The flight-spec recon's mention of `mcp/_pool.py:196` as the third citation was speculative and rejected at design review.)

3. **Patch the `agents.md` connector-type checklist (items 4 and 6)**
   - Item 4 — current text (paraphrased): "Flight 8's v15 migration adds the CHECK ... v14 is already claimed by leg 02's `name` column on `connector_accounts`."
   - Item 4 — new text: "v14 is claimed by leg 02's `name` column on `connector_accounts` (F1 L2); v15 by leg 02 of Flight 2 — `idle_timeout_seconds`; Flight 8's **v16** migration adds the CHECK via the table-rename ceremony established by v6/v12."
   - Item 6 — current text: "Frontend — `interfaces/web/static/js/areas/admin.js`: connector-type defaults, badge styles in `tokens.css` + `admin.css`. Flight 2 lands the Admin connector pages + Studio attach surface; Flight 8 supplies the Discord-specific assets."
   - Item 6 — new text: "Frontend — `interfaces/web/static/js/areas/studio/connector-accounts-grid.js` + `studio/connector-account-editor.js` + integration in `static/js/areas/studio.js`. Badge styles land in `tokens.css` + the corresponding studio CSS rule. Flight 2 lands the Studio connector pages + Studio attach surface; Flight 8 supplies the Discord-specific assets. (Admin only if a future surface needs it.)"

4. **Insert the "Skeleton for a real plugin" code block in `connectors/README.md`**
   - Locate §3 ("Protocol decomposition") around L69.
   - After the existing prose ("Single contract file (the mission criterion) means one `base.py`, not one Protocol. Multiple Protocols in one file satisfy the criterion."), add a sub-heading like `### Skeleton for a real plugin` followed by a fenced Python code block (~30 lines, ±10).
   - The skeleton:
     - Imports from `the_one.connectors.base` (canonical path).
     - Defines a `HypotheticalPlatformPlugin` class (no inheritance — `structural-Protocol-satisfaction`).
     - Implements `connect(account, encryptor) -> ConnectorClient`, `disconnect(client) -> None`, `doctor(account, encryptor) -> DoctorReport`, `normalize_session_key(account, envelope) -> SessionKey`. Bodies are illustrative stubs with `# pseudo-code — replace with real SDK call` comments noting where real platform-SDK calls would go.
     - Includes a `# Registered via register_builtin_connectors() in connectors/registry.py — see agents.md "Connector type extension checklist".` comment.
   - Use explicit `# pseudo-code` comments in place of `# type: ignore` / `cast()` pragmas — keeps lint quiet without leaking ignore-noise into the canonical skeleton.
   - Does NOT mention Discord or Slack by name.

5. **Patch the F1 flight.md leg-6 bullet**
   - Open `missions/10-bi-directional-comms-connectors/flights/01-connector-plugin-contract-and-lifecycle-foundation/flight.md`.
   - Locate the leg-6 bullet around L175 (current text contains "**wired into `app.py` only in Flight 2**").
   - Replace the wired-into clause with: "**wired into `app.py` in this flight's leg 6** (FastAPI lifespan shutdown invokes `shutdown_drain` AFTER the MCP pool drain and BEFORE the OAuth periodic-sweep stop)."

6. **Run lint + tests**
   - `make lint` — clean.
   - `make test` — clean. (The flight log records the pre-leg test count; this leg adds zero new tests and modifies zero existing ones, so the count should be byte-identical.)

7. **Update artifacts and the flight log per the leg-execution prompt**
   - Set this leg's status to `landed` after acceptance criteria pass.
   - Append a "Leg Progress" entry to the flight log with the changes made.
   - Do NOT commit — per `/agentic-workflow`, review and commit happen once at the end of the flight.

## Edge Cases

- **Test files on the current branch** — verified at design time: the regression net for the Fernet envelope lives across `tests/test_db_repositories.py`, `tests/test_connectors.py`, `tests/test_connectors_pool.py`, and `tests/test_connectors_e2e.py`. There is NO `tests/test_repositories.py` or `tests/test_mcp_sources_repository.py` on this branch; ignore those names if any prior drafts mentioned them.
- **Comment-only consumers of `_secrets_to_ciphertext` / `_ciphertext_to_secrets`** — confirmed at design time: `interfaces/web/api.py:2784` and `tests/test_provider_api.py:950` reference the symbol in **comments only** (no behavioural call). Leg makes no change to those comments. If the implementer chooses to update the comment text to reference the new shared helper as well as the delegating method, that is OK; it is not required.
- **The shared helpers may need an `Encryptor` import** — the file already imports `Encryptor` for the repository classes; if `from the_one.encryption import Encryptor` is already in place, the new module-level functions can use it directly. Otherwise add the import. **`Any` and `json` and `InvalidToken`** are likewise already imported for the existing methods.
- **`mcp/_pool.py` citation isn't a load-cycle-break** — covered in step 2 above. If the implementer cannot confirm the cycle-break motivation at the cited line after inspection, they may substitute a different citation (with verification) or drop to a 2-occurrence list and note the pending third. The convention can still go in `agents.md` with two citations — naming the pattern matters more than padding the citation list. **Do not invent motivation that isn't there.**
- **`connectors/README.md` heading-level consistency** — §3 currently uses `## §3. Protocol decomposition` (level 2). The new "Skeleton for a real plugin" sub-heading should be `### Skeleton for a real plugin` (level 3) so the section TOC stays clean.
- **`agents.md` Project Conventions ordering** — append the new convention to the END of the convention list (after `landmark-elements-over-aria-roles`) so the most recently-added pattern is most-recent in the file. Do NOT alphabetize; the existing ordering is by introduction order.

## Files Affected

- `the_one/db/repositories.py` — lift two helper bodies to module level; reduce four methods to delegating one-liners. ~30 LoC net change (~+10 / -20), behaviour-preserving.
- `the_one/agents.md` — append one Project Conventions subsection (~6 lines); update two items in the connector-type extension checklist (~4 lines net).
- `the_one/connectors/README.md` — add ~30 lines (sub-heading + fenced code block) inside §3.
- `missions/10-bi-directional-comms-connectors/flights/01-connector-plugin-contract-and-lifecycle-foundation/flight.md` — replace one phrase in the leg-6 bullet at L175.
- `missions/10-bi-directional-comms-connectors/flights/02-admin-surface-for-connector-accounts/flight-log.md` — append a "Leg Progress" entry for this leg.
- `missions/10-bi-directional-comms-connectors/flights/02-admin-surface-for-connector-accounts/flight.md` — check off this leg in the Legs list.

## State-Machine Reachability Audit

No state-machine or lifecycle-value changes in this leg. The Fernet helper lift is behaviour-preserving by construction; the documentation edits do not introduce or change any runtime state. No FK / CHECK / cache-invalidation surface is touched.

## Cache Freshness Contract

N/A — this leg does not read from or populate any cache.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified
- [ ] `make test` passing (byte-identical pass count vs. pre-leg baseline)
- [ ] `make lint` clean
- [ ] Flight log updated with a "Leg Progress" entry under `### Leg Progress` summarizing the five carry-forward items addressed
- [ ] This leg's status updated to `landed` (in this file's header)
- [ ] This leg checked off in `flight.md` Legs list
- [ ] Do NOT commit — review and commit happen once at the end of the flight per `/agentic-workflow`

---

## Citation Audit

6 code-location citations verified against current code at leg design time (5 original + 1 added during design-review incorporation):

- `the_one/db/repositories.py: _secrets_to_ciphertext / _ciphertext_to_secrets` (MCP at L301/L304; Connector at L456/L459) — **OK** (verified live; flight log Reconnaissance Report cited L301-326 / L456-479 — the small bookkeeping drift between the recon's 301-326 range and the actual L301/L304 starts is not material).
- `the_one/db/repositories.py: find_by_runtime_package — "Local import to avoid a circular: cache_cleanup is in the_one.mcp"` (L396-398) — **OK**.
- `the_one/connectors/_pool.py: _load_account — function-local import block (L157-169)` — **OK** (the docstring at L157-167 explicitly explains the load cycle).
- `the_one/agents.md: Connector type extension checklist item 4 (L280) and item 6 (L282)` — **OK** (verified live).
- `missions/10-bi-directional-comms-connectors/flights/01-connector-plugin-contract-and-lifecycle-foundation/flight.md: leg-6 bullet at L175 — "wired into `app.py` only in Flight 2"` — **OK** (verified live; phrase still present and contradicts what shipped).

Added after design review (consumer-audit baseline):

- `interfaces/web/api.py:2784 (rotate_encryption_key)` — comment-only reference to `_ciphertext_to_secrets` — **OK** (no behavioural call; flagged in Implementation Guidance step 0).
- `tests/test_provider_api.py:950` — comment-only reference — **OK** (no behavioural call).

1 original citation rejected at design review (not drift — original was speculative):

- `the_one/mcp/_pool.py:196` — **unverifiable as load-cycle-break**. Line 196 is `from the_one.mcp.oauth import build_oauth_provider_for_source`; surrounding code does not document a load-cycle motivation. The 3rd-citation slot in the new `function-local-import-to-break-load-cycle` convention is **dropped** (the convention lands with 2 documented citations + a one-line "pending 3rd documented occurrence" note). This is the recommended path per design review.
