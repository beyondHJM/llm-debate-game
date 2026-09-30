import pytest

from debate_game.domain import Control, Role
from debate_game.errors import StreamProtocolError
from debate_game.protocol import StreamingControlParser


def test_debater_marker_is_stripped_across_chunks() -> None:
    parser = StreamingControlParser(Role.PRO)
    visible: list[str] = []
    for chunk in ("A strong ", "argument.\n<DEBATE_", "CONTINUE/>"):
        visible.extend(parser.feed(chunk))

    result = parser.finish()

    assert "".join(visible) == "A strong argument."
    assert result.control is Control.CONTINUE


def test_judge_verdict_is_stripped() -> None:
    parser = StreamingControlParser(Role.JUDGE)
    visible = parser.feed('Affirmative wins.\n<DEBATE_VERDICT winner="pro"/>\n')

    result = parser.finish()

    assert "".join(visible) == "Affirmative wins."
    assert result.control is Control.PRO_WINS


def test_missing_marker_is_rejected() -> None:
    parser = StreamingControlParser(Role.CON)
    parser.feed("No control marker")

    with pytest.raises(StreamProtocolError, match="缺少"):
        parser.finish()


def test_wrong_role_marker_is_rejected_without_leaking_marker() -> None:
    parser = StreamingControlParser(Role.PRO)
    visible = parser.feed('Text\n<DEBATE_VERDICT winner="con"/>')

    assert "DEBATE_VERDICT" not in "".join(visible)
    with pytest.raises(StreamProtocolError, match="当前角色"):
        parser.finish()


def test_content_after_marker_is_rejected_and_hidden() -> None:
    parser = StreamingControlParser(Role.CON)
    visible = parser.feed("Speech\n<DEBATE_CONTINUE/>should stay hidden")

    assert "hidden" not in "".join(visible)
    with pytest.raises(StreamProtocolError, match="最后内容"):
        parser.finish()
