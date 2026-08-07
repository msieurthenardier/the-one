"""Tests for the_one.interfaces.web.handoff_store — Mission 20 / Flight 1 /
Leg 2 (`gate-middleware`), DD12, LD2.

Covers the one-time browser-handoff credential store in isolation from the
gate middleware: mint/consume, single-use, TTL via an injectable clock
(never `time.sleep`), per-process isolation (a fresh store neither
recognises an outstanding value from another store nor can resurrect one
that store already consumed), and atomic concurrent consumption.
"""

from __future__ import annotations

import threading

from the_one.interfaces.web.handoff_store import (
    DEFAULT_TTL_SECONDS,
    HandoffStore,
    get_default_handoff_store,
    mint_handoff_credential,
)


class _FakeClock:
    """A settable clock — the injectable-clock seam the leg's TTL tests
    require instead of `time.sleep`."""

    def __init__(self, start: float = 0.0) -> None:
        self._now = start

    def __call__(self) -> float:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += seconds


class TestMintAndConsume:
    def test_freshly_minted_token_consumes_successfully(self) -> None:
        store = HandoffStore()
        token = store.mint()
        assert store.consume(token) is True

    def test_unknown_token_does_not_consume(self) -> None:
        store = HandoffStore()
        assert store.consume("never-minted") is False

    def test_single_use_replay_fails(self) -> None:
        store = HandoffStore()
        token = store.mint()
        assert store.consume(token) is True
        assert store.consume(token) is False

    def test_mint_returns_distinct_tokens(self) -> None:
        store = HandoffStore()
        tokens = {store.mint() for _ in range(20)}
        assert len(tokens) == 20


class TestTTL:
    def test_unused_token_within_ttl_consumes(self) -> None:
        clock = _FakeClock()
        store = HandoffStore(ttl_seconds=60.0, clock=clock)
        token = store.mint()
        clock.advance(59.0)
        assert store.consume(token) is True

    def test_unused_token_past_ttl_is_refused(self) -> None:
        clock = _FakeClock()
        store = HandoffStore(ttl_seconds=60.0, clock=clock)
        token = store.mint()
        clock.advance(61.0)
        assert store.consume(token) is False

    def test_expired_token_stays_refused_and_is_not_resurrected_by_replay(self) -> None:
        clock = _FakeClock()
        store = HandoffStore(ttl_seconds=10.0, clock=clock)
        token = store.mint()
        clock.advance(11.0)
        assert store.consume(token) is False
        assert store.consume(token) is False

    def test_default_ttl_is_generous(self) -> None:
        # DD12: "choose the TTL generously; failure mode is a relaunch."
        # Minutes, not seconds.
        assert DEFAULT_TTL_SECONDS >= 60.0


class TestPerProcessIsolation:
    def test_fresh_store_rejects_a_value_outstanding_on_another_store(self) -> None:
        """A fresh store (standing in for a restarted process) does not
        recognise a token that is still outstanding (unconsumed, unexpired)
        on a different store instance."""
        store_a = HandoffStore()
        token = store_a.mint()  # outstanding on store_a, never consumed there

        store_b = HandoffStore()  # fresh instance — the "restart"

        assert store_b.consume(token) is False

    def test_fresh_store_cannot_resurrect_a_value_already_spent_elsewhere(self) -> None:
        store_a = HandoffStore()
        token = store_a.mint()
        assert store_a.consume(token) is True  # spent on store_a

        store_b = HandoffStore()  # fresh instance — the "restart"

        assert store_b.consume(token) is False


class TestConcurrentConsumption:
    def test_two_racing_consumers_never_both_succeed(self) -> None:
        store = HandoffStore()
        token = store.mint()
        results: list[bool] = []
        results_lock = threading.Lock()
        start_barrier = threading.Barrier(2)

        def _race() -> None:
            start_barrier.wait()
            result = store.consume(token)
            with results_lock:
                results.append(result)

        threads = [threading.Thread(target=_race) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert sorted(results) == [False, True]

    def test_many_racing_consumers_exactly_one_succeeds(self) -> None:
        store = HandoffStore()
        token = store.mint()
        results: list[bool] = []
        results_lock = threading.Lock()
        n = 16
        start_barrier = threading.Barrier(n)

        def _race() -> None:
            start_barrier.wait()
            result = store.consume(token)
            with results_lock:
                results.append(result)

        threads = [threading.Thread(target=_race) for _ in range(n)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert results.count(True) == 1
        assert results.count(False) == n - 1


class TestDefaultStoreAndMintFunction:
    def test_get_default_handoff_store_returns_a_stable_singleton(self) -> None:
        assert get_default_handoff_store() is get_default_handoff_store()

    def test_mint_handoff_credential_mints_into_the_default_store(self) -> None:
        token = mint_handoff_credential()
        assert get_default_handoff_store().consume(token) is True
