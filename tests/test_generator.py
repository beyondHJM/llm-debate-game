from collections.abc import Iterator, Sequence

from pytest import MonkeyPatch

from debate_game.client import Message, StreamEvent, StreamEventKind
from debate_game.config import AgentConfig
from debate_game.domain import Control, Role
from debate_game.events import DebateEvent, EventKind
from debate_game.generator import StreamingSpeechGenerator


class RecordingSink:
    def __init__(self) -> None:
        self.events: list[DebateEvent] = []

    def emit(self, event: DebateEvent) -> None:
        self.events.append(event)


class FakeStreamingClient:
    def __init__(self, config: AgentConfig) -> None:
        del config

    def stream_chat(self, messages: Sequence[Message]) -> Iterator[StreamEvent]:
        del messages
        yield StreamEvent(StreamEventKind.REASONING, "# Internal analysis")
        yield StreamEvent(
            StreamEventKind.CONTENT,
            "**Public claim**\n<DEBATE_CONTINUE/>",
        )
        yield StreamEvent(StreamEventKind.DONE)


def test_generator_publishes_reasoning_separately(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr("debate_game.generator.OpenAIStreamingClient", FakeStreamingClient)
    config = AgentConfig(
        api_base="http://model.invalid",
        model="model",
        api_key=None,
        temperature=0.1,
        max_tokens=None,
        connect_timeout=1,
        read_timeout=1,
        retries=0,
    )
    sink = RecordingSink()
    generator = StreamingSpeechGenerator({role: config for role in Role}, sink)

    speech = generator.generate(Role.PRO, [{"role": "user", "content": "motion"}], 1)

    assert speech.text == "**Public claim**"
    assert speech.control is Control.CONTINUE
    assert [event.kind for event in sink.events] == [
        EventKind.THINKING_STARTED,
        EventKind.REASONING_DELTA,
        EventKind.SPEECH_STARTED,
        EventKind.CONTENT_DELTA,
        EventKind.SPEECH_FINISHED,
    ]
    assert sink.events[1].data["text"] == "# Internal analysis"
