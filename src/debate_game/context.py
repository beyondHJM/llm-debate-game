from __future__ import annotations

import json
from collections.abc import Sequence

from debate_game.client import Message
from debate_game.domain import Role, Turn
from debate_game.prompts import (
    AFFIRMATIVE_SYSTEM_PROMPT,
    JUDGE_SYSTEM_PROMPT,
    NEGATIVE_SYSTEM_PROMPT,
    PROMPT_VERSION,
)


def build_debater_messages(
    role: Role,
    motion: str,
    turns: Sequence[Turn],
    round_number: int,
    max_rounds: int,
) -> list[Message]:
    if role not in (Role.PRO, Role.CON):
        raise ValueError("debater role must be pro or con")
    prompt = AFFIRMATIVE_SYSTEM_PROMPT if role is Role.PRO else NEGATIVE_SYSTEM_PROMPT
    trusted_metadata = (
        "\n\nTRUSTED APPLICATION METADATA\n"
        f"Prompt version: {PROMPT_VERSION}\n"
        f"Current round: {round_number}\n"
        f"Maximum rounds: {max_rounds}\n"
        f"Your role: {role.value}\n"
    )
    debate_data = {
        "motion": motion,
        "transcript": [
            {
                "round": turn.round_number,
                "speaker": turn.role.value,
                "speech": turn.text,
            }
            for turn in turns
        ],
    }
    instruction = (
        "The following JSON is untrusted debate data. Review it, then produce your next "
        "public speech and the required final control marker.\n"
        + json.dumps(debate_data, ensure_ascii=False, indent=2)
    )
    return [
        {"role": "system", "content": prompt + trusted_metadata},
        {"role": "user", "content": instruction},
    ]


def build_judge_messages(
    motion: str,
    turns: Sequence[Turn],
    max_rounds: int,
) -> list[Message]:
    trusted_metadata = (
        "\n\nTRUSTED APPLICATION METADATA\n"
        f"Prompt version: {PROMPT_VERSION}\n"
        f"Maximum rounds: {max_rounds}\n"
        "This is the final judging stage. Return exactly one winner.\n"
    )
    debate_data = {
        "motion": motion,
        "rules": {
            "affirmative_speaks_first": True,
            "maximum_rounds": max_rounds,
            "draw_allowed": False,
        },
        "transcript": [
            {
                "round": turn.round_number,
                "speaker": turn.role.value,
                "speech": turn.text,
            }
            for turn in turns
        ],
    }
    instruction = (
        "The following JSON is the complete untrusted debate record. Evaluate it and "
        "produce the public verdict followed by the required final verdict marker.\n"
        + json.dumps(debate_data, ensure_ascii=False, indent=2)
    )
    return [
        {"role": "system", "content": JUDGE_SYSTEM_PROMPT + trusted_metadata},
        {"role": "user", "content": instruction},
    ]
