"""Candidate GleepGlorp prompts (M36 F1 L09 part B): ``evals/gleepglorp/prompts/<name>.toml``.

A candidate holds the prompt's sections as ``the_one.gleepglorp.prompt`` has them (lower-case
keys: identity, scope, limits, secrets, answering_tools, answering_tool_free, links, style) and
an optional ``web_off_answering`` (the tool-capable answering text used when web access is off).
``--prompt-file`` patches the sections for one invocation through the product module's eval-only
seam and restores them afterwards; nothing in the product reads a file or a setting for it.
"""

from __future__ import annotations

import contextlib
import hashlib
import tomllib
from collections.abc import Iterator
from pathlib import Path

REQUIRED = (
    "identity",
    "scope",
    "limits",
    "secrets",
    "answering_tools",
    "answering_tool_free",
    "links",
    "style",
)
OPTIONAL = ("web_off_answering",)


class PromptFileError(Exception):
    """A candidate prompt file that cannot be used; the message is shown to the operator."""


def load_sections(path: Path) -> dict[str, str]:
    """The candidate's sections keyed by the product module's constant names."""
    try:
        data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise PromptFileError(f"--prompt-file {path}: {exc}") from exc
    unknown = sorted(set(data) - set(REQUIRED) - set(OPTIONAL))
    missing = [k for k in REQUIRED if k not in data]
    if unknown or missing:
        raise PromptFileError(
            f"--prompt-file {path}: "
            + "; ".join(
                m
                for m in (
                    f"missing sections: {', '.join(missing)}" if missing else "",
                    f"unknown keys: {', '.join(unknown)}" if unknown else "",
                )
                if m
            )
        )
    bad = [k for k, v in data.items() if not isinstance(v, str) or not v.strip()]
    if bad:
        raise PromptFileError(f"--prompt-file {path}: not a non-empty string: {', '.join(bad)}")
    return {k.upper(): v for k, v in data.items()}


def digest(path: Path) -> str:
    """A hash of the candidate's sections (not of the file's comments or layout)."""
    sections = load_sections(path)
    blob = "\x00".join(f"{k}={sections[k]}" for k in sorted(sections))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def require_builder_scenarios(scenarios: object) -> None:
    """Refuse unless every scenario is a ``builder = "gleepglorp"`` one."""
    items = scenarios.values() if isinstance(scenarios, dict) else scenarios
    items = list(items)
    if not items or any(getattr(sc, "builder", None) != "gleepglorp" for sc in items):
        raise PromptFileError(
            '--prompt-file applies only to GleepGlorp scenarios (builder = "gleepglorp"); '
            "use it with --scenarios-dir evals/gleepglorp/scenarios or --measure-dir "
            "evals/gleepglorp/measure"
        )


@contextlib.contextmanager
def applied(path: Path | None) -> Iterator[None]:
    """Use the candidate's sections for the block; a no-op when ``path`` is ``None``."""
    if path is None:
        yield
        return
    from the_one.gleepglorp import prompt as gp

    with gp.override_sections(load_sections(path)):
        yield
