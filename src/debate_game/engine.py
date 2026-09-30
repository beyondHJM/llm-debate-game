from __future__ import annotations

from collections.abc import Callable, Sequence

from debate_game.client import Message
from debate_game.context import build_debater_messages, build_judge_messages
from debate_game.domain import (
    Control,
    DebateOutcome,
    EndReason,
    Role,
    Turn,
)
from debate_game.errors import StreamProtocolError
from debate_game.generator import SpeechGenerator
from debate_game.transcript import JsonlRecorder

DebaterMessageBuilder = Callable[[Role, str, Sequence[Turn], int, int], list[Message]]
JudgeMessageBuilder = Callable[[str, Sequence[Turn], int], list[Message]]


class DebateEngine:
    def __init__(
        self,
        generator: SpeechGenerator,
        recorder: JsonlRecorder,
        max_rounds: int,
        debater_message_builder: DebaterMessageBuilder = build_debater_messages,
        judge_message_builder: JudgeMessageBuilder = build_judge_messages,
    ) -> None:
        if max_rounds < 1:
            raise ValueError("max_rounds must be positive")
        self._generator = generator
        self._recorder = recorder
        self._max_rounds = max_rounds
        self._build_debater_messages = debater_message_builder
        self._build_judge_messages = judge_message_builder

    def run(self, motion: str) -> DebateOutcome:
        turns: list[Turn] = []
        for round_number in range(1, self._max_rounds + 1):
            for role in (Role.PRO, Role.CON):
                messages = self._build_debater_messages(
                    role,
                    motion,
                    turns,
                    round_number,
                    self._max_rounds,
                )
                speech = self._generator.generate(role, messages, round_number)
                if speech.control not in (Control.CONTINUE, Control.CONCEDE):
                    raise StreamProtocolError("辩手返回了无效控制结果")
                turn = Turn(
                    round_number=round_number,
                    role=role,
                    text=speech.text,
                    elapsed_seconds=speech.elapsed_seconds,
                    usage=speech.usage,
                )
                turns.append(turn)
                self._recorder.record_turn(turn, speech.control.value)
                if speech.control is Control.CONCEDE:
                    winner = Role.CON if role is Role.PRO else Role.PRO
                    completed = round_number - 1 if role is Role.PRO else round_number
                    outcome = DebateOutcome(
                        winner=winner,
                        reason=EndReason.CONCESSION,
                        completed_rounds=completed,
                        turns=tuple(turns),
                    )
                    self._recorder.record_outcome(outcome)
                    return outcome

        judge_messages = self._build_judge_messages(motion, turns, self._max_rounds)
        judgment = self._generator.generate(Role.JUDGE, judge_messages, None)
        if judgment.control is Control.PRO_WINS:
            winner = Role.PRO
        elif judgment.control is Control.CON_WINS:
            winner = Role.CON
        else:
            raise StreamProtocolError("裁判没有返回唯一胜者")
        self._recorder.record_judgment(judgment)
        outcome = DebateOutcome(
            winner=winner,
            reason=EndReason.JUDGE_VERDICT,
            completed_rounds=self._max_rounds,
            turns=tuple(turns),
            judge_text=judgment.text,
        )
        self._recorder.record_outcome(outcome)
        return outcome
