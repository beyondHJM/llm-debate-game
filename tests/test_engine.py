from collections.abc import Sequence
from pathlib import Path

from debate_game.client import Message
from debate_game.domain import Control, EndReason, GeneratedSpeech, Role
from debate_game.engine import DebateEngine
from debate_game.transcript import JsonlRecorder


class ScriptedGenerator:
    def __init__(self, controls: list[Control]) -> None:
        self.controls = iter(controls)
        self.calls: list[Role] = []

    def generate(
        self,
        role: Role,
        messages: Sequence[Message],
        round_number: int | None,
    ) -> GeneratedSpeech:
        del messages, round_number
        self.calls.append(role)
        return GeneratedSpeech(
            text=f"speech by {role.value}",
            control=next(self.controls),
            elapsed_seconds=0.1,
        )


def recorder(tmp_path: Path) -> JsonlRecorder:
    return JsonlRecorder(tmp_path, "motion", 2)


def test_early_concession_skips_opponent_and_judge(tmp_path: Path) -> None:
    generator = ScriptedGenerator([Control.CONCEDE])
    engine = DebateEngine(generator, recorder(tmp_path), max_rounds=2)

    outcome = engine.run("motion")

    assert generator.calls == [Role.PRO]
    assert outcome.winner is Role.CON
    assert outcome.reason is EndReason.CONCESSION
    assert outcome.completed_rounds == 0


def test_con_concession_after_pro_awards_pro(tmp_path: Path) -> None:
    generator = ScriptedGenerator([Control.CONTINUE, Control.CONCEDE])
    engine = DebateEngine(generator, recorder(tmp_path), max_rounds=2)

    outcome = engine.run("motion")

    assert generator.calls == [Role.PRO, Role.CON]
    assert outcome.winner is Role.PRO
    assert outcome.completed_rounds == 1


def test_round_limit_calls_judge_exactly_once(tmp_path: Path) -> None:
    generator = ScriptedGenerator(
        [
            Control.CONTINUE,
            Control.CONTINUE,
            Control.CONTINUE,
            Control.CONTINUE,
            Control.CON_WINS,
        ]
    )
    engine = DebateEngine(generator, recorder(tmp_path), max_rounds=2)

    outcome = engine.run("motion")

    assert generator.calls == [Role.PRO, Role.CON, Role.PRO, Role.CON, Role.JUDGE]
    assert outcome.winner is Role.CON
    assert outcome.reason is EndReason.JUDGE_VERDICT
    assert outcome.completed_rounds == 2
    assert len(outcome.turns) == 4
