"""Declarative scenarios (DD2) read with ``tomllib``.

A scenario file declares: ``id``, ``class`` and ``description``; the agent setup
(``[agent]``: persona, ``notes_enabled``, ``routines_enabled``, ``rich_visuals``, rules,
seeded notes, knowledge-base fixtures, ``tools_off``, ``builder`` and ``web_access`` for the
built-in GleepGlorp assistant, with its ``[app]`` rows); the clock (``[clock]``);
``[variants]`` (phrasings x facts, DD9); one or more ``[[conversations]]`` (each a list of
user ``turns``; a new conversation means a freshly built agent); and ``[[checks]]``.

Placeholders ``{phrasing}``, a fact's keys and ``{fixture_base}`` are substituted
in turn text and in check parameters when a variant is instantiated. Unknown
``{names}`` are left untouched, so regexes such as ``a{2}`` are safe.

Every loader error is one line naming the file and the field.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from evals import checks as checks_mod
from evals.checks import CheckDecl

CLASSES = ("safety", "improve", "hold")  # a scenario's own class
# A check's class may also be ``report``: scored and shown, never gated and never in the outcome.
CHECK_CLASSES = (*CLASSES, "report")
DEFAULT_INSTANT = datetime(2026, 3, 2, 15, 0, 0, tzinfo=timezone.utc)
DEFAULT_ZONE = "Pacific/Kiritimati"  # UTC+14: separates the host date from the zone date
DEFAULT_HOST_ZONE = "America/Los_Angeles"

_TOP_KEYS = {
    "id",
    "class",
    "description",
    "agent",
    "app",
    "clock",
    "variants",
    "conversations",
    "checks",
}
_AGENT_KEYS = {
    "persona",
    "notes_enabled",
    "tools_off",
    "rules",
    "seeded_notes",
    "kb",
    "max_iterations",
    "routines_enabled",
    "rich_visuals",
    "builder",
    "web_access",
    "skip_empty_final_reply",
}
# The agent builders a scenario can name (``agent.builder``): the built-in GleepGlorp assistant.
BUILDERS = ("gleepglorp",)
# The ``[agent]`` keys a builder scenario may not set (the assistant has none of them).
_BUILDER_REFUSES = ("kb", "routines_enabled", "persona", "rules", "rich_visuals", "max_iterations")
_APP_KEYS = {"agents", "mcp_servers", "secrets"}
_MCP_TYPES = ("stdio", "streamable-http")
_CLOCK_KEYS = {"instant", "zone", "host_zone"}
_PLACEHOLDER = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


class ScenarioError(ValueError):
    """A scenario file is invalid. The message is one line: file, field, reason."""


@dataclass(frozen=True)
class KBRef:
    name: str  # the knowledge base's display name; its tool slug derives from it verbatim
    fixture: str  # directory name under fixtures/kb/


@dataclass(frozen=True)
class SeedNote:
    text: str
    untrusted: bool = False


@dataclass(frozen=True)
class AppAgent:
    """An ``agents`` row a builder scenario seeds (what the stored agent has: name, description,
    system prompt)."""

    name: str
    description: str = ""
    system_prompt: str = ""


@dataclass(frozen=True)
class AppMcp:
    """An ``mcp_sources`` row (``MCPSource``): a stdio server's command, args and ``env``, or a
    streamable-http server's url and ``headers``. Header and env values are credentials."""

    name: str
    type: str
    command: str = ""
    args: tuple[str, ...] = ()
    url: str = ""
    headers: tuple[tuple[str, str], ...] = ()
    env: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class AppSecret:
    """A Library secret (``SecretRepository.create``): name, description, key/value pairs and the
    tools it is allowed on."""

    name: str
    description: str = ""
    values: tuple[tuple[str, str], ...] = ()
    allowed_tools: tuple[str, ...] = ("http_request",)


@dataclass
class AppSeed:
    """The ``[app]`` table: rows GleepGlorp can read, seeded per run (placeholders expand)."""

    agents: list[AppAgent] = field(default_factory=list)
    mcp_servers: list[AppMcp] = field(default_factory=list)
    secrets: list[AppSecret] = field(default_factory=list)

    def empty(self) -> bool:
        return not (self.agents or self.mcp_servers or self.secrets)


@dataclass(frozen=True)
class Variant:
    id: str
    phrasing_index: int
    fact_index: int
    mapping: dict[str, str]


@dataclass(frozen=True)
class StepTurn:
    """A turn that is the operator's decision on the chat's open proposal, not a typed message:
    ``approve`` (``{approve = true}``) or ``dismiss`` (``{dismiss = true}``). The harness acts on
    it through the app's own apply path (M36 F2 L9)."""

    kind: str  # "approve" | "dismiss"


@dataclass(frozen=True)
class PageTurn:
    """A user turn sent from a page (M36 F3 L4): ``{text = "...", page = {line = "...",
    descriptor = {...}?}}``. ``page["line"]`` is the page line the app would have stored,
    ``page["descriptor"]`` (optional, checked with ``the_one.gleepglorp.page``) is what Leg 5's
    ``fill_form`` gate reads from ``TurnContext.page``."""

    text: str
    page: dict[str, Any]


Turn = str | StepTurn | PageTurn
STEP_KINDS = ("approve", "dismiss")
PAGE_TURN_KEYS = ("text", "page")


def is_user_turn(turn: Turn) -> bool:
    """True for a turn that is user text (one model call at least), False for a step."""
    return isinstance(turn, (str, PageTurn))


@dataclass
class Instance:
    """A scenario instantiated for one variant."""

    scenario: Scenario
    variant: Variant
    conversations: list[list[Turn]]
    checks: list[CheckDecl]


@dataclass
class Scenario:
    id: str
    klass: str
    description: str
    path: Path
    persona: str = ""
    notes_enabled: bool = False
    tools_off: bool = False
    routines_enabled: bool = False
    # None: omitted, so the product default (on) applies (Mission 35 F1 L4).
    rich_visuals: bool | None = None
    rules: list[str] = field(default_factory=list)
    seeded_notes: list[SeedNote] = field(default_factory=list)
    kbs: list[KBRef] = field(default_factory=list)
    max_iterations: int | None = None
    # ``agent.builder``: the name of the agent builder ("gleepglorp"), or None for a stored agent.
    builder: str | None = None
    web_access: bool = False  # builder scenarios only: the GleepGlorp ``web_access`` setting
    # Opt-in reply extraction: skip an empty closing assistant message (see ``TurnTrace.reply``).
    skip_empty_final_reply: bool = False
    app: AppSeed = field(default_factory=AppSeed)
    instant: datetime = DEFAULT_INSTANT
    zone: str = DEFAULT_ZONE
    host_zone: str = DEFAULT_HOST_ZONE
    phrasings: list[str] = field(default_factory=lambda: [""])
    facts: list[dict[str, str]] = field(default_factory=lambda: [{}])
    conversations: list[list[Turn]] = field(default_factory=list)
    raw_checks: list[dict[str, Any]] = field(default_factory=list)

    def variants(self) -> list[Variant]:
        """Distinct variants, fact-set major so a small n covers one fact across phrasings."""
        out = []
        for fi, fact in enumerate(self.facts):
            for pi, phrasing in enumerate(self.phrasings):
                out.append(
                    Variant(
                        id=f"f{fi}p{pi}",
                        phrasing_index=pi,
                        fact_index=fi,
                        mapping={**fact, "phrasing": phrasing},
                    )
                )
        return out

    def instant_for(self, variant: Variant | None) -> datetime:
        """The frozen instant for a variant: its fact's ``instant`` key, else the scenario's."""
        raw = variant.mapping.get("instant") if variant else None
        if not raw:
            return self.instant
        return _parse_instant(self.path, raw)

    def cells(self) -> list[str]:
        seen: list[str] = []
        for c in self.raw_checks:
            cell = c.get("cell", self.id)
            if cell not in seen:
                seen.append(cell)
        return seen

    def cell_classes(self) -> dict[str, str]:
        """Each cell's gate class: a check's own ``class``, else the scenario's."""
        out: dict[str, str] = {}
        for c in self.raw_checks:
            out.setdefault(c.get("cell", self.id), c.get("class", self.klass))
        return out

    def instantiate(self, variant: Variant, fixture_base: str = "") -> Instance:
        mapping = {**variant.mapping, "fixture_base": fixture_base}

        # ``expand`` runs on text only (a string turn, a page turn's text and line); an approve
        # or dismiss step has no text.
        def _expand_turn(t: Turn) -> Turn:
            if isinstance(t, str):
                return expand(t, mapping)
            if isinstance(t, PageTurn):
                return PageTurn(
                    expand(t.text, mapping),
                    {**t.page, "line": expand(t.page["line"], mapping)},
                )
            return t

        convs = [[_expand_turn(t) for t in turns] for turns in self.conversations]
        decls = self._decls(mapping, self.path)
        return Instance(self, variant, convs, decls)

    def _decls(self, mapping: dict[str, str], path: Path) -> list[CheckDecl]:
        decls = []
        for i, raw in enumerate(self.raw_checks):
            params = {
                k: _expand_value(v, mapping)
                for k, v in raw.items()
                if k not in checks_mod.COMMON_KEYS
            }
            try:
                params = checks_mod.validate_params(raw["name"], params)
            except ValueError as exc:
                raise ScenarioError(f"{path.name}: checks[{i}]: {exc}") from exc
            exposed_if = None
            if "exposed_if" in raw:
                exposed_if = _expand_value(raw["exposed_if"], mapping)
                try:
                    re.compile(exposed_if)
                except re.error as exc:
                    raise ScenarioError(
                        f"{path.name}: checks[{i}].exposed_if: not a valid regex ({exc})"
                    ) from exc
            decls.append(
                CheckDecl(
                    name=raw["name"],
                    params=params,
                    cell=raw.get("cell", self.id),
                    klass=raw.get("class", self.klass),
                    exposed_if=exposed_if,
                )
            )
        return decls


def expand(text: str, mapping: dict[str, str]) -> str:
    """Substitute known ``{names}`` (repeated, so a phrasing may use fact keys)."""
    for _ in range(3):
        new = _PLACEHOLDER.sub(lambda m: str(mapping.get(m.group(1), m.group(0))), text)
        if new == text:
            break
        text = new
    return text


def _expand_value(value: Any, mapping: dict[str, str]) -> Any:
    """Expand placeholders in a string, or in each string of a list (window bounds)."""
    if isinstance(value, str):
        return expand(value, mapping)
    if isinstance(value, list):
        return [expand(v, mapping) if isinstance(v, str) else v for v in value]
    return value


def _fail(path: Path, field_name: str, message: str) -> ScenarioError:
    return ScenarioError(f"{path.name}: {field_name}: {message}")


def _expect(path: Path, data: dict, key: str, typ: type | tuple, field_name: str) -> Any:
    value = data[key]
    types = typ if isinstance(typ, tuple) else (typ,)
    if (isinstance(value, bool) and bool not in types) or not isinstance(value, types):
        raise _fail(path, field_name, f"must be a {_tname(typ)}")
    return value


def _tname(typ: type | tuple) -> str:
    if isinstance(typ, tuple):
        return " or ".join(t.__name__ for t in typ)
    return typ.__name__


def _check_zone(path: Path, value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise _fail(path, field_name, "must be a time zone name")
    try:
        ZoneInfo(value)
    except Exception as exc:  # noqa: BLE001 - any failure to load means unknown
        raise _fail(path, field_name, f"unknown time zone {value!r}") from exc
    return value


def _parse_instant(path: Path, value: Any) -> datetime:
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise _fail(path, "clock.instant", "must be an ISO-8601 instant") from exc
    else:
        raise _fail(path, "clock.instant", "must be an ISO-8601 instant")
    if dt.tzinfo is None:
        raise _fail(path, "clock.instant", "must carry a UTC offset (for example ...Z)")
    return dt.astimezone(timezone.utc)


def _str_table(path: Path, value: Any, field_name: str) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, dict) or not all(
        isinstance(k, str) and k and isinstance(v, str) for k, v in value.items()
    ):
        raise _fail(path, field_name, "must be a table of non-empty names to strings")
    return tuple(value.items())


def _app_rows(path: Path, app: dict, key: str, allowed: set[str]) -> list[dict]:
    rows = app.get(key, [])
    if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
        raise _fail(path, f"app.{key}", "must be an array of tables")
    for i, row in enumerate(rows):
        for k in row:
            if k not in allowed:
                raise _fail(path, f"app.{key}[{i}].{k}", "unknown field")
        name = row.get("name")
        if not isinstance(name, str) or not name.strip():
            raise _fail(path, f"app.{key}[{i}].name", "needs a non-empty name")
    return rows


def _opt_str(path: Path, row: dict, key: str, field_name: str) -> str:
    if key not in row:
        return ""
    if not isinstance(row[key], str):
        raise _fail(path, field_name, "must be a string")
    return row[key]


def _parse_app(path: Path, app: Any) -> AppSeed:
    """The ``[app]`` table: ``agents``, ``mcp_servers`` and ``secrets`` row arrays. String values
    may hold ``{placeholders}`` (expanded from the variant's facts when seeded)."""
    if not isinstance(app, dict):
        raise _fail(path, "app", "must be a table")
    for key in app:
        if key not in _APP_KEYS:
            raise _fail(path, f"app.{key}", "unknown field")
    seed = AppSeed()
    for i, row in enumerate(
        _app_rows(path, app, "agents", {"name", "description", "system_prompt"})
    ):
        f = f"app.agents[{i}]"
        seed.agents.append(
            AppAgent(
                row["name"],
                _opt_str(path, row, "description", f"{f}.description"),
                _opt_str(path, row, "system_prompt", f"{f}.system_prompt"),
            )
        )
    mcp_keys = {"name", "type", "command", "args", "url", "headers", "env"}
    for i, row in enumerate(_app_rows(path, app, "mcp_servers", mcp_keys)):
        f = f"app.mcp_servers[{i}]"
        kind = row.get("type")
        if kind not in _MCP_TYPES:
            raise _fail(path, f"{f}.type", f"must be one of {', '.join(_MCP_TYPES)}")
        args = row.get("args", [])
        if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
            raise _fail(path, f"{f}.args", "must be a list of strings")
        command = _opt_str(path, row, "command", f"{f}.command")
        url = _opt_str(path, row, "url", f"{f}.url")
        if kind == "stdio" and not command:
            raise _fail(path, f"{f}.command", "a stdio server needs a command")
        if kind == "streamable-http" and not url:
            raise _fail(path, f"{f}.url", "a streamable-http server needs a url")
        seed.mcp_servers.append(
            AppMcp(
                row["name"],
                kind,
                command,
                tuple(args),
                url,
                _str_table(path, row.get("headers", {}), f"{f}.headers"),
                _str_table(path, row.get("env", {}), f"{f}.env"),
            )
        )
    for i, row in enumerate(
        _app_rows(path, app, "secrets", {"name", "description", "values", "allowed_tools"})
    ):
        f = f"app.secrets[{i}]"
        values = _str_table(path, row.get("values", {}), f"{f}.values")
        if not values:
            raise _fail(path, f"{f}.values", "needs at least one key and value")
        tools = row.get("allowed_tools", ["http_request"])
        if not isinstance(tools, list) or not tools or not all(isinstance(t, str) for t in tools):
            raise _fail(path, f"{f}.allowed_tools", "must be a non-empty list of tool names")
        seed.secrets.append(
            AppSecret(
                row["name"],
                _opt_str(path, row, "description", f"{f}.description"),
                values,
                tuple(tools),
            )
        )
    return seed


def _page_turn(path: Path, table: dict, where: str) -> PageTurn:
    for key in table:
        if key not in PAGE_TURN_KEYS:
            raise _fail(
                path,
                f"{where}.{key}",
                'unknown field (a page turn is {text = "...", page = {line = "..."}})',
            )
    text = table.get("text")
    if not isinstance(text, str) or not text.strip():
        raise _fail(path, f"{where}.text", "is required and must be a non-empty string")
    page = table.get("page")
    if not isinstance(page, dict):
        raise _fail(path, f"{where}.page", "is required and must be a table with a line")
    for key in page:
        if key not in ("line", "descriptor"):
            raise _fail(path, f"{where}.page.{key}", "unknown field (line, descriptor)")
    line = page.get("line")
    if not isinstance(line, str) or not line.strip():
        raise _fail(path, f"{where}.page.line", "is required and must be a non-empty string")
    out: dict[str, Any] = {"line": line}
    if "descriptor" in page:
        from the_one.gleepglorp.page import validate_descriptor

        descriptor, error = validate_descriptor(page["descriptor"])
        if error is not None:
            raise _fail(path, f"{where}.page.descriptor", error.removeprefix("value: "))
        out["descriptor"] = descriptor
    return PageTurn(text, out)


def _step_turn(path: Path, table: dict, where: str) -> StepTurn:
    for key in table:
        if key not in STEP_KINDS:
            raise _fail(
                path,
                f"{where}.{key}",
                "unknown field (a step is {approve = true} or {dismiss = true})",
            )
    if len(table) != 1:
        raise _fail(path, where, "a step names exactly one of approve or dismiss")
    ((kind, value),) = table.items()
    if value is not True:
        raise _fail(path, f"{where}.{kind}", "must be true")
    return StepTurn(kind)


def parse_scenario(
    path: Path, *, n: int | None = None, fixtures_root: Path | None = None
) -> Scenario:
    """Load and validate one scenario file."""
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ScenarioError(f"{path.name}: toml: {exc}") from exc
    except OSError as exc:
        raise ScenarioError(f"{path.name}: file: {exc}") from exc

    for key in data:
        if key not in _TOP_KEYS:
            raise _fail(path, key, "unknown field")
    for req in ("id", "class", "conversations", "checks"):
        if req not in data:
            raise _fail(path, req, "is required")

    sid = _expect(path, data, "id", str, "id")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", sid):
        raise _fail(path, "id", "must be lowercase letters, digits and hyphens")
    klass = _expect(path, data, "class", str, "class")
    if klass not in CLASSES:
        raise _fail(path, "class", f"must be one of {', '.join(CLASSES)}")
    sc = Scenario(id=sid, klass=klass, description=str(data.get("description", "")), path=path)

    agent = data.get("agent", {})
    if not isinstance(agent, dict):
        raise _fail(path, "agent", "must be a table")
    for key in agent:
        if key not in _AGENT_KEYS:
            raise _fail(path, f"agent.{key}", "unknown field")
    if "persona" in agent:
        sc.persona = _expect(path, agent, "persona", str, "agent.persona")
    for flag in ("notes_enabled", "tools_off", "routines_enabled", "skip_empty_final_reply"):
        if flag in agent:
            setattr(sc, flag, _expect(path, agent, flag, bool, f"agent.{flag}"))
    if "rich_visuals" in agent:
        sc.rich_visuals = _expect(path, agent, "rich_visuals", bool, "agent.rich_visuals")
    if "max_iterations" in agent:
        mi = _expect(path, agent, "max_iterations", int, "agent.max_iterations")
        if mi < 1:
            raise _fail(path, "agent.max_iterations", "must be at least 1")
        sc.max_iterations = mi
    if "rules" in agent:
        rules = _expect(path, agent, "rules", list, "agent.rules")
        if not all(isinstance(r, str) and r.strip() for r in rules):
            raise _fail(path, "agent.rules", "must be a list of non-empty strings")
        sc.rules = list(rules)
    for i, note in enumerate(agent.get("seeded_notes", [])):
        if not isinstance(note, dict) or not isinstance(note.get("text"), str) or not note["text"]:
            raise _fail(path, f"agent.seeded_notes[{i}]", "needs a non-empty text")
        unknown = set(note) - {"text", "untrusted"}
        if unknown:
            raise _fail(path, f"agent.seeded_notes[{i}].{sorted(unknown)[0]}", "unknown field")
        sc.seeded_notes.append(SeedNote(note["text"], bool(note.get("untrusted", False))))
    if sc.seeded_notes and not sc.notes_enabled:
        raise _fail(path, "agent.seeded_notes", "seeded notes need agent.notes_enabled = true")
    for i, kb in enumerate(agent.get("kb", [])):
        if (
            not isinstance(kb, dict)
            or not isinstance(kb.get("name"), str)
            or not isinstance(kb.get("fixture"), str)
            or not kb["name"]
            or not kb["fixture"]
        ):
            raise _fail(path, f"agent.kb[{i}]", "needs a name and a fixture")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", kb["fixture"]):
            raise _fail(path, f"agent.kb[{i}].fixture", "must match [A-Za-z0-9_-]{1,40}")
        if fixtures_root is not None and not (fixtures_root / "kb" / kb["fixture"]).is_dir():
            raise _fail(path, f"agent.kb[{i}].fixture", f"no fixture directory {kb['fixture']!r}")
        sc.kbs.append(KBRef(kb["name"], kb["fixture"]))
    if "builder" in agent:
        builder = _expect(path, agent, "builder", str, "agent.builder")
        if builder not in BUILDERS:
            raise _fail(path, "agent.builder", f"must be one of {', '.join(BUILDERS)}")
        for key in _BUILDER_REFUSES:
            if key in agent:
                raise _fail(
                    path,
                    "agent.builder",
                    f"{builder!r} cannot be combined with agent.{key} (the assistant has none)",
                )
        sc.builder = builder
    if "web_access" in agent:
        sc.web_access = _expect(path, agent, "web_access", bool, "agent.web_access")
        if sc.builder is None:
            raise _fail(path, "agent.web_access", "needs agent.builder")
    if "app" in data:
        if sc.builder is None:
            raise _fail(path, "app", "needs agent.builder")
        sc.app = _parse_app(path, data["app"])

    clock = data.get("clock", {})
    if not isinstance(clock, dict):
        raise _fail(path, "clock", "must be a table")
    for key in clock:
        if key not in _CLOCK_KEYS:
            raise _fail(path, f"clock.{key}", "unknown field")
    if "instant" in clock:
        sc.instant = _parse_instant(path, clock["instant"])
    if "zone" in clock:
        sc.zone = _check_zone(path, clock["zone"], "clock.zone")
    if "host_zone" in clock:
        sc.host_zone = _check_zone(path, clock["host_zone"], "clock.host_zone")

    variants = data.get("variants", {})
    if not isinstance(variants, dict):
        raise _fail(path, "variants", "must be a table")
    for key in variants:
        if key not in ("phrasings", "facts"):
            raise _fail(path, f"variants.{key}", "unknown field")
    if "phrasings" in variants:
        ph = variants["phrasings"]
        if not isinstance(ph, list) or not ph or not all(isinstance(p, str) for p in ph):
            raise _fail(path, "variants.phrasings", "must be a non-empty list of strings")
        sc.phrasings = list(ph)
    if "facts" in variants:
        facts = variants["facts"]
        if not isinstance(facts, list) or not facts:
            raise _fail(path, "variants.facts", "must be a non-empty list of tables")
        out_facts = []
        for i, f in enumerate(facts):
            if not isinstance(f, dict) or not all(
                isinstance(k, str) and isinstance(v, (str, int, float)) for k, v in f.items()
            ):
                raise _fail(path, f"variants.facts[{i}]", "must be a table of strings")
            if "phrasing" in f or "fixture_base" in f:
                raise _fail(path, f"variants.facts[{i}]", "may not use the reserved keys")
            if "instant" in f:
                _parse_instant(path, f["instant"])
            out_facts.append({k: str(v) for k, v in f.items()})
        sc.facts = out_facts
    if n is not None and n > len(sc.variants()):
        raise _fail(
            path,
            "variants",
            f"n={n} exceeds the {len(sc.variants())} distinct variants "
            f"({len(sc.phrasings)} phrasings x {len(sc.facts)} facts)",
        )

    convs = data["conversations"]
    if not isinstance(convs, list) or not convs:
        raise _fail(path, "conversations", "must be a non-empty list of tables")
    for i, conv in enumerate(convs):
        turns = conv.get("turns") if isinstance(conv, dict) else None
        if not isinstance(turns, list) or not turns:
            raise _fail(
                path,
                f"conversations[{i}].turns",
                "must be a non-empty list of strings, page turns, {approve = true} "
                "or {dismiss = true}",
            )
        parsed: list[Turn] = []
        for j, t in enumerate(turns):
            where = f"conversations[{i}].turns[{j}]"
            if isinstance(t, str) and t.strip():
                parsed.append(t)
            elif isinstance(t, dict) and ("text" in t or "page" in t):
                parsed.append(_page_turn(path, t, where))
            elif isinstance(t, dict):
                parsed.append(_step_turn(path, t, where))
            else:
                raise _fail(
                    path,
                    where,
                    "must be a non-empty string, a {text, page} table, {approve = true} "
                    "or {dismiss = true}",
                )
        if isinstance(parsed[0], StepTurn):
            raise _fail(
                path,
                f"conversations[{i}].turns[0]",
                "the first turn must be a string or a page turn "
                "(a step needs a proposal made earlier)",
            )
        sc.conversations.append(parsed)

    raw_checks = data["checks"]
    if not isinstance(raw_checks, list) or not raw_checks:
        raise _fail(path, "checks", "must be a non-empty list of tables")
    for i, raw in enumerate(raw_checks):
        if not isinstance(raw, dict) or not isinstance(raw.get("name"), str):
            raise _fail(path, f"checks[{i}].name", "is required")
        if "class" in raw and raw["class"] not in CHECK_CLASSES:
            raise _fail(path, f"checks[{i}].class", f"must be one of {', '.join(CHECK_CLASSES)}")
        if "cell" in raw and (not isinstance(raw["cell"], str) or not raw["cell"]):
            raise _fail(path, f"checks[{i}].cell", "must be a non-empty string")
        if "exposed_if" in raw and (
            not isinstance(raw["exposed_if"], str) or not raw["exposed_if"]
        ):
            raise _fail(path, f"checks[{i}].exposed_if", "must be a non-empty regex string")
        sc.raw_checks.append(dict(raw))
    by_cell: dict[str, set[bool]] = {}
    for raw in sc.raw_checks:
        by_cell.setdefault(raw.get("cell", sc.id), set()).add("exposed_if" in raw)
    for cell, kinds in by_cell.items():
        if len(kinds) > 1:
            raise _fail(
                path,
                "checks",
                f"cell {cell!r} mixes checks with and without exposed_if "
                "(a cell is measured or not exposed as a whole)",
            )
    # Validate names and parameters now (against the first variant's expansion
    # and a placeholder fixture base), so a bad file fails at load, not mid-run.
    first = sc.variants()[0]
    from evals.fixtures import FIXTURE_HOSTNAME

    sc.instantiate(first, f"http://{FIXTURE_HOSTNAME}")
    return sc


def load_scenarios(
    scenarios_dir: Path,
    *,
    ids: list[str] | None = None,
    n: int | None = None,
    fixtures_root: Path | None = None,
) -> list[Scenario]:
    """Load every ``*.toml`` in ``scenarios_dir`` (sorted), optionally filtered by id."""
    if not scenarios_dir.is_dir():
        raise ScenarioError(f"{scenarios_dir}: no such scenarios directory")
    out = [
        parse_scenario(p, n=n, fixtures_root=fixtures_root)
        for p in sorted(scenarios_dir.glob("*.toml"))
    ]
    seen: dict[str, Path] = {}
    for sc in out:
        if sc.id in seen:
            raise ScenarioError(f"{sc.path.name}: id: duplicate of {seen[sc.id].name}")
        seen[sc.id] = sc.path
    if ids:
        known = {s.id for s in out}
        for want in ids:
            if want not in known:
                raise ScenarioError(f"--scenarios: unknown scenario {want!r}")
        out = [s for s in out if s.id in ids]
    return out
