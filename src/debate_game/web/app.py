from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request, status
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, field_validator

from debate_game.config import AgentConfig
from debate_game.domain import Role
from debate_game.web.sessions import (
    DebateSession,
    DebateSessionManager,
    SessionCapacityError,
    StoredEvent,
)

STATIC_DIR = Path(__file__).parent / "static"


class CreateDebateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    motion: str = Field(min_length=1, max_length=2000)
    max_rounds: int = Field(default=5, ge=1, le=50)

    @field_validator("motion")
    @classmethod
    def strip_motion(cls, value: str) -> str:
        motion = value.strip()
        if not motion:
            raise ValueError("motion must not be blank")
        return motion


def _require_session(manager: DebateSessionManager, session_id: str) -> DebateSession:
    session = manager.get(session_id)
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "找不到该对局")
    return session


def _format_sse(event: StoredEvent) -> str:
    payload = json.dumps(event.data, ensure_ascii=False, separators=(",", ":"))
    return f"id: {event.event_id}\nevent: {event.name}\ndata: {payload}\n\n"


def create_app(
    configs: dict[Role, AgentConfig],
    runs_dir: Path,
    max_concurrent: int = 4,
) -> FastAPI:
    app = FastAPI(
        title="LLM Debate Game",
        version="0.2.0",
        docs_url="/api/docs",
        redoc_url=None,
    )
    manager = DebateSessionManager(configs, runs_dir, max_concurrent)
    app.state.session_manager = manager
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/debates", status_code=status.HTTP_201_CREATED)
    def create_debate(body: CreateDebateRequest) -> dict[str, object]:
        try:
            session = manager.create(body.motion, body.max_rounds)
        except SessionCapacityError as exc:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, str(exc)) from exc
        return session.snapshot()

    @app.get("/api/debates/{session_id}")
    def get_debate(session_id: str) -> dict[str, object]:
        return _require_session(manager, session_id).snapshot()

    @app.post("/api/debates/{session_id}/cancel", status_code=status.HTTP_202_ACCEPTED)
    def cancel_debate(session_id: str) -> dict[str, object]:
        session = _require_session(manager, session_id)
        accepted = session.request_cancel()
        return {"accepted": accepted, "status": session.status}

    @app.get("/api/debates/{session_id}/events")
    async def stream_events(
        session_id: str,
        request: Request,
        last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
    ) -> StreamingResponse:
        session = _require_session(manager, session_id)
        try:
            cursor = max(0, int(last_event_id or "0"))
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Last-Event-ID 无效") from exc

        async def event_source() -> AsyncIterator[str]:
            nonlocal cursor
            while True:
                if await request.is_disconnected():
                    return
                events, terminal = await asyncio.to_thread(session.wait_after, cursor, 15.0)
                for event in events:
                    cursor = event.event_id
                    yield _format_sse(event)
                if terminal and not events:
                    return
                if not events:
                    yield ": keep-alive\n\n"

        return StreamingResponse(
            event_source(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    return app
