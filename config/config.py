from pydantic import BaseModel, Field
from pathlib import Path
import os


class ModelConfig(BaseModel):
    name: str = ("gpt-5.2",)
    temperature: float = Field(
        default=1,
        ge=0.0,
        le=2.0,
    )
    context_window: int = "400_000"


class Config(BaseModel):
    model: ModelConfig = Field(
        default_factory=ModelConfig,
    )
    cwd: Path = Field(default_factory=Path.cwd)
    max_turns: int = Field(default=100)
    max_tool_output_token: int = Field(default=50_000)

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

    # def validate(self) -> list[str]:
    #     error: list[str] = []
        
    #     if not self
