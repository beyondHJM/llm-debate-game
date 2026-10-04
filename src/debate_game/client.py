from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import httpx

from debate_game.config import AgentConfig
from debate_game.domain import Usage
from debate_game.errors import ModelAPIError, StreamProtocolError

Message = dict[str, str]


class StreamEventKind(StrEnum):
    REASONING = "reasoning"
    CONTENT = "content"
    USAGE = "usage"
    DONE = "done"


@dataclass(frozen=True, slots=True)
class StreamEvent:
    kind: StreamEventKind
    text: str = ""
    usage: Usage | None = None


def build_chat_request(
    config: AgentConfig,
    messages: Sequence[Message],
) -> dict[str, Any]:
    request: dict[str, Any] = {
        "model": config.model,
        "messages": list(messages),
        "temperature": config.temperature,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    if config.max_tokens is not None:
        request["max_tokens"] = config.max_tokens
    if config.chat_template_kwargs:
        request["chat_template_kwargs"] = dict(config.chat_template_kwargs)
    if config.repetition_penalty is not None:
        request["repetition_penalty"] = config.repetition_penalty
    return request


def parse_sse_payload(payload: str) -> tuple[StreamEvent, ...]:
    """Parse one OpenAI SSE data payload into normalized events."""
    if payload.strip() == "[DONE]":
        return (StreamEvent(StreamEventKind.DONE),)

    try:
        document: dict[str, Any] = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise StreamProtocolError("模型返回了无效的 SSE JSON") from exc

    if error := document.get("error"):
        message = error.get("message", str(error)) if isinstance(error, dict) else str(error)
        raise ModelAPIError(f"模型 API 错误：{message}")

    events: list[StreamEvent] = []
    choices = document.get("choices") or []
    if choices:
        delta = choices[0].get("delta") or {}
        reasoning = delta.get("reasoning_content") or delta.get("reasoning")
        content = delta.get("content")
        if reasoning:
            events.append(StreamEvent(StreamEventKind.REASONING, str(reasoning)))
        if content:
            events.append(StreamEvent(StreamEventKind.CONTENT, str(content)))

    if usage_data := document.get("usage"):
        events.append(
            StreamEvent(
                StreamEventKind.USAGE,
                usage=Usage(
                    prompt_tokens=usage_data.get("prompt_tokens"),
                    completion_tokens=usage_data.get("completion_tokens"),
                    total_tokens=usage_data.get("total_tokens"),
                ),
            )
        )
    return tuple(events)


class OpenAIStreamingClient:
    def __init__(self, config: AgentConfig) -> None:
        self._config = config

    def stream_chat(self, messages: Sequence[Message]) -> Iterator[StreamEvent]:
        headers = {"Content-Type": "application/json"}
        if self._config.api_key:
            headers["Authorization"] = f"Bearer {self._config.api_key}"

        request = build_chat_request(self._config, messages)
        timeout = httpx.Timeout(
            connect=self._config.connect_timeout,
            read=self._config.read_timeout,
            write=self._config.connect_timeout,
            pool=self._config.connect_timeout,
        )
        saw_done = False
        try:
            with httpx.Client(timeout=timeout) as client, client.stream(
                "POST",
                f"{self._config.api_base}/chat/completions",
                headers=headers,
                json=request,
            ) as response:
                if response.status_code >= 400:
                    body = response.read().decode("utf-8", errors="replace")[:1000]
                    raise ModelAPIError(
                        f"模型 API 返回 HTTP {response.status_code}: {body}"
                    )
                for line in response.iter_lines():
                    if not line or line.startswith(":"):
                        continue
                    if not line.startswith("data:"):
                        continue
                    payload = line.removeprefix("data:").lstrip()
                    for event in parse_sse_payload(payload):
                        yield event
                        if event.kind is StreamEventKind.DONE:
                            saw_done = True
                            break
                    if saw_done:
                        break
        except httpx.TransportError as exc:
            raise ModelAPIError(f"无法连接模型服务：{exc}") from exc

        if not saw_done:
            raise StreamProtocolError("模型流在 [DONE] 之前意外结束")
