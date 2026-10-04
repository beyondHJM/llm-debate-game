from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from debate_game.cancellation import CancellationToken
from debate_game.config import AgentConfig
from debate_game.domain import DebateOutcome, Role
from debate_game.engine import DebateEngine
from debate_game.errors import DebateCancelled, DebateError
from debate_game.events import DebateEvent, EventKind, EventSink
from debate_game.generator import StreamingSpeechGenerator
from debate_game.markdown import create_markdown_renderer
from debate_game.transcript import JsonlRecorder

TERMINAL_STATUSES = frozenset({"finished", "failed", "cancelled"})
ACTIVE_STATUSES = frozenset({"pending", "running", "cancelling"})
MARKDOWN_RENDER_INTERVAL_SECONDS = 0.08


@dataclass(slots=True)
class _TokenRateTracker:
    first_token_at: float | None = None
    token_count: int = 0
    token_rate: float | None = None

    def observe(self, now: float) -> None:
        self.token_count += 1
        if self.first_token_at is None:
            self.first_token_at = now
            return
        elapsed = now - self.first_token_at
        if elapsed > 0:
            self.token_rate = (self.token_count - 1) / elapsed


@dataclass(frozen=True, slots=True)
class StoredEvent:
    event_id: int
    name: str
    data: dict[str, Any]


class DebateSession:
    def __init__(self, motion: str, max_rounds: int) -> None:
        self.id = uuid4().hex
        self.motion = motion
        self.max_rounds = max_rounds
        self.cancellation = CancellationToken()
        self.created_at = datetime.now(UTC)
        self._updated_at = self.created_at
        self._condition = threading.Condition()
        self._events: list[StoredEvent] = []
        self._status = "pending"
        self._winner: str | None = None
        self._record_path: str | None = None
        self._error: str | None = None

    @property
    def status(self) -> str:
        with self._condition:
            return self._status

    def publish(self, name: str, **data: Any) -> StoredEvent:
        with self._condition:
            return self._publish_locked(name, data)

    def mark_running(self) -> None:
        with self._condition:
            self._status = "cancelling" if self.cancellation.is_cancelled else "running"
            self._updated_at = datetime.now(UTC)

    def complete(
        self,
        outcome: DebateOutcome,
        elapsed_seconds: float,
        record_path: Path,
    ) -> None:
        with self._condition:
            self._status = "finished"
            self._winner = outcome.winner.value
            self._record_path = str(record_path)
            self._updated_at = datetime.now(UTC)
            self._publish_locked(
                "debate_finished",
                {
                    "winner": outcome.winner.value,
                    "reason": outcome.reason.value,
                    "completed_rounds": outcome.completed_rounds,
                    "elapsed_seconds": round(elapsed_seconds, 3),
                    "record_path": str(record_path),
                },
            )

    def fail(self, message: str, record_path: Path | None) -> None:
        with self._condition:
            self._status = "failed"
            self._error = message
            self._record_path = str(record_path) if record_path is not None else None
            self._updated_at = datetime.now(UTC)
            self._publish_locked(
                "debate_failed",
                {"message": message, "record_path": self._record_path},
            )

    def mark_cancelled(self, record_path: Path | None) -> None:
        with self._condition:
            self._status = "cancelled"
            self._record_path = str(record_path) if record_path is not None else None
            self._updated_at = datetime.now(UTC)
            self._publish_locked(
                "debate_cancelled",
                {"record_path": self._record_path},
            )

    def request_cancel(self) -> bool:
        with self._condition:
            if self._status not in {"pending", "running"}:
                return False
            self._status = "cancelling"
            self._updated_at = datetime.now(UTC)
        self.cancellation.cancel()
        self.publish("cancellation_requested")
        return True

    def wait_after(
        self,
        last_event_id: int,
        timeout_seconds: float,
    ) -> tuple[tuple[StoredEvent, ...], bool]:
        with self._condition:
            if len(self._events) <= last_event_id and self._status not in TERMINAL_STATUSES:
                self._condition.wait(timeout_seconds)
            events = tuple(self._events[last_event_id:])
            return events, self._status in TERMINAL_STATUSES

    def snapshot(self) -> dict[str, Any]:
        with self._condition:
            return {
                "id": self.id,
                "motion": self.motion,
                "max_rounds": self.max_rounds,
                "status": self._status,
                "winner": self._winner,
                "record_path": self._record_path,
                "error": self._error,
                "created_at": self.created_at.isoformat(),
                "updated_at": self._updated_at.isoformat(),
                "last_event_id": len(self._events),
            }

    def _publish_locked(self, name: str, data: dict[str, Any]) -> StoredEvent:
        event = StoredEvent(len(self._events) + 1, name, data)
        self._events.append(event)
        self._updated_at = datetime.now(UTC)
        self._condition.notify_all()
        return event


class SessionEventSink(EventSink):
    def __init__(
        self,
        session: DebateSession,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._session = session
        self._markdown = create_markdown_renderer()
        self._clock = clock
        self._buffers: dict[tuple[Role, int | None, str], list[str]] = {}
        self._last_rendered_at: dict[tuple[Role, int | None, str], float] = {}
        self._rates: dict[tuple[Role, int | None, str], _TokenRateTracker] = {}

    def emit(self, event: DebateEvent) -> None:
        payload = event.as_dict()
        speech_key = (event.role, event.round_number, "speech")
        reasoning_key = (event.role, event.round_number, "reasoning")

        if event.kind is EventKind.THINKING_STARTED:
            self._buffers[speech_key] = []
            self._buffers[reasoning_key] = []
            self._rates[speech_key] = _TokenRateTracker()
            self._rates[reasoning_key] = _TokenRateTracker()
            self._last_rendered_at.pop(speech_key, None)
            self._last_rendered_at.pop(reasoning_key, None)
        elif event.kind is EventKind.REASONING_DELTA:
            self._append_markdown(
                reasoning_key,
                str(event.data.get("text", "")),
                payload,
                self._clock(),
            )
        elif event.kind is EventKind.CONTENT_DELTA:
            self._append_markdown(
                speech_key,
                str(event.data.get("text", "")),
                payload,
                self._clock(),
            )
        elif event.kind is EventKind.SPEECH_STARTED:
            reasoning = "".join(self._buffers.get(reasoning_key, ()))
            if reasoning:
                payload["reasoning_html"] = self._markdown.render(reasoning)
            self._add_rate(payload, reasoning_key, "reasoning_")
        elif event.kind is EventKind.SPEECH_FINISHED:
            speech = "".join(self._buffers.get(speech_key, ()))
            payload["html"] = self._markdown.render(speech)
            self._add_rate(payload, speech_key)
            self._add_rate(payload, reasoning_key, "reasoning_")

        self._session.publish(event.kind.value, **payload)

    def _append_markdown(
        self,
        key: tuple[Role, int | None, str],
        text: str,
        payload: dict[str, Any],
        now: float,
    ) -> None:
        parts = self._buffers.setdefault(key, [])
        parts.append(text)
        rate = self._rates.setdefault(key, _TokenRateTracker())
        rate.observe(now)
        self._add_rate(payload, key)
        last_rendered = self._last_rendered_at.get(key)
        if last_rendered is None or now - last_rendered >= MARKDOWN_RENDER_INTERVAL_SECONDS:
            payload["html"] = self._markdown.render("".join(parts))
            self._last_rendered_at[key] = now

    def _add_rate(
        self,
        payload: dict[str, Any],
        key: tuple[Role, int | None, str],
        prefix: str = "",
    ) -> None:
        rate = self._rates.get(key)
        if rate is None:
            return
        payload[f"{prefix}token_count"] = rate.token_count
        payload[f"{prefix}token_rate"] = (
            round(rate.token_rate, 2) if rate.token_rate is not None else None
        )


class SessionCapacityError(Exception):
    """Raised when the configured concurrent debate limit is reached."""


class DebateSessionManager:
    def __init__(
        self,
        configs: dict[Role, AgentConfig],
        runs_dir: Path,
        max_concurrent: int = 4,
        retention: timedelta = timedelta(hours=1),
    ) -> None:
        self._configs = configs
        self._runs_dir = runs_dir
        self._max_concurrent = max_concurrent
        self._retention = retention
        self._sessions: dict[str, DebateSession] = {}
        self._lock = threading.Lock()

    def create(self, motion: str, max_rounds: int) -> DebateSession:
        with self._lock:
            self._cleanup_locked()
            active = sum(
                session.status in ACTIVE_STATUSES for session in self._sessions.values()
            )
            if active >= self._max_concurrent:
                raise SessionCapacityError("当前运行中的网页对局数量已达到上限")
            session = DebateSession(motion, max_rounds)
            self._sessions[session.id] = session

        session.publish(
            "debate_started",
            debate_id=session.id,
            motion=motion,
            max_rounds=max_rounds,
        )
        threading.Thread(
            target=self._run_session,
            args=(session,),
            name=f"debate-{session.id[:8]}",
            daemon=True,
        ).start()
        return session

    def get(self, session_id: str) -> DebateSession | None:
        with self._lock:
            return self._sessions.get(session_id)

    def _run_session(self, session: DebateSession) -> None:
        recorder: JsonlRecorder | None = None
        started = time.monotonic()
        try:
            session.mark_running()
            recorder = JsonlRecorder(
                self._runs_dir,
                session.motion,
                session.max_rounds,
            )
            generator = StreamingSpeechGenerator(
                self._configs,
                SessionEventSink(session),
                session.cancellation,
            )
            engine = DebateEngine(generator, recorder, session.max_rounds)
            outcome = engine.run(session.motion)
            session.complete(outcome, time.monotonic() - started, recorder.path)
        except DebateCancelled:
            if recorder is not None:
                recorder.record_event("debate_cancelled")
            session.mark_cancelled(recorder.path if recorder is not None else None)
        except DebateError as exc:
            if recorder is not None:
                recorder.record_event(
                    "debate_failed",
                    error_type=type(exc).__name__,
                    message=str(exc),
                )
            session.fail(str(exc), recorder.path if recorder is not None else None)
        except Exception as exc:  # Defensive boundary for a background worker.
            if recorder is not None:
                recorder.record_event(
                    "debate_failed",
                    error_type=type(exc).__name__,
                    message="网页对局发生内部错误",
                )
            session.fail("网页对局发生内部错误", recorder.path if recorder else None)

    def _cleanup_locked(self) -> None:
        cutoff = datetime.now(UTC) - self._retention
        expired = [
            session_id
            for session_id, session in self._sessions.items()
            if session.status in TERMINAL_STATUSES
            and datetime.fromisoformat(session.snapshot()["updated_at"]) < cutoff
        ]
        for session_id in expired:
            del self._sessions[session_id]
