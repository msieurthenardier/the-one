# Leg: routing-schema-and-acl-extraction

**Status**: landed
**Flight**: [Multi-Agent Routing and the Platform-Side Command Surface](../flight.md)

## Objective

Land two routing primitives in one leg: (i) extend `ConnectorAccount`'s Pydantic validator `_validate_config_reserved_keys` at `the_one/db/models.py:190` to recognize a third reserved key `config["routing"]` with shape `{"rules": list[RoutingRule], "default": str | None}`; (ii) extract per-agent ACL admission from `the_one/tools/connector_send.py:144-217` into a new module `the_one/connectors/_acl.py` exporting two pure functions `admits_outbound(...)` and `admits_inbound(...)` — the latter is new and consumed by L5's dispatcher. F6 outbound caller becomes a one-line delegation; F6 outbound tests pass byte-identically. No schema migration.

## Context

This is the second F7 leg. Per Design Decisions in `flight.md`:

- **"Account-config persistence with ordered rule list"** — routing rides on the existing `config: dict[str, Any]` JSON column under reserved key `config["routing"]`. Same pattern as F6's `config["allowlist"]` and `config["pairing"]`. Shape:
  ```python
  config["routing"] = {
      "rules": [
          {"scope": "channel", "match": "<channel_id>", "agent": "<slug>"},
          # ... in operator-declared order ...
      ],
      "default": "<slug>" | None,
  }
  ```
- **"ACL admission as pure function — pre-commit to extracting `connectors/_acl.py`"** — the F6 outbound check at `tools/connector_send.py:144-217` is two layers: account-scope channels (HAT-redesigned semantic: empty list = unrestricted) and per-agent channels (tri-state: `None` = inherit, `[]` = DMs-only fail-closed, `[items]` = subset). L2 lifts this into a pure function and adds the symmetric inbound counterpart covering both peers and channels axes.
- **ACL-section scope clarification** — the F6 outbound ACL section spans `tools/connector_send.py:167-217`. Lines `137-166` (target-shape validation + account-id check + account fetch) are the PRELUDE and STAY in `connector_send.py`. Lines `167-217` are the two ACL layers (account-scope channels at 167-184; per-agent channels at 185-217) that move to `_acl.py`.
- **L2 unblocks L3 / L4 / L5** — the routing engine (L4) needs the routing schema to exist; the dispatcher integration (L5) needs the inbound ACL pure function. Without both primitives in place, L4 / L5 design becomes speculative.
- **Module name** — the leg picks `connectors/_acl.py` over `_admission.py` because the project already uses "ACL" nomenclature (`AgentConfig.connector_acls`, `connectors/README.md §4` uses "ACL-aware"). Consistency wins.
- **Per-axis semantic framing — narrowing vs defaulting**. `admits_inbound`'s per-agent peers axis treats `[]` as deny ("no peer admitted via this agent"), while account-scope peers treats `[]` as permit ("unrestricted"). This is deliberate, not a copy-paste accident. The framing: **per-agent axes are NARROWING modifiers** (`None` inherits account-scope, non-empty narrows to the listed items, `[]` is the strongest narrowing signal — "no items"); **account-scope axes are DEFAULTING anchors** (`[]` = "no explicit list" = unrestricted; F6 HAT-redesign locked this in). Symmetric application: per-agent `channels = []` is DMs-only fail-closed (channels-axis "no items" signal); per-agent `peers = []` is "no peer admitted" (peers-axis "no items" signal). The asymmetry between scopes is the framing; the symmetry within per-agent is the consistency. The leg pins this with a dedicated test (`test_account_scope_peers_empty_is_unrestricted_but_per_agent_peers_empty_is_deny`) so any future "let's unify" refactor breaks the test rather than silently flipping behavior.
- **Reason-string vocabulary** — outbound channel reasons use the verb **"reachable"** (verbatim from F6 — locked by exact-equality assertions in `tests/test_connector_send_tool.py`). Inbound reasons (new in this leg) use the verb **"admitted"**. The divergence is a F6-back-compat constraint, not a vocabulary preference — `_acl.py`'s module docstring documents this so L5's audit-log code can pick one verb deliberately and stay consistent. If a future leg wants vocabulary unification, the cost is updating the F6 outbound regression assertions; the cost is mechanical and contained.

Key learnings from prior legs (from the flight log):

- F6's HAT redesign flipped the "empty list" semantic: pre-redesign `allowlist.channels = []` denied everyone; post-redesign it permits everyone on that axis. The lifted code keeps the post-HAT semantic — byte-identical to current behavior.
- Per-axis tri-state is the source of truth: `None` = inherit, `[]` = explicit-empty (semantic varies by scope), `[items]` = subset.
- `tools/connector_send.py:151-154` uses function-local imports to break a connectors→db cycle; `_acl.py` is in `connectors/` and consults `ConnectorAccount` and `AgentConfig` shapes via type-only access — no runtime imports of repositories. The cycle-break stays local to `connector_send.py`'s call sites.

## Inputs

What exists before this leg runs:

- `the_one/db/models.py:188-317` — `ConnectorAccount._validate_config_reserved_keys` handling `pairing` and `allowlist` reserved keys. The validator returns the unchanged `value` after validation (shape-only enforcement).
- `the_one/tools/connector_send.py:167-217` — F6 outbound ACL check (account-scope channels at 167-184; per-agent channels at 185-217). The 137-166 prelude (target validation + account-id check + account fetch) is NOT moved.
- `the_one/agent/config.py:184` + `:189-240` — `AgentConfig.connector_acls: dict[str, dict[str, list[str] | None]] | None` and its validator; the per-agent ACL shape is `{"peers": list[str] | None, "channels": list[str] | None}` per-account.
- F1–F7 (post-L1) test suite green: `docker exec the-one pytest tests/test_connectors*.py -x --timeout 30` returns 166 passed.
- No existing `_acl.py`, `_admission.py`, `admits_outbound`, `admits_inbound`, or `routing` config-key references in `the_one/` or `tests/` (grep verified — only the L1-landed forward-references mention F7 routing).

## Outputs

What exists after this leg completes:

- `the_one/db/models.py` with `_validate_config_reserved_keys` extended to validate `config["routing"]` shape.
- `the_one/connectors/_acl.py` (NEW) exporting `admits_outbound(account, agent_acl, channel_id) -> tuple[bool, str]` and `admits_inbound(account, agent_acl, peer_id, channel_id) -> tuple[bool, str]`. Pure functions; no I/O.
- `the_one/tools/connector_send.py` with the ACL section replaced by a one-line delegation to `admits_outbound`; behavior byte-identical to F6.
- `tests/test_connectors_routing_schema.py` (NEW) pinning the routing-key validator's shape contract.
- `tests/test_connectors_acl.py` (NEW) pinning both pure functions across the per-axis tri-state matrix.
- F1–F7 (post-L1) regression suite passes byte-identically including all F6 outbound tests in `test_connector_send_tool.py`.

## Acceptance Criteria

- [ ] `the_one/db/models.py:_validate_config_reserved_keys` recognizes `config["routing"]` as a third reserved key alongside `pairing` and `allowlist`. Shape contract:
  - `value.get("routing")` is `None`-tolerant (`None` or absent both treated as "no routing config").
  - When present, `routing` MUST be a dict with EXACTLY the keys `{"rules", "default"}` (no extra keys, no missing keys).
  - `routing["rules"]` MUST be a list (empty list IS valid). Each entry MUST be a dict with EXACTLY the keys `{"scope", "match", "agent"}`.
  - `routing["rules"][i]["scope"]` MUST be one of `{"channel", "thread", "dm", "peer"}` (case-sensitive). Any other string rejects.
  - `routing["rules"][i]["match"]` MUST be a non-empty string.
  - `routing["rules"][i]["agent"]` MUST be a non-empty string. (Slug-shape validation is NOT enforced here — operator may reference an agent that doesn't yet exist; the routing engine in L4 handles unreachable agents via fallback. Matches the F6 pattern where `allowlist.peers` carries opaque peer_id strings.)
  - `routing["default"]` MUST be either `None` or a non-empty string.
  - The validator returns `value` unchanged after validation (shape-only, no normalization).
- [ ] `the_one/connectors/_acl.py` ships and exports:
  - `admits_outbound(account: ConnectorAccount, agent_acl: dict[str, list[str] | None] | None, channel_id: str) -> tuple[bool, str]`. Behavior MUST match the current `tools/connector_send.py:167-217` outbound check byte-identically:
    - Account-scope `allowlist.channels`: absent / `[]` → unrestricted; non-empty list → `channel_id` must be in the list.
    - Per-agent `agent_acl["channels"]`: `None` (or `agent_acl is None`) → inherit account-scope; `[]` → DMs-only fail-closed (F8-deferred); non-empty list → `channel_id` must be in the list.
    - Returns `(True, "")` on admit; `(False, reason)` on deny. Reason strings match the existing error messages in `connector_send.py` verbatim so existing tests that assert on those strings continue to pass.
  - `admits_inbound(account: ConnectorAccount, agent_acl: dict[str, list[str] | None] | None, peer_id: str, channel_id: str) -> tuple[bool, str]`. New function. Behavior:
    - Account-scope `allowlist.peers`: absent / `[]` → unrestricted; non-empty list → `peer_id` must be in the list.
    - Account-scope `allowlist.channels`: absent / `[]` → unrestricted; non-empty list → `channel_id` must be in the list.
    - Per-agent `agent_acl["peers"]`: `None` (or `agent_acl is None`) → inherit account-scope; `[]` → no peer is admitted via this agent on this account (explicit-empty peers axis denies — symmetric to channels' DMs-only semantic but for peers, "explicit empty = deny" matches operator intent of "I've cleared the per-agent peer list, that means no peers"; this is the F6 HAT-redesign analog on the peers axis); non-empty list → `peer_id` must be in the list.
    - Per-agent `agent_acl["channels"]`: `None` → inherit account-scope; `[]` → DMs-only sentinel; non-empty list → `channel_id` must be in the list.
    - Both axes (peers AND channels) MUST permit for the function to return `(True, "")`. Returns `(False, reason)` on first deny.
- [ ] `the_one/tools/connector_send.py` ACL section (lines 167-217 — the two ACL layers; the 137-166 prelude STAYS) replaced by:
  - The account-id-not-attached / account-not-found / target-shape-validation prelude STAYS (those are not ACL concerns).
  - The account-scope channels check + per-agent channels check are replaced by `admits, reason = admits_outbound(account, self._connector_acls.get(account_id) if self._connector_acls else None, channel_id)`. If `not admits`, return the `reason` formatted with the existing `[error] [constraint] ...` envelope.
  - The function-local import block at `connector_send.py:151-154` STAYS (still consults `ConnectorAccount` and `AgentConfig` repositories).
  - All existing F6 outbound test assertions (deny reasons, OK responses) pass byte-identically.
- [ ] `tests/test_connectors_routing_schema.py` (NEW) lands and passes:
  - Valid full shape round-trip — model-validate then re-emit, byte-equal.
  - `routing = None` accepted (treated as absent).
  - `routing = {}` rejected (missing `rules` and `default`).
  - `routing = {"rules": []}` rejected (missing `default`); `routing = {"rules": [], "default": None}` accepted (valid empty-rules empty-default).
  - Extra top-level keys in `routing` rejected.
  - Each rule's missing/extra/wrong-type keys rejected (scope-not-string, scope-not-in-enum, match-not-string, match-empty, agent-not-string, agent-empty).
  - Every valid scope value (`channel`, `thread`, `dm`, `peer`) accepted; one invalid (`group`, `Channel`, etc.) rejected.
  - `default = None` accepted; `default = ""` rejected; `default = "alice"` accepted.
- [ ] `tests/test_connectors_acl.py` (NEW) lands and passes:
  - For each function (`admits_outbound`, `admits_inbound`): per-axis tri-state matrix — `None`, `[]`, `[items]` at both account-scope and per-agent levels.
  - Outbound parity: every reason string returned by `admits_outbound` is an exact match to what `connector_send.py` formerly returned for the same input.
  - DMs-only sentinel: per-agent `channels = []` → `admits_outbound` returns deny with the "DMs-only override; DM classification lands in F8" reason verbatim.
  - **Asymmetry pin**: dedicated test `test_account_scope_peers_empty_is_unrestricted_but_per_agent_peers_empty_is_deny` for `admits_inbound` — proves account-scope `allowlist.peers = []` admits any peer, while per-agent `agent_acl["peers"] = []` denies. This pins the per-axis-semantic-framing decision against silent unification.
  - **`agent_acl = {}` equivalence pin**: required (not optional) — `admits_outbound(account, {}, channel)` returns the same `(bool, reason)` as `admits_outbound(account, None, channel)`; same for `admits_inbound`.
  - Account-not-attached / target-shape-validation cases are NOT in this test file (those stay in `test_connector_send_tool.py` because they precede the ACL check).
- [ ] F1–F7 (post-L1) regression suite passes byte-identically:
  ```
  docker exec the-one sh -c 'pytest tests/test_connectors*.py -x --timeout 30'
  ```
  Including `test_connector_send_tool.py` which exercises F6's outbound ACL paths and pins the reason strings via EXACT-EQUALITY (`==`) assertions at lines 661-664, 692-695, 742-746 (not substring / regex). The leg MUST preserve the F6 outbound reason strings verbatim — any character drift breaks regression.
- [ ] No new files outside `the_one/connectors/_acl.py`, `tests/test_connectors_routing_schema.py`, `tests/test_connectors_acl.py`. No schema migration. No new entries in `__all__` of `the_one/connectors/__init__.py` (the pure functions are private to the connector subsystem; their canonical imports are `from the_one.connectors._acl import admits_outbound, admits_inbound`).

## Verification Steps

How to confirm each criterion is met:

**Routing-schema validator** (in `tests/test_connectors_routing_schema.py`):

- Valid round-trip: build a `ConnectorAccount` with `config={"routing": {"rules": [{"scope": "channel", "match": "C1", "agent": "alice"}], "default": "bob"}}`; `.config["routing"]` equals the input verbatim.
- `routing = None`: build a `ConnectorAccount` with `config={"routing": None}`; validator returns without error.
- `routing = {}`: ValueError raised mentioning missing required keys `["default", "rules"]`.
- `routing = {"rules": [], "default": None}`: accepted; empty rules + null default is valid.
- Extra key: `routing = {"rules": [], "default": None, "extra": "x"}` → ValueError mentioning extra keys.
- Per-rule shape:
  - `{"scope": "channel", "match": "C1", "agent": "a"}` → valid.
  - `{"scope": "Channel", "match": "C1", "agent": "a"}` → ValueError (case-sensitive).
  - `{"scope": "group", "match": "C1", "agent": "a"}` → ValueError (not in enum).
  - `{"scope": "channel", "match": "", "agent": "a"}` → ValueError (empty match).
  - `{"scope": "channel", "match": "C1", "agent": ""}` → ValueError (empty agent).
  - Missing field: `{"scope": "channel", "match": "C1"}` → ValueError.
  - Extra field: `{"scope": "channel", "match": "C1", "agent": "a", "extra": "x"}` → ValueError.
- `default`:
  - `default = None` → accepted.
  - `default = "alice"` → accepted.
  - `default = ""` → ValueError.
  - `default = 42` → ValueError.

**ACL pure functions** (in `tests/test_connectors_acl.py`):

For `admits_outbound`:
- Account-scope channels:
  - `allowlist` absent → `(True, "")` regardless of channel.
  - `allowlist.channels = []` → `(True, "")` regardless of channel.
  - `allowlist.channels = ["C1"]`, channel `"C1"` → `(True, "")`.
  - `allowlist.channels = ["C1"]`, channel `"C2"` → `(False, "channel_id 'C2' is not reachable on account 'acc-1'")`.
- Per-agent channels (with permissive account-scope):
  - `agent_acl is None` → inherit; `(True, "")`.
  - `agent_acl = {"peers": None, "channels": None}` → inherit; `(True, "")`.
  - `agent_acl = {"peers": None, "channels": []}` → DMs-only fail-closed; `(False, "channel_id 'C1' is not reachable for this agent on account 'acc-1' (DMs-only override; DM classification lands in F8)")`.
  - `agent_acl = {"peers": None, "channels": ["C1"]}`, channel `"C1"` → `(True, "")`.
  - `agent_acl = {"peers": None, "channels": ["C1"]}`, channel `"C2"` → `(False, ...)`.
- Intersection: account-scope `["C1", "C2"]` + per-agent `["C2"]`, channel `"C2"` → `(True, "")`; channel `"C1"` → `(False, ...)` (per-agent narrows further).

For `admits_inbound`:
- Account-scope peers (account-scope channels permissive):
  - `allowlist` absent → `(True, "")` regardless of peer.
  - `allowlist.peers = []` → `(True, "")` regardless of peer.
  - `allowlist.peers = ["P1"]`, peer `"P1"` → `(True, "")`.
  - `allowlist.peers = ["P1"]`, peer `"P2"` → `(False, "peer_id 'P2' is not admitted on account 'acc-1'")`.
- Account-scope channels (account-scope peers permissive):
  - Same matrix as outbound channel cases above; reason string format `"channel_id 'CX' is not admitted on account 'acc-1'"` (inbound uses "admitted", outbound uses "reachable" — preserves the existing outbound reason verbatim; the inbound axis is a new reason format).
- Per-agent peers (with permissive account-scope and channels):
  - `agent_acl is None` → inherit; `(True, "")`.
  - `agent_acl = {"peers": None, "channels": None}` → inherit; `(True, "")`.
  - `agent_acl = {"peers": [], "channels": None}` → explicit-empty peers axis denies; `(False, "peer_id 'P1' is not admitted for this agent on account 'acc-1' (per-agent peers axis is explicitly empty)")`.
  - `agent_acl = {"peers": ["P1"], "channels": None}`, peer `"P1"` → `(True, "")`.
  - `agent_acl = {"peers": ["P1"], "channels": None}`, peer `"P2"` → `(False, "peer_id 'P2' is not admitted for this agent on account 'acc-1'")`.
- Per-agent channels (with permissive account-scope and peers):
  - Same matrix as outbound, but the F8-DMs-only reason for `[]` MAY have the same wording or an inbound-tailored variant; the leg artifact picks the SAME reason string as outbound for cross-axis consistency: `"channel_id 'C1' is not admitted for this agent on account 'acc-1' (DMs-only override; DM classification lands in F8)"`.
- Both axes denied: deny on first axis encountered (peers checked first, then channels); reason reflects the first-denied axis. The test pins peers-first ordering.

**Outbound parity regression**:
- Run `docker exec the-one sh -c 'pytest tests/test_connector_send_tool.py -x --timeout 30 -v'`. Every test that asserts on a `[error] [constraint] ...` reason continues to pass — the leg MUST preserve the existing outbound reasons verbatim.
- Spot-check by greppin: `grep -n "is not reachable\|DMs-only override\|DM classification lands in F8" tests/` — count matches against the pre-edit count.

**Forward-reference / regression**:
- `grep -nE "_acl|admits_outbound|admits_inbound" the_one/connectors/_acl.py the_one/tools/connector_send.py` confirms the new module is declared and consumed.
- `docker exec the-one sh -c 'pytest tests/test_connectors*.py -x --timeout 30'` — full F1–F7 (post-L1) connector test suite green.

## Implementation Guidance

### 1. Extend `_validate_config_reserved_keys` in `the_one/db/models.py`

Add the `routing` validation block after the existing `allowlist` block (currently ends at line 315). Mirror the existing block's style: nested `isinstance` checks, exact-keys enforcement, per-field type/value enforcement, `raise ValueError` on each violation with operator-readable messages.

```python
# After the allowlist block:

routing = value.get("routing")
if routing is not None:
    if not isinstance(routing, dict):
        raise ValueError(
            "config['routing'] must be a dict with keys {'rules', 'default'}"
        )
    extra = set(routing.keys()) - {"rules", "default"}
    if extra:
        raise ValueError(
            f"config['routing'] has unexpected keys: {sorted(extra)}"
        )
    missing = {"rules", "default"} - set(routing.keys())
    if missing:
        raise ValueError(
            f"config['routing'] is missing required keys: {sorted(missing)}"
        )
    rules = routing["rules"]
    if not isinstance(rules, list):
        raise ValueError(
            "config['routing']['rules'] must be a list"
        )
    _VALID_ROUTING_SCOPES = frozenset({"channel", "thread", "dm", "peer"})
    for i, rule in enumerate(rules):
        if not isinstance(rule, dict):
            raise ValueError(
                f"config['routing']['rules'][{i}] must be a dict with keys "
                f"{{'scope', 'match', 'agent'}}"
            )
        extra = set(rule.keys()) - {"scope", "match", "agent"}
        if extra:
            raise ValueError(
                f"config['routing']['rules'][{i}] has unexpected keys: "
                f"{sorted(extra)}"
            )
        missing = {"scope", "match", "agent"} - set(rule.keys())
        if missing:
            raise ValueError(
                f"config['routing']['rules'][{i}] is missing required keys: "
                f"{sorted(missing)}"
            )
        scope = rule["scope"]
        if not isinstance(scope, str) or scope not in _VALID_ROUTING_SCOPES:
            raise ValueError(
                f"config['routing']['rules'][{i}]['scope'] must be one of "
                f"{sorted(_VALID_ROUTING_SCOPES)}; got {scope!r}"
            )
        match = rule["match"]
        if not isinstance(match, str) or not match:
            raise ValueError(
                f"config['routing']['rules'][{i}]['match'] must be a "
                f"non-empty string"
            )
        agent = rule["agent"]
        if not isinstance(agent, str) or not agent:
            raise ValueError(
                f"config['routing']['rules'][{i}]['agent'] must be a "
                f"non-empty string"
            )
    default = routing["default"]
    if default is not None and (not isinstance(default, str) or not default):
        raise ValueError(
            "config['routing']['default'] must be either None or a "
            "non-empty string"
        )
```

The `_VALID_ROUTING_SCOPES` constant is module-level (NOT nested inside the validator function). Verified: `the_one/db/models.py` currently has zero module-level constants — every top-level item is a `class` definition. The leg adds one constant deliberately, just above the `ConnectorAccount` class, with a one-line comment explaining the hoist:

```python
# Hoisted module-level so the F7 L7 Studio editor (and any future routing UI)
# can import the enum without going through the validator.
_VALID_ROUTING_SCOPES = frozenset({"channel", "thread", "dm", "peer"})
```

This makes the placement choice explicit and survives a "why is this not nested?" code review.

Update `_validate_config_reserved_keys`'s docstring to mention the third reserved key (`routing`) with one-paragraph shape contract:

> - ``config["routing"] = {"rules": list[RoutingRule], "default": str | None}``
>   where ``RoutingRule = {"scope": Literal["channel","thread","dm","peer"], "match": str, "agent": str}``.
>   The rule list is operator-declared order; the routing engine in F7 L4
>   walks it top-to-bottom and the first match wins (Specificity-then-order
>   precedence per F7 design decisions). Empty rule list is permitted.
>   ``default`` is the per-account fallback agent slug; ``None`` means
>   "use first-eligible-attached-agent at routing-engine time."

### 2. New module `the_one/connectors/_acl.py`

```python
"""Per-agent and account-scope ACL admission — pure functions.

M10 F07 L2: extracts the per-axis tri-state admission logic that the
platform-send tool's outbound execute path (F6 L3) had inlined, and
adds the symmetric inbound counterpart that the F7 dispatcher
consumes after picking an agent.

Two functions, both pure (no I/O, no repository access):

- :func:`admits_outbound` — account-scope channels intersected with
  per-agent channels. F6 HAT-redesigned "empty list = unrestricted"
  semantic on the account-scope channels axis. Per-agent
  ``channels: []`` is the DMs-only sentinel (fail-closed pending F8
  DM classification).
- :func:`admits_inbound` — covers BOTH peers AND channels axes at
  both scopes. Designed for use by the dispatcher's per-agent
  admission check.

**Per-axis semantic framing — narrowing vs defaulting** (codifies the
F6 HAT-redesign rule and extends it consistently to the per-agent
peers axis):

- **Account-scope axes are DEFAULTING anchors.** ``allowlist`` absent
  → unrestricted; ``allowlist.{peers,channels} = []`` → unrestricted
  (HAT-redesigned: empty list at this scope means "no explicit list",
  not "explicitly nobody"); non-empty list → subset.
- **Per-agent axes are NARROWING modifiers.** ``None`` → inherit
  account-scope (no narrowing); non-empty list → narrows to listed
  items (intersected with account-scope); ``[]`` → the strongest
  narrowing signal: "no items on this axis." For channels axis: DMs-
  only fail-closed pending F8. For peers axis: no peer admitted via
  this agent on this account.

The asymmetry between scopes for the SAME axis is intentional and
follows the framing — account-scope `[]` means "no explicit list";
per-agent `[]` means "explicitly no items." See M10 F7 L2 leg
artifact for the full rationale and the dedicated regression test.

**Reason-string vocabulary**:

- Outbound channel reasons use the verb **"reachable"** — verbatim
  from F6, locked by exact-equality assertions in
  ``tests/test_connector_send_tool.py``. Cannot be changed without
  updating those tests.
- Inbound reasons (this leg) use the verb **"admitted"**. New
  vocabulary; not back-compat-constrained.

The divergence is a F6-back-compat reality, not a vocabulary
preference. The dispatcher audit-log (F7 L5) and the Studio surfaces
(F7 L7) should pick one verb deliberately and stay consistent.

All deny paths return ``(False, reason)`` where ``reason`` is a
short operator-readable string suitable for embedding into the
``[error] [constraint] ...`` envelope at the call site.
"""

from __future__ import annotations

from the_one.db.models import ConnectorAccount

__all__ = ["admits_outbound", "admits_inbound"]


def admits_outbound(
    account: ConnectorAccount,
    agent_acl: dict[str, list[str] | None] | None,
    channel_id: str,
) -> tuple[bool, str]:
    """Check whether outbound to ``channel_id`` on ``account`` is permitted.

    Returns ``(True, "")`` on admit; ``(False, reason)`` on deny.
    ``reason`` is suitable for embedding directly after the
    ``[error] [constraint] `` envelope prefix.

    Per-axis tri-state per the module docstring. Account-scope channels
    intersected with per-agent channels.
    """
    account_id = account.id
    # Account-scope channels axis.
    allowlist = account.config.get("allowlist")
    if allowlist is not None:
        allowed_channels = allowlist.get("channels", [])
        if allowed_channels and channel_id not in allowed_channels:
            return (
                False,
                f"channel_id {channel_id!r} is not reachable on account "
                f"{account_id!r}",
            )
    # Per-agent channels axis.
    if agent_acl is not None:
        agent_channels = agent_acl.get("channels")
        if agent_channels is None:
            pass  # inherit account-scope
        elif agent_channels == []:
            return (
                False,
                f"channel_id {channel_id!r} is not reachable for this agent "
                f"on account {account_id!r} (DMs-only override; DM "
                f"classification lands in F8)",
            )
        elif channel_id not in agent_channels:
            return (
                False,
                f"channel_id {channel_id!r} is not reachable for this agent "
                f"on account {account_id!r}",
            )
    return True, ""


def admits_inbound(
    account: ConnectorAccount,
    agent_acl: dict[str, list[str] | None] | None,
    peer_id: str,
    channel_id: str,
) -> tuple[bool, str]:
    """Check whether inbound from ``peer_id`` in ``channel_id`` on
    ``account`` is permitted to invoke this agent.

    Returns ``(True, "")`` on admit; ``(False, reason)`` on deny.
    Both axes (peers AND channels) must permit. Peers checked first;
    short-circuit on first deny.

    Used by F7 L5 dispatcher AFTER the routing engine (F7 L4) picks an
    agent, to verify the picked agent's per-agent ACL admits this
    (peer, channel) combination. F6's plugin resolver hook handles
    account-scope first-contact pairing — this function is the
    per-agent admission layer that composes on top.
    """
    account_id = account.id
    # Account-scope peers axis.
    allowlist = account.config.get("allowlist")
    if allowlist is not None:
        allowed_peers = allowlist.get("peers", [])
        if allowed_peers and peer_id not in allowed_peers:
            return (
                False,
                f"peer_id {peer_id!r} is not admitted on account "
                f"{account_id!r}",
            )
        allowed_channels = allowlist.get("channels", [])
        if allowed_channels and channel_id not in allowed_channels:
            return (
                False,
                f"channel_id {channel_id!r} is not admitted on account "
                f"{account_id!r}",
            )
    # Per-agent peers axis.
    if agent_acl is not None:
        agent_peers = agent_acl.get("peers")
        if agent_peers is None:
            pass  # inherit account-scope
        elif agent_peers == []:
            return (
                False,
                f"peer_id {peer_id!r} is not admitted for this agent on "
                f"account {account_id!r} (per-agent peers axis is "
                f"explicitly empty)",
            )
        elif peer_id not in agent_peers:
            return (
                False,
                f"peer_id {peer_id!r} is not admitted for this agent on "
                f"account {account_id!r}",
            )
        # Per-agent channels axis (same shape as outbound).
        agent_channels = agent_acl.get("channels")
        if agent_channels is None:
            pass  # inherit account-scope
        elif agent_channels == []:
            return (
                False,
                f"channel_id {channel_id!r} is not admitted for this agent "
                f"on account {account_id!r} (DMs-only override; DM "
                f"classification lands in F8)",
            )
        elif channel_id not in agent_channels:
            return (
                False,
                f"channel_id {channel_id!r} is not admitted for this agent "
                f"on account {account_id!r}",
            )
    return True, ""
```

### 3. Refactor `the_one/tools/connector_send.py`

Replace lines 167-217 (the two ACL blocks — account-scope channels at 167-184; per-agent channels at 185-217) with a single delegation block. Keep the function-local imports at 151-154 and the account fetch at 156-165. Insert after the account fetch:

```python
        # M10 F7 L2: ACL admission extracted to connectors/_acl.py — single
        # pure function consumed by both outbound (here) and inbound (F7 L5
        # dispatcher). Per-axis tri-state semantic unchanged from F6 L7 HAT.
        from the_one.connectors._acl import admits_outbound

        agent_acl: dict[str, list[str] | None] | None = (
            self._connector_acls.get(account_id)
            if self._connector_acls is not None
            else None
        )
        admits, reason = admits_outbound(account, agent_acl, channel_id)
        if not admits:
            return f"[error] [constraint] {reason}"
```

Update the module docstring at `connector_send.py:1-28` to reference `_acl.py` for the ACL semantic (the inline HAT-redesign note at lines 15-22 stays but should reference `_acl.py` as the canonical home of the pure functions).

### 4. New test file `tests/test_connectors_routing_schema.py`

Style mirrors `tests/test_connectors_resolver.py`: type-level surface tests + inline minimal fixtures.

```python
"""Routing-schema validator tests for F7 L2's extension of
``ConnectorAccount._validate_config_reserved_keys`` to recognize the
third reserved top-level config key ``"routing"``.

Pins the shape contract:
- valid round-trip
- ``routing = None`` accepted
- exact-keys enforcement (no extra; no missing)
- per-rule shape (scope, match, agent — all required, all type-checked)
- scope ∈ {channel, thread, dm, peer} (case-sensitive)
- default ∈ {None, non-empty str}

The routing engine in F7 L4 consumes the validated shape; F7 L5
dispatcher composes with the engine; F7 L7 Studio editor authors
through the API write path. The validator at the model layer is the
single point of contract enforcement.
"""
```

Then `class TestRoutingSchema` with one method per assertion above. Use direct `ConnectorAccount(**kwargs)` construction (Pydantic v2 fires the validator on direct construction; no `model_validate` wrapper needed).

### 5. New test file `tests/test_connectors_acl.py`

Style mirrors `tests/test_connectors_resolver.py`. Inline minimal fixtures: build a tiny `_account(allowlist=None)` helper that constructs a `ConnectorAccount` with the given allowlist, leaving other fields at sensible defaults.

```python
"""ACL pure-function tests for F7 L2's ``connectors/_acl.py`` —
``admits_outbound`` and ``admits_inbound``.

Pins the per-axis tri-state matrix at both scopes (account-scope +
per-agent), plus the DMs-only-channels sentinel and the
explicit-empty-peers-axis deny. Outbound reasons are byte-identical
to what ``tools/connector_send.py`` formerly produced — the F6
``test_connector_send_tool.py`` integration tests continue
to assert on these strings, so any drift here breaks F6 regression.
"""
```

Then `class TestAdmitsOutbound` and `class TestAdmitsInbound` covering the verification matrix above.

### 6. Order of file edits

1. `the_one/db/models.py` (extend validator)
2. `the_one/connectors/_acl.py` (NEW)
3. `the_one/tools/connector_send.py` (refactor — pre-existing tests in `test_connector_send_tool.py` must continue to pass)
4. `tests/test_connectors_routing_schema.py` (NEW)
5. `tests/test_connectors_acl.py` (NEW)
6. Run full regression: `docker exec the-one sh -c 'pytest tests/test_connectors*.py -x --timeout 30'`

### 7. Things NOT in scope for this leg

- Routing-engine logic (L4 — `connectors/_routing.py` is a separate module).
- Dispatcher integration (L5 — wires both routing engine and `admits_inbound` into `_inbound.py`).
- Studio editor (L7).
- Documentation in `agents.md` for the routing convention (L4 or L5 leg as part of routing-engine landing).
- New `__all__` entries in `the_one/connectors/__init__.py` — the pure functions are private to the connector subsystem, accessed via canonical `from the_one.connectors._acl import ...`. Mirror `_pairing.py`'s pattern (private module; not re-exported from `__init__.py`).

## Edge Cases

- **`agent_acl is None` vs `agent_acl = {}`**: both should mean "no per-agent narrowing." The `admits_outbound` / `admits_inbound` early-return on `agent_acl is None` covers the `None` case; for `agent_acl = {}`, the `.get("channels")` / `.get("peers")` returns `None` which hits the "inherit" branch. Both paths produce identical results. (Optional explicit test: `admits_outbound(account, {}, "C1")` returns same as `admits_outbound(account, None, "C1")`.)
- **`allowlist = None`** (JSON `null` from the validator's perspective): `account.config.get("allowlist")` returns `None`; the `if allowlist is not None:` guard skips the block; account-scope is unrestricted on both axes. This is the operator-cleared-allowlist case — must continue to permit.
- **`account.config = {}`** (no allowlist key at all): same as `allowlist = None` via `.get` semantics.
- **`agent_acl["peers"]` present but `agent_acl["channels"]` absent**: the validator at `agent/config.py:_validate_connector_acls` requires BOTH keys present; this case should be impossible at runtime. The pure functions defensively `.get(...)` so they don't KeyError, but no test covers the validator-impossible path (it would be testing the validator, not the pure function).
- **Account-scope `allowlist.channels = []`**: HAT-redesigned semantic → unrestricted. Confirmed in both pure functions. Outbound test confirms this (one of the F6 regression cases). Inbound test must mirror.
- **Reason string drift**: the outbound reason strings (`"channel_id 'C1' is not reachable..."` etc.) are checked by F6 integration tests at `tests/test_connector_send_tool.py:661-664, 692-695, 742-746` via EXACT-EQUALITY assertions (`result == "[error] [constraint] ..."`). The leg MUST preserve them character-by-character. F6's current outbound strings are concatenated f-strings; the leg's `_acl.py` reproductions are also concatenated f-strings — the final concatenated string is what matters. Implementer should before-and-after grep for the literal substrings `is not reachable on account`, `is not reachable for this agent on account`, and `DMs-only override; DM classification lands in F8` and confirm they all still appear at the call site in `connector_send.py` (now indirectly via `admits_outbound`'s return) producing the same final envelope.
- **`admits_inbound` peers-first ordering**: when both peers and channels would deny, the function short-circuits on peers. This is a test invariant (pin it), not a UX-critical choice — the dispatcher's audit log records whichever axis denied first. If the dispatcher's UX would benefit from "report both axis denies" later, refactor the function's signature to return a list of reasons; L2 ships the single-reason form for parity with `admits_outbound`.

## Files Affected

- `the_one/db/models.py` — extend `_validate_config_reserved_keys` for `config["routing"]`; add module-level `_VALID_ROUTING_SCOPES` constant; update validator docstring.
- `the_one/connectors/_acl.py` (NEW) — `admits_outbound` + `admits_inbound` pure functions.
- `the_one/tools/connector_send.py` — replace the ACL section (lines 167-217) with a one-line delegation to `admits_outbound`; update module docstring to reference `_acl.py`.
- `tests/test_connectors_routing_schema.py` (NEW) — pin routing-key validator's shape contract.
- `tests/test_connectors_acl.py` (NEW) — pin both pure functions across the per-axis tri-state matrix.

---

## Post-Completion Checklist

**Complete ALL steps before signaling `[COMPLETE:leg]`:**

- [ ] All acceptance criteria verified
- [ ] Tests passing
- [ ] Update flight-log.md with leg progress entry
- [ ] Set this leg's status to `completed` (in this file's header)
- [ ] Check off this leg in flight.md
- [ ] If final leg of flight:
  - [ ] Update flight.md status to `landed`
  - [ ] Check off flight in mission.md
- [ ] Commit all changes together (code + artifacts)

## Citation Audit

Citations verified against current code at leg design time:

| Citation | Status | Notes |
|----------|--------|-------|
| `the_one/db/models.py:188-317` (`_validate_config_reserved_keys`) | OK | Validator definition spans those lines; pairing block 241-286; allowlist block 288-315; return statement 317 |
| `the_one/db/models.py:190` (validator method header) | OK | `def _validate_config_reserved_keys(cls, value: ...)` confirmed |
| `the_one/tools/connector_send.py:144-217` (F6 outbound ACL check) | OK | Span confirmed via Read: account-scope channels at 176-184; per-agent channels at 195-217; the leg replaces this block |
| `the_one/tools/connector_send.py:151-154` (function-local import block) | OK | Imports at 151-154; cycle-break documented in lines 145-150 |
| `the_one/tools/connector_send.py:167` (HAT semantic block header) | OK | "M10 F6 L7 HAT — allowlist/ACL semantic redesign." comment at line 167 |
| `the_one/agent/config.py:184` (`connector_acls` field) | OK | Field declaration confirmed |
| `the_one/agent/config.py:189-240` (`_validate_connector_acls`) | OK | Validator spans 189-240 |
| `tests/test_connectors_resolver.py` (test-style mirror) | OK | Style confirmed at L1 design time; still applicable |
| `tests/test_connector_send_tool.py` (F6 regression net) | OK | File present; contains outbound ACL tests that pin the existing reason strings |

5 in-leg-artifact code-location citations verified against current code at leg design time.
