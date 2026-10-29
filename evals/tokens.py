"""Token measurement of the platform text (DD12).

The platform text is everything the platform, not the operator, puts before the
model on the first call, reported by part:

- prompt sections: the platform prompt's own sections (the tool-free prompt's for the
  tool-free configuration), the rules layer and the notes layer (each minus the operator's
  rule and note texts), the date line, and ``other`` for any text that no known
  part explains (so the parts always sum to the total);
- one part per starting tool schema (name + description + JSON parameters,
  serialised deterministically).

The reference count is ``tiktoken``'s ``o200k_base``. The counter is injectable:
unit tests use :class:`StandInCounter` and never import tiktoken. Each model's
own count is the provider-reported ``input_tokens`` of the first call, measured
cold (Ollama is unloaded first).
"""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import json
import logging
import math
import os
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

PACKAGE_DIR = Path(__file__).resolve().parent
MEASURE_DIR = PACKAGE_DIR / "measure"
MEASURE_FIXTURES = MEASURE_DIR / "fixtures"
DEFAULT_CACHE_DIR = PACKAGE_DIR / ".cache" / "tiktoken"
ENCODING = "o200k_base"
SEPARATOR = "\n\n---\n\n"

CONFIGS = ("bare", "all-on", "tool-free")
# DD13: the bare and all-on configurations again, with a connector row whose
# ``default_agent`` is the variant's own agent name. name -> (base config, attempt).
CONNECTOR_VARIANTS = {"bare-connector": ("bare", 90), "all-on-connector": ("all-on", 91)}
# Measured and counted but outside the prompt fingerprint: the all-on agent with Routines on
# (M33 F2 L4). Loaded only when its file exists, so a custom measure directory needs no copy.
EXTRA_CONFIGS = ("routines-on",)
ALL_CONFIGS = (*CONFIGS, *CONNECTOR_VARIANTS, *EXTRA_CONFIGS)
# the starting tools that exist only for a connector-mapped agent's benefit (DD13 a')
CONNECTOR_TOOLS = ("send_to_platform_channel", "find_platform_destination")
CONFIG_FILES = {c: MEASURE_DIR / f"{c}.toml" for c in CONFIGS}
GROUP_PROMPT = "prompt"
GROUP_TOOLS = "tools"
KB_TOOL_PREFIX = "kb__"
MEASURE_MODEL = "measure"  # the scripted stand-in preset's name

UNLOAD_TIMEOUT_S = 60.0
UNLOAD_POLL_S = 1.0


class Counter(Protocol):
    name: str

    def count(self, text: str) -> int: ...


class TiktokenMissingError(RuntimeError):
    """tiktoken is not installed (the ``[evals]`` extra)."""


class StandInCounter:
    """A deterministic counter for tests: ceil(utf-8 bytes / 4)."""

    name = "standin:bytes/4"

    def count(self, text: str) -> int:
        return math.ceil(len(text.encode("utf-8")) / 4)


class TiktokenCounter:
    def __init__(self, cache_dir: Path | None = None) -> None:
        # Set before first use: tiktoken reads it when it first fetches the encoding.
        cache = Path(cache_dir or DEFAULT_CACHE_DIR)
        cache.mkdir(parents=True, exist_ok=True)
        os.environ["TIKTOKEN_CACHE_DIR"] = str(cache)
        try:
            import tiktoken
        except ImportError as exc:
            raise TiktokenMissingError(
                'tiktoken is not installed: run pip install -e ".[evals]"'
            ) from exc
        self._enc = tiktoken.get_encoding(ENCODING)
        self.name = f"tiktoken:{ENCODING}"

    def count(self, text: str) -> int:
        return len(self._enc.encode(text, disallowed_special=()))


# ── Parts ─────────────────────────────────────────────────────────────────


@dataclass
class Part:
    name: str
    group: str  # "prompt" | "tools"
    tokens: int
    chars: int

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


def schema_text(schema: dict[str, Any]) -> str:
    """A tool schema as the model reads it: name, description, JSON parameters."""
    body = schema.get("function", schema)
    params = body.get("parameters", body.get("input_schema", {}))
    return f"{body.get('name', '')}\n{body.get('description', '')}\n" + json.dumps(
        params, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


def schema_name(schema: dict[str, Any]) -> str:
    return str(schema.get("function", schema).get("name", ""))


def _without(text: str, operator_texts: list[str]) -> str:
    for t in operator_texts:
        if t:
            text = text.replace(t, "", 1)
    return text


SectionSplitter = Callable[[str], list[tuple[str, str]]]


def _single_platform_part(text: str) -> list[tuple[str, str]]:
    """The default section hook: the whole platform text is one part."""
    return [("platform", text)]


class PlatformAttributionError(RuntimeError):
    """The platform text matches no capability combination the splitter knows."""


def platform_prompt_sections(text: str, *, strict: bool = False) -> list[tuple[str, str]]:
    """Split a first-call platform text into the platform prompt's own sections.

    The platform prompt is conditional (Flight 2 leg 1c), so the text is matched against
    the render of every capability combination (tools on or off, knowledge, execution
    tools); the first render equal to ``text`` supplies the split. When none matches the
    text stays one ``platform`` part (and a warning is logged), so the parts always sum
    to the total. With ``strict`` a no-match raises :class:`PlatformAttributionError`
    instead: measurement must never report unattributed sizes as if they were sections.
    """
    import itertools

    from the_one.agent.platform_prompt import Capabilities, render_platform, sections_for

    combos = [
        Capabilities(tools=True, knowledge=kb, exec_tools=ex)
        for kb, ex in itertools.product((True, False), repeat=2)
    ] + [Capabilities(tools=False, knowledge=False, exec_tools=False)]
    for caps in combos:
        if render_platform(caps) == text:
            return sections_for(caps)
    if strict:
        raise PlatformAttributionError(
            "platform text matches no capability combination (tools, knowledge, exec_tools, "
            "tool-free); a new conditional section needs its capability added to "
            "evals/tokens.py::platform_prompt_sections"
        )
    logging.getLogger(__name__).warning(
        "platform text matches no capability combination; counted as one part"
    )
    return _single_platform_part(text)


def strict_platform_prompt_sections(text: str) -> list[tuple[str, str]]:
    """:func:`platform_prompt_sections` that raises when the text cannot be attributed."""
    return platform_prompt_sections(text, strict=True)


def _layers(
    system: str,
    persona: str,
    tail_names: list[str],
) -> tuple[str, list[tuple[str, str]]]:
    """Split ``system`` into (platform text, [(layer name, text)]) by the layer order.

    The order is platform, persona, rules, notes, date; ``tail_names`` lists which of
    rules/notes/date this configuration carries. A persona is located by its own text
    first, so a persona that contains the separator cannot confuse the split. Layers
    beyond the known ones are named ``unattributed``.
    """
    idx = system.find(SEPARATOR + persona + SEPARATOR) if persona else -1
    if idx < 0 and persona and system.endswith(SEPARATOR + persona):
        idx = len(system) - len(persona) - len(SEPARATOR)
    if idx >= 0:
        platform = system[:idx]
        rest = system[idx + len(SEPARATOR) + len(persona) :]
        segs = rest[len(SEPARATOR) :].split(SEPARATOR) if rest.startswith(SEPARATOR) else []
    else:
        first, *segs = system.split(SEPARATOR)
        platform = first
    named = [
        (tail_names[i] if i < len(tail_names) else "unattributed", s) for i, s in enumerate(segs)
    ]
    return platform, named


def extract_parts(
    system: str,
    schemas: list[dict[str, Any]],
    counter: Counter,
    *,
    persona: str = "",
    rule_texts: list[str] | None = None,
    note_texts: list[str] | None = None,
    date_lines: list[str] | None = None,
    notes_present: bool | None = None,
    platform_sections: SectionSplitter | None = None,
) -> list[Part]:
    """Split a first-call system prompt and its tool schemas into platform-text parts.

    Structural (DD10): the prompt is split on the layer separator and layers are
    assigned by their known order (platform, persona, rules, notes, date; each present
    by configuration). Operator-authored text (persona, rule texts, note texts) is
    subtracted from the layer that holds it, never guessed. The platform text goes through
    ``platform_sections`` (``text -> [(id, text)]``, default one ``platform`` part;
    :func:`platform_prompt_sections` splits it into the platform prompt's sections); a
    layer no configuration explains becomes ``unattributed``.
    """
    rule_texts = rule_texts or []
    note_texts = note_texts or []
    if notes_present is None:
        notes_present = bool(note_texts)
    tail_names = (
        (["rules_layer"] if rule_texts else [])
        + (["notes_layer"] if notes_present else [])
        + (["date_line"] if date_lines else [])
    )
    # Each layer is stripped of the operator texts that layer holds. A short rule text
    # is not searched for in the notes layer (it could match the platform's own words).
    holds = {"rules_layer": rule_texts, "notes_layer": note_texts}
    platform, layers = _layers(system, persona, tail_names)
    sections = (platform_sections or _single_platform_part)(platform)
    texts: list[tuple[str, str]] = [(sid, t) for sid, t in sections]
    unattributed: list[str] = []
    for name, seg in layers:
        seg = _without(seg, holds.get(name, []))
        if name == "unattributed":
            unattributed.append(seg)
        else:
            texts.append((name, seg))
    parts = [Part(n, GROUP_PROMPT, counter.count(t), len(t)) for n, t in texts]
    if len(sections) > 1 and "".join(t for _, t in sections) == platform:
        # Sections that tile the platform text are counted cumulatively (each part is the
        # growth in the count of the text so far), so the parts sum exactly to the count of
        # the whole platform text: tokens can merge across a section boundary.
        done, prev = "", 0
        for i, (sid, t) in enumerate(sections):
            done += t
            now = counter.count(done)
            parts[i] = Part(sid, GROUP_PROMPT, now - prev, len(t))
            prev = now
    if unattributed:
        joined = SEPARATOR.join(unattributed)
        parts.append(Part("unattributed", GROUP_PROMPT, counter.count(joined), len(joined)))
    for s in schemas:
        t = schema_text(s)
        parts.append(Part(f"tool:{schema_name(s)}", GROUP_TOOLS, counter.count(t), len(t)))
    return parts


def totals(parts: list[Part]) -> dict[str, int]:
    prompt = sum(p.tokens for p in parts if p.group == GROUP_PROMPT)
    tools = sum(p.tokens for p in parts if p.group == GROUP_TOOLS)
    return {"prompt_sections": prompt, "tools": tools, "platform": prompt + tools}


# ── Building the three configurations ─────────────────────────────────────


@dataclass
class RawConfig:
    """What the first call carried, in memory only (the hash, not the text, is stored)."""

    name: str
    system: str
    schemas: list[dict[str, Any]]
    kb_schema: dict[str, Any] | None
    persona: str
    rule_texts: list[str]
    note_texts: list[str]
    date_lines: list[str]
    notes_present: bool = False


def _script_for(config: str, kb_query: str):
    from evals import scripted

    if config in ("all-on", "all-on-connector"):
        return [scripted.call("search_tools", {"query": kb_query}), scripted.text("ok")]
    return [scripted.text("ok")]


def load_config_scenarios(measure_dir: Path | None = None) -> dict[str, Any]:
    from evals.scenario import parse_scenario

    d = measure_dir or MEASURE_DIR
    names = [*CONFIGS, *(c for c in EXTRA_CONFIGS if (d / f"{c}.toml").is_file())]
    return {c: parse_scenario(d / f"{c}.toml", fixtures_root=d / "fixtures") for c in names}


@contextlib.asynccontextmanager
async def connector_row(agent_name: str):
    """Insert a connector whose ``default_agent`` is ``agent_name``; delete it on exit."""
    from the_one.config import settings
    from the_one.db.connection import get_connection
    from the_one.db.models import Connector
    from the_one.db.repositories import ConnectorRepository
    from the_one.encryption import get_encryptor

    conn = await get_connection()
    repo = ConnectorRepository(conn, get_encryptor(settings.data_dir))
    row = Connector(
        id=f"measure-{agent_name}",
        name=f"measure-{agent_name}",
        type="stub",
        config={"default_agent": agent_name},
    )
    await repo.create(row)
    try:
        yield row
    finally:
        await repo.delete(row.id)


async def build_raw_configs(harness: Any, scenarios: dict[str, Any]) -> dict[str, RawConfig]:
    """Build the bare, all-on and tool-free agents, then the two connector-mapped
    variants (DD13), with the scripted provider."""
    from evals import scripted
    from evals.harness import RunSpec, expected_date_lines

    out: dict[str, RawConfig] = {}
    plan: list[tuple[str, str, int]] = [(c, c, 1) for c in scenarios]
    plan += [(n, base, att) for n, (base, att) in CONNECTOR_VARIANTS.items() if base in scenarios]
    for config, base, attempt_no in plan:
        sc = scenarios[base]
        holder: list[Any] = []

        def hook(spec: Any, _b: str, config: str = config, holder: list[Any] = holder) -> Any:
            p = scripted.ScriptedProvider(_script_for(config, "measurement"))
            holder.append(p)
            return p

        harness.provider_hook = hook
        spec = RunSpec(sc, sc.variants()[0], MEASURE_MODEL, attempt=attempt_no)
        if config in CONNECTOR_VARIANTS:
            async with connector_row(spec.agent_name):
                attempt = await harness.run_once(spec)
        else:
            attempt = await harness.run_once(spec)
        if attempt.exc is not None:
            raise RuntimeError(
                f"measuring {config}: {type(attempt.exc).__name__}: {attempt.exc}"
            ) from attempt.exc
        rec = attempt.recorder
        if not rec.systems or rec.starting_schemas is None:
            raise RuntimeError(f"measuring {config}: the agent made no model call")
        kb_schema = None
        if base == "all-on":
            for call_ in holder[-1].calls:
                for t in call_["tools"] or []:
                    if schema_name(t).startswith(KB_TOOL_PREFIX):
                        kb_schema = t
            if kb_schema is None:
                raise RuntimeError(f"measuring {config}: no knowledge-base search tool was found")
        out[config] = RawConfig(
            name=config,
            system=rec.systems[0],
            schemas=rec.starting_schemas,
            kb_schema=kb_schema,
            persona=sc.persona,
            rule_texts=list(sc.rules),
            note_texts=[n.text for n in sc.seeded_notes],
            date_lines=expected_date_lines(sc),
            notes_present=bool(sc.notes_enabled),
        )
    return out


def measure_configs(
    raw: dict[str, RawConfig],
    counter: Counter,
    platform_sections: SectionSplitter | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name, rc in raw.items():
        parts = extract_parts(
            rc.system,
            rc.schemas,
            counter,
            persona=rc.persona,
            rule_texts=rc.rule_texts,
            note_texts=rc.note_texts,
            date_lines=rc.date_lines,
            notes_present=rc.notes_present,
            platform_sections=platform_sections or strict_platform_prompt_sections,
        )
        out[name] = {"parts": [p.to_dict() for p in parts], "totals": totals(parts)}
    return out


def kb_tool_entry(raw: dict[str, RawConfig], counter: Counter) -> dict[str, Any] | None:
    kb = raw["all-on"].kb_schema if "all-on" in raw else None
    if kb is None:
        return None
    return {"name": schema_name(kb), "tokens": counter.count(schema_text(kb))}


# ── Cold model counts ─────────────────────────────────────────────────────


async def ollama_unload(
    base_url: str,
    model: str,
    *,
    transport: Any = None,
    timeout_s: float = UNLOAD_TIMEOUT_S,
    poll_s: float = UNLOAD_POLL_S,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> None:
    """Unload ``model`` (``keep_alive: 0``) and poll ``/api/ps`` until it is gone.

    A loaded model reuses its cached prefix, which leaves that prefix out of
    ``prompt_eval_count``; so a cold count needs the model unloaded first.
    """
    import httpx

    from the_one.llm.ollama_api import strip_v1

    url = strip_v1(base_url)
    async with httpx.AsyncClient(timeout=30.0, transport=transport) as client:
        r = await client.post(f"{url}/api/generate", json={"model": model, "keep_alive": 0})
        r.raise_for_status()
        deadline = clock() + timeout_s
        while True:
            r = await client.get(f"{url}/api/ps")
            r.raise_for_status()
            loaded = {m.get("name") or m.get("model") for m in r.json().get("models", [])}
            if model not in loaded:
                return
            if clock() >= deadline:
                raise RuntimeError(f"ollama: {model} still loaded after {timeout_s:.0f}s")
            await sleep(poll_s)


def first_call_input_tokens(attempt: Any) -> int | None:
    from the_one.llm.base import Role

    for t in attempt.trace.turns:
        for m in t.messages:
            if m.role == Role.ASSISTANT and m.usage is not None:
                return m.usage.input_tokens
    return None


async def measure_model_counts(
    harness: Any,
    scenarios: dict[str, Any],
    presets: list[Any],
    *,
    unload: Callable[[Any], Awaitable[None]] | None = None,
    server_info: Callable[[Any], Awaitable[dict[str, Any]]] | None = None,
    provider_hook: Callable[[Any, str], Any] | None = None,
) -> dict[str, Any]:
    """Each model's own cold first-call ``input_tokens`` for each configuration.

    ``provider_hook`` is a test seam (a scripted provider); the command uses the real one.
    """
    from evals.harness import RunSpec

    harness.provider_hook = provider_hook
    out: dict[str, Any] = {}
    for preset in presets:
        entry: dict[str, Any] = {"server": {}, "input_tokens": {}}
        if server_info is not None:
            entry["server"] = await server_info(preset)
        for config, sc in scenarios.items():
            if preset.type == "ollama" and unload is not None:
                await unload(preset)
            one_call = dataclasses.replace(sc, max_iterations=1)
            attempt = await harness.run_once(RunSpec(one_call, one_call.variants()[0], preset.name))
            if attempt.exc is not None:
                raise RuntimeError(
                    f"model count {preset.name}/{config}: "
                    f"{type(attempt.exc).__name__}: {attempt.exc}"
                ) from attempt.exc
            entry["input_tokens"][config] = first_call_input_tokens(attempt)
        out[preset.name] = entry
    return out


# ── The command ───────────────────────────────────────────────────────────


@dataclass
class MeasureOptions:
    with_model_counts: bool = False
    models: list[str] | None = None
    models_file: Path | None = None
    token_file: Path | None = None
    json_out: Path | None = None
    cache_dir: Path | None = None
    run_dir: Path | None = None
    measure_dir: Path | None = None
    counter: Counter | None = None
    environ: Any = None
    unload: Callable[[Any], Awaitable[None]] | None = None
    server_info: Callable[[Any], Awaitable[dict[str, Any]]] | None = None
    model_hook: Callable[[Any, str], Any] | None = None


async def measure_prompt(opts: MeasureOptions) -> dict[str, Any]:
    """Build the three configurations offline and return the measurement document.

    Raises ``TiktokenMissingError`` (before anything is created) when no counter is
    injected and tiktoken is absent; ``EvalRefusalError`` on a start-up refusal.
    """
    import shutil

    from evals.env import StartupOptions, shutdown, startup
    from evals.fingerprint import prompt_fingerprint
    from evals.fixtures import KBFixtures
    from evals.harness import Harness
    from evals.models import Preset, load_presets, select_presets
    from evals.scenario import DEFAULT_INSTANT, DEFAULT_ZONE

    counter = opts.counter or TiktokenCounter(opts.cache_dir)
    scenarios = load_config_scenarios(opts.measure_dir)
    presets: list[Preset] = []
    if opts.with_model_counts:
        presets = select_presets(load_presets(opts.models_file), opts.models)
    scratch = Preset(MEASURE_MODEL, "ollama", "measure-scripted", "http://127.0.0.1:9")
    run_dir = opts.run_dir or (PACKAGE_DIR / "runs" / f"measure-{os.getpid()}")
    env = await startup(
        StartupOptions(
            run_dir=run_dir,
            need_token=any(p.needs_token for p in presets),
            token_file=opts.token_file,
            environ=opts.environ,
        )
    )
    doc: dict[str, Any]
    try:
        harness = Harness(
            env,
            {p.name: p for p in [scratch, *presets]},
            kb=KBFixtures(env, (opts.measure_dir or MEASURE_DIR) / "fixtures"),
        )
        await harness.setup()
        raw = await build_raw_configs(harness, scenarios)
        doc = {
            "schema": 1,
            "counter": counter.name,
            "pinned": {"instant": DEFAULT_INSTANT.isoformat(), "zone": DEFAULT_ZONE},
            "configs": measure_configs(raw, counter),
            "kb_tool": kb_tool_entry(raw, counter),
            "fingerprints": {
                "prompt": prompt_fingerprint(
                    {k: v for k, v in raw.items() if k not in EXTRA_CONFIGS}
                )
            },
            "model_counts": {},
        }
        if presets:
            doc["model_counts"] = await measure_model_counts(
                harness,
                scenarios,
                presets,
                unload=opts.unload or _default_unload,
                server_info=opts.server_info or _default_server_info,
                provider_hook=opts.model_hook,
            )
    finally:
        await shutdown(env)
        shutil.rmtree(run_dir, ignore_errors=True)
    if opts.json_out:
        opts.json_out.parent.mkdir(parents=True, exist_ok=True)
        opts.json_out.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return doc


async def _default_unload(preset: Any) -> None:
    await ollama_unload(preset.base_url, preset.model)


async def _default_server_info(preset: Any) -> dict[str, Any]:
    from evals.models import ollama_server_info

    if preset.type != "ollama":
        return {}
    return await ollama_server_info(preset.base_url, preset.model)


def render_tables(doc: dict[str, Any]) -> str:
    """Per-part tables for the three configurations, then the model counts."""
    lines = [f"counter: {doc['counter']}", ""]
    for name in ALL_CONFIGS:
        cfg = doc["configs"].get(name)
        if not cfg:
            continue
        lines.append(f"[{name}]")
        lines.append(f"{'part':34} {'group':8} {'tokens':>7}")
        for p in cfg["parts"]:
            lines.append(f"{p['name']:34} {p['group']:8} {p['tokens']:>7}")
        t = cfg["totals"]
        lines.append(f"{'prompt sections':34} {'':8} {t['prompt_sections']:>7}")
        lines.append(f"{'tool schemas':34} {'':8} {t['tools']:>7}")
        lines.append(f"{'platform text total':34} {'':8} {t['platform']:>7}")
        lines.append("")
    kb = doc.get("kb_tool")
    if kb:
        lines.append(
            f"all-on KB search tool (not in the starting set): {kb['name']} = {kb['tokens']}"
        )
        lines.append("")
    if doc.get("model_counts"):
        lines.append("model first-call input_tokens (cold)")
        for model, entry in doc["model_counts"].items():
            counts = ", ".join(
                f"{c}={entry['input_tokens'].get(c)}"
                for c in (*CONFIGS, *EXTRA_CONFIGS)
                if c in entry["input_tokens"]
            )
            lines.append(f"  {model}: {counts}  {entry.get('server') or ''}".rstrip())
        lines.append("")
    lines.append(f"prompt fingerprint: {doc['fingerprints']['prompt']}")
    return "\n".join(lines) + "\n"
