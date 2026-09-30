from __future__ import annotations

from dataclasses import dataclass

from debate_game.domain import Control, Role
from debate_game.errors import StreamProtocolError

DEBATER_MARKERS = {
    "<DEBATE_CONTINUE/>": Control.CONTINUE,
    "<DEBATE_CONCEDE/>": Control.CONCEDE,
}
JUDGE_MARKERS = {
    '<DEBATE_VERDICT winner="pro"/>': Control.PRO_WINS,
    '<DEBATE_VERDICT winner="con"/>': Control.CON_WINS,
}


@dataclass(frozen=True, slots=True)
class ParsedControl:
    control: Control


class StreamingControlParser:
    """Strip control markers without delaying normal streamed text."""

    def __init__(self, role: Role) -> None:
        self._markers = JUDGE_MARKERS if role is Role.JUDGE else DEBATER_MARKERS
        self._all_markers = {**DEBATER_MARKERS, **JUDGE_MARKERS}
        self._buffer = ""
        self._seen: list[str] = []
        self._post_marker = ""

    def feed(self, text: str) -> tuple[str, ...]:
        if not text:
            return ()
        if self._seen:
            self._post_marker += text
            return ()

        self._buffer += text
        located = self._find_first_marker(self._buffer)
        if located is not None:
            index, marker = located
            visible = self._buffer[:index].rstrip()
            self._seen.append(marker)
            self._post_marker = self._buffer[index + len(marker) :]
            self._buffer = ""
            return (visible,) if visible else ()

        marker_keep = self._partial_marker_suffix_length(self._buffer)
        keep = marker_keep or self._trailing_whitespace_length(self._buffer)
        if marker_keep:
            marker_start = len(self._buffer) - marker_keep
            while marker_start > 0 and self._buffer[marker_start - 1].isspace():
                marker_start -= 1
            keep = len(self._buffer) - marker_start
        if keep:
            visible, self._buffer = self._buffer[:-keep], self._buffer[-keep:]
        else:
            visible, self._buffer = self._buffer, ""
        return (visible,) if visible else ()

    def finish(self) -> ParsedControl:
        if not self._seen:
            raise StreamProtocolError("模型响应缺少最终控制标记")
        if len(self._seen) != 1:
            raise StreamProtocolError("模型响应包含多个控制标记")
        marker = self._seen[0]
        if marker not in self._markers:
            raise StreamProtocolError("模型返回了不属于当前角色的控制标记")
        if self._post_marker.strip():
            raise StreamProtocolError("控制标记不是模型响应的最后内容")
        return ParsedControl(self._markers[marker])

    def _find_first_marker(self, text: str) -> tuple[int, str] | None:
        matches = [
            (text.index(marker), marker)
            for marker in self._all_markers
            if marker in text
        ]
        return min(matches, default=None, key=lambda item: item[0])

    def _partial_marker_suffix_length(self, text: str) -> int:
        longest = 0
        for marker in self._all_markers:
            upper = min(len(text), len(marker) - 1)
            for length in range(1, upper + 1):
                if text.endswith(marker[:length]):
                    longest = max(longest, length)
        return longest

    @staticmethod
    def _trailing_whitespace_length(text: str) -> int:
        return len(text) - len(text.rstrip())
