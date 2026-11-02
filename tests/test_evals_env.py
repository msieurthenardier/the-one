"""Start-up order, guards, environment pinning, token handling, locks, shutdown (DD3, DD4, DD19)."""

from __future__ import annotations

import os
import subprocess
import sys

import _evals_helpers as h
import pytest
from _evals_helpers import FAKE_TOKEN, token_file

from evals import env as ev
from evals.env import EvalRefusalError, StartupOptions, shutdown, startup

EVALS_REAL_MIGRATIONS = True  # this module proves the real start-up path
evals_isolation = h.evals_isolation
real_data_dir = h.real_data_dir
pytestmark = pytest.mark.usefixtures("evals_isolation")


def test_paths_overlap_equal_contains_inside(tmp_path):
    a = tmp_path / "a"
    assert ev.paths_overlap(a, a)
    assert ev.paths_overlap(a / "b", a)  # inside
    assert ev.paths_overlap(a, a / "b")  # contains
    assert not ev.paths_overlap(a, tmp_path / "ab")  # sibling with a shared prefix


def test_guard_refuses_equal_contains_inside_real_dir(tmp_path, real_data_dir):
    for bad in (real_data_dir, real_data_dir / "evals" / "data", tmp_path / "real-user-data"):
        with pytest.raises(EvalRefusalError) as ei:
            ev.guard_data_dir(bad, real_data_dir, None)
        assert "\n" not in str(ei.value)
    ev.guard_data_dir(tmp_path / "run" / "data", real_data_dir, None)  # fine


def test_guard_refuses_run_dir_overlapping_the_resolved_settings_dir(tmp_path, real_data_dir):
    configured = tmp_path / "ops" / "op-data"
    for bad in (configured, configured / "evals" / "data", tmp_path / "ops"):
        with pytest.raises(EvalRefusalError, match="THE_ONE_DATA_DIR"):
            ev.guard_data_dir(bad, real_data_dir, configured)
    ev.guard_data_dir(tmp_path / "run" / "data", real_data_dir, configured)  # fine
    # the usual case: nothing configured, so settings.data_dir resolves to the real default;
    # a run directory elsewhere is fine
    ev.guard_data_dir(tmp_path / "run" / "data", real_data_dir, real_data_dir)


async def test_startup_refuses_run_dir_inside_real_dir_and_creates_nothing(tmp_path, real_data_dir):
    run_dir = real_data_dir / "evals-run"
    with pytest.raises(EvalRefusalError):
        await startup(StartupOptions(run_dir=run_dir))
    assert not real_data_dir.exists()


async def test_startup_refuses_settings_dir_from_environment(tmp_path, real_data_dir, monkeypatch):
    from the_one.config import settings

    run_dir = tmp_path / "runs" / "r"
    # as THE_ONE_DATA_DIR / a .env would: the configured dir is the run's own data/
    monkeypatch.setattr(settings, "data_dir", run_dir / "data")
    with pytest.raises(EvalRefusalError, match="THE_ONE_DATA_DIR"):
        await startup(StartupOptions(run_dir=run_dir))
    assert not run_dir.exists()  # nothing created


@pytest.mark.parametrize("name", ev.PINNED_ENV)
async def test_startup_refuses_pinned_env(tmp_path, real_data_dir, monkeypatch, name):
    monkeypatch.setenv(name, "1")
    run_dir = tmp_path / "runs" / "r"
    with pytest.raises(EvalRefusalError, match=name):
        await startup(StartupOptions(run_dir=run_dir))
    assert not run_dir.exists()


async def test_startup_order_is_guard_token_home_data_dir_sweep_init(
    tmp_path, real_data_dir, monkeypatch
):
    calls: list[str] = []

    def spy(name):
        orig = getattr(ev, name)

        def wrapper(*a, **k):
            calls.append(name)
            return orig(*a, **k)

        monkeypatch.setattr(ev, name, wrapper)

    async def init_spy():
        calls.append("init_database")
        return await orig_init()

    orig_init = ev.init_database
    for n in (
        "check_pinned_env",
        "real_default_data_dir",
        "guard_data_dir",
        "read_token",
        "switch_home",
        "assign_data_dir",
        "sweep_stale",
        "acquire_lock",
    ):
        spy(n)
    monkeypatch.setattr(ev, "init_database", init_spy)

    home_at_default_dir = []
    orig_default = ev.real_default_data_dir

    def default_spy():
        home_at_default_dir.append(os.environ["HOME"])
        return orig_default()

    monkeypatch.setattr(ev, "real_default_data_dir", default_spy)

    real_home = os.environ["HOME"]
    env = await startup(
        StartupOptions(
            run_dir=tmp_path / "runs" / "r", need_token=True, token_file=token_file(tmp_path)
        )
    )
    try:
        assert calls == [
            "check_pinned_env",
            "real_default_data_dir",
            "guard_data_dir",
            "read_token",
            "switch_home",
            "assign_data_dir",
            "sweep_stale",
            "acquire_lock",
            "init_database",
        ]
        # the real default dir was computed while HOME was still the real one
        assert home_at_default_dir == [real_home]
        assert os.environ["HOME"] == str(env.home)
        assert os.environ["USERPROFILE"] == str(env.home)
        assert (env.home / "workspace").is_dir()
        from the_one.config import settings

        assert settings.data_dir == env.data_dir
    finally:
        await shutdown(env)
    assert os.environ["HOME"] == real_home


async def test_assigning_data_dir_does_not_trigger_legacy_migration(tmp_path, real_data_dir):
    from the_one.config import settings

    env = await startup(StartupOptions(run_dir=tmp_path / "runs" / "r"))
    try:
        assert "data_dir" in settings.model_fields_set
        assert not (env.home / ".the-one").exists()
        assert not real_data_dir.exists()
    finally:
        await shutdown(env)


async def test_no_token_read_unless_needed(tmp_path, real_data_dir):
    env = await startup(
        StartupOptions(run_dir=tmp_path / "runs" / "r", need_token=False, token_file=tmp_path / "x")
    )
    try:
        assert env.token is None
    finally:
        await shutdown(env)


async def test_missing_or_empty_token_file_refuses_without_leaking(tmp_path, real_data_dir):
    with pytest.raises(EvalRefusalError, match="cannot read the plan token file"):
        await startup(
            StartupOptions(
                run_dir=tmp_path / "runs" / "r", need_token=True, token_file=tmp_path / "missing"
            )
        )
    empty = tmp_path / "empty"
    empty.write_text("  \n")
    with pytest.raises(EvalRefusalError, match="is empty"):
        await startup(
            StartupOptions(run_dir=tmp_path / "runs" / "r2", need_token=True, token_file=empty)
        )


def test_read_token_strips_whitespace(tmp_path):
    assert ev.read_token(token_file(tmp_path, "  abc-token \n")) == "abc-token"


async def test_shutdown_order_and_data_deleted(tmp_path, real_data_dir, monkeypatch):
    order: list[str] = []

    class Mgr:
        async def drain(self):
            order.append("drain")

        def cancelled_kb_ids(self):
            return frozenset()

    import the_one.db as db
    import the_one.vectors as vectors

    orig_close_vs, orig_close_conn = vectors.close_vector_store, db.close_connection

    async def close_vs(**kw):
        order.append("close_vector_store")
        await orig_close_vs(**kw)

    async def close_conn():
        order.append("close_connection")
        await orig_close_conn()

    monkeypatch.setattr(vectors, "close_vector_store", close_vs)
    monkeypatch.setattr(db, "close_connection", close_conn)
    env = await startup(StartupOptions(run_dir=tmp_path / "runs" / "r"))
    env.managers.append(Mgr())
    assert env.data_dir.is_dir()
    await shutdown(env)
    assert order == ["drain", "close_vector_store", "close_connection"]
    assert not env.data_dir.exists()
    assert (env.run_dir / "owner.lock").exists()  # present, but released
    assert (env.run_dir / "owner.lock").read_text().strip() == "released"


async def test_data_deleted_when_the_body_raises(tmp_path, real_data_dir):
    env = await startup(StartupOptions(run_dir=tmp_path / "runs" / "r"))
    with pytest.raises(RuntimeError):
        try:
            raise RuntimeError("boom")
        finally:
            await shutdown(env)
    assert not env.data_dir.exists()


async def test_lock_holds_pid_and_live_owner_data_survives_a_second_start(
    tmp_path, real_data_dir, monkeypatch
):
    runs = tmp_path / "runs"
    monkeypatch.setattr(ev, "DEFAULT_RUNS_ROOT", runs)
    other = runs / "other"
    (other / "data").mkdir(parents=True)
    (other / "data" / "the-one.db").write_text("live")
    (other / "owner.lock").write_text(str(os.getpid()))  # a live owner

    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    stale = runs / "stale"
    (stale / "data").mkdir(parents=True)
    (stale / "owner.lock").write_text(str(dead.pid))  # a dead owner
    nolock = runs / "nolock"
    (nolock / "data").mkdir(parents=True)  # no lock at all: never ours, never touched

    env = await startup(StartupOptions(run_dir=runs / "mine"))
    try:
        assert (env.run_dir / "owner.lock").read_text().strip() == str(os.getpid())
        assert (other / "data" / "the-one.db").read_text() == "live"
        assert not (stale / "data").exists()
        assert (nolock / "data").exists()
    finally:
        await shutdown(env)


async def test_refuses_a_run_dir_owned_by_another_live_process(tmp_path, real_data_dir):
    run_dir = tmp_path / "runs" / "r"
    run_dir.mkdir(parents=True)
    parent = os.getppid()  # a live process that is not us
    (run_dir / "owner.lock").write_text(str(parent))
    with pytest.raises(EvalRefusalError, match="in use by process"):
        await startup(StartupOptions(run_dir=run_dir))
    assert os.environ["HOME"] != str(run_dir / "home")  # HOME restored after the failure


# ── the redactor ──────────────────────────────────────────────────────────


def test_redactor_replaces_token_in_text_json_and_objects():
    r = ev.Redactor(FAKE_TOKEN)
    assert FAKE_TOKEN not in r.redact(f"Authorization: Bearer {FAKE_TOKEN}")
    assert FAKE_TOKEN not in r.dumps({"a": [FAKE_TOKEN, {"b": f"x{FAKE_TOKEN}y"}]})
    assert FAKE_TOKEN not in str(r.obj({"k": (FAKE_TOKEN,)}))
    assert FAKE_TOKEN not in r.exc_text(ValueError(f"bad {FAKE_TOKEN}"))
    # a token with characters that JSON escapes
    odd = 'tok"en\\with"quotes'
    assert odd not in ev.Redactor(odd).dumps({"v": odd})
    assert ev.Redactor(None).redact("plain") == "plain"


def test_log_redaction_handler(capsys):
    import logging

    r = ev.Redactor(FAKE_TOKEN)
    lr = ev.LogRedaction(r)
    lr.install()
    try:
        logging.getLogger("evals.test").warning("leak %s", FAKE_TOKEN)
        try:
            raise ValueError(FAKE_TOKEN)
        except ValueError:
            logging.getLogger("evals.test").exception("with traceback")
    finally:
        lr.uninstall()
    err = capsys.readouterr().err
    assert FAKE_TOKEN not in err
    assert "leak [REDACTED]" in err


# ── sweep_stale containment ──────────────────────────────────────────────


def _dead_pid() -> int:
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    return proc.pid


def _mk(root, name, lock=None, lock_bytes=None):
    d = root / name
    (d / "data").mkdir(parents=True)
    (d / "data" / "important").write_text("x")
    if lock is not None:
        (d / "owner.lock").write_text(lock)
    if lock_bytes is not None:
        (d / "owner.lock").write_bytes(lock_bytes)
    return d


def test_sweep_lockless_sibling_survives(tmp_path):
    d = _mk(tmp_path, "proj")
    assert ev.sweep_stale(tmp_path, default_root=tmp_path) == []
    assert (d / "data" / "important").exists()


def test_sweep_unreadable_lock_survives(tmp_path):
    a = _mk(tmp_path, "a", lock_bytes=b"\xff\xfe garbage")
    b = _mk(tmp_path, "b", lock="not-a-pid")
    c = _mk(tmp_path, "c")
    (c / "owner.lock").mkdir()  # unreadable as a file
    assert ev.sweep_stale(tmp_path, default_root=tmp_path) == []
    for d in (a, b, c):
        assert (d / "data" / "important").exists()


def test_sweep_outside_default_root_sweeps_nothing(tmp_path):
    root = tmp_path / "default"
    root.mkdir()
    other = tmp_path / "work"
    d = _mk(other, "eval1", lock=str(_dead_pid()))
    assert ev.sweep_stale(other, default_root=root) == []
    assert (d / "data" / "important").exists()


def test_sweep_does_not_follow_symlinks(tmp_path):
    victim = tmp_path / "victim"
    victim.mkdir()
    (victim / "keep").write_text("x")
    root = tmp_path / "runs"
    d = root / "r"
    d.mkdir(parents=True)
    (d / "owner.lock").write_text(str(_dead_pid()))
    (d / "data").symlink_to(victim, target_is_directory=True)
    linked = root / "linked"
    linked.symlink_to(_mk(tmp_path / "elsewhere", "t", lock=str(_dead_pid())))
    assert ev.sweep_stale(root, default_root=root) == []
    assert (victim / "keep").exists()
    assert (tmp_path / "elsewhere" / "t" / "data" / "important").exists()


def test_sweep_dead_swept_live_survives_released_swept(tmp_path):
    dead = _mk(tmp_path, "dead", lock=str(_dead_pid()))
    live = _mk(tmp_path, "live", lock=str(os.getpid()))
    rel = _mk(tmp_path, "rel", lock="released\n")
    removed = ev.sweep_stale(tmp_path, default_root=tmp_path)
    assert sorted(p.parent.name for p in removed) == ["dead", "rel"]
    assert not (dead / "data").exists() and not (rel / "data").exists()
    assert (live / "data" / "important").exists()
