import os

import anthropic
from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeRemainingColumn,
)

from orchestrator.state import FeedAnalyzerState

CLEANER_PROMPT = (
    "Extract only the content-relevant part of this YouTube Short description. "
    "Remove all promotional content including social media links, follow requests, "
    "discount codes, merchandise links, and sponsor mentions. "
    "Return only the part that describes what the video is actually about. "
    "If there is no content-relevant part, return an empty string.\n\n"
    "Description: {description_raw}"
)

console = Console()


def run_cleaner_agent(state: FeedAnalyzerState) -> FeedAnalyzerState:
    """Strip promotional noise from raw Short descriptions using Claude."""
    console.rule("[bold blue]Stage 3 of 4 — Cleaning")

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    raw_shorts = state.get("raw_shorts", [])
    cleaned_shorts = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold magenta]Cleaning descriptions[/bold magenta]"),
        BarColumn(bar_width=40),
        MofNCompleteColumn(),
        TextColumn("•"),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("cleaning", total=len(raw_shorts))

        for i, short in enumerate(raw_shorts):
            description_raw = short.get("description_raw", "").strip()

            if description_raw:
                try:
                    response = client.messages.create(
                        model="claude-sonnet-4-20250514",
                        max_tokens=512,
                        messages=[
                            {
                                "role": "user",
                                "content": CLEANER_PROMPT.format(description_raw=description_raw),
                            }
                        ],
                    )
                    description_clean = response.content[0].text.strip()
                except Exception as exc:
                    progress.console.log(f"[red]API error on short {i}:[/red] {exc}")
                    description_clean = ""
            else:
                description_clean = ""

            cleaned_shorts.append({**short, "description_clean": description_clean})
            progress.update(task, advance=1)

    console.print(f"[green]✓[/green] Cleaned [bold]{len(cleaned_shorts)}[/bold] Shorts.")
    return {**state, "cleaned_shorts": cleaned_shorts, "current_agent": "cleaner"}
