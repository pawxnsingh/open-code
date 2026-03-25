from pydantic import BaseModel, Field
from pathlib import Path
from typing import Any
import os


class ModelConfig(BaseModel):
    # alias "model" is provided for convenience when reading from config files
    # so users can specify the model by writing `model = "gpt-5.4"`.
    name: str = Field(default="gpt-5.2", alias="model")
    temperature: float = Field(
        default=1,
        ge=0.0,
        le=2.0,
    )
    context_window: int = "400_000"


class ShellEnvironmentPolicy(BaseModel):
    ignore_default_excludes: bool = False
    exclude_patterns: list = Field(
        default_factory=lambda: ["*KEY*", "*SECRET*", "*TOKEN*"]
    )
    set_vars: dict[str, Any] = Field(default_factory=dict)


class Config(BaseModel):
    model: ModelConfig = Field(
        default_factory=ModelConfig,
    )
    cwd: Path = Field(default_factory=Path.cwd)
    shell_environment: ShellEnvironmentPolicy = Field(
        default_factory=ShellEnvironmentPolicy
    )
    max_turns: int = Field(default=100)

    developer_instructions: str | None = None
    user_instructions: str | None = None

    debug: bool = Field(default=False)

    @property
    def api_key(self) -> str:
        return os.environ.get("AZURE_OPENAI_API_KEY")

    @property
    def base_url(self) -> str:
        return os.environ.get("AZURE_OPENAI_ENDPOINT")

    @property
    def api_version(self) -> str:
        return os.environ.get("AZURE_OPENAI_API_VERSION")

    @property
    def model_name(self) -> str:
        return self.model.name

    @model_name.setter
    def model_name(self, value: str) -> None:
        self.model.name = value

    @property
    def temperature(self) -> float:
        return self.model.temperature

    @temperature.setter
    def temperature(self, value: float) -> None:
        self.model.temperature = value

    def validate(self) -> list[str]:
        error: list[str] = []

        if not self.api_key:
            error.append("AZURE_OPENAI_API_KEY is not present in the .env")

        if not self.base_url:
            error.append("AZURE_OPENAI_ENDPOINT is not present in the .env")

        if not self.api_version:
            error.append("AZURE_OPENAI_API_VERSION is not present in the .env")

        if not self.cwd.exists():
            error.append(f"current working directory, dont exist, {self.cwd}")

        return error
