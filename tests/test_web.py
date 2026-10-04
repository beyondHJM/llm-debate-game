import asyncio
from pathlib import Path

import httpx

from debate_game.config import AgentConfig
from debate_game.domain import Role
from debate_game.events import DebateEvent, EventKind
from debate_game.web.app import create_app
from debate_game.web.sessions import DebateSession, SessionEventSink


def configs() -> dict[Role, AgentConfig]:
    config = AgentConfig(
        api_base="http://127.0.0.1:9",
        model="test-model",
        api_key=None,
        temperature=0.1,
        max_tokens=None,
        connect_timeout=0.1,
        read_timeout=0.1,
        retries=0,
    )
    return {role: config for role in Role}


def test_health_and_index_are_served(tmp_path: Path) -> None:
    async def exercise() -> tuple[httpx.Response, httpx.Response]:
        transport = httpx.ASGITransport(app=create_app(configs(), tmp_path))
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get("/health"), await client.get("/")

    health, index = asyncio.run(exercise())

    assert health.json() == {"status": "ok"}
    assert index.status_code == 200
    assert "AI 辩论场" in index.text
    assert "reasoning-toggle" in index.text
    assert "reasoning-rate" in index.text
    assert "speech-rate" in index.text
    assert "app.js?v=token-rate-2" in index.text
    assert "markdown-body" in index.text


def test_blank_motion_is_rejected_without_starting_session(tmp_path: Path) -> None:
    async def exercise() -> httpx.Response:
        transport = httpx.ASGITransport(app=create_app(configs(), tmp_path))
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.post(
                "/api/debates",
                json={"motion": "   ", "max_rounds": 5},
            )

    response = asyncio.run(exercise())

    assert response.status_code == 422


def test_session_replays_events_after_cursor() -> None:
    session = DebateSession("motion", 5)
    session.publish("first", value=1)
    session.publish("second", value=2)

    events, terminal = session.wait_after(1, 0)

    assert [event.name for event in events] == ["second"]
    assert terminal is False


def test_session_cancel_is_idempotent() -> None:
    session = DebateSession("motion", 5)
    session.mark_running()

    assert session.request_cancel() is True
    assert session.request_cancel() is False
    session.mark_cancelled(None)
    assert session.request_cancel() is False


def test_terminal_event_and_status_are_observed_together() -> None:
    session = DebateSession("motion", 5)

    session.fail("bad response", None)
    events, terminal = session.wait_after(0, 0)

    assert terminal is True
    assert events[-1].name == "debate_failed"
    assert events[-1].data["message"] == "bad response"


def test_web_sink_renders_reasoning_and_speech_markdown_safely() -> None:
    session = DebateSession("motion", 5)
    times = iter((10.0, 10.5, 11.0, 11.25))
    sink = SessionEventSink(session, clock=lambda: next(times))
    sink.emit(DebateEvent(EventKind.THINKING_STARTED, Role.PRO, 1))
    sink.emit(
        DebateEvent(
            EventKind.REASONING_DELTA,
            Role.PRO,
            1,
            {"text": "# Plan\n\n<script>alert(1)</script>"},
        )
    )
    sink.emit(
        DebateEvent(EventKind.REASONING_DELTA, Role.PRO, 1, {"text": "\n\nStep two"})
    )
    sink.emit(DebateEvent(EventKind.SPEECH_STARTED, Role.PRO, 1))
    sink.emit(
        DebateEvent(EventKind.CONTENT_DELTA, Role.PRO, 1, {"text": "**Claim**"})
    )
    sink.emit(DebateEvent(EventKind.CONTENT_DELTA, Role.PRO, 1, {"text": " continued"}))
    sink.emit(DebateEvent(EventKind.SPEECH_FINISHED, Role.PRO, 1))

    events, _ = session.wait_after(0, 0)
    reasoning = [event for event in events if event.name == "reasoning_delta"][-1]
    content = [event for event in events if event.name == "content_delta"][-1]
    started = next(event for event in events if event.name == "speech_started")
    finished = next(event for event in events if event.name == "speech_finished")

    assert "<h1>Plan</h1>" in reasoning.data["html"]
    assert "<script>" not in reasoning.data["html"]
    assert reasoning.data["token_count"] == 2
    assert reasoning.data["token_rate"] == 2.0
    assert started.data["reasoning_token_rate"] == 2.0
    assert "<strong>Claim</strong>" in content.data["html"]
    assert content.data["token_count"] == 2
    assert content.data["token_rate"] == 4.0
    assert finished.data["html"] == content.data["html"]
    assert finished.data["token_rate"] == 4.0
    assert finished.data["reasoning_token_rate"] == 2.0
