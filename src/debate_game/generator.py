from __future__ import annotations

import time
from collections.abc import Sequence
from typing import Protocol

from debate_game.cancellation import CancellationToken
from debate_game.client import (
    Message,
    OpenAIStreamingClient,
    StreamEventKind,
)
from debate_game.config import AgentConfig
from debate_game.domain import GeneratedSpeech, Role, Usage
from debate_game.errors import DebateCancelled, DebateError, StreamProtocolError
from debate_game.events import DebateEvent, EventKind, EventSink
from debate_game.protocol import StreamingControlParser


class SpeechGenerator(Protocol):
    def generate(
        self,
        role: Role,
        messages: Sequence[Message],
        round_number: int | None,
    ) -> GeneratedSpeech: ...


class StreamingSpeechGenerator:
    def __init__(
        self,
        configs: dict[Role, AgentConfig],
        event_sink: EventSink,
        cancellation: CancellationToken | None = None,
    ) -> None:
        self._configs = configs
        self._event_sink = event_sink
        self._cancellation = cancellation or CancellationToken()

    def generate(
        self,
        role: Role,
        messages: Sequence[Message],
        round_number: int | None,
    ) -> GeneratedSpeech:
        config = self._configs[role]
        total_attempts = config.retries + 1
        for attempt in range(1, total_attempts + 1):
            self._cancellation.raise_if_cancelled()
            started = time.monotonic()
            parser = StreamingControlParser(role)
            public_parts: list[str] = []
            usage = Usage()
            received_content = False
            public_output_started = False
            self._emit(EventKind.THINKING_STARTED, role, round_number)
            try:
                client = OpenAIStreamingClient(config)
                for event in client.stream_chat(messages):
                    self._cancellation.raise_if_cancelled()
                    if event.kind is StreamEventKind.REASONING:
                        self._emit(
                            EventKind.REASONING_DELTA,
                            role,
                            round_number,
                            text=event.text,
                        )
                        continue
                    if event.kind is StreamEventKind.USAGE and event.usage is not None:
                        usage = event.usage
                        continue
                    if event.kind is not StreamEventKind.CONTENT:
                        continue
                    received_content = True
                    elapsed = time.monotonic() - started
                    if not public_output_started:
                        self._emit(
                            EventKind.SPEECH_STARTED,
                            role,
                            round_number,
                            thinking_seconds=elapsed,
                        )
                        public_output_started = True
                    for visible in parser.feed(event.text):
                        public_parts.append(visible)
                        self._emit(
                            EventKind.CONTENT_DELTA,
                            role,
                            round_number,
                            text=visible,
                        )

                parsed = parser.finish()
                text = "".join(public_parts).strip()
                if not text:
                    raise StreamProtocolError("模型没有返回可展示的正式内容")
                elapsed = time.monotonic() - started
                self._emit(
                    EventKind.SPEECH_FINISHED,
                    role,
                    round_number,
                    elapsed_seconds=elapsed,
                )
                return GeneratedSpeech(
                    text=text,
                    control=parsed.control,
                    elapsed_seconds=elapsed,
                    usage=usage,
                )
            except DebateCancelled:
                self._emit(EventKind.GENERATION_FAILED, role, round_number)
                raise
            except DebateError:
                self._emit(EventKind.GENERATION_FAILED, role, round_number)
                if received_content or attempt >= total_attempts:
                    raise
                self._emit(
                    EventKind.RETRYING,
                    role,
                    round_number,
                    attempt=attempt,
                    total_attempts=total_attempts,
                )
                time.sleep(min(2 ** (attempt - 1), 4))
        raise AssertionError("unreachable")

    def _emit(
        self,
        kind: EventKind,
        role: Role,
        round_number: int | None,
        **data: object,
    ) -> None:
        self._event_sink.emit(
            DebateEvent(
                kind=kind,
                role=role,
                round_number=round_number,
                data=dict(data),
            )
        )
