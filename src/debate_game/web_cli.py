from __future__ import annotations

import threading
import webbrowser
from pathlib import Path
from typing import Annotated

import typer
import uvicorn
from rich.console import Console

from debate_game.config import load_agent_config
from debate_game.domain import Role
from debate_game.errors import ConfigurationError
from debate_game.web.app import create_app

app = typer.Typer(
    add_completion=False,
    no_args_is_help=False,
    help="在浏览器中运行 AI 辩论游戏。",
)


@app.command()
def run(
    host: Annotated[str, typer.Option(help="监听地址。")] = "127.0.0.1",
    port: Annotated[int, typer.Option(min=1, max=65535, help="监听端口。")] = 8000,
    max_concurrent: Annotated[
        int,
        typer.Option(min=1, max=32, help="最大并发网页对局数。"),
    ] = 4,
    runs_dir: Annotated[Path, typer.Option(help="JSONL 对局记录目录。")] = Path("runs"),
    pro_config: Annotated[Path, typer.Option(help="正方 JSON 配置。")] = Path(
        "configs/affirmative.json"
    ),
    con_config: Annotated[Path, typer.Option(help="反方 JSON 配置。")] = Path(
        "configs/negative.json"
    ),
    judge_config: Annotated[Path, typer.Option(help="裁判 JSON 配置。")] = Path(
        "configs/judge.json"
    ),
    open_browser: Annotated[
        bool,
        typer.Option("--open-browser/--no-open-browser", help="启动后打开浏览器。"),
    ] = True,
) -> None:
    """Start the local debate web application."""
    console = Console()
    try:
        configs = {
            Role.PRO: load_agent_config(pro_config),
            Role.CON: load_agent_config(con_config),
            Role.JUDGE: load_agent_config(judge_config),
        }
    except ConfigurationError as exc:
        console.print(f"[bold red]配置错误：[/bold red]{exc}")
        raise typer.Exit(2) from exc

    web_app = create_app(configs, runs_dir, max_concurrent)
    url_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    url = f"http://{url_host}:{port}"
    console.print(f"[bold cyan]网页版辩论已启动：[/bold cyan]{url}")
    if open_browser:
        threading.Timer(0.8, webbrowser.open, args=(url,)).start()
    uvicorn.run(web_app, host=host, port=port, log_level="info")


def main() -> None:
    app()
