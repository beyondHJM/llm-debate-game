from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol

from debate_game.domain import Role


class EventKind(StrEnum):
    THINKING_STARTED = "thinking_started"
    REASONING_DELTA = "reasoning_delta"
    SPEECH_STARTED = "speech_started"
    CONTENT_DELTA = "content_delta"
    SPEECH_FINISHED = "speech_finished"
    GENERATION_FAILED = "generation_failed"
    RETRYING = "retrying"


@dataclass(frozen=True, slots=True)
class DebateEvent:
    kind: EventKind
    role: Role
    round_number: int | None
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def as_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "role": self.role.value,
            "round": self.round_number,
            **self.data,
        }


class EventSink(Protocol):
    def emit(self, event: DebateEvent) -> None: ...


class NullEventSink:
    def emit(self, event: DebateEvent) -> None:
        del event
