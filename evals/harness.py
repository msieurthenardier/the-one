"""The per-run agent setup, clock and zone, tool-free wrapper and conversation driving.

Runs are in-process and sequential, against one scratch data directory per
invocation and one agent per run (DD3). Each run drives the real
``AgentFactory`` / prompt assembly / agent loop the way
``the_one/interfaces/cli.py::_run_cli`` does, with a fresh ``TurnContext`` around
every ``agent.step``. A conversation boundary calls ``AgentFactory.create`` again
for the same agent name, so a fresh ``Agent`` is built with a freshly built system
prompt that reads that run's notes from the same database.

Two module globals are patched, which is why runs are sequential:

- ``the_one.agent.factory.get_provider`` (DD6, DD18), scoped to ``create()`` only:
  it returns the real provider (``tools_off`` overrides the instance's async
  ``supports_tools`` to return False) or a scripted one, and records calls.
- ``the_one.time_zones.utcnow`` / ``detect_system_zone`` (DD8), active across
  every ``create()`` AND every ``agent.step`` of a run, because the
  ``current_time`` tool reads ``time_zones.utcnow`` at call time; restored in a
  ``finally`` at run end.

Containment (DD19): ``HOME`` is the scratch home (set by ``env.startup``); the
filesystem tools' ``path_allowlist`` is narrowed to it; ``web_search`` and
``download_file`` are disabled; ``fetch_url`` / ``http_request`` reach only the
fixture host. The execution tools (``shell``, ``python_exec``, the four
``shell_session_*``) are DISABLED for eval agents: ``host_access`` is a plain tool
argument in ``shell.py`` / ``python_exec.py`` / ``sessions.py`` and no
``ExecutionConfig`` field can refuse it, so a model could escape the box.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from evals.checks import CheckDecl, NoteView, RoutineView, RunTrace, TurnTrace
from evals.env import EvalRefusalError
from evals.fixtures import (
    FIXTURE_HOST,
    FIXTURE_HOSTNAME,
    NONCE_PATH,
    FixtureServer,
    KBFixtures,
)
from evals.models import Preset, effective_values, provider_row
from evals.scenario import PageTurn, Scenario, StepTurn, Variant, expand

FS_TOOLS = (
    "read_file",
    "write_file",
    "edit_file",
    "delete_file",
    "move_file",
    "mkdir",
    "glob",
    "grep",
    "list_dir",
)
EXEC_TOOLS = (
    "shell",
    "python_exec",
    "shell_session_start",
    "shell_session_send",
    "shell_session_close",
    "shell_session_list",
)
DISABLED_TOOLS = (*EXEC_TOOLS, "web_search", "download_file")
WEB_TOOLS = ("http_request", "fetch_url")
EXECUTION_TOOLS_STATE = "disabled"

DEFAULT_TURN_TIMEOUT_S = 900.0
_TOOL_TIMEOUT = re.compile(r"^tool \S+ timed out after \d+s")


@dataclass(frozen=True)
class RunSpec:
    scenario: Scenario
    variant: Variant
    model: str
    attempt: int = 1

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.scenario.id, self.model, self.variant.id)

    @property
    def agent_name(self) -> str:
        """``ev-{scenario}-{model}-{variant}-{attempt}`` (deterministic, <= 64 chars)."""
        full = f"ev-{self.scenario.id}-{self.model}-{self.variant.id}-{self.attempt}"
        full = re.sub(r"[^A-Za-z0-9_-]", "-", full)
        if len(full) <= 64:
            return full
        digest = hashlib.sha256(full.encode()).hexdigest()[:8]
        return f"{full[:55]}-{digest}"

    @property
    def stem(self) -> str:
        s, m, v = self.key
        return f"{s}__{m}__{v}__a{self.attempt}"


@dataclass
class CallRecorder:
    """Record-only view of the calls a provider receives (no behaviour change)."""

    calls: list[dict[str, Any]] = field(default_factory=list)
    starting_schemas: list[dict[str, Any]] | None = None
    systems: list[str] = field(default_factory=list)
    llm: Any = None
    conversation: int = 0
    _seen_conversations: set[int] = field(default_factory=set)

    def attach(self, llm: Any) -> None:
        self.llm = llm
        if getattr(llm, "_evals_recorded", False):
            return
        orig = llm.stream
        rec = self

        async def stream(*args: Any, **kwargs: Any):
            messages = kwargs.get("messages", args[0] if args else None) or []
            tools = kwargs.get("tools", args[1] if len(args) > 1 else None)
            rec._note(messages, tools)
            async for chunk in orig(*args, **kwargs):
                yield chunk

        llm.stream = stream
        llm._evals_recorded = True

    def _note(self, messages: list[Any], tools: list[dict[str, Any]] | None) -> None:
        system = None
        if messages and getattr(messages[0].role, "value", None) == "system":
            system = messages[0].content
        if self.conversation not in self._seen_conversations:
            self._seen_conversations.add(self.conversation)
            self.systems.append(system if isinstance(system, str) else "")
        if self.starting_schemas is None:
            self.starting_schemas = [dict(t) for t in (tools or [])]
        self.calls.append(
            {
                "conversation": self.conversation,
                "n_messages": len(messages),
                "tools": [t.get("name") for t in (tools or [])],
            }
        )


@dataclass
class Attempt:
    """Everything one attempt at a run produced, including what a failure left behind."""

    trace: RunTrace
    recorder: CallRecorder
    exc: BaseException | None = None
    model_failure: str | None = None
    wall_s: float = 0.0
    turn_s: list[float] = field(default_factory=list)
    effective: dict[str, Any] = field(default_factory=dict)
    fixture_requests: list[tuple[str, str]] = field(default_factory=list)
    notes: list[dict[str, Any]] = field(default_factory=list)
    # Captured at the run's first ``factory.create`` (leg 1 of sortie 11): the registry's schemas
    # in registry order, whether the agent is connector-bound, and the exposure record the agent
    # carries (``ToolExposure.to_dict()``, or None when the agent has none).
    registry_schemas: list[dict[str, Any]] | None = None
    connector_bound: bool = False
    exposure: dict[str, Any] | None = None


async def _supports_no_tools() -> bool:
    return False


@contextlib.contextmanager
def fixture_host_patch(port: int):
    """Rewrite requests to ``FIXTURE_HOSTNAME`` onto the loopback fixture server (DD4).

    Wraps ``httpx.AsyncHTTPTransport.handle_async_request``. ``SSRFGuardedTransport`` reaches
    that method through ``super()`` only after its host policy check and its
    ``extra_allowed_hosts`` branch, so the rewrite sits behind the real policy for every web
    tool. A request whose host is another name passes through untouched. The rewrite builds a
    NEW request (the caller's keeps its hostname, so a relative redirect resolves against the
    name and ``response.url`` keeps it). Class-level and process-wide: restored in a
    ``finally``, which is why runs are sequential.
    """
    import httpx

    original = httpx.AsyncHTTPTransport.handle_async_request

    async def rewriting(self: Any, request: httpx.Request) -> httpx.Response:
        if request.url.host == FIXTURE_HOSTNAME:
            request = httpx.Request(
                request.method,
                request.url.copy_with(host=FIXTURE_HOST, port=port),
                headers=httpx.Headers(request.headers),  # Host is kept: the original netloc
                stream=request.stream,
                extensions=request.extensions,
            )
        return await original(self, request)

    httpx.AsyncHTTPTransport.handle_async_request = rewriting  # type: ignore[method-assign]
    try:
        yield
    finally:
        httpx.AsyncHTTPTransport.handle_async_request = original  # type: ignore[method-assign]


@contextlib.contextmanager
def provider_patch(*, tools_off: bool, scripted: Any, recorder: CallRecorder):
    """Scoped to ``AgentFactory.create`` only (DD6, DD18)."""
    from the_one.agent import factory as factory_mod

    original = factory_mod.get_provider

    def patched(name: str, **kwargs: Any) -> Any:
        llm = scripted if scripted is not None else original(name, **kwargs)
        if tools_off:
            llm.supports_tools = _supports_no_tools
        recorder.attach(llm)
        return llm

    factory_mod.get_provider = patched
    try:
        yield
    finally:
        factory_mod.get_provider = original


@contextlib.contextmanager
def clock_patch(instant: datetime, host_zone: str):
    """Hold the clock at ``instant`` for a whole run (create() and every step)."""
    from the_one import time_zones

    orig_utcnow, orig_detect = time_zones.utcnow, time_zones.detect_system_zone
    time_zones.utcnow = lambda: instant
    time_zones.detect_system_zone = lambda: host_zone
    try:
        yield
    finally:
        time_zones.utcnow = orig_utcnow
        time_zones.detect_system_zone = orig_detect


def expected_date_lines(sc: Scenario, variant: Variant | None = None) -> list[str]:
    from the_one import time_zones

    eff = time_zones.EffectiveZone(sc.zone, ZoneInfo(sc.zone))
    wordings = [False] if sc.tools_off else [True, False]
    return [time_zones.date_line(sc.instant_for(variant), eff, tool_available=w) for w in wordings]


class Harness:
    def __init__(
        self,
        env: Any,
        presets: dict[str, Preset],
        *,
        fixture_server: FixtureServer | None = None,
        kb: KBFixtures | None = None,
        model_info: dict[str, dict[str, Any]] | None = None,
        provider_hook: Callable[[RunSpec, str], Any] | None = None,
        turn_timeout: float = DEFAULT_TURN_TIMEOUT_S,
    ) -> None:
        self.env = env
        self.presets = presets
        self.fixture_server = fixture_server
        self.kb = kb
        self.model_info = model_info or {}
        self.provider_hook = provider_hook
        self.turn_timeout = turn_timeout
        self._stack = contextlib.ExitStack()
        # A builder run's seeded ``[app]`` rows ("agent" name / "mcp" id / "secret" id) and
        # secret-bearing values, reset at the top of every builder ``_seed``.
        self._app_rows: list[tuple[str, str]] = []
        self._run_secrets: list[str] = []
        # M36 F2 L9: the agent names that existed before a builder run's seeding (None: no run
        # in flight) and the run's chat session ids, so the run's proposals and any agent an
        # approved proposal created are removed again (``_clean_proposal_state``).
        self._agent_snapshot: set[str] | None = None
        self._proposal_sessions: list[str] = []

    @property
    def fixture_base(self) -> str:
        return self.fixture_server.base_url if self.fixture_server else ""

    def close(self) -> None:
        """Leave the fixture-host rewrite (idempotent). Call in the invocation's ``finally``."""
        self._stack.close()

    async def setup(self) -> None:
        """Write the provider rows and the containment ToolConfig rows (once per invocation).

        With a fixture server this also enters the hostname rewrite (kept until ``close()``) and
        runs the nonce self-test; a refusal closes the rewrite before it propagates.
        """
        from the_one.config import settings
        from the_one.db.connection import get_connection
        from the_one.db.repositories import LLMProviderRepository, ToolConfigRepository
        from the_one.encryption import get_encryptor

        if self.fixture_server is not None:
            self._stack.enter_context(fixture_host_patch(self.fixture_server.port))
        try:
            conn = await get_connection()
            enc = get_encryptor(settings.data_dir)
            providers = LLMProviderRepository(conn, enc)
            for preset in self.presets.values():
                await providers.create(provider_row(preset, self.env.token))
            tools = ToolConfigRepository(conn, enc)
            home = str(self.env.home)
            for name in FS_TOOLS:
                await tools.upsert(name, {"path_allowlist": [home]})
            for name in WEB_TOOLS:
                await tools.upsert(
                    name,
                    {
                        "extra_allowed_hosts": [FIXTURE_HOSTNAME],
                        "host_allowlist": [FIXTURE_HOSTNAME],
                    },
                )
            for name in DISABLED_TOOLS:
                await tools.upsert(name, {}, enabled=False)
            if self.fixture_server is not None:
                await self._self_test()
        except BaseException:
            self.close()
            raise

    async def _self_test(self) -> None:
        """Fetch a per-invocation nonce through the REAL ``fetch_url`` (DD4).

        The tool is built the way the factory builds it, from the ``WebConfig`` the scratch
        database now holds, so a policy refusal or a failed rewrite shows up here, at start,
        and not as a model "failure" in every run. Anything but ``"[200]\\n" + nonce`` refuses.
        """
        from the_one.config import settings
        from the_one.db.connection import get_connection
        from the_one.db.repositories import ToolConfigRepository
        from the_one.encryption import get_encryptor
        from the_one.tools.builtins import BuiltinToolProvider

        assert self.fixture_server is not None
        nonce = self.fixture_server.nonce
        url = f"{self.fixture_server.base_url}{NONCE_PATH}"
        try:
            repo = ToolConfigRepository(await get_connection(), get_encryptor(settings.data_dir))
            configs = {c.name: c.merged_config() for c in await repo.list()}
            tools = BuiltinToolProvider().get_tools(configs, {}, agent_name="evals-self-test")
            tool = next(t for t in tools if t.name == "fetch_url")
            got = await tool.execute(url=url)
        except Exception as exc:  # noqa: BLE001 - every failure is a refusal
            raise EvalRefusalError(
                "refusing to run: the fixture hostname rewrite failed its self-test "
                f"({type(exc).__name__}: {exc})"
            ) from exc
        if got != f"[200]\n{nonce}":
            shown = got if len(got) <= 80 else got[:80] + "..."
            raise EvalRefusalError(
                "refusing to run: the fixture hostname rewrite failed its self-test "
                f"(fetching {url} returned {shown!r}, not the nonce)"
            )

    async def discard_agent(self, name: str) -> None:
        """Remove a partial attempt's agent (and, by cascade, its notes and rules)."""
        from the_one.db.connection import get_connection
        from the_one.db.repositories import SQLiteAgentStore
        from the_one.naming import GLEEPGLORP_AGENT_NAME

        if name == GLEEPGLORP_AGENT_NAME:
            return  # no agents row; the next builder ``_seed`` resets its state
        store = SQLiteAgentStore(await get_connection())
        if await store.exists(name):
            await store.delete(name)

    async def _seed(self, spec: RunSpec) -> set[str]:
        """Create the agent, its rules and seeded notes. Returns the seeded note ids."""
        from the_one import time_zones
        from the_one.agent.config import AgentConfig
        from the_one.db.connection import get_connection
        from the_one.db.repositories import (
            AgentNoteRepository,
            AgentRuleRepository,
            SQLiteAgentStore,
        )

        sc = spec.scenario
        preset = self.presets[spec.model]
        conn = await get_connection()
        if sc.kbs and self.kb is None:
            raise RuntimeError("scenario attaches a knowledge base but no KB fixtures are set up")
        kb_ids = [await self.kb.ensure(ref) for ref in sc.kbs] if sc.kbs else []
        await time_zones.save_setting(conn, time_zones.TimeZoneSetting(mode="zone", zone=sc.zone))
        if sc.builder == "gleepglorp":
            return await self._seed_gleepglorp(spec, conn)
        cfg = AgentConfig(
            name=spec.agent_name,
            description=f"eval run {spec.stem}",
            provider_config_id=preset.provider_id,
            llm_model=preset.model,
            system_prompt=sc.persona,
            kb_ids=kb_ids,
            notes_enabled=sc.notes_enabled,
            **({"max_iterations": sc.max_iterations} if sc.max_iterations else {}),
            **({"rich_visuals": sc.rich_visuals} if sc.rich_visuals is not None else {}),
        )
        store = SQLiteAgentStore(conn)
        await store.save(cfg)
        if sc.routines_enabled:
            # Operator-owned switches (M33 F2): on, and writes apply so they can be checked.
            await store.set_routines_self_config(
                spec.agent_name, enabled=True, requires_approval=False
            )
        rules = AgentRuleRepository(conn)
        mapping = {**spec.variant.mapping, "fixture_base": self.fixture_base}
        for text in sc.rules:
            await rules.create(spec.agent_name, expand(text, mapping))
        seeded: set[str] = set()
        notes = AgentNoteRepository(conn)
        for seed in sc.seeded_notes:
            note, _created = await notes.create(
                spec.agent_name,
                expand(seed.text, mapping),
                untrusted=seed.untrusted,
                sources=["seeded"] if seed.untrusted else [],
                origin_kind="other",
                origin_session_id=None,
                origin_label="seeded",
                origin_platform=None,
                origin_peer_id=None,
                origin_peer_name=None,
            )
            seeded.add(note.id)
        return seeded

    def agent_for(self, spec: RunSpec) -> str:
        """The name of the agent a run builds: ``spec.agent_name`` for a stored agent, the
        built-in assistant's own name for a ``builder = "gleepglorp"`` scenario (the session id
        stem keeps ``spec.stem``)."""
        if spec.scenario.builder == "gleepglorp":
            from the_one.naming import GLEEPGLORP_AGENT_NAME

            return GLEEPGLORP_AGENT_NAME
        return spec.agent_name

    async def _remove_app_rows(self) -> None:
        """Delete the ``[app]`` rows the last builder run seeded (agents, MCP servers, secrets)."""
        from the_one.config import settings
        from the_one.db.connection import get_connection
        from the_one.db.repositories import (
            MCPSourceRepository,
            SecretRepository,
            SQLiteAgentStore,
        )
        from the_one.encryption import get_encryptor

        rows, self._app_rows = self._app_rows, []
        if not rows:
            return
        conn = await get_connection()
        enc = get_encryptor(settings.data_dir)
        for kind, key in rows:
            if kind == "agent":
                store = SQLiteAgentStore(conn)
                if await store.exists(key):
                    await store.delete(key)
            elif kind == "mcp":
                await MCPSourceRepository(conn, enc).delete(key)
            elif kind == "secret":
                await SecretRepository(conn, enc).delete(key)

    async def _seed_gleepglorp(self, spec: RunSpec, conn: Any) -> set[str]:
        """Seed a ``builder = "gleepglorp"`` run. GleepGlorp is one singleton per data directory,
        so state is RESET first, on every attempt (a transient retry included): its notes are
        cleared (the counter is left, so note numbers drift between runs and no check names one)
        and the previous run's ``[app]`` rows are removed; then ready settings are written, the
        seeded notes and the ``[app]`` rows go in. Returns the seeded note ids."""
        from the_one.agent.config import AgentConfig
        from the_one.config import settings
        from the_one.db.models import MCPSource
        from the_one.db.repositories import (
            MCPSourceRepository,
            SecretRepository,
            SQLiteAgentStore,
        )
        from the_one.encryption import get_encryptor
        from the_one.gleepglorp import GleepGlorpSettings, save_settings
        from the_one.gleepglorp.notes import GleepGlorpNoteRepository
        from the_one.naming import GLEEPGLORP_AGENT_NAME

        sc = spec.scenario
        preset = self.presets[spec.model]
        await self._remove_app_rows()
        # The pre-seed reset: the previous run's proposals, and any agent its approvals created,
        # go (a transient retry, or a run that never reached its ``finally``).
        await self._clean_proposal_state(conn)
        notes = GleepGlorpNoteRepository(conn)
        await notes.clear()
        self._run_secrets = []
        # The snapshot is taken after the reset and before seeding.
        self._agent_snapshot = await _agent_name_set(conn)
        self._proposal_sessions = [f"ev-{spec.stem}-c{ci}" for ci in range(len(sc.conversations))]
        # Named fields (the model is ``extra="forbid"``). The provider row exists from setup(),
        # so the state is ``ready`` and ``provider_patch`` (which swaps only get_provider) applies.
        await save_settings(
            conn,
            GleepGlorpSettings(
                enabled=True,
                provider_config_id=preset.provider_id,
                model=preset.model,
                web_access=sc.web_access,
                memory=sc.notes_enabled,
            ),
        )
        mapping = {**spec.variant.mapping, "fixture_base": self.fixture_base}

        def x(text: str) -> str:
            return expand(text, mapping)

        enc = get_encryptor(settings.data_dir)
        # Row shapes are the ones the app's own repositories take: ``AgentConfig`` for the agent
        # store, ``MCPSource`` (config: command/args/env or url/headers) for MCPSourceRepository,
        # ``SecretRepository.create(name, description, allowed_tools, [{key, value}])``.
        store = SQLiteAgentStore(conn)
        for ag in sc.app.agents:
            await store.save(
                AgentConfig(
                    name=x(ag.name),
                    description=x(ag.description),
                    system_prompt=x(ag.system_prompt),
                    provider_config_id=preset.provider_id,
                    llm_model=preset.model,
                )
            )
            self._app_rows.append(("agent", x(ag.name)))
        mcps = MCPSourceRepository(conn, enc)
        for srv in sc.app.mcp_servers:
            if srv.type == "stdio":
                config: dict[str, Any] = {
                    "command": x(srv.command),
                    "args": [x(a) for a in srv.args],
                    "env": {k: x(v) for k, v in srv.env},
                }
            else:
                config = {"url": x(srv.url), "headers": {k: x(v) for k, v in srv.headers}}
            row_id = f"ev-mcp-{len(self._app_rows)}"
            await mcps.create(MCPSource(id=row_id, name=x(srv.name), type=srv.type, config=config))
            self._app_rows.append(("mcp", row_id))
            self._run_secrets += [x(v) for _k, v in (*srv.headers, *srv.env)]
        secrets = SecretRepository(conn, enc)
        for sec in sc.app.secrets:
            made = await secrets.create(
                x(sec.name),
                x(sec.description),
                list(sec.allowed_tools),
                [{"key": x(k), "value": x(v)} for k, v in sec.values],
            )
            self._app_rows.append(("secret", made.id))
            self._run_secrets += [x(v) for _k, v in sec.values]
        seeded: set[str] = set()
        for seed in sc.seeded_notes:
            note, _created = await notes.create(
                GLEEPGLORP_AGENT_NAME,
                x(seed.text),
                untrusted=seed.untrusted,
                sources=["seeded"] if seed.untrusted else [],
                origin_kind="other",
                origin_session_id=None,
                origin_label="seeded",
                origin_platform=None,
                origin_peer_id=None,
                origin_peer_name=None,
            )
            seeded.add(note.id)
        return seeded

    async def _clean_proposal_state(self, conn: Any) -> None:
        """Delete the run's ``gleepglorp_proposals`` rows (no foreign key, so explicitly) and every
        agent absent from the pre-seed snapshot (an approved proposal made it; its rules and
        routines go by cascade). Idempotent; resets the run's bookkeeping."""
        from the_one.db._write_lock import write_transaction
        from the_one.db.repositories import SQLiteAgentStore

        sessions, self._proposal_sessions = self._proposal_sessions, []
        snapshot, self._agent_snapshot = self._agent_snapshot, None
        if sessions:
            marks = ", ".join("?" for _ in sessions)
            async with write_transaction(conn):
                await conn.execute(
                    f"DELETE FROM gleepglorp_proposals WHERE session_id IN ({marks})",  # noqa: S608
                    sessions,
                )
        if snapshot is not None:
            store = SQLiteAgentStore(conn)
            for name in sorted(await _agent_name_set(conn) - snapshot):
                if await store.exists(name):
                    await store.delete(name)

    async def _write_deps(self, conn: Any) -> Any:
        """The agent write services' repositories, built the way the approve route builds them
        (``api._agent_write_deps``) without importing the web layer. The store carries the
        encryptor, as the route's does (the harness's own store has none)."""
        from the_one.agent.service import AgentWriteDeps
        from the_one.config import settings
        from the_one.db.repositories import (
            LLMProviderRepository,
            MCPSourceRepository,
            SecretRepository,
            SQLiteAgentStore,
            ToolConfigRepository,
        )
        from the_one.encryption import get_encryptor
        from the_one.mcp.override_validation import validate_mcp_overrides

        enc = get_encryptor(settings.data_dir)
        return AgentWriteDeps(
            store=SQLiteAgentStore(conn, enc),
            mcp_repo=MCPSourceRepository(conn, enc),
            provider_repo=LLMProviderRepository(conn, enc),
            secret_repo=SecretRepository(conn, enc),
            tool_config_repo=ToolConfigRepository(conn, enc),
            override_validator=validate_mcp_overrides,
        )

    async def _decide(
        self, conn: Any, step: StepTurn, session_id: str, tt: TurnTrace
    ) -> str | None:
        """Run an approve or dismiss step on the conversation's open proposal.

        Returns the continuation text to send as the turn's user message, or ``None`` when the
        step sent none: nothing was open or the apply did not succeed (``tt.approve_outcome`` is
        ``none_open``, ``stale``, ``failed`` or ``gone``, and the caller ends the conversation).
        The apply is the app's own ``apply_proposal(..., continue_chat=False)``, the harness
        driving the continuation itself; its frames go to no socket."""
        from the_one import time_zones
        from the_one.gleepglorp.proposals import continuation
        from the_one.gleepglorp.proposals.apply import apply_proposal, dismiss_proposal
        from the_one.gleepglorp.proposals.store import GleepGlorpProposalRepository

        open_proposal = await GleepGlorpProposalRepository(conn).open_for_session(session_id)
        if open_proposal is None:
            tt.approve_outcome = "none_open"
            return None
        tt.proposal_id = open_proposal.id
        if step.kind == "dismiss":
            res = await dismiss_proposal(conn, open_proposal.id, continue_chat=False)
            if res.outcome != "dismissed":
                tt.approve_outcome = "failed"
                return None
            tt.approve_outcome = "dismissed"
            return continuation.dismissal_text(
                open_proposal.id, continuation.proposal_title(open_proposal)
            )

        async def zone() -> Any:
            return (await time_zones.load_effective_zone(conn)).tzinfo

        res = await apply_proposal(
            conn,
            await self._write_deps(conn),
            open_proposal.id,
            override=False,
            now=time_zones.utcnow(),
            zone=zone,
            continue_chat=False,
        )
        if res.outcome != "applied" or res.view is None:
            tt.approve_outcome = (
                res.outcome if res.outcome in ("stale", "failed", "gone") else "failed"
            )
            return None
        tt.approve_outcome = "applied"
        summary = (res.view.get("result") or {}).get("summary", "")
        return continuation.approval_text(open_proposal.id, summary)

    async def _collect_proposals(
        self, conn: Any, sessions: list[str], turn_of: dict[int, int]
    ) -> list[dict[str, Any]]:
        """The run's proposals as plain views, in id order (``RunTrace.proposals``)."""
        from the_one.gleepglorp.proposals.store import GleepGlorpProposalRepository, proposal_view

        repo = GleepGlorpProposalRepository(conn)
        out: list[dict[str, Any]] = []
        for sid in sessions:
            for p in await repo.list_for_session(sid):
                view = await proposal_view(conn, p)
                out.append(
                    {
                        "id": p.id,
                        "kind": p.kind,
                        "action": p.action,
                        "agent_name": p.agent_name,
                        "changes": p.changes,
                        "display": view["changes"],
                        "status": p.status,
                        "untrusted": p.untrusted,
                        "untrusted_sources": p.untrusted_sources,
                        "tool_call_id": p.tool_call_id,
                        "turn": turn_of.get(p.id),
                        "applied_result": p.result if p.status == "applied" else None,
                    }
                )
        return sorted(out, key=lambda v: v["id"])

    async def _collect_routines(self, agent_name: str) -> list[RoutineView]:
        """The routines the run's agent left in the database (the stored columns)."""
        from the_one.db.connection import get_connection
        from the_one.routines.repository import AgentRoutineRepository

        rows = await AgentRoutineRepository(await get_connection()).list_for_agent(agent_name)
        return [
            RoutineView(
                name=r.name,
                kind=_schedule_class(r.schedule),
                next_run_at=r.next_run_at,
                created_by=r.created_by,
                untrusted=r.untrusted,
            )
            for r in rows
        ]

    async def run_once(self, spec: RunSpec) -> Attempt:
        """One attempt at a run. Model and provider exceptions are captured, not raised."""
        from the_one.agent._context import TurnContext, current_turn
        from the_one.agent.factory import AgentFactory
        from the_one.db.connection import get_connection
        from the_one.db.repositories import AgentNoteRepository, SQLiteAgentStore

        sc = spec.scenario
        agent_name = self.agent_for(spec)
        builder = sc.builder == "gleepglorp"
        inst = sc.instantiate(spec.variant, self.fixture_base)
        recorder = CallRecorder()
        trace = RunTrace(
            date_lines=expected_date_lines(sc, spec.variant),
            instant=sc.instant_for(spec.variant),
            routines_enabled=sc.routines_enabled,
        )
        attempt = Attempt(trace=trace, recorder=recorder)
        scripted = self.provider_hook(spec, self.fixture_base) if self.provider_hook else None
        fixture_mark = len(self.fixture_server.requests) if self.fixture_server else 0
        seeded: set[str] = set()
        proposal_turns: dict[int, int] = {}  # proposal id -> the run-global turn that made it
        t_run = time.monotonic()
        agent = None
        with clock_patch(sc.instant_for(spec.variant), sc.host_zone):
            try:
                seeded = await self._seed(spec)
                trace.seeded_secrets = list(self._run_secrets) if builder else []
                conn = await get_connection()
                factory = AgentFactory(store=SQLiteAgentStore(conn))
                turn_index = 0
                for ci, turns in enumerate(inst.conversations):
                    recorder.conversation = ci
                    with provider_patch(
                        tools_off=sc.tools_off, scripted=scripted, recorder=recorder
                    ):
                        agent = await factory.create(agent_name)
                    trace.system_prompts.append(agent.system_prompt)
                    if attempt.registry_schemas is None:
                        from the_one.db.repositories import agent_names_in_use

                        attempt.registry_schemas = [dict(s) for s in agent.tools.all_schemas()]
                        attempt.connector_bound = agent_name in await agent_names_in_use(conn)
                        exp = getattr(agent, "tool_exposure", None)
                        attempt.exposure = exp.to_dict() if exp is not None else None
                    session_id = f"ev-{spec.stem}-c{ci}"
                    attempt.effective = effective_values(agent.llm)
                    for turn in turns:
                        is_step = isinstance(turn, StepTurn)
                        is_page = isinstance(turn, PageTurn)
                        tt = TurnTrace(
                            conversation=ci,
                            index=turn_index,
                            user="" if is_step else (turn.text if is_page else turn),
                            skip_empty_reply=sc.skip_empty_final_reply,
                            step=turn.kind if is_step else None,
                            page=dict(turn.page) if is_page else None,
                        )
                        trace.turns.append(tt)
                        turn_index += 1
                        known = await _proposal_status(conn, session_id) if builder else {}
                        text: str | None = tt.user
                        t0 = time.monotonic()
                        if is_step:
                            # The operator's decision, through the app's own apply path. A step
                            # that sends no text (nothing open, or the apply did not succeed)
                            # ends the conversation and is never a model failure.
                            text = await self._decide(conn, turn, session_id, tt)
                            tt.user = text or ""
                            if text is None:
                                attempt.turn_s.append(round(time.monotonic() - t0, 3))
                                await _note_proposals(conn, session_id, known, tt, proposal_turns)
                                break
                        # A page turn only: the keyword and the context page are passed only
                        # when there is a page, as the app does.
                        page_kw: dict[str, Any] = {}
                        turn_ctx = TurnContext(session_id=session_id)
                        if tt.page:
                            page_kw = {"page": {"line": tt.page["line"]}}
                            turn_ctx.page = {
                                "line": tt.page["line"],
                                "descriptor": tt.page.get("descriptor"),
                            }
                        token = current_turn.set(turn_ctx)
                        try:
                            async with asyncio.timeout(self.turn_timeout):
                                async for msg in agent.step(text, **page_kw):
                                    tt.messages.append(msg)
                        except TimeoutError:
                            attempt.model_failure = f"turn timed out after {self.turn_timeout:.0f}s"
                        finally:
                            current_turn.reset(token)
                            attempt.turn_s.append(round(time.monotonic() - t0, 3))
                            if builder:
                                await _note_proposals(conn, session_id, known, tt, proposal_turns)
                        if attempt.model_failure:
                            break
                        if not tt.has_final_reply:
                            attempt.model_failure = "max_iterations exhausted with no final reply"
                            break
                        timed_out = _first_tool_timeout(tt)
                        if timed_out:
                            attempt.model_failure = timed_out
                            break
                    attempt.effective = effective_values(agent.llm)
                    await agent.aclose()
                    agent = None
                    if attempt.model_failure:
                        break
            except Exception as exc:  # noqa: BLE001 - classified by the caller
                attempt.exc = exc
            finally:
                if agent is not None:
                    with contextlib.suppress(Exception):
                        attempt.effective = effective_values(agent.llm)
                        await agent.aclose()
                try:
                    conn = await get_connection()
                    if builder:
                        from the_one.gleepglorp.notes import GleepGlorpNoteRepository

                        stored = await GleepGlorpNoteRepository(conn).list_for_agent()
                    else:
                        stored = await AgentNoteRepository(conn).list_for_agent(agent_name)
                    for n in stored:
                        if n.id in seeded:
                            continue
                        trace.saved_notes.append(NoteView(n.text, n.untrusted, n.untrusted_sources))
                        attempt.notes.append(
                            {
                                "text": n.text,
                                "untrusted": n.untrusted,
                                "sources": n.untrusted_sources,
                            }
                        )
                except Exception as exc:  # noqa: BLE001 - note collection must not mask the run
                    attempt.exc = attempt.exc or exc
                if sc.routines_enabled:
                    try:
                        trace.routines = await self._collect_routines(agent_name)
                    except Exception as exc:  # noqa: BLE001 - must not mask the run
                        attempt.exc = attempt.exc or exc
                if builder:
                    try:
                        trace.proposals = await self._collect_proposals(
                            await get_connection(),
                            [f"ev-{spec.stem}-c{ci}" for ci in range(len(inst.conversations))],
                            proposal_turns,
                        )
                    except Exception as exc:  # noqa: BLE001 - must not mask the run
                        attempt.exc = attempt.exc or exc
                if builder:
                    # The run's [app] rows go again (the next seed removes them too, so a run
                    # that never got here leaves nothing the next one can see), and so do its
                    # proposals and any agent an approved proposal created.
                    try:
                        await self._remove_app_rows()
                        await self._clean_proposal_state(await get_connection())
                    except Exception as exc:  # noqa: BLE001 - must not mask the run
                        attempt.exc = attempt.exc or exc
        attempt.wall_s = round(time.monotonic() - t_run, 3)
        if self.fixture_server:
            attempt.fixture_requests = list(self.fixture_server.requests[fixture_mark:])
        trace.fixture_requests = list(attempt.fixture_requests)
        return attempt


async def _proposal_status(conn: Any, session_id: str) -> dict[int, str]:
    """``{proposal id: status}`` for a chat's proposals (the snapshot a turn is attributed by)."""
    from the_one.gleepglorp.proposals.store import GleepGlorpProposalRepository

    rows = await GleepGlorpProposalRepository(conn).list_for_session(session_id)
    return {p.id: p.status for p in rows}


async def _note_proposals(
    conn: Any, session_id: str, before: dict[int, str], tt: TurnTrace, turn_of: dict[int, int]
) -> None:
    """After a turn: attribute the proposals new since ``before`` to it (a snapshot, because tool
    call ids repeat) and record how many of the chat's proposals are still open."""
    now = await _proposal_status(conn, session_id)
    for pid in now:
        if pid not in before:
            turn_of[pid] = tt.index
    tt.open_proposals = sum(1 for s in now.values() if s in ("pending", "failed"))


async def _agent_name_set(conn: Any) -> set[str]:
    async with conn.execute("SELECT name FROM agents") as cur:
        return {r[0] for r in await cur.fetchall()}


def _schedule_class(schedule: dict) -> str:
    """Classify a stored schedule for the checks: the output name ``RoutineView.kind`` carries.

    ``repeat`` null is ``once``; every 1 day is ``daily``; every 1 week on exactly Monday to
    Friday is ``weekdays``, on other days ``weekly``; every N hours is ``interval``; anything
    else is the unit name. ``ends`` is ignored, so a series that stops reads as its kind."""
    repeat = schedule.get("repeat")
    if repeat is None:
        return "once"
    unit, every = repeat.get("unit"), repeat.get("every")
    if unit == "day" and every == 1:
        return "daily"
    if unit == "week" and every == 1:
        return "weekdays" if repeat.get("days") == [0, 1, 2, 3, 4] else "weekly"
    if unit == "hour":
        return "interval"
    return str(unit)


def _first_tool_timeout(tt: TurnTrace) -> str | None:
    for m in tt.messages:
        tr = m.tool_result
        if tr is not None and tr.is_error and _TOOL_TIMEOUT.match(str(tr.content)):
            return "tool call timed out"
    return None


def off_fixture_fetches(trace: RunTrace) -> list[str]:
    """Targets of fetch_url / http_request calls aimed at any host but the fixture server."""
    out = []
    for tc in trace.tool_calls():
        if tc.name in WEB_TOOLS:
            url = str(tc.arguments.get("url", ""))
            if urlparse(url).hostname != FIXTURE_HOSTNAME:
                out.append(url)
    return out


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


__all__ = [
    "Attempt",
    "CheckDecl",
    "Harness",
    "RunSpec",
    "clock_patch",
    "expected_date_lines",
    "fixture_host_patch",
    "off_fixture_fetches",
    "provider_patch",
]
