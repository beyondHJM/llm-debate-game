from __future__ import annotations

from threading import Event

from debate_game.errors import DebateCancelled


class CancellationToken:
    def __init__(self) -> None:
        self._event = Event()

    @property
    def is_cancelled(self) -> bool:
        return self._event.is_set()

    def cancel(self) -> None:
        self._event.set()

    def raise_if_cancelled(self) -> None:
        if self.is_cancelled:
            raise DebateCancelled("对局已由用户停止")
