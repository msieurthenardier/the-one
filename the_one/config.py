from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_prefix": "THE_ONE_", "env_file": ".env", "extra": "ignore"}

    # LLM
    llm_provider: str = "openai"
    llm_model: str = "gpt-4o"

    # Web
    host: str = "127.0.0.1"
    port: int = 8484

    # Paths
    data_dir: Path = Path.home() / ".the-one"

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
