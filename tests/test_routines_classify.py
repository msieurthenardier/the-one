"""Pure unit tests: ``classify`` row by row and ``RunRegistry`` (M33 F1 L4, AC1, AC8)."""

from __future__ import annotations

import asyncio

import pytest

from the_one.connectors.delivery import DeliveryResult
from the_one.routines import runner
from the_one.routines.runner import RunRegistry, classify


def c(state="done", info=None, *, timed_out=False, timeout=900.0, name="Disc"):
    return classify(
        state, info or {}, timed_out=timed_out, timeout_seconds=timeout, connector_name=name
    )


def test_clean_ok():
    assert c() == ("ok", None)


@pytest.mark.parametrize("status", ["delivered", "already_sent"])
def test_delivered_ok(status):
    assert c(info={"delivery": DeliveryResult(status)}) == ("ok", None)


def test_step_limit_ok():
    assert c(info={"step_limit": True}) == ("ok", "Stopped at the step limit.")


def test_no_text():
    assert c(info={"delivery": DeliveryResult("no_text")}) == (
        "ok",
        "The agent gave no reply to send.",
    )


def test_send_failed_and_no_client():
    assert c(info={"delivery": DeliveryResult("send_failed", "boom")}) == (
        "failed",
        "Couldn't send to Disc: boom.",
    )
    assert c(info={"delivery": DeliveryResult("no_client")}) == (
        "failed",
        "Couldn't send to Disc: not connected.",
    )


def test_paused():
    assert c(info={"paused": "Notion"}) == (
        "failed",
        "Needs a sign-in to Notion. Sign in on its page in Library, then run it again.",
    )


def test_error():
    assert c(info={"error": "kaput"}) == ("failed", "kaput")


def test_timeout_before_start_is_skipped():
    assert c("cancelled", timed_out=True, timeout=900) == (
        "skipped",
        "The chat stayed busy for 15 minutes.",
    )


def test_timeout_after_start_is_failed():
    assert c("done", {"started": True, "cancelled": True}, timed_out=True, timeout=900) == (
        "failed",
        "The run took longer than 15 minutes.",
    )


def test_minutes_floor_and_rounding():
    assert c(timed_out=True, timeout=20)[1] == "The chat stayed busy for 1 minute."
    assert c(timed_out=True, timeout=150)[1] == "The chat stayed busy for 2 minutes."


def test_stop():
    assert c("cancelled") == ("stopped", "Stopped from the chat.")
    assert c("done", {"started": True, "cancelled": True}) == ("stopped", "Stopped from the chat.")


def test_interrupted():
    assert c("interrupted") == ("interrupted", "The app stopped during this run.")


def test_timeout_env_and_floor(monkeypatch):
    monkeypatch.delenv("THE_ONE_ROUTINE_RUN_TIMEOUT_SECONDS", raising=False)
    assert runner.routine_run_timeout_seconds() == 900
    monkeypatch.setenv("THE_ONE_ROUTINE_RUN_TIMEOUT_SECONDS", "10")
    assert runner.routine_run_timeout_seconds() == 60
    monkeypatch.setattr(runner, "_TIMEOUT_FLOOR_SECONDS", 0.05)
    monkeypatch.setenv("THE_ONE_ROUTINE_RUN_TIMEOUT_SECONDS", "0.2")
    assert runner.routine_run_timeout_seconds() == 0.2
    monkeypatch.setenv("THE_ONE_ROUTINE_RUN_TIMEOUT_SECONDS", "x")
    assert runner.routine_run_timeout_seconds() == 900


async def test_registry_try_spawn_is_synchronous_and_exclusive():
    reg = RunRegistry()
    gate = asyncio.Event()
    made = []

    async def work():
        made.append(1)
        await gate.wait()

    t1 = reg.try_spawn("r", work)
    assert t1 is not None and reg.is_running("r")
    called = []
    assert reg.try_spawn("r", lambda: called.append(1)) is None
    assert called == []  # no coroutine was created
    gate.set()
    await t1
    await asyncio.sleep(0)
    assert not reg.is_running("r")
    assert reg.try_spawn("r", work) is not None
    await reg.drain(1)


async def test_registry_pause_memory():
    reg = RunRegistry()
    assert reg.own_pause("r") is None
    reg.remember_pause("r", "s1")
    assert reg.own_pause("r") == "s1"
    reg.clear_pause("r")
    assert reg.own_pause("r") is None


async def test_registry_drain_cancels_and_bounds():
    reg = RunRegistry()

    async def forever():
        await asyncio.sleep(60)

    t = reg.try_spawn("r", forever)
    await asyncio.sleep(0)
    await reg.drain(1.0)
    assert t.cancelled() and not reg.is_running("r")
