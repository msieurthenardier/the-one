# Leg: account-config-pairing-and-allowlist-schema

**Status**: completed
**Flight**: [Pairing, Allowlists, and Per-Agent ACLs](../flight.md)

> **Post-redesign note (M10 F6 L7 HAT, 2026-05-19)**: the
> account-scope `config.allowlist` SHAPE captured below is unchanged
> (still `{"peers": list[str], "channels": list[str]}`), but the
> SEMANTIC for empty lists was flipped during HAT: empty list now
> means "unrestricted on this axis" (was "lockdown / no peer
> admitted"). See the **Deviations** entry in
> `../flight-log.md` ("Allowlist/ACL semantic redesign at HAT") for
> the full new model, surface impact, and rationale. The body of this
> artifact reflects the pre-redesign contract for archaeology.

## Objective

Carve a typed schema into the existing `ConnectorAccount.config: dict[str, Any]` slot for two reserved keys — `config["pairing"]` (DM-pairing state: code + issuance timestamp) and `config["allowlist"]` (account-scope peers + channels lists). Validation lands as a `@field_validator("config", mode="after")` on `ConnectorAccount` that parses ONLY the reserved keys; the rest of `config` stays schema-loose per the F1 promise. Both the API write path (`api.py:create_connector_account` at L2154, `update_connector_account` at L2218) and the DB read path (`repositories.py:ConnectorAccountRepository._row_to_model` at L559-570) run through the validator because Pydantic v2's direct `ConnectorAccount(...)` construction runs `@field_validator` on `__init__` — confirmed by the existing `_validate_idle_timeout_seconds` + `_validate_session_continuation_seconds` behavior that already runs on both paths. No schema migration: rides on the existing `config TEXT` column.

## Context

- **Flight Design Decision — "Account-config persistence for account-scope state"** (flight.md): `config["pairing"] = {"code": str, "issued_at": iso}` and `config["allowlist"] = {"peers": list[str], "channels": list[str]}`. No schema migration.
- **Flight In-Flight §2** (flight.md): "Pydantic validators land via a `@field_validator("config")` on `ConnectorAccount` that parses ONLY the reserved keys (the rest of `config` stays schema-loose per the F1 promise). The validator fires on `ConnectorAccount.model_validate(merged)` at `api.py:2218`; the read-from-DB path at `repositories.py:_row_to_model` constructs via direct kwargs so it skips the validator — leg 1b's design walks both paths and decides whether to add `model_validate` on read or accept one-sided validation."
- **Pydantic v2 behavior verified at design time**: direct `ConnectorAccount(id=..., config=..., ...)` construction DOES run `@field_validator` — the existing `_validate_idle_timeout_seconds` and `_validate_session_continuation_seconds` validators run on BOTH the API path (via `model_validate`) AND the repository read path (via direct kwargs construction at `_row_to_model` L559). The cycle-1 H2 concern ("validators on `dict[str, Any]` don't fire on JSON read path without explicit `model_validate`") was a Pydantic-v1-era worry; in v2, `BaseModel(**kwargs)` runs validators. The leg-design decision is therefore: **NO change to `_row_to_model`** — keep the direct-kwargs construction; the validator runs automatically on both paths. This avoids touching the repository layer and keeps the leg surface narrow.
- **F4 L5 substrate**: `ConnectorAccount` already carries `connector_account_ids` integration; this leg adds two ORTHOGONAL keys to its `config` dict. The four-field `_row_to_model` shape (id, name, type, config, secrets + the two timeouts + timestamps) is verified at `repositories.py:559-570`.
- **Schema-loose contract**: the F1 promise (per `db/models.py:134` comment, README §1, and the cycle-1 architect ratification) is that `config` accepts arbitrary operator-managed connector state. Leg 1b RESERVES two top-level keys (`"pairing"`, `"allowlist"`) and ONLY validates those keys; any other top-level key passes through. Existing rows with `config={"intent": "guild_messages"}` continue to round-trip unchanged.
- **Default-permissive semantics**: an account whose `config` lacks the `"allowlist"` key MUST be treated by legs 2 and 3 as "no allowlist — permit everyone" (the `_default_permit` outcome from leg 1a). Likewise, missing `"pairing"` means "no pairing code issued for this account — `NeedsPairing` outcomes are unresolvable until the operator generates a code in leg 4's Studio surface." Leg 1b ENCODES this default by:
  - Making both reserved keys OPTIONAL in the validator (absent key = no validation work; not a default-injection)
  - NOT auto-populating either key on create (operator must opt in via the Admin surface in leg 4)
- **Empty-allowlist semantics — different from absent-allowlist**: `config["allowlist"] = {"peers": [], "channels": []}` is structurally valid (both lists empty) and means "no peer / no channel is admitted" (operator-locked account). `config["allowlist"]` absent means "default-permit." Documented in the validator docstring AND consumed by leg 2 (inbound) AND leg 3 (outbound). The distinction matters: leg 4's Studio UI must NOT erase a deliberate `{"peers": [], "channels": []}` lockdown back to "absent" when the operator clicks save with no entries.
- **Pairing code shape**: `{"code": str, "issued_at": str (ISO timestamp)}`. The validator enforces `code` is a non-empty string and `issued_at` is parseable as ISO (use `datetime.fromisoformat`). The CODE itself is operator-supplied (or operator-regenerated from Studio in leg 4) — leg 1b does NOT generate the code; that's leg 4's writer. Leg 2's dispatcher does the validate-against-stored-code work.
- **Allowlist shape**: `{"peers": list[str], "channels": list[str]}`. Both keys REQUIRED when `allowlist` is present (no partial-shape allowlist). String entries (platform-native peer/channel IDs). The validator does NOT validate the contents of the strings (a Discord snowflake vs. a Slack user-id has no shared schema) — only the structural shape (lists of strings; both keys present; no extra keys under `allowlist`).
- **Validator placement**: `mode="after"` rather than `mode="before"` — the field default-factory has already produced a dict by the time the validator runs, so the validator's job is shape-checking, not coercion. Matches the existing `_validate_idle_timeout_seconds` / `_validate_session_continuation_seconds` precedent which use the default (`mode="after"`).
- **Test fixture style**: `tests/test_db_repositories.py::TestConnectorAccountRepository` (L462+) is the established home for round-trip tests. Two new test methods (or a dedicated TestConnectorAccountConfigSchema class) for the pairing + allowlist round-trips. Pydantic-validator unit tests can live in a new `tests/test_db_models.py` or be appended to a model-test module — there is no existing `test_db_models.py`, so the cleanest home is to extend `tests/test_db_repositories.py` with model-level construction tests OR to introduce a new module. Leg-design decision: append a `TestConnectorAccountConfigValidator` class to `tests/test_db_repositories.py` (lighter than a new module; the class boundary captures the scope).
- **Backward-compatibility surface**: existing rows in production / dev databases have `config` shapes the operator wrote during F1/F2/F4 — typically `{"intent": "guild_messages"}` or similar arbitrary stub-era keys. None contain `pairing` or `allowlist` keys (grep verified zero hits across the codebase and tests). Validator MUST NOT reject these rows on read — the optional-key validator design ensures this.
- **Leg 2/leg 3 read pattern**: both consume `account.config.get("pairing")` and `account.config.get("allowlist")`. Optional values, default-permit-on-absence. The exact accessor shape will be a leg-2 / leg-3 decision; leg 1b ships the data so they have something to read.

## Inputs

- `the_one/db/models.py:118-186` — `ConnectorAccount` Pydantic model with the two existing field validators and the `config: dict[str, Any]` field
- `the_one/db/repositories.py:458-570` — `ConnectorAccountRepository` with `_row_to_model` (L559-570) using direct kwargs construction
- `the_one/interfaces/web/api.py:2148-2240` — POST + PUT handlers using `ConnectorAccount.model_validate` (L2154 and L2218 respectively)
- `the_one/interfaces/web/api.py:2087-2104` — `_connector_account_response` masking surface (NOT touched in leg 1b — pairing code is part of `config`, which is currently rendered as-is; legs 2/4 will revisit masking semantics for the pairing code when the operator-facing API exposes it)
- `tests/test_db_repositories.py:462+` — `TestConnectorAccountRepository` round-trip tests; leg 1b adds sibling tests
- Existing field-validator precedent at `the_one/db/models.py:141-159` (`_validate_idle_timeout_seconds`) and `:161-186` (`_validate_session_continuation_seconds`) — same shape, same docstring style, same `ValueError` raising pattern
- Leg 1a's `Permit` / `NeedsPairing` / `Deny` ADT is NOT directly consumed by this leg — leg 1b ships the persistence shape; legs 2 and 3 wire the outcome construction. The connection between the two surfaces is documented at the leg-1b validator docstring (one-line forward reference).

## Outputs

- `the_one/db/models.py` — `ConnectorAccount` gains a `@field_validator("config", mode="after")` method `_validate_config_reserved_keys` that walks the two reserved keys (`pairing`, `allowlist`) and validates each independently. Absent key → no work (returns unchanged). Non-conforming key → `ValueError` with operator-facing message.
- `the_one/db/repositories.py` — UNCHANGED (`_row_to_model` keeps its direct-kwargs construction; the validator runs on both paths because Pydantic v2 runs `@field_validator` on `__init__`).
- `the_one/interfaces/web/api.py` — UNCHANGED (the existing `model_validate` calls at L2154 and L2218 already exercise the validator; no API-handler edits needed)
- `tests/test_db_repositories.py` — new `TestConnectorAccountConfigValidator` class (appended after `TestConnectorAccountRepository`) with: round-trip pairing through repo write+read; round-trip allowlist through repo write+read; allowlist with empty `{"peers": [], "channels": []}` is preserved verbatim (not erased to absent); arbitrary non-reserved keys pass through unchanged; malformed `pairing` (missing `code`) raises at model_validate; malformed `pairing` (non-string `code`) raises; malformed `pairing` (non-ISO `issued_at`) raises; malformed `allowlist` (partial shape — only `peers`) raises; malformed `allowlist` (extra key) raises; malformed `allowlist` (non-list `peers`) raises; non-string entries in `peers` raise; direct construction round-trip (no API layer, no DB) exercises the validator path
- The validator MUST NOT auto-inject defaults (no `config.setdefault("allowlist", {...})`). An absent key stays absent.

## Acceptance Criteria

- [ ] `ConnectorAccount` model in `the_one/db/models.py` carries a `@field_validator("config", mode="after")` classmethod named `_validate_config_reserved_keys` that:
  - Walks ONLY the two reserved keys `"pairing"` and `"allowlist"`
  - Leaves all other top-level keys unchanged (round-trip preservation)
  - Raises `ValueError` with operator-facing messages on shape violations
  - Returns the (unchanged on the happy path) dict
- [ ] The `"pairing"` key, when present, MUST have shape `{"code": str (non-empty), "issued_at": str (ISO-parseable)}` and no extra keys
- [ ] The `"allowlist"` key, when present, MUST have shape `{"peers": list[str], "channels": list[str]}` and no extra keys; both inner lists are REQUIRED (absent → ValueError); empty inner lists are PERMITTED and PRESERVED VERBATIM (not coerced to absent)
- [ ] An account constructed with `config={}` (default), `config={"intent": "guild_messages"}` (existing F1/F2 test fixture shape), or `config={"pairing": {...valid...}, "allowlist": {...valid...}, "other": "key"}` (mixed reserved + non-reserved) ALL round-trip cleanly through `ConnectorAccount(**kwargs)`, `ConnectorAccount.model_validate(dict)`, and through `ConnectorAccountRepository.{create, get, update, list}`
- [ ] No auto-injection of reserved keys on create — `ConnectorAccount(id=..., name=..., type=...)` results in `config == {}` (NOT `{"allowlist": {...}, "pairing": {...}}`)
- [ ] Existing tests in `tests/test_db_repositories.py::TestConnectorAccountRepository` pass byte-identically (no count change; the fixture shape `config={"intent": "guild_messages"}` continues to round-trip)
- [ ] Existing tests in `tests/test_db_api.py` (connector-account API tests live there — confirmed at design time; hits at L544, L557, L567, L574, L581, L603, L612, L621, L637, L650, L676, L689, L698, L707, L720, L733, L746) pass byte-identically — the validator does not change the API contract for accounts that don't use the reserved keys
- [ ] F1/F2/F3/F4/F5 regression suites pass byte-identically (no consumer touches the reserved keys yet)
<!-- Removed aspirational AC about _default_permit — that's a legs 2/3 concern, not verifiable inside leg 1b. Documented in Context above. -->
- [ ] New tests in `tests/test_db_repositories.py::TestConnectorAccountConfigValidator` cover: pairing round-trip; allowlist round-trip; empty-allowlist preservation; non-reserved-key pass-through; malformed pairing (3 variants); malformed allowlist (4 variants); direct-construction validator path
- [ ] `ruff check` clean on modified files; full test suite `docker exec the-one pytest -x --timeout 30` passes

## Verification Steps

- `python -c "from the_one.db.models import ConnectorAccount; a = ConnectorAccount(id='1', name='n', type='stub'); assert a.config == {}; print('ok')"` (inside the container)
- `python -c "from the_one.db.models import ConnectorAccount; a = ConnectorAccount(id='1', name='n', type='stub', config={'pairing': {'code': 'abc', 'issued_at': '2026-05-18T00:00:00Z'}}); print(a.config)"`
- `python -c "from the_one.db.models import ConnectorAccount; ConnectorAccount(id='1', name='n', type='stub', config={'pairing': {'code': '', 'issued_at': '2026-05-18T00:00:00Z'}})"` should raise `ValueError`
- `python -c "from the_one.db.models import ConnectorAccount; ConnectorAccount(id='1', name='n', type='stub', config={'allowlist': {'peers': ['p1']}})"` should raise `ValueError` (missing `channels`)
- `python -c "from the_one.db.models import ConnectorAccount; ConnectorAccount(id='1', name='n', type='stub', config={'allowlist': {'peers': [], 'channels': []}})"` should succeed and round-trip with verbatim `{'peers': [], 'channels': []}`
- `docker exec the-one pytest -x --timeout 30 tests/test_db_repositories.py::TestConnectorAccountRepository tests/test_db_repositories.py::TestConnectorAccountConfigValidator`
- `docker exec the-one pytest -x --timeout 30` — full suite passes

## Implementation Guidance

1. **Add the validator to `ConnectorAccount` in `the_one/db/models.py`** — placement right after `_validate_session_continuation_seconds` (around line 186), before the next model class starts. The shape:

   ```python
   @field_validator("config", mode="after")
   @classmethod
   def _validate_config_reserved_keys(cls, value: dict[str, Any]) -> dict[str, Any]:
       """Enforce shape on the two F6-reserved top-level keys in ``config``.

       The reserved keys are ``"pairing"`` (DM-pairing state) and
       ``"allowlist"`` (account-scope peer/channel admission). Each is
       OPTIONAL — when absent, the resolver subsystem defaults to permit
       (see ``_default_permit`` at ``the_one/connectors/base.py``). All
       other top-level keys in ``config`` pass through unchanged — the F1
       promise that ``config`` is schema-loose remains intact.

       Shape contracts (raise ``ValueError`` on violation):

       - ``config["pairing"] = {"code": str (non-empty), "issued_at": str (ISO)}``.
         No extra keys. Both fields required when ``pairing`` is present.
       - ``config["allowlist"] = {"peers": list[str], "channels": list[str]}``.
         Both inner lists required (no partial shape). Empty inner lists
         are PERMITTED and PRESERVED VERBATIM — they mean "locked account,
         no peers admitted." Absent ``allowlist`` means "default-permit
         (no restriction)." Distinct semantics; the leg-4 Studio surface
         MUST NOT erase a deliberate empty lockdown back to absent.

       Pydantic v2 ``@field_validator`` runs on both
       ``ConnectorAccount(**kwargs)`` direct construction AND
       ``ConnectorAccount.model_validate(dict)``, so this fires on the
       repository read path AT
       ``the_one/db/repositories.py:_row_to_model`` and on the API write
       path at ``the_one/interfaces/web/api.py:{create,update}_connector_account``.
       """
       pairing = value.get("pairing")
       if pairing is not None:
           if not isinstance(pairing, dict):
               raise ValueError(
                   "config['pairing'] must be a dict with keys "
                   "{'code', 'issued_at'}"
               )
           extra = set(pairing.keys()) - {"code", "issued_at"}
           if extra:
               raise ValueError(
                   f"config['pairing'] has unexpected keys: {sorted(extra)}"
               )
           missing = {"code", "issued_at"} - set(pairing.keys())
           if missing:
               raise ValueError(
                   f"config['pairing'] is missing required keys: {sorted(missing)}"
               )
           code = pairing.get("code")
           if not isinstance(code, str) or not code:
               raise ValueError(
                   "config['pairing']['code'] must be a non-empty string"
               )
           issued_at = pairing.get("issued_at")
           if not isinstance(issued_at, str):
               raise ValueError(
                   "config['pairing']['issued_at'] must be an ISO-format string"
               )
           # Require a time component (T separator) — date-only strings
           # like "2026-05-18" parse cleanly through fromisoformat but
           # carry no audit value. The leg-4 Studio writer emits full
           # ISO timestamps with time + offset; this guard rejects
           # accidental date-only entries.
           if "T" not in issued_at:
               raise ValueError(
                   "config['pairing']['issued_at'] must include a time "
                   "component (e.g. '2026-05-18T12:34:56Z'); got "
                   f"date-only value {issued_at!r}"
               )
           try:
               # Accept Z-suffix and naive forms; Python 3.11+
               # ``fromisoformat`` parses both with the .replace shim.
               datetime.fromisoformat(issued_at.replace("Z", "+00:00"))
           except ValueError as e:
               raise ValueError(
                   f"config['pairing']['issued_at'] is not ISO-format: {e}"
               )

       allowlist = value.get("allowlist")
       if allowlist is not None:
           if not isinstance(allowlist, dict):
               raise ValueError(
                   "config['allowlist'] must be a dict with keys "
                   "{'peers', 'channels'}"
               )
           extra = set(allowlist.keys()) - {"peers", "channels"}
           if extra:
               raise ValueError(
                   f"config['allowlist'] has unexpected keys: {sorted(extra)}"
               )
           missing = {"peers", "channels"} - set(allowlist.keys())
           if missing:
               raise ValueError(
                   f"config['allowlist'] is missing required keys: {sorted(missing)}"
               )
           for key in ("peers", "channels"):
               entries = allowlist[key]
               if not isinstance(entries, list):
                   raise ValueError(
                       f"config['allowlist'][{key!r}] must be a list of strings"
                   )
               for i, item in enumerate(entries):
                   if not isinstance(item, str):
                       raise ValueError(
                           f"config['allowlist'][{key!r}][{i}] must be a string"
                       )

       return value
   ```

2. **NO change to `the_one/db/repositories.py`** — confirm by running the existing `TestConnectorAccountRepository` test suite and the new `TestConnectorAccountConfigValidator` tests; the repository's `_row_to_model` direct-kwargs construction exercises the validator transparently because Pydantic v2's `BaseModel.__init__` runs `@field_validator`. Document this in the validator docstring (above).

3. **NO change to `the_one/interfaces/web/api.py`** — the existing `model_validate` calls already exercise the validator. The 422 error handling at L2155 / L2219 catches `ValidationError` and surfaces operator-facing detail.

4. **Append the test class** `TestConnectorAccountConfigValidator` to `tests/test_db_repositories.py` after `TestConnectorAccountRepository`. Use the existing `connector_repo` fixture for round-trip tests; pure-model tests can construct `ConnectorAccount(...)` directly without a repo. Test method shape:

   ```python
   class TestConnectorAccountConfigValidator:
       """F6 L1b — config["pairing"] + config["allowlist"] schema."""

       # --- Direct-construction (model-only) tests ---

       def test_empty_config_is_unchanged(self) -> None:
           account = ConnectorAccount(id="a", name="n", type="stub")
           assert account.config == {}

       def test_non_reserved_keys_pass_through(self) -> None:
           account = ConnectorAccount(
               id="a", name="n", type="stub",
               config={"intent": "guild_messages", "version": 2},
           )
           assert account.config == {"intent": "guild_messages", "version": 2}

       def test_valid_pairing_round_trips(self) -> None:
           pairing = {"code": "abc-123", "issued_at": "2026-05-18T00:00:00Z"}
           account = ConnectorAccount(
               id="a", name="n", type="stub", config={"pairing": pairing}
           )
           assert account.config["pairing"] == pairing

       def test_valid_allowlist_round_trips(self) -> None:
           allowlist = {"peers": ["u1", "u2"], "channels": ["c1"]}
           account = ConnectorAccount(
               id="a", name="n", type="stub", config={"allowlist": allowlist}
           )
           assert account.config["allowlist"] == allowlist

       def test_empty_allowlist_is_preserved_verbatim(self) -> None:
           """Distinct from absent allowlist: empty lists mean lockdown."""
           account = ConnectorAccount(
               id="a", name="n", type="stub",
               config={"allowlist": {"peers": [], "channels": []}},
           )
           assert account.config["allowlist"] == {"peers": [], "channels": []}

       def test_mixed_reserved_and_non_reserved_round_trips(self) -> None:
           config = {
               "pairing": {"code": "x", "issued_at": "2026-05-18T00:00:00Z"},
               "allowlist": {"peers": [], "channels": []},
               "intent": "guild_messages",
           }
           account = ConnectorAccount(
               id="a", name="n", type="stub", config=config
           )
           assert account.config == config

       # --- Pairing malformed shape tests ---

       def test_pairing_must_be_dict(self) -> None:
           with pytest.raises(ValidationError):
               ConnectorAccount(
                   id="a", name="n", type="stub",
                   config={"pairing": "not-a-dict"},
               )

       def test_pairing_missing_code_raises(self) -> None:
           with pytest.raises(ValidationError):
               ConnectorAccount(
                   id="a", name="n", type="stub",
                   config={"pairing": {"issued_at": "2026-05-18T00:00:00Z"}},
               )

       def test_pairing_missing_issued_at_raises(self) -> None:
           with pytest.raises(ValidationError):
               ConnectorAccount(
                   id="a", name="n", type="stub",
                   config={"pairing": {"code": "x"}},
               )

       def test_pairing_extra_key_raises(self) -> None:
           with pytest.raises(ValidationError):
               ConnectorAccount(
                   id="a", name="n", type="stub",
                   config={"pairing": {
                       "code": "x", "issued_at": "2026-05-18T00:00:00Z",
                       "extra": "field",
                   }},
               )

       def test_pairing_empty_code_raises(self) -> None:
           with pytest.raises(ValidationError):
               ConnectorAccount(
                   id="a", name="n", type="stub",
                   config={"pairing": {"code": "", "issued_at": "2026-05-18T00:00:00Z"}},
               )

       def test_pairing_non_string_code_raises(self) -> None:
           with pytest.raises(ValidationError):
               ConnectorAccount(
                   id="a", name="n", type="stub",
                   config={"pairing": {"code": 123, "issued_at": "2026-05-18T00:00:00Z"}},
               )

       def test_pairing_malformed_issued_at_raises(self) -> None:
           with pytest.raises(ValidationError):
               ConnectorAccount(
                   id="a", name="n", type="stub",
                   config={"pairing": {"code": "x", "issued_at": "not-iso"}},
               )

       def test_pairing_date_only_issued_at_raises(self) -> None:
           """date-only strings parse via fromisoformat but lack time
           component — leg-4 Studio writer emits full timestamps.
           """
           with pytest.raises(ValidationError):
               ConnectorAccount(
                   id="a", name="n", type="stub",
                   config={"pairing": {"code": "x", "issued_at": "2026-05-18"}},
               )

       # --- Allowlist malformed shape tests ---

       def test_allowlist_must_be_dict(self) -> None:
           with pytest.raises(ValidationError):
               ConnectorAccount(
                   id="a", name="n", type="stub",
                   config={"allowlist": ["not-a-dict"]},
               )

       def test_allowlist_missing_peers_raises(self) -> None:
           with pytest.raises(ValidationError):
               ConnectorAccount(
                   id="a", name="n", type="stub",
                   config={"allowlist": {"channels": []}},
               )

       def test_allowlist_missing_channels_raises(self) -> None:
           with pytest.raises(ValidationError):
               ConnectorAccount(
                   id="a", name="n", type="stub",
                   config={"allowlist": {"peers": []}},
               )

       def test_allowlist_extra_key_raises(self) -> None:
           with pytest.raises(ValidationError):
               ConnectorAccount(
                   id="a", name="n", type="stub",
                   config={"allowlist": {"peers": [], "channels": [], "extra": []}},
               )

       def test_allowlist_non_list_peers_raises(self) -> None:
           with pytest.raises(ValidationError):
               ConnectorAccount(
                   id="a", name="n", type="stub",
                   config={"allowlist": {"peers": "not-a-list", "channels": []}},
               )

       def test_allowlist_non_string_peer_raises(self) -> None:
           with pytest.raises(ValidationError):
               ConnectorAccount(
                   id="a", name="n", type="stub",
                   config={"allowlist": {"peers": [123], "channels": []}},
               )

       # --- Repository round-trip tests ---

       async def test_pairing_round_trips_through_repo(
           self, connector_repo: ConnectorAccountRepository
       ) -> None:
           pairing = {"code": "abc", "issued_at": "2026-05-18T00:00:00Z"}
           account = ConnectorAccount(
               id="a1", name="n", type="stub", config={"pairing": pairing}
           )
           await connector_repo.create(account)
           loaded = await connector_repo.get("a1")
           assert loaded.config["pairing"] == pairing

       async def test_allowlist_round_trips_through_repo(
           self, connector_repo: ConnectorAccountRepository
       ) -> None:
           allowlist = {"peers": ["u1"], "channels": ["c1"]}
           account = ConnectorAccount(
               id="a1", name="n", type="stub", config={"allowlist": allowlist}
           )
           await connector_repo.create(account)
           loaded = await connector_repo.get("a1")
           assert loaded.config["allowlist"] == allowlist

       async def test_empty_allowlist_round_trips_through_repo(
           self, connector_repo: ConnectorAccountRepository
       ) -> None:
           """Empty-allowlist lockdown survives DB round-trip — does NOT
           become absent. Leg-4 Studio UI relies on this invariant.
           """
           empty = {"peers": [], "channels": []}
           account = ConnectorAccount(
               id="a1", name="n", type="stub", config={"allowlist": empty}
           )
           await connector_repo.create(account)
           loaded = await connector_repo.get("a1")
           assert loaded.config["allowlist"] == empty
           assert "allowlist" in loaded.config  # not erased

       async def test_empty_allowlist_stored_as_lists_not_null(
           self, connector_repo: ConnectorAccountRepository
       ) -> None:
           """Pin the storage-layer invariant — empty lists are stored
           literally as ``[]`` in the JSON column, NOT as ``null`` or
           absent. The Pydantic round-trip proves the model-level
           invariant; this proves the persistence-level invariant. Leg
           4's UI writer reads back through Pydantic, but a raw SQL
           inspection from a future operator tool or migration would
           otherwise be ambiguous.
           """
           import json
           empty = {"peers": [], "channels": []}
           account = ConnectorAccount(
               id="a1", name="n", type="stub", config={"allowlist": empty}
           )
           await connector_repo.create(account)
           async with connector_repo.conn.execute(
               "SELECT config FROM connector_accounts WHERE id = ?", ("a1",)
           ) as cur:
               row = await cur.fetchone()
           raw = json.loads(row["config"])
           assert raw == {"allowlist": {"peers": [], "channels": []}}
           # JSON null would deserialize as None; absent key would mean
           # "allowlist" not in raw. Neither is the case.
           assert raw["allowlist"]["peers"] == []
           assert raw["allowlist"]["channels"] == []

       async def test_validator_fires_on_repo_read_path(
           self, connector_repo: ConnectorAccountRepository
       ) -> None:
           """Hand-write a malformed config — read MUST raise.

           Confirms the cycle-1 H2 concern is closed: Pydantic v2 fires
           ``@field_validator`` on direct ``BaseModel(**kwargs)`` (which
           is what ``_row_to_model`` does), so the read path is validated.

           Implementation: create a VALID row through the repository
           (so secrets ciphertext is well-formed), then UPDATE the
           ``config`` column with malformed JSON via raw SQL. This
           bypasses the model validator on write while leaving the
           secrets ciphertext intact so the read path reaches
           ``_validate_config_reserved_keys`` and raises there (not
           on secrets-decrypt).
           """
           import json
           account = ConnectorAccount(
               id="bad", name="n", type="stub", secrets={"TOKEN": "x"}
           )
           await connector_repo.create(account)
           malformed = json.dumps({"pairing": {"code": ""}})  # missing issued_at + empty code
           await connector_repo.conn.execute(
               "UPDATE connector_accounts SET config = ? WHERE id = ?",
               (malformed, "bad"),
           )
           await connector_repo.conn.commit()
           with pytest.raises(ValidationError):
               await connector_repo.get("bad")
   ```

   Note: the imports at the top of `tests/test_db_repositories.py` already include `ConnectorAccount`, `ConnectorAccountRepository`, and the `connector_repo` fixture (via L84). Add `from pydantic import ValidationError` (verify it is not already imported). The repository-level read-path test creates a valid row via the repository, then UPDATEs only the `config` column with malformed JSON via raw SQL — this keeps the secrets ciphertext well-formed so the read reaches the config validator. The `connector_repo.conn` accessor pattern is the existing convention (cited at L539 of the same file).

5. **Verify the validator fires on both paths** during testing — confirm by running the test class above; in particular `test_validator_fires_on_repo_read_path` is the explicit cycle-1 H2 closure assertion.

6. **Update the flight log** with a leg-1b entry under "## Leg Progress" capturing: shape contracts, the cycle-1 H2 closure (Pydantic v2 runs validators on direct construction), the empty-allowlist-preservation invariant for leg-4 UI consumers, and test counts.

7. **Set leg status to `landed`** at end of implementation. DO NOT commit (deferred-batched workflow).

## Edge Cases

- **Pydantic v2 `mode="after"` vs `mode="before"`**: the existing precedent uses default mode (effectively `mode="after"`). After-mode means the field has already been parsed to a dict by Pydantic; the validator's job is structural validation. Before-mode would receive raw input (which could be a JSON string) — irrelevant here because `config` is `dict[str, Any]` and Pydantic doesn't auto-parse JSON strings.
- **Non-dict `config` is rejected at the field-level type check, NOT by the new validator** — `ConnectorAccount(..., config="not-a-dict")` raises `ValidationError` from Pydantic's `dict[str, Any]` enforcement before `_validate_config_reserved_keys` runs. No separate test is needed for that case. Only the reserved-key sub-shapes are this validator's responsibility.
- **API PUT semantics for "clear allowlist back to default-permit"**: the existing PUT handler at `interfaces/web/api.py:2215-2218` does `merged = existing.model_dump(); merged.update(data); ConnectorAccount.model_validate(merged)`. `dict.update` is shallow at the top level, so if the operator sends `{"config": {"intent": "X"}}` with no `allowlist` key, the merged `config` will REPLACE the existing `config` entirely (the new dict has no `allowlist`, the merge sets `merged["config"]` to that new dict, allowlist is gone). To clear an allowlist while keeping other config keys, the operator sends the full config minus the allowlist key. The leg-4 Studio writer is the operator-facing surface that must compose this correctly; the model-level validator is silent on intent (it doesn't differentiate "operator cleared" from "operator never set"). Documented here so leg-4 design accounts for it.
- **Existing rows with `config={}`**: the most common shape in test fixtures (`ConnectorAccount(id="a", name="n", type="stub")` defaults `config` to `{}`). Validator sees `{}.get("pairing")` and `{}.get("allowlist")` both as `None`, returns unchanged. No false-positive failures.
- **`config={"pairing": null}`** (JSON `null` materialized as Python `None`): `.get("pairing")` returns `None`, validator branches into the `if pairing is not None` guard and skips validation. This is permissive — an operator who explicitly nulls out the pairing key effectively un-pairs the account. Document in the docstring. (Whether the leg-4 Studio UI ever emits `null` rather than absent is a UI-leg call; both produce the same semantics here.)
- **Whitespace-only `code`**: `"   "` is a non-empty string; the validator does NOT trim. If the operator pastes a code with leading/trailing whitespace, it's stored as-is and the dispatcher in leg 2 compares verbatim. Document in the docstring. (Trimming is a leg-4 Studio-form concern, not a model-validation concern.)
- **ISO timestamp with timezone offset vs UTC `Z`**: `datetime.fromisoformat` in Python 3.11+ accepts `"2026-05-18T00:00:00+00:00"` and (with the `.replace("Z", "+00:00")` shim) `"2026-05-18T00:00:00Z"`. Both round-trip cleanly. Do NOT normalize the stored value — preserve the operator-supplied form verbatim (audit-trail concern; the dispatcher in leg 2 only does presence + freshness checks, not bit-for-bit timestamp comparison).
- **`allowlist` with duplicate entries**: `{"peers": ["u1", "u1"]}` is structurally valid (`list[str]`). The validator does NOT de-duplicate. Leg 2's dispatcher compares membership with `in`, so duplicates are inert. Document this; the leg-4 Studio UI may de-duplicate on save as a UX touch but the model does not enforce.
- **Concurrent updates that touch `config`**: the repository's `update()` does a fresh SQL UPDATE on the entire `config` JSON column. Two concurrent operators editing the same account's allowlist will see last-writer-wins. This is the existing behavior; leg 1b does not change it. Documented (and a leg-4 / leg-7 concern if optimistic concurrency becomes desirable).
- **Existing API tests for the connector accounts CRUD path**: `tests/test_connector_accounts_api.py` (or wherever it lives — verify before edit) exercises the API edges. Those tests use stub fixtures with `config={"intent": ...}` and should pass byte-identically. Confirm by running the existing test file first as a regression baseline.
- **F4 L5's `connector_account_ids` substrate is orthogonal**: this leg does NOT touch agent-side config. Per-agent ACLs ship in leg 1c on `AgentConfig.connector_acls`. The two persistence layers compose by referring to the same `account_id` from each side.
- **Encryption boundary**: the pairing CODE is stored in plaintext `config`, NOT in encrypted `secrets`. Rationale: the code is a one-time low-entropy shared secret meant to gate first-contact; it doesn't carry the lifetime threat model of an API token. The operator regenerates it freely. Document this in the validator docstring AND in the leg-4 Studio surface design (when leg 4 is planned). Cycle-2 architect / HAT may surface this — if a follow-up wants the code in `secrets`, the migration shape is well-understood (move the key, update legs 2/3 readers, update leg-4 writer). Not in F6 scope.

## Files Affected

- `the_one/db/models.py` — add `_validate_config_reserved_keys` field validator to `ConnectorAccount` (one new classmethod with full docstring; ~80 lines)
- `tests/test_db_repositories.py` — append `TestConnectorAccountConfigValidator` class (~22 test methods covering direct construction, repository round-trip, malformed shapes, empty-allowlist preservation, and the cycle-1 H2 read-path closure assertion)
- `the_one/db/repositories.py` — UNCHANGED
- `the_one/interfaces/web/api.py` — UNCHANGED
- `the_one/connectors/base.py` — UNCHANGED (leg 1a's surface is sufficient for legs 2/3 to read; leg 1b's persistence is data they read)
- `the_one/connectors/_stub.py` — UNCHANGED
- The flight log gains a leg-1b entry under "## Leg Progress" (handled by the implementing agent)

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[HANDOFF:review-needed]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `landed` (in this file's header) — NOT `completed` (the batched commit at flight end advances to `completed`)
- [ ] Do NOT modify flight.md (the leg checkbox is ticked at batched commit time, not now)
- [ ] Do NOT commit (deferred-batched workflow — Flight Director batches review + commit after the last autonomous leg)

## Citation Audit

Citations verified against current code at leg design time:
- `the_one/db/models.py:118-186` — confirmed (`ConnectorAccount` model with existing validators)
- `the_one/db/models.py:141-159` — confirmed (`_validate_idle_timeout_seconds` precedent)
- `the_one/db/models.py:161-186` — confirmed (`_validate_session_continuation_seconds` precedent)
- `the_one/db/repositories.py:458-570` — confirmed (`ConnectorAccountRepository` + `_row_to_model` at L559)
- `the_one/interfaces/web/api.py:2148-2167` — confirmed (POST handler uses `model_validate`)
- `the_one/interfaces/web/api.py:2169-2240` — confirmed (PUT handler uses `model_validate` at L2218)
- `the_one/interfaces/web/api.py:2087-2104` — confirmed (`_connector_account_response`; not touched in leg 1b)
- `tests/test_db_repositories.py:462+` — confirmed (`TestConnectorAccountRepository`)
- `tests/test_db_repositories.py:84` — confirmed (`connector_repo` fixture)
- Leg 1a artifact at `legs/01a-allowlist-resolver-hook-and-outcomes.md` (status `landed`) — confirmed

All 10 citations verified clean.
