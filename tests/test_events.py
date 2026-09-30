from debate_game.cancellation import CancellationToken
from debate_game.domain import Role
from debate_game.errors import DebateCancelled
from debate_game.events import DebateEvent, EventKind


def test_event_serializes_role_and_round() -> None:
    event = DebateEvent(
        kind=EventKind.CONTENT_DELTA,
        role=Role.CON,
        round_number=2,
        data={"text": "response"},
    )

    assert event.as_dict()["role"] == "con"
    assert event.as_dict()["round"] == 2
    assert event.as_dict()["text"] == "response"


def test_cancellation_token_raises_after_cancel() -> None:
    token = CancellationToken()
    token.raise_if_cancelled()

    token.cancel()

    try:
        token.raise_if_cancelled()
    except DebateCancelled:
        pass
    else:
        raise AssertionError("cancelled token did not raise")
