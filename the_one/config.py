from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_prefix": "THE_ONE_", "env_file": ".env", "extra": "ignore"}

    # LLM
    llm_provider: str = "ollama"
    llm_model: str = "qwen2.5:7b"
    llm_base_url: str = "http://localhost:11434/v1"

    # Web
    host: str = "127.0.0.1"
    port: int = 8484

    # Paths
    data_dir: Path = Path.home() / ".the-one"
    workspace_dir: Path = Path("/workspace")

    # Concourse CI
    concourse_target: str = "local"
    concourse_pipeline: str = "the-one"

    @property
    def agents_dir(self) -> Path:
        return self.data_dir / "agents"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "the-one.db"

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
