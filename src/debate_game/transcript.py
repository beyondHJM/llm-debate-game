from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from debate_game.domain import DebateOutcome, GeneratedSpeech, Role, Turn
from debate_game.prompts import PROMPT_VERSION


class JsonlRecorder:
    def __init__(self, runs_dir: Path, motion: str, max_rounds: int) -> None:
        runs_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        self.path = runs_dir / f"{timestamp}-{uuid4().hex[:8]}.jsonl"
        self.path.touch(mode=0o600, exist_ok=False)
        self._write(
            {
                "type": "debate_started",
                "timestamp": datetime.now(UTC).isoformat(),
                "motion": motion,
                "max_rounds": max_rounds,
                "prompt_version": PROMPT_VERSION,
            }
        )

    def record_turn(self, turn: Turn, control: str) -> None:
        self._write(
            {
                "type": "turn",
                "round": turn.round_number,
                "role": turn.role.value,
                "text": turn.text,
                "control": control,
                "elapsed_seconds": round(turn.elapsed_seconds, 3),
                "usage": turn.usage.as_dict(),
            }
        )

    def record_judgment(self, speech: GeneratedSpeech) -> None:
        self._write(
            {
                "type": "judgment",
                "role": Role.JUDGE.value,
                "text": speech.text,
                "control": speech.control.value,
                "elapsed_seconds": round(speech.elapsed_seconds, 3),
                "usage": speech.usage.as_dict(),
            }
        )

    def record_outcome(self, outcome: DebateOutcome) -> None:
        self._write(
            {
                "type": "debate_finished",
                "winner": outcome.winner.value,
                "reason": outcome.reason.value,
                "completed_rounds": outcome.completed_rounds,
            }
        )

    def record_event(self, event_type: str, **data: Any) -> None:
        self._write({"type": event_type, **data})

    def _write(self, record: dict[str, Any]) -> None:
        payload = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(payload + "\n")
            handle.flush()
            os.fsync(handle.fileno())
