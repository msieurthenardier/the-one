"""Token measurement of the platform text (DD12).

The platform text is everything the platform, not the operator, puts before the
model on the first call, reported by part:

- prompt sections: the base prompt (or ``CHAT_ONLY_PROMPT`` for the tool-free
  configuration), the rules layer and the notes layer (each minus the operator's
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
import dataclasses
import json
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


def extract_parts(
    system: str,
    schemas: list[dict[str, Any]],
    counter: Counter,
    *,
    persona: str = "",
    rule_texts: list[str] | None = None,
    note_texts: list[str] | None = None,
    date_lines: list[str] | None = None,
) -> list[Part]:
    """Split a first-call system prompt and its tool schemas into platform-text parts.

    Operator-authored text (the persona, rule texts, note texts) is removed by
    subtracting the strings the scenario seeded, never by guessing. Text that no
    known part explains becomes ``other``, so the parts always sum to the total.
    """
    from the_one.agent.config import BASE_PROMPT, CHAT_ONLY_PROMPT
    from the_one.db._notes import NOTES_HEADING
    from the_one.db._rules import RULES_HEADING

    texts: list[tuple[str, str]] = []  # (part name, text counted)
    if system.startswith(BASE_PROMPT):
        head, name = BASE_PROMPT, "base_prompt"
    elif system.startswith(CHAT_ONLY_PROMPT):
        head, name = CHAT_ONLY_PROMPT, "chat_only_prompt"
    else:
        head, name = "", ""
    if head:
        texts.append((name, head))
        rest = system[len(head) :]
        segments = rest.split(SEPARATOR)
        # the base text ends with a newline, so the separator's leading blank lines
        # may be partly part of ``head``: a leading empty piece is not a layer.
        segments = [s for i, s in enumerate(segments) if not (i == 0 and s.strip("\n") == "")]
    else:
        segments = [system] if system else []
    seen: set[str] = set()
    for seg in segments:
        if persona and seg == persona:
            continue  # operator-authored: not platform text
        if seg.startswith(RULES_HEADING) and "rules_layer" not in seen:
            seen.add("rules_layer")
            texts.append(("rules_layer", _without(seg, rule_texts or [])))
        elif seg.startswith(NOTES_HEADING) and "notes_layer" not in seen:
            seen.add("notes_layer")
            texts.append(("notes_layer", _without(seg, note_texts or [])))
        elif seg in (date_lines or []) and "date_line" not in seen:
            seen.add("date_line")
            texts.append(("date_line", seg))
        else:
            texts.append(("other", seg))
    parts: list[Part] = []
    other = [t for n, t in texts if n == "other"]
    for n, t in texts:
        if n != "other":
            parts.append(Part(n, GROUP_PROMPT, counter.count(t), len(t)))
    if other:
        joined = SEPARATOR.join(other)
        parts.append(Part("other", GROUP_PROMPT, counter.count(joined), len(joined)))
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


def _script_for(config: str, kb_query: str):
    from evals import scripted

    if config == "all-on":
        return [scripted.call("search_tools", {"query": kb_query}), scripted.text("ok")]
    return [scripted.text("ok")]


def load_config_scenarios(measure_dir: Path | None = None) -> dict[str, Any]:
    from evals.scenario import parse_scenario

    d = measure_dir or MEASURE_DIR
    return {c: parse_scenario(d / f"{c}.toml", fixtures_root=d / "fixtures") for c in CONFIGS}


async def build_raw_configs(harness: Any, scenarios: dict[str, Any]) -> dict[str, RawConfig]:
    """Build the bare, all-on and tool-free agents with the scripted provider."""
    from evals import scripted
    from evals.harness import RunSpec, expected_date_lines

    out: dict[str, RawConfig] = {}
    for config, sc in scenarios.items():
        holder: list[Any] = []

        def hook(spec: Any, base: str, config: str = config, holder: list[Any] = holder) -> Any:
            p = scripted.ScriptedProvider(_script_for(config, "measurement"))
            holder.append(p)
            return p

        harness.provider_hook = hook
        spec = RunSpec(sc, sc.variants()[0], MEASURE_MODEL)
        attempt = await harness.run_once(spec)
        if attempt.exc is not None:
            raise RuntimeError(
                f"measuring {config}: {type(attempt.exc).__name__}: {attempt.exc}"
            ) from attempt.exc
        rec = attempt.recorder
        if not rec.systems or rec.starting_schemas is None:
            raise RuntimeError(f"measuring {config}: the agent made no model call")
        kb_schema = None
        if config == "all-on":
            for call_ in holder[-1].calls:
                for t in call_["tools"] or []:
                    if schema_name(t).startswith(KB_TOOL_PREFIX):
                        kb_schema = t
            if kb_schema is None:
                raise RuntimeError("measuring all-on: no knowledge-base search tool was found")
        out[config] = RawConfig(
            name=config,
            system=rec.systems[0],
            schemas=rec.starting_schemas,
            kb_schema=kb_schema,
            persona=sc.persona,
            rule_texts=list(sc.rules),
            note_texts=[n.text for n in sc.seeded_notes],
            date_lines=expected_date_lines(sc),
        )
    return out


def measure_configs(raw: dict[str, RawConfig], counter: Counter) -> dict[str, Any]:
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
            "fingerprints": {"prompt": prompt_fingerprint(raw)},
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
    for name in CONFIGS:
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
            counts = ", ".join(f"{c}={entry['input_tokens'].get(c)}" for c in CONFIGS)
            lines.append(f"  {model}: {counts}  {entry.get('server') or ''}".rstrip())
        lines.append("")
    lines.append(f"prompt fingerprint: {doc['fingerprints']['prompt']}")
    return "\n".join(lines) + "\n"
