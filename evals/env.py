"""Start-up order, guards, containment of the process environment, the token
reader and redactor, locks and sweeps (DD3, DD4, DD19).

``startup`` is the one safety-critical function and its order is fixed:

1. the operator's real default data directory is computed ONCE (platformdirs reads
   ``HOME``, so this must precede step 4) and kept for every refusal check;
2. the guard (nothing is created before it passes);
3. the plan token file is read, only if a selected preset needs it;
4. ``HOME`` / ``USERPROFILE`` are switched to the scratch home;
5. ``settings.data_dir`` is assigned the scratch data directory;
6. stale ``data/`` directories (dead owner PID) are swept and this run's lock taken;
7. ``init_db``.

Shutdown mirrors the web lifespan: stop indexing, ``close_vector_store()``,
``close_connection()``, delete ``data/``.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PINNED_ENV = (
    "THE_ONE_ANTHROPIC_EXTENDED_THINKING",
    "THE_ONE_REASONING_EFFORT",
    "THE_ONE_OLLAMA_NUM_CTX",
    "THE_ONE_STOP",
    "THE_ONE_RESPONSE_FORMAT",
)
DEFAULT_TOKEN_FILE = "~/.config/the-one-evals/plan-token"
REDACTED = "[REDACTED]"


class EvalRefusalError(Exception):
    """A start-up refusal. The message is a single line; nothing has been created."""


# ── Paths and guards ──────────────────────────────────────────────────────


def _resolved(p: Path) -> Path:
    return Path(os.path.abspath(os.path.expanduser(str(p)))).resolve()


def paths_overlap(a: Path, b: Path) -> bool:
    """True when ``a`` equals, contains or lies inside ``b``."""
    ra, rb = _resolved(a), _resolved(b)
    return ra == rb or ra in rb.parents or rb in ra.parents


def real_default_data_dir() -> Path:
    """The operator's real default data directory. Compute before HOME changes."""
    from the_one.config import _default_data_dir

    return _default_data_dir()


def resolved_settings_data_dir() -> Path:
    """``settings.data_dir`` as already resolved (env var or working-directory ``.env``)."""
    from the_one.config import settings

    return Path(settings.data_dir)


def check_pinned_env(environ: Any = None) -> None:
    """Refuse when a provider-shaping variable is set (these are read from ``os.environ``)."""
    environ = os.environ if environ is None else environ
    for name in PINNED_ENV:
        if name in environ:
            raise EvalRefusalError(
                f"refusing to run: {name} is set; unset it so the app's shipped defaults apply"
            )


def guard_data_dir(run_data_dir: Path, real_default: Path, settings_dir: Path | None) -> None:
    """Refuse a run whose data directory would touch an operator data directory.

    Two directories are protected: the real platform default (computed once, before
    ``HOME`` changes) and the already-resolved ``settings.data_dir``, which a
    ``THE_ONE_DATA_DIR`` in the environment or in a working-directory ``.env`` may
    point somewhere else entirely. The run's ``data/`` is deleted at exit, so it may
    equal, contain or lie inside neither.
    """
    if paths_overlap(run_data_dir, real_default):
        raise EvalRefusalError(
            f"refusing to run: {run_data_dir} equals, contains or lies inside the real data "
            f"directory {real_default}"
        )
    if settings_dir is not None and paths_overlap(run_data_dir, settings_dir):
        raise EvalRefusalError(
            f"refusing to run: {run_data_dir} equals, contains or lies inside the configured "
            f"data directory {settings_dir} (THE_ONE_DATA_DIR or a .env)"
        )


# ── The token and the redactor ────────────────────────────────────────────


def read_token(path: Path) -> str:
    """Read and strip the plan token. The error never includes the token."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise EvalRefusalError(f"cannot read the plan token file {path}: {exc.strerror}") from None
    token = text.strip()
    if not token:
        raise EvalRefusalError(f"the plan token file {path} is empty")
    return token


_GENERIC_TOKEN = re.compile(r"sk-ant-[A-Za-z0-9_\-]{16,}")


class Redactor:
    """Replaces the token (raw and JSON-escaped forms) wherever it appears."""

    def __init__(self, token: str | None = None) -> None:
        self._needles: list[str] = []
        if token:
            self._needles.append(token)
            escaped = json.dumps(token)[1:-1]
            if escaped != token:
                self._needles.append(escaped)
            self._needles.sort(key=len, reverse=True)

    def redact(self, text: str) -> str:
        for n in self._needles:
            text = text.replace(n, REDACTED)
        return _GENERIC_TOKEN.sub(REDACTED, text)

    def obj(self, value: Any) -> Any:
        """Redact every string in a JSON-able structure."""
        if isinstance(value, str):
            return self.redact(value)
        if isinstance(value, dict):
            return {self.obj(k): self.obj(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [self.obj(v) for v in value]
        return value

    def dumps(self, value: Any, **kw: Any) -> str:
        return self.redact(json.dumps(value, ensure_ascii=False, default=str, **kw))

    def exc_text(self, exc: BaseException) -> str:
        return self.redact(f"{type(exc).__name__}: {exc}")

    def write_text(self, path: Path, text: str) -> None:
        path.write_text(self.redact(text), encoding="utf-8")

    def append_line(self, path: Path, line: str) -> None:
        """Append one line durably (results are appended as each run finishes)."""
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(self.redact(line) + "\n")
            fh.flush()
            os.fsync(fh.fileno())


class _RedactingFormatter(logging.Formatter):
    def __init__(self, redactor: Redactor) -> None:
        super().__init__("%(levelname)s %(name)s: %(message)s")
        self._redactor = redactor

    def format(self, record: logging.LogRecord) -> str:
        return self._redactor.redact(super().format(record))


class LogRedaction:
    """Routes the root logger through one redacting handler for the invocation."""

    def __init__(self, redactor: Redactor) -> None:
        self._handler = logging.StreamHandler(sys.stderr)
        self._handler.setFormatter(_RedactingFormatter(redactor))
        self._root = logging.getLogger()
        self._saved_handlers: list[logging.Handler] = []
        self._saved_level = logging.NOTSET

    def install(self) -> None:
        self._saved_handlers = list(self._root.handlers)
        self._saved_level = self._root.level
        for h in self._saved_handlers:
            self._root.removeHandler(h)
        self._root.addHandler(self._handler)
        self._root.setLevel(logging.WARNING)

    def uninstall(self) -> None:
        self._root.removeHandler(self._handler)
        for h in self._saved_handlers:
            self._root.addHandler(h)
        self._root.setLevel(self._saved_level)


# ── Locks and sweeps ──────────────────────────────────────────────────────


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _lock_pid(run_dir: Path) -> int | None:
    try:
        return int((run_dir / "owner.lock").read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


DEFAULT_RUNS_ROOT = Path(__file__).resolve().parent / "runs"


def _lock_state(run_dir: Path) -> str | int | None:
    """``int`` pid, ``"released"``, or ``None`` when absent/unreadable/unparseable."""
    try:
        text = (run_dir / "owner.lock").read_text(encoding="utf-8").strip()
    except (OSError, ValueError):
        return None
    if text == "released":
        return "released"
    try:
        return int(text)
    except ValueError:
        return None


def sweep_stale(runs_root: Path, default_root: Path | None = None) -> list[Path]:
    """Delete a ``data/`` directory left behind by a crash, only when its owner is dead.

    It holds an encrypted token beside its key. Only the default runs root is ever swept
    (a user-supplied ``--run-dir`` elsewhere sweeps nothing), only siblings holding an
    ``owner.lock`` this runner wrote are considered, an unreadable lock is never touched,
    and symlinks are never followed. A live owner PID is never touched. Returns the
    directories removed.
    """
    removed: list[Path] = []
    root = (default_root or DEFAULT_RUNS_ROOT).resolve()
    try:
        if runs_root.is_symlink() or runs_root.resolve() != root or not runs_root.is_dir():
            return removed
        siblings = sorted(runs_root.iterdir())
    except OSError:
        return removed
    for run_dir in siblings:
        if run_dir.is_symlink() or not run_dir.is_dir():
            continue
        lock = run_dir / "owner.lock"
        data = run_dir / "data"
        if lock.is_symlink() or not lock.is_file():
            continue
        state = _lock_state(run_dir)
        if state is None:
            continue
        if isinstance(state, int) and pid_alive(state):
            continue
        if data.is_symlink() or not data.is_dir():
            continue
        shutil.rmtree(data, ignore_errors=True)
        lock.unlink(missing_ok=True)
        removed.append(data)
    return removed


def acquire_lock(run_dir: Path) -> None:
    pid = _lock_pid(run_dir)
    if pid is not None and pid != os.getpid() and pid_alive(pid):
        raise EvalRefusalError(f"refusing to run: {run_dir} is in use by process {pid}")
    (run_dir / "owner.lock").write_text(str(os.getpid()), encoding="utf-8")


# ── The environment object ────────────────────────────────────────────────


@dataclass
class StartupOptions:
    run_dir: Path
    need_token: bool = False
    token_file: Path | None = None
    environ: Any = None


@dataclass
class EvalEnv:
    run_dir: Path
    data_dir: Path
    home: Path
    token: str | None
    redactor: Redactor
    conn: Any = None
    managers: list[Any] = field(default_factory=list)
    saved_home: dict[str, str | None] = field(default_factory=dict)
    saved_data_dir: Path | None = None
    log_redaction: LogRedaction | None = None
    closed: bool = False

    def say(self, message: str) -> None:
        print(self.redactor.redact(message), flush=True)

    def warn(self, message: str) -> None:
        print(self.redactor.redact(message), file=sys.stderr, flush=True)


def switch_home(home: Path, saved: dict[str, str | None]) -> None:
    for var in ("HOME", "USERPROFILE"):
        saved[var] = os.environ.get(var)
        os.environ[var] = str(home)


def restore_home(saved: dict[str, str | None]) -> None:
    for var, old in saved.items():
        if old is None:
            os.environ.pop(var, None)
        else:
            os.environ[var] = old


def assign_data_dir(data_dir: Path) -> Path:
    """Point ``settings.data_dir`` at the scratch directory (by assignment: the
    sweep script's precedent; this also marks the field as explicitly set, so the
    legacy ``~/.the-one`` migration never runs). Creates nothing; returns the previous
    value."""
    from the_one.config import settings

    previous = Path(settings.data_dir)
    settings.data_dir = data_dir
    return previous


async def init_database() -> Any:
    """``init_db`` and key reconcile, as the CLI and the web lifespan do."""
    from the_one.config import settings
    from the_one.db import init_db
    from the_one.db.connection import get_connection
    from the_one.db.key_reconcile import reconcile_pending_key
    from the_one.encryption import get_encryptor

    await init_db()
    conn = await get_connection()
    await reconcile_pending_key(conn, get_encryptor(settings.data_dir))
    return conn


async def startup(opts: StartupOptions) -> EvalEnv:
    """The fixed start-up order. See the module docstring."""
    run_dir = _resolved(opts.run_dir)  # resolved before HOME changes
    data_dir = run_dir / "data"
    check_pinned_env(opts.environ)

    real_default = real_default_data_dir()  # 1
    guard_data_dir(data_dir, real_default, resolved_settings_data_dir())  # 2

    token: str | None = None
    if opts.need_token:  # 3
        token_file = _resolved(opts.token_file or Path(DEFAULT_TOKEN_FILE))
        token = read_token(token_file)
    redactor = Redactor(token)

    home = run_dir / "home"
    (home / "workspace").mkdir(parents=True, exist_ok=True)  # the first thing created
    env = EvalEnv(run_dir=run_dir, data_dir=data_dir, home=home, token=token, redactor=redactor)
    env.log_redaction = LogRedaction(redactor)
    env.log_redaction.install()
    try:
        switch_home(home, env.saved_home)  # 4
        env.saved_data_dir = assign_data_dir(data_dir)  # 5
        sweep_stale(run_dir.parent)  # 6
        acquire_lock(run_dir)
        data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        env.conn = await init_database()  # 7
    except BaseException:
        await shutdown(env)
        raise
    return env


async def shutdown(env: EvalEnv) -> None:
    """Stop indexing, close the vector store, close the connection, delete ``data/``.

    Every step runs even if an earlier one fails; the first failure is re-raised last.
    """
    if env.closed:
        return
    env.closed = True
    first: BaseException | None = None
    cancelled: frozenset[str] = frozenset()

    async def step(coro: Any) -> None:
        nonlocal first
        try:
            await coro
        except Exception as exc:  # noqa: BLE001 - keep shutting down
            first = first or exc

    for m in env.managers:
        await step(m.drain())
        try:
            cancelled = cancelled | frozenset(m.cancelled_kb_ids())
        except Exception:  # noqa: BLE001
            pass
    try:
        from the_one.db import close_connection
        from the_one.vectors import close_vector_store

        await step(close_vector_store(skip_kb_ids=cancelled))
        await step(close_connection())
    except ImportError:
        pass
    shutil.rmtree(env.data_dir, ignore_errors=True)
    if _lock_pid(env.run_dir) == os.getpid():
        # Release: the file stays (it marks the directory as a run directory) but no longer
        # names a process, so a recycled PID can never make a finished run look owned.
        (env.run_dir / "owner.lock").write_text("released\n", encoding="utf-8")
    if env.saved_data_dir is not None:
        try:
            from the_one.config import settings

            settings.data_dir = env.saved_data_dir
        except Exception:  # noqa: BLE001
            pass
    restore_home(env.saved_home)
    if env.log_redaction is not None:
        env.log_redaction.uninstall()
    if first is not None:
        raise first
