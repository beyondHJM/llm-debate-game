import pytest

from debate_game.client import StreamEventKind, build_chat_request, parse_sse_payload
from debate_game.config import AgentConfig
from debate_game.errors import ModelAPIError, StreamProtocolError


def test_parse_reasoning_content_and_public_content() -> None:
    events = parse_sse_payload(
        '{"choices":[{"delta":{"reasoning_content":"private",'
        '"content":"public"}}]}'
    )

    assert [(event.kind, event.text) for event in events] == [
        (StreamEventKind.REASONING, "private"),
        (StreamEventKind.CONTENT, "public"),
    ]


def test_parse_usage() -> None:
    (event,) = parse_sse_payload(
        '{"choices":[],"usage":{"prompt_tokens":10,'
        '"completion_tokens":20,"total_tokens":30}}'
    )

    assert event.kind is StreamEventKind.USAGE
    assert event.usage is not None
    assert event.usage.total_tokens == 30


def test_parse_done() -> None:
    (event,) = parse_sse_payload("[DONE]")
    assert event.kind is StreamEventKind.DONE


def test_invalid_json_is_rejected() -> None:
    with pytest.raises(StreamProtocolError):
        parse_sse_payload("not json")


def test_api_error_is_rejected() -> None:
    with pytest.raises(ModelAPIError, match="bad request"):
        parse_sse_payload('{"error":{"message":"bad request"}}')


def test_max_tokens_is_omitted_by_default() -> None:
    config = AgentConfig(
        api_base="http://localhost/v1",
        model="model",
        api_key=None,
        temperature=0.7,
        max_tokens=None,
        connect_timeout=10,
        read_timeout=180,
        retries=1,
    )

    request = build_chat_request(config, [{"role": "user", "content": "hello"}])

    assert "max_tokens" not in request


def test_explicit_max_tokens_is_preserved() -> None:
    config = AgentConfig(
        api_base="http://localhost/v1",
        model="model",
        api_key=None,
        temperature=0.7,
        max_tokens=2048,
        connect_timeout=10,
        read_timeout=180,
        retries=1,
    )

    request = build_chat_request(config, [{"role": "user", "content": "hello"}])

    assert request["max_tokens"] == 2048
