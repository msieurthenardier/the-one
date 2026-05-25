from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_prefix": "THE_ONE_", "env_file": ".env", "extra": "ignore"}

    # Web
    host: str = "127.0.0.1"
    port: int = 8484

    # Dev mode (gates the mock provider type)
    dev_mode: bool = False

    # Paths
    data_dir: Path = Path.home() / ".the-one"

    # M11 F7 L7: inference provider + model for the engagement-policy gate.
    # When BOTH are set, the L8 dispatcher gate at decision-tree step 4 uses
    # this provider+model for the inference call ("does this message warrant
    # an agent response?"). When BOTH are unset, falls back to the routed
    # agent's configured LLM (the dispatcher passes the agent's llm_model
    # alongside the provider id). Partial pairs (only id OR only model set)
    # are operator misconfiguration — surfaced as silence per Flight DD §9's
    # safe-default discipline (the inference helper logs + returns None).
    # Backed by env vars ``THE_ONE_INFERENCE_PROVIDER_CONFIG_ID`` and
    # ``THE_ONE_INFERENCE_MODEL``.
    inference_provider_config_id: str | None = None
    inference_model: str | None = None

    @property
    def agents_dir(self) -> Path:
        return self.data_dir / "agents"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "the-one.db"

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)


_settings: Settings | None = None


def __getattr__(name: str) -> Settings:
    """PEP 562 lazy accessor: instantiate Settings() on first access to
    `settings`, then cache. Defers env-var read until after any
    conftest-level environment mutation has run.
    """
    if name == "settings":
        global _settings
        if _settings is None:
            _settings = Settings()
        return _settings
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
