from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError, field_validator

from debate_game.errors import ConfigurationError


@dataclass(frozen=True, slots=True)
class AgentConfig:
    api_base: str
    model: str
    api_key: str | None
    temperature: float
    max_tokens: int | None
    connect_timeout: float
    read_timeout: float
    retries: int


class AgentConfigDocument(BaseModel):
    """Validated representation of one role's JSON configuration."""

    model_config = ConfigDict(extra="forbid")

    api_base: str
    model: str
    api_key: SecretStr | None = None
    temperature: float = Field(default=0.7, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=64)
    connect_timeout: float = Field(default=10.0, gt=0)
    read_timeout: float = Field(default=180.0, gt=0)
    retries: int = Field(default=1, ge=0, le=5)

    @field_validator("api_base")
    @classmethod
    def normalize_api_base(cls, value: str) -> str:
        normalized = value.strip().rstrip("/")
        if not normalized:
            raise ValueError("api_base must not be empty")
        return normalized

    @field_validator("model")
    @classmethod
    def non_empty_model(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("model must not be empty")
        return normalized

    def to_runtime(self) -> AgentConfig:
        return AgentConfig(
            api_base=self.api_base,
            model=self.model,
            api_key=self.api_key.get_secret_value() if self.api_key is not None else None,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            connect_timeout=self.connect_timeout,
            read_timeout=self.read_timeout,
            retries=self.retries,
        )


def load_agent_config(path: Path) -> AgentConfig:
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ConfigurationError(f"找不到角色配置文件：{path}") from exc
    except OSError as exc:
        raise ConfigurationError(f"无法读取角色配置文件 {path}：{exc}") from exc

    try:
        document = AgentConfigDocument.model_validate_json(raw)
    except ValidationError as exc:
        raise ConfigurationError(f"角色配置文件格式无效 {path}：{exc}") from exc
    return document.to_runtime()
