from __future__ import annotations

import time
from collections.abc import Sequence
from typing import Protocol

from debate_game.client import (
    Message,
    OpenAIStreamingClient,
    StreamEventKind,
)
from debate_game.config import AgentConfig
from debate_game.domain import GeneratedSpeech, Role, Usage
from debate_game.errors import DebateError, StreamProtocolError
from debate_game.protocol import StreamingControlParser
from debate_game.renderer import TerminalRenderer


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
        renderer: TerminalRenderer,
    ) -> None:
        self._configs = configs
        self._renderer = renderer

    def generate(
        self,
        role: Role,
        messages: Sequence[Message],
        round_number: int | None,
    ) -> GeneratedSpeech:
        config = self._configs[role]
        total_attempts = config.retries + 1
        for attempt in range(1, total_attempts + 1):
            started = time.monotonic()
            parser = StreamingControlParser(role)
            public_parts: list[str] = []
            usage = Usage()
            received_content = False
            self._renderer.begin_generation(role, round_number)
            try:
                client = OpenAIStreamingClient(config)
                for event in client.stream_chat(messages):
                    if event.kind is StreamEventKind.REASONING:
                        continue
                    if event.kind is StreamEventKind.USAGE and event.usage is not None:
                        usage = event.usage
                        continue
                    if event.kind is not StreamEventKind.CONTENT:
                        continue
                    received_content = True
                    elapsed = time.monotonic() - started
                    self._renderer.begin_public_output(role, round_number, elapsed)
                    for visible in parser.feed(event.text):
                        public_parts.append(visible)
                        self._renderer.write_public(visible)

                parsed = parser.finish()
                text = "".join(public_parts).strip()
                if not text:
                    raise StreamProtocolError("模型没有返回可展示的正式内容")
                elapsed = time.monotonic() - started
                self._renderer.finish_public_output()
                return GeneratedSpeech(
                    text=text,
                    control=parsed.control,
                    elapsed_seconds=elapsed,
                    usage=usage,
                )
            except DebateError:
                self._renderer.generation_failed()
                if received_content or attempt >= total_attempts:
                    raise
                self._renderer.show_retry(role, attempt, total_attempts)
                time.sleep(min(2 ** (attempt - 1), 4))
        raise AssertionError("unreachable")
