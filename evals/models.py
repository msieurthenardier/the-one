"""Model presets, provider rows and effective-value recording (DD4).

Presets come from ``evals/models.toml``. The runner writes one
``LLMProviderConfig`` row per preset into the scratch database and points each
run's agent at it, so the provider is built by the real factory path. Every run
records the effective provider values (thinking, reasoning effort, ``num_ctx``,
temperature) read from the built instance, plus, for Ollama presets, the model
digest and server version.
"""

from __future__ import annotations

import inspect
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_MODELS_FILE = Path(__file__).with_name("models.toml")
TOKEN_TYPES = ("anthropic-plan-token",)


class PresetError(ValueError):
    """The presets file is invalid or names an unknown preset."""


@dataclass(frozen=True)
class Preset:
    name: str
    type: str
    model: str
    base_url: str
    config: dict[str, Any] = field(default_factory=dict)
    # In the set a run selects when no ``--models`` names any (DD9). A non-default preset stays
    # selectable by name. Not part of the preset's fingerprint (``fingerprint.preset_dict``).
    default: bool = True

    @property
    def needs_token(self) -> bool:
        return self.type in TOKEN_TYPES

    @property
    def provider_id(self) -> str:
        return f"ev-{self.name}"


def load_presets(path: Path | None = None) -> dict[str, Preset]:
    path = path or DEFAULT_MODELS_FILE
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise PresetError(f"{path.name}: {exc}") from exc
    out: dict[str, Preset] = {}
    for name, body in data.items():
        if not isinstance(body, dict):
            raise PresetError(f"{path.name}: {name}: must be a table")
        for key in ("type", "model", "base_url"):
            if not isinstance(body.get(key), str) or not body[key]:
                raise PresetError(f"{path.name}: {name}.{key}: is required")
        unknown = set(body) - {"type", "model", "base_url", "config", "default"}
        if unknown:
            raise PresetError(f"{path.name}: {name}.{sorted(unknown)[0]}: unknown field")
        if "default" in body and not isinstance(body["default"], bool):
            raise PresetError(f"{path.name}: {name}.default: must be true or false")
        out[name] = Preset(
            name=name,
            type=body["type"],
            model=body["model"],
            base_url=body["base_url"],
            config=dict(body.get("config", {})),
            default=body.get("default", True),
        )
    return out


def select_presets(all_presets: dict[str, Preset], names: list[str] | None) -> list[Preset]:
    """The named presets, or (no names) only the default ones, in file order."""
    if not names:
        return [p for p in all_presets.values() if p.default]
    out = []
    for n in names:
        if n not in all_presets:
            raise PresetError(
                f"--models: unknown model preset {n!r} (known: {', '.join(all_presets)})"
            )
        out.append(all_presets[n])
    return out


def provider_row(preset: Preset, token: str | None):
    """The ``LLMProviderConfig`` for a preset. The token is the row's ``api_key``
    (encrypted at rest by the repository); it is stored nowhere else."""
    from the_one.db.models import LLMProviderConfig

    if preset.needs_token and not token:
        raise PresetError(f"preset {preset.name!r} needs the plan token")
    return LLMProviderConfig(
        id=preset.provider_id,
        name=f"evals {preset.name}",
        type=preset.type,  # type: ignore[arg-type]
        base_url=preset.base_url,
        api_key=token if preset.needs_token else None,
        config=dict(preset.config),
    )


def effective_values(llm: Any) -> dict[str, Any]:
    """The values the built provider resolves, read from the instance.

    An attribute a provider does not expose is recorded as ``None``, honestly.
    """
    out: dict[str, Any] = {
        "thinking": None,
        "reasoning_effort": None,
        "num_ctx": None,
        "temperature": None,
    }
    if hasattr(llm, "_thinking_enabled_config"):
        from the_one.llm.anthropic_provider import (
            resolve_extended_thinking,
            supports_adaptive_thinking,
        )

        out["thinking"] = resolve_extended_thinking(
            llm._thinking_enabled_config
        ) and supports_adaptive_thinking(llm.model)
    if hasattr(llm, "_reasoning_effort_config"):
        from the_one.llm._request_params import resolve_reasoning_effort

        out["reasoning_effort"] = resolve_reasoning_effort(llm._reasoning_effort_config)
    if hasattr(llm, "_runtime_num_ctx"):
        out["num_ctx"] = llm._runtime_num_ctx or getattr(llm, "_configured_num_ctx", None)
    try:
        # Agent.step passes no temperature, so the provider's own default applies.
        default = inspect.signature(type(llm).stream).parameters["temperature"].default
        out["temperature"] = None if default is inspect.Parameter.empty else default
    except (KeyError, ValueError, TypeError):
        pass
    return out


async def ollama_server_info(
    base_url: str, model: str, *, transport: Any = None, timeout: float = 20.0
) -> dict[str, Any]:
    """The Ollama server version and the model digest. Failures record ``None``."""
    import httpx

    from the_one.llm.ollama_api import strip_v1

    url = strip_v1(base_url)
    info: dict[str, Any] = {"server_version": None, "model_digest": None}
    async with httpx.AsyncClient(timeout=timeout, transport=transport) as client:
        try:
            r = await client.get(f"{url}/api/version")
            r.raise_for_status()
            info["server_version"] = r.json().get("version")
        except Exception:  # noqa: BLE001 - recorded as None, never fatal
            pass
        try:
            r = await client.post(f"{url}/api/show", json={"model": model})
            r.raise_for_status()
            info["model_digest"] = r.json().get("digest")
        except Exception:  # noqa: BLE001
            pass
        if info["model_digest"] is None:
            try:
                r = await client.get(f"{url}/api/tags")
                r.raise_for_status()
                for m in r.json().get("models", []):
                    if m.get("name") == model or m.get("model") == model:
                        info["model_digest"] = m.get("digest")
                        break
            except Exception:  # noqa: BLE001
                pass
    return info
