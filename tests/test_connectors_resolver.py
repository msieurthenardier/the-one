"""Type-level surface tests for F6's resolver outcome ADT and the
optional ``resolve(account, envelope) -> ResolveOutcome`` plugin hook.

Leg 1a of M10 F06 lands the surface but NO consumer; legs 2 and 3 will
wire ``getattr(plugin, "resolve", _default_permit)`` into the inbound
dispatcher and the platform-send tool respectively. These tests pin:

- the outcome dataclasses (``Permit``, ``NeedsPairing``, ``Deny``) are
  frozen + slotted + hashable
- the ``ResolveOutcome`` union accepts each
- ``_default_permit`` returns ``Permit()`` for any inputs
- the ``StubPlugin`` does NOT implement ``resolve`` (regression-net
  preservation; the F1–F5 dispatcher tests exercise the fallback path)
- ``_default_permit`` is reachable only via the canonical
  ``the_one.connectors.base`` path (NOT re-exported from the package
  ``__init__``)

Inline minimal fixtures (mirrors the ``test_connectors.py`` F1 surface-test
convention); the heavyweight helpers in ``_connector_dispatch_helpers.py``
are overkill for type-level surface tests.
"""

from __future__ import annotations

from the_one.connectors import Deny, NeedsPairing, Permit, ResolveOutcome
from the_one.connectors.base import InboundEnvelope, _default_permit
from the_one.db.models import ConnectorAccount


def _account() -> ConnectorAccount:
    """Minimal ``ConnectorAccount`` fixture.

    Only ``id``/``name``/``type``/``config``/``secrets`` are passed; the
    Pydantic model fills ``created_at``/``updated_at`` via
    ``Field(default_factory=now_iso)`` and ``idle_timeout_seconds`` /
    ``session_continuation_seconds`` default to ``None``. None of this
    leg's tests consult any account field — ``_default_permit`` ignores
    both parameters — so a stub-shaped account is sufficient.
    """
    return ConnectorAccount(
        id="acc-1",
        name="test",
        type="stub",
        config={},
        secrets={},
    )


def _envelope() -> InboundEnvelope:
    return InboundEnvelope(
        platform="stub",
        account_id="acc-1",
        channel_id="c",
        thread_id=None,
        peer_id="p",
        peer_name="P",
        text="t",
        raw={},
    )


def test_smoke_import_canonical_path() -> None:
    """Catches 'added symbol broke base.py at import time'."""
    from the_one.connectors.base import (  # noqa: F401
        Deny,
        NeedsPairing,
        Permit,
        ResolveOutcome,
        _default_permit,
    )

    # ``_default_permit`` is reachable via the canonical path.
    assert _default_permit.__module__ == "the_one.connectors.base"


def test_outcomes_construct_and_equate() -> None:
    assert Permit() == Permit()
    assert NeedsPairing("x") == NeedsPairing("x")
    assert NeedsPairing("x") != NeedsPairing("y")
    assert Deny("x") != Deny("y")
    # frozen+slots → hashable
    assert hash(Permit()) == hash(Permit())
    assert hash(NeedsPairing("x")) == hash(NeedsPairing("x"))
    assert hash(Deny("x")) == hash(Deny("x"))


def test_resolve_outcome_union_accepts_all_three() -> None:
    outcomes: list[ResolveOutcome] = [Permit(), NeedsPairing("r"), Deny("r")]
    for o in outcomes:
        assert isinstance(o, (Permit, NeedsPairing, Deny))


def test_default_permit_returns_permit_for_any_inputs() -> None:
    result = _default_permit(_account(), _envelope())
    assert isinstance(result, Permit)
    # ``Permit`` instances are frozen-dataclass-equal — callers may compare
    # against a sentinel without identity reliance.
    assert result == Permit()


def test_stub_plugin_does_not_implement_resolve() -> None:
    """Regression-net preservation: the stub MUST stay at its 4-method shape.

    F1–F5 dispatcher tests drive inbound through the stub and exercise
    the ``getattr(plugin, "resolve", _default_permit)`` fallback path.
    """
    from the_one.connectors._stub import StubPlugin

    plugin = StubPlugin()
    assert not hasattr(plugin, "resolve")
    # The getattr-discovery convention falls back to ``_default_permit``:
    hook = getattr(plugin, "resolve", _default_permit)
    assert hook is _default_permit


def test_default_permit_is_not_publicly_reexported() -> None:
    """``_default_permit`` is private to the connector package.

    Consumers (``connectors/_inbound.py`` in F6 leg 2,
    ``tools/connector_send.py`` in F6 leg 3) import via the canonical
    path ``the_one.connectors.base._default_permit``, NOT via the
    ``the_one.connectors`` convenience re-export.
    """
    import the_one.connectors as pkg

    assert "_default_permit" not in getattr(pkg, "__all__", [])
