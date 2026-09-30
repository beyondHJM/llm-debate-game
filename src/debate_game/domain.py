from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class Role(StrEnum):
    PRO = "pro"
    CON = "con"
    JUDGE = "judge"

    @property
    def display_name(self) -> str:
        return {
            Role.PRO: "正方 / Affirmative",
            Role.CON: "反方 / Negative",
            Role.JUDGE: "裁判 / Judge",
        }[self]


class Control(StrEnum):
    CONTINUE = "continue"
    CONCEDE = "concede"
    PRO_WINS = "pro_wins"
    CON_WINS = "con_wins"


class EndReason(StrEnum):
    CONCESSION = "concession"
    JUDGE_VERDICT = "judge_verdict"


@dataclass(frozen=True, slots=True)
class Usage:
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None

    def as_dict(self) -> dict[str, int | None]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
        }


@dataclass(frozen=True, slots=True)
class Turn:
    round_number: int
    role: Role
    text: str
    elapsed_seconds: float
    usage: Usage = field(default_factory=Usage)


@dataclass(frozen=True, slots=True)
class GeneratedSpeech:
    text: str
    control: Control
    elapsed_seconds: float
    usage: Usage = field(default_factory=Usage)


@dataclass(frozen=True, slots=True)
class DebateOutcome:
    winner: Role
    reason: EndReason
    completed_rounds: int
    turns: tuple[Turn, ...]
    judge_text: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
