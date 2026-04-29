import os
from pathlib import Path

import typer
from dotenv import load_dotenv
from rich.console import Console

load_dotenv()

from orchestrator.orchestrator import build_graph
from orchestrator.state import FeedAnalyzerState

app = typer.Typer(help="YouTube Shorts feed analyzer — multi-agent CLI tool")
console = Console()


@app.callback()
def _root():
    """YouTube Shorts feed analyzer — multi-agent CLI tool."""

COUNT_MIN = 10
COUNT_MAX = 500
COUNT_DEFAULT = 100


@app.command()
def analyze(
    count: int = typer.Option(
        COUNT_DEFAULT,
        "--count",
        "-n",
        help=f"Number of Shorts to scroll ({COUNT_MIN}–{COUNT_MAX}).",
        min=COUNT_MIN,
        max=COUNT_MAX,
    )
):
    """Scroll YouTube Shorts, analyze with Claude, and generate a categorized report."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        console.print("[bold red]Error:[/bold red] ANTHROPIC_API_KEY not set. Add it to your .env file.")
        raise typer.Exit(code=1)

    console.print(f"[bold cyan]yt-feed-analyzer[/bold cyan] — analyzing [bold]{count}[/bold] Shorts\n")

    initial_state: FeedAnalyzerState = {
        "session_ready": False,
        "target_count": count,
        "raw_shorts": [],
        "checkpoint": 0,
        "cleaned_shorts": [],
        "categorized_shorts": [],
        "current_agent": "",
        "error": None,
        "status": "running",
    }

    graph = build_graph()

    final_state = graph.invoke(initial_state)

    if final_state.get("error"):
        console.print(f"\n[bold red]Run failed:[/bold red] {final_state['error']}")
        raise typer.Exit(code=1)

    # Find latest report
    output_dir = Path("output")
    reports = sorted(output_dir.glob("report_*.md"), reverse=True)
    if reports:
        console.print(f"\n[bold green]Report saved:[/bold green] {reports[0].resolve()}")
    else:
        console.print("\n[yellow]No report file found in output/[/yellow]")


if __name__ == "__main__":
    app()
