from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from debate_game.domain import Role


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


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="DEBATE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    api_base: str = "http://127.0.0.1:18080/v1"
    model: str = "Qwen3-14B-f16.gguf"
    api_key: str | None = None

    pro_api_base: str | None = None
    pro_model: str | None = None
    pro_api_key: str | None = None
    con_api_base: str | None = None
    con_model: str | None = None
    con_api_key: str | None = None
    judge_api_base: str | None = None
    judge_model: str | None = None
    judge_api_key: str | None = None

    max_rounds: int = Field(default=5, ge=1, le=50)
    temperature: float = Field(default=0.7, ge=0, le=2)
    judge_temperature: float = Field(default=0.2, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=64)
    judge_max_tokens: int | None = Field(default=None, ge=64)
    connect_timeout: float = Field(default=10.0, gt=0)
    read_timeout: float = Field(default=180.0, gt=0)
    retries: int = Field(default=1, ge=0, le=5)
    runs_dir: Path = Path("runs")

    @field_validator("api_base", "pro_api_base", "con_api_base", "judge_api_base")
    @classmethod
    def normalize_api_base(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        return value.strip().rstrip("/")

    @field_validator(
        "api_key",
        "pro_api_key",
        "con_api_key",
        "judge_api_key",
        "pro_model",
        "con_model",
        "judge_model",
        "max_tokens",
        "judge_max_tokens",
        mode="before",
    )
    @classmethod
    def empty_string_is_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    def for_role(self, role: Role) -> AgentConfig:
        prefix = role.value
        api_base = getattr(self, f"{prefix}_api_base") or self.api_base
        model = getattr(self, f"{prefix}_model") or self.model
        api_key = getattr(self, f"{prefix}_api_key") or self.api_key
        is_judge = role is Role.JUDGE
        return AgentConfig(
            api_base=api_base.rstrip("/"),
            model=model,
            api_key=api_key,
            temperature=self.judge_temperature if is_judge else self.temperature,
            max_tokens=self.judge_max_tokens if is_judge else self.max_tokens,
            connect_timeout=self.connect_timeout,
            read_timeout=self.read_timeout,
            retries=self.retries,
        )
