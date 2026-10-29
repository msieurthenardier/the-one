"""Declarative scenarios (DD2) read with ``tomllib``.

A scenario file declares: ``id``, ``class`` and ``description``; the agent setup
(``[agent]``: persona, ``notes_enabled``, ``routines_enabled``, rules, seeded notes, knowledge-base
fixtures, ``tools_off``); the clock (``[clock]``); ``[variants]`` (phrasings x
facts, DD9); one or more ``[[conversations]]`` (each a list of user ``turns``;
a new conversation means a freshly built agent); and ``[[checks]]``.

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

CLASSES = ("safety", "improve", "hold")
DEFAULT_INSTANT = datetime(2026, 3, 2, 15, 0, 0, tzinfo=timezone.utc)
DEFAULT_ZONE = "Pacific/Kiritimati"  # UTC+14: separates the host date from the zone date
DEFAULT_HOST_ZONE = "America/Los_Angeles"

_TOP_KEYS = {"id", "class", "description", "agent", "clock", "variants", "conversations", "checks"}
_AGENT_KEYS = {
    "persona",
    "notes_enabled",
    "tools_off",
    "rules",
    "seeded_notes",
    "kb",
    "max_iterations",
    "routines_enabled",
}
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
class Variant:
    id: str
    phrasing_index: int
    fact_index: int
    mapping: dict[str, str]


@dataclass
class Instance:
    """A scenario instantiated for one variant."""

    scenario: Scenario
    variant: Variant
    conversations: list[list[str]]
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
    rules: list[str] = field(default_factory=list)
    seeded_notes: list[SeedNote] = field(default_factory=list)
    kbs: list[KBRef] = field(default_factory=list)
    max_iterations: int | None = None
    instant: datetime = DEFAULT_INSTANT
    zone: str = DEFAULT_ZONE
    host_zone: str = DEFAULT_HOST_ZONE
    phrasings: list[str] = field(default_factory=lambda: [""])
    facts: list[dict[str, str]] = field(default_factory=lambda: [{}])
    conversations: list[list[str]] = field(default_factory=list)
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
        convs = [[expand(t, mapping) for t in turns] for turns in self.conversations]
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
            decls.append(
                CheckDecl(
                    name=raw["name"],
                    params=params,
                    cell=raw.get("cell", self.id),
                    klass=raw.get("class", self.klass),
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
    for flag in ("notes_enabled", "tools_off", "routines_enabled"):
        if flag in agent:
            setattr(sc, flag, _expect(path, agent, flag, bool, f"agent.{flag}"))
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
        if (
            not isinstance(turns, list)
            or not turns
            or not all(isinstance(t, str) and t.strip() for t in turns)
        ):
            raise _fail(path, f"conversations[{i}].turns", "must be a non-empty list of strings")
        sc.conversations.append(list(turns))

    raw_checks = data["checks"]
    if not isinstance(raw_checks, list) or not raw_checks:
        raise _fail(path, "checks", "must be a non-empty list of tables")
    for i, raw in enumerate(raw_checks):
        if not isinstance(raw, dict) or not isinstance(raw.get("name"), str):
            raise _fail(path, f"checks[{i}].name", "is required")
        if "class" in raw and raw["class"] not in CLASSES:
            raise _fail(path, f"checks[{i}].class", f"must be one of {', '.join(CLASSES)}")
        if "cell" in raw and (not isinstance(raw["cell"], str) or not raw["cell"]):
            raise _fail(path, f"checks[{i}].cell", "must be a non-empty string")
        sc.raw_checks.append(dict(raw))
    # Validate names and parameters now (against the first variant's expansion
    # and a placeholder fixture base), so a bad file fails at load, not mid-run.
    first = sc.variants()[0]
    sc.instantiate(first, "http://127.0.0.1:0")
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
