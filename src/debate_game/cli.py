from __future__ import annotations

import time
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError
from rich.console import Console
from rich.prompt import Prompt

from debate_game.config import Settings
from debate_game.domain import Role
from debate_game.engine import DebateEngine
from debate_game.errors import DebateError
from debate_game.generator import StreamingSpeechGenerator
from debate_game.renderer import TerminalRenderer
from debate_game.transcript import JsonlRecorder

app = typer.Typer(
    add_completion=False,
    no_args_is_help=False,
    help="有限轮、三角色、流式终端 AI 辩论游戏。",
)


def _validate_motion(value: str) -> str:
    motion = value.strip()
    if not motion:
        raise typer.BadParameter("辩题不能为空")
    if len(motion) > 2000:
        raise typer.BadParameter("辩题不能超过 2000 个 Unicode 字符")
    return motion


@app.command()
def run(
    topic: Annotated[
        str | None,
        typer.Option("--topic", "-t", help="辩题；省略时在终端交互输入。"),
    ] = None,
    max_rounds: Annotated[
        int | None,
        typer.Option("--max-rounds", "-r", min=1, max=50, help="最大完整轮回数。"),
    ] = None,
    runs_dir: Annotated[
        Path | None,
        typer.Option("--runs-dir", help="JSONL 对局记录目录。"),
    ] = None,
) -> None:
    """Start a new debate."""
    console = Console()
    try:
        settings = Settings()
    except ValidationError as exc:
        console.print(f"[bold red]配置错误：[/bold red]{exc}")
        raise typer.Exit(2) from exc

    effective_rounds = max_rounds or settings.max_rounds
    renderer = TerminalRenderer(console)
    renderer.show_welcome(effective_rounds)
    raw_motion = topic if topic is not None else Prompt.ask("请输入辩题")
    try:
        motion = _validate_motion(raw_motion)
    except typer.BadParameter as exc:
        console.print(f"[bold red]输入错误：[/bold red]{exc.message}")
        raise typer.Exit(2) from exc

    recorder = JsonlRecorder(runs_dir or settings.runs_dir, motion, effective_rounds)
    configs = {role: settings.for_role(role) for role in Role}
    generator = StreamingSpeechGenerator(configs, renderer)
    engine = DebateEngine(generator, recorder, effective_rounds)
    started = time.monotonic()
    try:
        outcome = engine.run(motion)
    except KeyboardInterrupt:
        recorder.record_event("debate_interrupted")
        console.print("\n[yellow]对局已由用户中断。[/yellow]")
        renderer.show_record_path(str(recorder.path))
        raise typer.Exit(130) from None
    except DebateError as exc:
        recorder.record_event("debate_failed", error_type=type(exc).__name__, message=str(exc))
        console.print(f"\n[bold red]对局失败：[/bold red]{exc}")
        renderer.show_record_path(str(recorder.path))
        raise typer.Exit(1) from exc

    renderer.show_outcome(outcome, time.monotonic() - started)
    renderer.show_record_path(str(recorder.path))


def main() -> None:
    app()
