import asyncio
from pathlib import Path

import httpx

from debate_game.config import AgentConfig
from debate_game.domain import Role
from debate_game.web.app import create_app
from debate_game.web.sessions import DebateSession


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
