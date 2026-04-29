import json
import os
from datetime import datetime, timezone
from pathlib import Path

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

from orchestrator.state import FeedAnalyzerState, CategorizerPrivateState

CATEGORIZED_DIR = Path("data/categorized")

CATEGORIZER_PROMPT = (
    "Categorize this YouTube Short into ONE primary category and ONE optional subcategory "
    "based on the following metadata. "
    "Return ONLY a JSON object with fields: "
    "category (string), subcategory (string or null), confidence (float 0-1), reasoning (one sentence).\n\n"
    "Metadata:\n"
    "title={title}\n"
    "channel={channel}\n"
    "hashtags={hashtags}\n"
    "audio_track={audio_track}\n"
    "description={description_clean}"
)

console = Console()


def _parse_category_response(text: str) -> dict:
    """Extract JSON from Claude response, tolerating markdown fences."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return json.loads(text)


def run_categorizer_agent(state: FeedAnalyzerState) -> FeedAnalyzerState:
    """Categorize each cleaned Short using Claude."""
    console.rule("[bold blue]Stage 4 of 4 — Categorizing")

    CATEGORIZED_DIR.mkdir(parents=True, exist_ok=True)

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    cleaned_shorts = state.get("cleaned_shorts", [])

    private: CategorizerPrivateState = {
        "llm_token_usage": 0,
        "failed_shorts": [],
    }

    categorized_shorts = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[bold yellow]Categorizing[/bold yellow]"),
        BarColumn(bar_width=40),
        MofNCompleteColumn(),
        TextColumn("•"),
        TimeRemainingColumn(),
        TextColumn("• [dim]{task.fields[tokens]} tokens[/dim]"),
        console=console,
    ) as progress:
        task = progress.add_task("categorizing", total=len(cleaned_shorts), tokens=0)

        for i, short in enumerate(cleaned_shorts):
            prompt = CATEGORIZER_PROMPT.format(
                title=short.get("title", ""),
                channel=short.get("channel", ""),
                hashtags=short.get("hashtags", []),
                audio_track=short.get("audio_track", ""),
                description_clean=short.get("description_clean", ""),
            )

            try:
                response = client.messages.create(
                    model="claude-sonnet-4-20250514",
                    max_tokens=256,
                    messages=[{"role": "user", "content": prompt}],
                )
                raw_text = response.content[0].text
                private["llm_token_usage"] += response.usage.input_tokens + response.usage.output_tokens

                cat_data = _parse_category_response(raw_text)
                category = cat_data.get("category", "uncategorized")
                subcategory = cat_data.get("subcategory", None)
                confidence = float(cat_data.get("confidence", 0.0))
                reasoning = cat_data.get("reasoning", "")

            except Exception as exc:
                progress.console.log(
                    f"[red]Failed short {i}[/red] ({short.get('title', '')[:30]}): {exc}"
                )
                private["failed_shorts"].append(short)
                category = "uncategorized"
                subcategory = None
                confidence = 0.0
                reasoning = ""

            categorized_shorts.append({
                **short,
                "category": category,
                "subcategory": subcategory,
                "confidence": confidence,
                "reasoning": reasoning,
            })

            progress.update(task, advance=1, tokens=private["llm_token_usage"])

    # Save output
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = CATEGORIZED_DIR / f"categorized_{timestamp}.json"
    out_path.write_text(json.dumps(categorized_shorts, indent=2))

    failed = len(private["failed_shorts"])
    console.print(
        f"[green]✓[/green] Categorized [bold]{len(categorized_shorts)}[/bold] Shorts"
        + (f" ([red]{failed} failed[/red])" if failed else "")
        + f" — [dim]{private['llm_token_usage']:,} tokens used[/dim]"
    )

    return {**state, "categorized_shorts": categorized_shorts, "current_agent": "categorizer"}
