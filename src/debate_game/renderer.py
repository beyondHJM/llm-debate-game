from __future__ import annotations

from rich.console import Console
from rich.status import Status

from debate_game.domain import DebateOutcome, EndReason, Role
from debate_game.events import DebateEvent, EventKind


class TerminalRenderer:
    def __init__(self, console: Console | None = None) -> None:
        self.console = console or Console()
        self._status: Status | None = None
        self._speaking = False

    def show_welcome(self, max_rounds: int) -> None:
        self.console.print("[bold cyan]AI 自动辩论场[/bold cyan]")
        self.console.print(
            f"正方先手，最多 [bold]{max_rounds}[/bold] 个完整轮回；无人认输则由裁判裁决。"
        )

    def emit(self, event: DebateEvent) -> None:
        if event.kind is EventKind.THINKING_STARTED:
            self.begin_generation(event.role, event.round_number)
        elif event.kind is EventKind.SPEECH_STARTED:
            self.begin_public_output(
                event.role,
                event.round_number,
                float(event.data["thinking_seconds"]),
            )
        elif event.kind is EventKind.CONTENT_DELTA:
            self.write_public(str(event.data["text"]))
        elif event.kind is EventKind.SPEECH_FINISHED:
            self.finish_public_output()
        elif event.kind is EventKind.GENERATION_FAILED:
            self.generation_failed()
        elif event.kind is EventKind.RETRYING:
            self.show_retry(
                event.role,
                int(event.data["attempt"]),
                int(event.data["total_attempts"]),
            )

    def begin_generation(self, role: Role, round_number: int | None) -> None:
        self._speaking = False
        if role is Role.JUDGE:
            text = "[bold yellow]裁判评议中...[/bold yellow]"
        else:
            text = f"[bold]{role.display_name} 第 {round_number} 轮思考中...[/bold]"
        self._status = self.console.status(text, spinner="dots")
        self._status.start()

    def begin_public_output(
        self,
        role: Role,
        round_number: int | None,
        thinking_seconds: float,
    ) -> None:
        if self._speaking:
            return
        self._stop_status()
        if role is Role.JUDGE:
            heading = "裁判裁决 / Judge's Verdict"
            color = "yellow"
        else:
            heading = f"{role.display_name} · 第 {round_number} 轮"
            color = "green" if role is Role.PRO else "magenta"
        self.console.print(
            f"\n[bold {color}]{heading}[/bold {color}] "
            f"[dim](思考 {thinking_seconds:.1f}s)[/dim]"
        )
        self._speaking = True

    def write_public(self, text: str) -> None:
        self.console.print(text, end="", markup=False, highlight=False, soft_wrap=True)

    def finish_public_output(self) -> None:
        self._stop_status()
        if self._speaking:
            self.console.print()
        self._speaking = False

    def generation_failed(self) -> None:
        self._stop_status()
        if self._speaking:
            self.console.print()
        self._speaking = False

    def show_retry(self, role: Role, attempt: int, total_attempts: int) -> None:
        self.console.print(
            f"[yellow]{role.display_name} 请求失败，将重试 "
            f"({attempt}/{total_attempts})...[/yellow]"
        )

    def show_outcome(self, outcome: DebateOutcome, elapsed_seconds: float) -> None:
        self.console.rule("[bold cyan]辩论结束[/bold cyan]")
        reason = "对方主动认输" if outcome.reason is EndReason.CONCESSION else "裁判终局裁决"
        self.console.print(f"胜者：[bold green]{outcome.winner.display_name}[/bold green]")
        self.console.print(
            f"结束方式：{reason}；完成轮回：{outcome.completed_rounds}；"
            f"总耗时：{elapsed_seconds:.1f}s"
        )

    def show_record_path(self, path: str) -> None:
        self.console.print(f"[dim]对局记录：{path}[/dim]")

    def _stop_status(self) -> None:
        if self._status is not None:
            self._status.stop()
            self._status = None
